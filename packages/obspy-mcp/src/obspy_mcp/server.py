"""ObsPy MCP server.

Each tool below is a thin, typed wrapper over ObsPy. FastMCP derives the
JSON schema from the type hints and the tool description from the docstring,
so there is no manual schema to maintain.

Design notes:

- Read functions return *summaries* (trace id, npts, start/end, stats),
  never the sample arrays themselves — arrays belong on disk or in a plot,
  not in the model context window.
- All processing tools write the result to an output file and return its
  path plus a summary, so downstream tools (or the user) can chain on it.
- Plotting returns an inline Image for small plots, else a file path.
"""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless; must precede pyplot use in obspy's plot
import numpy as np
from mcp.server.fastmcp import FastMCP, Image

from ._helpers import figure_to_image, save_figure, probe_obspy

mcp = FastMCP("obspy-mcp")


# ---------------------------------------------------------------------------
# Tool 1: diagnose_environment — always first; tells the agent what's usable.
# ---------------------------------------------------------------------------
@mcp.tool()
def diagnose_environment() -> str:
    """Report whether ObsPy is importable and which version is available.

    Call this first to confirm the backend is ready before using any other
    tool. Returns a short status line; safe to call any time.
    """
    st = probe_obspy()
    return st


# ---------------------------------------------------------------------------
# Tool 2: read_waveform — read a file (SAC/MSEED/SEG-Y/...) and summarize.
# ---------------------------------------------------------------------------
@mcp.tool()
def read_waveform(
    path: str,
    *,
    format: str | None = None,
) -> str:
    """Read a waveform file and return a summary of its traces.

    Supports any format ObsPy can read (SAC, MiniSEED, SEG-Y, GSE2, SAC, ...).
    Set *format* to force a reader (e.g. "SAC", "MSEED"); leave None for
    auto-detection. Returns trace count and per-trace header digest; sample
    data is NOT returned (use ``plot_waveform`` or ``filter_waveform`` to act
    on the data).
    """
    from obspy import read

    _require(path)
    st = read(path, format=format)
    return _summarize_stream(st, f"read {len(st)} trace(s) from {path}")


# ---------------------------------------------------------------------------
# Tool 3: filter_waveform — read, filter, write to a new file.
# ---------------------------------------------------------------------------
@mcp.tool()
def filter_waveform(
    input_path: str,
    output_path: str,
    filter_type: str = "bandpass",
    freqmin: float = 1.0,
    freqmax: float = 20.0,
    corners: int = 4,
    zerophase: bool = True,
) -> str:
    """Read *input_path*, apply a filter, write the result to *output_path*.

    *filter_type* is one of ObsPy's: ``bandpass`` (default), ``lowpass``,
    ``highpass``, ``bandstop``. For low/highpass only ``freqmin`` is used (as
    the cutoff). Returns the output path plus a summary of the filtered stream.
    """
    from obspy import read

    _require(input_path)
    st = read(input_path)

    if filter_type in ("bandpass", "bandstop"):
        st.filter(filter_type, freqmin=freqmin, freqmax=freqmax,
                  corners=corners, zerophase=zerophase)
    elif filter_type in ("lowpass", "highpass"):
        st.filter(filter_type, freq=freqmin, corners=corners, zerophase=zerophase)
    else:
        return f"ERROR: unsupported filter_type {filter_type!r}"

    st.write(output_path)
    return _summarize_stream(
        st, f"filtered ({filter_type}) → wrote {output_path}"
    )


# ---------------------------------------------------------------------------
# Tool 4: preprocess — detrend + taper + remove_mean, the standard front-end.
# ---------------------------------------------------------------------------
@mcp.tool()
def preprocess(
    input_path: str,
    output_path: str,
    *,
    detrend: bool = True,
    taper_max_percent: float = 5.0,
    remove_mean: bool = True,
) -> str:
    """Apply standard preprocessing and write to *output_path*.

    Sequence (each optional): linear detrend → taper → demean. This is the
    usual pre-filter housekeeping. Returns output path + summary.
    """
    from obspy import read

    _require(input_path)
    st = read(input_path)
    if detrend:
        st.detrend("linear")
    if taper_max_percent > 0:
        st.taper(max_percentage=taper_max_percent / 100.0)
    if remove_mean:
        st.detrend("demean")
    st.write(output_path)
    return _summarize_stream(st, f"preprocessed → wrote {output_path}")


