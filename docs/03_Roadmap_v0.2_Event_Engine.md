# Roadmap v0.2 — Feature / Event / Signal Engine

> 版本定位：真正开始“盯盘”。  
> Token：0  
> 核心目标：从行情中发现少量高价值 Event，并控制提醒噪声。

## 1. 数据链路

```text
Snapshot
   ↓
Feature Engine
   ↓
Event Rules
   ↓
MarketEvent
   ↓
Dedupe
   ↓
Cluster
   ↓
Cooldown
   ↓
Signal
```

## 2. Feature Engine

### Price

- 1m / 5m / 15m change；
- day change；
- day range position。

### Volume

- 1m volume ratio；
- 5m volume ratio。

### Technical

- VWAP；
- EMA5；
- EMA20；
- RSI14；
- Day High / Day Low。

原则：纯函数优先、可单测、不访问 UI、不调用 Agent、不直接通知。

## 3. Event Rules v1

1. `rapid_move`
2. `volume_spike`
3. `price_volume_expansion`
4. `day_high_breakout`
5. `day_low_breakdown`
6. `vwap_cross`
7. `momentum`
8. `volatility_expansion`

## 4. Severity

```text
1 = weak
2 = mild
3 = notable
4 = strong
5 = exceptional
```

示例：

```text
单一 volume spike → 2
volume + price move → 3
volume + breakout + rapid move → 4
```

## 5. Dedupe

建议：

```text
dedupeKey = symbol + eventType + direction + timeBucket
```

目标：同一市场行为尽量只产生一个 Event。

## 6. Cluster

短时间内：

```text
volume_spike
rapid_move
day_high_breakout
```

可聚合成一个“量价突破”类 Signal，但不表达买卖建议。

## 7. Cooldown

```ts
interface CooldownPolicy {
  eventType: string;
  cooldownMs: number;
}
```

不同 Event 使用不同 cooldown；更高 severity 可以覆盖旧事件。

## 8. Signal Composer

第一版规则式生成：

```text
Title: 腾讯控股出现明显量价异动
Summary: 5 分钟 +1.8%，成交量 2.6×，突破日内高点
```

必须标记：

```text
generatedBy: rule
```

## 9. Trace

保存：

- source events；
- triggered rules；
- feature snapshot；
- timings。

## 10. Scheduler 联动

```text
mild precursor
COLD → WARM

strong precursor / event
WARM → HOT
```

加入 `pre-signal warming`，在事件完全形成前提前升频。

## 11. CLI v2

```text
00700.HK HOT
price      602.50
5m         +1.82%
volume     2.84x
VWAP       ABOVE

EVENTS
[3] volume_spike
[4] breakout

SIGNAL
[IMPORTANT] 放量突破
```

## 12. 观测指标

```text
raw events / hour
deduped events / hour
clusters / hour
signals / hour
average detection latency
average signal latency
```

## 13. 验收

- [x] Feature Engine 单测；
- [x] 至少 5 条 Event Rule；
- [x] severity 可解释；
- [x] dedupe；
- [x] cluster；
- [x] cooldown；
- [x] Signal；
- [x] Scheduler 可被 Event 驱动；
- [x] Token = 0；
- [x] CLI 展示完整 Feature → Event → Signal。

## 14. Implementation status (v0.2 RC)

M9 completes the v0.2 Release Candidate on `feat/v0.2-event-engine`. This does not start v0.3.

| Milestone | Status |
|---|---|
| M1 Domain / provider contract (v0.1 carry-forward) | done |
| M2 Runtime tick / scheduler / feed health (v0.1) | done |
| M3 Feature Engine | done |
| M4 Event rules (six) | done |
| M5 Dedupe + cooldown | done |
| M6 Cluster + Signal composer | done |
| M6.1 Signal lifecycle | done |
| M6.2 Episode-aware cooldown / NONE attribution | done |
| M7 Runtime Integration | done |
| M8 CLI v2 diagnostics | done |
| M9 Replay / E2E / perf / coverage gate / docs | done |

Not in v0.2: Cursor Host, TypeScript, live HTTP provider, `notified_timestamp`, LLM / News / MCP, merge to main, `v0.2.0` tag.
