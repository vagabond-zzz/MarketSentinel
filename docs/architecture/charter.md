# Market Sentinel 项目任务书

> 工作名：Market Sentinel  
> 当前阶段：MVP / Phase 1  
> 目标宿主：Cursor 优先，后续兼容 DeepSeek Harness、ZCode 等终端  
> 核心原则：高频行情数据与低频智能分析彻底解耦

## 1. 项目目标

构建一个运行在开发终端中的轻量盯盘核心。首期最多监控 **10 只股票**，持续获取行情，通过价格、成交量与技术指标发现异常事件，并输出统一 `Signal` 给宿主 UI。

第一阶段不追求“AI 炒股”，而是优先做好稳定、低延迟、低资源占用的 **Market Event Engine**。

核心链路：

```text
Market Feed
    ↓
Market State / Ring Buffer
    ↓
Feature Engine
    ↓
Event Engine
    ↓
Dedupe / Cluster / Cooldown
    ↓
Signal Engine
    ↓
Host Adapter
    ↓
Cursor / DSH / ZCode UI
```

## 2. MVP 原则

1. 行情更新不调用 LLM；
2. 技术指标和事件检测全部本地执行；
3. Event 与 Signal 明确分层；
4. Core 不依赖 Cursor / VS Code API；
5. UI 只消费统一 `MarketUIState`；
6. 为 Agent 层预留接口，但 MVP Token 消耗为 0；
7. 为 DSH / ZCode 等宿主预留 Adapter 边界；
8. 状态栏视觉最后优化，不提前绑死核心协议。

## 3. MVP 非目标

暂不包含：

- News Agent；
- 财报、公告、基本面分析；
- 自动交易与下单；
- 买入/卖出建议；
- Level 2 / Order Book；
- 全市场扫描；
- 多 LLM Agent；
- 复杂 K 线终端；
- 云端同步。

## 4. Watchlist

第一版限制：

```text
Watchlist Limit: 10
```

支持：

- 添加/删除股票；
- 暂停/恢复监控；
- 保存本地 Watchlist；
- 启动时恢复配置；
- 单只股票独立维护 Scheduler 状态。

## 5. 核心架构

```text
┌────────────────────────────────────────────┐
│ Host Layer                                 │
│ Cursor / DSH / ZCode / CLI                 │
└────────────────────┬───────────────────────┘
                     │ MarketUIState
┌────────────────────▼───────────────────────┐
│ Signal Layer                               │
│ Dedupe / Cluster / Cooldown / Priority     │
└────────────────────┬───────────────────────┘
                     │ MarketEvent
┌────────────────────▼───────────────────────┐
│ Event Engine                               │
│ Price / Volume / Breakout / Momentum       │
└────────────────────┬───────────────────────┘
                     │ MarketFeatures
┌────────────────────▼───────────────────────┐
│ Feature Engine                             │
│ Returns / Volume Ratio / VWAP / EMA / RSI  │
└────────────────────┬───────────────────────┘
                     │ MarketSnapshot
┌────────────────────▼───────────────────────┐
│ Market Data Core                           │
│ Provider / Scheduler / Ring Buffer         │
└────────────────────────────────────────────┘
```

## 6. 核心数据协议

### 6.1 MarketSnapshot

```ts
export interface MarketSnapshot {
  symbol: string;
  price: number;
  open: number;
  high: number;
  low: number;
  prevClose: number;
  volume: number;
  turnover?: number;
  marketTimestamp: number;
  receivedTimestamp: number;
}
```

### 6.2 MarketFeatures

```ts
export interface MarketFeatures {
  symbol: string;
  priceChange: {
    m1: number;
    m5: number;
    m15: number;
    day: number;
  };
  volume: {
    ratio1m: number;
    ratio5m: number;
  };
  position: {
    dayRange: number;
  };
  technical: {
    vwap?: number;
    aboveVWAP?: boolean;
    ema5?: number;
    ema20?: number;
    rsi14?: number;
    breakDayHigh?: boolean;
    breakDayLow?: boolean;
  };
}
```

### 6.3 MarketEvent

`MarketEvent` 表示客观发生的市场事实，不包含投资建议。

```ts
export interface MarketEvent {
  id: string;
  symbol: string;
  type:
    | "rapid_move"
    | "volume_spike"
    | "breakout"
    | "vwap_cross"
    | "momentum"
    | "volatility";
  severity: 1 | 2 | 3 | 4 | 5;
  occurredAt: number;
  metrics: Record<string, number | boolean>;
  dedupeKey: string;
  ttlMs: number;
}
```

### 6.4 Signal

```ts
export interface Signal {
  id: string;
  eventIds: string[];
  symbol: string;
  priority: "info" | "notice" | "important" | "critical";
  title: string;
  summary: string;
  confidence?: number;
  generatedBy: "rule" | "agent" | "hybrid";
  createdAt: number;
  expiresAt?: number;
}
```

### 6.5 MarketUIState

```ts
export interface MarketUIState {
  status: "idle" | "active" | "alert" | "stale";
  unreadSignals: number;
  headline?: {
    symbol: string;
    text: string;
    severity: number;
  };
  hover: {
    marketStatus: string;
    monitoredSymbols: number;
    activeEvents: number;
    signals: SignalPreview[];
  };
}
```

## 7. 数据生命周期

```text
Raw Snapshot
    ↓
Validation
    ↓
Normalize
    ↓
Ring Buffer
    ↓
Feature Update
    ↓
Event Detection
```

Ring Buffer 第一阶段维护：

- 最近 30～60 分钟高频采样；
- 1 分钟窗口；
- 5 分钟窗口；
- 15 分钟窗口；
- 当日统计信息。

