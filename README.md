# Market Sentinel

Low-latency market monitoring core for developer hosts (Cursor, DeepSeek Harness, ZCode).

Current version: **v0.2.0 — Market Event Engine**. v0.3 Cursor Host is in progress on `feat/v0.3-cursor-host` (Python JSONL daemon + TypeScript IPC client; no Cursor UI yet). High-frequency market updates never call an LLM (`Token = 0`). There is no live HTTP provider, no `notified_timestamp`, and no LLM / News / MCP.

## Positioning

Market Sentinel watches a small watchlist, turns quotes into Features / Events / Signals, and keeps alerts rare. It is a Core plus diagnostics CLI, not a trading product and not a final IDE UI.

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

Default pytest is offline. Coverage fails under 85%. Do not depend on live market HTTP.

## CLI

```bash
uv run market-sentinel --watchlist data/watchlist.json watchlist add 00700.HK
uv run market-sentinel --watchlist data/watchlist.json watchlist list
uv run market-sentinel --watchlist data/watchlist.json run --once
uv run market-sentinel --watchlist data/watchlist.json run --once --verbose
```

`--provider` defaults to `fake`. `replay` reads a JSONL fixture (`--replay path`). `http` is not implemented as a Core provider.

Host protocol (v0.3; stdout is JSONL only):

```bash
uv run market-sentinel --provider fake daemon
```

Commands are JSON lines on stdin (`hello`, `start`, `pause`, `resume`, `set_watchlist`, `get_state`, `shutdown`). Logs go to stderr. `set_watchlist` is runtime-only and does not write `data/watchlist.json`.

The Cursor package (`apps/cursor-extension`) includes a vscode-free JSONL IPC client and Python process manager. Spawn is argv-based (`shell: false`):

```text
uv run --directory <repo> market-sentinel --provider fake daemon
```

Handshake order is `hello` → `set_watchlist` → `start`. Host UI (StatusBar / Hover / commands) is M4+.

```bash
pnpm test
pnpm lint
pnpm typecheck
pnpm build
```

## Architecture

```text
Market Provider
  → normalize
  → Ring Buffer
  → Feature Engine
  → Event Rules
  → Dedupe / Cluster / Cooldown
  → Signal
  → WarmingPolicy / Adaptive Scheduler
  → Runtime (MarketState + EngineTickResult)
  → CLI diagnostics
```

## v0.2 capabilities

Watchlist of **at most 10 symbols**.

### Features

- 1m / 5m / 15m change (decimal fraction: `0.006` = 0.6%)
- session volume ratio (1m / 5m)
- EMA5 / EMA20
- RSI14
- VWAP and above/below
- session high / low from provider extremes

### Event rules

1. `rapid_move`
2. `volume_spike`
3. `price_volume_expansion`
4. `day_high_breakout`
5. `day_low_breakdown`
6. `vwap_cross`

### Diagnostics meaning

| Section | Source | Meaning |
|---|---|---|
| Persistent rows + `ACTIVE SIGNALS` | `MarketState` | Current live episode look-back, not a new reminder |
| `EVENTS THIS TICK` | `SymbolTickResult.accepted_events` | Events accepted on this tick only |
| `ALERTS THIS TICK` | `SymbolTickResult.alert_candidates` | New reminder eligibility this tick only |

A Signal can stay in `ACTIVE SIGNALS` while `ALERTS THIS TICK` is `None` (cooldown).

## Current limitations

- At most **10 symbols**.
- `MarketSnapshot.volume` / `turnover` are **session cumulative**, not per-interval.
- Volume ratio needs about **20 in-session 1-minute baselines** before it is defined (`None` until then, never treated as 0).
- Session id is the **UTC+8 calendar day**. That matches current A/H MVP examples; there is no full exchange calendar.
- `MarketBar` is an adaptive-polling **sampled/observed** 1-minute bar, not an exchange official K-line.
- VWAP needs reliable cumulative **turnover and volume**.
- No Cursor StatusBar / Hover / WebView yet (v0.3 M4–M8).
- No formal HTTP live provider.
- No `notified_timestamp` (alert candidate ≠ notified).
- No LLM, News, MCP, auto-trading, or buy/sell advice.

## v0.1 status

Done: dual clock, Fake/Replay providers, normalize, ring buffer, watchlist, COLD/WARM/HOT scheduler, feed health, steppable `MarketEngine.tick()`.
