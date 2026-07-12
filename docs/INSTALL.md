# Installation Guide / 安装指南

[English](#english) · [中文](#中文)

---

<a id="english"></a>
## English

> Plain-language setup. For the 30-second version, see the
> [main README](../README.md). This doc covers prerequisites, per-client
> configuration for five AI assistants, and troubleshooting.

### TL;DR

```sh
brew install uv                                        # install uv (macOS/Linux)
claude mcp add obspy -- uvx obspy-mcp                  # mount a server (Claude Code)
```

That's it for ObsPy. CWP-SU and SAC need their own software installed first.

### Prerequisites

**Python & uv.** seismo-mcp servers are Python packages run via
[uv](https://docs.astral.sh/uv/), which creates isolated environments so
nothing pollutes your system Python.

```sh
brew install uv          # macOS/Linux
uv --version             # verify: "uv 0.11.x"
```

**The seismology software.** Each server wraps a toolchain you install
separately:

| Server | Software needed | Check it's installed |
|---|---|---|
| `obspy-mcp` | ObsPy | (auto-installed — nothing to do) |
| `cwp-su-mcp` | CWP-SU (Seismic Un\*x) | `echo $CWPROOT` set; `which sufilter` works |
| `sac-mcp` | SAC (Seismic Analysis Code) | `which sac` works; `SACHOME` set |
| `gmt-mcp` | PyGMT + GMT binary | `which gmt` works (`brew install gmt` on macOS) |

If you don't have CWP-SU, SAC, or GMT yet: [CWP-SU](https://wiki.seismic-unix.org)
(free, open-source), [SAC](https://ds.iris.edu/ds/nodes/dmc/software/downloads/sac/)
(free, requires registration), [GMT](https://www.generic-mapping-tools.org)
(`brew install gmt` on macOS; PyGMT is auto-installed by `gmt-mcp`).

### Installing the servers

**From PyPI (once published):**
```sh
uvx obspy-mcp    # runs the latest published version in an isolated env
```

**From source (for now / development):**
```sh
git clone https://github.com/AnnanRen/seismo-mcp.git
cd seismo-mcp
uv sync
```

### Configuring your AI assistant

Different AI assistants read MCP config from different places. **Pick the one
you use.** All examples below mount the `obspy-mcp` server — swap the package
name for `cwp-su-mcp` or `sac-mcp` as needed.

#### Claude Desktop (the desktop app)

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "obspy": {
      "command": "uvx",
      "args": ["obspy-mcp"]
    }
  }
}
```

⚠️ **Claude Desktop is a GUI app — it does NOT inherit your shell PATH.** If
`uvx` isn't found, use an absolute path: run `which uvx` in a terminal and
paste that path (e.g. `/Users/you/.local/bin/uvx`) as `command`.

#### Claude Code (the CLI)

Simplest — one command:

```sh
claude mcp add obspy -- uvx obspy-mcp
```

Scopes: `--scope local` (default, this project), `--scope user` (all your
projects), `--scope project` (writes `.mcp.json` to share with a team).

#### Codex (OpenAI Codex CLI)

Edit `~/.codex/config.toml` (TOML format, not JSON):

```toml
[mcp_servers.obspy]
command = "uvx"
args = ["obspy-mcp"]
```

Verify with `codex mcp list`. (stdio transport only; remote MCP not natively
supported.)

#### OpenCode (sst/opencode)

Edit `~/.config/opencode/opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "obspy": {
      "type": "local",
      "command": ["uvx", "obspy-mcp"],
      "enabled": true
    }
  }
}
```

⚠️ **OpenCode-specific:** `command` is a **single array** combining the
executable and its args — there's no separate `args` field. Don't paste the
Claude-style format here.

#### ZCode

Edit `~/.zcode/cli/config.json`:

```json
{
  "mcp": {
    "servers": {
      "obspy": {
        "type": "stdio",
        "command": "uvx",
        "args": ["obspy-mcp"]
      }
    }
  }
}
```

⚠️ **ZCode-specific:** `command` is a **string**, `args` is an **array**.
Unknown top-level keys silently drop the server — keep it minimal.

#### Cross-client cheat sheet

| Client | Config file (macOS) | Format | `command` field | Inherits shell PATH? |
|---|---|---|---|---|
| Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json` | JSON `mcpServers` | `"command": "uvx"` | **No** — use absolute path |
| Claude Code | `~/.claude.json` (or `.mcp.json`) | JSON; `claude mcp add` | `claude mcp add n -- uvx <pkg>` | Yes |
| Codex | `~/.codex/config.toml` | TOML `[mcp_servers.n]` | `command = "uvx"` | Yes |
| OpenCode | `~/.config/opencode/opencode.json` | JSON `mcp` | `"command": ["uvx","<pkg>"]` | Yes |
| ZCode | `~/.zcode/cli/config.json` | JSON `mcp.servers` | `"command": "uvx"` | Yes |

