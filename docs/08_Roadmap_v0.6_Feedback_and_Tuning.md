# Roadmap v0.6 — Feedback, Observability & Tuning

> Status: **M0–M5 complete.** **M6 release prep** on `feat/v0.6-feedback-observability`. Package versions **0.6.0**. Protocol **1**. Tuning artifact schema **2**. Tuning comparison schema **2**. Do **not** merge `master`, tag, or start v1.0.
>
> Token target: **低**
>
> See `docs/16_v0.6_Metrics_Contract.md`.

---

## 1. 目标

v0.6 开始回答：

> **哪些 Event / Signal / Alert 对用户真正有用？哪些规则太吵？**

不是自动交易优化，也不是让 LLM 自己在线改规则。

---

## 2. Feedback Pipeline

```text
Market Event
   ↓
Signal Episode
   ↓
Alert Candidate
   ↓
Host Presentation
   ↓
User Interaction
   ↓
Feedback Metrics
   ↓
Offline Tuning
```

---

## 3. 最低记录指标

至少记录：

```text
Events generated
Events deduped
Events clustered
Signal episodes created
Signal escalations
Alert candidates
Alerts presented
Signals opened
Alerts reset/dismissed
Signals muted
```

如果 Intelligence 已开启：

```text
Intelligence routed
Intelligence skipped
Intelligence success
Intelligence fallback
Token usage
Latency
```

---

## 4. Optional Explicit Feedback

可选：

```text
Useful
Not Useful
Too Noisy
Too Late
```

不要在 v0.6 强迫用户每次反馈。

低打扰优先。

---

## 5. Feedback ≠ Core Event Mutation

Host interaction 不能回写：

```text
“This event never happened”
```

客观 Event 历史与用户反馈分开。

例如：

```text
Event: rapid_move
Feedback: not useful for this user
```

而不是删除 Event。

---

## 6. Tuning Scope

反馈可以支持离线调整：

### Event / Signal

- threshold；
- severity mapping；
- cooldown；
- cluster look-back；
- episode behavior。

### Scheduler

- WARM/HOT entry；
- dwell；
- downgrade hysteresis。

### Intelligence

- Router threshold；
- eligible priority；
- prompt compactness；
- call budget。

但调整必须：

- 有版本；
- 有 replay regression；
- 有 before/after metrics；
- 不在线自修改生产规则。

---

## 7. Data Model

建议概念上分：

```text
TelemetryEvent
UserFeedback
TuningSnapshot
```

不要直接把所有东西塞回 `MarketState`。

Protocol 与存储 schema 也不要混为一体。

---

## 8. Privacy

默认只记录 Market Sentinel 自己产生的：

- event metadata；
- signal metadata；
- Host interaction；
- latency/cost。

不采集无关 workspace 内容。

如果未来持久化或上传反馈数据，必须单独设计 opt-in / privacy boundary。

---

## 9. Storage

v0.6 MVP 使用本地 append-only JSONL（不是 SQLite）。

选择以：

```text
single-process
local-first
simple auditability
```

为优先。

不要因为 telemetry 引入数据库服务 / Redis / Kafka。

路径是 Market Sentinel local data directory（可用 `MARKET_SENTINEL_DATA_DIR` 注入），不是 repo / cwd / Protocol stdout。

---

## 10. Evaluation

核心指标可以包括：

```text
alerts per market hour
important/critical ratio
repeated episode alerts
open rate
mute/dismiss rate
useful rate
average intelligence tokens per day
fallback rate
```

不以“更多 alert”为成功指标。

---

## 11. Replay Tuning

任何规则调整前：

```text
old config
vs
new config
```

跑固定 Replay corpus。

至少检查：

- normal market noise；
- rapid move；
- volume spike；
- breakout；
- reversal；
- stale/disconnect；
- episode lifecycle。

---

## 12. Milestones

### M0 — Metrics contract

- [x] 定义什么记录、什么不记录（`docs/16_v0.6_Metrics_Contract.md`；Core types + offline tests only）。
- [x] 外审后最终冻结（`21e96dc` on `feat/v0.6-feedback-observability`）。

M0 已纳入：`run_id`、`market_timestamp`、Host→Core collector 所有权、`alert_presented` 每 candidate、`alert_suppressed`、`decision_reason` / `latency_stage`、`event_clustered` once-per-run、无 `notes` 的 `TuningSnapshot`、最低 validation。

### M1 — Telemetry wiring

- [x] 每 execution 一个 opaque `run_id`（不是 market session）。
- [x] fail-open collector；pipeline / intelligence / Host interaction 按冻结 contract emit。
- [x] Protocol v1 additive `host_interaction`（`alert_presented` per candidate、`alert_badge_reset`）。
- [x] `signal_opened` / `alert_dismissed` / `signal_muted` taxonomy 保留；当前 UX 不伪造 producer。

