# Background Mode

BG-1 changes the default execution path to MT5 background CLI mode.

## Default Path

1. Generate task JSON.
2. Generate one `.set` file from task inputs.
3. Copy that `.set` into `MQL5\Profiles\Tester\<test_id>.set`.
4. Generate one `.ini` file for MT5 Strategy Tester with native tester paths.
5. Launch `terminal64.exe /config:<ini>`.
6. Wait for process exit with timeout.
7. Discover the raw report.
8. Parse and store the result.

Before launch, the runner now checks whether the configured `terminal64.exe` is already running. If it is, the CLI run fails fast with `TERMINAL_ALREADY_RUNNING` unless you explicitly stop that matching process first.

The default CLI mode is still a one-shot mode:

1. open MT5 in background
2. run one Strategy Tester config
3. wait for process exit
4. discover reports and logs
5. let MT5 shut down by default

This is deliberate for safer smoke testing and reproducible single-run diagnostics.

## Generated Files

- `artifacts/generated_tasks/<test_id>.json`
- `artifacts/generated_sets/<test_id>.set`
- `artifacts/generated_ini/<test_id>.ini`
- `<terminal_data>\MQL5\Profiles\Tester\<test_id>.set`
- `artifacts/raw_reports/<test_id>.htm`
- `artifacts/parsed_reports/<test_id>.json`
- `artifacts/logs/*.json`

## Native Tester Paths

MT5 command-line tester mode is more reliable when:

- `ExpertParameters=` points to a `.set` filename that exists inside `MQL5\Profiles\Tester`
- `Report=` stays relative to the terminal data folder instead of pointing at an arbitrary absolute filesystem path

The default report strategy is now `terminal_relative_reports`, which writes:

```ini
ExpertParameters=<test_id>.set
Report=reports\<test_id>
```

Use this preparation command before a real smoke run:

```powershell
python -m mt5_research_agent prepare-mt5-files artifacts/generated_tasks/US30-SMOKE-0001-FIXED.json
```

## First Real Smoke Test

1. Configure `terminal_path` to the real MT5 executable:

```json
{
  "terminal_path": "C:/Program Files/MetaTrader 5/terminal64.exe"
}
```

2. Verify the config and paths:

```powershell
python -m mt5_research_agent doctor
```

3. Generate and inspect one task:

```powershell
python -m mt5_research_agent create-smoke-task --test-id US30-SMOKE-0001 --ea US30_MultiStrategyLab_M15 --symbol US30 --timeframe M15 --period-from 2024.01.01 --period-to 2024.02.01 --deposit 10000
python -m mt5_research_agent show-task artifacts/generated_tasks/US30-SMOKE-0001.json
python -m mt5_research_agent print-ini artifacts/generated_tasks/US30-SMOKE-0001.json
python -m mt5_research_agent print-set artifacts/generated_tasks/US30-SMOKE-0001.json
python -m mt5_research_agent smoke-cli artifacts/generated_tasks/US30-SMOKE-0001.json
```

4. Review the printed `.set` path, `.ini` path, expected report path, and exact MT5 command.

5. Only after the preview looks correct, launch the real background test:

```powershell
python -m mt5_research_agent smoke-cli artifacts/generated_tasks/US30-SMOKE-0001.json --run --timeout-seconds 900
python -m mt5_research_agent inspect-run US30-SMOKE-0001
python -m mt5_research_agent find-reports --since-minutes 120
```

6. Review persisted outputs:

```powershell
python -m mt5_research_agent parse-report artifacts/raw_reports/US30-SMOKE-0001-FIXED.htm
python -m mt5_research_agent explain-decision US30-SMOKE-0001-FIXED
python -m mt5_research_agent inspect-run US30-SMOKE-0001-FIXED
python -m mt5_research_agent leaderboard
python -m mt5_research_agent summarize
```

The smoke command keeps failed attempts, stores process metadata, and records:

- `REPORT_MISSING` when MT5 completed but no report file was found
- `PARSE_FAILED` when report parsing raised an exception
- `FAIL_WITH_MISSING_METRICS` when the report exists but required acceptance metrics are unavailable
- `FAIL` only when a real parsed metric violates an acceptance rule
- `PASS` when all required rules pass

## Keep-Open Diagnostics

If you need MT5 to remain open after a smoke test so you can inspect the tester state manually, use:

```powershell
python -m mt5_research_agent smoke-cli artifacts/generated_tasks/US30-SMOKE-0001.json --run --timeout-seconds 900 --keep-terminal-open
```

This sets `ShutdownTerminal=0` in the generated INI.

Use this only for short manual diagnosis. It is not the long-term batch execution model.

## Report Discovery Checklist

If MT5 appears to run but the stored result is still `REPORT_MISSING`:

1. Run `python -m mt5_research_agent inspect-run <test_id>`.
2. Run `python -m mt5_research_agent print-terminal-folders`.
3. Run `python -m mt5_research_agent find-reports --since-minutes 120`.
4. Check tester and agent logs under `MetaQuotes\\Tester\\...`.
5. Confirm whether the tester finished successfully but simply did not emit a report file.

Future batch-oriented execution should move toward CLI optimization or a persistent research-session mode so long experiments do not reopen and close MT5 for every test.

## Strategy Fallbacks

If MT5 still completes the tester run but no report is emitted, try:

```powershell
python -m mt5_research_agent test-report-strategies artifacts/generated_tasks/US30-SMOKE-0001-FIXED.json --timeout-seconds 900
```

This tries:

- `terminal_relative_reports`
- `terminal_root_stem`
- `terminal_mql5_files`
- `artifacts_absolute_current`

It stops at the first strategy that produces a report and prints the winning strategy.

## Single Instance Rule

- the best long-term setup is a dedicated MT5 research terminal instance
- do not use the same terminal interactively while background CLI tests are running
- use `python -m mt5_research_agent mt5-process-status` before a smoke test if you are unsure
- use `python -m mt5_research_agent stop-mt5 --confirm` only for the configured research terminal path

## Safety

- Strategy Tester only
- no live trading
- no broker order placement
- no `MetaTrader5.order_send`
- failed attempts are preserved and stored

## Persistent research session vs one-shot

Background CLI (`smoke-cli`, `run-task --execution-mode cli`) launches its own
terminal per test and shuts it down — ideal for smoke/debug, but it restarts MT5
every test. To avoid per-test restarts:

- **Optimizer fast-mode** (`run-optimization`) — one launch, many combinations.
- **Persistent session** (`session-start` / `session-status` / `session-stop`) —
  keep one terminal open and reuse it via GUI (`run-batch --session
  --allow-gui-clicks`). MT5 cannot inject a new `/config` run into a running
  terminal, so session reuse goes through GUI automation. Only the configured
  terminal is ever started/stopped. See [EXECUTION_MODES.md](EXECUTION_MODES.md).
