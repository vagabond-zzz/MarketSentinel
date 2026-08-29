# Changelog

## Unreleased — v0.6.5 UX polish (no version bump)

Host daily-usability polish on `feat/v0.6.5-ux-polish`. Package stays **0.6.0**. Protocol stays **1** (additive optional wire fields only). Market semantics unchanged. **Not merged. Not tagged. Not pushed.**

### Added

- CLI `--intelligence` / `--no-intelligence` (explicit flag > `MARKET_SENTINEL_INTEL_ENABLED` > default off)
- Cursor settings: `marketSentinel.intelligence` (`off` / `on` / `inherit`, default `off`), `symbolNames`, `symbolDisplay`, `statusBarMaxSymbols`
- Command Palette: Add Symbol, Remove Symbol, Manage Watchlist (Workspace `marketSentinel.watchlist`; no sync with `data/watchlist.json`)
- StatusBar quote line with Codicons, no error/warning background, max 2 symbols + overflow
- Hover sections: connection / feed / AI status, day change, rule vs AI, grouped 1m/5m/15m metrics
- Replay EOF: `replay_complete` additive field, freeze last MarketState, no missing-quote warnings
- Additive optional wire fields: `change_day`, session high/low refs, `intelligence_enabled`, `replay_complete`, `last_market_timestamp`

### Fixed

- Host `alert_presented` is flushed before Core teardown so unread count cannot outrun telemetry

## 0.6.0 — 2026-08-29 (not tagged yet)

**Market Sentinel v0.6.0 — Feedback, Observability & Offline Tuning**

Package versions are **0.6.0**. Protocol stays **1** (`host_interaction` / `user_feedback` are v1 additive). Tuning artifact schema is **2**. Tuning comparison schema is **2**. These are independent version spaces. **Not merged. Not tagged. Not pushed.**

v0.6 does **not** automatically optimize trading parameters, rewrite production config, or collect workspace/conversation content.

### Added

- Deterministic telemetry contract: opaque `run_id`, `market_timestamp` vs `created_timestamp`, pipeline / Host interaction / Intelligence events, strict privacy allowlist
- Local-first append-only `telemetry.jsonl` (rotation, corruption-safe reader, data-quality warnings). Not Protocol stdout
- Read-only `EvaluationReport`: funnel, noise, repeated episodes, A-share market-hour semantics, per-run / per-market-date, Intelligence metrics, explicit-feedback metrics, corruption/data-quality warnings
- Optional explicit signal feedback only: `useful` / `not_useful` / `too_noisy` / `too_late`. Append-only `feedback.jsonl`. Correlation `(run_id, signal_id)`. No free text
- Offline tuning snapshots (immutable schema-v2) and baseline/candidate Replay comparison. CLI is `snapshot` / `compare` / `report` only

### Safety / boundaries

- No online self-modification. No `apply` / `promote` / `activate` / `deploy`
- A candidate tuning snapshot is not active production config. Normal runtime does not scan or load `tuning/`
- Supported offline parameters are only the seven with Consumed + Observable + Sensitivity proof: `cluster_lookback_s`, `hot_event_severity`, `hot_volume_ratio_5m`, `hot_change_5m`, `warm_change_1m`, `warm_change_5m`, `warm_volume_ratio`
- Deferred (cannot enter a candidate): cooldown/dwell, Intelligence Router / call budget, live scheduler polling intervals, Event thresholds/TTL, and other parameters not injected into Offline Replay
- No trading advice. No workspace / conversation / source / prompt / API-key collection. Signal title/summary are not stored in telemetry or feedback
- Draft tuning artifact schema 1 was never a released v0.6 artifact; load fail-closes; no migration
- Old Protocol v1 clients that omit `host_interaction` / `user_feedback` keep the previous path. New local files do not change MarketState / Event / Signal wire semantics

### Limitations

- A-share `.SH`/`.SZ` market-hour metric; weekends excluded; no full exchange holiday calendar; HK market-hour is unavailable rather than an A-share window
- Host `signal_opened` / `alert_dismissed` / `signal_muted` producers are unimplemented (rates unavailable, not 0%)
- JSONL writes stay synchronous (`write` → `flush` → `stat` → possible rotate)
- `ClusterMembershipTracker` retains clustered event ids for the run (theoretically unbounded within a run)
- Tuning Replay is monotonic-frozen, so cooldown/dwell stay deferred. Comparator does not attach Intelligence. Event module-global thresholds/TTL stay deferred
- Explicit feedback samples have self-selection bias. Trusted local Protocol may store structurally valid unknown `signal_id`; tuning datasets join telemetry and drop orphans

