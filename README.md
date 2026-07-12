# seismo-mcp

> **Let AI assistants process seismic waveforms by chatting — no code, no scripts.**
>
> **让 AI 助手通过对话处理地震波形——不写代码，不写脚本。**

[English](#what-is-this) · [中文](#这是什么)

---

## What is this?

**seismo-mcp** is a bridge between AI assistants (like Claude, Cursor) and
the software seismologists actually use: [ObsPy](https://obspy.org),
[CWP/SU](https://wiki.seismic-unix.org), and [SAC](https://ds.iris.edu/ds/nodes/dmc/software/downloads/sac/).

Normally, to filter a seismogram you open a terminal and type something like
`sac` commands or write a Python script with ObsPy. With seismo-mcp
installed, you just **tell the AI what you want in plain language**, and it
calls the right tool for you.

### A 30-second example

Install it once. Then, in Claude Desktop:

> **You:** Here's `event.sac`. Bandpass filter 0.5–2 Hz, remove the mean, then
> cut −5 to 30 seconds and show me the first trace.

The assistant calls the `sac-mcp` tools behind the scenes — it reads the
header, filters, preprocesses, cuts, and plots — and hands you back the
processed file and a plot. **You never wrote a line of code.**

```
you: "bandpass 0.5-2 Hz, demean, cut -5 to 30 s, plot"
         │
         ▼  (the assistant decides which tools to call)
   ┌─────────────────────────────────────────┐
   │ seismo-mcp servers (already installed)   │
   │   sac-mcp  →  sac_filter / preprocess /  │
   │               cut / plot                 │
   └─────────────────────────────────────────┘
         │
         ▼  (the server runs the real software)
   SAC / ObsPy / CWP-SU  (your local install)
         │
         ▼
   processed file + plot, handed back to you
```

## Why would I want this?

- **For researchers & students** — skip the "how do I write this command
  again?" friction. Describe the processing, get the result.
- **For multi-toolchain workflows** — ObsPy, SU, and SAC speak different
  dialects; seismo-mcp gives the assistant one consistent way to reach all
  three.
- **For teaching & demos** — show seismology processing live, in plain
  language, without a screen full of shell commands.

## How do I use it?

### 1. Install one or more servers

Pick only what you need. Each server is independent.

| Server | Use it if you work with | Install command |
|---|---|---|
| **obspy-mcp** | ObsPy / general waveform I/O | `claude mcp add obspy -- uvx obspy-mcp` |
| **cwp-su-mcp** | CWP/SU reflection processing | `claude mcp add su -- uvx cwp-su-mcp` |
| **sac-mcp** | SAC waveform analysis | `claude mcp add sac -- uvx sac-mcp` |
| **gmt-mcp** | Maps & plots (PyGMT) | `claude mcp add gmt -- uvx gmt-mcp` |

> **Prerequisite:** the relevant software must be installed on your computer
> (ObsPy is auto-installed by `obspy-mcp`; CWP-SU, SAC, and the GMT binary
> must be installed separately). See the [install guide](docs/INSTALL.md) for details.
>
> **Note:** `uvx` comes from [uv](https://docs.astral.sh/uv/) — install it
> with `brew install uv` (macOS/Linux) if you don't have it. The packages
> will be on PyPI soon; until then see [INSTALL.md](docs/INSTALL.md) for the
> from-source method.

### 2. Restart your AI assistant and just ask

After installing, restart Claude Desktop (or your MCP-compatible client).
Then describe what you want — the assistant will use the tools automatically.

**Example things to say:**
- *"Read `shot.su`, how many traces and what's the sample interval?"*
- *"Bandpass this SAC file 2–10 Hz and plot it."*
- *"Convert `trace.sac` to MiniSEED."*
- *"Apply AGC with a 0.5 s window to `gather.su`, then sort by offset."*

## What's inside?

Three independent servers, each wrapping one toolchain:

| Server | What it can do |
|---|---|
| **[obspy-mcp](packages/obspy-mcp)** | Read any waveform format (SAC/MSEED/SEG-Y…), filter, preprocess, resample, convert formats, plot. |
| **[cwp-su-mcp](packages/cwp-su-mcp)** | Seismic Unix trace ops: read headers, filter, gain (AGC), window, sort, set headers. |
| **[sac-mcp](packages/sac-mcp)** | SAC waveform ops: list headers, preprocess, filter, cut, merge, remove instrument response. |
| **[gmt-mcp](packages/gmt-mcp)** | Maps & plots: basemaps, coastlines, epicenter/station maps, x-y plots, labels. |

## Who is this for?

- **Seismologists** who want a faster way to drive their existing tools.
- **Students** learning seismology — see what each operation does, in plain words.
- **Anyone curious** about connecting scientific software to AI assistants.

## Learn more

- 📖 **[Install guide](docs/INSTALL.md)** — step-by-step setup (ObsPy, CWP-SU, SAC, uv).
- 🛠 **[Design & technical details](docs/DESIGN.md)** — why one server per
  toolchain, the three wrapping patterns, what gotchas were solved.
- 🔧 **[Each server's README](packages/)** — full tool tables and examples.

## Status

Working and tested against real local installs of ObsPy / CWP-SU / SAC / PyGMT.
Four servers, ~28 tools. Feedback and contributions welcome.

## License

MIT — see [LICENSE](LICENSE).

---

<a id="这是什么"></a>
## 中文

### 这是什么？

**seismo-mcp** 是一座桥，把 AI 助手（Claude、Cursor 等）和地震学家真正在用的
软件连起来：[ObsPy](https://obspy.org)、[CWP/SU](https://wiki.seismic-unix.org)、
[SAC](https://ds.iris.edu/ds/nodes/dmc/software/downloads/sac/)。

平时，要处理一个地震波形，你得打开终端敲 `sac` 命令，或用 ObsPy 写 Python 脚
本。装上 seismo-mcp 后，你只需**用大白话告诉 AI 你要什么**，它就会替你调用相应
的工具。

### 一个 30 秒的例子

安装一次。然后在 Claude Desktop 里：

> **你：** 这是 `event.sac`。带通滤波 0.5–2 Hz，去均值，截取 −5 到 30 秒，
> 然后画第一道给我看。

助手会在后台调用 `sac-mcp` 的工具——读头、滤波、预处理、截取、绘图——然后把
处理好的文件和图交给你。**你全程没写一行代码。**

### 我为什么要用？

- **研究者和学生**——跳过"这个命令怎么写来着"的折腾，描述你要的处理，直接拿
  结果。
- **跨工具链的工作流**——ObsPy、SU、SAC 各说各的方言；seismo-mcp 给了助手一
  个统一的方式触达三者。
- **教学和演示**——用大白话现场展示地震处理过程，不用满屏的 shell 命令。

### 怎么用？

**1. 安装你需要的 server（按需，互相独立）**

| Server | 适用场景 | 安装命令 |
|---|---|---|
| **obspy-mcp** | ObsPy / 通用波形读写 | `claude mcp add obspy -- uvx obspy-mcp` |
| **cwp-su-mcp** | CWP/SU 反射地震处理 | `claude mcp add su -- uvx cwp-su-mcp` |
| **sac-mcp** | SAC 波形分析 | `claude mcp add sac -- uvx sac-mcp` |
| **gmt-mcp** | 地图与绘图（PyGMT）| `claude mcp add gmt -- uvx gmt-mcp` |

> **前提：** 相应软件需已装在本机（ObsPy 会由 `obspy-mcp` 自动安装；CWP-SU、
> SAC 和 GMT 二进制需自行安装）。详见[安装指南](docs/INSTALL.md)。

**2. 重启 AI 助手，直接开口**

装好后重启 Claude Desktop（或其他支持 MCP 的客户端），然后用大白话描述需求，
助手会自动调用工具。

**可以这样说：**
- *"读一下 `shot.su`，多少道？采样率多少？"*
- *"把这个 SAC 文件带通滤波 2–10 Hz，然后画出来。"*
- *"把 `trace.sac` 转成 MiniSEED。"*
- *"对 `gather.su` 做 0.5 秒窗口的 AGC，然后按 offset 排序。"*

### 里面有什么？

三个独立 server，各封装一个工具链：

| Server | 能做什么 |
|---|---|
| **[obspy-mcp](packages/obspy-mcp)** | 读各种波形格式（SAC/MSEED/SEG-Y…）、滤波、预处理、重采样、格式转换、绘图。 |
| **[cwp-su-mcp](packages/cwp-su-mcp)** | 地震 Unix 道处理：读头、滤波、增益（AGC）、时窗、排序、设头。 |
| **[sac-mcp](packages/sac-mcp)** | SAC 波形操作：读头、预处理、滤波、截取、合并、去仪器响应。 |
| **[gmt-mcp](packages/gmt-mcp)** | 地图与绘图：底图、海岸线、震中/台站分布、x-y 图、文字标注。 |

### 想了解更多

- 📖 **[安装指南](docs/INSTALL.md)** —— 分步设置（ObsPy、CWP-SU、SAC、uv）。
- 🛠 **[设计与技术细节](docs/DESIGN.md)** —— 为什么一工具链一 server、三种封装模式、解决了哪些坑。
- 🔧 **[各 server 的 README](packages/)** —— 完整工具表和示例。

### 状态

已在真实安装的 ObsPy / CWP-SU / SAC / PyGMT 上测试通过。四个 server、约 28 个
工具。欢迎反馈和贡献。

### 许可证

MIT —— 见 [LICENSE](LICENSE)。
