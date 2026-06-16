"""AI provider system (master prompt section 8).

Optional, local-first AI configuration. The deterministic CLI works with **no**
AI provider; AI is purely advisory and never gains a trading capability.

Design and safety:

- AI is disabled by default ("local-only, no AI"). Nothing here runs unless the
  user explicitly enables a provider.
- API keys are **never** stored in ``config.json``. The config only records the
  *name* of an environment variable to read the key from at call time.
- Every call carries a safety system prompt: AI must not place trades, bypass
  safety, hide bad results, or claim guaranteed profit. The architecture also
  prevents trading structurally - the AI layer only returns text; it has no tool
  that can touch MT5, orders, or the Strategy Tester.
- Calls are budgeted (max calls, optional max USD) and usage is ledgered so an
  autonomous loop cannot run away.

Supported providers: OpenAI, Anthropic, OpenRouter, Groq, Ollama, and any custom
OpenAI-compatible base URL. The HTTP transport is dependency-free (stdlib
``urllib``) and injectable, so the dispatch logic is unit-tested without network.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from mt5_research_agent.config import resolve_config_path
from mt5_research_agent.result_store import get_results_dir


SAFETY_SYSTEM_PROMPT = (
    "You are an assistant inside the MT5 Research Agent, a Strategy-Tester-only "
    "research tool. Non-negotiable rules: never place trades, never call "
    "order_send, never suggest live trading or clicking Buy/Sell, never bypass "
    "safety, never hide or downplay failed/negative results, and never claim "
    "guaranteed or risk-free profit. You may interpret research prompts, draft "
    "request files, summarize reports, and propose next backtests. Always state "
    "that backtest results are not predictive of live performance."
)


# provider -> (default base_url, default api_key_env, api_style)
PROVIDER_DEFAULTS: dict[str, tuple[str, str, str]] = {
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY", "openai"),
    "anthropic": ("https://api.anthropic.com/v1", "ANTHROPIC_API_KEY", "anthropic"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "openai"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "openai"),
    "ollama": ("http://localhost:11434/v1", "OLLAMA_API_KEY", "openai"),
    "custom": ("", "AI_API_KEY", "openai"),
    "none": ("", "", "none"),
}

# Providers that legitimately run without an API key (local inference).
KEYLESS_PROVIDERS = {"ollama", "none"}


Transport = Callable[[str, dict[str, str], dict[str, Any], int], dict[str, Any]]


class AIDisabledError(RuntimeError):
    """Raised when an AI call is attempted but AI is disabled or unset."""


class AIConfigError(ValueError):
    """Raised when the AI configuration is incomplete (missing model/key)."""


class BudgetError(RuntimeError):
    """Raised when an AI call would exceed the configured call/cost budget."""


@dataclass(slots=True)
class AIProviderConfig:
    provider: str = "none"
    model: str = ""
    base_url: str = ""
    api_key_env: str = ""
    enabled: bool = False
    max_calls: int = 50
    max_cost_usd: float = 0.0
    usd_per_1k_tokens: float = 0.0
    allow_autonomous_planning: bool = False
    require_confirmation: bool = True
    timeout_seconds: int = 60

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AIProviderConfig":
        return cls(
            provider=str(data.get("provider", "none")).strip().casefold() or "none",
            model=str(data.get("model", "")).strip(),
            base_url=str(data.get("base_url", "")).strip(),
            api_key_env=str(data.get("api_key_env", "")).strip(),
            enabled=bool(data.get("enabled", False)),
            max_calls=int(data.get("max_calls", 50)),
            max_cost_usd=float(data.get("max_cost_usd", 0.0)),
            usd_per_1k_tokens=float(data.get("usd_per_1k_tokens", 0.0)),
            allow_autonomous_planning=bool(data.get("allow_autonomous_planning", False)),
            require_confirmation=bool(data.get("require_confirmation", True)),
            timeout_seconds=int(data.get("timeout_seconds", 60)),
        )


@dataclass(slots=True)
class AIResult:
    text: str
    provider: str
    model: str
    total_tokens: int
    est_cost_usd: float


def _provider_defaults(provider: str) -> tuple[str, str, str]:
    return PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["custom"])


def resolve_base_url(config: AIProviderConfig) -> str:
    if config.base_url:
        return config.base_url.rstrip("/")
    return _provider_defaults(config.provider)[0].rstrip("/")


def resolve_api_key_env(config: AIProviderConfig) -> str:
    if config.api_key_env:
        return config.api_key_env
    return _provider_defaults(config.provider)[1]


def resolve_api_style(config: AIProviderConfig) -> str:
    return _provider_defaults(config.provider)[2]


def _read_raw_config(config_path: Path | None = None) -> dict[str, Any]:
    path = config_path or resolve_config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_ai_config(config_path: Path | None = None) -> AIProviderConfig:
    raw = _read_raw_config(config_path)
    ai_section = raw.get("ai")
    if not isinstance(ai_section, dict):
        return AIProviderConfig()
    return AIProviderConfig.from_dict(ai_section)


def save_ai_config(updates: dict[str, Any], config_path: Path | None = None) -> Path:
    path = config_path or resolve_config_path()
    raw = _read_raw_config(path)
    existing = raw.get("ai") if isinstance(raw.get("ai"), dict) else {}
    current = asdict(AIProviderConfig.from_dict(existing)) if existing else asdict(AIProviderConfig())
    # Never persist a secret here - only the env var name is stored.
    for key, value in updates.items():
        if value is not None:
            current[key] = value
    raw["ai"] = current
    path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Usage ledger
# --------------------------------------------------------------------------- #
def ai_usage_path() -> Path:
    return get_results_dir() / "ai_usage.json"


def load_ai_usage() -> dict[str, Any]:
    path = ai_usage_path()
    if not path.exists():
        return {"calls": 0, "total_tokens": 0, "est_cost_usd": 0.0, "history": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"calls": 0, "total_tokens": 0, "est_cost_usd": 0.0, "history": []}
    return data if isinstance(data, dict) else {"calls": 0, "total_tokens": 0, "est_cost_usd": 0.0, "history": []}


def record_ai_usage(provider: str, model: str, tokens: int, cost_usd: float) -> dict[str, Any]:
    usage = load_ai_usage()
    usage["calls"] = int(usage.get("calls", 0)) + 1
    usage["total_tokens"] = int(usage.get("total_tokens", 0)) + tokens
    usage["est_cost_usd"] = round(float(usage.get("est_cost_usd", 0.0)) + cost_usd, 6)
    history = usage.get("history")
    if not isinstance(history, list):
        history = []
    history.append(
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "provider": provider,
            "model": model,
            "tokens": tokens,
            "cost_usd": round(cost_usd, 6),
        }
    )
    usage["history"] = history[-200:]
    ai_usage_path().write_text(json.dumps(usage, indent=2), encoding="utf-8")
    return usage


def check_budget(config: AIProviderConfig) -> None:
    usage = load_ai_usage()
    if config.max_calls > 0 and int(usage.get("calls", 0)) >= config.max_calls:
        raise BudgetError(
            f"AI call budget reached: {usage.get('calls', 0)}/{config.max_calls} calls. "
            "Raise max_calls or reset results/ai_usage.json."
        )
    if config.max_cost_usd > 0 and float(usage.get("est_cost_usd", 0.0)) >= config.max_cost_usd:
        raise BudgetError(
            f"AI cost budget reached: ${usage.get('est_cost_usd', 0.0)}/${config.max_cost_usd}. "
            "Raise max_cost_usd or reset results/ai_usage.json."
        )


# --------------------------------------------------------------------------- #
# HTTP transport (injectable)
# --------------------------------------------------------------------------- #
def default_transport(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - localhost/HTTPS API
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"AI provider HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"AI provider request failed: {exc.reason}") from exc
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"AI provider returned non-JSON response: {body[:500]}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("AI provider returned a non-object JSON response.")
    return parsed


def _openai_request(
    base_url: str, api_key: str, model: str, system: str, prompt: str
) -> tuple[str, dict[str, str], dict[str, Any]]:
    url = f"{base_url}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    return url, headers, payload


def _openai_parse(response: dict[str, Any]) -> tuple[str, int]:
    choices = response.get("choices")
    text = ""
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            text = str(message.get("content", ""))
    usage = response.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    tokens = int(usage.get("total_tokens", 0) or 0)
    return text, tokens


def _anthropic_request(
    base_url: str, api_key: str, model: str, system: str, prompt: str
) -> tuple[str, dict[str, str], dict[str, Any]]:
    url = f"{base_url}/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": model,
        "system": system,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }
    return url, headers, payload


def _anthropic_parse(response: dict[str, Any]) -> tuple[str, int]:
    content = response.get("content")
    text = ""
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict):
            text = str(first.get("text", ""))
    usage = response.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    tokens = int(usage.get("input_tokens", 0) or 0) + int(usage.get("output_tokens", 0) or 0)
    return text, tokens


def complete(
    prompt: str,
    *,
    system: str | None = None,
    config: AIProviderConfig | None = None,
    transport: Transport | None = None,
) -> AIResult:
    config = config or load_ai_config()
    if not config.enabled or config.provider in {"none", ""}:
        raise AIDisabledError(
            "AI is disabled. Enable a provider with `ai-config --provider <p> --enable`. "
            "The deterministic CLI does not require AI."
        )
    if not config.model:
        raise AIConfigError("AI model is not set. Use `ai-config --model <model>`.")

    api_style = resolve_api_style(config)
    base_url = resolve_base_url(config)
    if not base_url:
        raise AIConfigError("AI base_url is not set for this provider. Use `ai-config --base-url <url>`.")

    api_key = os.environ.get(resolve_api_key_env(config), "")
    if not api_key and config.provider not in KEYLESS_PROVIDERS:
        raise AIConfigError(
            f"No API key found in environment variable '{resolve_api_key_env(config)}'. "
            "Set it before making AI calls (keys are never stored in config.json)."
        )

    check_budget(config)

    combined_system = SAFETY_SYSTEM_PROMPT if not system else f"{SAFETY_SYSTEM_PROMPT}\n\n{system}"
    if api_style == "anthropic":
        url, headers, payload = _anthropic_request(base_url, api_key, config.model, combined_system, prompt)
        parser = _anthropic_parse
    else:
        url, headers, payload = _openai_request(base_url, api_key, config.model, combined_system, prompt)
        parser = _openai_parse

    send = transport or default_transport
    response = send(url, headers, payload, config.timeout_seconds)
    text, tokens = parser(response)
    est_cost = round((tokens / 1000.0) * config.usd_per_1k_tokens, 6) if config.usd_per_1k_tokens > 0 else 0.0
    record_ai_usage(config.provider, config.model, tokens, est_cost)
    return AIResult(text=text, provider=config.provider, model=config.model, total_tokens=tokens, est_cost_usd=est_cost)


# --------------------------------------------------------------------------- #
# CLI command entry points
# --------------------------------------------------------------------------- #
def run_ai_status_command() -> int:
    config = load_ai_config()
    usage = load_ai_usage()
    key_env = resolve_api_key_env(config)
    key_present = bool(os.environ.get(key_env, "")) if key_env else False
    print(f"enabled: {config.enabled}")
    print(f"provider: {config.provider}")
    print(f"model: {config.model or '<unset>'}")
    print(f"base_url: {resolve_base_url(config) or '<unset>'}")
    print(f"api_key_env: {key_env or '<none>'} (set: {key_present})")
    print(f"max_calls: {config.max_calls}")
    print(f"max_cost_usd: {config.max_cost_usd}")
    print(f"allow_autonomous_planning: {config.allow_autonomous_planning}")
    print(f"require_confirmation: {config.require_confirmation}")
    print(f"usage: {usage.get('calls', 0)} calls, {usage.get('total_tokens', 0)} tokens, ${usage.get('est_cost_usd', 0.0)}")
    if not config.enabled:
        print("note: AI is off; the deterministic CLI works without it.")
    return 0


def run_ai_config_command(
    *,
    provider: str | None,
    model: str | None,
    base_url: str | None,
    api_key_env: str | None,
    max_calls: int | None,
    max_cost_usd: float | None,
    usd_per_1k_tokens: float | None,
    enable: bool,
    disable: bool,
    allow_autonomous: bool,
    no_autonomous: bool,
) -> int:
    if enable and disable:
        print("Choose either --enable or --disable, not both.")
        return 2
    if provider is not None and provider not in PROVIDER_DEFAULTS:
        print(f"Unsupported provider: {provider}. Expected one of {', '.join(sorted(PROVIDER_DEFAULTS))}.")
        return 2

    updates: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "api_key_env": api_key_env,
        "max_calls": max_calls,
        "max_cost_usd": max_cost_usd,
        "usd_per_1k_tokens": usd_per_1k_tokens,
    }
    if enable:
        updates["enabled"] = True
    if disable:
        updates["enabled"] = False
    if allow_autonomous:
        updates["allow_autonomous_planning"] = True
    if no_autonomous:
        updates["allow_autonomous_planning"] = False

    path = save_ai_config(updates)
    print(f"ai config written: {path}")
    print("reminder: API keys are read from the configured environment variable, never stored in config.json.")
    return run_ai_status_command()


def run_ai_complete_command(prompt_path: str, system: str | None) -> int:
    source = Path(prompt_path)
    prompt = source.read_text(encoding="utf-8") if source.exists() else prompt_path
    try:
        result = complete(prompt, system=system)
    except (AIDisabledError, AIConfigError, BudgetError) as exc:
        print(str(exc))
        return 1
    except Exception as exc:
        print(f"AI call failed: {exc}")
        return 1
    print(result.text)
    print("")
    print(f"-- {result.provider}/{result.model}, {result.total_tokens} tokens, ${result.est_cost_usd} --")
    return 0


def ai_result_to_payload(result: AIResult) -> dict[str, Any]:
    return asdict(result)
