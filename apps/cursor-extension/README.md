# Market Sentinel (Cursor host)

Developer-install Cursor / VS Code **Desktop** extension for Market Sentinel **v0.3.0**.

Package version: `0.3.0`  
Extension identifier: `market-sentinel-local.market-sentinel`

`publisher` is `market-sentinel-local`. This is a **local/developer identifier** for the VSIX. It is not a Visual Studio Marketplace publisher identity. Changing it later will change the extension identifier.

Python Core is **not** bundled. The extension spawns:

```text
uv run --directory <coreRoot> market-sentinel --provider fake daemon
```

For live A-shares, set `marketSentinel.provider` to `longbridge` and export `LONGBRIDGE_APP_KEY` / `LONGBRIDGE_APP_SECRET` / `LONGBRIDGE_ACCESS_TOKEN` in the environment inherited by the child process (not in settings). Install the SDK with `uv sync --extra live`. See repository `docs/12_v0.4_Longbridge_Provider_Setup.md`.

Wire protocol is JSONL Protocol v1 (`protocol_version === 1`).

## Install from VSIX

1. From the repository root: `pnpm build` then `pnpm package:vsix`.
2. In Cursor Desktop: Extensions → `...` → Install from VSIX → select `apps/cursor-extension/market-sentinel-0.3.0.vsix`.
3. Open a **trusted** workspace that contains the Python Core checkout, or set `marketSentinel.coreRoot`.
4. Confirm `uv` is on PATH or set `marketSentinel.uvPath`.

This extension is `extensionKind: ["ui"]` (local Desktop). Remote SSH / Codespaces / Web are not supported in v0.3.0.

## Commands

- Market Sentinel: Pause Monitoring
- Market Sentinel: Resume Monitoring
- Market Sentinel: Restart Core
- Market Sentinel: Show Output
- Market Sentinel: Reset Alert Badge

## Settings

- `marketSentinel.coreRoot`
- `marketSentinel.uvPath`
- `marketSentinel.watchlist`
- `marketSentinel.provider` (`fake` | `replay` | `longbridge`)
- `marketSentinel.replayPath`
- `marketSentinel.enableHoverDetails` (default true)
- `marketSentinel.alertToast` (`off` | `critical`, default `off`)

## Manual smoke

See the repository root `README.md` for the v0.3.0 Cursor Desktop checklist (StatusBar, Hover, Pause/Resume, Restart Core, unread badge, shutdown).
