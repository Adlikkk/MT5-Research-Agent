# CLI Reference

Commands are invoked as `mt5-research-agent <command> [args]` (after
`pip install`) or `python -m mt5_research_agent <command> [args]`.
Strategy Tester only. No command places live orders. Agent-facing commands
accept `--json` where noted.

## Getting started (beginner-friendly)

| Command | Purpose |
| --- | --- |
| `examples [--json]` | Print a command cheat sheet |
| `config-wizard` | Detect MT5 and write `config.json` |
| `doctor [--json]` | Environment check with PASS/WARN/FAIL and an overall status |
| `first-smoke --ea <EA> --symbol US30 --timeframe M15 [--run]` | Create and optionally run a guided first smoke test |
| `open-report <test_id> [--json]` | Open a run's report in the OS default app |
| `open-artifacts [--json]` | Open the artifacts and results folders |

## Environment and diagnostics

| Command | Purpose |
| --- | --- |
| `version` | Print package version |
| `doctor` | Run local environment checks |
| `config-wizard [--terminal-path P] [--artifacts-dir D] [--results-dir D] [--portable]` | Detect MT5 and write/update `config.json` without clobbering existing values |
| `terminal-info` | Print MT5 terminal and Experts folder info |
| `print-terminal-folders` | Print likely data/Experts/log/tester/report folders |
| `mt5-process-status` | Inspect whether `terminal64.exe` is running |
| `stop-mt5 [--dry-run] [--confirm] [--all]` | Stop the configured MT5 terminal safely |
| `find-reports --since-minutes N` | Search report folders for recent files |

## Tasks and single runs

| Command | Purpose |
| --- | --- |
| `create-smoke-task ...` | Create a relaxed-acceptance smoke task |
| `show-task <task.json>` | Print a compact task summary |
| `locate-ea <ea>` / `compile-ea <ea>` | Find / compile an EA |
| `preflight-task <task.json>` | EA, report-path, symbol preflight checks |
| `fix-smoke-task <task.json> [--in-place]` | Patch the inferred `Expert=` value |
| `prepare-mt5-files <task.json>` | Generate `.set`/`.ini`, copy native set, print paths |
| `print-ini` / `print-set <task.json>` | Print generated MT5 files |
| `smoke-cli <task.json> [--run] [--timeout-seconds N]` | Preview or run one background CLI backtest |
| `run-task <task.json> [--execution-mode cli\|gui]` | Run one task end-to-end |
| `test-report-strategies <task.json>` | Try report-path strategies until one emits a report |
| `parse-report <report.htm>` | Parse a raw MT5 report into JSON metrics |
| `explain-decision <test_id>` | Explain the stored pass/fail decision |
| `inspect-run <test_id>` | Inspect the latest persisted attempt metadata |

## Experiments, batches, and planning

| Command | Purpose |
| --- | --- |
| `validate-experiment <exp.json>` / `generate-tasks <exp.json>` | Validate / expand a matrix experiment |
| `run-experiment <exp.json> --allow-gui-clicks` | Run matrix-generated tasks sequentially |
| `run-batch <task_dir> [--limit N] [--execution-mode cli\|gui] [--dry-run] [--rerun] [--session]` | BG-4A small batch runner over pre-generated tasks |
| `batch-status` | Show the most recent batch result |

## Research session / MT5 lifecycle

See [EXECUTION_MODES.md](EXECUTION_MODES.md). Only the configured terminal is started/stopped.

