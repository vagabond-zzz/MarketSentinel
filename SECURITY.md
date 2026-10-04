# Security Policy

## What Market Sentinel is (and is not)

Market Sentinel is a **local, read-only market observation tool**:

- It does **not** execute trades, place orders, or connect to any broker trading API. The Longbridge integration is quote-pull only.
- It does **not** provide buy/sell advice. The optional intelligence layer structurally rejects model output containing trading advice (fail-closed parser), and rule signals are deterministic code, not model output.
- It does **not** send telemetry anywhere. Telemetry, explicit feedback, and tuning snapshots are append-only JSONL files on your machine (Windows: `%LOCALAPPDATA%/MarketSentinel`, Unix: `$XDG_DATA_HOME/market-sentinel` or `~/.local/share/market-sentinel`).

## Credentials and secrets

All credentials come exclusively from environment variables and are never written to disk by the project:

| Variable | Used for |
|---|---|
| `LONGBRIDGE_APP_KEY` / `LONGBRIDGE_APP_SECRET` / `LONGBRIDGE_ACCESS_TOKEN` | live quote provider (optional, requires `uv sync --extra live`) |
| `DASHSCOPE_API_KEY` | optional LLM intelligence provider |

By design:

- Credentials are never accepted in extension settings, CLI flags, watchlist files, or config files, and never included in telemetry, feedback, or tuning artifacts. The extension test suite asserts that no credential value reaches process argv, spawn env overrides, or settings JSON.
- Secret values that appear in provider error messages are redacted before logging.
- What the LLM sees is limited to a compacted, allowlisted payload of signal context (symbol, event types, price/volume features, feed status). Workspace contents, source code, prompts, raw ticks, and API keys are denylisted and never sent.

## Reporting a vulnerability

Please report security issues privately via [GitHub private vulnerability reporting](https://github.com/vagabond-zzz/MarketSentinel/security/advisories/new) rather than a public issue.

Include: affected version/commit, a minimal reproduction, and your assessment of impact. Please give maintainers reasonable time to respond before any public disclosure.

Supported versions: the latest tagged release on `master` (currently v0.6.5).

## Scope notes

- Because the tool is local-only and ships no server component, issues that require network-reachable infrastructure or a published package do not currently apply.
- If you find credentials committed to the repository or leaked into telemetry output, that **is** in scope — please report it with the file and line.
- Third-party market-data endpoints probed by `tools/live_probe/` (Tencent, Sina) are public quote pages used read-only for development verification; abuse of those services is out of scope for this project's threat model but strictly discouraged.
