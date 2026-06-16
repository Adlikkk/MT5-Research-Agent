# MCP Server

`serve-mcp` exposes the **safe** agent surface to MCP clients over stdio
(JSON-RPC 2.0). It is dependency-free and binds to nothing — it just reads
stdin and writes stdout, so a client launches it as a subprocess.

```powershell
python -m mt5_research_agent serve-mcp
```

## Safety

MT5-launching tools (`run-task`, `run-batch`, `run-optimization --run`,
`split-validate`, `improve-ea`) are **deliberately not exposed** over MCP. They
start the Strategy Tester and stay on the explicit CLI so an automated agent can
never trigger an MT5 launch through this server. Everything reachable via MCP is
non-destructive, never places trades, and never hides results (tool errors are
returned as `isError: true` content, not swallowed).

## Exposed tools

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

## Protocol

Standard MCP handshake: `initialize` → `notifications/initialized` →
`tools/list` → `tools/call`. `ping` is supported. Results from `tools/call` are
returned as a single text content block containing pretty-printed JSON.

Example session (line-delimited JSON-RPC on stdin):

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_leaderboard","arguments":{"limit":5}}}
```

The routing is a pure function (`handle_mcp_message`) so the protocol and tools
are unit-tested without any stdio plumbing.
