# Market Sentinel

Low-latency market monitoring core for developer hosts (Cursor, DeepSeek Harness, ZCode).

Current Core package: **v0.2.0**. Cursor Host **v0.3 Release Candidate** is on `feat/v0.3-cursor-host`. Wire compatibility is **Protocol v1** (`protocol_version`), not the Python package version. High-frequency market updates never call an LLM (`Token = 0`). There is no live HTTP provider, no `notified_timestamp`, and no LLM / News / MCP.

## Positioning

Market Sentinel watches a small watchlist, turns quotes into Features / Events / Signals, and keeps alerts rare. It is a Core plus diagnostics CLI plus a desktop Cursor host, not a trading product.

## v0.3 Cursor Host (Release Candidate)

Desktop Cursor / VS Code extension that spawns the Python daemon over stdin/stdout JSONL (Protocol v1).

Included:

- Cursor / VS Code **Desktop** extension
- Python daemon via **uv**
- JSONL Protocol v1
- StatusBar (`DISCONNECTED` / `STARTING` / `PAUSED` / `STALE` / `ALERT` / `HOT` / `WARM` / `NORMAL`)
- Hover (persistent `WireMarketState`)
- Pause / Resume / Restart Core / Show Output
- Unread alert badge (unsolicited `alert` edges only)
- Optional critical toast (`marketSentinel.alertToast`)
- Reset Alert Badge

Python Core is **not** bundled in the VSIX. Developer install still needs a Core checkout and `uv`.

Extension identifier: `market-sentinel-local.market-sentinel`. Publisher `market-sentinel-local` is a **local VSIX id**, not a Marketplace publisher.

### Developer install

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 20+, pnpm, Cursor Desktop (or VS Code Desktop).

```bash
uv sync
pnpm install
pnpm build
pnpm package:vsix
```

Then in Cursor: Extensions → **Install from VSIX…** → `apps/cursor-extension/market-sentinel-0.3.0.vsix`.

Open a **trusted** workspace. Set `marketSentinel.coreRoot` when the window is not a single-folder Core checkout. Confirm `marketSentinel.uvPath` (default `uv`).

### Settings

| Setting | Role |
|---|---|
| `marketSentinel.coreRoot` | Python Core checkout (`pyproject.toml`). Required when no single workspace folder is open, and for multi-root windows. |
| `marketSentinel.uvPath` | `uv` executable (`shell: false`). |
| `marketSentinel.watchlist` | Host watchlist intent (Core still enforces 10-symbol limit). |
| `marketSentinel.provider` | `fake` (default) or `replay`. |
| `marketSentinel.replayPath` | Required when provider is `replay`. |
| `marketSentinel.enableHoverDetails` | Full StatusBar hover (default `true`). Host-only. |
| `marketSentinel.alertToast` | `off` (default) or `critical`. Host-only. |

### Manual Cursor Desktop checklist

1. Install the VSIX.
2. Open a trusted workspace.
3. Configure `marketSentinel.coreRoot` if needed.
4. Confirm `uvPath`.
5. Set `provider` to `fake` or `replay`.
6. Configure `watchlist`.
7. Reload the window.
8. StatusBar item appears (`MS …`).
9. Hover shows feed / symbols (or a lifecycle message).
10. Pause / Resume.
11. Restart Core.
12. Show Output.
13. Reset Alert Badge.
14. Close Cursor.
15. Confirm no leftover `market-sentinel daemon` / Python child.

This checklist is manual. Automated tests cover Protocol IPC, HostController, StatusBar mapping, and an Extension Host smoke activate/deactivate path.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

The default `python` on some machines is 3.11. Always use `uv run`.

## Setup

```bash
uv sync
pnpm install
```

## Tests and checks

```bash
uv run pytest
uv run pytest --cov=market_sentinel
uv run ruff check .
uv run ruff format --check .
```

```bash
pnpm test
pnpm lint
pnpm typecheck
pnpm build
pnpm package:vsix
pnpm test:extension-host
```

Default pytest is offline. Coverage fails under 85%. Do not depend on live market HTTP. `pnpm test:extension-host` downloads a VS Code Desktop binary via `@vscode/test-electron` (not Cursor).

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

Spawn is argv-based (`shell: false`):

```text
uv run --directory <repo> market-sentinel --provider fake daemon
```

Handshake order is `hello` → `set_watchlist` → `start`.

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
  → JSONL daemon
  → Cursor Host (StatusBar / Hover / unread)
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

## Known limitations

- At most **10 symbols**.
- `MarketSnapshot.volume` / `turnover` are **session cumulative**, not per-interval.
- Volume ratio needs about **20 in-session 1-minute baselines** before it is defined (`None` until then, never treated as 0).
- Session id is the **UTC+8 calendar day**. That matches current A/H MVP examples; there is no full exchange calendar.
- `MarketBar` is an adaptive-polling **sampled/observed** 1-minute bar, not an exchange official K-line.
- VWAP needs reliable cumulative **turnover and volume**.
- No live HTTP provider.
- Python runtime is **not bundled** in the VSIX (developer install: `coreRoot` + `uvPath`).
- Desktop Cursor / VS Code only (`extensionKind: ui`). Web / browser Cursor is unsupported. Remote SSH / Codespaces is not validated.
- Untrusted workspaces are unsupported because the host starts a local Python Core.
- Unread alert count is Host-local and resets on extension reload (not written to workspaceState).
- No WebView, no alert history panel.
- No `notified_timestamp` (alert candidate ≠ notified).
- No LLM, News, MCP, auto-trading, or buy/sell advice.

## v0.1 status

Done: dual clock, Fake/Replay providers, normalize, ring buffer, watchlist, COLD/WARM/HOT scheduler, feed health, steppable `MarketEngine.tick()`.