### Verifying

After installing and restarting your client, ask the assistant:
> *Check the environment for this server.*

It should call `diagnose_environment` and report `OK: ... found at /path`.

### Troubleshooting

**"command not found" / `spawn uvx ENOENT`** — the client can't find `uvx`.
Most likely you're on Claude Desktop (which doesn't inherit PATH). Run
`which uvx` in a terminal and use that absolute path as `command`.

**"CWP-SU not found" / "sac not found"** — the server can't find the software.
Either it isn't installed, or it's not on the server's PATH. Set `env`
explicitly in the config:
```json
"env": { "PATH": "/usr/local/sac/bin:/usr/local/cwp/bin:/usr/bin:/bin" }
```

**SAC: "aux directory not Found"** — SAC's `sacinit.sh` hard-codes
`/usr/local/sac`. If SAC is elsewhere, set it explicitly:
```json
"env": { "SACHOME": "/Users/you/src/sac", "SACAUX": "/Users/you/src/sac/aux" }
```

**Tool returns a file path instead of showing data** — intentional. Waveform
arrays are too big for the model's context, so processing tools write a file
and return the path. Open it yourself, or ask the assistant to plot it.

---

<a id="中文"></a>
## 中文

> 大白话的安装说明。30 秒极简版见[主 README](../README.md)。本文件涵盖前置依赖、
> 五款 AI 助手各自的配置方法，以及故障排查。

### 极简流程

```sh
brew install uv                                        # 安装 uv (macOS/Linux)
claude mcp add obspy -- uvx obspy-mcp                  # 挂载某个 server (Claude Code)
```

ObsPy 无需额外操作。CWP-SU 和 SAC 需先自行安装相应软件。

### 前置依赖

