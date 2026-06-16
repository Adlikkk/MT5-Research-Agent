# EA Lab

The EA Lab creates, compiles, smoke-tests, versions, and improves MetaTrader 5
Expert Advisors. It only ever drives the Strategy Tester.

## Safety defaults of generated EAs

Generated EAs default to:

- one position at a time (`InpMaxPositions`, refuses values < 1)
- no martingale, no grid, no unlimited stacking
- explicit risk controls (`InpLots` / `InpRiskPercent`, ATR-based stops)
- a session filter and a spread filter
- every meaningful value exposed as an MQL5 `input`
- no hidden network calls and no hardcoded account credentials

## Folder layout

```text
artifacts/ea_lab/<ea_name>/
  source/              active source (.mq5)
  versions/            every versioned source + pre-revert backups
  compiled/            compiled outputs (when available)
  compile_logs/        compile evidence
  smoke_tests/         generated smoke task JSON
  research_requests/   request files used to improve this EA
  improvement_history/ improvement records
  reports/             reports for this EA
  metadata.json        current version + version/improvement history
```

## Workflow

```powershell
python -m mt5_research_agent create-ea-from-prompt research_requests/ea_prompt.md
python -m mt5_research_agent compile-ea-lab US30_Breakout_Lab
python -m mt5_research_agent smoke-test-ea US30_Breakout_Lab --symbol US30 --timeframe M15
python -m mt5_research_agent smoke-test-ea US30_Breakout_Lab --symbol US30 --timeframe M15 --run
python -m mt5_research_agent improve-ea US30_Breakout_Lab --goal research_requests/us30_goal.md
python -m mt5_research_agent ea-version-history US30_Breakout_Lab
python -m mt5_research_agent revert-ea US30_Breakout_Lab --to-version 1
```

## Versioning

A working EA version is never overwritten without keeping the previous source in
`versions/`. Each version records the reason for the change; compile and smoke
results are attached to the version as they happen. `improve-ea` performs
goal-driven **parameter** search first (recorded in the improvement history).
Automatic source-code mutation is not yet implemented — code changes remain a
manual, evidence-backed step.

## EA prompt format

```markdown
## EA name
US30 Breakout Lab

## Symbol
US30

## Timeframe
M15

## Strategy
Breakout with ATR stop loss, TP_R input, session filter, max one position,
no martingale, tester-safe inputs.
```

Generated EAs are written into a sandbox subfolder
`MQL5\Experts\MT5ResearchAgentLab\` so your own EAs are never touched.
