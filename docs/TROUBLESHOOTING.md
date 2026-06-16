# Troubleshooting

## Invalid `terminal_path`

- run `python -m mt5_research_agent doctor`
- `terminal_path` must exist and end with `terminal64.exe`
- if the path is wrong, fix `config.json` before trying `run-task` or `smoke-cli --run`
- use `python -m mt5_research_agent smoke-cli artifacts/generated_tasks/GOLD-0001.json` to preview the exact command without launching MT5

## MT5 Window Not Found

- confirm MT5 is already open
- confirm `mt5_window_title_contains` matches the visible title
- run `python -m mt5_research_agent inspect --backend win32`

## Strategy Tester Not Detected

- open MT5 manually
- run `python -m mt5_research_agent tester-status`
- if needed, run `python -m mt5_research_agent open-tester --allow-gui-clicks`

## Inputs Grid Cannot Be Read

- run `python -m mt5_research_agent inputs-status`
- expect UIA limitations on some MT5 builds
- use the existing keyboard fallback path

## Requested EA Or Symbol Not Available

- verify the EA is present in MT5
- verify the broker symbol suffix matches the request
- update the task or request file instead of forcing unsupported UI changes

## EA Not Found

- if MT5 exits without a usable report, inspect the JSON log under `artifacts/logs/`
- open the generated `.ini` and confirm `Expert=<ea name>` matches the installed tester EA
- confirm the EA is compiled and visible to Strategy Tester in the configured terminal data folder
- run `python -m mt5_research_agent terminal-info` to inspect likely `MQL5\Experts` folder candidates
- run `python -m mt5_research_agent locate-ea US30_MultiStrategyLab_M15`
- if only `.mq5` is found, run `python -m mt5_research_agent compile-ea US30_MultiStrategyLab_M15`

## Symbol Not Found

- confirm the task symbol exactly matches the broker symbol in MT5, including suffixes such as `_DUKA`
- if MT5 completed without a report, inspect nearby files listed in the run log to see whether MT5 wrote a different artifact instead
- run `python -m mt5_research_agent preflight-task artifacts/generated_tasks/US30-SMOKE-0001.json`
- correct the task JSON or the research request instead of guessing a replacement symbol

## Report Missing

- confirm the MT5 process completed and check whether the run was stored as `REPORT_MISSING`
- run `python -m mt5_research_agent prepare-mt5-files <task.json>`
- confirm the native `.set` was copied into `MQL5\Profiles\Tester`
- confirm the generated `Report=` value is relative and MT5-compatible
- review `artifacts/logs/` for:
  - expected report path
  - native set path
  - report path strategy
  - MT5 `Report=` value
  - expected native report paths
  - discovered report path
  - nearby report-folder files
  - report candidates discovered by extension or creation time
  - tester log candidates
  - terminal log candidates and copied snippets
- run `python -m mt5_research_agent print-terminal-folders`
- run `python -m mt5_research_agent find-reports --since-minutes 120`
- inspect `MetaQuotes\\Tester\\<hash>\\Agent-127.0.0.1-3000\\logs\\*.log` because MT5 may finish the tester run even when no report file is emitted
- open the generated `.ini` and confirm the `Report=` value points to a writable location
- if needed, run `python -m mt5_research_agent test-report-strategies <task.json> --timeout-seconds 900`
- do not delete failed attempts; keep the missing-report run for diagnosis

## Parser And Decision Checks

- run `python -m mt5_research_agent parse-report <report.htm>` to see normalized metrics, parser warnings, and the parsed JSON path
- run `python -m mt5_research_agent explain-decision <test_id>` to see acceptance rules, parsed metrics used, each rule check, and the final effective decision
- use `FAIL_WITH_MISSING_METRICS` when a required acceptance metric could not be read from the report
- use `PARSE_FAILED` when parsing raised an exception before a structured metric payload could be produced
- use ordinary `FAIL` only when the report parsed and a real metric violated the configured rule
- for smoke tests, keep acceptance relaxed so infrastructure validation is not confused with strategy rejection

## Terminal Already Running

- run `python -m mt5_research_agent mt5-process-status`
- if the configured terminal path is already running, background CLI mode will refuse to launch a second instance
- run `python -m mt5_research_agent stop-mt5 --dry-run` first
- if the target path is correct, run `python -m mt5_research_agent stop-mt5 --confirm`
- for one-shot runs, `smoke-cli` and `run-task` also support `--allow-stop-existing-terminal`

## Process Timeout

- rerun with a larger timeout, for example `python -m mt5_research_agent smoke-cli artifacts/generated_tasks/GOLD-0001.json --run --timeout-seconds 7200`
- inspect the run log for `process_started_at`, `process_ended_at`, and `duration_seconds`
- confirm the EA and symbol are valid so MT5 is not stalling before report generation
- the timed-out attempt is kept in storage as a failed run for later review

## Smoke-CLI First Run

- run `python -m mt5_research_agent create-smoke-task --test-id US30-SMOKE-0001 --ea US30_MultiStrategyLab_M15 --symbol US30 --timeframe M15 --period-from 2024.01.01 --period-to 2024.02.01 --deposit 10000`
- run `python -m mt5_research_agent print-ini artifacts/generated_tasks/US30-SMOKE-0001.json`
- run `python -m mt5_research_agent print-set artifacts/generated_tasks/US30-SMOKE-0001.json`
- run `python -m mt5_research_agent preflight-task artifacts/generated_tasks/US30-SMOKE-0001.json`
- run `python -m mt5_research_agent smoke-cli artifacts/generated_tasks/US30-SMOKE-0001.json`
- confirm the printed command matches your real MT5 installation before adding `--run`
- the run will be stored with `REPORT_MISSING`

## One-Shot Mode

- default CLI mode uses `ShutdownTerminal=1`
- this means smoke runs normally start MT5, run one tester config, then let the terminal exit
- use `--keep-terminal-open` only for short manual diagnosis after a smoke run
- longer future batch modes should use a dedicated persistent research-session path instead of reopening MT5 for every single test

## MT5 restarts for every test

That is expected in one-shot CLI mode (smoke/debug). For many tests, use
optimizer fast-mode (`run-optimization`, one launch many combos) or a persistent
research session:

```powershell
mt5-research-agent session-start
mt5-research-agent session-status
mt5-research-agent run-batch <dir> --session --allow-gui-clicks
mt5-research-agent session-stop --confirm
```

If `run-batch --session` refuses, it is telling you honestly that session reuse
needs GUI automation (`--allow-gui-clicks`); otherwise use optimizer fast-mode.
`session-stop` only stops the configured research terminal — never unrelated MT5
instances. See [EXECUTION_MODES.md](EXECUTION_MODES.md).
