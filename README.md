# Market Sentinel

Low-latency market monitoring core for developer hosts (Cursor, DeepSeek Harness, ZCode).

Current stage: **v0.2 Event Engine** (M8 CLI v2). High-frequency market updates never call an LLM (`Token = 0`). M9 wrap-up is not implemented.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

The default `python` on some machines is 3.11. Always use `uv run`.

## Setup

```bash
uv sync
```

## Tests and checks

```bash
uv run pytest
uv run pytest --cov=market_sentinel
uv run ruff check .
uv run ruff format --check .
```

Default pytest is offline. Do not depend on live market HTTP.

## CLI

```bash
uv run market-sentinel --watchlist data/watchlist.json watchlist add 00700.HK
uv run market-sentinel --watchlist data/watchlist.json watchlist list
uv run market-sentinel --watchlist data/watchlist.json run --once
uv run market-sentinel --watchlist data/watchlist.json run --once --verbose
```

`--provider` defaults to `fake`. `replay` reads a JSONL fixture. `http` is not part of the offline v0.1 Core path.

## v0.2 status (in progress)

Done through M8:

- Feature Engine, Event rules, dedupe, cluster, cooldown, Signal composer
- `MarketEngine.tick()` pipeline: features → events → signals → warming → `EngineTickResult`
- `MarketState.features` and `MarketState.active_signals` (multiple live episodes)
- `alert_candidates` are edge-triggered, not durable notification state
- Diagnostics CLI: persistent state vs `EVENTS THIS TICK` vs `ALERTS THIS TICK`

Not in this stage: M9 replay/perf/docs wrap-up, Cursor UI, DSH / ZCode adapters, LLM, `notified_timestamp`.

## v0.1 status

Done:

- Dual clock (`wall_time` + `monotonic_time`)
- MarketProvider + FakeProvider + ReplayProvider
- Snapshot normalize
- Ring buffer and market state
- Watchlist (max 10, JSON)
- COLD/WARM/HOT scheduler (any transition; upgrade fast, downgrade cautious)
- Feed health with consecutive-failure disconnect
- `MarketEngine.tick()` and diagnostics CLI

Not in v0.1: Feature / Event / Signal engines, Cursor UI, DSH / ZCode adapters, live HttpQuoteProvider as a Core gate, HTTP API, database, LLM.
