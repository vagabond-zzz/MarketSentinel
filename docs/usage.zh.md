# 使用手册（中文 / Usage Guide）

> 本手册承接早期 README 的操作细节，覆盖 package `0.7.0` + productization M2–M10（capabilities / demo / doctor / MCP）。
> 项目概览、架构与安全边界见根目录 [README](../README.md)；命令均经实际验证。

## 1. 环境要求与安装

- Python `3.12+`、[uv](https://docs.astral.sh/uv/)
- Node.js `20+`、`pnpm`（仅扩展开发需要）
- Cursor Desktop 或 VS Code Desktop（仅扩展用户需要）

```bash
uv sync
pnpm install          # 仅扩展开发需要
uv sync --extra live  # 可选：Longbridge live provider
uv sync --extra mcp   # 可选：MCP server
```

Cursor Host 启动 Core 时不会自动附加 `--extra live`，因此 live extra 需提前安装。

## 2. Provider 选择

| Provider | 用途 | 说明 |
|---|---|---|
| `fake` | 首次体验、离线开发、UI 验证 | 默认，无外部网络 |
| `replay` | 固定行情复现、Event / Signal 调试、Evaluation、Tuning | 读取 JSONL fixture |
| `longbridge` | 可选 live 行情 | 需要 `uv sync --extra live` 和环境变量 |
| `http` | 预留 stub | 选择即抛错，提示可用 provider |

Tencent / Sina 仅用于 `tools/live_probe` 开发探针，不是正式 Core provider（见 [architecture/provider-source-audit.md](architecture/provider-source-audit.md)）。

Longbridge 环境变量（只走环境变量，不进任何配置文件）：

```text
LONGBRIDGE_APP_KEY
LONGBRIDGE_APP_SECRET
LONGBRIDGE_ACCESS_TOKEN
```

详细接入说明见 [integrations/longbridge.md](integrations/longbridge.md)。

## 3. Watchlist 与显示配置

Cursor 命令面板：

```text
Market Sentinel: Add Symbol / Remove Symbol / Manage Watchlist
```

Cursor Host 的 `marketSentinel.watchlist` 与 CLI 的 `data/watchlist.json` 是两个独立入口，不自动双向同步。Core 最多接受 10 个 symbol。

显示别名与模式：

```json
"marketSentinel.symbolNames": { "600519.SH": "贵州茅台" },
"marketSentinel.symbolDisplay": "name | nameAndCode | code"
```

## 4. 推荐 Replay 场景

仓库自带三股票场景（同时用于 `market-sentinel demo`）：

```text
tests/fixtures/multi_a_share_ui.jsonl    600519.SH / 000001.SZ / 300750.SZ
```

推荐 Cursor 配置：

```json
{
  "marketSentinel.provider": "replay",
  "marketSentinel.replayPath": "<repo-root>/tests/fixtures/multi_a_share_ui.jsonl",
  "marketSentinel.watchlist": ["600519.SH", "000001.SZ", "300750.SZ"],
  "marketSentinel.symbolDisplay": "nameAndCode",
  "marketSentinel.statusBarMaxSymbols": 3,
  "marketSentinel.intelligence": "off"
}
```

Replay 结束后保留最后行情 / Signal，不制造持续 missing-quote 故障（`replay_complete`）。

## 5. Intelligence 配置

默认关闭。优先级：

```text
显式 CLI --intelligence / --no-intelligence
> MARKET_SENTINEL_INTEL_ENABLED
> Core 默认关闭
```

Cursor：`marketSentinel.intelligence = inherit | on | off`（修改后需 `Market Sentinel: Restart Core`）。DashScope key 只从 `DASHSCOPE_API_KEY` 读取。Provider / 模型 / 超时等环境变量见 §8。契约细节见 [architecture/intelligence-contract.md](architecture/intelligence-contract.md)。

## 6. Cursor / VS Code Desktop 使用

- Extension ID：`market-sentinel-local.market-sentinel`（本地 developer VSIX，未发布 Marketplace）。
- StatusBar 为报价型 UI（codicon 表达状态），点击打开可滚动 Details Webview；Hover 为快速摘要。
- 常用命令：Add/Remove/Manage Symbol、Pause、Resume、Restart Core、Show Details、Show Output、Reset Alert Badge、Signal Feedback。
- `coreRoot` 指向 Python Core checkout；`uvPath` 默认 `uv`；凭据永远不进 settings。
- Python Core 不打包进 VSIX；扩展通过 `uv run --directory <coreRoot> market-sentinel daemon` 拉起 Core。

## 7. CLI 参考

```bash
# watchlist
uv run market-sentinel --watchlist data/watchlist.json watchlist add 600519.SH
uv run market-sentinel --watchlist data/watchlist.json watchlist list

# 单次 / 持续运行
uv run market-sentinel --watchlist data/watchlist.json run --once [--verbose]

# 宿主协议（stdout = Protocol v1 JSONL only，stderr = 日志）
uv run market-sentinel --provider fake daemon

# 离线演示 / 环境诊断 / MCP server
uv run market-sentinel demo
uv run market-sentinel doctor [--json]
uv run market-sentinel mcp          # 需要 [mcp] extra

# 遥测评估
uv run market-sentinel telemetry report [--data-dir <dir>] [--run-id <id>] [--format text]

# Offline tuning（snapshot / compare / report）
uv run market-sentinel tuning snapshot --config-version baseline-v0.6
uv run market-sentinel tuning compare --baseline <id> --candidate <id> --corpus default
```

daemon stdin 命令：`hello / start / pause / resume / set_watchlist / get_state / host_interaction / user_feedback / shutdown`（典型握手 `hello → set_watchlist → start`）。`set_watchlist` 只修改当前 runtime，不写回 CLI watchlist 文件。

## 8. 配置总表

### Cursor 设置

| Setting | 作用 |
|---|---|
| `marketSentinel.coreRoot` | Core checkout 路径 |
| `marketSentinel.uvPath` | uv 可执行文件（默认 `uv`） |
| `marketSentinel.watchlist` | Host watchlist（≤10） |
| `marketSentinel.provider` | `fake` / `replay` / `longbridge` |
| `marketSentinel.replayPath` | Replay JSONL |
| `marketSentinel.enableHoverDetails` | Hover 详情开关 |
| `marketSentinel.alertToast` | `off` / `critical` |
| `marketSentinel.intelligence` | `inherit` / `on` / `off` |
| `marketSentinel.symbolNames` / `symbolDisplay` | 本地显示别名 / 模式 |
| `marketSentinel.statusBarMaxSymbols` | 1–3，默认 2 |

### Core / 环境变量

| 变量 | 作用 |
|---|---|
| `MARKET_SENTINEL_DATA_DIR` | 覆盖 telemetry / feedback / tuning 数据目录 |
| `MARKET_SENTINEL_INTEL_ENABLED` | Intelligence 开关（1/true/yes） |
| `MARKET_SENTINEL_INTEL_PROVIDER` / `_MODEL` / `_BASE_URL` / `_TIMEOUT_S` / `_MAX_OUTPUT_TOKENS` / `_API_KEY_ENV` | Intelligence 细项（默认 dashscope / qwen3.7-max-2026-06-08 / compatible-mode / 8.0 / 150 / DASHSCOPE_API_KEY） |
| `DASHSCOPE_API_KEY` | DashScope API key |
| `LONGBRIDGE_APP_KEY` / `_APP_SECRET` / `_ACCESS_TOKEN` | Longbridge 凭据 |

## 9. 本地数据目录

```text
Windows: %LOCALAPPDATA%/MarketSentinel
Unix:    $XDG_DATA_HOME/market-sentinel 或 ~/.local/share/market-sentinel
布局：telemetry.jsonl(.N) / feedback.jsonl(.N) / tuning/<snapshot>.json
```

Telemetry / feedback 为 append-only（1MB×5 轮转，损坏行修复）；tuning snapshot immutable。存储与所有权契约见 [architecture/metrics-contract.md](architecture/metrics-contract.md)。

## 10. Alert、反馈与 Evaluation

`alert_candidate`（Core）与 `alert_presented`（Host）是两个不同事实；unread badge 由 Host 维护。显式反馈标签：`useful / not_useful / too_noisy / too_late`——反馈是主观评价，不修改 Event，也不自动改 threshold / cooldown / router。指标语义（`feedback_count`、`useful_rate`、`alerts_per_market_hour` 等，含 unavailable 哨兵）见 metrics contract；`useful_rate` 无反馈时是 unavailable 而非 0%。

## 11. Offline Tuning

7 个受证据支持的参数（`cluster_lookback_s`、`hot_event_severity`、`hot_volume_ratio_5m`、`hot_change_5m`、`warm_change_1m`、`warm_change_5m`、`warm_volume_ratio`）。流程：baseline snapshot → candidate JSON → compare（固定 corpus 的 before/after/delta）。Runtime 不扫描 tuning 目录；没有 `apply / promote / deploy`。cooldown / dwell / router 参数仍 deferred。

## 12. 数据语义

- `ACTIVE SIGNALS`：episode 生命周期内仍 active 的 Signal；`EVENTS THIS TICK` / `ALERTS THIS TICK` 是当前 tick 的新产出。Active Signal 存在不代表当前 tick 有新 Alert（cooldown 抑制重复提醒）。
- 时间戳三分：`market_timestamp`（行情本身）、`created/detected/received`（runtime 墙钟）、`run_id`（一次 runtime/Replay 执行）。不要混用。

## 13. 隐私边界

保存：低基数结构化数据（run/symbol/event/signal 关联 ID、固定反馈标签、延迟、token usage、聚合指标）。
默认不保存：workspace / 对话 / 源码；用户文件内容或绝对 fixture 路径；raw tick / feature payload；prompt / API key / 模型原始输出；Signal title/summary；自由文本反馈。

## 14. 本地测试与发布前检查

```bash
uv run pytest                 # 默认排除 live；726 passed 基线（M6 快照）
uv run ruff check .
uv run ruff format --check .
pnpm test && pnpm typecheck && pnpm lint && pnpm build
uv build                      # wheel + sdist；发布验证记录见 CHANGELOG
```

Coverage gate 85%（当前 91%）；perf regression 测试需在无 coverage 下单独运行（见 CONTRIBUTING）。live 测试分两类：Longbridge smoke（无凭据自动 skip）、Tencent gate（fail-closed，真联网）。

## 15. 工程 backlog（未排期，非承诺）

以下方向基于已知边界，不代表排期：

- 更完整的交易所日历与跨市场 session 语义（`alerts_per_market_hour` 目前仅 `.SH`/`.SZ`）；
- Host alert history、per-alert dismiss/mute、`signal_opened` / `alert_dismissed` / `signal_muted` producer（对应评估指标当前为 unavailable）；
- bounded async telemetry queue + 后台写、长时 daemon 下 ClusterMembershipTracker 内存边界、更真实的 replay monotonic clock；
- cooldown / dwell / scheduler timing / intelligence router 的 offline comparison harness 扩展（保持"比较候选"而非自动 promote）；
- 经验证的 live source 正式 wiring、VSIX 分发与 release automation。

继续保持的边界：观察 ≠ 交易、反馈 ≠ 市场事实、评估 ≠ 自动优化、候选配置 ≠ 生产配置、模型 ≠ 高频主链。
