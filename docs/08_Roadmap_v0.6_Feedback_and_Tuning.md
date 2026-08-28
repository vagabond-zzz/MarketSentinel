# Roadmap v0.6 — Feedback, Observability & Tuning

> Status: **M0 Metrics Contract on `feat/v0.6-feedback-observability`.** Waiting for external review. Not tagged. Package versions remain **0.5.0**. Protocol **1**.
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

v0.6 MVP 可先本地保存。

候选：

- JSONL；
- SQLite。

选择以：

```text
single-process
local-first
simple auditability
```

为优先。

不要因为 telemetry 引入数据库服务 / Redis / Kafka。

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

- [x] 定义什么记录、什么不记录（`docs/16_v0.6_Metrics_Contract.md`；Core types only）。

### M1 — Host interaction telemetry

- opened；
- reset；
- mute/dismiss placeholder。

### M2 — Local storage

- append-only；
- rotation；
- corruption-safe。

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

- [ ] Event → Signal → Alert → Host interaction 可追踪；
- [ ] persistent state 与 telemetry 分离；
- [ ] local-first storage；
- [ ] optional explicit feedback；
- [ ] no automatic online rule mutation；
- [ ] tuning 必须跑 Replay regression；
- [ ] Intelligence token/cost 可统计；
- [ ] 不采集无关 workspace 内容。

---

## 14. 明确不做

v0.6 不做：

- reinforcement learning；
- autonomous threshold rewriting；
- cloud telemetry backend；
- user profiling system；
- trading PnL optimization；
- multi-host rollout。