### M2 — Local storage

- [x] append-only JSONL（不是 SQLite）。
- [x] rotation（默认 1 MiB / 5 backups）。
- [x] trailing partial 可恢复；middle-of-file malformed 可检测。
- [x] 严格 allowlist serialization；落盘目录可注入，默认不写 repo / cwd。

### M3 — Evaluation report

- [x] daily/session summary from JSONL (`per_run`, `per_market_date`; market date from `market_timestamp` only);
- [x] pipeline funnel + noise metrics (priority, suppression by reason, repeated episode, alerts per A-share market hour);
- [x] A-share market-hour metric is `.SH`/`.SZ` only; non-A-share is `unsupported_market_scope`, not A-share windows;
- [x] intelligence cost (skip/fallback breakdown on frozen keys, latency stages, actual token events only);
- [x] Host unimplemented facts (`signal_opened` / dismiss / mute) reported as **unavailable**, never fake 0%.

Read-only. Does not rewrite telemetry semantics, Event/Signal rules, thresholds, or RouterPolicy.

### M4 — Explicit feedback

- [x] frozen taxonomy `useful` / `not_useful` / `too_noisy` / `too_late` (no free text);
- [x] Protocol v1 additive `user_feedback` on `signal_id` only; Host produces facts, Core stores;
- [x] `feedback.jsonl` append-only, separate from `telemetry.jsonl`;
- [x] optional Cursor command / QuickPick; hover / badge reset / toast are not feedback;
- [x] M3 report reads feedback (`feedback_count`, label counts, explicit `useful_rate`, `feedback_coverage`).

Feedback does not mutate Event/Signal, cooldown, RouterPolicy, Scheduler, or thresholds.

### M5 — Tuning workflow

- [x] versioned `TuningSnapshot` + `OfflineTuningConfig` artifact (`$DATA_DIR/tuning/<snapshot_id>.json`);
- [x] `capture_baseline_config()` from current production defaults;
- [x] fixed Replay corpus comparison (one baseline vs one candidate);
- [x] `TuningFeedbackDataset` requires `(run_id, signal_id)` join to Core signal lifecycle evidence; latest valid feedback wins per target;
- [x] no `apply` / `promote` / `activate` / `deploy`; production runtime does not load snapshots.

M5 provides **offline evidence, not automatic tuning**. Candidate configs are never automatically loaded by production runtime.

Supported M5 parameters must pass Consumed + Observable + Sensitivity proof (Comparison Report delta, not Engine facts alone):

```text
cluster_lookback_s
hot_event_severity, hot_volume_ratio_5m, hot_change_5m
warm_change_1m, warm_change_5m, warm_volume_ratio
```

Deferred (still in `tuning_parameter_inventory()`, rejected from candidate config):

```text
cooldown_s, upgrade/hot/warm dwells   # deterministic M5 Replay freezes monotonic time
router_* / episode_max_calls / allow_escalation_recall  # comparator does not attach Intelligence
cold/warm/hot_interval_s             # live AdaptiveScheduler cadence; Replay uses interval 0
event thresholds / TTL               # events/thresholds.py module globals
prompt compactness, intelligence_timeout_s, volume_ratio_lookback
```

Artifact `schema_version` is **2** (draft schema 1 fail-closed). Comparison report `schema_version` is **2** and includes `scheduler` tick counts. Protocol remains **1**.

Feedback used for tuning must join telemetry by `(run_id, signal_id)` to Core lifecycle evidence (`signal_episode_created` / `signal_escalated` / `alert_candidate` / `alert_suppressed`). Storage stays append-only; the tuning dataset uses latest `created_timestamp` then `feedback_id` per target. `no feedback != not_useful`.

### M6 — Release prep

Package **0.6.0**. See `docs/17_v0.6_Release_Candidate.md`. No merge, tag, push, or v1.0.

---

## 13. v0.6 验收

- [x] Event → Signal → Alert → Host interaction 可追踪；
- [x] persistent state 与 telemetry 分离；
- [x] local-first storage；
- [x] optional explicit feedback；
- [x] no automatic online rule mutation；
- [x] tuning 必须跑 Replay regression；
- [x] Intelligence token/cost 可统计（actual `intelligence_token_usage` only; unavailable when none）；
- [x] 不采集无关 workspace 内容。

---

## 14. 明确不做

v0.6 不做：

- reinforcement learning；
- autonomous threshold rewriting；
- cloud telemetry backend；
- user profiling system；
- trading PnL optimization；
- multi-host rollout。
