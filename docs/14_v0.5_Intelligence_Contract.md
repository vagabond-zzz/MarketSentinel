# v0.5 M0 — Intelligence Contract

> Status: **contract still the v0.5 source of truth.** Package versions **0.5.0**. Protocol v1 is additive. Default tests do not call a model.
>
> Baseline branch: `feat/v0.5-market-intelligence` from v0.4 live-gate checkpoint `6980371`.
>
> v0.4 remains **live gate passed / RC baseline**, not a tagged `v0.4.0`. Tencent/Sina stay probes. Longbridge stays optional. This document does not close v0.4 Core-wiring.

---

## 1. Architecture

```text
Market Provider
    ↓
Normalization
    ↓
Feature
    ↓
Event
    ↓
Signal Episode          ← deterministic Rule Signal (unchanged)
    ↓
Deterministic Intelligence Router
    ├── NO  → original Rule Signal
    └── YES → async Intelligence sidecar
                    ↓
              optional IntelligenceAnnotation (by signal_id)
```

`Signal` is not an LLM object. Annotation lives in a separate registry keyed by `signal_id`.

## 2. Types

| Type | Role |
|---|---|
| `IntelligenceInput` | Compressed facts for Router / model |
| `IntelligenceAnnotation` | Model output attached by `signal_id` |
| `IntelligenceResult` | Status + annotation + fallback + latency counters |
| `IntelligenceStatus` | `not_requested` / `queued` / `running` / `enriched` / `fallback` |
| `FallbackReason` | Why a call was skipped or failed |
| `EpisodeCallBudget` | Default max 1 call; escalation recall **off** |

## 3. Model payload allowlist

Only these keys may be sent to a model:

```text
signal_id, symbol, family, direction, priority, event_types,
change_1m, change_5m, volume_ratio_5m, above_vwap, rsi14, day_range_position
```

Never sent: `SignalTrace`, `event_ids`, raw ticks, RingBuffer, workspace, Cursor conversation, secrets, `api_key`.

## 4. Episode budget

- Default: one model call per `signal.id`.
- A later priority escalation does **not** get a second call unless `allow_escalation_recall=True`.
- Host unread / toast / click / hover cannot create budget.

## 5. Invariants

High-frequency market path does not call a model. Token = 0 on ordinary tape. Rule Signal remains the fact source. Model failure cannot drop the signal.

## 6. Episode invalidation

`compress_intelligence_input(..., expired=)` is not a constant. An episode is expired when it is absent from the current active set, or when `Signal.expires_at` has passed.

Queued sidecar work is generation-invalidated when the episode retires:

```text
queued work + episode inactive before provider.complete
→ provider is not called
→ stale_discard += 1
→ registry is not resurrected
```

In-flight work is best-effort cancelled. If the transport cannot abort an already-issued HTTP request, that call may still consume tokens. The completed result must not reattach an annotation:

```text
in-flight + episode inactive
→ best-effort task cancel
→ if a result still arrives, it is discarded
→ registry is not resurrected
```

Call-budget / generation / pending maps are forgotten only after `pending == 0` for a retired id, so queued or in-flight work cannot become valid again by a premature `dict.pop`.

## 7. Output policy

The parser is deterministic fail-closed. Actionable trading instructions (buy/sell/hold, 持有/减持, 止损, 目标价, stop loss, target price, …) are `IntelligenceMalformedError`. Descriptive tape observation is allowed. System prompt is not the control.

## 8. Sidecar availability

Intelligence bootstrap/auth/provider failure logs a WARNING on stderr (secrets redacted) and returns `None`. Deterministic Core continues Rule-only. stdout remains Protocol JSONL only.

## 9. Secret handling

Coordinator fallback logs pass exception text through `redact_secrets`. Adapter HTTP errors stay generic and do not include the API key or provider body. Keys come from the environment only.