## Development lineage — v0.6 M0–M5 (logged while package was still 0.5.0)

Historical milestone notes below are unchanged. They describe work landed before the 0.6.0 version bump.

## Unreleased — v0.6 M5 review fixes (no version bump)

Evidence-driven `supported` parameters after external M5 review. Package **0.5.0**. Protocol **1**. No M6.

- `OfflineTuningConfig` keeps only parameters that are consumed, visible in `TuningComparisonReport`, and individually sensitivity-tested
- Intelligence router/budget and cooldown/dwell are `deferred` (comparator does not attach Intelligence; Replay freezes monotonic time)
- Comparison report schema 2 adds `scheduler` tick counts; artifact schema 2 fail-closes draft schema 1
- Empty or duplicate corpus ids raise `TuningConfigError` (CLI exit 2)

## Unreleased — v0.6 M5 Offline Tuning Workflow (no version bump)

Offline snapshot + Replay comparison on `feat/v0.6-feedback-observability`. Package **0.5.0**. Protocol **1**. No M6. M5 provides offline evidence, not automatic tuning.

- `OfflineTuningConfig` + `TuningSnapshot` artifact under `tuning/<snapshot_id>.json`; `capture_baseline_config()` maps current production defaults
- `market-sentinel tuning snapshot|compare|report` only; no apply/promote/activate
- `TuningFeedbackDataset` joins `(run_id, signal_id)` to Core lifecycle evidence; latest explicit label wins per target
- Candidate Replay is isolated; hypothetical results are not written to telemetry.jsonl or feedback.jsonl

## Unreleased — v0.6 M4 review fixes (no version bump)

Bind explicit feedback to Core execution identity after M4 external review. Package **0.5.0**. Protocol **1**. No M5.

- Host clears feedback targets on restart / disconnect / shutdown / new Core generation; pause/resume of the same process keeps them
- `submitSignalFeedback` refuses stale QuickPick selections (no `user_feedback` IPC)
- `feedback_coverage` uses unique `(run_id, signal_id)` keys, not `signal_id` alone
- Evaluation semantically validates feedback JSONL rows; invalid rows increment `invalid_feedback_record_count` / `semantic_warning_count` and never enter `useful_rate`

## Unreleased — v0.6 M4 Optional Explicit Feedback (no version bump)

Optional, explicit, low-cardinality signal feedback on `feat/v0.6-feedback-observability`. Package **0.5.0**. Protocol **1** (additive `user_feedback`). No M5 tuning, no online mutation, no free text.

- Taxonomy: `useful` / `not_useful` / `too_noisy` / `too_late` (UI wording is not storage)
- Host Command Palette / QuickPick produces facts; Core validates, stamps `run_id`, appends `feedback.jsonl`
- Same `run_id + signal_id` may appear more than once (append-only; no rewrite)
- Hover / `alert_presented` / badge reset / dismiss are not feedback
- Evaluation adds `explicit_feedback` counts, `useful_rate` (explicit sample only), and `feedback_coverage`; no feedback → `useful_rate` unavailable, not 0%
- Feedback write failure returns a command error; market pipeline continues

## Unreleased — v0.6 M3 review fixes (no version bump)

Correct evaluation time semantics after M3 external review. Package **0.5.0**. Protocol **1**. No M4.

- `alerts_per_market_hour` uses per-run telemetry-observed market-time span (all `market_timestamp` observations), not candidate-only min/max
- Multi-run exposure is summed per `run_id`; never min(r1)→max(rN)
- A-share market-hour metric supports `.SH`/`.SZ` only; `.HK` is `unsupported_market_scope`
- Weekends contribute 0 cash-session seconds; official holidays still not calendar-aware
- `per_run` / `per_market_date` summaries; breakdowns use frozen keys only (unknown values → counts + `data_quality_warning`)

## Unreleased — v0.6 M3 Evaluation Report (no version bump)

