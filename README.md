# seismo-mcp

> **A toolkit of focused [MCP](https://modelcontextprotocol.io) servers that let LLM agents drive seismology software — without writing code.**
>
> **一套面向地震学软件的 MCP（模型上下文协议）服务器工具集——让 AI 智能体直接操作 ObsPy / CWP-SU / SAC，无需编写代码。**

[English](#english) · [中文](#中文)

---

<a id="english"></a>
## English

Seismology runs on a handful of venerable, powerful, and famously crusty
toolchains: [ObsPy](https://obspy.org), [CWP/SU](https://wiki.seismic-unix.org),
and [SAC](https://ds.iris.edu/ds/nodes/dmc/software/downloads/sac/). They live
on the command line or inside Python scripts. **seismo-mcp turns their everyday
operations into tools an agent can call directly** — so you can say *"bandpass
this SAC file 0.5–2 Hz, demean, cut −5 to 30 s"* and watch it happen, with no
script in between.

### Why

Asking an LLM to "process this seismogram" usually means letting it write and
run code that calls these tools. That works, but it's slow and error-prone:
the agent can misremember flag syntax (`f=5,40`? `f=5-40`?), invent parameters,
and there's no reusable boundary between the agent and the binary. seismo-mcp
instead exposes **pre-wrapped, typed tools** — the agent calls `sac_filter(...)`,
the server runs SAC correctly, every time. The agent's job becomes *deciding
what to do*, not *figuring out how to type it*.

### The one-server-per-toolchain design

Each toolchain gets its **own MCP server**, and you mount only the ones you
need. This is a deliberate context-budget decision: every mounted server
contributes its tool definitions to the agent's working context, so splitting
by toolchain means an agent doing a quick ObsPy read doesn't also carry SU/SAC
schemas. Adding a future toolchain (Madagascar, GMT, …) is a new package with
zero changes to the others.

```
seismo-mcp/
├── packages/obspy-mcp/    ← uvx obspy-mcp
├── packages/cwp-su-mcp/   ← uvx cwp-su-mcp
└── packages/sac-mcp/      ← uvx sac-mcp
```

### Servers

| Server | Wraps | Tools | Install |
|---|---|---|---|
| **[obspy-mcp](packages/obspy-mcp)** | ObsPy (Python lib) | read / filter / preprocess / resample / convert / plot | `claude mcp add obspy -- uvx obspy-mcp` |
| **[cwp-su-mcp](packages/cwp-su-mcp)** | CWP/SU: Seismic Un\*x | gethw / count / filter / gain / wind / sort / sethw | `claude mcp add su -- uvx cwp-su-mcp` |
| **[sac-mcp](packages/sac-mcp)** | SAC (Seismic Analysis Code) | listhdr / preprocess / filter / cut / merge / transfer | `claude mcp add sac -- uvx sac-mcp` |

Each server is self-contained — no cross-package dependencies — so each
publishes and installs independently. See each package's README for its tool
table, requirements, and examples.

### Three wrapping patterns

The interesting engineering here is that the three backends need **three
different wrapping strategies**:

| Backend | Shape | Wrapping pattern |
|---|---|---|
| ObsPy | Python library | in-process `import` — tools call ObsPy directly |
| CWP-SU | CLI, Unix-pipe programs | `subprocess` with concurrent stdout/stderr drain + timeout |
| SAC | interactive REPL | feed a command script to the interpreter's stdin (batch mode) |

CWP-SU programs read SU traces from stdin and write to stdout; the wrapper
feeds bytes and drains both pipes concurrently to avoid the classic pipe
deadlock, with a timeout so a hung trace can't wedge the server. SAC is a
`SAC>` prompt, so the wrapper builds a small script (`r file → op → w out → q`)
and pipes it in — plus injects the correct `SACHOME`/`SACAUX`, because SAC's
bundled `sacinit.sh` hard-codes `/usr/local/sac` and breaks user-dir installs.

### Design principles

- **Binary trace data never enters the model context.** Read tools return
  *summaries* (trace id, npts, timing); processing tools write a new file and
  return its path. Waveforms belong on disk or in a plot, not in the token
  stream.
- **Each tool is a typed function.** Type hints + docstring become the JSON
  schema — the agent can't pass a malformed flag the way it can when
  free-form shell-ing a CLI.
- **Failures are readable.** A CWP/SAC error is captured and returned as text,
  so the agent sees *"wagc too long for trace"* instead of a silent nonzero
  exit.
- **One `diagnose_environment` per server.** Call first to confirm the
  backend's installed and where; the agent learns what's usable before
  reaching for a tool that isn't there.

### Requirements

- Python ≥ 3.10
- For `cwp-su-mcp`: a working CWP-SU install (`CWPROOT` set)
- For `sac-mcp`: a working SAC install (`SACHOME`/`SACAUX`)
- `obspy-mcp` pulls ObsPy in automatically

### Development

This repo is a [uv](https://docs.astral.sh/uv/) workspace.

```sh
uv sync                                                        # set up all packages
uv run --package obspy-mcp python examples/_test_obspy_mcp.py  # run a server's tests
uv build --package sac-mcp                                     # build one server
```

Each package has an end-to-end test in `examples/` that drives its tools
against real data on the local install.

### Status

Three servers, three wrapping patterns, ~22 tools, all tested against real
local installs of ObsPy / CWP-SU / SAC. CPS (Computer Programs in Seismology)
is a possible future addition — its control-file workflow makes it the hardest
to wrap cleanly.

### License

MIT. See [LICENSE](LICENSE) and each package's LICENSE.

---

<a id="中文"></a>
## 中文

地震学依赖几套历史悠久、功能强大、但出了名"难用"的工具链：
[ObsPy](https://obspy.org)、[CWP/SU](https://wiki.seismic-unix.org)、
[SAC](https://ds.iris.edu/ds/nodes/dmc/software/downloads/sac/)。它们要么在命令
行里，要么藏在 Python 脚本里。**seismo-mcp 把这些工具的日常操作封装成 AI
智能体可以直接调用的工具**——你只需说"把这个 SAC 文件带通滤波 0.5–2 Hz、去均
值、截取 −5 到 30 秒"，它就自动完成，中间不需要写任何代码。

### 为什么做这个

让大模型"处理一个地震波形"，通常意味着让它写代码去调用这些工具。这能用，但慢
且容易出错：模型可能记错命令参数（`f=5,40` 还是 `f=5-40`？）、编造不存在的选
项，而且模型和二进制程序之间没有可复用的边界。seismo-mcp 转而提供**预先封装
好的、带类型签名的工具**——模型调用 `sac_filter(...)`，服务器每次都正确地跑
SAC。模型的工作变成"决定做什么"，而不是"搞清楚怎么敲命令"。

### 为什么每个工具链一个独立 server

每个工具链都有**自己的 MCP server**，你只挂载需要的那几个。这是一个有意为之
的"上下文预算"决策：每个挂载的 server 都会把它所有工具的定义送进模型的上下
文，所以按工具链拆分意味着——一个只想快速读个波形的 ObsPy 会话，不必额外背着
SU/SAC 的工具定义。将来要加新工具链（Madagascar、GMT……），只需新建一个包，
对现有包零改动。

```
seismo-mcp/
├── packages/obspy-mcp/    ← uvx obspy-mcp
├── packages/cwp-su-mcp/   ← uvx cwp-su-mcp
└── packages/sac-mcp/      ← uvx sac-mcp
```

### 三个 server 一览

| Server | 封装对象 | 工具 | 安装命令 |
|---|---|---|---|
| **[obspy-mcp](packages/obspy-mcp)** | ObsPy（Python 库） | 读取 / 滤波 / 预处理 / 重采样 / 格式转换 / 绘图 | `claude mcp add obspy -- uvx obspy-mcp` |
| **[cwp-su-mcp](packages/cwp-su-mcp)** | CWP/SU 地震 Unix | 读头 / 计数 / 滤波 / 增益 / 时窗 / 排序 / 设头 | `claude mcp add su -- uvx cwp-su-mcp` |
| **[sac-mcp](packages/sac-mcp)** | SAC（地震分析代码） | 读头 / 预处理 / 滤波 / 截取 / 合并 / 去仪器响应 | `claude mcp add sac -- uvx sac-mcp` |

每个 server 自包含——包与包之间无依赖——所以各自独立发布、独立安装。各包的
README 里有完整的工具表、依赖说明和使用示例。

### 三种封装模式

本项目真正有技术含量的地方在于：三个后端需要**三种完全不同的封装策略**：

| 后端 | 形态 | 封装方式 |
|---|---|---|
| ObsPy | Python 库 | 进程内 `import`——工具直接调用 ObsPy |
| CWP-SU | 命令行、Unix 管道程序 | `subprocess`，并发排空 stdout/stderr + 超时保护 |
| SAC | 交互式 REPL | 把命令脚本喂给解释器的 stdin（批处理模式） |

CWP-SU 的程序从 stdin 读 SU 道数据、往 stdout 写；封装层喂入字节流，并发排空两
个管道以避免经典的管道死锁，并加超时，防止一条卡死的道把整个服务器拖住。SAC 是
一个 `SAC>` 提示符环境，封装层因此拼出一段小脚本（`r 文件 → 操作 → w 输出 → q`）
喂进去——此外还注入了正确的 `SACHOME`/`SACAUX`，因为 SAC 自带的 `sacinit.sh`
把路径硬编码成了 `/usr/local/sac`，在用户目录安装时会直接崩溃。

### 设计原则

- **二进制波形数据绝不进入模型上下文。** 读取类工具只返回*摘要*（道 ID、采样
  点数、时间范围）；处理类工具写一个新文件并返回路径。波形应该待在磁盘上或图
  里，而不是塞进 token 流。
- **每个工具都是一个带类型签名的函数。** 类型注解 + docstring 自动生成 JSON
  schema——模型没法像手敲命令行那样传错参数。
- **失败要可读。** CWP/SAC 的报错被捕获并以文本返回，模型能看到"wagc too long
  for trace"，而不是一个无声的非零退出码。
- **每个 server 第一个工具都是 `diagnose_environment`。** 先调它确认后端装好
  了、在哪——模型在伸手用某个工具前，先知道它到底能不能用。

### 环境要求

- Python ≥ 3.10
- `cwp-su-mcp` 需要本机已装 CWP-SU（设置了 `CWPROOT`）
- `sac-mcp` 需要本机已装 SAC（设置了 `SACHOME`/`SACAUX`）
- `obspy-mcp` 会自动拉取 ObsPy

### 开发

本仓库是一个 [uv](https://docs.astral.sh/uv/) workspace。

```sh
uv sync                                                        # 初始化所有包
uv run --package obspy-mcp python examples/_test_obspy_mcp.py  # 跑某个 server 的测试
uv build --package sac-mcp                                     # 构建单个 server
```

每个包在 `examples/` 里都有一个端到端测试，用本机真实数据驱动它的全部工具。

### 当前状态

三个 server、三种封装模式、约 22 个工具，全部已用本机真实安装的 ObsPy / CWP-SU
/ SAC 测试通过。CPS（Computer Programs in Seismology）是未来可能加入的——它的
控制文件工作流是几套里最难干净封装的。

### 许可证

MIT。见 [LICENSE](LICENSE) 及各包的 LICENSE。
