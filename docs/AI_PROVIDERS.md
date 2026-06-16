# AI Providers (optional, local-first)

AI is **optional and off by default**. The deterministic CLI does everything
without it. When enabled, AI is purely advisory — it can interpret prompts,
draft request files, summarize reports, and propose next backtests. It can never
place trades: the AI layer only returns text and has no tool that touches MT5,
orders, or the Strategy Tester.

## Safety

- Disabled by default ("local-only, no AI").
- **API keys are never stored in `config.json`.** The config records the *name*
  of an environment variable; the key is read from the environment at call time.
- Every call carries a safety system prompt (no trades, no `order_send`, never
  hide bad results, never claim guaranteed profit, always note backtests are not
  predictive).
- Calls are budgeted by `max_calls` and optional `max_cost_usd`; usage is
  ledgered in `results/ai_usage.json` so an autonomous loop cannot run away.

## Supported providers

| Provider | Default base URL | Default key env | API style |
| --- | --- | --- | --- |
| `openai` | `https://api.openai.com/v1` | `OPENAI_API_KEY` | OpenAI |
| `anthropic` | `https://api.anthropic.com/v1` | `ANTHROPIC_API_KEY` | Anthropic |
| `openrouter` | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` | OpenAI |
| `groq` | `https://api.groq.com/openai/v1` | `GROQ_API_KEY` | OpenAI |
| `ollama` | `http://localhost:11434/v1` | (keyless) | OpenAI |
| `custom` | (you set `--base-url`) | `AI_API_KEY` | OpenAI |

`ollama` runs locally and needs no key. `custom` works with any
OpenAI-compatible endpoint.

## Commands

```powershell
# Show current AI config + usage (no secrets are printed).
python -m mt5_research_agent ai-status

# Enable a provider. The key stays in your environment, not in config.json.
$env:OPENAI_API_KEY = "sk-..."
python -m mt5_research_agent ai-config --provider openai --model gpt-4o-mini --enable --max-calls 25 --max-cost 2.0

# Local Ollama (no key needed).
python -m mt5_research_agent ai-config --provider ollama --model llama3 --enable

# One guarded completion from a prompt file.
python -m mt5_research_agent ai-complete research_requests/prompt.md --system "Draft a research request."

# Turn it back off.
python -m mt5_research_agent ai-config --disable
```

The config is stored as an `ai` object inside `config.json`; `ai-config` merges
fields without clobbering the rest of the config.

## Config shape

```json
{
  "ai": {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "base_url": "",
    "api_key_env": "OPENAI_API_KEY",
    "enabled": true,
    "max_calls": 25,
    "max_cost_usd": 2.0,
    "usd_per_1k_tokens": 0.0,
    "allow_autonomous_planning": false,
    "require_confirmation": true,
    "timeout_seconds": 60
  }
}
```

`base_url` and `api_key_env` are optional — empty values fall back to the
provider defaults above. Set `usd_per_1k_tokens` if you want the usage ledger to
estimate cost and enforce `max_cost_usd`.
