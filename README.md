# Market Sentinel

> 面向开发者宿主的低延迟市场监控核心：把行情快照转化为 Features / Events / Signals，并通过 Cursor / VS Code Desktop、CLI、本地 Telemetry / Evaluation / Feedback 与 Offline Tuning 提供低打扰、可解释、可回放的市场观察能力。

| 项目 | 当前状态 |
|---|---|
| Package | `0.6.5` |
| Protocol | `1` |
| Tuning Artifact Schema | `2` |
| Tuning Comparison Schema | `2` |
| Python | `3.12+` |
| Watchlist | 最多 `10` 个 symbol |
| 默认 Provider | `fake` |
| 默认 Intelligence | 关闭 |
| 当前发布状态 | v0.6.5 已在 `master` 并推送到 GitHub；tag `v0.6.5`；VSIX 仅本地安装，未上 Marketplace |
| 远程仓库 | https://github.com/vagabond-zzz/MarketSentinel |

> Package、Protocol、Tuning Artifact Schema、Tuning Comparison Schema 是四套独立版本空间。Market Sentinel 是观察与提醒系统，不是自动交易系统；反馈不会改写市场事实，离线评估也不会自动修改生产参数。

## 目录

1. [项目简介](#1-项目简介)
2. [快速开始](#2-快速开始)
3. [完整使用](#3-完整使用)
4. [Cursor / VS Code Desktop 使用说明](#4-cursor--vs-code-desktop-使用说明)
5. [CLI 功能](#5-cli-功能)
6. [面向开发者：架构、模块、数据与开发说明](#6-面向开发者架构模块数据与开发说明)
7. [本地测试与发布前检查](#7-本地测试与发布前检查)
8. [未来可以增加的方向](#8-未来可以增加的方向)

---

# 1. 项目简介

Market Sentinel 适合希望用 Python + Cursor / VS Code Desktop 观察少量股票、研究行情事件与 Signal episode、复现固定 Replay、收集本地反馈并做离线 before / after 对比的个人开发者和研究型用户。

它的主链是确定性的：

```text
Market Provider
→ Normalization / Ring Buffer
→ Features
→ Events
→ Dedupe / Cluster / Signal
→ Cooldown / Alert Candidate
→ MarketState
→ CLI / Cursor Host / Telemetry
```

可选 Intelligence 只作为异步 sidecar：

```text
Rule Signal
→ deterministic router
→ optional Intelligence request
→ structured annotation
```

默认高频行情路径不会调用 LLM；模型失败只影响 Intelligence annotation，不影响 Rule Signal、Alert 或行情状态。当前 Intelligence 不读取 workspace、代码或对话作为默认输入，也不提供自动交易或买卖建议。

### 当前核心能力

- **Watchlist 监控**：最多 10 个 symbol，正式市场时段评估主要面向 A 股 `.SH` / `.SZ`。
- **行情特征**：1m / 5m / 15m 涨跌幅、1m / 5m volume ratio、EMA5 / EMA20、RSI14、VWAP、session high / low。
- **确定性事件**：`rapid_move`、`volume_spike`、`price_volume_expansion`、`day_high_breakout`、`day_low_breakdown`、`vwap_cross`。
- **Signal episode**：Dedupe、Cluster、Episode composition、Cooldown，区分“当前仍 active 的 Signal”和“当前 tick 新产生的 Alert”。
- **市场状态**：COLD / WARM / HOT，并由 WarmingPolicy / AdaptiveScheduler 调整调度行为。
- **Cursor / VS Code Host**：报价型 StatusBar、短 Hover、可滚动 Details Webview、Alert badge、Watchlist 命令、Pause / Resume / Restart。
- **Replay**：确定性回放；结束后保留最后行情 / Signal，不制造持续 missing-quote 故障。
- **Telemetry / Feedback / Evaluation**：本地 append-only JSONL，显式反馈与评估均不修改生产 MarketState。
- **Offline Tuning**：对人工提供的 candidate config 做固定 Replay corpus 的 before / after / delta 比较，不自动 apply / promote / deploy。

---

# 2. 快速开始

## 2.1 环境要求

- Python `3.12+`
- [`uv`](https://docs.astral.sh/uv/)
- Node.js `20+`
- `pnpm`
- Cursor Desktop 或 VS Code Desktop

项目建议始终通过 `uv run` 执行 Python 命令。

## 2.2 安装依赖

```bash
uv sync
pnpm install
```

如果要使用 Longbridge：

```bash
uv sync --extra live
```

Cursor Host 启动 Core 时不会自动附加 `--extra live`，因此 live extra 需要提前安装。

## 2.3 最小 CLI 体验

默认 Provider 是 `fake`：

```bash
uv run market-sentinel --watchlist data/watchlist.json watchlist add 600519.SH
uv run market-sentinel --watchlist data/watchlist.json watchlist list
uv run market-sentinel --watchlist data/watchlist.json run --once
```

查看详细输出：

```bash
uv run market-sentinel --watchlist data/watchlist.json run --once --verbose
```

## 2.4 构建并安装 Cursor / VS Code 扩展

```bash
pnpm build
pnpm package:vsix
```

生成：

```text
apps/cursor-extension/market-sentinel-0.6.5.vsix
```

在 Cursor / VS Code Desktop 中选择：

```text
Extensions
→ Install from VSIX…
→ market-sentinel-0.6.5.vsix
```

Python Core **不会打包进 VSIX**，使用扩展时仍需要本地 Core checkout 和 `uv`。

---

# 3. 完整使用

## 3.1 选择 Provider

| Provider | 用途 | 说明 |
|---|---|---|
| `fake` | 第一次安装、离线开发、UI 验证 | 默认，不需要外部网络 |
| `replay` | 固定行情复现、Event / Signal 调试、Evaluation、Tuning | 读取 JSONL fixture |
| `longbridge` | 可选 live Core 接入 | 需要 `uv sync --extra live` 和环境变量 |
| `http` | 预留 | 当前仍为未实现 stub |

Tencent / Sina 当前用于 live probe / cross-check，不是正式 Core `MarketProvider` wiring。

### Longbridge 环境变量

```text
LONGBRIDGE_APP_KEY
LONGBRIDGE_APP_SECRET
LONGBRIDGE_ACCESS_TOKEN
```

不要把这些凭据写进 Cursor `settings.json`。

## 3.2 配置 Watchlist 与显示名

Cursor 可以通过 Command Palette 管理：

```text
Market Sentinel: Add Symbol
Market Sentinel: Remove Symbol
Market Sentinel: Manage Watchlist
```

也可以使用：

```text
marketSentinel.watchlist
```

Cursor Host 的 Watchlist 和 CLI 的 `data/watchlist.json` 是两个独立入口，不自动双向同步。Core 最多接受 10 个 symbol。

中文名采用本地 UI alias，不改变 provider / Signal / Telemetry identity：

```json
"marketSentinel.symbolNames": {
  "600519.SH": "贵州茅台",
  "000001.SZ": "平安银行",
  "300750.SZ": "宁德时代"
}
```

显示模式：

```text
marketSentinel.symbolDisplay = name | nameAndCode | code
```

## 3.3 推荐的三股票 Replay

仓库提供：

```text
tests/fixtures/multi_a_share_ui.jsonl
```

用于同时观察：

```text
600519.SH  贵州茅台
000001.SZ  平安银行
300750.SZ  宁德时代
```

推荐 Cursor 配置：

```json
{
  "marketSentinel.provider": "replay",
  "marketSentinel.replayPath": "D:\\path\\to\\Market_Sentinel\\tests\\fixtures\\multi_a_share_ui.jsonl",
  "marketSentinel.watchlist": [
    "600519.SH",
    "000001.SZ",
    "300750.SZ"
  ],
  "marketSentinel.symbolNames": {
    "600519.SH": "贵州茅台",
    "000001.SZ": "平安银行",
    "300750.SZ": "宁德时代"
  },
  "marketSentinel.symbolDisplay": "nameAndCode",
  "marketSentinel.statusBarMaxSymbols": 3,
  "marketSentinel.intelligence": "off"
}
```

`tests/fixtures/*.jsonl` 中用于 Replay / tuning 的示例数据统一使用 A 股 `.SH` / `.SZ` symbol。

## 3.4 Intelligence

默认关闭。优先级：

```text
显式 CLI --intelligence / --no-intelligence
> MARKET_SENTINEL_INTEL_ENABLED
> Core 默认关闭
```

Cursor：

```text
marketSentinel.intelligence = inherit | on | off
```

- `inherit`（默认）：Host 不传 flag，沿用环境变量 / Core 默认。
- `on`：Host 传 `--intelligence`。
- `off`：Host 传 `--no-intelligence`。

DashScope Key 只从环境变量读取：

```text
DASHSCOPE_API_KEY
```

修改 Cursor Intelligence 设置后需要 `Market Sentinel: Restart Core`。Hover / Details 不会主动触发模型调用。

## 3.5 Alert、反馈与 Evaluation

Core 的 `alert_candidate` 与 Host 真正呈现后的 `alert_presented` 是两个不同事实。Host 收到新的 unsolicited alert edge 后才增加 unread badge。

可用命令包括：

```text
Market Sentinel: Reset Alert Badge
Market Sentinel: Signal Feedback
```

显式反馈标签：

```text
useful
not_useful
too_noisy
too_late
```

Feedback 只表示用户对 Signal 的主观评价，不修改 Event，也不会自动改 threshold、cooldown 或 RouterPolicy。

查看本地 Evaluation：

```bash
uv run market-sentinel telemetry report
uv run market-sentinel telemetry report --data-dir <dir>
uv run market-sentinel telemetry report --data-dir <dir> --run-id <id> --format text
```

`feedback_count`、`useful_rate`、`feedback_coverage`、`alerts_per_market_hour` 等指标遵循 `docs/16_v0.6_Metrics_Contract.md`；没有 feedback 时 `useful_rate` 是 unavailable，不应解释为 0%。

## 3.6 Offline Tuning

创建 baseline：

```bash
uv run market-sentinel tuning snapshot --config-version baseline-v0.6
```

准备 candidate JSON，例如：

```json
{
  "cluster_lookback_s": 60.0,
  "hot_event_severity": 3,
  "hot_volume_ratio_5m": 2.0,
  "hot_change_5m": 0.012,
  "warm_change_1m": 0.004,
  "warm_change_5m": 0.008,
  "warm_volume_ratio": 1.5
}
```

创建 candidate：

```bash
uv run market-sentinel tuning snapshot \
  --config-version candidate-001 \
  --config candidate.json \
  --source manual
```

比较：

```bash
uv run market-sentinel tuning compare \
  --baseline <snapshot_id> \
  --candidate <snapshot_id> \
  --corpus default
```

当前支持 7 个 evidence-backed 参数：

| 参数 | 作用 |
|---|---|
| `cluster_lookback_s` | Signal episode cluster look-back |
| `hot_event_severity` | HOT event severity threshold |
| `hot_volume_ratio_5m` | HOT 5m volume ratio threshold |
| `hot_change_5m` | HOT 5m change threshold |
| `warm_change_1m` | WARM 1m change threshold |
| `warm_change_5m` | WARM 5m change threshold |
| `warm_volume_ratio` | WARM volume ratio threshold |

Runtime 不扫描 `<data-dir>/tuning/`，CLI 也没有 `apply` / `promote` / `activate` / `deploy`。

## 3.7 配置总表

### Cursor 设置

| Setting | 作用 |
|---|---|
| `marketSentinel.coreRoot` | Python Core checkout 路径 |
| `marketSentinel.uvPath` | `uv` 可执行文件，默认 `uv` |
| `marketSentinel.watchlist` | Host Watchlist，最多 10 个 |
| `marketSentinel.provider` | `fake` / `replay` / `longbridge` |
| `marketSentinel.replayPath` | Replay JSONL 文件 |
| `marketSentinel.enableHoverDetails` | 控制 StatusBar Hover 详情显示 |
| `marketSentinel.alertToast` | `off` / `critical`，默认 `off` |
| `marketSentinel.intelligence` | `inherit` / `on` / `off`，默认 `inherit` |
| `marketSentinel.symbolNames` | 本地 UI alias |
| `marketSentinel.symbolDisplay` | `name` / `nameAndCode` / `code` |
| `marketSentinel.statusBarMaxSymbols` | StatusBar 最多显示 1–3 只，默认 2 |

### Core / 环境变量

| 变量 | 作用 |
|---|---|
| `MARKET_SENTINEL_DATA_DIR` | 覆盖 telemetry / feedback / tuning 本地数据目录 |
| `MARKET_SENTINEL_INTEL_ENABLED` | Intelligence 环境开关 |
| `DASHSCOPE_API_KEY` | DashScope API Key |
| `LONGBRIDGE_APP_KEY` | Longbridge App Key |
| `LONGBRIDGE_APP_SECRET` | Longbridge App Secret |
| `LONGBRIDGE_ACCESS_TOKEN` | Longbridge Access Token |

## 3.8 本地数据目录

默认：

```text
Windows: %LOCALAPPDATA%/MarketSentinel
Unix:    $XDG_DATA_HOME/market-sentinel
         或 ~/.local/share/market-sentinel
```

布局：

```text
MarketSentinel/
├ telemetry.jsonl
├ telemetry.jsonl.1
├ feedback.jsonl
├ feedback.jsonl.1
└ tuning/
   └ <snapshot_uuid>.json
```

Telemetry / Feedback 是 append-only；tuning snapshot 是 immutable。Host 不直接写这些文件，Core / local CLI 拥有本地 storage。

## 3.9 关键文档

| 文档 | 建议阅读场景 |
|---|---|
| `CHANGELOG.md` | 查看各版本完成了什么 |
| `docs/08_Roadmap_v0.6_Feedback_and_Tuning.md` | 理解 v0.6 telemetry / feedback / tuning 路线与边界 |
| `docs/12_v0.4_Longbridge_Provider_Setup.md` | 配置 Longbridge |
| `docs/16_v0.6_Metrics_Contract.md` | 修改 telemetry、feedback、evaluation、market-time 统计前必读 |
| `docs/17_v0.6_Release_Candidate.md` | v0.6.0 历史 Release Candidate |
| `docs/18_v0.6.5_UX_Polish.md` | v0.6.5 Host / CLI UX 实现记录 |
| `docs/19_v0.6.5_Release_Candidate.md` | v0.6.5 发布准备、tests、VSIX、privacy / mutation audit |

## 3.10 已知边界

当前版本仍有这些明确限制：

- Watchlist 最多 10 个 symbol。
- Cursor Host 与 CLI Watchlist 不同步。
- Python Core 不打包进 VSIX。
- Desktop Cursor / VS Code 为主要支持形态；Web / browser Cursor 不支持。
- `MarketSnapshot.volume / turnover` 是 session cumulative；Longbridge `turnover` 仍可能为 `None`。
- Adaptive polling 产生的是 sampled / observed 1-minute bar，不等于交易所官方 1 分钟 K 线。
- `alerts_per_market_hour` 当前只对 `.SH` / `.SZ` 定义，尚未接入完整交易所节假日日历。
- Host 仍没有完整 Alert history，unread badge 是 Host-local。
- `signal_opened` / `alert_dismissed` / `signal_muted` producer 尚未实现，因此对应 rate 是 unavailable。
- Telemetry JSONL 当前同步写入；长时间 daemon 下 ClusterMembershipTracker 理论上会增长。
- Offline Tuning 只有 7 个受证据支持的参数，cooldown、dwell、Router、Event threshold 等仍 deferred。
- Intelligence 默认关闭，不包含 News、MCP、auto-trading、buy/sell advice 或默认 live model test。

---

# 4. Cursor / VS Code Desktop 使用说明

## 4.1 Extension 信息

```text
Extension ID: market-sentinel-local.market-sentinel
Publisher:    market-sentinel-local
```

这是本地 / developer VSIX 标识，不是 Marketplace publisher。

## 4.2 日常 UI

StatusBar 以报价为主，例如：

```text
$(circle-outline) 贵州茅台 1412.30 +1.28% | 平安银行 12.34 -0.55%
```

不再把 `MS NORMAL` / `MS STALE` 作为主要文字，也不用整条红黄背景提示状态。Feed 异常、暂停、Alert、Replay 完成等状态通过 Codicon 表达。

### Hover

Hover 是快速摘要，适合扫一眼：

- 连接 / 行情源 / AI；
- 未读提醒；
- 最后行情时间（UTC+8）；
- 价格、当日涨跌幅、COLD / WARM / HOT。

### 可滚动 Details Webview

直接点击 Market Sentinel StatusBar，或运行：

```text
Market Sentinel: Show Details
```

会在编辑器区域打开：

```text
Market Sentinel · 行情详情
```

该面板持久、可滚动，并展示每只股票的完整快照、Rule Signal、AI 增强、涨跌幅、成交、技术指标、VWAP 和日内区间。Core 更新时面板会刷新，并尽量保持当前滚动位置。

日志仍通过：

```text
Market Sentinel: Show Output
```

单独查看。

## 4.3 Command Palette

常用命令：

```text
Market Sentinel: Add Symbol
Market Sentinel: Remove Symbol
Market Sentinel: Manage Watchlist
Market Sentinel: Pause
Market Sentinel: Resume
Market Sentinel: Restart Core
Market Sentinel: Show Details
Market Sentinel: Show Output
Market Sentinel: Reset Alert Badge
Market Sentinel: Signal Feedback
```

## 4.4 推荐验收流程

1. 安装最新 VSIX，打开 Trusted Workspace。
2. 必要时配置 `coreRoot`、确认 `uvPath`。
3. 先选 `replay`，用 `multi_a_share_ui.jsonl` 看 2–3 只股票。
4. 确认 StatusBar 是报价型 UI；Hover 足够短；点击 StatusBar 能打开可滚动详情。
5. 用 Add / Remove / Manage Watchlist 实际操作一次。
6. 验证 Pause / Resume / Restart Core / Show Output。
7. Replay 播放结束后确认不持续刷 missing quote，最后行情仍保留。
8. 需要 Intelligence 时再设为 `on`，确认 Cursor 进程能继承 `DASHSCOPE_API_KEY`。
9. 关闭 Cursor 后确认没有残留 `market-sentinel daemon` / Python child。

---

# 5. CLI 功能

## 5.1 Watchlist

```bash
uv run market-sentinel --watchlist data/watchlist.json watchlist add 600519.SH
uv run market-sentinel --watchlist data/watchlist.json watchlist list
```

## 5.2 单次运行

```bash
uv run market-sentinel --watchlist data/watchlist.json run --once
uv run market-sentinel --watchlist data/watchlist.json --intelligence run --once
uv run market-sentinel --watchlist data/watchlist.json --no-intelligence run --once
uv run market-sentinel --watchlist data/watchlist.json run --once --verbose
```

`--intelligence` / `--no-intelligence` 是全局 CLI flag，应放在子命令 `run` / `daemon` 前。

## 5.3 Daemon / Host Protocol

```bash
uv run market-sentinel --provider fake daemon
```

约束：

```text
stdout = Protocol v1 JSONL only
stderr = logs
```

stdin command：

```text
hello
start
pause
resume
set_watchlist
get_state
host_interaction
user_feedback
shutdown
```

典型握手：

```text
hello
→ set_watchlist
→ start
```

`set_watchlist` 只修改当前 runtime，不写回 CLI 的 `data/watchlist.json`。

## 5.4 Telemetry / Evaluation

```bash
uv run market-sentinel telemetry report
uv run market-sentinel telemetry report --data-dir <dir>
uv run market-sentinel telemetry report --data-dir <dir> --run-id <id> --format text
```

## 5.5 Offline Tuning

```bash
uv run market-sentinel tuning snapshot --config-version baseline-v0.6

uv run market-sentinel tuning snapshot \
  --config-version candidate-001 \
  --config candidate.json \
  --source manual

uv run market-sentinel tuning compare \
  --baseline <snapshot_id> \
  --candidate <snapshot_id> \
  --corpus default
```

---

# 6. 面向开发者：架构、模块、数据与开发说明

## 6.1 架构

```text
Market Provider
    │
    ▼
Normalization → Ring Buffer → Feature Engine
    │
    ▼
Event Rules → Dedupe → Cluster / Signal Composer → Cooldown
    │
    ├────────────► optional Intelligence Sidecar
    ▼
MarketState / EngineTickResult
    │
    ├────────────► CLI
    ├────────────► Protocol v1 JSONL → Cursor Host
    └────────────► Telemetry → local JSONL → Evaluation / Tuning evidence
```

设计原则：

```text
Event = observed market fact
Feedback = user's subjective evaluation of a Signal
Measurement != mutation
Offline evidence != automatic tuning
Model != high-frequency main path
```

## 6.2 主要模块

| 模块 | 职责 |
|---|---|
| `market_data` | Provider 接口、Fake / Replay、Longbridge optional adapter、session、normalization |
| `features` | change、EMA、RSI、VWAP、volume ratio 等 |
| `events` | 确定性市场事件规则 |
| `signals` | Dedupe、Cluster、Episode composition、Cooldown、Alert candidate |
| `scheduler` | WarmingPolicy、AdaptiveScheduler、COLD / WARM / HOT |
| `runtime` | 串联 provider → feature → event → signal → scheduler，生成 MarketState |
| `ipc` | Protocol v1、daemon JSONL、mapping、Host command、lifecycle |
| `intelligence` | deterministic router、episode budget、async sidecar、structured annotation |
| `telemetry` | TelemetryEvent、UserFeedback、collector、JSONL、rotation / corruption handling |
| `evaluation` | funnel / noise / host / intelligence / market-time / feedback 指标 |
| `tuning` | immutable snapshot、eligibility dataset、Replay comparison、delta report |
| `cli` | watchlist、run、daemon、telemetry、tuning |
| `apps/cursor-extension` | Core process、Protocol、StatusBar、Hover、Details、Alert、Feedback、VSIX |

## 6.3 数据语义

### ACTIVE SIGNALS / EVENTS THIS TICK / ALERTS THIS TICK

- `ACTIVE SIGNALS`：来自 MarketState，表示当前仍在 episode 生命周期内的 Signal。
- `EVENTS THIS TICK`：当前 tick 新接受的 Event。
- `ALERTS THIS TICK`：当前 tick 新满足提醒资格的 Alert candidate。

因此 Active Signal 存在，不代表当前 tick 一定有新 Alert；Cooldown 可以让 Signal 持续，但不重复提醒。

### Timestamp

- `created_timestamp`：观测 / runtime wall-clock。
- `market_timestamp`：行情本身的市场时间。
- `run_id`：一次 Core runtime / Replay execution 的关联 ID。

不要把三者混用。

## 6.4 Telemetry / Feedback / Privacy

允许保存的是低基数结构化数据，例如 run / symbol / event / signal correlation ID、固定 feedback label、latency、实际 token usage、聚合指标。

默认不保存：

- workspace / conversation / source code；
- 用户文件内容或绝对 fixture path；
- raw tick / feature payload；
- prompt / API key / model raw output；
- Signal title / summary；
- free-text feedback / tuning notes。

## 6.5 开发约束

- `stdout` 必须保持纯 Protocol JSONL，日志走 `stderr`。
- Telemetry / Feedback 失败必须 fail-open，不能拖垮 market pipeline。
- Runtime 不自动读取 tuning snapshot。
- 不要把 user feedback 回写为 Event 事实。
- 不要把 Intelligence 变成 tick-by-tick 主链。
- 新的 Protocol 字段优先保持 additive optional，除非明确计划升级 Protocol。
- 修改 telemetry / evaluation / feedback / market-time 语义前先阅读 `docs/16_v0.6_Metrics_Contract.md`。

---

# 7. 本地测试与发布前检查

## 7.1 Python

完整离线测试：

```bash
uv run pytest
```

Coverage：

```bash
uv run pytest \
  --cov=market_sentinel \
  --deselect tests/integration/test_engine_perf.py::test_ten_symbol_engine_replay_stays_within_regression_budget
```

Coverage gate：

```text
85%
```

Timing regression 必须在无 coverage instrumentation 下运行：

```bash
uv run pytest tests/integration/test_engine_perf.py::test_ten_symbol_engine_replay_stays_within_regression_budget -s
```

Ruff：

```bash
uv run ruff check .
uv run ruff format --check .
```

默认 pytest 不跑 live market / live model gate。

## 7.2 TypeScript / Extension

```bash
pnpm test
pnpm typecheck
pnpm lint
pnpm build
pnpm test:extension-host
```

`test:extension-host` 使用 `@vscode/test-electron` 的 VS Code Desktop binary，不等于真实 Cursor Desktop；最终 UI 仍需人工验收。

## 7.3 VSIX

```bash
pnpm package:vsix
```

当前包：

```text
apps/cursor-extension/market-sentinel-0.6.5.vsix
```

发布前至少确认：

- Package `0.6.5`、Protocol `1`；
- Python Core 未被打进 VSIX；
- 无 `node_modules` 污染；
- 无 telemetry / feedback / tuning 数据；
- 无 `.env` / API key；
- 无 review archive / patch；
- commands / settings contributions 完整；
- StatusBar、Hover、Details Webview、Watchlist 命令在真实 Cursor Desktop 中可用。

精确测试数量、Coverage、Timing、VSIX file count / size 和最终 release audit 以 `docs/19_v0.6.5_Release_Candidate.md` 为准，避免 README 因每次测试新增而频繁过期。

## 7.4 推荐发布前顺序

```text
Python full tests
→ Coverage
→ Timing
→ Ruff
→ TS tests / typecheck / lint / build
→ extension-host smoke
→ VSIX package + audit
→ Cursor Desktop manual smoke
→ git diff --check
→ external final verification
```

v0.6.5 已在 `master` 发布并打 tag。VSIX 仍是本地 / developer 安装，不要发布到 Marketplace；不要开始 v1.0。

---

# 8. 未来可以增加的方向

以下方向基于当前局限，不代表已经排期或承诺实现。

### 更完整的交易所与 Market Session

- 官方节假日日历、特殊交易日；
- HK 独立 market-hour 语义；
- 更明确的跨市场 session abstraction。

### 更完整的 Cursor / Host 体验

- Alert history；
- per-alert dismiss / mute；
- `signal_opened` / `alert_dismissed` / `signal_muted` producer；
- 更丰富的 Details Webview，例如历史列表、趋势图和更稳定的交互状态；
- 更长期的 Host interaction metrics。

### 更完善的数据与性能层

- bounded async telemetry queue + background writer；
- 长时间 daemon 下 ClusterMembershipTracker 的内存边界设计；
- 更真实的 Replay monotonic clock；
- 更丰富的 Replay corpus 与场景生成器。

### 更完整的 Offline Evaluation / Tuning

- cooldown / dwell / Scheduler timing 的 Replay 评估；
- Intelligence router threshold / episode call budget 的离线 comparison harness；
- Event threshold / TTL 的可注入 candidate config；
- 更完善的 sensitivity evidence；
- 继续保持“比较候选”而不是“自动 promote production config”。

### Live Provider 与分发

- 将经过验证的 live source 正式 wiring 到 `MarketProvider`；
- 更易安装的 Python Core；
- VSIX 正式分发、Marketplace / 内部 registry；
- 在现有 GitHub remote 上补充 release automation。

---

## 一句话总结

Market Sentinel 是一套面向开发者的小规模市场观察系统：用确定性 Features / Events / Signals 做低打扰提醒，用 Cursor / VS Code Desktop 提供日常 UI，用本地 Telemetry / Feedback / Evaluation 形成可解释证据，再通过 Offline Tuning 比较候选配置。

它最重要的边界始终是：

```text
观察 ≠ 交易
反馈 ≠ 市场事实
评估 ≠ 自动优化
候选配置 ≠ 生产配置
模型 ≠ 高频主链
```
