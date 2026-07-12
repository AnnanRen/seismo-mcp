# Installation Guide

> Plain-language setup for seismo-mcp. If you just want the 30-second version,
> see the [main README](../README.md). This doc covers prerequisites, each
> client's config, and troubleshooting.

## TL;DR

```sh
# 1. Install uv (if you don't have it)
brew install uv          # macOS/Linux. Or: curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Mount the server(s) you want in your MCP client
claude mcp add obspy -- uvx obspy-mcp
claude mcp add su     -- uvx cwp-su-mcp
claude mcp add sac    -- uvx sac-mcp

# 3. Restart your client and just ask.
```

That's it for ObsPy. CWP-SU and SAC need their own software installed first
(see below).

---

## Prerequisites

### Python & uv

seismo-mcp servers are Python packages. You need:

- **Python ≥ 3.10** (3.12 recommended)
- **[uv](https://docs.astral.sh/uv/)** — a fast Python package runner. `uvx`
  (bundled with uv) runs the servers in isolated environments without
  polluting your system Python.

Install uv:
```sh
# macOS / Linux
brew install uv
# or
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Verify:
```sh
uv --version    # should print something like "uv 0.11.x"
```

### The seismology software itself

Each server wraps a toolchain that must be **installed separately** on your
computer. The server talks to it; it doesn't include it.

| Server | Software needed | How to check it's installed |
|---|---|---|
| `obspy-mcp` | ObsPy | (auto-installed by the server — nothing to do) |
| `cwp-su-mcp` | CWP-SU (Seismic Un\*x) | `echo $CWPROOT` should be set; `which sufilter` works |
| `sac-mcp` | SAC (Seismic Analysis Code) | `which sac` works; `SACHOME` set |

**If you don't have CWP-SU or SAC yet**, you need to install them first —
seismo-mcp can't help without the underlying software. See their official docs:
- CWP-SU: https://wiki.seismic-unix.org (free, open-source)
- SAC: https://ds.iris.edu/ds/nodes/dmc/software/downloads/sac/ (free, requires registration)

---

## Installing the servers

### Option A: From PyPI (recommended, once published)

After the packages are on PyPI, this is the one-line install:

```sh
claude mcp add obspy -- uvx obspy-mcp
```

`uvx` downloads the package on first run, creates an isolated environment,
and launches it. You never manage the Python deps yourself.

### Option B: From source (for now, or for development)

Until PyPI publishing, run directly from a clone:

```sh
git clone https://github.com/AnnanRen/seismo-mcp.git
cd seismo-mcp
uv sync                           # set up all packages

# Mount from the local clone (Claude Code / Cursor):
claude mcp add obspy -- uv run --directory . --package obspy-mcp python -m obspy_mcp.server
```

(Adjust the path to point at your clone.)

---

## Configuring your MCP client

Different AI clients read MCP config from different places. The
`claude mcp add` command handles Claude Desktop/Code automatically. For other
clients, edit their config file manually.

### Claude Desktop (macOS)

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "obspy": {
      "command": "uvx",
      "args": ["obspy-mcp"]
    },
    "sac": {
      "command": "uvx",
      "args": ["sac-mcp"],
      "env": {
        "SACHOME": "/usr/local/sac",
        "SACAUX": "/usr/local/sac/aux",
        "PATH": "/usr/local/sac/bin:/usr/bin:/bin"
      }
    }
  }
}
```

> **Note the `env` block for `sac`:** MCP clients don't run servers from a
> login shell, so environment variables like `SACHOME` and `PATH` aren't
> inherited. You may need to set them explicitly here so the server can find
> SAC/CWP-SU binaries. (The servers also try to auto-detect common install
> paths, but explicit `env` is the most reliable.)

### Cursor

In Cursor settings → MCP, add servers via the UI, or edit
`~/.cursor/mcp.json` with the same structure as Claude Desktop above.

### Other clients (VS Code, etc.)

Any client that speaks MCP accepts the same `{command, args, env}` shape. See
your client's docs for where its config file lives.

---

## Verifying it works

After installing and restarting your client, ask the assistant:

> *Check the environment for the obspy / su / sac server.

It should call `diagnose_environment`, which reports whether the backend is
found. If you see `OK: ... found at /path`, you're set. If you see an error,
read on.

---

## Troubleshooting

### "CWP-SU not found" / "sac not found"

The server can't find the software on PATH. Either:

1. **The software isn't installed.** Install CWP-SU / SAC first (links above).
2. **It's installed but not on the server's PATH.** MCP clients don't launch
   servers from a login shell, so your `~/.zshrc` PATH edits don't apply.
   Fix it by setting `env` explicitly in the client config (see the Claude
   Desktop example above — set `PATH` to include the software's `bin` dir).

### SAC: "aux directory not Found"

SAC's bundled `sacinit.sh` hard-codes `SACHOME=/usr/local/sac`. If you
installed SAC somewhere else (e.g. `~/src/sac`), set `SACHOME` and `SACAUX`
explicitly in the client config's `env` block:

```json
"env": {
  "SACHOME": "/Users/you/src/sac",
  "SACAUX": "/Users/you/src/sac/aux"
}
```

The `sac-mcp` server also auto-detects common paths, but explicit is safer.

### `uvx: command not found`

Install uv (see Prerequisites above).

### The tool runs but returns "ERROR: ..."

The server captured an error from the underlying software. The error text is
returned to the assistant verbatim — read it; it usually names the problem
(e.g. `"wagc too long for trace"` means your AGC window exceeds the trace
length). Fix the parameters and try again.

### Tool returns a file path instead of showing the data

This is **intentional**, not an error. Waveform arrays are too large for the
model's context, so processing tools write a new file and return the path.
Open the file yourself, or ask the assistant to plot it (the plot comes back
as an inline image).

---

## Uninstalling

Remove the server from your client (delete its entry from the config file,
or `claude mcp remove <name>`), then if you installed from PyPI:

```sh
uv cache clean    # optional: clears uvx-cached packages
```

There's nothing else to clean up — `uvx` runs everything in isolated
environments that are auto-managed.
