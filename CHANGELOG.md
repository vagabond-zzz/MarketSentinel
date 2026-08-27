# Changelog

## v0.3 — in progress (`feat/v0.3-cursor-host`)

Python JSONL daemon, Protocol v1, and a vscode-free TypeScript IPC client / process manager (M3). No Cursor UI (M4+).

### M0 — Node / pnpm workspace

Root `package.json`, `pnpm-workspace.yaml`, and `apps/cursor-extension` skeleton with `pnpm test` / `lint` / `typecheck` / `build`. No StatusBar/Hover.

### M1 — Protocol v1 DTO / codec / mapping

Versioned JSONL envelope, explicit wire DTOs, and `MarketState` → DTO mapper. Core models are not `asdict`'d onto the wire.

### M2 — Python daemon transport

`market-sentinel daemon`: Windows-safe stdin, flushed JSONL stdout, stderr logging, daemon phase machine, runtime-only `set_watchlist`, command/tick lock, graceful shutdown. Integration test runs `uv run ... daemon`.

### M3 — TypeScript protocol guards, JSONL IPC client, process manager

Hand-written Protocol v1 guards (no zod), JSONL line decoder, `IpcClient` request map, and `ProcessManager` (`uv run --directory <coreRoot> ... daemon`, `shell: false`). Handshake is hello → set_watchlist → start. `active_signals` stay on state; alerts only come from `alert` messages. No `vscode` import in these modules.

## v0.2.0 — 2026-08-26

Market Event Engine: deterministic Features, six Event Rules, Dedupe / Cluster / episode-aware Cooldown, Signal lifecycle, COLD/WARM/HOT Runtime integration, CLI diagnostics, Replay E2E, and coverage/performance gates.

- Feature Engine: 1m/5m/15m change, volume ratio, EMA5/20, RSI14, VWAP, session high/low
- Six Event Rules: `rapid_move`, `volume_spike`, `price_volume_expansion`, `day_high_breakout`, `day_low_breakdown`, `vwap_cross`
- Dedupe / Cluster / episode-aware Cooldown (identity = Signal episode id)
- Signal lifecycle (90s look-back episode, reversal isolation, `active_signals` from live composer state)
- COLD/WARM/HOT Runtime integration (`WarmingPolicy` + `EngineTickResult`)
- CLI diagnostics (`ACTIVE SIGNALS` / `EVENTS THIS TICK` / `ALERTS THIS TICK`, `run --once`, `run --verbose`)
- Replay E2E scenarios (normal, WARM precursor, rapid move, volume spike, price+volume+breakout, episode, reversal, persistence, alert edge)
- Coverage gate (`fail_under = 85`) and 10-symbol engine regression budget

Still out of scope: Cursor Host, live HTTP provider, `notified_timestamp`, LLM / News / MCP, auto-trading.

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

## M7 — Runtime Integration

`MarketEngine.tick()` now runs the v0.2 pipeline after fetch/health. Core logic stays in the steppable `async tick()`; there is no `while True` + `sleep()` inside the engine. CLI v2, Replay/perf docs wrap-up, and Cursor are not in this milestone.

### Data flow

```text
due → fetch → normalize → ring buffer → feed health
  → FeatureEngine.compute → SignalPipeline.process → WarmingPolicy
  → AdaptiveScheduler.set_level → MarketState projection → EngineTickResult
```

### Durable state vs tick output

- `MarketState` is persistent: latest snapshot, scheduler level, feed status/latency/age, latest `MarketFeatures`, and `active_signals` (multiple episodes; not `last_signal`).
- `EngineTickResult` / `SymbolTickResult` are this tick's edge-triggered output (`accepted_events`, `signal_updates`, `traces`, `alert_candidates`, level before/after).

### Alert candidates

- `alert_candidates` are Signals that newly gained reminder eligibility on this tick.
- An active Signal remaining in `MarketState` does not re-emit an alert candidate on a quiet follow-up tick.

### Cooldown vs attention

- Cooldown may suppress `alert_candidates` while `signal_updates` still refresh `active_signals`.
- Expired episodes are pruned from composer state and therefore from `active_signals`.
- `WarmingPolicy` maps current features/events to a `LevelRequest`. Notification cooldown is not an input; a suppressed alert can remain HOT.
- Engine applies `AdaptiveScheduler.set_level` without `force`, so existing dwell still blocks immediate downgrade.

### Failure isolation

- Feature or pipeline errors are logged with symbol and stage, then other symbols continue.
- The failed symbol keeps its last known safe features/signals.

### API

| Item | Change |
|---|---|
| `MarketState` | `features`, `active_signals` |
| `EngineTickResult` / `SymbolTickResult` | new tick output |
| `MarketEngine.tick()` | returns `EngineTickResult` |
| `WarmingPolicy` / `LevelRequest` | new orchestration boundary |
| CLI v2 / Cursor / `notified_timestamp` | not implemented |

## M8 — CLI v2 / Diagnostics

Diagnostics CLI for Core acceptance and as a reference before Cursor Host work. Feature math, Event thresholds, Dedupe, Cluster, Cooldown, Signal episodes, Scheduler dwell, and `MarketEngine` pipeline are unchanged.

### Three information planes

- Persistent state comes from `MarketState` (price, level, feed, features, `active_signals`).
- `EVENTS THIS TICK` comes from `SymbolTickResult.accepted_events` only.
- `ALERTS THIS TICK` comes from `SymbolTickResult.alert_candidates` only.

An active episode remaining in `MarketState.active_signals` is not re-printed as a new alert on a quiet follow-up tick.

### Display

- Missing values render as `N/A` (never `0`, `0.00%`, or `1.00x`).
- CLI formats decimal fractions as percents (`0.006` → `+0.60%`) and volume ratios as `1.80x`.
- Multiple live episodes (UP / DOWN / VWAP / NONE) are all listed under `ACTIVE SIGNALS`.
- ASCII-only chrome; no color, rich, or textual.

### Commands

- `run --once` still ticks, prints, and exits.
- `run --verbose` adds `Scheduler: COLD -> HOT`, timestamps, and ids.

## M9 — v0.2 Release Candidate

Replay fixtures, end-to-end scenarios, a loose performance check, coverage gate, and documentation wrap-up. Feature math, the six Event thresholds, Dedupe, Cluster, Cooldown, Signal episodes, and Scheduler dwell are unchanged. No v0.3, Cursor, merge to main, or `v0.2.0` tag.

### Replay

Deterministic JSONL under `tests/fixtures/` (`normal_market`, `pre_signal_warm`, `rapid_move`, `volume_spike`, `price_breakout`, `price_volume_breakout`, `episode_lifecycle`, `reversal`, `tape_then_vwap`). Scenarios run `ReplayProvider → MarketEngine.tick() → Feature → Event → Signal → Scheduler → MarketState`.

### Runtime isolation

If a due symbol gets no fresh snapshot this tick (timeout, missing quote), the engine does not re-run Feature/Event/Signal on stale buffer data. Last safe `features` / `active_signals` stay; tick output has empty events and alerts.

### Performance

10 symbols × 120 snapshots through the full engine tick path must finish in under 8s (observed ~0.95s uninstrumented, ~3.4s under coverage). Feature-only 10×120 remains under 1s.

### Coverage

`[tool.coverage.report] fail_under = 85` is enabled for `uv run pytest --cov=market_sentinel`.