**Python 和 uv。** seismo-mcp 的 server 是 Python 包，通过
[uv](https://docs.astral.sh/uv/) 运行——uv 会创建隔离环境，不会污染你的系统
Python。

```sh
brew install uv          # macOS/Linux
uv --version             # 验证: 应显示 "uv 0.11.x"
```

**地震学软件本身。** 每个 server 封装的工具链需单独安装：

| Server | 需要的软件 | 检查是否已装 |
|---|---|---|
| `obspy-mcp` | ObsPy |（自动安装，无需操作）|
| `cwp-su-mcp` | CWP-SU（地震 Unix）| `echo $CWPROOT` 已设；`which sufilter` 有结果 |
| `sac-mcp` | SAC（地震分析代码）| `which sac` 有结果；`SACHOME` 已设 |
| `gmt-mcp` | PyGMT + GMT 二进制 | `which gmt` 有结果（macOS: `brew install gmt`）|

若还没装 CWP-SU、SAC 或 GMT：[CWP-SU](https://wiki.seismic-unix.org)（免费开
源）、[SAC](https://ds.iris.edu/ds/nodes/dmc/software/downloads/sac/)（免费，
需注册）、[GMT](https://www.generic-mapping-tools.org)（macOS 用 `brew install gmt`；PyGMT 由 `gmt-mcp` 自动安装）。

### 安装 server

**从 PyPI（发布后）：**
```sh
uvx obspy-mcp    # 在隔离环境里运行最新发布版
```

**从源码（当前 / 开发用）：**
```sh
git clone https://github.com/AnnanRen/seismo-mcp.git
cd seismo-mcp
uv sync
```

### 配置你的 AI 助手

不同 AI 助手读取 MCP 配置的位置不同。**选你用的那一个。** 下面示例都挂载
`obspy-mcp`——把包名换成 `cwp-su-mcp` 或 `sac-mcp` 即可装别的。

#### Claude Desktop（桌面应用）

编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "obspy": {
      "command": "uvx",
      "args": ["obspy-mcp"]
    }
  }
}
```

⚠️ **Claude Desktop 是图形应用，不继承你 shell 的 PATH。** 若提示找不到
`uvx`，在终端运行 `which uvx`，把得到的绝对路径（如
`/Users/你/.local/bin/uvx`）填到 `command` 里。

#### Claude Code（命令行工具）

最简单——一条命令：

```sh
claude mcp add obspy -- uvx obspy-mcp
```

作用域：`--scope local`（默认，当前项目）、`--scope user`（你的所有项目）、
`--scope project`（写入 `.mcp.json`，供团队共享）。

#### Codex（OpenAI Codex CLI）

编辑 `~/.codex/config.toml`（TOML 格式，不是 JSON）：

```toml
[mcp_servers.obspy]
command = "uvx"
args = ["obspy-mcp"]
```

用 `codex mcp list` 验证。（仅支持 stdio 传输，不原生支持远程 MCP。）

#### OpenCode（sst/opencode）

编辑 `~/.config/opencode/opencode.json`：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "obspy": {
      "type": "local",
      "command": ["uvx", "obspy-mcp"],
      "enabled": true
    }
  }
}
```

⚠️ **OpenCode 专属：** `command` 是**单个数组**，把可执行文件和参数合在一起
——没有单独的 `args` 字段。别把 Claude 的格式粘到这里。

#### ZCode

编辑 `~/.zcode/cli/config.json`：

```json
{
  "mcp": {
    "servers": {
      "obspy": {
        "type": "stdio",
        "command": "uvx",
        "args": ["obspy-mcp"]
      }
    }
  }
}
```

⚠️ **ZCode 专属：** `command` 是**字符串**，`args` 是**数组**。多余的字段会让
server 被静默丢弃——保持精简。

#### 五客户端速查表

| 客户端 | 配置文件（macOS）| 格式 | `command` 写法 | 继承 shell PATH？|
|---|---|---|---|---|
| Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json` | JSON `mcpServers` | `"command": "uvx"` | **否**——用绝对路径 |
| Claude Code | `~/.claude.json`（或 `.mcp.json`）| JSON；`claude mcp add` | `claude mcp add n -- uvx <pkg>` | 是 |
| Codex | `~/.codex/config.toml` | TOML `[mcp_servers.n]` | `command = "uvx"` | 是 |
| OpenCode | `~/.config/opencode/opencode.json` | JSON `mcp` | `"command": ["uvx","<pkg>"]` | 是 |
| ZCode | `~/.zcode/cli/config.json` | JSON `mcp.servers` | `"command": "uvx"` | 是 |

### 验证

装好并重启客户端后，问助手：
> *检查一下这个 server 的环境。*

它应调用 `diagnose_environment`，返回 `OK: ... found at /路径`。

### 故障排查

**"command not found" / `spawn uvx ENOENT`**——客户端找不到 `uvx`。多半是用
Claude Desktop（不继承 PATH）。在终端 `which uvx`，用那个绝对路径作为
`command`。

**"CWP-SU not found" / "sac not found"**——server 找不到软件。要么没装，要么不
在 server 的 PATH 上。在配置里显式设 `env`：
```json
"env": { "PATH": "/usr/local/sac/bin:/usr/local/cwp/bin:/usr/bin:/bin" }
```

**SAC: "aux directory not Found"**——SAC 自带的 `sacinit.sh` 把路径硬编码成
`/usr/local/sac`。若 SAC 装在别处，显式设置：
```json
"env": { "SACHOME": "/Users/你/src/sac", "SACAUX": "/Users/你/src/sac/aux" }
```

**工具返回了文件路径而不是显示数据**——这是**设计如此**，不是报错。波形数组
太大，不能塞进模型上下文，所以处理类工具写文件、返回路径。你自己打开文件，
或让助手画图（图会以内联图片返回）。
