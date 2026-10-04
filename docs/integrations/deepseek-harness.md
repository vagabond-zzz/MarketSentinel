# DeepSeek Harness (DSH) 集成

Market Sentinel 通过标准 **MCP stdio** 接入 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)（`dsh`，developer preview）。本文档记录配置方式与实际宿主验证结果。

```text
DSH session
  ↓ MCP stdio（dsh-mcp-client，mcp__market-sentinel__*）
Market Sentinel MCP server（standalone runtime）
  ↓
MarketCapabilities（只读）
  ↓
Deterministic Core
```

## 1. 验证环境

| 项 | 值 |
|---|---|
| 验证日期 | 2026-10-05（UTC+8） |
| OS | Windows 10.0.26200 |
| DSH | **0.2.0-rc.2**（npm `@deepseek-ai/dsh`，全局安装，`dsh headless` 驱动） |
| dsh-mcp-client | **0.2.0-rc.2**（随 dsh 包内置，无需单独安装） |
| Node / npm | v22.23.1 / 12.1.0 |
| Python / uv | 3.12.1 / `D:/uv/bin/uv.exe` |
| Market Sentinel | 0.6.5 + `[mcp]` extra（mcp SDK 1.30.0），commit `482e8b8` 后 |
| 默认模型 | `deepseek-official / deepseek-flash`（headless profile 默认） |

## 2. 配置方式（实际使用的机制）

DSH 配置是 **Cordis entry 组合**。MCP server 以 entry 形式注入，形状由官方模板定义（`dsh-agent-preset` 的 `templates/mcp/cordis.patch.yml`）：

```yaml
- insert:
    - id: mcp-market-sentinel
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: market-sentinel
        transport: stdio
        command: D:/uv/bin/uv.exe
        args: ['--directory', '<repo-root>', 'run', 'market-sentinel', 'mcp']
        failOnStartupError: false
```

注入途径二选一：

- **`--patch overlay.yml`**（本次验证使用）：每次启动时叠加，**不持久化**任何配置；
- 写入 profile 的 `cordis.patch.yml`（持久，属于用户私有配置，**不要提交进 Market Sentinel 仓库**）。

关键字段（dsh-mcp-client 0.2.0-rc.2 README 为准）：`serverName`（工具命名空间，`[A-Za-z0-9_-]{1,32}`）、stdio 的 `command/args/env/cwd`、`toolCallTimeoutMs`（默认 60000）、`failOnStartupError`（默认 false：启动失败时 harness 照常运行、仅无该 server 工具并记日志）、`reconnect`（默认启用：initial 500ms 指数退避，上限 30s / 10 次）。

serverName 使用了两个：`market-sentinel`（fake）与 `market-sentinel-replay`（replay fixture），验证了命名空间隔离（`mcp__<serverName>__<tool>`）。

## 3. 工具面

与 ZCode / 任意 MCP 客户端一致：恰好 6 个只读工具，`mcp__market-sentinel__*`；输出统一信封 `{"ok": true, "data"}` / `{"ok": false, "error": {"code","message"}}`；错误码 `not_found / invalid_argument / not_running / unavailable / timeout / internal`。无写 / 配置 / 交易 / shell / 文件系统工具，无 resources / prompts（DSH 侧确认 "Resources: none"）。

## 4. 验证结果（真实 `dsh headless` 会话）

| # | 验证项 | 结果 | 证据摘要 |
|---|---|---|---|
| 1 | MCP discovery | **VERIFIED** | 会话可见恰好 6 个 `mcp__market-sentinel__*` 工具，无多余/隐藏工具 |
| 2 | 直调 happy path（5/6 工具） | **VERIFIED** | 信封 `ok:true`；watchlist=3；price/LIVE/health 正常；无 traceback |
| 3 | capability error | **VERIFIED** | `BAD`→invalid_argument、`00700.HK`→not_found、未知 signal→not_found，信封逐字透传 |
| 4 | schema 拒绝（limit 0 / 201） | **VERIFIED** | 到达 tool 前被 pydantic schema 拒绝（greater_than_equal / less_than_equal），信息明确，**与 capability 信封清晰可区分**，无 traceback |
| 5 | replay → event → MCP → DSH | **VERIFIED** | watchlist 从 fixture 推导；轮询数轮后 `get_recent_events` 返回真实 vwap_cross 事件；事件对象恰好 8 个字段，**无 metrics / dedupe_key / ttl_s** |
| 6 | Agent-level tool use | **VERIFIED** | 服务器日志见真实 `CallToolRequest`；agent 回答完全引用工具返回数据（价格/level/age），未虚构 |
| 7 | Negative permission test | **VERIFIED** | 要求加 watchlist / 下单 / 改配置：agent 确认 **三个操作在工具面中均不可表达**，零状态变更，未借助 shell |
| 8 | Reconnect | **VERIFIED**（透明） | 会话中途强制杀掉 server 进程链（uv→market-sentinel.exe→python），模型侧 15 次调用**零失败**，会话继续拿到新鲜事件并以干净关闭结束 |
| 9 | Shutdown / 孤儿进程 | **VERIFIED** | 全部 8 个会话退出后进程表无任何 market-sentinel 相关 uv/python/node 进程 |
| 10 | DSH 沙箱与 shell | **OBSERVED** | headless 沙箱拒绝在 repo 目录附近执行 shell 写（`SetNamedSecurityInfoW Win32 5`）且无审批通道——DSH preview 行为，与 MCP 路径无关；用 MCP 轮询绕过 |

未验证 / UNKNOWN：DSH Desktop/Web GUI 中的呈现、`reconnect` 上限耗尽后的表现（10 次连续失败）、其他 DSH 版本。

## 5. Troubleshooting

| 现象 | 处理 |
|---|---|
| 会话中看不到 market-sentinel 工具 | ① 先在终端跑 `uv run market-sentinel mcp` 确认 server 可启动；② 确认 overlay/patch 的 `name:` 是 `@deepseek-ai/dsh-mcp-client` 且 entry 已被组合（`dsh --profile headless --patch overlay.yml --dump-config` 检查）；③ 看 DSH 启动日志中 mcp-client 的错误（`failOnStartupError:false` 时失败是静默的，只有日志） |
| 工具在但调用超时 | `toolCallTimeoutMs` 默认 60s；server 冷启动慢时加大该值 |
| 同名 server 冲突 | 同一注册 scope 内 `serverName` 必须唯一，后加载者报明确错误 |
| 插件版本不匹配警告 | DSH 对 peerDependencies 严格（本验证中出现 2 个无关社区插件被跳过）；`dsh-mcp-client` 内置于 dsh 包，版本天然匹配 |

## 6. 已知限制

- DSH 为 **developer preview**（0.2.0-rc.2）：API 可能变化，升级后需复验；
- 验证仅覆盖 `headless` profile + stdio transport；GUI/Web profile 与 streamable-http 未验证；
- DSH 桥接 MCP **tools** 与 resources 读取；Market Sentinel 未提供 resources/prompts，故实际可用面就是 6 个工具；
- replay 模式下 feed 会显示 DELAYED（fixture 的 market_timestamp 滞后于墙钟，属正确语义，不是故障）。

## 7. 安全边界（本验证确认）

- DSH 侧只能调用 6 个只读工具；agent 亲自确认加 watchlist / 下单 / 改配置在工具面中不存在；
- 无 shell / 文件系统 / 任意代码工具来自 Market Sentinel（DSH 自带的通用工具与其沙箱是 DSH 自身的权限体系，与本项目无关）；
- 凭据只走环境变量；配置文件（overlay / patch）不含任何凭据，也不进入 Market Sentinel 仓库。
