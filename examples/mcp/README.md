# MCP client configuration examples

Fragments for pointing MCP clients at the Market Sentinel stdio server.
All paths are placeholders — replace `<repo-root>` with **your** clone
location and `uv` with its absolute path if it is not on the client's
PATH.

Prerequisite (once, in the repo):

```bash
uv sync --extra mcp
```

Smoke test before configuring any host:

```bash
uv run market-sentinel mcp   # Ctrl+C to stop; stdio stays silent, logs go to stderr
```

## Files

| File | Purpose |
|---|---|
| `zcode-mcp-servers.json` | `mcp.servers` fragment for `~/.zcode/cli/config.json` (user scope) or `<repo>/.zcode/config.json` (workspace scope) — verified against ZCode 0.16.9 |
| `any-mcp-client.json` | Generic `mcpServers` fragment (Claude Desktop-style clients) |
| `deepseek-harness.md` | DeepSeek Harness `dsh-mcp-client` composition — verified against DSH 0.2.0-rc.2 (headless, stdio) |

## Platform notes

- **Windows**: JSON needs escaped backslashes in paths; prefer the absolute
  path to `uv.EXE` as `command` (e.g. `D:\\uv\\bin\\uv.EXE`).
- **macOS / Linux**: `command: "uv"` works only if the client process can
  find `uv` on PATH; otherwise use the absolute path (`which uv`).
- Replay mode needs `--replay <fixture>`; live Longbridge additionally needs
  `--live` plus the `LONGBRIDGE_*` environment variables — never put
  credentials in the config file itself.

See [docs/integrations/mcp.md](../../docs/integrations/mcp.md) for the tool
surface, error codes, and the verified-vs-supported matrix.
