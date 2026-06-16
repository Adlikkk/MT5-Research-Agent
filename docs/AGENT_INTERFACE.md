# Agent Interface

This project exposes a deterministic shell/CLI interface for agent use.

## CLI Surface

- `python -m mt5_research_agent agent-run-task <task.json>`
- `python -m mt5_research_agent agent-task-status <test_id>`
- `python -m mt5_research_agent agent-latest-results`
- `python -m mt5_research_agent locate-ea <ea_name>`
- `python -m mt5_research_agent preflight-task <task.json>`
- `python -m mt5_research_agent mt5-process-status`
- `python -m mt5_research_agent stop-mt5 --dry-run`
- `python -m mt5_research_agent print-terminal-folders`
- `python -m mt5_research_agent find-reports --since-minutes 120`
- `python -m mt5_research_agent prepare-mt5-files <task.json>`
- `python -m mt5_research_agent test-report-strategies <task.json> --timeout-seconds 900`
- `python -m mt5_research_agent smoke-cli <task.json>`
- `python -m mt5_research_agent parse-report <report.htm>`
- `python -m mt5_research_agent explain-decision <test_id>`

These commands are thin wrappers around the existing deterministic background runner.

## JSON Output Mode

The agent commands emit concise JSON so a local AI agent can:

- create a task
- locate and verify the compiled EA
- run preflight checks before launching MT5
- run one task
- poll status
- inspect the latest results without scraping human-readable text

Suggested external-agent sequence for a first smoke test:

1. `create-smoke-task`
2. `locate-ea`
3. `compile-ea` if `.ex5` is missing or stale
4. `preflight-task`
5. `mt5-process-status`
6. `prepare-mt5-files`
7. `smoke-cli`
8. `agent-task-status`
9. `find-reports` if the result is `REPORT_MISSING`
10. `test-report-strategies` only if the native default still does not emit a report
11. `parse-report`
12. `explain-decision`

## Future Adapters

- future MCP adapter: expose the same deterministic commands as local tools
- future local HTTP adapter: wrap the same command contracts behind a local-only service
- future persistent-session adapter: keep a dedicated MT5 research terminal alive for batch runs without using GUI clicks as the default path

## Safety Scope

- Strategy Tester only
- no live trading
- no broker order placement
- never use `MetaTrader5.order_send`
- GUI remains fallback only
