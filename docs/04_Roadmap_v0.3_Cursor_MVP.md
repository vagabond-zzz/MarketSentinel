# Roadmap v0.3 — Cursor MVP

> 版本定位：把 Core 变成日常可用的 Cursor 插件。  
> 原则：UI 只消费协议，不反向污染 Core。

## 1. 目标

将：

```text
MarketUIState
Signal
MarketState
```

映射到：

```text
StatusBar
Hover / Tooltip
Commands
Simple Settings
```

## 2. Cursor Adapter

```text
apps/cursor-extension/
├── extension.ts
├── adapter/
│   ├── market-ui-adapter.ts
│   └── command-adapter.ts
├── statusbar/
├── hover/
└── settings/
```

Core 禁止 import `vscode`。

## 3. StatusBar 最小协议

先只定义状态：

```text
NORMAL
WARM
HOT
ALERT
STALE
```

不提前确定最终 icon / 文案 / 隐蔽样式。

## 4. Hover

第一版展示：

```text
Feed Status
Last Update
Monitored Symbols
HOT Symbols
Unread Signals
Top Signals
```

## 5. Commands

建议：

```text
Market Sentinel: Open Watchlist
Market Sentinel: Pause Monitoring
Market Sentinel: Resume Monitoring
Market Sentinel: Show Signals
Market Sentinel: Reset Alerts
Market Sentinel: Show Diagnostics
```

## 6. Settings

至少：

```text
watchlist
coldInterval
warmInterval
hotInterval
signalCooldown
enableHoverDetails
```

规则阈值可先通过配置文件调整，不要求全部 GUI 化。

## 7. Diagnostics

需要查看：

```text
Feed latency
Detection latency
Last provider error
Scheduler levels
Active events
Recent signals
Memory estimate
```

## 8. 交互原则

不做：

- 大面积闪烁；
- 高频 toast；
- 每个 Event 都通知；
- 持续抢占注意力。

信息层级：

```text
StatusBar → Hover → Detail
```

## 9. 验收

- [ ] Cursor 可安装；
- [ ] 加载 10 只股票；
- [ ] Core 持续运行；
- [ ] StatusBar 表达 NORMAL/WARM/HOT/ALERT/STALE；
- [ ] Hover 查看详情；
- [ ] Important Signal 可发现；
- [ ] Feed stale 明确展示；
- [ ] 插件关闭正确释放资源；
- [ ] UI 无 Feature/Event 业务判断。

## 10. UI Backlog

后续再优化：

- 隐蔽模式；
- 百分比模式；
- icon / emoji；
- 动态 headline；
- 多套 preset；
- 临时闪现后恢复；
- 详情 WebView。

优先级：**提醒可靠 > 视觉漂亮**。

## 11. Implementation status (v0.3)

| Milestone | Status |
|---|---|
| M0 Node / pnpm workspace | done |
| M1 Protocol v1 DTO / codec / mapping | done |
| M2 Python daemon JSONL transport | done |
| M3 TypeScript protocol + IPC client | done |
| M4 Cursor extension lifecycle | done |
| M5 Minimal StatusBar | done |
| M6 Hover | done |
| M7 Alert handling | done |
| M8 Host integration tests / packaging | done (Release Candidate; not tagged) |

v0.3 Host watchlist source of truth is `marketSentinel.watchlist` (settings). The daemon holds a non-persistent runtime Watchlist updated via `set_watchlist` and does not write `data/watchlist.json`.

M8 Release Candidate identity (local VSIX, not Marketplace):

```text
publisher: market-sentinel-local
name: market-sentinel
id: market-sentinel-local.market-sentinel
extensionKind: ["ui"]
```

`market-sentinel-local` is a developer/local publisher identifier. Changing it later changes the extension identifier. Python Core is not bundled; install still needs `coreRoot` + `uvPath`. Do not tag `v0.3.0` or enter v0.4 until a separate release audit.