| Command | Purpose |
| --- | --- |
| `session-start [--confirm] [--json]` | Open the configured research terminal once and keep it alive |
| `session-status [--json]` | Show the research session terminal status |
| `session-stop [--confirm] [--json]` | Stop ONLY the configured research terminal (never unrelated MT5) |
| `run-batch <dir> --session --allow-gui-clicks` | Run a batch in the open session terminal (GUI reuse, no per-test restart) |
| `run-research <req.md> --session --allow-gui-clicks` | Run research in the open session terminal |
| `create-research-request <prompt.md>` | Scaffold a structured research request |
| `validate-research-request <request.md>` | Validate a request and report TODOs + goal constraints |
| `plan-from-request <request.md>` | Build deterministic draft plan files |
| `plan-next --request <request.md>` | Propose the next explainable batch |
| `run-planned <experiment.json>` | Run a planner-generated experiment |
| `run-research <request.md>` | One-pass sweep + split validation + report |

## Goal-seeking and validation

| Command | Purpose |
| --- | --- |
| `run-goal-seek <request.md> [--max-rounds N]` | Iterate toward the goal; produce a final report |
| `final-report --request <request.md>` | Write a final goal report from stored runs (no MT5 launch) |
| `run-splits <split_experiment.json> --allow-gui-clicks` | Run one candidate across fixed date splits |
| `split-validate <candidate_id> --request <request.md>` | Split-validate an already-tested candidate |
| `summarize-candidate <id>` / `candidate-report <id>` | Write a candidate Markdown report |
| `leaderboard` / `summarize` | Refresh CSV leaderboard / Markdown summary |

## Optimization (single-launch, many combos)

See [OPTIMIZATION.md](OPTIMIZATION.md) for the full guide.

| Command | Purpose |
| --- | --- |
| `optimization-spec-from-request <request.md> [--algorithm A] [--criterion C]` | Derive an optimization spec (numeric ranges) from a research request |
| `plan-optimization <spec.json>` | Preview the generated `.set`/`.ini` and slow-complete grid size (no MT5 launch) |
| `run-optimization <spec.json> [--run] [--timeout-seconds N] [--allow-stop-existing-terminal]` | Run one MT5 optimization (many combos in a single launch) and rank its passes |
| `parse-optimization <report.xml> [--limit N] [--min-profit-factor X] [--max-dd X] [--min-trades X]` | Parse and rank an existing MT5 optimization report |
| `optimization-status <test_id>` | Show the stored result of the most recent optimization |

## EA Lab

| Command | Purpose |
| --- | --- |
| `create-ea-from-prompt <prompt.md>` | Generate a safe-by-default EA (versioned) |
| `compile-ea-lab <ea_name>` | Compile the current EA version and record the result |
| `smoke-test-ea <ea_name> --symbol S --timeframe T [--run]` | Create / run a smoke test for the current version |
| `improve-ea <ea_name> --goal <request.md>` | Goal-driven parameter search; records improvement history |
| `ea-lab-status <ea_name>` | Show current version and last compile/smoke state |
| `ea-version-history <ea_name>` | List all versions |
| `revert-ea <ea_name> --to-version N` | Restore a previous version (with backup) |

## Maintenance and agent integration

| Command | Purpose |
| --- | --- |
| `export-bundle <run_or_request_id>` | Zip a run's or request's artifacts |
| `clean-artifacts [--safe]` | Remove regeneratable `.set`/`.ini` scaffolding (reports/logs preserved) |
| `serve-api [--host 127.0.0.1] [--port 8765]` | Serve the localhost-only JSON API |
| `serve-mcp` | Serve the safe MCP tool surface over stdio (see [MCP_SERVER.md](MCP_SERVER.md)) |
| `agent-run-task <task.json>` / `agent-task-status <id>` / `agent-latest-results` | Concise JSON for agent orchestration |

## Optional AI providers

See [AI_PROVIDERS.md](AI_PROVIDERS.md). Off by default; keys come from env vars, never config.

| Command | Purpose |
| --- | --- |
| `ai-status` | Show AI provider config and usage (no secrets) |
| `ai-config [--provider P] [--model M] [--base-url U] [--enable\|--disable] [--max-calls N] [--max-cost C]` | Configure the optional AI provider |
| `ai-complete <prompt_path> [--system S]` | Run one guarded AI completion |
