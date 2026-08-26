# Market Sentinel

Low-latency market monitoring core for developer hosts (Cursor, DeepSeek Harness, ZCode).

Current stage: **v0.1 Core Foundation**. High-frequency market updates never call an LLM (`Token = 0`).

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

## v0.1 scope

Python Core only: Market Provider, Snapshot normalize, Ring Buffer, Market State, Adaptive Scheduler, Feed Health, CLI diagnostics.

Not in v0.1: Feature / Event / Signal engines, Cursor UI, DSH / ZCode adapters, HTTP API, database, LLM.
