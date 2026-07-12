# gmt-mcp

An [MCP](https://modelcontextprotocol.io) server that lets LLM agents make
maps with [PyGMT](https://pygmt.org) (the Python interface to the Generic
Mapping Tools) — basemaps, coastlines, epicenter/station maps, x-y plots —
without writing code.

> Part of [**seismo-mcp**](../..). Mount only what you need.

## Install

```sh
claude mcp add gmt -- uvx gmt-mcp
```

**Requires** PyGMT (auto-installed) AND the GMT binary
(`brew install gmt` on macOS).

## Tools

| Tool | What it does |
|---|---|
| `diagnose_environment` | Check PyGMT + GMT binary are available. |
| `make_basemap` | Base map with optional coastline → PNG. |
| `coast_map` | Coastline/bathymetry map (no data) → PNG. |
| `plot_points` | Plot (lon,lat) points (epicenters, stations) → PNG. |
| `plot_xy` | Cartesian x-y scatter/line plot → PNG. |
| `text_on_map` | Add text labels to a map → PNG. |

See the main repo README for the full toolkit and demo.
