# DeepSeek Harness (dsh) — MCP client composition (UNVERIFIED)

> Status: **configuration sketch only**. DeepSeek Harness is a developer
> preview and Market Sentinel has **not** verified this integration against
> a live DSH install yet (planned milestone M5). Verify against the official
> `packages/mcp/mcp-client/README.md` in the deepseek-ai/deepseek-harness
> repository before relying on field names.

DeepSeek Harness bridges external MCP servers through its official
`@deepseek-ai/dsh-mcp-client` plugin (stdio and Streamable HTTP; **tools
only** — MCP resources and prompts are not bridged, which is why Market
Sentinel exposes everything as tools).

Sketch of a stdio composition (community-documented Cordis YAML shape):

```yaml
services:
  market-sentinel-mcp:
    name: "@deepseek-ai/dsh-mcp-client"
    config:
      serverName: market-sentinel
      transport: stdio
      command: uv
      args:
        - --directory
        - <repo-root>
        - run
        - market-sentinel
        - mcp
```

Notes:

- `serverName` must be unique per client instance; tools surface to the
  model as `mcp__market-sentinel__<tool>`.
- Live mode: add `--live` to `args` and export the `LONGBRIDGE_*`
  environment variables in the Harness process — never in this file.
- Pin your DSH version; the preview warns about breaking changes.

Once verified, this file will be updated with the exact composition and a
verification record (see the roadmap in `docs/integrations/mcp.md`).
