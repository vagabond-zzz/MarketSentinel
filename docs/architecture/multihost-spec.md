# Roadmap v1.0 — Multi-Host Architecture

> Goal: prove Market Sentinel Core is truly host-independent.

---

## 1. 目标

v1.0 至少支持：

```text
Cursor + 1 个非 VS Code 宿主
```

候选：

- DeepSeek Harness；
- ZCode。

不要求同时完成两个。

---

## 2. 已有基础

v0.3 已证明：

```text
Python Core
   ↓
Protocol DTO
   ↓
JSONL Protocol v1
   ↓
Cursor Host
```

v1.0 不重新设计 Core。

主要工作是验证第二个 Host 可以复用同一协议语义。

---

## 3. Host Contract

未来 Host abstraction 是概念接口，不等于 Wire Protocol。

建议：

```ts
export interface HostAdapter {
  updateState(state: MarketUIState): void;
  notifyAlert(alert: AlertCandidate): void;
  openDetails?(signalId?: string): void;
  dispose(): void;
}
```

重要：

```text
updateState
!=
notifyAlert
```

因此：

```text
active_signals
!=
new notification
```

禁止恢复成：

```ts
notify(signal: Signal)
```

因为 persistent signal 不是 alert edge。

---

## 4. Wire Protocol vs Host Adapter

```text
Wire Protocol
= Core ↔ Process boundary

Host Adapter
= Wire DTO ↔ Host API mapping
```

两者不要合并。

第二个 Host 不应 import Cursor implementation。

---

## 5. 共享能力

所有 Host 共享：

- Provider；
- Feed Health；
- Scheduler；
- Feature Engine；
- Event Engine；
- Signal Engine；
- Intelligence Router；
- Protocol semantics。

Host 只新增：

```text
Lifecycle Binding
Settings Binding
UI Binding
Notification Binding
```

---

## 6. Protocol Evolution

v1.0 允许 Protocol 演进，但必须有明确版本兼容策略。

原则：

- additive change 优先；
- breaking change 才升 protocol version；
- Host/Core handshake 明确拒绝不支持版本；
- core_version 不是 wire compatibility 判断。

---

## 7. Second Host MVP

第二个 Host 至少实现：

```text
spawn/connect
hello
set_watchlist
start
state
alert
pause/resume
shutdown
```

UI 不要求复制 Cursor StatusBar。

只要能表达：

- health；
- persistent state；
- alert edge；
- lifecycle。

---

## 8. Cross-Host Consistency

相同 Replay / live input 下：

```text
Core Event
Signal episode
Alert candidate
Feed Health
Scheduler state
```

必须与 Host 无关。

Cursor 与第二 Host 允许：

- 文案不同；
- UI 布局不同；
- notification style 不同。

不允许：

- Event threshold 不同；
- cooldown 不同；
- warming 不同；
- alert edge 语义不同。

---

## 9. Settings Contract

Host settings 可不同，但最终都映射到同一 Core command/DTO。

例如：

```text
watchlist
provider
replay path
intelligence enabled
```

Core 仍是业务限制权威。

---

## 10. Distribution

v1.0 需要明确：

### Cursor

已有 local VSIX；是否进入 Marketplace 单独决定。

### Second Host

使用其原生插件/扩展方式。

### Python Core

评估：

- developer checkout；
- bundled runtime；
- standalone packaged daemon。

但不要为了 distribution 改掉 Core architecture。

---

## 11. Multi-host Tests

至少：

### Protocol contract tests

同一 fixture：

- Cursor client；
- Second Host client。

### Replay consistency

同一 Replay：

```text
same accepted events
same signal updates
same alert candidates
```

### Lifecycle

- start；
- crash；
- reconnect；
- shutdown；
- no orphan。

---

## 12. Milestones

### M0 — Second Host selection

- DSH vs ZCode；
- capability audit；
- lifecycle / IPC constraints；
- no implementation first。

### M1 — Host-neutral adapter contract

- state；
- alert；
- settings；
- lifecycle。

### M2 — Second Host IPC client

- Protocol support；
- validation；
- request map。

### M3 — Second Host lifecycle

- connect/spawn；
- shutdown；
- recovery。

### M4 — Minimal UI

- health；
- state；
- alert。

### M5 — Cross-host parity tests

- Replay；
- alert semantics；
- feed health；
- scheduler。

### M6 — Packaging / release

- docs；
- distribution；
- version；
- migration notes。

---

## 13. v1.0 验收

- [ ] Core 无宿主依赖；
- [ ] Cursor 正常使用；
- [ ] 至少一个非 VS Code Host 可运行；
- [ ] Protocol compatibility 明确；
- [ ] persistent state / alert edge 语义一致；
- [ ] Event Rule 行为一致；
- [ ] Signal episode 行为一致；
- [ ] Feed Health 行为一致；
- [ ] Scheduler 行为一致；
- [ ] Intelligence Router 行为一致；
- [ ] Host UI 差异不影响 Core semantics。

---

## 14. 明确不做

v1.0 不以以下内容为必要条件：

- 三个 Host 全部完成；
- 100-symbol scale；
- cloud SaaS；
- auto trading；
- fully autonomous agents。
