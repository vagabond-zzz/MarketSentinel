# Roadmap v0.6 — Feedback, Observability & Tuning

> Status: **M0 frozen.** M1/M2 review fixes applied on `feat/v0.6-feedback-observability`. Package versions remain **0.5.0**. Protocol **1**. **M3 is not approved.**
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

- daily/session summary；
- noise metrics；
- intelligence cost。

### M4 — Explicit feedback

- useful/not useful；
- optional UX。

### M5 — Tuning workflow

- config snapshot；
- replay comparison；
- no automatic mutation。

### M6 — Release prep

- privacy docs；
- regression；
- version。

---

## 13. v0.6 验收

- [x] Event → Signal → Alert → Host interaction 可追踪；
- [x] persistent state 与 telemetry 分离；
- [x] local-first storage；
- [ ] optional explicit feedback；
- [x] no automatic online rule mutation；
- [ ] tuning 必须跑 Replay regression；
- [ ] Intelligence token/cost 可统计；
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