Read-only evaluation over M1/M2 telemetry on `feat/v0.6-feedback-observability`. Package **0.5.0**. Protocol **1**. No M4 feedback UX, no threshold changes, no storage redesign.

- `TelemetryReader` → `evaluate()` → `EvaluationReport.to_record()`; CLI `market-sentinel telemetry report`
- Funnel, noise, repeated-episode, A-share market-hour, Intelligence skip/fallback/latency, actual token totals only
- Host open/dismiss/mute rates are **unavailable** (`producer_not_implemented`), not 0%
- Data quality: rotated JSONL oldest→newest; middle corruption warning; trailing partial surfaced
- Evidence: sync JSONL vs NoOp Replay elapsed; `cluster_tracker_seen_count` (once-per-run unchanged)

## Unreleased — v0.6 M1/M2 review fixes (no version bump)

Narrow telemetry-edge fixes on `feat/v0.6-feedback-observability` after M1/M2 external review. Package **0.5.0**. Protocol **1**. No M3.

- Same-tick duplicate `produced` rows: episode created/escalated once per `signal.id`; `alert_suppressed(same_tick_duplicate)` unchanged
- JSONL reader decodes complete lines as raw bytes; invalid UTF-8 is corruption, not `UnicodeDecodeError`

## Unreleased — v0.6 M2 Local JSONL Storage (no version bump)

Persist Core telemetry as append-only JSONL on `feat/v0.6-feedback-observability`. Package versions stay **0.5.0**. Protocol stays **1**. No evaluation report, feedback files, TuningSnapshot persistence, SQLite, or M3.

- `TelemetrySink` / `JsonlTelemetrySink` behind `SinkTelemetryCollector`; producers do not import JSONL
- Local data dir (`MARKET_SENTINEL_DATA_DIR`, else `%LOCALAPPDATA%/MarketSentinel` or XDG); not the repo, cwd, or Protocol stdout
- Strict `to_record()` allowlist serialization; rotation defaults 1 MiB / 5 backups; trailing-partial repair
- CLI `run` / `daemon` persist via fail-open JSONL; storage failure does not change Event/Signal/Alert facts

## Unreleased — v0.6 M1 Telemetry Wiring (no version bump)

Wire frozen M0 observations on `feat/v0.6-feedback-observability`. Package versions stay **0.5.0**. Protocol stays **1** (additive `host_interaction`). No evaluation report, tuning, or online mutation.

- Per-execution opaque `run_id`; fail-open collector (`NoOp` / `InMemory`; JSONL sink in M2)
- Pipeline: generated/deduped/clustered, episode created/escalated, alert candidate/suppressed
- Intelligence: routed/skipped/succeeded/fallback/latency-by-stage; tokens only from adapter usage
- Host produces `alert_presented` (per candidate) and `alert_badge_reset` via Protocol v1 `host_interaction`

## Unreleased — v0.6 M0 Metrics Contract (no version bump)

Optional telemetry contract on `feat/v0.6-feedback-observability`. Package versions stay **0.5.0**. Protocol stays **1**. No storage, Host UI, or online tuning. **Frozen** after external review at `21e96dc`.

- `TelemetryEvent` / `UserFeedback` / `TuningSnapshot` types and allowlist/denylist
- `run_id` (one Core/Replay execution) and `market_timestamp` (not mixed with wall-clock `created_timestamp`); no telemetry `session_id`
- Host interaction facts owned by Host; collector/future local storage owned by Core
- `alert_presented` = one Host presentation/unread incorporation per candidate (not toast)
- `alert_suppressed` + `SuppressionReason` (`cooldown`, `same_tick_duplicate`)
- Intelligence `decision_reason` vs `fallback_reason`; `latency_stage` (`router`/`model`/`parse`)
- `event_clustered` at most once per `event_id` per run (`ClusterMembershipTracker`)
- `TuningSnapshot` has no `notes`; minimum correlation/non-negative validation
- Measurement does not mutate Event/Signal; feedback is not a market fact

## 0.5.0 — 2026-08-28 (not tagged yet)

Package versions are **0.5.0**. Protocol stays **1**.

**v0.4.0 was never released/tagged.** v0.5.0 includes the unreleased v0.4 live-data lineage plus the v0.5 Intelligence Router.

