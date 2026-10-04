# MCP Server 集成

Market Sentinel 通过 **MCP（Model Context Protocol）** 把只读观察能力暴露给 AI Agent 宿主（ZCode、DeepSeek Harness、Claude Desktop 等任何支持 MCP 的客户端）。

```text
Market Sentinel Core
        ↓
MarketCapabilities        （只读能力层，M2）
        ↓
MCP stdio server          （薄适配层，本文件）
        ↓
ZCode / DeepSeek Harness / 其他 MCP 客户端
```

## standalone runtime 是什么

MCP server 运行**自己独立的 Core runtime**：它启动自己的 Provider → Engine → tick loop，并把每个已完成 tick 喂给 capabilities（这样 `get_recent_events` 才有数据）。

必须明确：

- **它不连接 Cursor daemon**，不共享 daemon 状态，不走 Protocol v1；
- 一个进程一份 runtime；MCP 查询不写 telemetry（NoOp 默认），不会混入 CLI/daemon 的评估数据集；
- 默认 **fake / replay**（无 API key、无网络、确定性）；live 是显式 opt-in（见下文）。

## 安装

MCP SDK 是 optional extra，核心安装不含它：

```bash
uv sync --extra mcp                      # 项目 checkout
pip install 'market-sentinel[mcp]'       # 已安装的包
```

用 `market-sentinel doctor` 可确认 `mcp extra` 状态。

## 启动

```bash
market-sentinel mcp                                       # fake provider，默认 3 只 A 股演示标的
market-sentinel --provider replay --replay <fixture.jsonl> mcp
market-sentinel --watchlist data/watchlist.json mcp       # 用 watchlist 文件
market-sentinel mcp --symbols 600519.SH,000001.SZ         # 显式标的列表
```

标的解析顺序：`--symbols` > 已存在的 `--watchlist` 文件 > provider 默认（fake=三只演示标的；replay=从 fixture 首行推导；longbridge **无默认，缺失即启动失败**）。

**live mode（显式 opt-in）**：`--provider longbridge` 必须同时给 `--live` 才能启动（否则 fail-closed）；凭据只走既有环境变量（`LONGBRIDGE_APP_KEY` / `LONGBRIDGE_APP_SECRET` / `LONGBRIDGE_ACCESS_TOKEN`），doctor 只报凭据名存在性，从不打印值。

## Tools（6 个，全部只读）

| Tool | 输入 | 返回（`data` 字段） |
|---|---|---|
| `get_market_state` | — | `WireMarketState`：整表快照 |
| `get_symbol_state` | `symbol: string` | `WireSymbolState` |
| `get_active_signals` | — | `{symbol: [WireSignal...]}` |
| `get_signal` | `signal_id: string` | `WireSignal`（含 intelligence annotation） |
| `get_feed_health` | — | `FeedHealthReport` |
| `get_recent_events` | `symbol?: string, limit?: int(1..200)` | `[EventView...]`（无 metrics/dedupe_key/ttl） |

**输出信封**（所有 tool 统一）：

```json
{"ok": true,  "data": { ... }}
{"ok": false, "error": {"code": "not_found", "message": "..."}}
```

**错误码**（稳定，勿按 message 解析）：`not_found` / `invalid_argument` / `not_running` / `unavailable` / `timeout` / `internal`。参数类型错误（如 symbol 传数字）由 MCP schema 校验层拒绝，表现为 `isError: true` 的 tool result。

没有的 tool（永远不会加在只读层）：set_watchlist、configure_*、tune、deploy、trade、execute、restart、shell、文件系统访问。

## 客户端配置（stdio）

通用 `mcpServers` 形状（Claude Desktop 风格）：

```json
{
  "mcpServers": {
    "market-sentinel": {
      "command": "uv",
      "args": ["--directory", "<repo-root>", "run", "market-sentinel", "mcp"]
    }
  }
}
```

平台差异：