## 8. 分级更新策略

### 8.1 状态

| Level | 含义 | 初始建议刷新频率 |
|---|---|---:|
| COLD | 正常，无明显异动 | 10s |
| WARM | 轻度异动或接近条件 | 3s |
| HOT | 已出现/正在形成明显异动 | 1s |

刷新频率必须可配置。

### 8.2 升级条件

COLD → WARM：

- 1m / 5m 波动增加；
- 成交量开始放大；
- 接近日内高低点；
- 指标接近阈值。

WARM → HOT：

- 放量突破；
- 短时快速涨跌；
- 多指标同时触发；
- 高 severity Event。

### 8.3 防抖

建议：

```text
HOT minimum dwell: 30s
WARM minimum dwell: 60s
```

配合滞回阈值和无事件持续时间，避免状态频繁震荡。

## 9. Feature v1

必做：

- 1m / 5m / 15m 涨跌幅；
- 日内涨跌幅；
- 1m / 5m 成交量倍率；
- 日内高低点；
- 日内区间位置；
- VWAP；
- EMA5 / EMA20；
- RSI14。

后续候选：MACD、Bollinger、ATR、Realized Volatility。

## 10. Event Rules v1

建议首批 5～8 条：

1. `rapid_move`：短时快速涨跌；
2. `volume_spike`：成交量异常放大；
3. `price_volume_expansion`：量价同步扩张；
4. `day_high_breakout`：突破日内高点；
5. `day_low_breakdown`：跌破日内低点；
6. `vwap_cross`：穿越 VWAP；
7. `momentum`：动量增强；
8. `volatility_expansion`：波动率突然扩张。

Event Rule 全部 deterministic，Token = 0。

## 11. Signal Engine

```text
Event
 ↓
Dedupe
 ↓
Cluster
 ↓
Cooldown
 ↓
Priority
 ↓
Signal
```

目标：同一市场行为尽量只提醒一次，多种相关 Event 尽量聚合为一个 Signal。

## 12. 延迟指标

```ts
export interface EventTiming {
  marketTimestamp: number;
  receivedTimestamp: number;
  detectedTimestamp: number;
  notifiedTimestamp?: number;
}
```

计算：

```text
Feed latency      = received - market
Detection latency = detected - received
Signal latency    = notified - detected
Total latency     = notified - market
```

## 13. Feed Health

必须区分：

```text
LIVE
DELAYED
STALE
DISCONNECTED
```

核心不能在行情失效时继续表现为正常。

## 14. 性能目标

```text
监控股票：10
LLM Token：0
Feature + Event Detection：目标 < 100ms
规则计算：目标 < 50ms
正常 CPU：尽量 < 1~2%
内存：尽量 < 100MB
断流检测：必须有
Feed 恢复：必须自动
```

这些是工程目标，不是交易系统 SLA。

## 15. Trace

```ts
export interface SignalTrace {
  signalId: string;
  sourceEvents: string[];
  features: MarketFeatures;
  rulesTriggered: string[];
  createdAt: number;
}
```

用于：误报分析、阈值调参、未来 Agent Router、解释“为什么提醒”。

## 16. 推荐目录结构

```text
market-sentinel/
├── packages/
│   ├── core/
│   │   ├── market-data/
│   │   ├── scheduler/
│   │   ├── ring-buffer/
│   │   ├── features/
│   │   ├── events/
│   │   ├── signals/
│   │   └── protocol/
│   └── adapters/
├── apps/
│   ├── cli/
│   ├── cursor-extension/
│   ├── dsh-plugin/
│   └── zcode-plugin/
├── tests/
└── docs/
```

MVP 优先完成 `core + cli + cursor-extension`。

## 17. Host Adapter 原则

Core 禁止直接依赖 `vscode`。宿主只消费：

```text
MarketUIState
Signal
```

Cursor / DSH / ZCode 的差异只存在于 Adapter 与 UI Binding。

## 18. Agent 预留

MVP 不调用 Agent。

未来接口：

```ts
export interface IntelligenceProvider {
  analyze(input: IntelligenceInput): Promise<IntelligenceResult>;
}
```

默认先由规则式实现承担。后续只有 Significant Event 才允许进入 LLM。

## 19. MVP 验收

### 数据
- [ ] 稳定加载 10 只股票；
- [ ] 持续刷新；
- [ ] 断流可检测；
- [ ] 恢复后自动继续；
- [ ] Ring Buffer 正常。

### Feature
- [ ] 1m / 5m / 15m 涨跌；
- [ ] Volume Ratio；
- [ ] VWAP；
- [ ] EMA5 / EMA20；
- [ ] RSI14；
- [ ] 日内位置。

### Event / Signal
- [ ] 至少 5 条 Event Rule；
- [ ] severity；
- [ ] dedupe；
- [ ] cluster；
- [ ] cooldown；
- [ ] Signal trace。

### Scheduler
- [ ] COLD / WARM / HOT；
- [ ] 自动升级/降级；
- [ ] minimum dwell / hysteresis。

### Host
- [ ] CLI 可独立运行；
- [ ] Cursor 可加载 Core；
- [ ] Cursor 有最小状态展示；
- [ ] Hover 可展示基础信息。

## 20. 第一阶段成功定义

1. 10 只股票持续运行稳定；
2. 行情延迟可观测；
3. Event 检测快速；
4. 重复提醒得到控制；
5. Core 无 Cursor 依赖；
6. Token 消耗为 0；
7. 后续接 Agent 不需要重构 Core；
8. 后续接 DSH/ZCode 只需新增 Adapter/UI。
