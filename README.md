# Market Sentinel

> 面向开发者宿主的低延迟市场监控核心：把行情快照转化为 Features / Events / Signals，并通过 Cursor / VS Code Desktop、CLI 和本地评估工具提供低打扰的市场状态、提醒、反馈与离线调优能力。

## 项目概览

| 项目 | 当前状态 |
|---|---|
| 包版本 | `0.6.0` |
| Protocol | `1` |
| Tuning Artifact Schema | `2` |
| Tuning Comparison Schema | `2` |
| Python | `3.12+` |
| Watchlist 上限 | `10` 个 symbol |
| 默认 Provider | `fake` |
| 默认 Intelligence | 关闭 |
| 当前发布状态 | 本地 release-ready；尚未创建 `v0.6.0` tag，也未推送远端 |

> `0.6.0`、Protocol `1`、Tuning Artifact Schema `2`、Tuning Comparison Schema `2` 是四套独立版本空间，不要把它们混为同一个版本号。

Market Sentinel 的目标不是做交易终端，也不是自动交易系统。它负责持续观察少量关注标的，把报价加工成结构化特征、事件和信号，并尽量把提醒保持在“少而有用”的范围内。

默认高频行情路径不调用 LLM。只有显式启用 Intelligence sidecar 时，系统才会在独立异步路径上做结构化智能增强；Event / Signal / Alert 的确定性主链不依赖模型。

---

## 目录