- Optional low-frequency Intelligence sidecar; Rule `Signal` remains source of truth
- DashScope compatible-mode adapter sends `enable_thinking: false` (default timeout remains 8s)
- Protocol v1 additive `intelligence` on `WireSignal`
- Cursor hover shows enrichment only when status is `enriched`
- Unreleased Tencent/Sina live-gate probes and Longbridge optional provider from the v0.4 lineage

## Unreleased — v0.5 Final Release Verification (no version bump)

Verification-only against feature freeze `95398c4`. Package versions stay **0.3.0**. Protocol stays **1**.

- Local DashScope one-shot smoke: eligible Replay episode → one real model call → `status=enriched` (30s timeout override; default 8s timed out)
- Sidecar fail-open runtime smoke: missing key → stderr WARNING, Rule-only Core, clean stdout
- VSIX packaging audit: `pnpm package:vsix` 0.3.0, 21 files, not published
- Gates unchanged: 428 pytest + 5 live deselected, coverage 90.66%, 145 pnpm tests

## Unreleased — v0.5 RC Fix Pass (no version bump)

External review blockers on `feat/v0.5-market-intelligence`. Package versions stay **0.3.0**. Protocol stays **1**.

- Episode retirement invalidates queued work before `provider.complete`; in-flight results cannot resurrect annotations
- Retired episode call-budget / generation maps are forgotten after pending work drains
- Parser fail-closes Chinese and English trading-instruction phrasing
- Intelligence config/auth/provider failure is fail-open: WARNING on stderr, Rule-only Core continues
- CLI `run` / `--once` start, drain, and shut down the sidecar
- Coordinator fallback logs redact configured secrets

## Unreleased — v0.5 Market Intelligence Router (no version bump)

Optional low-frequency Intelligence sidecar on `feat/v0.5-market-intelligence`. Package versions stay **0.3.0**. Protocol stays **1** (additive `intelligence` on `WireSignal` only). Default `MARKET_SENTINEL_INTEL_ENABLED` is off, so ordinary ticks still make **zero** model calls.

- Deterministic `need_intelligence` router; Rule `Signal` is unchanged
- Async coordinator with bounded queue, episode call budget (default 1), timeout, fallback
- Fake provider for default tests; DashScope/Qwen adapter isolated under `intelligence/providers`
- Cursor hover shows enrichment only when status is `enriched`

## Unreleased — v0.4 Tencent/Sina live gate (no version bump)

Preferred live source is Tencent `qt.gtimg.cn` with a one-shot Sina `hq.sinajs.cn` cross-check. Longbridge stays in-tree but is optional and does not block. Tushare is excluded. Package versions stay **0.3.0**. Protocol stays **1**.

- Reused existing Tencent probe for efficient 1 / 2 / 10 symbol batches (`sh`/`sz` vendor codes)
- In-session freshness: today's CST date, cash-session quote time, recorded received−market latency, non-decreasing volume, positive volume delta (price change not required)
- Sina probe is one-shot with Referer; no polling loop
- Access-denied / anti-bot payloads fail closed
- Live tests fail closed (no skip/mock) for Tencent and Sina
- `HealthPolicy.delayed_s` remains 3.0
- Longbridge implementation is not deleted

## Unreleased — v0.4 audit-blocker fixes (live session gate pending)

External v0.4 Release Audit rejected the previous RC. Package versions stay **0.3.0** and Protocol stays **1** until every gate passes. Do not tag `v0.4.0` yet.

- `SecurityQuote.timestamp` timezone-aware datetime → Unix at the Longbridge Provider boundary (naive datetime fail-closed)
- Process-lifetime lazy `AsyncQuoteContext`; native `await quote()`; `asyncio.Lock` single-flight; `wait_for` timeout; no production `to_thread` quote path
- Error codes: 301603 → `ProviderNoDataError` (not Auth); 301604/401003/40320x → Auth; 301606/42900x → rate limit
- Older quotes no longer refresh FeedHealth success; duplicate timestamps do not re-fire alert edges
- Turnover cannot be enabled in v0.4 (`vendor_quote_to_raw` always `None`)
- Host Option A: `uv sync --extra live` is manual; Cursor spawn never passes `--extra live`
- Live tests skip only when credentials are absent; provider errors fail when credentials exist
- Session smoke tool: `python -m tools.live_probe session` (1/2/10 symbol batches; excluded from default CI)

## v0.3.0 — 2026-08-27

