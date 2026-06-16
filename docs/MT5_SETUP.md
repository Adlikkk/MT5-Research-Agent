# MT5 Setup

## Terminal compatibility

- **Tested on FP Markets MT5.**
- Designed for local MT5 terminals that support Strategy Tester CLI mode
  (`terminal64.exe /config:<ini>`).
- Other broker terminals may require symbol, path, or configuration adjustments
  (symbol suffixes, data folder location, available history).

The fastest way to set up and check your terminal is the wizard, which writes
`config.json` and reports a PASS/WARN map of your environment (data folder,
`MQL5\Experts`, `MQL5\Profiles\Tester`, report-path writability, MetaEditor):

```powershell
mt5-research-agent config-wizard
mt5-research-agent doctor
```

## Intended Terminal State

- MetaTrader 5 is already open
- the target account is visible in the window title
- Strategy Tester can be toggled with `Ctrl+R`
- Expert Advisors to be tested are already available in MT5

## Recommended Local Configuration

- use a dedicated MT5 terminal for research
- disable or avoid any live trading workflows in the same terminal session
- keep the Strategy Tester visible when running automation phases
- use stable symbol names and confirm broker-specific suffixes

## Window Matching

Set `mt5_window_title_contains` in `config.json` to a stable substring of your MT5 window title, for example:

```json
{
  "mt5_window_title_contains": "MetaTrader"
}
```

## Before Running GUI Commands

- open MT5 manually
- confirm Strategy Tester is the only intended target
- confirm no live chart trading buttons should ever be used
- run `python -m mt5_research_agent inspect --backend win32`
- run `python -m mt5_research_agent tester-status`
