# Demo EA

`US30_Demo_Breakout.mq5` is a **demonstration** Expert Advisor, shipped only so
new users can see the research workflow end to end. It is the output of the
MT5 Research Agent EA Lab safe-by-default template.

- **Strategy Tester only. No live trading.** Compile and test it through the MT5
  Strategy Tester, never on a live chart.
- **No guarantee of any kind.** It is not a profitable strategy and is not
  advice. It exists purely as a working example.
- Safety defaults baked in: max one position, no martingale, no grid, ATR-based
  stop, session filter, spread filter, all values exposed as `input`s.
- Only the `.mq5` source is shipped. Compiled `.ex5` binaries are never
  committed.

## Try it

```powershell
# Generate your own safe EA from a prompt (recommended):
mt5-research-agent create-ea-from-prompt research_requests/ea_prompt.md

# Or copy this demo into your terminal's MQL5\Experts folder, compile it in
# MetaEditor (F7), then:
mt5-research-agent first-smoke --ea US30_Demo_Breakout --symbol US30 --timeframe M15 --run
```