Cursor Host MVP. Python Core and the desktop extension are both 0.3.0. Wire compatibility remains Protocol v1.

- pnpm workspace
- Protocol v1
- Python JSONL daemon
- TypeScript IPC
- Cursor lifecycle
- StatusBar
- Hover
- alert / unread
- local VSIX
- IDLE empty-watchlist hardening

### M0 — Node / pnpm workspace

Root `package.json`, `pnpm-workspace.yaml`, and `apps/cursor-extension` skeleton with `pnpm test` / `lint` / `typecheck` / `build`. No StatusBar/Hover.

### M1 — Protocol v1 DTO / codec / mapping

Versioned JSONL envelope, explicit wire DTOs, and `MarketState` → DTO mapper. Core models are not `asdict`'d onto the wire.

### M2 — Python daemon transport

`market-sentinel daemon`: Windows-safe stdin, flushed JSONL stdout, stderr logging, daemon phase machine, runtime-only `set_watchlist`, command/tick lock, graceful shutdown. Integration test runs `uv run ... daemon`.

### M3 — TypeScript protocol guards, JSONL IPC client, process manager

Hand-written Protocol v1 guards (no zod), JSONL line decoder, `IpcClient` request map, and `ProcessManager` (`uv run --directory <coreRoot> ... daemon`, `shell: false`). Handshake is hello → set_watchlist → start. `active_signals` stay on state; alerts only come from `alert` messages. No `vscode` import in these modules.

### M4 — Cursor extension lifecycle, settings, commands

`HostController` keeps `desiredState` (RUNNING/PAUSED) separate from process actual state. Trusted-workspace-only desktop extension: `onStartupFinished` + pause/resume/restartCore/showOutput. Watchlist hot-applies; coreRoot/uvPath/provider/replayPath require `restartCore`. Crash while RUNNING retries 1s/3s/10s (max 3). Crash while PAUSED does not auto-start. `ready.core_version` is diagnostics-only.

### M5 — Minimal StatusBar

StatusBar maps host lifecycle + Protocol v1 `state`/`alert` to `DISCONNECTED | PAUSED | STARTING | STALE | ALERT | HOT | WARM | NORMAL`. Feed STALE/DISCONNECTED is never shown as NORMAL. `ALERT` comes only from `alert` messages (15s hold; `elapsed === hold` is expired), never from `state.active_signals`. RUNNING without a MarketState maps to STARTING, not NORMAL. Click opens the Output Channel. No unread/toast.

### M6 — Hover Details

StatusBar hover is read-only persistent-state inspection. `HoverModel` maps host lifecycle + `WireMarketState` (no vscode). Markdown is rendered separately; `MarkdownString.isTrusted` stays false and there are no command links. `marketSentinel.enableHoverDetails` (default true) is a Host-only hot setting and does not restart Core. `active_signals` can appear in Hover but never become StatusBar `ALERT`.

### M7 — Host Alert Handling

Unread badge and optional critical toast come only from unsolicited Protocol `alert` messages (`unread += candidates.length`). `state.active_signals` never increment unread or toast. Transient 15s ALERT hold is independent of unread. `marketSentinel.resetAlertBadge` clears Host-local unread only. `marketSentinel.alertToast` (`off` | `critical`, default `off`) is Host-only. Unread is not persisted across extension reload. Core crash/restart keeps unread. Host does not write `notified_timestamp`.

### M8 — Host Integration / VSIX

Local developer VSIX via `@vscode/vsce` (`pnpm package:vsix`). Identity `market-sentinel-local.market-sentinel` is a local publisher id, not Marketplace. `extensionKind: ["ui"]`. Python Core is not bundled. Extension Host smoke uses `@vscode/test-electron`. Host-level IPC covers hello → set_watchlist → start → pause → resume → get_state → shutdown. Restart invariant: unread survives Core crash; `active_signals` still do not increment unread; a new `alert` edge increments unread.

### M8.1 — Empty watchlist IDLE

Host StatusBar maps RUNNING + empty watchlist (`watchlist_count === 0` and `symbols === []`) to `IDLE` with default tone. A configured symbol whose feed is STALE/DISCONNECTED still maps to `STALE`. Hover says “No symbols configured” instead of presenting Core `feed_status=DISCONNECTED` as a data outage. Unread is unchanged.

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
