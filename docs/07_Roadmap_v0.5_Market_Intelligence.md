# Roadmap v0.5 — Market Intelligence Router

> Status: **RC Fix Pass on `feat/v0.5-market-intelligence`.** Waiting for second external review. Not tagged, not merged, versions remain 0.3.0.
>
> Token target: **0 by default**; **极低** only when intelligence is explicitly enabled.
>
> See `docs/14_v0.5_Intelligence_Contract.md` and `docs/15_v0.5_Release_Candidate.md`.

---

## 1. 目标

在已经稳定的真实市场数据链路上，引入第一个**低频、可失败、可旁路**的 Intelligence 层。

Agent 不参与行情刷新。

```text
Market Feed
   ↓
Feature / Event / Signal
   ↓
Significant Episode
   ↓
Intelligence Router
   ├── NO → Rule Signal
   └── YES → Analyst → Enriched Signal
```

---

## 2. Token 原则

正确：

```text
Token Cost ≈ significant episode count × analysis budget
```

禁止：

```text
symbols × refresh frequency × time
```

正常行情：

```text
Token = 0
```

---

## 3. Router 输入

Router 不读 raw tick stream。

只读压缩结构化摘要，例如：

```json
{
  "symbol": "00700.HK",
  "family": "tape",
  "direction": "up",
  "priority": "important",
  "change_1m": 0.008,
  "change_5m": 0.018,
  "volume_ratio_5m": 2.6,
  "above_vwap": true,
  "rsi14": 68,
  "event_types": ["rapid_move", "price_volume_expansion"]
}
```

不发送：

- RingBuffer；
- raw ticks；
- full bar history；
- 全量 SignalTrace；
- irrelevant symbols。

---

## 4. Need Intelligence?

Router 必须 deterministic-first。

例：

### 不调用

- INFO；
- ordinary NOTICE；
- duplicate / cooldown-suppressed；
- stale feed；
- insufficient features。

### 可调用

- IMPORTANT / CRITICAL；
- price + volume + breakout cluster；
- escalation episode；
- rare multi-rule convergence。

具体 threshold 不由 LLM 决定。

---

## 5. 第一个 Agent

只实现一个逻辑角色：

```text
Supervisor / Analyst
```

不真正构建多 Agent network。

Price / Volume / Technical specialization 继续由 deterministic module 完成。

---

## 6. LLM 输出

只回答：

1. 是否值得提升提醒表达；
2. 主要异常原因；
3. confidence；
4. 简短摘要。

建议结构：

```json
{
  "worth_highlight": true,
  "reason": "price and volume expanded together near the session high",
  "confidence": 0.82,
  "summary": "Price-volume expansion is unusually strong."
}
```

输出预算：

```text
~100 tokens or less
```

---

## 7. Rule Signal vs Enriched Signal

必须保留 deterministic origin。

Enriched Signal 不能替代/覆盖事实 Event。

概念：

```text
Rule Signal
+ optional Intelligence Annotation
```

而不是：

```text
LLM invents a new market event
```

必须可区分：

```text
generated_by = rule
intelligence = none | enriched
```

具体字段在实现前再冻结。

---

## 8. Failure Fallback

LLM：

- timeout；
- transport error；
- malformed JSON；
- model unavailable；
- rate limited；

全部：

```text
fallback → original Rule Signal
```

市场事件不能因为模型不可用而丢失。

---

## 9. Latency

Intelligence latency 必须与 market path 分离统计。

记录：

```text
router decision latency
model request latency
parse latency
fallback count
```

不能让 Model 阻塞 Core 高频 tick loop。

建议异步旁路：

```text
Core signal episode
→ enqueue intelligence work
→ Core continues
```

具体并发模型实现前单独设计。

---

## 10. Episode Call Budget

默认：

> 每个 Signal episode 最多一次 Intelligence 调用。

只有明确的 priority escalation 才考虑第二次。

Host unread / notification 行为不能反向触发模型。

---

## 11. Protocol

优先保持 Protocol v1 可兼容扩展。

Host 最终可收到：

- original rule signal state；
- optional enriched summary；
- intelligence status / fallback diagnostics。

不要把 provider/model secrets 放进 Protocol。

若必须 breaking change，先单独做 protocol design，不自行偷偷升级。

---

## 12. Privacy / Prompt Scope

只发送完成任务所需的结构化市场信息。

默认不发送：

- workspace source code；
- Cursor conversation；
- local files；
- user private notes。

Intelligence Router 是市场分析组件，不是 Workspace Agent。

---

## 13. Milestones

### M0 — Intelligence contract

- Router input；
- Router output；
- fallback；
- token budget；
- no code first。

### M1 — Deterministic Router

- need-intelligence decision；
- no model yet；
- tests。

### M2 — Model adapter

- single provider adapter；
- timeout；
- structured output parse。

### M3 — Async execution

- no high-frequency blocking；
- episode budget；
- cancellation / stale work。

### M4 — Enriched signal state

- original rule signal preserved；
- enrichment attached；
- fallback visible。

### M5 — Cursor presentation

- concise enriched summary；
- no extra noisy toast；
- low distraction。

### M6 — Replay evaluation

- significant episodes；
- normal market token=0；
- failure fallback；
- latency stats。

### M7 — Release prep

- docs / tests / cost / privacy / protocol-compat audit；
- **no** version bump, tag, merge, or push — stop for external review。

---

## 14. v0.5 验收

- [x] Agent 只由 Significant Event / Episode 触发；
- [x] 正常行情 Token = 0；
- [x] 每个 episode 默认最多一次 LLM 调用；
- [x] raw ticks 不发送给模型；
- [x] LLM failure → Rule Signal fallback；
- [x] Rule Signal / Enrichment 可区分；
- [x] Intelligence latency 单独统计；
- [x] Core tick 不等待模型；
- [x] Host 不触发 intelligence decision；
- [x] no trading advice。

---

## 15. 明确不做

v0.5 不做：

- multi-agent swarm；
- News Agent；
- Sector Agent；
- long context market memory；
- autonomous rule editing；
- Workspace source-code ingestion；
- auto trading。
