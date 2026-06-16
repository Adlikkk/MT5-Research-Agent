# Agent API (Local HTTP)

The local HTTP API exposes a safe subset of the research surface for another
agent or UI to call. It binds to `127.0.0.1` only and refuses non-localhost
hosts, so reports and config are never exposed publicly. No endpoint places a
live order.

## Start the server

```powershell
python -m mt5_research_agent serve-api --host 127.0.0.1 --port 8765
```

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness + version |
| GET | `/config` | Non-sensitive operational config (no raw terminal path) |
| GET | `/tools` | List of safe tool names |
| GET | `/runs` | Latest stored runs |
| GET | `/leaderboard` | Refresh and return leaderboard rows |
| GET | `/reports/<test_id>` | Stored status + parsed metrics for one run |
| POST | `/research-requests` | Body `{"request_path": "..."}` → validate a request |
| POST | `/planner/next` | Body `{"request_path": "..."}` → propose the next batch |
| POST | `/ea/create` | Body `{"prompt_path": "..."}` → generate an EA |

Example:

```powershell
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/runs
curl -X POST http://127.0.0.1:8765/research-requests -d '{"request_path":"research_requests/us30_goal.md"}'
```

## Safe tool names

The `/tools` endpoint lists the safe tool surface that maps onto CLI commands:

```
validate_environment, locate_ea, compile_ea, create_smoke_task, run_task,
run_batch, get_task_status, get_leaderboard, parse_report, explain_decision,
create_research_request, plan_next, split_validate, create_ea_from_prompt,
improve_ea
```

## MCP

A dedicated MCP server is deferred. The same safe surface is reachable today
through this localhost HTTP API and through the deterministic CLI (which emits
JSON for `agent-*` commands).
