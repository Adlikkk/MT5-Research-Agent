# Goal-Seeking

The goal-seeking loop searches for a robust parameter set that reaches a target
such as "+250% over 5 years under 25% drawdown". It never optimizes for raw
profit alone and never claims guaranteed results.

## Goal constraints

Add a `## Goal constraints` block to a research request:

```markdown
## Goal constraints
- target_total_return_pct: 250
- target_period_years: 5
- max_equity_drawdown_pct: 25
- min_profit_factor: 1.2
- min_trades: 250
- must_validate_splits: true
- max_tests: 200
- max_runtime_minutes: 360
- objective: maximize robust return under drawdown and validation constraints
```

All keys are optional; sensible defaults apply, and missing constraints are
simply not enforced. The goal is separate from per-test "Hard limits"
(acceptance), which decide whether a single backtest passes.

## How the loop works

1. Run the bounded baseline sweep from the request's parameter space.
2. Rank candidates and split-validate the strongest raw candidates.
3. If no robust candidate is found and budget remains, ask the planner for
   nearby untested combinations and run another round.
4. Stop when the target is robustly reached, the test budget (`max_tests`) or
   runtime (`max_runtime_minutes`) is exhausted, or progress stalls.

A candidate is **robust** only when it meets the raw goal metrics **and**
(when `must_validate_splits` is true) passes split validation.

## Outputs

```powershell
python -m mt5_research_agent run-goal-seek research_requests/us30_goal.md --max-rounds 3
python -m mt5_research_agent final-report --request research_requests/us30_goal.md
```

The final report (`results/final_report_<slug>.md`) always states honestly
whether the target was reached. When it was not, it names the closest raw
candidate, why it was rejected, and the next suggested research direction:

```text
Target not robustly reached.
Best robust candidate: none
Closest raw candidate: `US30-0007` return=180% pf=1.3 dd=22% trades=410 splits_validated=False
Rejected because: SPLITS_FAILED
Next suggested research direction: ...
```
