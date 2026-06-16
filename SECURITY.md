# Security Policy

## Supported Use

This project automates MT5 Strategy Tester research. It does not trade live and does not provide financial advice.

The intended scope is:

- local Windows-only MetaTrader 5 Strategy Tester automation
- deterministic research execution
- offline result parsing and experiment planning

Out of scope:

- live trading
- broker order placement
- account management
- any workflow that clicks Buy/Sell or uses `MetaTrader5.order_send`

## Reporting A Vulnerability

Please do not open a public issue for a security-sensitive problem.

Report privately with:

- affected version or commit
- reproduction steps
- expected safety behavior
- actual behavior
- screenshots or logs if available

If the issue could cause live-trading interaction or unsafe GUI behavior, stop using the tool until the report is reviewed.

## High-Priority Safety Issues

The following should be treated as high severity:

- any path that can place live broker orders
- any path that can click live chart trading controls
- any use of `MetaTrader5.order_send`
- any failure to stop when the expected MT5 UI state is missing
- any leakage of local terminal paths, account identifiers, or private reports
