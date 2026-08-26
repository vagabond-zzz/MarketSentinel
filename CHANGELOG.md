# Changelog

## M6.1 — Signal Lifecycle & Pipeline Semantics

Hardening of Signal episode identity, pipeline batching, cooldown vs. Core state, and directional clustering. Event Rule thresholds, Feature Engine, Scheduler, and `MarketEngine` are unchanged. No M7 Runtime Integration.

### Signal episode lifecycle

- A Signal ID is one look-back-continuous **episode**, not a permanent `(symbol, lineage)` slot.
- Reuse ID and `signal_created_timestamp` only while the active episode’s last `market_timestamp` is still inside the 90s look-back.
- After look-back continuity breaks (e.g. volume/rapid at t=100/110, then rapid at t=300): new ID and new `signal_created_timestamp`.
- Composer active state is pruned to live episodes (bounded).

### Pipeline

- `SignalPipeline.process` returns `SignalPipelineResult` instead of `(events, Signal | None, Trace | None)`.
- One Feature snapshot: detect all → dedupe all → compose accepted events as a batch → one cooldown check per **final** episode Signal.
- Same tick `rapid_move` + `volume_spike` + `price_volume_expansion` yields **one** tape Signal whose `event_ids` include all three (no intermediate two-event Signal).
- Tape and VWAP lineages in the same tick are both preserved in `signal_updates` / `traces` / `alert_candidates`.

### Cooldown vs. Core state

- `signal_updates` / `traces` always reflect the latest composed Signal (including breakout merged into an existing IMPORTANT `price_volume` episode).
- `alert_candidates` is the cooldown-filtered subset used for future Host alerts.
- `alert_candidate != notified`. v0.2 still has no `notified_timestamp`.

### Direction

- `EventDirection.NONE` (volume spike) may join an UP or DOWN episode.
- UP and DOWN directional events never share the same Signal episode; a later DOWN move starts a new episode.
- `Signal.direction` and `SignalTrace.direction` were added so Core can store both UP and DOWN episodes.

### Dedupe

- Incoming `market_timestamp` earlier than the stored record is ignored. Higher severity cannot rewind the dedupe timestamp.
- `elapsed == ttl` remains allowed.

### Domain / API

| Item | Change |
|---|---|
| `Signal` | added `direction: EventDirection` |
| `SignalTrace` | added `direction: EventDirection` |
| `SignalPipelineResult` | new (`accepted_events`, `signal_updates`, `traces`, `alert_candidates`) |
| `SignalComposer.consume_batch` / `active_signals` | new |
| `EventDeduper` | reject timestamp rewind |
| Rules / Feature Engine / Scheduler / Runtime | not modified |

## M6.2 — Episode-aware cooldown and NONE attribution

Small correction before Runtime Integration. Event Rule thresholds, Feature Engine, and `MarketEngine` are unchanged.

### Cooldown identity

- Cooldown keys on `signal.id` (one market episode), not `symbol + family`.
- Same episode: NOTICE emit → NOTICE suppress → IMPORTANT escalation emit.
- After an episode ends, a new Signal with the same symbol/family/priority gets a first alert.
- An UP → DOWN reversal (new Signal ID) has independent first-alert eligibility.
- v0.2 does not add a second family-level rate limiter.

### NONE attribution

- `EventDirection.NONE` is assigned to at most one active Signal episode.
- Unique UP or DOWN tape event in the current batch: NONE follows that batch direction.
- No batch direction, and look-back/live state has exactly one compatible directional tape episode: NONE may join it.
- Active UP and DOWN with no unique target: do not guess; keep/create a standalone NONE episode.
- Invariant: one `MarketEvent` ID belongs to at most one active Signal.
