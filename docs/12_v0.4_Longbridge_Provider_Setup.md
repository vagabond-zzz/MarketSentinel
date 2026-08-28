# v0.4 live provider setup

Target order for the v0.4 live gate:

1. **Tencent `qt.gtimg.cn`** — preferred primary (existing probe; 1/2/10 batch)
2. **Sina `hq.sinajs.cn`** — fallback / one-shot cross-check (no aggressive polling)
3. **Longbridge** — optional future provider; missing credentials must **not** block v0.4
4. **Tushare** — excluded (realtime/minute APIs need separately granted permissions)

Tencent and Sina remain **probes** until Core `MarketProvider` wiring is an explicit follow-up. Longbridge code is kept.

## Tencent probe

```bash
uv run python -m tools.live_probe tencent --symbols 600519.SH,000001.SZ --interval 2 --count 8 --out .tmp/tencent.jsonl
```

Vendor codes: `600519.SH` → `sh600519`, `000001.SZ` → `sz000001`. One HTTP request can carry 1, 2, or 10 symbols.

## Sina cross-check

One request only. Requires `Referer: https://finance.sina.com.cn/`.

```bash
uv run python -m tools.live_probe sina --symbols 600519.SH,000001.SZ
```

Do not loop this endpoint.

## Longbridge (optional)

Production adapter is **Longbridge OpenAPI Quote Pull** via a process-lifetime **`AsyncQuoteContext`**. It is **not** required for the Tencent live gate.

## Install policy (Option A)

Default development install does **not** pull the native SDK:

```bash
uv sync
```

Live extra (Python 3.12, including Windows `cp312-win_amd64`):

```bash
uv sync --extra live
```

That extra currently includes `longbridge>=4.0` (lockfile `4.5.0`) and the pre-existing unused `httpx` optional. Do not install Futu or Tushare.

**Host spawn never passes `--extra live`.** Cursor `ProcessManager` runs:

```text
uv run --directory <coreRoot> market-sentinel --provider longbridge daemon
```

Installing the SDK on every Cursor startup is forbidden. If the extra is missing, Core fails closed with:

```text
longbridge SDK is not installed; run uv sync --extra live
```

Do not rely on an old `.venv` that happens to still contain `longbridge`.

## Credentials

Set process environment variables. Never put them in Git, Protocol, settings.json, Output Channel, or the VSIX.

```text
LONGBRIDGE_APP_KEY
LONGBRIDGE_APP_SECRET
LONGBRIDGE_ACCESS_TOKEN
```

The Cursor child daemon inherits the environment of the Cursor process. On Windows, GUI-launched Cursor may not see variables you only set in a terminal. Set **User** environment variables and restart Cursor, or start Cursor from a shell that already has the variables.

CLI / daemon:

```bash
uv run market-sentinel --provider longbridge --watchlist data/watchlist.json run --once
uv run --directory <coreRoot> market-sentinel --provider longbridge daemon
```

Missing credentials exit 2 with **names only**. Missing SDK exits 2 with the extra-live install hint.

## SDK context lifecycle

```text
LongbridgeQuoteProvider
  → lazy AsyncQuoteContext.create(Config.from_apikey_env())
  → await ctx.quote(batch) under asyncio.Lock + wait_for timeout
  → reuse the same context on later fetches
```

- One in-flight quote batch per provider instance.
- No `asyncio.to_thread` on the quote path.
- No per-tick `QuoteContext` construction.
- The Python SDK has **no documented close()**; the child process exit is final cleanup.
- Ordinary quote success reuses the context.
- Recoverable provider/server errors are surfaced; Feed Health degrades.
- `TimeoutError` / `ConnectionError` / `OSError` discard the tracked context; the next fetch creates at most one replacement. No reconnect storm / pool.

## Timestamp conversion (provider boundary)

Official `SecurityQuote.timestamp` is a timezone-aware `datetime`.

```text
aware datetime.timestamp() → Unix float → normalize_snapshot()
```

- Naive datetime: fail closed (quote dropped).
- Numeric timestamps remain for tests/fixtures only.
- Never `datetime.now()` / `Clock.wall_time()` as `market_timestamp`.
- `received_timestamp` comes from Core `Clock` in `normalize_snapshot`.

## Error classification

Prefer structured SDK `code` when present:

| Code | Class |
|---|---|
| 301606, 429001, 429002 | `ProviderRateLimitError` |
| 401003, 403201, 403203, 403205, 301604 | `ProviderAuthError` |
| **301603** | **`ProviderNoDataError` (not Auth)** |
| 301602, 500000, transport | `ProviderUnavailableError` |

Secrets are redacted.

## Markets

v0.4 live adapter accepts **SH / SZ** only. Primary smoke symbols: `600519.SH`, `000001.SZ`. HK/US watchlist rows produce missing quotes (feed health degrades), not a forged snapshot.

## Mapping (conservative)

| Core field | Longbridge | Notes |
|---|---|---|
| `price` | `last_done` | fail closed if invalid |
| `open` / `high` / `low` / `prev_close` | same names | drop if high/low non-positive or inverted |
| `volume` | `volume` | passed through; **unit UNKNOWN**; treated as same-session cumulative |
| `turnover` | **always `None`** | no v0.4 escape hatch; no ×100 |
| `market_timestamp` | vendor `timestamp` | aware datetime → Unix; never `datetime.now()` |
| `received_timestamp` | Core `Clock.wall_time()` | set by `normalize_snapshot` |

## Cursor

`marketSentinel.provider` = `longbridge`. Changing it requires Core restart. Host does not parse vendor quotes, does not send credentials on argv or Protocol, and does not pass `uv run --extra live`.

## Live session smoke (not default CI)

Credentials absent → skip. Credentials present → provider errors **fail** (no skip).

Must run during an A-share session. All-zero volume deltas are **not** success.

```bash
uv sync --extra live
uv run python -m tools.live_probe session --symbols 600519.SH,000001.SZ --interval 2 --samples 20 --out .tmp/longbridge_session_smoke.json
uv run pytest -m live
```