# ---------------------------------------------------------------------------
# Tool 5: resample — change sample rate.
# ---------------------------------------------------------------------------
@mcp.tool()
def resample(
    input_path: str,
    output_path: str,
    target_rate_hz: float,
) -> str:
    """Resample traces to *target_rate_hz* (Hz) and write to *output_path*.

    Uses ObsPy's FFT-based resampler. Apply an anti-alias lowpass beforehand
    if downsampling by a large factor.
    """
    from obspy import read

    _require(input_path)
    st = read(input_path)
    st.resample(target_rate_hz)
    st.write(output_path)
    return _summarize_stream(st, f"resampled to {target_rate_hz} Hz → wrote {output_path}")


# ---------------------------------------------------------------------------
# Tool 6: convert_format — SAC ↔ MiniSEED ↔ SEG-Y etc.
# ---------------------------------------------------------------------------
@mcp.tool()
def convert_format(
    input_path: str,
    output_path: str,
    output_format: str,
) -> str:
    """Convert a waveform file between ObsPy-supported formats.

    *output_format* extension hints the writer, e.g. ``SAC``, ``MSEED``,
    ``SEG-Y`` (the output_path extension should match). Returns the path.
    """
    from obspy import read

    _require(input_path)
    st = read(input_path)
    st.write(output_path, format=output_format)
    return f"Converted {input_path} → {output_path} ({output_format}); {len(st)} trace(s)."


# ---------------------------------------------------------------------------
# Tool 7: plot_waveform — inline PNG for small plots, file path for big ones.
# ---------------------------------------------------------------------------
@mcp.tool()
def plot_waveform(
    input_path: str,
    output_path: str | None = None,
    *,
    trace_index: int = 0,
    dpi: int = 100,
) -> str:
    """Plot one trace from *input_path*.

    If *output_path* is omitted or the rendered PNG is large, the image is
    written to that path (or a temp file) and the path is returned; otherwise
    an inline image is returned for the model to view directly. *trace_index*
    selects which trace to draw when the file holds several.
    """
    from obspy import read
    import matplotlib.pyplot as plt

    _require(input_path)
    st = read(input_path)
    if not 0 <= trace_index < len(st):
        return f"ERROR: trace_index {trace_index} out of range (stream has {len(st)} trace(s))"

    tr = st[trace_index]
    fig, ax = plt.subplots(figsize=(10, 3))
    t = np.linspace(0, tr.stats.npts * tr.stats.delta, tr.stats.npts)
    ax.plot(t, tr.data, linewidth=0.6, color="black")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Amplitude")
    ax.set_title(f"{tr.id}  {tr.stats.starttime}")
    ax.grid(True, alpha=0.3)

    # Try inline first; fall back to file if it's too big.
    if output_path is None:
        try:
            return figure_to_image(fig, dpi=dpi)
        except ValueError:
            output_path = _tmp_png("obspy_plot")
    return save_figure(fig, output_path, dpi=dpi)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _require(path: str) -> None:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"No such file: {path}")


def _summarize_stream(st, header: str) -> str:
    lines = [header]
    for i, tr in enumerate(st):
        lines.append(
            f"  [{i}] {tr.id}  npts={tr.stats.npts}  "
            f"dt={tr.stats.delta:.4g}s  {tr.stats.starttime} → {tr.stats.endtime}"
        )
    return "\n".join(lines)


def _tmp_png(prefix: str) -> str:
    import tempfile
    fd, name = tempfile.mkstemp(prefix=f"{prefix}_", suffix=".png")
    os.close(fd)
    return name


def main() -> None:
    """Console entry point — launches the server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