- [1. 适合谁](#1-适合谁)
- [2. 你可以用它做什么](#2-你可以用它做什么)
- [3. 快速开始](#3-快速开始)
- [4. 面向使用者的完整使用流程](#4-面向使用者的完整使用流程)
- [5. Cursor / VS Code Desktop 使用说明](#5-cursor--vs-code-desktop-使用说明)
- [6. CLI 使用说明](#6-cli-使用说明)
- [7. 本地数据、评估与反馈](#7-本地数据评估与反馈)
- [8. Offline Tuning 使用说明](#8-offline-tuning-使用说明)
- [9. 系统架构](#9-系统架构)
- [10. 核心模块说明](#10-核心模块说明)
- [11. 功能与数据语义](#11-功能与数据语义)
- [12. 配置说明](#12-配置说明)
- [13. 关键文档](#13-关键文档)
- [14. 开发、测试与打包](#14-开发测试与打包)
- [15. 隐私与安全边界](#15-隐私与安全边界)
- [16. 已知局限](#16-已知局限)
- [17. 未来可能增加的方向](#17-未来可能增加的方向)
- [18. 当前发布边界](#18-当前发布边界)

---

# 1. 适合谁

Market Sentinel 当前最适合以下用户：

### 个人开发者 / 研究型用户

希望：

- 用 Python 观察少量股票；
- 研究行情事件、信号聚合和提醒节流；
- 用 Replay 做确定性回放；
- 在 Cursor / VS Code Desktop 内查看市场状态；
- 对提醒进行显式反馈；
- 对候选参数做离线 before / after 对比。

### 想构建“低打扰市场助手”的开发者

Market Sentinel 更偏向：

```text
行情观察
→ 结构化特征
→ 事件
→ 信号
→ 少量提醒
→ 用户反馈
→ 离线评估
```

而不是：

```text
行情
→ LLM
→ 自动交易
```

### 不适合的用途

当前版本不适合：

- 自动下单；
- 高频交易执行；
- 大规模全市场扫描；
- 浏览器版 Cursor；
- 依赖完整交易所官方日历的精确交易时段统计；
- 把 Offline Tuning 当作自动参数优化器；
- 让 LLM 自动修改生产规则。

---

# 2. 你可以用它做什么

## 2.1 小规模 Watchlist 监控

最多监控 **10 个 symbol**。

当前正式市场时段评估主要面向 A 股 `.SH` / `.SZ`。Core / Fake / Replay 仍可处理历史测试中的 `.HK` symbol，但 `.HK` 不会被错误套用 A 股的 `alerts_per_market_hour` 统计窗口。

## 2.2 行情特征计算

当前核心特征包括：

- 1 分钟 / 5 分钟 / 15 分钟涨跌幅；
- 1 分钟 / 5 分钟 session volume ratio；
- EMA5 / EMA20；
- RSI14；
- VWAP；
- 是否位于 VWAP 上方 / 下方；
- session high / session low。

其中涨跌幅使用小数：

```text
0.006 = 0.6%
```

## 2.3 市场事件识别

当前事件规则包括：

1. `rapid_move`
2. `volume_spike`
3. `price_volume_expansion`
4. `day_high_breakout`
5. `day_low_breakdown`
6. `vwap_cross`

Event 是“客观观察到的市场事实”。

用户后续觉得某个提醒“没用”或“太吵”，不会反向修改 Event 历史。

## 2.4 Signal episode 与提醒节流

系统会对事件进行：

```text
Dedupe
→ Cluster
→ Episode composition
→ Cooldown
→ Alert candidate
```

因此：

- 一个 Signal 可以持续存在；
- 但并不意味着每个 tick 都产生新提醒；
- cooldown 可以阻止重复提醒；
- `ACTIVE SIGNALS` 和 `ALERTS THIS TICK` 是两个不同概念。

## 2.5 自适应市场状态

系统使用：

```text
COLD
WARM
HOT
```

等状态表达当前市场关注程度，并通过 `WarmingPolicy / AdaptiveScheduler` 调整调度行为。

Cursor Host 会进一步呈现：

```text
DISCONNECTED
STARTING
PAUSED
IDLE
NORMAL
WARM
HOT
STALE
ALERT
```

## 2.6 可选 Intelligence Sidecar

Intelligence 默认关闭。

启用后，它作为异步 sidecar：

```text
Rule Signal
→ deterministic router
→ optional Intelligence request
→ structured annotation
```

核心原则：

- 高频行情主链不 await LLM；
- Rule Signal 始终是事实源；
- 模型失败不能丢掉 Rule Signal / Alert；
- Host hover / click 不会触发模型；
- 默认不收集 workspace、代码、会话、raw ticks；
- 不输出买卖建议；
- 默认 sidecar timeout 为 8 秒；
- DashScope 请求关闭模型 thinking：`enable_thinking: false`。

## 2.7 本地 Telemetry 与 Evaluation

v0.6 新增：

```text
Market observation
→ TelemetryEvent
→ local JSONL
→ EvaluationReport
```

可以回答：

- 产生了多少 Event；
- 有多少被 dedupe；
- 产生了多少 Signal episode；
- 有多少 alert candidate；
- 有多少 alert 被 suppression；
- 有多少真正到达 Host；
- Intelligence route / skip / fallback 情况；
- 每个 run / market date 的指标；
- A 股观察时间范围内的 alerts per market hour；
- repeated episode alert 情况。

## 2.8 可选显式反馈

用户可以对 Signal 显式提交：

```text
useful
not_useful
too_noisy
too_late
```

Cursor UI 中显示为：

```text
有用
没用
太吵
太晚
```

反馈是：

```text
用户对某个 Signal 的主观评价
```

不是：

```text
对 Event 客观事实的修改
```

也不会自动调整 threshold、cooldown 或 RouterPolicy。

## 2.9 Offline Tuning

v0.6 支持“候选配置的离线证据比较”，不是自动调参。

流程：

```text
当前 production defaults
→ baseline snapshot

人工提供 candidate config
→ candidate snapshot

baseline + candidate
→ 固定 Replay corpus
→ before / after / delta report
```

当前支持的 7 个参数：

- `cluster_lookback_s`
- `hot_event_severity`
- `hot_volume_ratio_5m`
- `hot_change_5m`
- `warm_change_1m`
- `warm_change_5m`
- `warm_volume_ratio`

只有满足下面三个条件的参数才算 supported：

```text
Consumed
+ Observable
+ Sensitivity proof
```

系统没有：

```text
apply
promote
activate
deploy
```

也不会自动加载 tuning snapshot。

---

# 3. 快速开始

## 3.1 环境要求

### Core

- Python `3.12+`
- [`uv`](https://docs.astral.sh/uv/)

### Cursor Host

- Node.js `20+`
- `pnpm`
- Cursor Desktop 或 VS Code Desktop

> 某些系统默认 `python` 仍是 3.11。项目建议始终通过 `uv run` 执行 Python 命令。

## 3.2 安装依赖

```bash
uv sync
pnpm install
```

如果要使用 Longbridge：

```bash
uv sync --extra live
```

Cursor Host 启动 Core 时不会自动附加 `--extra live`，因此 live extra 必须提前手动安装。

## 3.3 最小 CLI 体验

默认 Provider 是 `fake`。

```bash
uv run market-sentinel --watchlist data/watchlist.json watchlist add 600519.SH
uv run market-sentinel --watchlist data/watchlist.json watchlist list
uv run market-sentinel --watchlist data/watchlist.json run --once
```

查看更详细输出：

```bash
uv run market-sentinel --watchlist data/watchlist.json run --once --verbose
```

## 3.4 构建 Cursor VSIX

```bash
pnpm build
pnpm package:vsix
```

生成：

```text
apps/cursor-extension/market-sentinel-0.6.0.vsix
```

在 Cursor Desktop 中：

```text
Extensions
→ Install from VSIX…
→ 选择 market-sentinel-0.6.0.vsix
```

---

# 4. 面向使用者的完整使用流程

推荐把 Market Sentinel 当成一个“持续观察、偶尔提醒”的辅助工具，而不是一直盯着输出窗口。

## 第一步：选择 Provider

### Fake

适合：

- 第一次安装；
- UI 验证；
- 离线开发；
- 不需要网络。

```text
marketSentinel.provider = fake
```

### Replay

适合：

- 复现固定行情；
- 调试 Event / Signal；
- Evaluation；
- Offline Tuning。

```text
marketSentinel.provider = replay
marketSentinel.replayPath = <fixture.jsonl>
```

### Longbridge

适合可选 live Core 接入。

需要：

```bash
uv sync --extra live
```

并在 Cursor 启动进程可以继承到的环境中设置：

```text
LONGBRIDGE_APP_KEY
LONGBRIDGE_APP_SECRET
LONGBRIDGE_ACCESS_TOKEN
```

不要把这些凭据写入 `settings.json`。

## 第二步：配置 Watchlist

Command Palette：

```text
Market Sentinel: Add Symbol
Market Sentinel: Remove Symbol
Market Sentinel: Manage Watchlist
```

也可以继续用 Cursor 设置：

```text
marketSentinel.watchlist
```

Host 写入 Workspace 设置。CLI 的 `data/watchlist.json` 是另一套入口，两者不自动双向同步。

Core 最多接受：

```text
10 symbols
```

正式 Longbridge live 使用建议使用 `.SH` / `.SZ`。

显示名（仅 UI）：

```json
"marketSentinel.symbolNames": {
  "600519.SH": "贵州茅台"
}
```

真正 ID 永远是 `600519.SH`。

## 第三步：启动 Cursor Host

打开一个 **Trusted Workspace**。

如果当前窗口不是单目录的 Market Sentinel checkout，需要设置：

```text
marketSentinel.coreRoot
```

确认：

```text
marketSentinel.uvPath
```

默认是：

```text
uv
```

重新加载窗口后，StatusBar 会出现类似：

```text
$(circle-outline) 贵州茅台 1412.30 +1.28% | 平安银行 12.34 -0.55%
```

而不是诊断字 `MS NORMAL`。未配置别名时显示代码。Feed 异常用 icon，不用红/黄背景。

## 第四步：观察状态

常见状态（icon，不是整条变色）：

| 状态 | 含义 |
|---|---|
| 启动中 | Core 正在启动 |
| 已断开 / error icon | Core 未连接 |
| pause icon | 用户暂停；保留最后行情 |
| 无标的 | Watchlist 为空 |
| quotes + warning/error icon | 已配置 symbol，但 feed 过旧 / 断连 |
| bell + quotes · N | 有未读 alert |
| clock + quotes | DELAYED |
| check Replay 已结束 | Replay 播完，不是 live 故障 |

## 第五步：Hover 查看详情

StatusBar Hover 即使没有 Event / Signal 也显示行情快照。

你通常可以看到：

- 连接 / 行情源 / AI 状态 / 未读提醒 / 最后更新；
- 每只股票的价格、当日涨跌幅、COLD/WARM/HOT；
- 规则信号与 AI 增强分开标注；
- 1m / 5m / 15m 涨跌幅与量比各占一行。

当日涨跌幅来自 `prev_close`（wire `change_day`）。不要把 1m/5m 当成当日涨跌。缺字段显示 `--`。

Hover 本身不会触发 Intelligence 调用，也不会自动生成 feedback。

## 第六步：处理 Alert

Host 只有在收到新的 unsolicited `alert` edge 时才增加 unread badge。

需要时可以：

- Show Output；
- Reset Alert Badge；
- Pause；
- Resume；
- Restart Core。

可选：

```text
marketSentinel.alertToast = critical
```

只为 critical alert 使用 toast。

默认：

```text
off
```

## 第七步：提交显式反馈

Command Palette：

```text
Market Sentinel: Signal Feedback
```

流程：

```text
选择 Signal
→ 选择：
   有用
   没用
   太吵
   太晚
```

Feedback 是显式动作。

以下行为都不会自动变成 feedback：

- hover；
- badge reset；
- alert presented；
- signal 没打开；
- Cursor 窗口关闭；
- Intelligence enriched。

## 第八步：查看本地 Evaluation

```bash
uv run market-sentinel telemetry report
```

按数据目录：

```bash
uv run market-sentinel telemetry report --data-dir <dir>
```

只看一个 run：

```bash
uv run market-sentinel telemetry report --data-dir <dir> --run-id <id> --format text
```

默认输出 JSON，对应：

```text
EvaluationReport.to_record()
```

Evaluation 是只读的，不会修改 telemetry。

---

# 5. Cursor / VS Code Desktop 使用说明

## 5.1 Extension 信息

Extension ID：

```text
market-sentinel-local.market-sentinel
```

Publisher：

```text
market-sentinel-local
```

这是本地 / developer VSIX 标识，不是 Marketplace publisher。

当前只支持：

```text
Cursor Desktop
VS Code Desktop
```

不支持浏览器版。

## 5.2 Cursor 设置

| Setting | 作用 |
|---|---|
| `marketSentinel.coreRoot` | Python Core checkout 路径；多 root 或非单目录 checkout 时需要 |
| `marketSentinel.uvPath` | `uv` 可执行文件；进程使用 `shell: false` |
| `marketSentinel.watchlist` | Host 的 Watchlist 意图；Core 仍限制最多 10 个 |
| `marketSentinel.provider` | `fake` / `replay` / `longbridge` |
| `marketSentinel.replayPath` | `replay` provider 的 JSONL 文件 |
| `marketSentinel.enableHoverDetails` | 是否显示完整 StatusBar hover，默认 `true` |
| `marketSentinel.alertToast` | `off` 或 `critical`，默认 `off` |
| `marketSentinel.intelligence` | `off` / `on` / `inherit`，默认 `off`。`on`/`off` 显式传 CLI；`inherit` 让环境变量决定。改完需 Restart Core。不要把 API Key 写入 settings |
| `marketSentinel.symbolNames` | 显示别名，仅 UI |
| `marketSentinel.symbolDisplay` | `name` / `nameAndCode` / `code`，默认 `nameAndCode` |
| `marketSentinel.statusBarMaxSymbols` | StatusBar 最多显示 1–3 只，默认 2 |

## 5.3 推荐手工验收流程

1. 安装 VSIX；
2. 打开 Trusted Workspace；
3. 必要时配置 `coreRoot`；
4. 确认 `uvPath`；
5. 选择 provider；
6. 配置 Watchlist（命令面板 Add Symbol，或 settings）；
7. Longbridge 模式下设置环境变量；
8. 可选：`marketSentinel.intelligence` 与 `DASHSCOPE_API_KEY`；
9. Reload Window；
10. 确认 StatusBar 出现行情，而不是 `MS XXX`；
11. Hover 查看连接 / AI / 当日涨跌 / 规则与 AI；
12. Pause；
13. Resume；
14. Restart Core；
15. Show Output；
16. Reset Alert Badge；
17. 可选：提交 Signal Feedback；
18. 关闭 Cursor；
19. 确认没有残留 `market-sentinel daemon` / Python child。

---

# 6. CLI 使用说明

## 6.1 Watchlist

添加：

```bash
uv run market-sentinel --watchlist data/watchlist.json watchlist add 600519.SH
```

查看：

```bash
uv run market-sentinel --watchlist data/watchlist.json watchlist list
```

## 6.2 单次运行

```bash
uv run market-sentinel --watchlist data/watchlist.json run --once
uv run market-sentinel --watchlist data/watchlist.json --intelligence run --once
uv run market-sentinel --watchlist data/watchlist.json --no-intelligence run --once
```

Verbose：

```bash
uv run market-sentinel --watchlist data/watchlist.json run --once --verbose
```

## 6.3 Daemon / Host Protocol

```bash
uv run market-sentinel --provider fake daemon
```

stdout 只用于 JSONL Protocol v1。

日志写 stderr。

stdin command 包括：

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

`set_watchlist` 只修改当前 runtime，不会写回：

```text
data/watchlist.json
```

Handshake：

```text
hello
→ set_watchlist
→ start
```

Cursor Host spawn 使用 argv，不使用 shell：

```text
uv run --directory <repo> market-sentinel --provider fake daemon
```

## 6.4 Provider 说明

### `fake`

默认 Provider。

不需要外部网络。

### `replay`

读取 JSONL fixture：

```text
--provider replay
--replay <path>
```

用于确定性 Replay。

### `longbridge`

可选 Core adapter。

需要：

```bash
uv sync --extra live
```

以及 Longbridge 环境变量。

### `http`

目前仍是未实现 stub。

### Tencent / Sina

v0.4 live gate 使用 Tencent 作为主 live probe，Sina 作为 one-shot cross-check。

当前它们仍是 probe，不是 Core `MarketProvider` factory 的正式 wiring。

---

# 7. 本地数据、评估与反馈

## 7.1 默认数据目录

可以通过：

```text
MARKET_SENTINEL_DATA_DIR
```

覆盖。

默认：

### Windows

```text
%LOCALAPPDATA%/MarketSentinel
```

### Unix

```text
$XDG_DATA_HOME/market-sentinel
```

或：

```text
~/.local/share/market-sentinel
```

## 7.2 数据布局

```text
MarketSentinel data directory/
├ telemetry.jsonl
├ telemetry.jsonl.1
├ telemetry.jsonl.2
├ ...
├ feedback.jsonl
├ feedback.jsonl.1
├ ...
└ tuning/
   └ <snapshot_uuid>.json
```

说明：

- `telemetry.jsonl`：append-only；
- `feedback.jsonl`：append-only；
- tuning snapshot：immutable；
- Host 不直接写这些文件；
- Core / local CLI 拥有本地 storage。

## 7.3 Telemetry

Telemetry 记录的是：

```text
系统观察事实
```

不是生产 MarketState 的一部分。

关键维度包括：

- `run_id`
- `created_timestamp`
- `market_timestamp`
- `symbol`
- `event_id`
- `signal_id`
- pipeline / host / intelligence event type
- 固定低基数 reason / status
- latency
- actual token usage（只有 provider 真正返回时才记录）

## 7.4 Feedback

`feedback.jsonl` 只在用户显式提交 feedback 后创建。

Feedback：

```text
append-only
```

同一个 `(run_id, signal_id)` 可以存在多条历史反馈。

M3 Evaluation 统计的是显式交互本身。

M5 Offline Tuning dataset 则使用：

```text
latest valid explicit feedback wins
```

来构建 target-level evidence。

## 7.5 Evaluation 重要语义

### `feedback_count`

显式提交反馈的数量。

### `useful_rate`

```text
useful / all explicit feedback
```

如果没有 feedback：

```text
unavailable
```

不是：

```text
0%
```

因为：

```text
没有反馈 ≠ not useful
```

### `feedback_coverage`

定义为：

```text
收到至少一次有效 explicit feedback 的
unique alert_presented (run_id, signal_id)
/
全部 unique alert_presented (run_id, signal_id)
```

它不是所有 QuickPick 可选 Signal 的覆盖率。

### `alerts_per_market_hour`

当前只支持：

```text
.SH
.SZ
```

使用：

```text
每个 run 的 telemetry-observed market-time span
```

而不是：

```text
进程 wall-clock uptime
```

A 股 cash session：

```text
09:30–11:30
13:00–15:00
UTC+8
```

周末排除。

完整官方交易所节假日日历尚未接入。

---

# 8. Offline Tuning 使用说明

## 8.1 创建 Baseline Snapshot

```bash
uv run market-sentinel tuning snapshot --config-version baseline-v0.6
```

## 8.2 创建 Candidate Snapshot

准备：

```text
candidate.json
```

只允许当前 supported 字段。

示例：

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

然后：

```bash
uv run market-sentinel tuning snapshot \
  --config-version candidate-001 \
  --config candidate.json \
  --source manual
```

## 8.3 比较 Candidate

```bash
uv run market-sentinel tuning compare \
  --baseline <snapshot_id> \
  --candidate <snapshot_id> \
  --corpus default
```

输出包括：

```text
baseline metrics
candidate metrics
delta
feedback evidence
data quality
per-fixture metrics
scheduler metrics
```

它不会输出：

```text
winner
best
recommended
score
rank
```

## 8.4 当前支持的 7 个参数

| 参数 | 当前说明 |
|---|---|
| `cluster_lookback_s` | Signal episode cluster look-back |
| `hot_event_severity` | WarmingPolicy HOT event severity threshold |
| `hot_volume_ratio_5m` | HOT 5m volume ratio threshold |
| `hot_change_5m` | HOT 5m change threshold |
| `warm_change_1m` | WARM 1m change threshold |
| `warm_change_5m` | WARM 5m change threshold |
| `warm_volume_ratio` | WARM volume ratio threshold |

## 8.5 当前 deferred 参数

以下参数目前不能进入 candidate：

### Monotonic Replay 尚不支持

- `cooldown_s`
- `upgrade_dwell_s`
- `hot_downgrade_dwell_s`
- `warm_downgrade_dwell_s`

原因：

当前 M5 deterministic Replay 固定 monotonic clock，没有把 market timestamp delta 映射为 monotonic elapsed time。

### Intelligence comparator 尚未接入

- `router_min_priority`
- `router_require_alert_edge`
- `router_min_convergence_types`
- `episode_max_calls`
- `allow_escalation_recall`

### Live cadence

- `cold_interval_s`
- `warm_interval_s`
- `hot_interval_s`

### Event 规则

- Event thresholds
- Event TTL

目前仍是 module-level production constants，尚未作为 Offline Replay candidate injection。

## 8.6 重要边界

Candidate snapshot：

```text
不是 active production config
```

Runtime：

```text
run
daemon
Cursor Host
```

都不会扫描或加载：

```text
<data-dir>/tuning/
```

CLI 只有：

```text
snapshot
compare
report
```

没有：

```text
apply
promote
activate
deploy
```

---

# 9. 系统架构

## 9.1 主数据链

```text
Market Provider
    │
    ▼
Normalization
    │
    ▼
Ring Buffer
    │
    ▼
Feature Engine
    │
    ▼
Event Rules
    │
    ▼
Dedupe
    │
    ▼
Cluster / Signal Composer
    │
    ▼
Cooldown
    │
    ▼
Signal / Alert Candidate
    │
    ├──────────────► optional Intelligence Sidecar
    │
    ▼
WarmingPolicy / Adaptive Scheduler
    │
    ▼
Runtime
(MarketState + EngineTickResult)
    │
    ├──────────────► CLI diagnostics
    │
    ├──────────────► Protocol v1 JSONL daemon
    │                     │
    │                     ▼
    │                Cursor Host
    │          StatusBar / Hover / Alert / Feedback
    │
    └──────────────► Telemetry
                          │
                          ▼
                    local JSONL
                          │
                          ▼
                    Evaluation
```

## 9.2 Observability / Feedback / Tuning 链

```text
Core observations
    │
    ▼
TelemetryEvent
    │
    ▼
telemetry.jsonl
    │
    ├─────────────► EvaluationReport
    │
    └─────────────► tuning eligibility join
                          ▲
                          │
Cursor explicit feedback │
    │                     │
    ▼                     │
user_feedback             │
    │                     │
    ▼                     │
UserFeedback              │
    │                     │
    ▼                     │
feedback.jsonl ────────────┘

manual candidate config
    │
    ▼
immutable tuning snapshot
    │
    ▼
fixed Replay corpus
    │
    ▼
TuningComparisonReport
```

没有：

```text
feedback
→ 自动修改 production config
```

---

# 10. 核心模块说明

下面按开发者视角说明主要模块职责。

## `market_data`

职责：

- Market Provider 接口；
- Fake / Replay provider；
- Longbridge optional adapter；
- session semantics；
- market snapshot normalization。

重点：

- `MarketSnapshot.volume / turnover` 是 session cumulative；
- Longbridge 当前 `turnover` 仍可能映射为 `None`；
- Tencent / Sina 目前仍是 live probe，不是正式 Core provider wiring。

## `features`

职责：

- 从 ring buffer 生成行情特征；
- 计算 change、EMA、RSI、VWAP、volume ratio 等。

Feature 是 Event Rule 的输入，不直接等于提醒。

## `events`

职责：

- 确定性 Event Rule；
- 产生 `rapid_move`、`volume_spike` 等 Event。

原则：

```text
Event = observed market fact
```

用户反馈不能回写 Event。

## `signals`

职责：

- Event dedupe；
- cluster；
- Signal episode composition；
- cooldown；
- alert candidate。

这里决定：

```text
同一市场变化
是否属于同一个 episode
是否应该再次提醒
```

## `scheduler`

职责：

- `WarmingPolicy`
- `AdaptiveScheduler`
- COLD / WARM / HOT lifecycle

当前 Offline Tuning 的 6 个 Warming 参数作用于这里。

## `runtime`

职责：

- 组织 Engine tick；
- 生成 `MarketState`；
- 生成 `EngineTickResult`；
- 将 provider、feature、event、signal、scheduler 等模块串起来。

生产 runtime 不读取 tuning snapshots。

## `ipc`

职责：

- Protocol v1；
- daemon stdin/stdout JSONL；
- DTO / mapping；
- Host command；
- lifecycle。

重要约束：

```text
stdout = Protocol JSONL only
```

日志必须走 stderr。

Telemetry / feedback JSONL 是独立本地文件，不走 Protocol stdout。

## `intelligence`

职责：

- deterministic router；
- episode call budget；
- provider boundary；
- async sidecar coordinator；
- structured annotation；
- diagnostics。

默认关闭：

```text
MARKET_SENTINEL_INTEL_ENABLED=0
```

或 CLI / Cursor：

```text
--no-intelligence
marketSentinel.intelligence = off
```

启用：

```text
MARKET_SENTINEL_INTEL_ENABLED=1
```

或：

```text
--intelligence
marketSentinel.intelligence = on
```

优先级：显式 CLI > 环境变量 > 默认关闭。`inherit` 不传 CLI，兼容旧 env。

DashScope key：

```text
DASHSCOPE_API_KEY
```

模型失败只影响 Intelligence annotation，不影响 Rule Signal / Alert。

## `telemetry`

职责：

- `TelemetryEvent`
- `UserFeedback`
- strict allowlist
- collector
- fail-open boundary
- JSONL sink
- rotation / corruption handling

核心设计：

```text
measurement != mutation
```

## `evaluation`

职责：

- 读取 telemetry / feedback；
- 数据质量检查；
- funnel / noise / host / intelligence 指标；
- per-run；
- per-market-date；
- market-hour；
- repeated episode；
- feedback coverage。

Evaluation 是只读层。

## `tuning`

职责：

- `OfflineTuningConfig`
- tuning parameter inventory
- immutable snapshot
- feedback eligibility dataset
- deterministic Replay comparison
- before / after / delta report

核心原则：

```text
offline evidence
!=
automatic tuning
```

## `cli`

职责：

- Watchlist；
- run；
- daemon；
- telemetry report；
- tuning snapshot / compare / report。

## `apps/cursor-extension`

职责：

- 启动 Python Core；
- 管理 Protocol；
- StatusBar；
- Hover；
- unread alert；
- Pause / Resume / Restart；
- Show Output；
- Signal Feedback；
- VSIX packaging。

Python Core **不打包进 VSIX**。

---

# 11. 功能与数据语义

## 11.1 `ACTIVE SIGNALS`

来源：

```text
MarketState
```

表示当前仍处于 look-back / episode 生命周期中的 Signal。

它是持久状态。

## 11.2 `EVENTS THIS TICK`

来源：

```text
SymbolTickResult.accepted_events
```

只表示当前 tick 新接受的 Event。

## 11.3 `ALERTS THIS TICK`

来源：

```text
SymbolTickResult.alert_candidates
```

表示当前 tick 新的提醒资格。

因此：

```text
Signal 仍 active
```

并不意味着：

```text
这个 tick 一定有 alert
```

cooldown 可以让：

```text
ACTIVE SIGNALS != empty
ALERTS THIS TICK = None
```

## 11.4 Alert candidate 与真正 Host presentation

Core：

```text
alert_candidate
```

Host 真正收到并纳入 presentation / unread 后才有：

```text
alert_presented
```

它们不是同一个事实。

## 11.5 Timestamp

系统区分：

### `created_timestamp`

观测 / runtime wall-clock。

### `market_timestamp`

对应行情本身的市场时间。

### `run_id`

一次 Core runtime / Replay execution 的关联 ID。

不要把 `run_id`、市场 session date 和 wall-clock timestamp 混用。

---

# 12. 配置说明

## 12.1 Cursor 配置

见前面的 [Cursor 设置](#52-cursor-设置)。

## 12.2 Core 数据目录

```text
MARKET_SENTINEL_DATA_DIR
```

覆盖 telemetry / feedback / tuning 的本地根目录。

## 12.3 Intelligence

启用：

```text
MARKET_SENTINEL_INTEL_ENABLED=1
```

DashScope：

```text
DASHSCOPE_API_KEY
```

默认关闭 Intelligence。

## 12.4 Longbridge

环境变量：

```text
LONGBRIDGE_APP_KEY
LONGBRIDGE_APP_SECRET
LONGBRIDGE_ACCESS_TOKEN
```

依赖：

```bash
uv sync --extra live
```

Host 不会自动使用 `--extra live`。

## 12.5 Watchlist

CLI 默认文件示例：

```text
data/watchlist.json
```

Cursor Host 使用：

```text
marketSentinel.watchlist
```

`set_watchlist` 是 runtime-only，不会写 `data/watchlist.json`。Cursor Add/Remove Symbol 会写 Workspace `marketSentinel.watchlist`，然后 `set_watchlist`。两套入口不自动同步。

---

# 13. 关键文档

## `README.md`

项目入口。

适合：

- 新用户上手；
- 了解当前版本能力；
- 查安装、运行、配置和架构。

## `CHANGELOG.md`

记录版本变化和已完成能力。

当前 v0.6.0 的主题：

```text
Feedback
Observability
Offline Tuning
```

## `docs/08_Roadmap_v0.6_Feedback_and_Tuning.md`

v0.6 的设计路线与阶段定义。

重点：

- telemetry；
- feedback；
- evaluation；
- offline tuning；
- “feedback ≠ market fact”；
- 禁止 online self-modification。

## `docs/12_v0.4_Longbridge_Provider_Setup.md`

Longbridge provider 的安装与环境变量说明。

## `docs/16_v0.6_Metrics_Contract.md`

v0.6 telemetry / feedback / tuning 语义合同。

适合开发者在修改：

- telemetry name；
- run / market time；
- feedback；
- data quality；
- evaluation；
- tuning eligibility

之前阅读。

## `docs/17_v0.6_Release_Candidate.md`

v0.6.0 Release Candidate 的发布准备记录。

包括：

- version inventory；
- Protocol/schema；
- tests；
- coverage；
- offline smoke；
- VSIX；
- privacy；
- known limitations。

---

# 14. 开发、测试与打包

## 14.1 Python tests

```bash
uv run pytest
```

默认 pytest 是离线的。

live tests 默认 deselect。

## 14.2 Coverage

```bash
uv run pytest \
  --cov=market_sentinel \
  --deselect tests/integration/test_engine_perf.py::test_ten_symbol_engine_replay_stays_within_regression_budget
```

Coverage fail-under：

```text
85%
```

当前 v0.6 release verification 约：

```text
90.44%
```

## 14.3 Timing regression

Timing test 必须在无 coverage instrumentation 下运行：

```bash
uv run pytest tests/integration/test_engine_perf.py::test_ten_symbol_engine_replay_stays_within_regression_budget
```

coverage instrumentation 可能显著放大 wall-clock 时间，这本身不代表产品性能回归。

## 14.4 Ruff

```bash
uv run ruff check .
uv run ruff format --check .
```

## 14.5 TypeScript / Cursor

```bash
pnpm test
pnpm lint
pnpm typecheck
pnpm build
```

Extension Host smoke：

```bash
pnpm test:extension-host
```

该命令通过 `@vscode/test-electron` 下载 VS Code Desktop binary，不是 Cursor binary。

## 14.6 VSIX

```bash
pnpm package:vsix
```

当前版本：

```text
market-sentinel-0.6.0.vsix
```

Release verification 中：

```text
21 files
27208 bytes
audit pass
```

Python Core 不包含在 VSIX 中。

---

# 15. 隐私与安全边界

Market Sentinel v0.6 的本地 observability / feedback / tuning 只允许保存低基数结构化数据。

允许：

- 固定 config 字段；
- snapshot identity；
- corpus ID；
- 聚合指标；
- fixed feedback label；
- fixed data-quality counter；
- symbol / event / signal correlation ID；
- latency / actual token usage。

不保存：

- workspace 内容；
- conversation；
- source code；
- 文件内容；
- 用户绝对 fixture path；
- raw tick payload；
- feature payload；
- prompt；
- API key；
- model raw output；
- Signal title / summary；
- free-text feedback；
- free-form tuning notes。

Intelligence 也不会读取 workspace / conversation 作为默认输入。

---

# 16. 已知局限

## 16.1 Watchlist 规模

最多：

```text
10 symbols
```

这是当前 MVP 的明确范围。

## 16.2 Volume / Turnover 语义

`MarketSnapshot.volume` / `turnover` 是：

```text
session cumulative
```

不是每个 interval 的增量。

Volume ratio 大约需要：

```text
20 个 in-session 1-minute baseline
```

之后才定义。

之前是：

```text
None
```

不会被当成 `0`。

## 16.3 官方 K 线差异

`MarketBar` 是 adaptive polling 下的：

```text
sampled / observed 1-minute bar
```

不是交易所官方 1 分钟 K 线。

## 16.4 VWAP

VWAP 需要可靠：

```text
cumulative turnover
cumulative volume
```

Longbridge 当前 `turnover` 仍可能为 `None`。

## 16.5 市场时段

当前 session id 仍基于：

```text
UTC+8 calendar date
```

Evaluation 的 `alerts_per_market_hour`：

- 只支持 `.SH` / `.SZ`；
- 周末排除；
- 尚未接入完整交易所节假日日历；
- `.HK` 返回 `unsupported_market_scope`。

## 16.6 Live Provider

Tencent live gate 已通过：

```text
1 / 2 / 10 batches
freshness
```

Sina 是 one-shot cross-check。

它们当前仍是 probe，不是 Core `MarketProvider` 正式 wiring。

Longbridge 是 optional provider。

## 16.7 Cursor 形态

仅支持：

```text
Desktop Cursor / VS Code
```

不支持：

- Web / browser Cursor；
- 已验证的 Remote SSH；
- 已验证的 Codespaces。

Untrusted workspace 不支持，因为 Host 会启动本地 Python Core。

## 16.8 Python Core 不打包进 VSIX

用户仍需要：

```text
Core checkout
+ uv
```

Longbridge 还需要手动：

```bash
uv sync --extra live
```

## 16.9 Host 功能仍较轻

当前没有：

- WebView；
- Alert history panel；
- 持久 unread count；
- `notified_timestamp`。

Unread badge 是 Host-local，extension reload 后会重置。

## 16.10 Host interaction 指标仍有 unavailable

尚未实现 producer：

```text
signal_opened
alert_dismissed
signal_muted
```

所以对应 rate 是：

```text
unavailable
```

不是：

```text
0%
```

## 16.11 Intelligence

默认关闭。

当前没有：

- News；
- MCP；
- auto-trading；
- buy/sell advice；
- default live model tests。

## 16.12 ClusterMembershipTracker

为了保证：

```text
event_clustered
at most once / event_id / run
```

Tracker 会在整个 run 内保留 clustered event IDs。

长时间 daemon 理论上会增长。

当前没有用 LRU，因为 LRU eviction 会破坏 once-per-run 精确语义。

## 16.13 JSONL 同步写

当前：

```text
write
→ flush
→ stat
→ possible rotate
```

在 producer thread 同步执行。

v0.6 没有改成 async queue。

## 16.14 Feedback 存在自选择偏差

`useful_rate` 只代表：

```text
主动提交 feedback 的样本
```

不是：

```text
全部 alert 的满意度
```

没有反馈不能解释成负面反馈。

## 16.15 结构合法但未知 signal_id

Local / trusted Protocol 可以被手工构造：

```text
结构合法的 user_feedback
+
未知 signal_id
```

Core 仍可能落盘。

M5 tuning dataset 会通过：

```text
(run_id, signal_id)
```

join telemetry，把无法关联的 feedback 作为 orphan 排除。

## 16.16 Offline Tuning 不是全参数 tuning

当前只有 7 个 evidence-backed 参数。

Deferred：

- cooldown；
- dwell；
- Intelligence Router；
- episode call budget；
- live polling interval；
- Event thresholds / TTL；
- 其他未注入 Offline Replay 的参数。

## 16.17 Tuning draft schema 1 不兼容

当前正式：

```text
Tuning Artifact Schema = 2
Tuning Comparison Schema = 2
```

未发布的 draft schema 1：

```text
fail closed
```

不提供 migration。

---

# 17. 未来可能增加的方向

以下只是基于当前局限推导出的可能演进方向，不代表已经排期或承诺实现。

## 17.1 更完整的交易所日历

可能包括：

- 中国交易所官方节假日；
- 特殊交易日；
- HK 独立 market-hour 语义；
- 更明确的跨市场 session abstraction。

## 17.2 更完整的 Host 交互

可能包括：

- `signal_opened` producer；
- per-alert dismiss；
- mute；
- alert history；
- 可视化详情面板；
- 更长期的 Host interaction metrics。

## 17.3 Async Telemetry Sink

如果真实负载证明同步 JSONL 对 tick latency 有明显影响，可以考虑：

```text
bounded async queue
→ background writer
```

但需要继续保证：

```text
telemetry failure
!=
market pipeline failure
```

## 17.4 Cluster 生命周期优化

需要在：

```text
once-per-run exactness
```

和：

```text
long-lived memory bound
```

之间设计更合理的机制。

不能简单加 LRU。

## 17.5 更真实的 Replay Clock

未来如果 Replay 能忠实推进 monotonic time，就可以评估：

- cooldown；
- dwell；
- Scheduler timing；
- live cadence 类参数。

当前这些仍 deferred。

## 17.6 Intelligence Offline Evaluation

未来可以增加一个完全离线、可控的 Intelligence comparison harness，用于评估：

- router threshold；
- call budget；
- fallback；
- latency；
- structured output quality。

但仍应避免：

```text
自动 promote production config
```

## 17.7 Event Threshold Injection

未来可以把部分 Event thresholds / TTL 从 module globals 迁移为可注入 config。

前提是：

- production default 不变；
- Replay parity 明确；
- candidate isolation；
- sensitivity evidence；
- before / after 可观察。

## 17.8 Live Provider 正式 wiring

Tencent / Sina 当前是 probes。

未来可能将经过验证的 live source 正式接入：

```text
MarketProvider
→ Core
```

但应继续保持 provider boundary 与 replayability。

## 17.9 更完整的发布与分发

当前：

```text
本地 release-ready
无 remote
无 v0.6.0 tag
无 VSIX publication
```

未来可以在明确 remote topology 后：

```text
remote add
→ fetch
→ topology verify
→ annotated tag
→ push
→ release
```

也可以进一步考虑：

- VSIX 正式分发；
- 更易安装的 Python Core；
- Marketplace / 内部 registry；
- release automation。

---

# 18. 当前发布边界

当前本地状态：

```text
Market Sentinel v0.6.0
Package = 0.6.0
Protocol = 1
Tuning Artifact Schema = 2
Tuning Comparison Schema = 2
```

v0.6.0 已在本地完成：

```text
开发
→ Review
→ Release Prep
→ Final Verification
→ master fast-forward
→ master gates
```

当前仍然：

```text
No v0.6.0 tag
No push
No remote publication
No VSIX publication
No v1.0 work started
```

现有最后 Git tag 仍是：

```text
v0.3.0
```

`v0.4.0` 从未正式发布。

v0.5.0 包含：

- 未发布的 v0.4 live-data lineage；
- Intelligence Router / async sidecar。

v0.6.0 新增：

- observability；
- local JSONL storage；
- evaluation；
- explicit feedback；
- offline-only tuning comparison。

---

## 一句话总结

Market Sentinel 现在是一套：

```text
小规模行情观察
+ 确定性 Event / Signal
+ 低打扰 Alert
+ Cursor Desktop Host
+ 可选 Intelligence Sidecar
+ 本地 Telemetry / Feedback
+ Offline Evaluation
+ Evidence-based Offline Tuning
```

的开发者型市场监控系统。

它当前最重要的边界仍然是：

```text
观察 ≠ 交易
反馈 ≠ 市场事实
评估 ≠ 自动优化
候选配置 ≠ 生产配置
模型 ≠ 高频主链
```
