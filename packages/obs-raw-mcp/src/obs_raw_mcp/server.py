"""OBS raw MCP server.

Wraps IGGCAS's proprietary-format conversion tools (``graw2sac`` and
``raw2su``, by Wang Yuan at IGGCAS) as MCP tools. Both programs convert the
institute's ocean-bottom-seismometer raw binary into a standard seismic
format:

  - ``graw2sac`` → SAC (continuous recording, four components)
  - ``raw2su``   → SU  (per-shot gathers, requires a UKOOA shot file)

Each tool here follows the same shape: locate the station directory → merge
its raw shards (a multi-day deployment is split into ~11.5 h files) → run
the converter in an isolated working directory → fix the graw2sac npts bug
→ move the outputs to the requested location → return a one-line summary.
Binary trace data never enters the model context; tools return file paths.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile

from mcp.server.fastmcp import FastMCP

from ._helpers import (
    DEFAULT_TIMEOUT,
    RawResult,
    detect_obs_raw,
    find_station_dir,
    fix_sac_npts as _fix_sac_npts_impl,
    merge_raw_files,
    parse_datafile_lst,
    parse_tc,
    run_raw,
)

mcp = FastMCP("obs-raw-mcp")


# ---------------------------------------------------------------------------
# Tool 1: diagnose_environment
# ---------------------------------------------------------------------------
@mcp.tool()
def diagnose_environment() -> str:
    """Report whether ``raw2su`` and ``graw2sac`` are installed and on PATH.

    Call this first to confirm the backend is ready. Both programs are
    required (they produce different output formats). Returns a status line.
    """
    info = detect_obs_raw()
    if not info["available"]:
        return f"ERROR: {info['detail']}"
    return (
        f"OK: {info['detail']} "
        f"(raw2su={info['raw2su']}, graw2sac={info['graw2sac']})"
    )


# ---------------------------------------------------------------------------
# Tool 2: scan_station — auto-extract sps / TC / raw-file list
# ---------------------------------------------------------------------------
@mcp.tool()
def scan_station(raw_root: str, station: str) -> str:
    """Scan an OBS station directory and auto-extract every conversion parameter.

    Resolves ``<raw_root>/<station>_*`` to the station directory (e.g.
    ``C10`` → ``C10_A36``), then reads ``DATAFILE.LST`` for the sampling rate
    and ordered raw-file list, and ``A201606.LOG`` for the Time-Control value.
    Directories ending in ``_ex`` (excluded) or ``_lost`` are skipped.

    Returns a JSON string with ``sps``, ``TC``, ``n_raw_files``, the raw-file
    list, and the resolved ``station_dir`` — everything the other tools need.
    """
    station_dir = find_station_dir(station, _expand(raw_root))
    raw_files, sps = parse_datafile_lst(station_dir)
    tc = parse_tc(station_dir)
    return json.dumps({
        "station": station,
        "station_dir": str(station_dir),
        "sps": sps,
        "TC": tc,
        "n_raw_files": len(raw_files),
        "raw_files": raw_files,
    }, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tool 3: raw_to_sac — raw → continuous SAC (passive-source HVSR use case)
# ---------------------------------------------------------------------------
@mcp.tool()
def raw_to_sac(
    station_dir: str,
    output_dir: str,
    sps: int,
    tc: int,
    station_name: str,
    *,
    rfms: str = "0001",
) -> str:
    """Convert an OBS station's raw data to continuous SAC files (four components).

    Merges the station's raw shards (in DATAFILE.LST order, keeping the first
    file's hex name — required by graw2sac), runs ``graw2sac`` in an isolated
    workdir, fixes the graw2sac npts header bug, and moves the four SAC
    components (``bh1``, ``bh2``, ``bhz``, ``hyd``) to ``<output_dir>`` named
    ``<station_name>.<comp>.sac``.

    Use this for **passive-source** work (ambient-noise HVSR): the output is
    one continuous SAC per component, suitable for direct obspy ingestion.

    Args:
        station_dir:   path to the station directory (contains DATAFILE.LST + raw files)
        output_dir:    where to write the SAC files
        sps:           sampling rate (Hz); get from :func:`scan_station`
        tc:            Time-Control value; get from :func:`scan_station`
        station_name:  output filename prefix (e.g. ``C10`` → ``C10.bhz.sac``)
        rfms:          DATAFILE.LST sequence number, default ``"0001"``
    """
    info = detect_obs_raw()
    if not info["available"]:
        return f"ERROR: {info['detail']}"

    sdir = _expand(station_dir)
    out = _expand(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    raw_files, _ = parse_datafile_lst(sdir)
    first_hex = raw_files[0]
    hex_prefix = first_hex.split(".")[0]

    # Isolated workdir; the merged raw keeps the first file's hex name
    # (graw2sac parses the hex prefix to detect the format).
    work = _workdir(out, station_name)
    merged = work / first_hex
    merged_size = merge_raw_files(raw_files, sdir, merged)

    res = run_raw(
        "graw2sac",
        [f"rawfile={first_hex}", f"sps={sps}", f"TC={tc}", f"rfms={rfms}"],
        cwd=str(work),
    )
    if not res.ok:
        shutil.rmtree(work, ignore_errors=True)
        return f"graw2sac {res.error_text()}"

    # Collect SAC outputs, fix npts, rename, move to output_dir.
    sac_results = {}
    for sf in sorted(work.glob(f"{hex_prefix}.*.sac")):
        comp = sf.name.split(".")[-2]
        if comp not in ("bh1", "bh2", "bhz", "hyd"):
            continue
        old_npts, new_npts = _fix_sac_npts_impl(sf)
        dest = out / f"{station_name}.{comp}.sac"
        shutil.move(str(sf), str(dest))
        sac_results[comp] = {
            "path": str(dest),
            "size_mb": round(dest.stat().st_size / 1e6, 1),
            "npts": new_npts,
            "npts_fixed": old_npts != new_npts,
        }
    shutil.rmtree(work, ignore_errors=True)

    if not sac_results:
        return (f"ERROR: graw2sac produced no SAC files. stderr:\n{res.stderr[:1500]}")
    comps = ", ".join(sac_results.keys())
    total_mb = sum(r["size_mb"] for r in sac_results.values())
    return (
        f"Converted {station_name} → {len(sac_results)} SAC ({comps}), "
        f"{total_mb:.0f} MB total → {out}. "
        f"Input was {len(raw_files)} raw files ({merged_size / 1e9:.1f} GB merged)."
    )


# ---------------------------------------------------------------------------
# Tool 4: raw_to_su — raw → SU shot gathers (active-source dispersion use case)
# ---------------------------------------------------------------------------
@mcp.tool()
def raw_to_su(
    station_dir: str,
    output_dir: str,
    sps: int,
    tc: int,
    station_name: str,
    shotfile: str,
    *,
    lat: float = 0.0,
    lon: float = 0.0,
    water_depth_m: float = 0.0,
    t1: float = -5.0,
    t2: float = 50.0,
    rfms: str = "0001",
) -> str:
    """Convert an OBS station's raw data to SU shot gathers (per-shot windows).

    Merges the raw shards (same merge as :func:`raw_to_sac`), then runs
    ``raw2su`` with a UKOOA shot file to cut a ``[t1, t2]`` second window
    around every shot. Outputs four SU files (``bhx``, ``bhy``, ``bhz``,
    ``hyd``) named ``<station_name>.<comp>.su`` in ``<output_dir>``.

    Use this for **active-source** work: the output is one SU gather per
    component containing every shot window, ready for phase-shift dispersion
    extraction.

    Args:
        station_dir:   station directory (with DATAFILE.LST + raw files)
        output_dir:    where to write the SU files
        sps, tc:       sampling rate and Time-Control value (from scan_station)
        station_name:  output filename prefix
        shotfile:      path to the UKOOA P1/90 shot-point file
        lat, lon:      station coordinates (degrees)
        water_depth_m: water depth in meters (sign-corrected internally)
        t1, t2:        shot-window bounds in seconds (default −5 to 50)
        rfms:          DATAFILE.LST sequence number, default ``"0001"``
    """
    info = detect_obs_raw()
    if not info["available"]:
        return f"ERROR: {info['detail']}"

    sdir = _expand(station_dir)
    out = _expand(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    raw_files, _ = parse_datafile_lst(sdir)
    first_hex = raw_files[0]

    work = _workdir(out, station_name)
    merged = work / first_hex
    merge_raw_files(raw_files, sdir, merged)

    res = run_raw(
        "raw2su",
        [
            f"rawfile={first_hex}", f"sps={sps}",
            f"shotfile={_expand(shotfile)}",
            f"t1={t1}", f"t2={t2}",
            f"lat={lat}", f"lon={lon}",
            f"TC={tc}", f"rfms={rfms}",
            f"wdep={-abs(water_depth_m)}",
            f"outfile={station_name}",
        ],
        cwd=str(work),
        timeout=900,  # raw2su with a big shot file can take longer than graw2sac
    )
    if not res.ok:
        shutil.rmtree(work, ignore_errors=True)
        return f"raw2su {res.error_text()}"

    su_results = {}
    for sf in sorted(work.glob(f"{station_name}.*.su")):
        comp = sf.name.split(".")[-2]
        dest = out / sf.name
        shutil.move(str(sf), str(dest))
        su_results[comp] = {
            "path": str(dest),
            "size_mb": round(dest.stat().st_size / 1e6, 1),
        }
    shutil.rmtree(work, ignore_errors=True)

    if not su_results:
        return f"ERROR: raw2su produced no SU files. stderr:\n{res.stderr[:1500]}"
    comps = ", ".join(su_results.keys())
    total_mb = sum(r["size_mb"] for r in su_results.values())
    return (
        f"Converted {station_name} → {len(su_results)} SU ({comps}), "
        f"{total_mb:.0f} MB total → {out}. "
        f"Window t1={t1} to t2={t2} s."
    )


# ---------------------------------------------------------------------------
# Tool 5: fix_sac_npts — repair the graw2sac npts bug on a single file
# ---------------------------------------------------------------------------
@mcp.tool()
def fix_sac_npts(sac_path: str) -> str:
    """Repair the ``npts`` header word in a SAC file produced by graw2sac.

    graw2sac (V3.0) writes ``npts`` ~44 samples smaller than the actual data
    block, which makes obspy reject the file with *"Actual and theoretical
    file size are inconsistent"*. This tool recomputes ``npts`` from the real
    file size and rewrites the header (byte offset 316, little-endian int32).
    Safe to call on already-correct files (it's a no-op then).

    Use this standalone only if you have graw2sac-produced SAC files from
    elsewhere — :func:`raw_to_sac` already applies the fix inline.
    """
    path = _expand(sac_path)
    if not path.is_file():
        return f"ERROR: no such file: {path}"
    try:
        old, new = _fix_sac_npts_impl(path)
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {exc}"
    if old == new:
        return f"{path}: npts already correct ({new})."
    return f"{path}: npts {old} → {new} (diff {new - old})."


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------

def _expand(path: str):
    """Expand ``~`` and env vars, return a Path."""
    return os.path.expanduser(os.path.expandvars(path)) if isinstance(path, str) else path


def _require(path: str) -> None:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"No such file: {path}")


def _workdir(parent, name: str):
    """Create an isolated working subdir under *parent*."""
    d = parent / f".tmp_{name}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def main() -> None:
    """Console entry point — launches the server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
