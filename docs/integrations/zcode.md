# ZCode 集成

Market Sentinel 通过标准 **MCP stdio** 接入 [ZCode](https://zcode.z.ai)（CLI / Desktop）。本文档记录配置方式与实际宿主验证结果。

```text
ZCode session
  ↓ MCP stdio (mcp__market-sentinel__*)
Market Sentinel MCP server（standalone runtime）
  ↓
MarketCapabilities（只读）
  ↓
Deterministic Core
```

## 1. 前置条件

- ZCode CLI / Desktop（本验证使用 **0.16.9**）
- Python 3.12+ 与 uv；在 Market Sentinel 仓库执行 `uv sync --extra mcp`
- 先用 `market-sentinel doctor` 确认 `mcp extra` 为 ✓

## 2. 配置方式

### User scope（推荐，所有会话可用）

`~/.zcode/cli/config.json`：

```json
{
  "mcp": {
    "servers": {
      "market-sentinel": {
        "type": "stdio",
        "command": "<uv 绝对路径>",
        "args": [
          "--directory", "<repo-root>",
          "run", "market-sentinel", "mcp"
        ]
      }
    }
  }
}
```

Windows 实例（本验证机实际使用的值，路径以你自己的安装为准）：

```json
{
  "mcp": {
    "servers": {
      "market-sentinel": {
        "type": "stdio",
        "command": "D:/uv/bin/uv.exe",
        "args": [
          "--directory", "D:/1/3-wk/Market_Sentinel",
          "run", "market-sentinel", "mcp"
        ]
      }
    }
  }
}
```

可复制的模板见 [`examples/mcp/zcode-mcp-servers.json`](../../examples/mcp/zcode-mcp-servers.json)。

### Workspace scope（仅当前项目）

`<repo>/.zcode/config.json`，结构与上面相同。注意：

- **同名 server 时 user 覆盖 workspace**；想并存时用不同名字（如 `market-sentinel-replay`），工具名相应变成 `mcp__market-sentinel-replay__*`；
- workspace 配置用不同 provider（如 replay）验证事件流很方便，但**不要把包含机器绝对路径的 workspace 配置提交进 git**。

### 平台注意

| 平台 | 要点 |
|---|---|
| Windows | `command` 用 uv 的绝对路径（正斜杠或转义反斜杠均可）；JSON 内反斜杠需转义 |
| macOS / Linux | `command: "uv"` 仅当 ZCode 进程 PATH 含 uv 时可用，否则给 `which uv` 的绝对路径 |
| 所有平台 | ZCode 配置 schema 严格——未知键会**静默丢弃**整个 server 条目；启动超时默认 30s（`timeoutMs` 可调） |

## 3. 工具面

ZCode 会发现恰好 6 个只读工具（namespace `mcp__market-sentinel__*`）：

```text
get_market_state / get_symbol_state / get_active_signals
get_signal / get_feed_health / get_recent_events
```

输出统一信封 `{"ok": true, "data": ...}` / `{"ok": false, "error": {"code", "message"}}`；错误码 `not_found / invalid_argument / not_running / unavailable / timeout / internal`。无任何写 / 配置 / 交易 / shell / 文件系统工具。

## 4. 验证环境

| 项 | 值 |
|---|---|
| 验证日期 | 2026-10-05（UTC+8） |
| ZCode | Desktop + CLI **0.16.9**（Windows 10.0.26200） |
| Market Sentinel | 0.6.5 + MCP extra（mcp SDK 1.30.0），commit `7efdbda` 后 |
| server command | `D:/uv/bin/uv.exe --directory D:/1/3-wk/Market_Sentinel run market-sentinel mcp` |

## 5. 验证结果（真实 ZCode headless 会话，`zcode -p`）

| # | 验证项 | 结果 | 证据摘要 |
|---|---|---|---|
| 1 | Tool discovery | **VERIFIED** | 会话内可见恰好 6 个 `mcp__market-sentinel__*` 工具，命名与预期一致 |
| 2 | get_market_state / get_feed_health / get_symbol_state / get_active_signals | **VERIFIED** | 信封 `ok:true`；watchlist_count=3（fake 默认标的）；aggregate=LIVE；price 返回正常 |
| 3 | get_recent_events（fake） | **VERIFIED** | `ok:true, data:[]`——fake provider 行情静止，空是文档化语义，非故障 |
| 4 | 错误传播（invalid_argument / not_found） | **VERIFIED** | `BAD`→invalid_argument；`00700.HK`→not_found；未知 signal→not_found；信封逐字透传到会话 |
| 5 | 参数 schema 边界（limit 0 / 201） | **VERIFIED** | 在到达 tool 前被 MCP schema 校验拒绝（too_small / too_big），会话内可见明确信息 |
| 6 | replay 事件流（workspace 配置 `--provider replay`） | **VERIFIED** | watchlist 从 fixture 自动推导；45s 后 `get_recent_events` 返回真实 vwap_cross 事件；feed=D ELAYED（replay 时间戳滞后，语义正确） |
| 7 | 坏配置可诊断性 | **OBSERVED（部分）** | 会话内只表现为"无工具"；宿主日志（`~/.zcode/cli/log/zcode-*.jsonl`）精确记录 `mcp.server.failed` + spawn stderr。见 troubleshooting |
| 8 | 多 server 隔离 | **VERIFIED** | 同会话 4 个 MCP server：坏 server 失败不影响 market-sentinel 正常连接 |
| 9 | 生命周期 / 孤儿进程 | **VERIFIED** | 多轮调用 + 45s+ 长会话后全部退出；`tasklist` 无残留 python/uv/market-sentinel 进程 |

未验证：ZCode Desktop GUI 的 Settings → MCP 界面呈现（headless 验证覆盖协议与会话层；GUI 状态面板行为随版本变化，未单独截图验证）。

## 6. Troubleshooting

| 现象 | 原因 / 处理 |
|---|---|
| 会话里看不到任何 `mcp__market-sentinel__*` 工具 | server 启动失败。先在终端跑 `uv run market-sentinel mcp` 确认能启动；再查 `market-sentinel doctor` 的 mcp extra 行 |
| 确认 server 本身没问题但仍连不上 | 查 ZCode 日志 `~/.zcode/cli/log/zcode-<date>.jsonl`，搜 `mcp.server.failed`——其中 stderr 字段包含 spawn 级错误（如 uv 路径不存在）；GUI 用户看 Settings → MCP 的状态列 |
| 日志里 stderr 中文乱码 | Windows 控制台 GBK 编码问题，不影响功能；错误本质通常是 `xxx 不是内部或外部命令`（路径错误） |
| server 时连时断 / 超时 | uv 冷启动偏慢时给条目加 `"timeoutMs": 60000` |
| 配置改了但会话没反应 | MCP server 在**会话启动时**连接；改配置后需要新开会话 |
| 工具出现但调用报 schema 错误 | 参数类型错误（如 symbol 传数字）；错误信息含 `InputValidationError`，按 tool schema 修正参数即可 |

## 7. 安全边界（本验证确认）

- ZCode 侧只能调用 6 个只读工具；无 shell、无任意代码、无文件系统写、无配置变更、无交易能力；
- 凭据只走环境变量，不写入任何 ZCode 配置文件；MCP 输出不含凭据（有测试断言）；
- market-sentinel 的 ZCode 配置属于用户私有文件，不进 Market Sentinel 仓库。

## 8. 已知限制

- 验证覆盖 ZCode 0.16.9；其他版本的 MCP 行为以 ZCode 官方文档为准；
- ZCode 只桥接 MCP **tools**；resources/prompts 未暴露（Market Sentinel 也未提供）；
- fake provider 下 `get_recent_events` 恒为空——要看事件流请用 replay fixture 配置（见上文验证 #6）；
- MCP server 是独立 runtime，不与 Cursor 扩展共享状态。
