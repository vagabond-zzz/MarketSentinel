# Roadmap v0.4 — Live Market Data & Feed Reliability

> Status: **Tencent in-session live gate PASSED 2026-08-28 morning session.** Sina one-shot cross-check PASSED. Longbridge remains optional and is **not** a release blocker. Tushare is **excluded**. Core MarketProvider wiring is unchanged (no architecture redesign yet).
>
> Token target: **0**
>
> See `docs/12_v0.4_Longbridge_Provider_Setup.md` and `docs/13_v0.4_Release_Candidate.md`.
> Do not tag `v0.4.0` until the remaining Core-wiring / release steps are explicitly completed.

---

## 1. 目标

v0.4 的唯一主目标：

> **让至少一个真实市场数据源可靠地穿过现有 Core → Protocol → Cursor 全链路。**

这不是 Intelligence 版本，也不是 UI 版本。

```text
Live Market Source
       ↓
Provider Adapter
       ↓
Normalization
       ↓
MarketSnapshot
       ↓
MarketEngine
       ↓
Feature / Event / Signal
       ↓
Protocol v1
       ↓
Cursor Host
```

---

## 2. 不变的架构边界

v0.4 不修改以下责任分界：

### Provider

负责：

- 第三方 API / feed 接入；
- source field mapping；
- source semantics normalization；
- provider-specific error translation。

### Core

继续负责：

- Ring Buffer；
- Feature；
- Event；
- Signal；
- Scheduler；
- Feed Health。

### Cursor Host

继续只负责：

- child lifecycle；
- IPC；
- StatusBar；
- Hover；
- Host presentation。

Host 不解析第三方行情响应。

---

## 3. Live Provider MVP

**2026-08-28 plan change:** Longbridge credentials and extra realtime permissions (Tushare) must not block this release. The live **gate** uses the existing Tencent `qt.gtimg.cn` probe as primary, with a one-shot Sina cross-check. Core `MarketProvider` wiring is **not** redesigned in this step. Longbridge code stays in-tree as optional.

v0.4 只要求：

> **一个可验证、可测试的真实行情 Provider。**

不要同时做多个供应商。

Provider 必须最终归一到现有 `MarketSnapshot` 语义。

至少：

```text
symbol
price
volume
turnover?
high?
low?
market_timestamp
received_timestamp
```

### Volume 语义

Core 冻结：

```text
MarketSnapshot.volume = session cumulative volume
```

如果 source 给的是：

- per-trade volume；
- per-bar volume；
- lot；
- shares；
- source-specific cumulative field；

必须在 Provider boundary 明确转换。

不能把不兼容语义直接送进 Feature Engine。

### Turnover

若源提供可靠的 session cumulative turnover：

```text
turnover = normalized cumulative turnover
```

否则：

```text
None
```

禁止为了 VWAP 填假值。

---

## 4. Provider Contract

优先保持现有 Provider Protocol 简单。

Provider 层至少需要能够表达：

```text
success quote
symbol unavailable
partial quote
timeout
transport error
rate limited
provider unavailable
```

错误进入 Core 后必须被转成 feed-health / runtime failure 语义，而不是伪造 snapshot。

---

## 5. Timeout / Disconnect / Recovery

至少覆盖：

### Timeout

```text
fetch timeout
→ no new snapshot
→ no feature/event re-run on stale buffer
→ feed health degrades
```

### Temporary disconnect

```text
LIVE
→ failures
→ DELAYED / STALE / DISCONNECTED
```

### Recovery

```text
DISCONNECTED
→ valid fresh quote
→ LIVE
```

恢复后：

- 不能重放旧 Alert；
- 不能因为断线期间的累计变化制造伪造 minute volume；
- Scheduler 状态按现有策略恢复。

---

## 6. Timestamp 规则

必须区分：

```text
market_timestamp
received_timestamp
```

### market_timestamp

用于：

- rolling anchor；
- Event timing；
- bar bucket；
- session boundary。

### received_timestamp

用于：

- transport latency；
- diagnostics；
- feed health。

禁止用本地收到时间代替真实市场时间计算 1m / 5m / 15m move。

---

## 7. Out-of-order / Duplicate Quote

v0.4 必须明确：

### Duplicate timestamp

允许安全更新/忽略，但不能制造重复 Event。