- **Windows**：`command` 建议用 `uv` 的绝对路径（如 `D:\\uv\\bin\\uv.EXE`）；`<repo-root>` 写成绝对路径；JSON 里反斜杠需转义。
- **macOS / Linux**：`command: "uv"` 需在客户端进程 PATH 中，否则给绝对路径。
- 不要假设固定安装路径；`<repo-root>` 是你自己 clone 的位置。

具体宿主的示例片段见 `examples/mcp/`。

## 宿主支持状态（诚实声明）

| 宿主 | SUPPORTED BY MARKET SENTINEL | VERIFIED AGAINST HOST |
|---|---|---|
| 任意标准 MCP 客户端（stdio + tools） | 是 | **是**——协议级集成测试（initialize / tools/list / tools/call / 干净退出、stdout 纯净性） |
| ZCode | 是（标准 stdio MCP server，配置即接入） | **是**——ZCode 0.16.9（Windows）真实会话验证：discovery / 6 工具调用 / 错误传播 / replay 事件流 / 多 server 隔离 / 生命周期全过；详见 [zcode.md](zcode.md)（2026-10-05） |
| DeepSeek Harness | 是（经其官方 `@deepseek-ai/dsh-mcp-client`，stdio；仅桥接 tools，不桥接 resources/prompts） | **未验证**——DSH 处于 developer preview，配置方式见 `examples/mcp/`，M5 验证后回填 |

> 结论：Market Sentinel 侧交付的是一个**经过协议级验证的标准 MCP server**；"在某个宿主里可用"的最终判定以各宿主验证记录为准，未验证前不声称支持。

### ZCode 验证矩阵（2026-10-05，ZCode 0.16.9 / Windows）

| Layer | Status |
|---|---|
| MCP stdio protocol | VERIFIED（集成测试） |
| MarketSentinel MCP server | VERIFIED |
| ZCode MCP discovery | VERIFIED |
| ZCode tool invocation（6/6） | VERIFIED |
| ZCode error propagation（envelope + schema 边界） | VERIFIED |
| Replay 事件流（tick → observe_tick → tool → ZCode） | VERIFIED |
| 多 server 隔离 / 生命周期 / 无孤儿进程 | VERIFIED |
| 坏配置的会话内报错 | OBSERVED（仅宿主日志可诊断，会话内静默；见 zcode.md troubleshooting） |
| ZCode Desktop GUI Settings → MCP 呈现 | UNKNOWN（headless 验证未覆盖 GUI） |
| 其他 ZCode 版本 | UNKNOWN |

## 与 Cursor 宿主的关系

Cursor / VS Code 扩展继续走**专有 Protocol v1 daemon**（亚秒级推送 + 双向命令，MCP 不适合这个场景）。两条路径并存、互不依赖；不要试图让 MCP server 挂到 daemon 进程上。

## 安全边界

- 全部 tools 只读：Agent 可以 **Observe / Investigate / Explain**，不能 **Modify / Execute / Trade**；
- 不修改 watchlist / scheduler / provider / intelligence 配置 / tuning / 生产参数；
- 无文件系统、shell、任意代码执行工具；
- MCP runtime 不写 telemetry 文件（NoOp），不产生可交易建议（Intelligence 默认关闭）；
- 凭据永不进入 MCP 输出（有测试断言）。

## 已知边界

- `get_signal` 只覆盖 episode 生命周期内的 signal，无历史查询（Core 不保留过期 signal）；
- `get_recent_events` 的数据来自 runtime 自己的 tick loop；fake provider 行情静止，通常无事件——用 replay fixture 才能看到事件流；
- `serverInfo.version` 反映 MCP SDK 版本（FastMCP 不透出自定义版本），包版本以 `market-sentinel doctor` 为准；
- live mode 使用与 CLI 相同的 `MarketProvider` 抽象，Longbridge 语义（session-cumulative volume 等）见 `docs/architecture/provider-source-audit.md`。
