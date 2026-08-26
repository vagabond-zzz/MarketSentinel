# Market Sentinel

Low-latency market monitoring core for developer hosts (Cursor, DeepSeek Harness, ZCode).

Current stage: **v0.2 Event Engine** (M7 Runtime Integration). High-frequency market updates never call an LLM (`Token = 0`). M8 CLI v2 and M9 wrap-up are not implemented.

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
```

`--provider` defaults to `fake`. `replay` reads a JSONL fixture. `http` is not part of the offline v0.1 Core path.

## v0.2 status (in progress)

Done through M7:

- Feature Engine, Event rules, dedupe, cluster, cooldown, Signal composer
- `MarketEngine.tick()` pipeline: features → events → signals → warming → `EngineTickResult`
- `MarketState.features` and `MarketState.active_signals` (multiple live episodes)
- `alert_candidates` are edge-triggered, not durable notification state

Not in this stage: CLI v2, Cursor UI, DSH / ZCode adapters, LLM, `notified_timestamp`.

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
