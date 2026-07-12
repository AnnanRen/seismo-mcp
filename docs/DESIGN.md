# Design & Technical Details

> This document is for people who want to understand *how* seismo-mcp works
> under the hood — the architecture decisions, the three wrapping patterns,
> and the real-world gotchas that had to be solved. For "what is this / how do
> I use it", see the [main README](../README.md).

## What problem does an MCP server actually solve?

An LLM agent (Claude, Cursor, …) is good at *deciding* what to do, but it
can't directly call a function on your computer. Without something in between,
asking an agent to "filter a seismogram" means letting it **write and execute
code** that shells out to `sac` or imports `obspy`. That works, but:

- the agent can misremember flag syntax (`f=5,40` vs `f=5-40` vs `--freq 5 40`);
- there's no reusable boundary — every conversation reinvents the call;
- a free-form shell command can do anything, including destructive things;
- output (huge binary trace arrays) risks flooding the model's context.

An **MCP server** sits between the agent and your tools and exposes
**pre-defined, typed tools**. The agent calls `sac_filter(input, output,
freqmin, freqmax)`; the server validates the arguments, runs SAC correctly,
and returns a bounded summary. The agent's job becomes *intent*, not
*syntax*.

```
agent  ──MCP protocol──▶  seismo-mcp server (Python)  ──subprocess/import──▶  ObsPy / SU / SAC
                               ↑ typed tools                ↑ the real work
                          (schema from type hints
                           + docstrings)
```

MCP itself is just the **wire protocol** between the agent and the server —
the same standard regardless of which agent (Claude, Cursor, …) or which
backend (CLI, Python lib, …).

## Why one server per toolchain?

Every mounted MCP server contributes its **full set of tool definitions**
(name, description, JSON schema for parameters) to the agent's working
context for the whole conversation. That context is finite, and an
over-stuffed context makes the agent slower and costlier.

If we packed ObsPy + SU + SAC into one server, then an agent doing a
quick ObsPy read would still be carrying ~22 tool schemas it isn't using.
Splitting by toolchain means you mount only what you need, and the agent only
sees relevant tools. As a bonus, adding a future toolchain (Madagascar, GMT)
is a new package that doesn't touch the existing ones.

## The three wrapping patterns

The core engineering interest: the three backends have completely different
shapes, so each needs a different wrapping strategy.

### 1. ObsPy — in-process Python import (obspy-mcp)

ObsPy is a **Python library**. The server imports it directly and calls it
inside the same process — no subprocess, no serialization. This is the
cleanest case.

```python
@mcp.tool()
def filter_waveform(input_path, output_path, freqmin=1.0, freqmax=20.0):
    from obspy import read
    st = read(input_path)
    st.filter("bandpass", freqmin=freqmin, freqmax=freqmax)
    st.write(output_path)
    return _summarize(st)   # text summary, not the data array
```

**Key rule:** return *summaries* (trace id, npts, timing), never the sample
arrays — a 60-second trace at 100 Hz is 24 KB of floats that does not belong
in the model's token stream.

### 2. CWP-SU — subprocess with pipe draining (cwp-su-mcp)

CWP-SU is a family of ~450 **command-line programs** that follow classic Unix
pipe discipline: each reads SU-format traces from stdin, writes traces to
stdout, logs to stderr. The server shells out and feeds/receives bytes.

Three pitfalls, all handled in the `run_su()` helper:

| Pitfall | Mitigation |
|---|---|
| **Pipe deadlock** — blocking on stdout while stderr fills its buffer wedges both | `subprocess.run(..., capture_output=True)` drains both concurrently |
| **Hung process** — a misbehaving trace could hang the whole server (and the conversation) | Every call carries a `timeout` (default 300 s) |
| **Binary output** — SU traces are binary; decoding as text silently corrupts them | stdout stays `bytes`, never decoded |

**One special case worth noting:** `susort` is among the few CWP-SU programs
that *refuses* to read/write through a pipe (it enforces DISK→DISK I/O). For
it, the `su_sort` tool falls back to shell redirection
(`susort key < in > out`) rather than the in-memory pipe the other tools use.

### 3. SAC — interactive REPL, driven in batch (sac-mcp)