### Older market timestamp

```text
new.market_timestamp < latest.market_timestamp
```

Core 不得回退 rolling state。

至少：

- suppress / ignore；
- log diagnostics；
- 不 rewind dedupe/cooldown。

---

## 8. Session & Cumulative Reset

v0.4 继续以当前 A/H MVP session 规则为基线，不一次解决全球市场 calendar。

必须验证：

- overnight；
- new session cumulative volume reset；
- lunch / long gap；
- previous-session reference；
- long gap 不跨段算 rolling anchor。

关键 invariant：

```text
new session volume reset
!=
negative volume spike
```

以及：

```text
overnight price gap
!=
1m rapid move
```

---

## 9. Rate Limit

第一版不要设计复杂 distributed rate limiter。

至少需要：

- provider-specific minimum request interval；
- watchlist ≤ 10；
- 明确超限错误；
- 不在 Host 复制 provider 限流规则。

若真实 Provider 需要 batching，可在 Provider 内实现小范围 batching。

---

## 10. Cursor Host

尽量保持 Protocol v1 backward compatible。

Provider 从 fake/replay 增加到 live 后，Host 仍然只消费：

```text
state
alert
```

MVP settings 可增加真实 provider enum / provider-specific minimal settings。

不要在 StatusBar 里显示 API 原始字段。

---

## 11. Secrets / Credentials

若真实 Provider 需要 API Key：

- 不写入仓库；
- 不写进 Protocol DTO；
- 不写进 Output Channel；
- 不写进 VSIX；
- 不硬编码到 settings default。

v0.4 优先选择安全、最少凭据复杂度的接入方式。

---

## 12. Observability

至少记录：

```text
provider request success/failure
latency
timeout count
last market timestamp
last received timestamp
feed status transition
out-of-order count
reconnect count
```

不要记录大规模 tick payload。

---

## 13. Tests

### Unit

- source → MarketSnapshot mapping；
- volume semantics；
- missing turnover → None；
- malformed response；
- timestamp parsing；
- out-of-order handling；
- session reset。

### Integration

- live-provider adapter with recorded/fake transport；
- timeout → STALE；
- recover → LIVE；
- no forged Event during failure；
- cumulative reset safe；
- Cursor Host sees expected state transitions。

### Optional live smoke

真实网络测试默认不要进入普通 CI。

应作为显式：

```text
live smoke
```

由开发者手动运行。

---

## 14. Milestones

### M0 — Provider source audit

- 选择一个真实数据源；
- 确认字段、频率、限制、时间戳、volume semantics；
- 不编码。

### M1 — Live Provider adapter

- transport；
- response parser；
- normalized snapshot。

### M2 — Provider reliability

- timeout；
- malformed response；
- retry/recovery boundary；
- rate-limit handling。

### M3 — Timestamp / session hardening

- out-of-order；
- duplicate；
- reset；
- long gap。

### M4 — Runtime integration

- existing Engine；
- feed health；
- scheduler；
- no forged Event。

### M5 — Cursor configuration

- provider selection；
- minimal provider settings；
- diagnostics。

### M6 — Live smoke / regression

- real-data manual smoke；
- Fake / Replay regression；
- performance sanity。

### M7 — Release prep

- docs；
- tests；
- version；
- VSIX；
- tag only after audit。

---

## 15. v0.4 验收

- [ ] 至少一个真实行情 Provider；
- [ ] 正常行情 Token = 0；
- [ ] 10-symbol watchlist 可运行；
- [ ] Provider 语义在 boundary 被 normalize；
- [ ] timeout 不制造新 Event；
- [ ] disconnect → STALE/DISCONNECTED；
- [ ] reconnect → LIVE；
- [ ] out-of-order quote 不 rewind state；
- [ ] new-session cumulative reset 安全；
- [ ] long gap 不制造短周期假 move；
- [ ] Fake / Replay 全回归；
- [ ] Cursor Host 不复制 Provider 逻辑；
- [ ] Protocol v1 尽量保持兼容；
- [ ] 无 LLM 调用。

---

## 16. 明确不做

v0.4 不做：

- Intelligence Router；
- LLM；
- News Agent；
- WebView；
- multi-host；
- 50/100 symbols；
- 多 provider 自动 failover；
- 完整全球 exchange calendar；
- 自动交易。
