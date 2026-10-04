# DeepSeek Harness (DSH) — MCP client composition

> Status: **verified against DSH 0.2.0-rc.2** (2026-10-05, Windows; see
> [docs/integrations/deepseek-harness.md](../../docs/integrations/deepseek-harness.md)
> for the full verification record). DSH remains a developer preview —
> re-verify after upgrading.

The `@deepseek-ai/dsh-mcp-client` plugin ships **inside** the `dsh` npm
package (no separate install). Register the Market Sentinel stdio server as
a Cordis entry — either persistently in a profile's `cordis.patch.yml`
(user-private, never commit it) or per-invocation via `--patch`.

## Per-invocation overlay (used for verification)

`overlay.yml`:

```yaml
- insert:
    - id: mcp-market-sentinel
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: market-sentinel
        transport: stdio
        command: <uv-absolute-path>
        args: ['--directory', '<repo-root>', 'run', 'market-sentinel', 'mcp']
        failOnStartupError: false
```

Run:

```bash
dsh headless --patch overlay.yml "Inspect the current MarketSentinel market state using its MCP tools."
```

Replay event flow (real events appear after the runtime has ticked for a
while; poll `get_recent_events` instead of relying on shell sleeps — DSH's
headless sandbox may deny shell use):

```yaml
- insert:
    - id: mcp-market-sentinel-replay
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: market-sentinel-replay
        transport: stdio
        command: <uv-absolute-path>
        args: ['--directory', '<repo-root>', 'run', 'market-sentinel',
               '--provider', 'replay', '--replay', '<repo-root>/tests/fixtures/multi_a_share_ui.jsonl',
               'mcp']
        failOnStartupError: false
```

## Field reference (dsh-mcp-client 0.2.0-rc.2)

| Field | Default | Meaning |
|---|---|---|
| `serverName` | required | Tool namespace (`mcp__<serverName>__<tool>`), unique per scope |
| `transport` | required | `stdio` or `streamable-http` |
| `command` / `args` / `env` / `cwd` | — | stdio spawn |
| `toolCallTimeoutMs` | 60000 | Per tools/call timeout |
| `failOnStartupError` | false | false: startup failure logs an error and yields no tools |
| `reconnect.enabled` | true | Auto-reconnect (500ms doubling backoff, 30s cap, 10 attempts) |

Live mode: append `--live` to `args` and export the `LONGBRIDGE_*`
environment variables in the DSH process — never in this file.

## Platform notes

- **Windows**: use the absolute path to `uv.exe` as `command` (forward
  slashes are accepted); `<repo-root>` must be absolute.
- **macOS / Linux**: `command: uv` only if DSH's process PATH contains uv;
  otherwise use the absolute path.
- Check composition without booting a model:
  `dsh --profile headless --patch overlay.yml --dump-config`.
