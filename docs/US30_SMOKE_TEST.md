# US30 Smoke Test

Use this path to validate that the real EA, symbol, and MT5 terminal can produce any Strategy Tester report at all.

## Commands

```powershell
python -m mt5_research_agent create-smoke-task --test-id US30-SMOKE-0001 --ea US30_MultiStrategyLab_M15 --symbol US30 --timeframe M15 --period-from 2024.01.01 --period-to 2024.02.01 --deposit 10000
python -m mt5_research_agent locate-ea US30_MultiStrategyLab_M15
python -m mt5_research_agent compile-ea US30_MultiStrategyLab_M15
python -m mt5_research_agent preflight-task artifacts/generated_tasks/US30-SMOKE-0001.json
python -m mt5_research_agent mt5-process-status
python -m mt5_research_agent print-terminal-folders
python -m mt5_research_agent prepare-mt5-files artifacts/generated_tasks/US30-SMOKE-0001-FIXED.json
python -m mt5_research_agent show-task artifacts/generated_tasks/US30-SMOKE-0001.json
python -m mt5_research_agent print-ini artifacts/generated_tasks/US30-SMOKE-0001.json
python -m mt5_research_agent print-set artifacts/generated_tasks/US30-SMOKE-0001.json
python -m mt5_research_agent fix-smoke-task artifacts/generated_tasks/US30-SMOKE-0001.json
python -m mt5_research_agent smoke-cli artifacts/generated_tasks/US30-SMOKE-0001.json
python -m mt5_research_agent smoke-cli artifacts/generated_tasks/US30-SMOKE-0001.json --run --timeout-seconds 900
python -m mt5_research_agent parse-report artifacts/raw_reports/US30-SMOKE-0001-FIXED.htm
python -m mt5_research_agent explain-decision US30-SMOKE-0001-FIXED
python -m mt5_research_agent inspect-run US30-SMOKE-0001
python -m mt5_research_agent find-reports --since-minutes 120
```

## What To Check

- `Expert=` matches the compiled tester EA name
- `locate-ea` finds the `.ex5` in a visible `MQL5\Experts` folder
- `compile-ea` either builds the `.ex5` or prints exact manual compile steps
- `preflight-task` passes before you spend more time on runtime diagnosis
- `Symbol=` matches the broker symbol visible in Strategy Tester
- `Period=` is `M15`
- the report path is writable
- `mt5-process-status` shows that the configured terminal is not already running
- `print-terminal-folders` shows both the terminal data tree and the separate `MetaQuotes\Tester` tree
- `prepare-mt5-files` copies the `.set` into `MQL5\Profiles\Tester` and shows the exact native `Report=` strategy
- the MT5 process does not exit immediately without a report
- `inspect-run` includes `report_candidates`, `tester_log_candidates`, `terminal_log_candidates`, and the generated `ShutdownTerminal` value

If the process exits in under three seconds with `REPORT_MISSING`, treat that as a tester configuration failure first, not a strategy-performance outcome.

If the process emits a real report, use `parse-report` and `explain-decision` before changing the task:

- `FAIL` means a parsed metric really violated a rule
- `FAIL_WITH_MISSING_METRICS` means the report was found but one or more acceptance metrics could not be read
- `PARSE_FAILED` means report parsing itself raised an exception

For smoke tasks, keep acceptance relaxed. The goal is to prove MT5 background execution and report parsing, not to reject a candidate on tight performance thresholds.

Typical next causes in that case:

- `.ex5` is missing
- `.ex5` is in the wrong `Experts` folder
- `Expert=` needs a relative subfolder path such as `Strategies\US30_MultiStrategyLab_M15`
- `US30` is not the exact symbol name in that terminal
- MT5 wrote the reason into terminal logs, which `inspect-run` now surfaces
- the same terminal was already running, so MT5 refused the second CLI launch
- MT5 finished the tester run but did not emit a report file where expected; inspect `MetaQuotes\Tester\...\Agent-127.0.0.1-3000\logs`

If the default native strategy still does not emit a report, run:

```powershell
python -m mt5_research_agent test-report-strategies artifacts/generated_tasks/US30-SMOKE-0001-FIXED.json --timeout-seconds 900
```

The first strategy that emits a report is the winning strategy for that terminal setup.

For short manual diagnosis only, you can keep MT5 open after the run:

```powershell
python -m mt5_research_agent smoke-cli artifacts/generated_tasks/US30-SMOKE-0001.json --run --timeout-seconds 900 --keep-terminal-open
```
