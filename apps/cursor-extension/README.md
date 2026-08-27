# Market Sentinel (Cursor host)

Developer-install Cursor / VS Code **Desktop** extension for Market Sentinel v0.3.

Extension identifier: `market-sentinel-local.market-sentinel`

`market-sentinel-local` is a **local/developer publisher id** for this VSIX. It is not a Visual Studio Marketplace publisher identity. Changing it later will change the extension identifier.

Python Core is **not** bundled. The extension spawns:

```text
uv run --directory <coreRoot> market-sentinel --provider fake daemon
```

## Install from VSIX

1. Build: `pnpm build` then `pnpm package:vsix` from the repository root (or this package).
2. In Cursor Desktop: Extensions → `...` → Install from VSIX → select `market-sentinel-0.3.0.vsix`.
3. Open a **trusted** workspace that contains the Python Core checkout, or set `marketSentinel.coreRoot`.
4. Confirm `uv` is on PATH or set `marketSentinel.uvPath`.

This extension is `extensionKind: ["ui"]` (local Desktop). Remote SSH / Codespaces / Web are not supported in v0.3.

## Settings

- `marketSentinel.coreRoot`
- `marketSentinel.uvPath`
- `marketSentinel.watchlist`
- `marketSentinel.provider` (`fake` | `replay`)
- `marketSentinel.replayPath`
- `marketSentinel.enableHoverDetails` (default true)
- `marketSentinel.alertToast` (`off` | `critical`, default `off`)

## Manual smoke

See the repository root `README.md` for the v0.3 Cursor Desktop checklist (StatusBar, Hover, Pause/Resume, Restart Core, unread badge, shutdown).