SAC is an **interactive interpreter** (a `SAC>` prompt, like a seismology
Python). There's no single "filter" binary; you issue a sequence of commands
inside the session. The server's `run_sac_batch()` helper builds a small
script and pipes it in:

```
r input.sac
rmean
bp co 0.1 1.0 n 4 p 2
w output.sac
q
```

…then captures the session log and returns a one-line summary.

**The macOS-specific quirk:** SAC's bundled `sacinit.sh` hard-codes
`SACHOME=/usr/local/sac`. On any install *not* under `/usr/local/sac` (the
common case on a personal Mac), SAC exits immediately with *"aux directory
not Found"*. The `_sac_env()` helper **overrides `SACHOME`/`SACAUX`** from
the detected root before every launch, so a user-dir install just works.

**For fast header reads**, the server uses the standalone `saclst` binary
instead of spinning up the whole REPL — much faster, and `saclst` has its own
quirk: the argument order is `saclst <fields...> f <files...>` (the `f`
marker sits *between* fields and files), which is easy to get wrong.

## Design principles (consolidated)

1. **Binary trace data never enters the model context.** Reads return
   summaries; processing tools write a file and return its path. Waveforms
   live on disk or in a plot.
2. **Each tool is a typed function.** Type hints + docstring auto-generate the
   JSON schema via FastMCP — the agent literally cannot pass a flag the wrong
   way, because the schema constrains it.
3. **Failures are readable text.** A CWP/SAC error (`wagc too long for trace`,
   `key word not in segy.h`) is captured from stderr and returned to the
   agent, so it can reason about what went wrong instead of seeing a silent
   nonzero exit.
4. **One `diagnose_environment` per server.** The first tool the agent should
   call — it reports whether the backend is installed and where, so the agent
   learns what's usable before reaching for a tool that isn't there.
5. **Self-contained packages.** Each server inlines the ~100 lines of helpers
   it needs (subprocess / plot / env-detection) rather than depending on a
   shared internal package. This means each publishes to PyPI and installs
   standalone with `uvx <name>` — no companion package required.

## Decision: why CPS is not (yet) included

[Computer Programs in Seismology](https://www.eas.slu.edu/eqc/eqccps.html)
(CPS, Herrmann) was considered. Its core commands (e.g. surface-wave
inversion `srfinv96`) don't just take command-line flags — they require
**pre-generated text control files** (model files, `dfile`, `tmpsrfi.09`, …).
Wrapping CPS cleanly means the server must *generate those control files*
correctly, which is format-sensitive and high-effort for a relatively small
user base. It's a reasonable future addition, but was scoped out of v0.1.

## Project layout

```
seismo-mcp/                        ← uv workspace root (not published)
├── packages/
│   ├── obspy-mcp/                 ← independently published: uvx obspy-mcp
│   │   ├── pyproject.toml         ← declares deps + console entry point
│   │   ├── README.md              ← tool table, examples
│   │   └── src/obspy_mcp/
│   │       ├── server.py          ← @mcp.tool definitions
│   │       └── _helpers.py        ← inlined plot/env helpers
│   ├── cwp-su-mcp/                ← same structure
│   └── sac-mcp/                   ← same structure
├── docs/                          ← this file + INSTALL.md
├── examples/                      ← end-to-end tests per server
└── pyproject.toml                 ← workspace coordination only
```

Each package's `pyproject.toml` declares a `[project.scripts]` console entry
point (e.g. `obspy-mcp = obspy_mcp.server:main`), so once published,
`uvx obspy-mcp` launches the server over stdio.

## Tech stack

- **Python ≥ 3.10**, managed with [uv](https://docs.astral.sh/uv/) workspaces.
- **[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)**
  (`mcp` package), using the bundled FastMCP 1.0 API
  (`from mcp.server.fastmcp import FastMCP`). Pinned to `mcp>=1.27,<2` — the
  v2 SDK is alpha and not production-ready.
- **FastMCP** turns type hints + docstrings into the JSON schema
  automatically; `Image(data=..., format="png")` returns inline plots.
- **matplotlib** in headless `Agg` mode for plotting.
- Build/publish via `uv build` + `uv publish` (PyPI).
