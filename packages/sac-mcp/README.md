# sac-mcp

An [MCP](https://modelcontextprotocol.io) server that lets LLM agents drive
[SAC](https://ds.iris.edu/ds/nodes/dmc/software/downloads/sac/) (Seismic
Analysis Code) — read headers, preprocess, filter, cut, merge, stack, remove
instrument response — without leaving the chat.

> Part of [**seismo-mcp**](../..), a toolkit where each seismology toolchain
> gets its own focused MCP server. Mount only what you need.

## Why

SAC is the lingua franca of earthquake seismology and passive-source work.
But it's an **interactive REPL** (a ``SAC>`` prompt), which is great for a
human at a terminal and awkward for an agent. This server feeds SAC command
scripts to the interpreter in batch mode, so an agent can say *"bandpass
0.5–2 Hz, demean, cut −5 to 30 s"* and the server runs the SAC session for it.

## Install

```sh
claude mcp add sac -- uvx sac-mcp
```

**Requires** a working SAC installation with ``SACHOME`` and ``SACAUX`` set
(or installed under ``~/src/sac`` / ``/usr/local/sac``). The server injects
``SACHOME``/``SACAUX`` from the detected root — overriding SAC's bundled
``sacinit.sh``, which hard-codes ``/usr/local/sac`` and breaks user-dir installs.

## Tools

| Tool | What it does |
|---|---|
| `diagnose_environment` | Confirm SAC is installed and located. |
| `sac_listhdr` | Fast header read via `saclst` (no REPL spin-up). |
| `sac_preprocess` | Detrend + demean + taper → file. |
| `sac_filter` | Bandpass / lowpass / highpass (Butterworth) → file. |
| `sac_cut` | Extract a time window → file. |
| `sac_merge` | Merge (concatenate/interpolate) files → one. |
| `sac_transfer` | Remove instrument response (RESP / P&Z) → file. |

> Note: SAC's waveform stacking lives in the interactive `sss` (Signal
> Stacking Subprocess) subsystem, which doesn't lend itself to a clean batch
> wrapper — for stacking, prefer the `obspy-mcp` sibling or write a SAC macro.

**Design:** every tool builds a small SAC command script (`r file → op → w out
→ q`), feeds it to the interpreter via stdin, captures the session log, and
returns a one-line summary. Header reads use the standalone `saclst` binary
for speed. Output is always a file — trace arrays never enter the model
context.

## Example session

> **You:** Open `event.sac`, demean and bandpass 0.5–2 Hz two-pass, then cut
> −5 to 30 s.
>
> **Agent:** *calls* `sac_listhdr` → delta=0.05, npts=2000, B=−10, E=90.
> *calls* `sac_filter` → `event_bp.sac`. *calls* `sac_cut -5 30` →
> `event_bp_cut.sac`. ✓

## Development

Self-contained — no sibling-package dependencies.

```sh
uv build --package sac-mcp
uv publish
```

License: MIT.
