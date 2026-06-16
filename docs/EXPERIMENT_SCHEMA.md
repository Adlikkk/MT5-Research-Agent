# Experiment Schema

## Matrix Experiment

Used for deterministic cartesian sweeps.

Fields:

- `name`
- `base_task`
- `matrix`
- `limits.max_tests`
- `limits.stop_after_failures`

## Split Validation Experiment

Used for fixed date-split validation.

Fields:

- `name`
- `base_task`
- `splits[]`
- `acceptance`

## Planned Experiment

Used by the robust planner to run an explicit batch of selected combinations.

Fields:

- `name`
- `request_slug`
- `base_task`
- `limits`
- `tasks[]`

Each `tasks[]` entry is a partial input override object, for example:

```json
{
  "TP_R": "2.1",
  "SL_ATR": "1.7",
  "ADX_Hard_Min": "18"
}
```
