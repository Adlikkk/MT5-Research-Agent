# Execution Modes

The agent can run Strategy Tester work four ways. Pick by goal: validate
plumbing, sweep many parameters, run a queue without restarting MT5, or fall
back to GUI when a terminal is awkward. **All modes are Strategy Tester only —
none place live orders.**

| Mode | What it does | MT5 lifecycle | Best for |
| --- | --- | --- | --- |
| One-shot CLI | `terminal64.exe /config:<ini>` per test | starts + stops MT5 each test (`ShutdownTerminal=1`) | smoke / debug / reproducible single runs |
| Optimizer fast-mode | one launch evaluates many combinations | one start/stop for the whole sweep | many parameter combinations |
| Persistent session | keep one terminal open, drive it via GUI | one start; stop only when you say so | smaller task queues without per-test restarts |
| GUI fallback | UI automation of the open tester | uses whatever terminal is open | terminals where CLI `/config` is unreliable |

## 1. One-shot CLI (default; smoke/debug)

```powershell
mt5-research-agent smoke-cli artifacts/generated_tasks/US30-SMOKE-0001.json --run
mt5-research-agent first-smoke --ea <YourEA> --symbol US30 --timeframe M15 --run
```

Each run launches its own terminal instance with a generated `.ini`/`.set`, runs
one tester pass, writes the report, and shuts the terminal down. Deterministic
and isolated — ideal for the first smoke test and for diagnostics. `first-smoke`
defaults to the fast **`1 minute OHLC`** model (infrastructure validation).

## 2. Optimizer fast-mode (many combinations)

```powershell
mt5-research-agent run-optimization <spec.json> --run --timeout-seconds 3600
```

One MT5 launch evaluates the whole parameter grid (`Optimization=` in the ini).
This is the **preferred** way to sweep many combinations because it does not
restart MT5 per combination. See [OPTIMIZATION.md](OPTIMIZATION.md).

## 3. Persistent research session (keep one terminal open)

```powershell
mt5-research-agent session-start            # open the configured terminal once
mt5-research-agent session-status
mt5-research-agent run-batch <dir> --session --allow-gui-clicks
mt5-research-agent run-research <req.md> --session --allow-gui-clicks
mt5-research-agent session-stop --confirm   # stop ONLY the configured terminal
```

The session keeps **one** dedicated research terminal open. Because MT5 cannot
inject a new background `/config` run into an already-running terminal on the
same data folder, session runs reuse the open terminal through **GUI execution**
(hence `--allow-gui-clicks`). Without GUI clicks the agent refuses to silently
restart MT5 per test and instead points you to optimizer fast-mode (for sweeps)
or one-shot mode. Only the configured terminal path is ever started or stopped —
unrelated MT5 terminals are never touched.

**Honesty note:** for large sweeps, prefer optimizer fast-mode. Session mode is
for smaller queues where GUI automation is acceptable.

## 4. GUI fallback only

```powershell
mt5-research-agent run-task <task.json> --execution-mode gui --allow-gui-clicks
```

Direct Strategy Tester UI automation. Use only when background CLI mode is not
sufficient for a specific MT5 setup; it is the most fragile path and always
requires the explicit `--allow-gui-clicks` flag.

## Smoke vs research

- **Smoke test = infrastructure validation.** Fast/deterministic model
  (`1 minute OHLC`), relaxed acceptance. It proves the pipeline (launch → report
  → parse → decision) works, not that a strategy is good.
- **Research run = quality/performance validation.** Use
  `Every tick based on real ticks` for execution-quality fidelity, with real
  acceptance thresholds and split validation.
