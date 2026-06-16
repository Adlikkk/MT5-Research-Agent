# Task Schema

Research task JSON fields:

- `test_id` optional string
- `name` string
- `ea` string
- `symbol` string
- `timeframe` string
- `period_from` in `YYYY.MM.DD`
- `period_to` in `YYYY.MM.DD`
- `deposit` number
- `model` string
- `inputs` object of string key/value pairs, may be empty for smoke tests that rely on EA defaults
- `acceptance` object

Acceptance fields:

- `min_profit`
- `min_profit_factor`
- `max_equity_dd_pct`
- `min_trades`

Example:

```json
{
  "name": "gold_single_test",
  "ea": "GoldEA",
  "symbol": "XAUUSD_DUKA",
  "timeframe": "H1",
  "period_from": "2020.01.01",
  "period_to": "2026.06.01",
  "deposit": 10000,
  "model": "Every tick based on real ticks",
  "inputs": {
    "TP_R": "2.2",
    "SL_ATR": "1.7"
  },
  "acceptance": {
    "min_profit": 0,
    "min_profit_factor": 1.1,
    "max_equity_dd_pct": 18,
    "min_trades": 100
  }
}
```
