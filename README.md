# seismo-mcp

> A toolkit of focused [MCP](https://modelcontextprotocol.io) servers that let
> LLM agents (Claude, Cursor, ...) drive seismology software — without writing
> code.

Seismology runs on a handful of venerable, powerful, and famously crusty
toolchains: [ObsPy](https://obspy.org), [CWP/SU](https://wiki.seismic-unix.org),
and [SAC](https://ds.iris.edu/ds/nodes/dmc/software/downloads/sac/). They live
on the command line or inside Python scripts. **seismo-mcp turns their everyday
operations into tools an agent can call directly** — so you can say *"bandpass
this SAC file 0.5–2 Hz, demean, cut −5 to 30 s"* and watch it happen, no script
in between.

## The one-server-per-toolchain design

Each toolchain gets its **own MCP server**, and you mount only the ones you
need. This isn't aesthetic — it's a context-budget decision. Every mounted
server contributes its tool definitions to the agent's working context;
splitting by toolchain means an agent doing a quick ObsPy read doesn't also
carry SU/SAC schemas. Adding a future toolchain (Madagascar, GMT, …) is a new
package with zero changes to the others.

```
seismo-mcp/
├── packages/obspy-mcp/    ← uvx obspy-mcp
├── packages/cwp-su-mcp/   ← uvx cwp-su-mcp
└── packages/sac-mcp/      ← uvx sac-mcp
```

## Servers

| Server | Wraps | Tools | Install |
|---|---|---|---|
| **[obspy-mcp](packages/obspy-mcp)** | ObsPy (Python lib) | read / filter / preprocess / resample / convert / plot | `claude mcp add obspy -- uvx obspy-mcp` |
| **[cwp-su-mcp](packages/cwp-su-mcp)** | CWP/SU: Seismic Un\*x | gethw / count / filter / gain / wind / sort / sethw | `claude mcp add su -- uvx cwp-su-mcp` |
| **[sac-mcp](packages/sac-mcp)** | SAC (Seismic Analysis Code) | listhdr / preprocess / filter / cut / merge / transfer | `claude mcp add sac -- uvx sac-mcp` |

Each server is self-contained — no cross-package dependencies — so each
publishes and installs independently. See each package's README for its tool
table, requirements, and examples.

## Three wrapping patterns

The interesting engineering in this project is that the three backends need
**three different wrapping strategies**:

| Backend | Shape | Wrapping pattern |
|---|---|---|
| ObsPy | Python library | in-process `import` — tools call ObsPy directly |
| CWP-SU | CLI, Unix-pipe programs | `subprocess` with concurrent stdout/stderr drain + timeout |
| SAC | interactive REPL | feed a command script to the interpreter's stdin (batch mode) |

CWP-SU programs read SU traces from stdin and write to stdout; the wrapper
feeds bytes and drains both pipes concurrently to avoid the classic pipe
deadlock, with a timeout so a hung trace can't wedge the server. SAC is a
``SAC>`` prompt, so the wrapper builds a small script (`r file → op → w out →
q`) and pipes it in — plus injects the correct `SACHOME`/`SACAUX`, because
SAC's bundled `sacinit.sh` hard-codes `/usr/local/sac` and breaks user-dir
installs.

## Design principles

- **Binary trace data never enters the model context.** Read tools return
  *summaries* (trace id, npts, timing); processing tools write a new file and
  return its path. Waveforms belong on disk or in a plot, not in the token
  stream.
- **Each tool is a typed function.** Type hints + docstring become the JSON
  schema — the agent can't pass a malformed flag the way it can when free-form
  shell-ing a CLI.
- **Failures are readable.** A CWP/SAC error is captured and returned as text,
  so the agent sees *"wagc too long for trace"* instead of a silent nonzero
  exit.
- **One `diagnose_environment` per server.** Call first to confirm the
  backend's installed and where; the agent learns what's usable before
  reaching for a tool that isn't there.

## Requirements

- Python ≥ 3.10
- For `cwp-su-mcp`: a working CWP-SU install (`CWPROOT` set)
- For `sac-mcp`: a working SAC install (`SACHOME`/`SACAUX`)
- `obspy-mcp` pulls ObsPy in automatically

## Development

This repo is a [uv](https://docs.astral.sh/uv/) workspace.

```sh
uv sync                                      # set up all packages
uv run --package obspy-mcp python examples/_test_obspy_mcp.py
uv build --package sac-mcp                   # build one server
```

Each package has its own end-to-end test in `examples/` that drives the tools
against real data on the local install.

## Status

Three servers, three wrapping patterns, ~22 tools, all tested against real
local installs of ObsPy / CWP-SU / SAC. CPS (Computer Programs in Seismology)
is a possible future addition — its control-file workflow makes it the hardest
to wrap cleanly.

## License

MIT. See [LICENSE](LICENSE) and each package's LICENSE.
