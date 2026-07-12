# Design & Technical Details / 设计与技术细节

[English](#english) · [中文](#中文-1)

<a id="english"></a>

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

---

<a id="中文-1"></a>
## 中文

> 本文件写给想了解 seismo-mcp *底层怎么工作* 的人——架构决策、三种封装模式、
> 以及必须解决的真实坑。"这是什么 / 怎么用"请看[主 README](../README.md)。

### MCP server 到底解决了什么问题？

AI 智能体（Claude、Cursor……）擅长*决定*做什么，但它没法直接调用你电脑上的函
数。中间没有东西的话，让助手"滤波一个波形"，就意味着让它**写并执行代码**去 shell
调 `sac` 或 `import obspy`。这能用，但：

- 助手可能记错命令参数（`f=5,40` 还是 `f=5-40` 还是 `--freq 5 40`？）；
- 没有可复用的边界——每次对话都重新发明调用方式；
- 自由格式的 shell 命令什么都能干，包括破坏性操作；
- 输出（巨大的二进制波形数组）有淹没模型上下文的风险。

**MCP server** 夹在助手和你的工具之间，暴露**预先定义好的、带类型的工具**。助
手调用 `sac_filter(input, output, freqmin, freqmax)`；server 校验参数、正确运
行 SAC、返回有界的摘要。助手的工作变成*表达意图*，而不是*拼写语法*。

```
助手  ──MCP 协议──▶  seismo-mcp server (Python)  ──subprocess/import──▶  ObsPy / SU / SAC
                       ↑ 带类型的工具                ↑ 真正的活
                  （schema 由类型注解
                   + docstring 生成）
```

MCP 本身只是助手和 server 之间的**通信协议**——不管哪个助手（Claude、
Cursor……）、哪个后端（命令行、Python 库……），都是同一套标准。

### 为什么一个工具链一个 server？

每挂载一个 MCP server，它**全部工具的定义**（名称、描述、参数的 JSON schema）
就会进入助手整场对话的工作上下文。这个上下文是有限的，塞得太满会让助手变慢、
更费 token。

如果把 ObsPy + SU + SAC 塞进一个 server，那一个只想快速读波形的 ObsPy 会话，也
得额外背着它用不上的 ~22 个工具 schema。按工具链拆分意味着——你只挂载需要的，
助手只看到相关的工具。附带好处：将来加新工具链（Madagascar、GMT）只需新建一个
包，对现有包零改动。

### 三种封装模式

核心的技术趣味在于：三个后端形态完全不同，所以各自需要不同的封装策略。

#### 1. ObsPy —— 进程内 Python import（obspy-mcp）

ObsPy 是**Python 库**。server 直接 import 它、在同一进程里调用——没有
subprocess、没有序列化。这是最干净的情况。

```python
@mcp.tool()
def filter_waveform(input_path, output_path, freqmin=1.0, freqmax=20.0):
    from obspy import read
    st = read(input_path)
    st.filter("bandpass", freqmin=freqmin, freqmax=freqmax)
    st.write(output_path)
    return _summarize(st)   # 文字摘要，不是数据数组
```

**关键规则：** 返回*摘要*（道 ID、采样点数、时间范围），绝不返回采样数组——
100 Hz 采样的 60 秒波形是 24 KB 浮点数，不该塞进模型的 token 流。

#### 2. CWP-SU —— subprocess 排空管道（cwp-su-mcp）

CWP-SU 是一族约 450 个**命令行程序**，遵循经典 Unix 管道规矩：每个从 stdin 读
SU 格式道数据、往 stdout 写、往 stderr 记日志。server shell 出去，喂入/接收字
节。

三个坑，全在 `run_su()` helper 里处理：

| 坑 | 缓解措施 |
|---|---|
| **管道死锁**——阻塞在 stdout 上而 stderr 填满缓冲区，两边都卡住 | `subprocess.run(..., capture_output=True)` 并发排空两者 |
| **进程卡死**——一条不正常的道可能拖死整个 server（及整场对话）| 每次调用都带 `timeout`（默认 300 秒）|
| **二进制输出**——SU 道是二进制；当文本解码会无声损坏数据 | stdout 保持 `bytes`，绝不解码 |

**一个值得注意的特例：** `susort` 是少数*拒绝*通过管道读写（它强制 DISK→DISK
I/O）的 CWP-SU 程序之一。对它，`su_sort` 工具退回到 shell 重定向
（`susort key < in > out`），而非其他工具用的内存管道。

#### 3. SAC —— 交互式 REPL，批处理驱动（sac-mcp）

SAC 是**交互式解释器**（一个 `SAC>` 提示符，类似地震学版的 Python）。没有单个
"滤波"二进制；你在会话里发一串命令。server 的 `run_sac_batch()` helper 拼出小
脚本喂进去：

```
r input.sac
rmean
bp co 0.1 1.0 n 4 p 2
w output.sac
q
```

……然后捕获会话日志，返回一行摘要。

**macOS 专属怪癖：** SAC 自带的 `sacinit.sh` 把 `SACHOME` 硬编码成
`/usr/local/sac`。任何不装在 `/usr/local/sac` 的安装（个人 Mac 上的常见情况），
SAC 都会立即退出并报 *"aux directory not Found"*。`_sac_env()` helper 在每次启
动前**从检测到的根目录覆盖 `SACHOME`/`SACAUX`**，于是用户目录安装也能直接用。

**快速读头**用独立的 `saclst` 二进制而非启动整个 REPL——快得多，而且 `saclst`
有自己的怪癖：参数顺序是 `saclst <字段...> f <文件...>`（`f` 标记夹在字段和文
件*之间*），很容易写错。

### 设计原则（汇总）

1. **二进制波形数据绝不进入模型上下文。** 读取类工具返回摘要；处理类工具写文
   件、返回路径。波形待在磁盘上或图里。
2. **每个工具都是带类型的函数。** 类型注解 + docstring 经 FastMCP 自动生成
   JSON schema——助手根本没法把参数传错，因为 schema 约束了它。
3. **失败要是可读的文字。** CWP/SAC 的报错（`wagc too long for trace`、
   `key word not in segy.h`）从 stderr 捕获并返回给助手，让它能推理哪里出问题，
   而不是看到一个无声的非零退出码。
4. **每个 server 第一个工具都是 `diagnose_environment`。** 助手该先调它——报告
   后端装没装、在哪，让助手在伸手用某个工具前先知道它到底能不能用。
5. **自包含的包。** 每个 server 把自己需要的那 ~100 行 helper（subprocess /
   plot / env 检测）内联进来，而不是依赖一个共享的内部包。这意味着每个都能单
   独发到 PyPI、用 `uvx <名字>` 独立安装——不需要伴随包。

### 决策：为什么（暂）不包含 CPS

考虑过 [Computer Programs in Seismology](https://www.eas.slu.edu/eqc/eqccps.html)
（CPS，Herrmann）。它的核心命令（如面波反演 `srfinv96`）不只吃命令行参数——
它们需要**预先生成的文本控制文件**（模型文件、`dfile`、`tmpsrfi.09`……）。干净
地封装 CPS 意味着 server 必须*正确生成那些控制文件*，这对格式很敏感，对一个相
对小的用户群来说工作量大。它是合理的未来补充，但 v0.1 没纳入。

### 项目结构

```
seismo-mcp/                        ← uv workspace 根（不发布）
├── packages/
│   ├── obspy-mcp/                 ← 独立发布: uvx obspy-mcp
│   │   ├── pyproject.toml         ← 声明依赖 + console 入口
│   │   ├── README.md              ← 工具表、示例
│   │   └── src/obspy_mcp/
│   │       ├── server.py          ← @mcp.tool 定义
│   │       └── _helpers.py        ← 内联的 plot/env helper
│   ├── cwp-su-mcp/                ← 同结构
│   └── sac-mcp/                   ← 同结构
├── docs/                          ← 本文件 + INSTALL.md
├── examples/                      ← 每个 server 的端到端测试
└── pyproject.toml                 ← 仅用于 workspace 协调
```

每个包的 `pyproject.toml` 声明一个 `[project.scripts]` console 入口（如
`obspy-mcp = obspy_mcp.server:main`），所以一旦发布，`uvx obspy-mcp` 就通过
stdio 启动 server。

### 技术栈

- **Python ≥ 3.10**，用 [uv](https://docs.astral.sh/uv/) workspace 管理。
- **[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)**
  （`mcp` 包），用内置的 FastMCP 1.0 API
  （`from mcp.server.fastmcp import FastMCP`）。锁定 `mcp>=1.27,<2`——v2 SDK 还
  是 alpha，不适合生产。
- **FastMCP** 把类型注解 + docstring 自动转成 JSON schema；
  `Image(data=..., format="png")` 返回内联图。
- **matplotlib** 用无头 `Agg` 模式绘图。
- 构建/发布用 `uv build` + `uv publish`（PyPI）。
