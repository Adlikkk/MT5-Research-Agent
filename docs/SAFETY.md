# Safety

## Positioning

This project automates MT5 Strategy Tester research. It does not trade live and does not provide financial advice.

## Hard Rules

1. No live trading.
2. No broker order placement.
3. Never use `MetaTrader5.order_send`.
4. Never click Buy/Sell or any live chart trading button.
5. Only operate inside Strategy Tester.
6. Always save logs and screenshots before and after GUI actions.
7. Stop immediately if expected MT5 UI state is not found.

## Safe Usage Model

- Codex may create or edit local request, task, and experiment files.
- The deterministic Python tool executes the actual MT5 workflow.
- Every GUI-affecting command requires `--allow-gui-clicks`.
- Missing or ambiguous UI state should be treated as a hard stop, not a retry cue.

## Operational Advice

- use a dedicated local MT5 terminal for research only
- keep account risk isolated from research workflows
- review screenshots and logs after failures before rerunning
