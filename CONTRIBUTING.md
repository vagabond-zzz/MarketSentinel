# Contributing to Market Sentinel

Thanks for your interest in improving Market Sentinel. This document covers what you need to build, test, and submit changes.

## Project layout

- `src/market_sentinel/` — Python core (market pipeline, event/signal engines, IPC daemon, intelligence sidecar, telemetry)
- `apps/cursor-extension/` — Cursor / VS Code Desktop host (TypeScript)
- `tests/` — Python tests (unit + offline integration; fixtures are replay corpora)
- `tools/` — developer-only probes and benchmarks (not part of the installed package)
- `docs/` — architecture contracts, integration guides, and history (see [docs/README.md](docs/README.md))

Long-standing engineering rules live in [AGENTS.md](AGENTS.md). The short version:

1. The high-frequency market path is deterministic code — never call an LLM there.
2. Core never imports host APIs (VS Code / Cursor / any agent harness); hosts never copy core business logic.
3. Every core module is testable (injectable `Clock`, `FakeProvider`) and observable.
4. Agent-facing surfaces are read-only.

## Prerequisites

- Python 3.12+ and [`uv`](https://docs.astral.sh/uv/)
- Node.js 20+ and `pnpm` (only needed for the extension)

## Setup

```bash
git clone https://github.com/vagabond-zzz/MarketSentinel.git
cd MarketSentinel

uv sync          # Python core + dev tools
pnpm install     # extension toolchain
```

Optional live-market extras:

```bash
uv sync --extra live   # httpx + longbridge SDK; requires vendor credentials via env vars
```

## Running the checks

Python (all offline by default):

```bash
uv run pytest                          # unit + integration tests
uv run ruff check .
uv run ruff format --check .
```

Coverage gate is 85%:

```bash
uv run pytest --cov=market_sentinel \
  --deselect tests/integration/test_engine_perf.py::test_ten_symbol_engine_replay_stays_within_regression_budget
```

The deselected perf test must run without coverage instrumentation:

```bash
uv run pytest tests/integration/test_engine_perf.py::test_ten_symbol_engine_replay_stays_within_regression_budget -s
```

Tests marked `live` (real network/vendor probes) are excluded from a bare `uv run pytest`; run them explicitly with `uv run pytest -m live` only if you have the credentials and want to hit the real vendors.

TypeScript / extension:

```bash
pnpm test          # vitest (includes real core-process integration tests when uv is available)
pnpm typecheck
pnpm lint
pnpm build
pnpm package:vsix  # builds the VSIX and runs the packaging audit script
```

## Tests

- Default tests must run offline. Use `FakeProvider` / `ReplayProvider` / `FakeClock` in unit tests; network tests must be marked `live`.
- Time-dependent logic (scheduler, cooldown, feed health, TTL) must take an injected `Clock` — no `time.time()` / `datetime.now()` in core logic.
- New core features need tests in the same change; don't land features and tests in separate PRs.
- The wire protocol (`src/market_sentinel/ipc/`) is mirrored by hand in `apps/cursor-extension/src/protocol/`. If you change Protocol v1, update both sides and keep changes additive-optional; protocol and package versions are independent.
- Telemetry / evaluation semantics are frozen in [docs/architecture/metrics-contract.md](docs/architecture/metrics-contract.md) — read it before touching `market_sentinel.telemetry` or `market_sentinel.evaluation`.

## Commit style

Use Conventional Commits (`feat:`, `fix:`, `test:`, `refactor:`, `docs:`, `chore:`, `perf:`). Keep each commit independently understandable — don't bundle a whole version into one commit, and don't split one logical change into noise.

Before committing:

1. `git status` / `git diff` — review what you're actually committing
2. Run the relevant tests and lints (both languages if you touched both)
3. Confirm no secrets, no `.venv/`, no `node_modules/`, no generated artifacts are staged

## Submitting changes

Open a pull request against `master` with a short description of what changed and why, and the check results. For larger design changes (protocol, scheduler semantics, intelligence contract), open an issue first and reference the relevant contract doc in `docs/architecture/`.
