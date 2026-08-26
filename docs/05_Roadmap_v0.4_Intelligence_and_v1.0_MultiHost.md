# Roadmap v0.4 → v1.0 — Intelligence & Multi-Host

> v0.4 开始引入有限智能层；v1.0 验证跨宿主架构。

# Part A — v0.4 Market Intelligence

## 1. 目标

Agent 不参与行情刷新。

只有 Significant Event / Event Cluster 才可能进入 Intelligence Router。

```text
Event Cluster
    ↓
Rule Filter
    ↓
Need Intelligence?
   ├── NO → Rule Signal
   └── YES → LLM Analyze → Enriched Signal
```

## 2. Token 原则

正确：

```text
Token Cost ≈ significant event count × tokens per analysis
```

禁止：

```text
symbols × refresh frequency × time
```

## 3. LLM 输入压缩

模型只读结构化 Feature / Event 摘要，不读大量原始 tick/K 线。

示例：

```json
{
  "symbol": "00700.HK",
  "event": "price_volume_breakout",
  "priceChange5m": 1.8,
  "volumeRatio5m": 2.6,
  "breakDayHigh": true,
  "aboveVWAP": true,
  "rsi14": 68
}
```

## 4. LLM 输出

只回答：

1. 是否值得提醒；
2. 主要异常原因；
3. confidence；
4. 简短摘要。

建议输出不超过约 100 tokens。

## 5. 第一个 Agent

不真正做多 Agent，只实现：

```text
Supervisor / Analyst
```

逻辑上的 Price / Volume / Technical Agent 继续由 deterministic module 实现。

## 6. Failure Fallback

Agent 超时/失败：

```text
fallback → Rule Signal
```

市场事件不能因为模型不可用而丢失。

## 7. v0.4 验收

- [ ] Agent 只由 Significant Event 触发；
- [ ] 正常行情 Token = 0；
- [ ] Agent Failure 有 fallback；
- [ ] 每个 Event Cluster 默认最多一次 LLM 调用；
- [ ] 不发送大规模原始行情；
- [ ] Agent latency 单独统计；
- [ ] Rule Signal / Agent Signal 可区分。

# Part B — v0.5 Feedback / Tuning

记录：

```text
Events generated
Events clustered
Signals shown
Signals opened
Signals dismissed
Signals muted
```

可选反馈：

```text
Useful / Not Useful
```

据此调：rule threshold、cooldown、severity、cluster window、Router、HOT/WARM 策略。

# Part C — v1.0 Multi-Host

## 1. 目标

至少支持：

```text
Cursor + 1 个非 VS Code 宿主
```

候选：DeepSeek Harness / ZCode。

## 2. Host Contract

```ts
export interface HostAdapter {
  updateUI(state: MarketUIState): void;
  notify(signal: Signal): void;
  openDetails?(signalId?: string): void;
  dispose(): void;
}
```

## 3. 多宿主原则

不复制 Core，只新增：

```text
Host Adapter
UI Binding
Settings Binding
Lifecycle Binding
```

共享：Provider、Scheduler、Feature Engine、Event Engine、Signal Engine、Intelligence Router、Protocols。

## 4. v1.0 架构

```text
                    Market Core
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
     Cursor            DSH             ZCode
     Adapter           Adapter          Adapter
```

## 5. v1.0 验收

- [ ] Core 无宿主依赖；
- [ ] Cursor 正常使用；
- [ ] 至少一个其他宿主运行；
- [ ] Signal 行为一致；
- [ ] Feed Health 行为一致；
- [ ] Scheduler 行为一致；
- [ ] 换宿主不影响 Event Rule；
- [ ] 换宿主不影响 Intelligence Router。

# 长期 Backlog

### Market
- 50/100 symbols；
- batching；
- WebSocket provider；
- 多数据源 fallback；
- A/H/美股适配；
- market calendar。

### Technical
- MACD；
- Bollinger；
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
- 隐蔽模式；
- 多种状态栏 preset；
- alert headline；
- signal timeline；
- diagnostics dashboard。

### Distribution
- Cursor extension；
- DSH plugin；
- ZCode plugin；
- MCP server；
- standalone daemon。

# 版本总览

| Version | 核心目标 | Token |
|---|---|---:|
| v0.1 | 行情 Core / Ring Buffer / Scheduler | 0 |
| v0.2 | Feature / Event / Signal | 0 |
| v0.3 | Cursor MVP | 0 |
| v0.4 | Intelligence Router / 单 Agent | 极低 |
| v0.5 | Feedback / Tuning | 低 |
| v1.0 | Multi-Host | 视配置 |

最终原则：**高频数据处理由程序完成，低频复杂解释才交给模型；核心协议稳定，宿主只是 Adapter。**
