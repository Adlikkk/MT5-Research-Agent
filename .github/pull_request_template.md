<!--
Thanks for contributing! This project is Strategy Tester research only.
Keep the safety model intact: no live trading, no order_send, no Buy/Sell
automation, never hide failed results, no profitability claims.
-->

## Summary

<!-- What does this PR change and why? -->

## Type of change

- [ ] Bug fix
- [ ] Feature (within Strategy Tester research scope)
- [ ] Docs / cleanup
- [ ] Build / packaging

## Checklist

- [ ] `python -m pytest` passes
- [ ] `ruff check .` passes
- [ ] `mypy mt5_research_agent` passes
- [ ] UI (if touched): `cd ui && npm run typecheck && npm run build`
- [ ] No private data, API keys, real reports, `.ex5` binaries, or `config.json` committed
- [ ] Safety model preserved (Strategy Tester only; no live-trading path)
- [ ] Docs updated if behavior changed
