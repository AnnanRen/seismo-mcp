# obspy-mcp

An [MCP](https://modelcontextprotocol.io) server that lets LLM agents
(Claude, Cursor, ...) read, filter, plot, and convert seismic waveforms via
[ObsPy](https://obspy.org) — without writing code.

> Part of [**seismo-mcp**](../..), a toolkit where each seismology toolchain
> gets its own focused MCP server. Mount only what you need.

## Why

ObsPy is the de-facto Python library for seismology, but it's a *library* —
to use it you write a script. This server turns the everyday waveform
operations into tools an agent can call directly, so you can say *"bandpass
this SAC file 2–10 Hz, demean, and show me the first trace"* and the agent
does it. Good for quick looks, batch conversions, and teaching.

## Install

```sh
claude mcp add obspy -- uvx obspy-mcp
```

Requires a working ObsPy (installed automatically as a dependency) and
Python ≥ 3.10.

## Tools

| Tool | What it does |
|---|---|
| `diagnose_environment` | Confirm ObsPy is importable; call first. |
| `read_waveform` | Read any ObsPy-supported file (SAC/MSEED/SEG-Y/...) → trace summary. |
| `filter_waveform` | Bandpass / lowpass / highpass / bandstop → new file. |
| `preprocess` | Detrend → taper → demean (standard pre-filter housekeeping). |
| `resample` | Change sample rate (FFT-based). |
| `convert_format` | SAC ↔ MiniSEED ↔ SEG-Y ↔ ... |
| `plot_waveform` | Plot a trace; returns inline PNG or a file path. |

**Design:** read/processing tools return *summaries* (trace id, npts, timing),
never raw sample arrays — waveforms belong on disk or in a plot, not in the
model's context window.

## Example session

With the server mounted in Claude Desktop:

> **You:** I have `shot_001.sac`. Read it, preprocess, bandpass 2–10 Hz, and plot it.
>
> **Agent:** *calls* `read_waveform` → *sees* 1 trace, BHZ, 6000 samples.
> *calls* `preprocess` → `shot_001_pp.sac`. *calls* `filter_waveform` →
> `shot_001_bp.sac`. *calls* `plot_waveform` → returns the plot inline.

## Development

This package is self-contained — it has no sibling-package dependencies, so
it builds and publishes on its own.

```sh
uv build --package obspy-mcp
uv publish
```

License: MIT.
