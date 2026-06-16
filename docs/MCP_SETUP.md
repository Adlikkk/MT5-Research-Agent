# MCP Setup (Claude Desktop / Cursor)

The MT5 Research Agent ships an MCP server (`serve-mcp`) so AI agents can
**inspect, plan, explain, and parse** your research over stdio JSON-RPC. It is
safe by design — see Safety below.

## Health check

```powershell
mt5-research-agent serve-mcp --selfcheck
```

This runs the MCP handshake in-process and prints health JSON (protocol version,
server info, and the tool list). Exit code 0 means the server is ready.

## Claude Desktop

Add to `claude_desktop_config.json` (Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "mt5-research-agent": {
      "command": "mt5-research-agent",
      "args": ["serve-mcp"]
    }
  }
}
```

If the console script is not on PATH, use the module form:

```json
{
  "mcpServers": {
    "mt5-research-agent": {
      "command": "python",
      "args": ["-m", "mt5_research_agent", "serve-mcp"]
    }
  }
}
```

## Cursor

In `~/.cursor/mcp.json` (or the project `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "mt5-research-agent": {
      "command": "mt5-research-agent",
      "args": ["serve-mcp"]
    }
  }
}
```

## Tools exposed

All read/plan/parse — none launch MT5:

| Tool | Purpose |
| --- | --- |
| `validate_environment` | Run `doctor` checks |
| `get_leaderboard` | Refresh and return the top runs |
| `get_task_status` | Latest stored status for a `test_id` |
| `parse_report` | Parse an MT5 HTML report into metrics |
| `locate_ea` | Find `.mq5`/`.ex5` files for an EA |
| `create_research_request` | Scaffold a request from a prompt |
| `validate_research_request` | Validate a request, report TODOs |
| `plan_next` | Propose the next explainable batch |
| `plan_optimization` | Preview optimizer files + grid (no launch) |
| `parse_optimization` | Parse and rank an optimization `.xml` |
| `create_ea_from_prompt` | Generate a safe-by-default EA |

## Safety limits

- **MT5-launching tools are intentionally NOT exposed over MCP.** Backtests,
  optimization runs, split validation, and EA improvement stay on the explicit
  CLI / local API **job queue**, so an agent can never start an MT5 run through
  MCP. To run research, prefer the local API job endpoints (`POST /jobs`), which
  are guarded and async.
- Strategy Tester only. No live trading. No `order_send`. No Buy/Sell.
- Tool errors are returned as `isError: true` content — never hidden.

For running guarded research jobs programmatically, use the local HTTP API
(`serve-api` → `POST /jobs`) rather than MCP. See [AGENT_API.md](AGENT_API.md).
