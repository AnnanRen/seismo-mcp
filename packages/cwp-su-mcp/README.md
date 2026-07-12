# cwp-su-mcp

An [MCP](https://modelcontextprotocol.io) server that lets LLM agents
(Claude, Cursor, ...) drive [CWP/SU: Seismic Un\*x](https://wiki.seismic-unix.org)
trace-processing programs — filter, gain, window, sort, header ops — without
typing a shell pipeline.

> Part of [**seismo-mcp**](../..), a toolkit where each seismology toolchain
> gets its own focused MCP server. Mount only what you need.

## Why

CWP-SU is a powerful but crusty 450-program suite from the command-line era.
Its tools chain via Unix pipes (``sufilter < in.su | sugain ...``), which is
expressive but unforgiving — wrong flag syntax or a missing header and you get
opaque errors. This server wraps the everyday operations as typed tools an
agent can call directly: *"bandpass 5–40 Hz, AGC with 0.5 s window, then sort
by offset"* becomes three tool calls instead of a man-page dive.

## Install

```sh
claude mcp add su -- uvx cwp-su-mcp
```

**Requires** a working CWP-SU installation with ``CWPROOT`` set and
``$CWPROOT/bin`` on PATH. (The server detects it via ``CWPROOT``, then
``~/src/cwp``, then ``/usr/local/cwp``.)

## Tools

| Tool | CWP-SU program | What it does |
|---|---|---|
| `diagnose_environment` | — | Confirm CWP-SU is installed and located. |
| `su_gethw` | `sugethw` | Read a trace header key from a file. |
| `su_count` | `sugethw` | Trace count + ns + dt sanity read. |
| `su_filter` | `sufilter` | Bandpass / lowpass / highpass → file. |
| `su_gain` | `sugain` | AGC / t-power / balance → file. |
| `su_wind` | `suwind` | Time or trace windowing → file. |
| `su_sort` | `susort` | Sort traces by header key → file. |
| `su_sethw` | `sushw` | Set a header word on all traces → file. |

**Design:** processing tools read an SU file, run the CWP program with
``subprocess`` (capturing stdout/stderr concurrently to avoid pipe deadlock,
with a timeout so a hung trace can't wedge the server), and write the result
to a new file — binary trace data never enters the model's context.

## Example session

With the server mounted in Claude Desktop:

> **You:** Here's `gather.su`. Bandpass 5–40 Hz, then apply AGC with a 0.5 s
> window, and tell me how many traces.
>
> **Agent:** *calls* `su_count` → 48 traces, dt=4000 µs. *calls* `su_filter`
> → `gather_bp.su`. *calls* `su_gain` → `gather_bpagc.su`. *calls* `su_count`
> again → 48 traces preserved. ✓

## Development

Self-contained — no sibling-package dependencies.

```sh
uv build --package cwp-su-mcp
uv publish
```

License: MIT.
