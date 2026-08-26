# Roadmap v0.1 — Core Foundation

> 版本定位：把“行情持续流入并形成可计算状态”做稳定。  
> Token：0  
> UI：只做 CLI 调试界面。

## 1. 版本目标

```text
Provider
  ↓
Scheduler
  ↓
Snapshot Normalize
  ↓
Ring Buffer
  ↓
Market State
  ↓
CLI
```

重点：数据正确、状态稳定、时间戳完整、刷新机制可控。

## 2. Scope

必做：

- 10 只股票 Watchlist；
- `MarketProvider` 抽象；
- 第一套行情 Provider；
- Snapshot 标准化；
- Ring Buffer；
- 时间窗口查询；
- COLD/WARM/HOT Scheduler 骨架；
- Feed Health；
- CLI；
- 基础日志/metrics。

暂不做：LLM、News、Event Cluster、最终状态栏、多宿主。

## 3. M0 — 项目骨架

建立：

```text
packages/core
apps/cli
apps/cursor-extension
tests
docs
```

定义：

```text
MarketSnapshot
MarketState
WatchItem
SchedulerState
```

### Exit Criteria

- [ ] TypeScript 可构建；
- [ ] Core 不依赖宿主 API；
- [ ] CLI 可引用 Core。

## 4. M1 — Market Provider

```ts
export interface MarketProvider {
  fetchQuotes(symbols: string[]): Promise<MarketSnapshot[]>;
}
```

处理：失败、超时、字段缺失、无效 symbol、休市、时间戳异常。

### Exit Criteria

- [ ] 10 只股票可批量获取；
- [ ] Snapshot 字段统一；
- [ ] Provider 异常不导致主进程退出。

## 5. M2 — Ring Buffer

每只股票维护最近约 60 分钟滚动数据。

接口：

```text
getLatest()
getWindow(duration)
getSince(timestamp)
```

### Exit Criteria

- [ ] 10 只股票运行 1 小时无明显内存增长；
- [ ] Window Query 正确；
- [ ] 时间顺序正确。

## 6. M3 — Adaptive Scheduler

初始：

```text
COLD: 10s
WARM: 3s
HOT: 1s
```

支持：

```text
setLevel(symbol, level)
getLevel(symbol)
minimum dwell
```

### Exit Criteria

- [ ] 单只股票可动态调整刷新频率；
- [ ] 不出现频繁抖动；
- [ ] 10 只股票独立维护状态。

## 7. M4 — Feed Health

支持：

```text
LIVE / DELAYED / STALE / DISCONNECTED
```

记录：

```text
marketTimestamp
receivedTimestamp
feedLatency
lastUpdateAge
```

### Exit Criteria

- [ ] 人为断网后进入异常状态；
- [ ] 恢复后自动回到 LIVE；
- [ ] 状态变化可订阅。

## 8. M5 — CLI

示例：

```text
MARKET SENTINEL
Feed: LIVE
Watchlist: 10

00700.HK   602.50  +1.26%  WARM   age 0.8s
600519.SH  1482.30 +0.42%  COLD   age 1.1s
```

### Exit Criteria

- [ ] 不依赖 Cursor 可观察 Core；
- [ ] 可见 Scheduler 状态；
- [ ] 可见行情延迟。

## 9. 测试

至少覆盖：

- Provider normalize；
- Ring Buffer 边界；
- Window Query；
- Scheduler transition；
- Feed stale detection；
- Provider failure recovery。

## 10. Done Definition

```text
10 stocks
stable market stream
working ring buffer
adaptive scheduler skeleton
feed health
CLI
0 token
```
