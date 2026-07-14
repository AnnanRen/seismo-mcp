"""Self-contained helpers for obs-raw-mcp.

Inlined (no shared-package dependency) so this server publishes and installs
standalone via ``uvx obs-raw-mcp``.

IGGCAS OBS raw format (Wang Yuan, IGGCAS) is a proprietary binary format
written by the institute's ocean-bottom seismometers. Two companion programs
convert it:

  - ``graw2sac``  raw → SAC (continuous, all four components: bh1/bh2/bhz/hyd)
  - ``raw2su``    raw → SU  (per-shot gathers, requires a UKOOA shot file)

Unlike CWP-SU programs (which follow stdin/stdout pipe discipline), raw2su
and graw2sac operate on **disk files**: you point them at a merged raw file
via ``rawfile=`` and they write the converted artifacts next to it in the
working directory. So :func:`run_raw` below is a plain ``subprocess.run``
with a ``cwd`` argument — no stdin/stdout plumbing.

One quirk worth noting: the programs require the raw file's name to be a
**hex number** (e.g. ``41ACED87.453``) — they parse the hex prefix to detect
the format. So when a station's raw data is split across many ~11.5 h files
that must be merged first, the merged file has to keep the *first* file's
hex name, or the programs refuse with "input filename is not a Hex number".
"""

from __future__ import annotations

import re
import shutil
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TIMEOUT = 600  # converting a multi-day merged file can take a minute


# ---------------------------------------------------------------------------
# Result type (mirrors cwp-su-mcp's SUResult shape)
# ---------------------------------------------------------------------------

@dataclass
class RawResult:
    """Outcome of a raw2su / graw2sac invocation."""

    returncode: int
    stdout: str   # raw2su/graw2sac rarely write to stdout; diagnostics go to stderr
    stderr: str   # human-readable progress / errors (e.g. "writing BHX data to sac file ...")
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def error_text(self) -> str:
        """A context-friendly error summary (call only when not ok)."""
        tag = "TIMEOUT" if self.timed_out else f"exit {self.returncode}"
        return f"failed ({tag}):\n{self.stderr.strip()[:2000]}"


# ---------------------------------------------------------------------------
# Environment detection
# ---------------------------------------------------------------------------

def detect_obs_raw() -> dict:
    """Locate the IGGCAS ``raw2su`` and ``graw2sac`` programs on PATH.

    Both are required. Returns a dict with ``available`` (True only when BOTH
    are found), each program's resolved path, and a ``detail`` status line.
    """
    raw2su = shutil.which("raw2su")
    graw2sac = shutil.which("graw2sac")
    if raw2su and graw2sac:
        return {
            "available": True,
            "raw2su": raw2su,
            "graw2sac": graw2sac,
            "detail": f"raw2su and graw2sac found on PATH",
        }
    missing = [n for n, p in (("raw2su", raw2su), ("graw2sac", graw2sac)) if not p]
    return {
        "available": False,
        "raw2su": raw2su,
        "graw2sac": graw2sac,
        "detail": (
            f"{', '.join(missing)} not found on PATH. Install the IGGCAS "
            "raw2su/graw2sac tools (Wang Yuan, IGGCAS) and ensure both are "
            "executable on your PATH."
        ),
    }


# ---------------------------------------------------------------------------
# Subprocess chokepoint
# ---------------------------------------------------------------------------

