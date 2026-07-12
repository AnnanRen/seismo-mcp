"""CWP/SU MCP server.

Wraps CWP-SU trace-processing programs as MCP tools. CWP-SU programs follow
strict Unix-pipe discipline: each reads SU traces from stdin, writes traces
to stdout, and emits diagnostics on stderr. So every tool here has the same
shape:

    read input file (bytes) → run_su(...) → write stdout to output file →
    return a summary (trace count, header digest).

We never return raw trace bytes to the model — they're binary and can be
huge; they belong in a file. A failed run returns the stderr text so the
agent can see what CWP complained about (e.g. "wagc too long for trace").
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from ._helpers import detect_su, run_su, _su_env, DEFAULT_TIMEOUT

# Alias used by su_sort's shell-form invocation.
_cwp_env = _su_env

mcp = FastMCP("cwp-su-mcp")


# ---------------------------------------------------------------------------
# Tool 1: diagnose_environment
# ---------------------------------------------------------------------------
@mcp.tool()
def diagnose_environment() -> str:
    """Report whether CWP-SU is installed and where.

    Call this first to confirm the backend is ready. Checks CWPROOT and the
    presence of the ``sugethw`` program. Returns a status line.
    """
    info = detect_su()
    if not info["available"]:
        return f"ERROR: {info['detail']}"
    return f"OK: {info['detail']} (CWPROOT={info['root']})"


# ---------------------------------------------------------------------------
# Tool 2: su_gethw — read header words from an SU file
# ---------------------------------------------------------------------------
@mcp.tool()
def su_gethw(
    input_path: str,
    key: str,
) -> str:
    """Print values of a trace header *key* from an SU file.

    Common keys: ``tracl`` (trace number), ``offset`` (source-receiver
    offset), ``fldr`` (field record), ``cdp``, ``sx``/``gx`` (source/receiver
    coords), ``ns`` (samples), ``dt`` (sample interval, microsec). Returns
    one value per trace (may be long for big files).
    """
    _require(input_path)
    data = Path(input_path).read_bytes()
    res = run_su("sugethw", [f"key={key}"], stdin=data)
    if not res.ok:
        return res.error_text()
    out = res.stdout.decode("utf-8", errors="replace").strip()
    nlines = out.count("\n") + 1 if out else 0
    return f"{key} for {nlines} trace(s) in {input_path}:\n{out}"


# ---------------------------------------------------------------------------
# Tool 3: su_filter — bandpass / lowpass / highpass
# ---------------------------------------------------------------------------
@mcp.tool()
def su_filter(
    input_path: str,
    output_path: str,
    *,
    f: list[float] | None = None,
    freqmin: float | None = None,
    freqmax: float | None = None,
    filter_type: str = "bandpass",
) -> str:
    """Apply a frequency filter via CWP-SU ``sufilter``; write to *output_path*.

    Two conveniences on top of raw sufilter:

    - *bandpass* (default): give ``freqmin``/``freqmax`` and the full
      ``f=`` ramp slopes are generated automatically as
      ``[freqmin*0.7, freqmin, freqmax, freqmax*1.3]``.
    - *lowpass* / *highpass*: give just the cutoff as ``freqmin``.
    - For full control, pass explicit ``f=[f1,f2,f3,f4]`` (Hz) and it is used
      verbatim.
    """
    _require(input_path)
    if f is None:
        if freqmin is None:
            return "ERROR: provide either f=[...] or freqmin (and freqmax for bandpass)."
        if filter_type == "bandpass":
            if freqmax is None:
                return "ERROR: bandpass needs freqmax (or explicit f=[...])."
            f = [freqmin * 0.7, freqmin, freqmax, freqmax * 1.3]
        elif filter_type == "lowpass":
            f = [0.0, 0.0, freqmin, freqmin * 1.3]
        elif filter_type == "highpass":
            f = [freqmin * 0.7, freqmin, 9999.0, 9999.0]
        else:
            return f"ERROR: unknown filter_type {filter_type!r}"

    data = Path(input_path).read_bytes()
    res = run_su("sufilter", [f"f={','.join(str(x) for x in f)}"], stdin=data)
    if not res.ok:
        return res.error_text()
    Path(output_path).write_bytes(res.stdout)
    return f"Filtered ({filter_type}, f={f}) → wrote {output_path} ({len(res.stdout)} bytes)"


# ---------------------------------------------------------------------------
# Tool 4: su_gain — apply gain (AGC / tpower / balance)
# ---------------------------------------------------------------------------
@mcp.tool()
def su_gain(
    input_path: str,
    output_path: str,
    *,
    agc: bool = False,
    wagc: float = 0.5,
    tpow: float | None = None,
    balance: bool = False,
) -> str:
    """Apply amplitude gain via CWP-SU ``sugain``; write to *output_path*.

    - *agc=True*: automatic gain control with window *wagc* (seconds). Note
      ``wagc`` must be shorter than the trace length or sugain errors.
    - *tpow*: geometric-spreading correction, t^tpow.
    - *balance=True*: balance trace amplitudes pairwise.
    At least one must be requested.
    """
    _require(input_path)
    if not (agc or tpow is not None or balance):
        return "ERROR: enable at least one of agc / tpow / balance."

    args: list[str] = []
    if agc:
        args += ["agc=1", f"wagc={wagc}"]
    if tpow is not None:
        args.append(f"tpow={tpow}")
    if balance:
        args.append("bal=1")

    data = Path(input_path).read_bytes()
    res = run_su("sugain", args, stdin=data)
    if not res.ok:
        return res.error_text()
    Path(output_path).write_bytes(res.stdout)
    return f"Gain ({' '.join(args)}) → wrote {output_path} ({len(res.stdout)} bytes)"


# ---------------------------------------------------------------------------
# Tool 5: su_wind — time/trace windowing
# ---------------------------------------------------------------------------
@mcp.tool()
def su_wind(
    input_path: str,
    output_path: str,
    *,
    tmin: float | None = None,
    tmax: float | None = None,
    min_tracl: int | None = None,
    max_tracl: int | None = None,
) -> str:
    """Window traces in time (``tmin``/``tmax``, seconds) or by trace number
    (``min_tracl``/``max_tracl``) via CWP-SU ``suwind``; write to *output_path*.
    """
    _require(input_path)
    args: list[str] = []
    if tmin is not None:
        args.append(f"tmin={tmin}")
    if tmax is not None:
        args.append(f"tmax={tmax}")
    if min_tracl is not None:
        args.append(f"min=tracl:{min_tracl}")
    if max_tracl is not None:
        args.append(f"max=tracl:{max_tracl}")
    if not args:
        return "ERROR: give at least one of tmin/tmax/min_tracl/max_tracl."

    data = Path(input_path).read_bytes()
    res = run_su("suwind", args, stdin=data)
    if not res.ok:
        return res.error_text()
    Path(output_path).write_bytes(res.stdout)
    return f"Windowed ({' '.join(args)}) → wrote {output_path} ({len(res.stdout)} bytes)"


# ---------------------------------------------------------------------------
# Tool 6: su_sort — sort traces by header key
# ---------------------------------------------------------------------------
@mcp.tool()
def su_sort(
    input_path: str,
    output_path: str,
    key: str = "offset",
    *,
    descending: bool = False,
) -> str:
    """Sort traces by a header *key* (default ``offset``) via CWP-SU
    ``susort``; write to *output_path*. Prefix the key with ``-`` for
    descending order (or set *descending*).

    Note: ``susort`` is one of the few CWP-SU programs that cannot read/write
    through a pipe (it enforces DISK->DISK I/O), so this tool invokes it with
    shell redirection (``susort key < in > out``) rather than the in-memory
    pipe used by other tools."""
    _require(input_path)
    k = f"-{key}" if descending else key
    # Shell form to satisfy susort's DISK I/O requirement; input/output paths
    # are local file paths we control, so shell=True is acceptable here.
    import shlex
    cmd = f"susort {shlex.quote(k)} < {shlex.quote(input_path)} > {shlex.quote(output_path)}"
    import subprocess
    cwp_env = _cwp_env()
    try:
        proc = subprocess.run(  # noqa: S602 — shell form by necessity
            ["bash", "-c", cmd],
            capture_output=True,
            timeout=DEFAULT_TIMEOUT,
            env=cwp_env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"susort TIMEOUT after {DEFAULT_TIMEOUT}s"
    if proc.returncode != 0:
        return f"susort failed (exit {proc.returncode}):\n{(proc.stderr or b'').decode('utf-8','replace').strip()[:2000]}"
    size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    return f"Sorted by {key} ({'desc' if descending else 'asc'}) → wrote {output_path} ({size} bytes)"


# ---------------------------------------------------------------------------
# Tool 7: su_sethw — set a header word on all traces
# ---------------------------------------------------------------------------
@mcp.tool()
def su_sethw(
    input_path: str,
    output_path: str,
    key: str,
    value: float,
) -> str:
    """Set a header *key* to a constant *value* on all traces via CWP-SU
    ``sushw``; write to *output_path*. Useful for tagging offsets, field
    record numbers, coordinates, etc."""
    _require(input_path)
    data = Path(input_path).read_bytes()
    res = run_su("sushw", [f"key={key}", f"a={value}"], stdin=data)
    if not res.ok:
        return res.error_text()
    Path(output_path).write_bytes(res.stdout)
    return f"Set {key}={value} on all traces → wrote {output_path} ({len(res.stdout)} bytes)"


# ---------------------------------------------------------------------------
# Tool 8: su_count — quick trace count + dt/ns sanity (chains sugethw)
# ---------------------------------------------------------------------------
@mcp.tool()
def su_count(input_path: str) -> str:
    """Return trace count, samples-per-trace (ns), and sample interval (dt,
    microseconds) for an SU file — a quick sanity read."""
    _require(input_path)
    data = Path(input_path).read_bytes()
    res = run_su("sugethw", ["key=ns,dt"], stdin=data)
    if not res.ok:
        return res.error_text()
    out = res.stdout.decode("utf-8", errors="replace").strip()
    nlines = out.count("\n") + 1 if out else 0
    # Pull the first line's dt/ns for a summary.
    first = out.split("\n", 1)[0] if out else "(no data)"
    return f"{input_path}: {nlines} trace(s); first header → {first}"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _require(path: str) -> None:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"No such file: {path}")


def main() -> None:
    """Console entry point — launches the server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
