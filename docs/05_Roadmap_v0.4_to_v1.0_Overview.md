# Roadmap v0.4 → v1.0 — Live Data, Intelligence & Multi-Host

> Current baseline: **Market Sentinel v0.3.0 — Cursor Host**
>
> v0.1–v0.3 已完成 Core、Event Engine、Protocol v1、Python JSONL daemon 与 Cursor Host。后续版本不重新复制这些能力，而是在稳定边界上继续扩展。

---

## 1. 当前稳定基线

### v0.1 — Core Foundation ✅

已完成：

- MarketSnapshot / MarketState；
- Ring Buffer / rolling state；
- FakeProvider / ReplayProvider；
- Feed Health；
- COLD / WARM / HOT Scheduler；
- steppable async MarketEngine.tick()；
- CLI diagnostics；
- 高频路径 Token = 0。

### v0.2 — Market Event Engine ✅

已完成：

- rolling Features；
- EMA / RSI / VWAP；
- 6 条 Event Rules；
- dedupe / look-back cluster / cooldown；
- Signal episode lifecycle；
- persistent state 与 alert edge 分离；
- Replay E2E / performance regression。

### v0.3 — Cursor Host ✅

已完成：

- Protocol v1；
- Python JSONL daemon；
- TypeScript IPC client；
- child process lifecycle；
- Cursor Extension activate/deactivate；
- StatusBar / Hover；
- IDLE / NORMAL / WARM / HOT / STALE / ALERT；
- Host-local unread badge；
- optional critical toast；
- local VSIX packaging；
- Core Model ≠ Wire DTO；
- persistent state ≠ alert edge。

---

## 2. 后续版本总原则

```text
High-frequency market path
        ↓
Deterministic program logic
        ↓
Feature / Event / Signal
        ↓
Protocol DTO
        ↓
Host Adapter

Only significant low-frequency cases
        ↓
Optional Intelligence Router
        ↓
LLM
```

冻结原则：

1. **Agent 不参与行情刷新。**
2. **正常行情 Token = 0。**
3. **Provider 变化不改变 Feature / Event / Signal 规则。**
4. **Host 不复制市场规则。**
5. **Protocol 是跨宿主稳定边界。**
6. **persistent state ≠ alert edge。**
7. **active signal ≠ unread / notification。**
8. **模型失败不能导致市场事件丢失。**

---

## 3. 版本路线

| Version | 核心目标 | Token | 主要输出 |
|---|---|---:|---|
| v0.1 | Core / Ring Buffer / Scheduler | 0 | Core foundation |
| v0.2 | Feature / Event / Signal | 0 | deterministic signal engine |
| v0.3 | Cursor Host / Protocol v1 | 0 | desktop host MVP |
| **v0.4** | **Live Market Data / Feed Reliability** | **0** | first real-data full path |
| **v0.5** | **Intelligence Router / Single Analyst** | **极低** | event-triggered enrichment |
| **v0.6** | **Feedback / Tuning** | **低** | observability + tuning loop |
| **v1.0** | **Multi-Host** | **视配置** | Cursor + second host |

---

## 4. v0.4 — Live Market Data

目标：第一次让真实行情穿过完整链路：

```text
Live Provider
   ↓
Normalization
   ↓
MarketEngine
   ↓
Feature / Event / Signal
   ↓
Protocol v1
   ↓
Cursor Host
```

重点不是“接一个 HTTP API 就结束”，而是验证：

- source semantics normalization；
- timeout / malformed response；
- disconnect / reconnect；
- stale / delayed；
- out-of-order quote；
- cumulative volume reset；
- session boundary；
- provider failure 不制造假 Event。

详细见：`06_Roadmap_v0.4_Live_Market_Data.md`

---

## 5. v0.5 — Market Intelligence

只对 Significant Event / Event Cluster 进行低频智能增强：

```text
Event / Signal episode
        ↓
Rule Filter
        ↓
Need Intelligence?
   ├── NO → Rule Signal
   └── YES → Analyst → Enriched Signal
```

高频行情路径仍然完全不调用模型。

详细见：`07_Roadmap_v0.5_Market_Intelligence.md`

---

## 6. v0.6 — Feedback / Tuning

目标：开始回答“哪些提醒真的有价值”。

记录：

- events generated；
- events clustered；
- alert candidates；
- alerts shown；
- signals opened；
- dismissed / muted；
- optional useful / not useful。

用这些数据调整 deterministic parameters 与 Intelligence Router，而不是让模型在线自改规则。

详细见：`08_Roadmap_v0.6_Feedback_and_Tuning.md`

---

## 7. v1.0 — Multi-Host

目标：证明 Core / Protocol 真正与宿主解耦。

至少：

```text
Cursor + 1 个非 VS Code 宿主
```

候选：DeepSeek Harness / ZCode。

```text
                   Market Core
                       │
                 Protocol DTO
                       │
              ┌────────┴────────┐
              │                 │
              ▼                 ▼
           Cursor          Second Host
           Adapter           Adapter
```

详细见：`09_Roadmap_v1.0_MultiHost.md`

---

## 8. Distribution 状态

### Completed

- Cursor Extension — v0.3；
- Python standalone JSONL daemon — v0.3；
- local VSIX packaging — v0.3。

### Future

- DSH adapter；
- ZCode adapter；
- MCP server；
- packaged/bundled Python runtime；
- Marketplace distribution。

---

## 9. 长期 Backlog

### Market

- 50 / 100 symbols；
- request batching；
- WebSocket provider；
- multi-source fallback；
- A / H / US expansion；
- full exchange calendar。

### Technical

- MACD；
- Bollinger Bands；
- ATR；
- volatility regime；
- correlation；
- sector relative strength。

### Intelligence

- News Agent；
- Sector Agent；
- Risk Agent；
- event memory；
- contextual explanation。

### UI

- stealth mode；
- multiple StatusBar presets；
- alert headline；
- signal timeline；
- diagnostics dashboard。

### Distribution

- Marketplace identity；
- bundled runtime；
- DSH / ZCode；
- MCP；
- signed release workflow。

---

## 10. 最终原则

> **高频数据处理由程序完成，低频复杂解释才交给模型；核心协议稳定，宿主只是 Adapter。**
