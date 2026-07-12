"""SAC MCP server.

SAC (Seismic Analysis Code) is an interactive interpreter: you issue commands
like ``r file.sac``, ``rmean``, ``bp co 0.1 1.0``, ``w out.sac`` inside a
``SAC>`` prompt. Each tool here builds a small batch script of those commands
and feeds it to the interpreter via :func:`run_sac_batch`.

Every processing tool follows the same shape: read input → apply op(s) → write
output → return a summary. Header reads use the lightweight standalone
``saclst`` instead of the full REPL (much faster).
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from ._helpers import detect_sac, run_sac_batch, saclst

mcp = FastMCP("sac-mcp")


# ---------------------------------------------------------------------------
# Tool 1: diagnose_environment
# ---------------------------------------------------------------------------
@mcp.tool()
def diagnose_environment() -> str:
    """Report whether SAC is installed and where (SACHOME).

    Call this first to confirm the backend is ready. Returns a status line.
    """
    info = detect_sac()
    if not info["available"]:
        return f"ERROR: {info['detail']}"
    return f"OK: {info['detail']} (SACHOME={info['root']})"


# ---------------------------------------------------------------------------
# Tool 2: sac_listhdr — fast header read via saclst (no REPL)
# ---------------------------------------------------------------------------
@mcp.tool()
def sac_listhdr(
    files: list[str],
    fields: list[str] | None = None,
) -> str:
    """List SAC header *fields* for one or more *files* (fast; uses saclst).

    Default *fields* (if None): ``stnm kcmpnm delta npts b e stla stlo dist``.
    Returns one line per file with the field values.
    """
    for f in files:
        if not os.path.isfile(f):
            return f"ERROR: no such file: {f}"
    if not fields:
        # Use SAC's canonical header field names (kstnm not stnm, etc.).
        fields = ["kstnm", "kcmpnm", "delta", "npts", "b", "e", "stla", "stlo", "dist"]
    out = saclst(fields, files)
    return f"Header fields {fields}:\n{out}"


# ---------------------------------------------------------------------------
# Tool 3: sac_preprocess — rmean / rtrend / taper (standard housekeeping)
# ---------------------------------------------------------------------------
@mcp.tool()
def sac_preprocess(
    input_path: str,
    output_path: str,
    *,
    detrend: bool = True,
    remove_mean: bool = True,
    taper_percent: int = 5,
) -> str:
    """Apply standard SAC preprocessing and write to *output_path*.

    Sequence: linear detrend (``rtrend``) → remove mean (``rmean``) → taper
    (``taper`` with *taper_percent* of each end). Each step optional."""
    if not os.path.isfile(input_path):
        return f"ERROR: no such file: {input_path}"

    cmds = [f"r {input_path}"]
    if detrend:
        cmds.append("rtrend")
    if remove_mean:
        cmds.append("rmean")
    if taper_percent > 0:
        cmds.append(f"taper taper {taper_percent}")
    cmds += [f"w {output_path}", "q"]

    res = run_sac_batch(cmds)
    if not res.ok:
        return res.error_text()
    return _ok_summary(input_path, output_path, ops=[c for c in cmds[1:-2]])


# ---------------------------------------------------------------------------
# Tool 4: sac_filter — bandpass / lowpass / highpass
# ---------------------------------------------------------------------------
@mcp.tool()
def sac_filter(
    input_path: str,
    output_path: str,
    filter_type: str = "bandpass",
    *,
    corners: int = 4,
    passes: int = 2,
    freqmin: float = 0.1,
    freqmax: float = 1.0,
    cutoff: float | None = None,
) -> str:
    """Apply a SAC filter and write to *output_path*.

    - ``bandpass``: zero-phase Butterworth, *freqmin*–*freqmax* Hz. *passes*=2
      = two-pass (zero phase); =1 = one-pass (causal).
    - ``lowpass`` / ``highpass``: corner = *cutoff* (Hz).
    *corners* is the filter order (default 4).
    """
    if not os.path.isfile(input_path):
        return f"ERROR: no such file: {input_path}"

    if filter_type == "bandpass":
        flt = f"bp co {freqmin} {freqmax} n {corners} p {passes}"
    elif filter_type == "lowpass":
        if cutoff is None:
            return "ERROR: lowpass needs cutoff (Hz)."
        flt = f"lp co {cutoff} n {corners} p {passes}"
    elif filter_type == "highpass":
        if cutoff is None:
            return "ERROR: highpass needs cutoff (Hz)."
        flt = f"hp co {cutoff} n {corners} p {passes}"
    else:
        return f"ERROR: unknown filter_type {filter_type!r}"

    cmds = [f"r {input_path}", "rmean", flt, f"w {output_path}", "q"]
    res = run_sac_batch(cmds)
    if not res.ok:
        return res.error_text()
    return _ok_summary(input_path, output_path, ops=[flt])


# ---------------------------------------------------------------------------
# Tool 5: sac_cut — extract a time window
# ---------------------------------------------------------------------------
@mcp.tool()
def sac_cut(
    input_path: str,
    output_path: str,
    t_start: float,
    t_end: float,
) -> str:
    """Cut a time window [*t_start*, *t_end*] (seconds, absolute trace time)
    and write to *output_path*.

    Uses SAC's ``cut`` idiom: ``cuterr fillz`` (zero-fill outside the trace so
    out-of-range windows don't abort the session) → ``cut on`` → ``cut t1 t2``
    → read → ``cut off`` → write. The cut window is declared BEFORE the read,
    so SAC applies it during the read."""
    if not os.path.isfile(input_path):
        return f"ERROR: no such file: {input_path}"

    cmds = [
        "cuterr fillz",      # tolerate windows partially outside [B,E]
        "cut on",
        f"cut {t_start} {t_end}",
        f"r {input_path}",
        "cut off",
        f"w {output_path}",
        "q",
    ]
    res = run_sac_batch(cmds)
    if not res.ok:
        return res.error_text()
    return _ok_summary(input_path, output_path, ops=[f"cut {t_start}-{t_end}"])


# ---------------------------------------------------------------------------
# Tool 6: sac_merge — merge two SAC files (e.g. components, segments)
# ---------------------------------------------------------------------------
@mcp.tool()
def sac_merge(
    input_paths: list[str],
    output_path: str,
) -> str:
    """Merge (concatenate/interpolate) two or more SAC files into one and
    write to *output_path*. Files must overlap or abut in time."""
    for f in input_paths:
        if not os.path.isfile(f):
            return f"ERROR: no such file: {f}"
    cmds = ["r " + " ".join(input_paths), "merge", f"w {output_path}", "q"]
    res = run_sac_batch(cmds)
    if not res.ok:
        return res.error_text()
    return _ok_summary(input_paths[0], output_path, ops=[f"merge {len(input_paths)} files"])


# ---------------------------------------------------------------------------
# Tool 7: sac_transfer — instrument response removal (evalresp/P&Z)
# ---------------------------------------------------------------------------
@mcp.tool()
def sac_transfer(
    input_path: str,
    output_path: str,
    *,
    resp_file: str | None = None,
    freq_limits: list[float] | None = None,
    from_unit: str = "DIS",
    to_unit: str = "VEL",
) -> str:
    """Remove instrument response via SAC ``transfer`` and write to
    *output_path*.

    *resp_file*: path to a RESP or pole-zero file. *freq_limits*: optional
    [f1,f2,f3,f4] Hz water-level ramp (recommended to stabilize low-freq).
    *from_unit*/*to_unit*: DIS (displacement) / VEL / ACC.
    """
    if not os.path.isfile(input_path):
        return f"ERROR: no such file: {input_path}"
    if not resp_file:
        return "ERROR: transfer requires resp_file (RESP or P&Z file path)."

    args = [f"from {from_unit}", f"to {to_unit}", f"subst 1.0e10"]
    if freq_limits and len(freq_limits) == 4:
        args.append(f"f {freq_limits[0]} {freq_limits[1]} {freq_limits[2]} {freq_limits[3]}")
    args.append(f"polezero {resp_file}")

    cmds = [f"r {input_path}", "rmean", f"transfer {' '.join(args)}", f"w {output_path}", "q"]
    res = run_sac_batch(cmds)
    if not res.ok:
        return res.error_text()
    return _ok_summary(input_path, output_path, ops=["transfer"])


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _ok_summary(input_path: str, output_path: str, *, ops: list[str]) -> str:
    size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    return (f"Applied ({'; '.join(ops)}) → wrote {output_path} ({size} bytes). "
            f"Input was {input_path}.")


def main() -> None:
    """Console entry point — launches the server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
