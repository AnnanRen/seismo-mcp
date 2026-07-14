# obs-raw-mcp

An [MCP](https://modelcontextprotocol.io) server that lets LLM agents drive
**IGGCAS OBS raw → SAC / SU conversion** — the proprietary binary format
written by the institute's ocean-bottom seismometers, decoded by the
companion `raw2su` / `graw2sac` programs (Wang Yuan, IGGCAS) — without
leaving the chat.

> Part of [**seismo-mcp**](../..), a toolkit where each seismology toolchain
> gets its own focused MCP server. Mount only what you need.

## Why

IGGCAS OBS deployments record in a **proprietary binary format** that no
standard tool can read. Conversion requires two in-house programs
(`raw2su` → SU shot gathers, `graw2sac` → continuous SAC), plus three
mechanical steps that are easy to get wrong by hand:

1. each station's data is split across ~16 raw shards (~11.5 h each) that
   must be binary-merged **in DATAFILE.LST order**, keeping the first
   file's hex name (the converters parse the hex prefix to detect format);
2. the sampling rate (`sps`) and Time-Control value (`TC`) live in two
   separate metadata files (`DATAFILE.LST`, `A201606.LOG`) — `TC` must be
   the *last* occurrence in the LOG (the instrument can be restarted);
3. `graw2sac` (V3.0) has a fixed bug: the SAC `npts` header is ~44 samples
   short, which makes obspy reject the file.

This server automates all of that. An agent can say *"convert station C10
to SAC"* and the server resolves the directory, extracts the parameters,
merges, converts, fixes npts, and returns the file paths.

## Install

```sh
claude mcp add obs-raw -- uvx obs-raw-mcp
```

**Requires** the IGGCAS `raw2su` and `graw2sac` binaries on `PATH` (Wang
Yuan, IGGCAS — not open-source). The server probes both via
`shutil.which`; call `diagnose_environment` first to confirm.

## Tools

| Tool | What it does |
|---|---|
| `diagnose_environment` | Confirm `raw2su` and `graw2sac` are on PATH. |
| `scan_station` | Resolve `<id>_*` dir, extract `sps` / `TC` / raw-file list from metadata. |
| `raw_to_sac` | Merge shards → `graw2sac` → fix npts → 4 continuous SAC components. |
| `raw_to_su` | Merge shards → `raw2su` with UKOOA shot file → 4 SU shot gathers. |
| `fix_sac_npts` | Repair the graw2sac `npts` bug on a standalone SAC file. |

**Design:** every conversion tool runs in an isolated workdir under the
output directory, merges the raw shards there (keeping the first file's hex
name), runs the converter, fixes the npts header, moves the outputs into
place, and returns a one-line summary with file paths and sizes. Binary
trace data never enters the model context.

## Example session

> **You:** Scan station C10 in `/Volumes/.../YS2016OBS-RAW`, then convert it
> to continuous SAC.
>
> **Agent:** *calls* `scan_station` → sps=250, TC=2359293972, 16 raw files.
> *calls* `raw_to_sac(...)` → `C10.bh1.sac`, `C10.bh2.sac`, `C10.bhz.sac`,
> `C10.hyd.sac` (4 files, ~640 MB each). ✓

## Station-directory layout expected

```
<raw_root>/
├── C10_A36/                      ← <station>_<serial>
│   ├── DATAFILE.LST              ← raw-file list + sps (parsed by scan_station)
│   ├── A201606.LOG               ← TC value (last TC= line wins)
│   ├── 41ACED87.453              ← raw shards (hex-named)
│   ├── 41AE284A.504
│   └── ...
├── ukooa_YS2016.txt              ← UKOOA shot file (for raw_to_su)
└── C01_L73_ex/                   ← _ex / _lost dirs are skipped
```

## Known limitations

- **Proprietary dependency.** The server wraps `raw2su` / `graw2sac`; it
  cannot decode the raw format itself. Users must obtain those binaries
  from IGGCAS.
- **graw2sac npts bug.** Fixed inline by `raw_to_sac`; call `fix_sac_npts`
  only for SAC files produced elsewhere.
- **Excluded stations.** Directories ending in `_ex` (metadata damaged) or
  `_lost` (data missing) are skipped by `find_station_dir`.

## Development

Self-contained — no sibling-package dependencies.

```sh
uv build --package obs-raw-mcp
uv publish
```

License: MIT (the wrapped `raw2su` / `graw2sac` binaries are separate and
not distributed here).