def run_raw(
    program: str,
    args: list[str],
    *,
    cwd: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> RawResult:
    """Run ``raw2su`` or ``graw2sac`` in *cwd* with *args*.

    Both programs read the input via the ``rawfile=`` argument (a path
    relative to *cwd*) and write their output files into *cwd*. There is no
    stdin/stdout pipe to manage — unlike CWP-SU. The returned ``stderr``
    captures the progress log the programs print (sample rates, time
    corrections, "writing BHX data to sac file ..." lines).
    """
    info = detect_obs_raw()
    if not info["available"]:
        raise FileNotFoundError(info["detail"])

    exe = shutil.which(program)
    if exe is None:
        raise FileNotFoundError(
            f"{program!r} not found on PATH. {info['detail']}"
        )

    try:
        proc = subprocess.run(  # noqa: S603 — exe resolved via shutil.which
            [exe, *args],
            capture_output=True,
            timeout=timeout,
            cwd=cwd,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return RawResult(returncode=-1, stdout="", stderr="", timed_out=True)

    return RawResult(
        returncode=proc.returncode,
        stdout=(proc.stdout or b"").decode("utf-8", errors="replace"),
        stderr=(proc.stderr or b"").decode("utf-8", errors="replace"),
    )


# ---------------------------------------------------------------------------
# DATAFILE.LST / LOG parsing (parameter extraction)
# ---------------------------------------------------------------------------

def parse_datafile_lst(station_dir: Path) -> tuple[list[str], int]:
    """Extract the ordered raw-file list and sampling rate from DATAFILE.LST.

    Each line of DATAFILE.LST looks like::

        0001 2016-06-22 14:54:07.0263 1:\\41ACED87.453 250sps

    Column 4 is the raw file path (we take the basename after the backslash);
    column 5 carries the sampling rate as ``<N>sps``. Files are returned in
    the order they appear (which is chronological — must be preserved when
    merging).
    """
    lst_path = station_dir / "DATAFILE.LST"
    if not lst_path.exists():
        raise FileNotFoundError(f"No DATAFILE.LST in {station_dir}")

    files: list[str] = []
    sps: int | None = None
    for line in lst_path.read_text(errors="replace").splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        raw_name = parts[3].split("\\")[-1]
        # raw filenames are 8-hex-dot-3-hex, e.g. 41ACED87.453
        if re.match(r"^[0-9A-Fa-f]{8}\.[0-9A-Fa-f]{3}$", raw_name):
            files.append(raw_name)
        m = re.search(r"(\d+)sps", parts[4])
        if m:
            sps = int(m.group(1))

    if not files:
        raise ValueError(f"DATAFILE.LST in {station_dir} has no valid raw filenames")
    if sps is None:
        raise ValueError(f"DATAFILE.LST in {station_dir} has no sampling rate")
    return files, sps


def parse_tc(station_dir: Path) -> int:
    """Extract the Time-Control value from ``A201606.LOG``.

    The LOG may record several sampling start events (the instrument can be
    restarted); we take the **last** TC, which corresponds to the actual
    recording session that produced the files in DATAFILE.LST.
    """
    log_path = station_dir / "A201606.LOG"
    if not log_path.exists():
        raise FileNotFoundError(f"No A201606.LOG in {station_dir}")
    tc: int | None = None
    for line in log_path.read_text(errors="replace").splitlines():
        m = re.search(r"TC=(\d+)", line)
        if m:
            tc = int(m.group(1))
    if tc is None:
        raise ValueError(f"No TC= value in {log_path}")
    return tc


def find_station_dir(station: str, raw_root: Path) -> Path:
    """Resolve a station id (e.g. ``C10``) to its directory (``C10_A36``).

    Station directories are named ``<id>_<suffix>``; the suffix is an
    instrument serial. Directories ending in ``_ex`` (excluded) or
    ``_lost`` are skipped.
    """
    candidates = [
        p for p in raw_root.glob(f"{station}_*")
        if p.is_dir() and not p.name.endswith(("_ex", "_lost"))
    ]
    if not candidates:
        raise FileNotFoundError(
            f"No station directory matching {station}_* in {raw_root} "
            "(directories ending in _ex/_lost are skipped)."
        )
    return candidates[0]


# ---------------------------------------------------------------------------
# Raw-file merging + SAC npts fix (the two mechanical ops every conversion needs)
# ---------------------------------------------------------------------------

def merge_raw_files(raw_files: list[str], station_dir: Path, output: Path) -> int:
    """Binary-concatenate *raw_files* (in order) into *output*.

    Returns total bytes written. The merged file MUST keep the first raw
    file's hex name — raw2su/graw2sac refuse non-hex filenames.
    """
    size = 0
    with open(output, "wb") as out:
        for rf in raw_files:
            src = station_dir / rf
            if not src.exists():
                raise FileNotFoundError(f"raw file missing: {src}")
            with open(src, "rb") as inp:
                while True:
                    chunk = inp.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    size += len(chunk)
    return size


def fix_sac_npts(path: Path) -> tuple[int, int]:
    """Repair the SAC ``npts`` header word written by graw2sac.

    graw2sac (V3.0) has a fixed bug: the ``npts`` field (byte offset 316,
    little-endian int32) is ~44 smaller than the actual sample count in the
    data block, which makes obspy reject the file with
    "Actual and theoretical file size are inconsistent". This helper recomputes
    ``npts`` from ``(filesize - 632) // 4`` and rewrites the header.

    Returns ``(old_npts, new_npts)``.
    """
    size = path.stat().st_size
    data_size = size - 632  # SAC binary header is 632 bytes
    if data_size % 4 != 0:
        raise ValueError(f"data block not a multiple of 4 bytes: {data_size}")
    npts_actual = data_size // 4
    with open(path, "r+b") as f:
        f.seek(316)
        old = struct.unpack("<i", f.read(4))[0]
        if old != npts_actual:
            f.seek(316)
            f.write(struct.pack("<i", npts_actual))
    return old, npts_actual
