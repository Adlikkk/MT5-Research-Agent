from __future__ import annotations

import json
from pathlib import Path

import mt5_research_agent.providers as providers
from mt5_research_agent.providers import (
    AIConfigError,
    AIDisabledError,
    AIProviderConfig,
    BudgetError,
    complete,
    load_ai_config,
    load_ai_usage,
    resolve_api_key_env,
    resolve_api_style,
    resolve_base_url,
    run_ai_complete_command,
    run_ai_config_command,
    run_ai_status_command,
    save_ai_config,
)


def _write_config(tmp_path: Path, monkeypatch, ai: dict | None = None) -> Path:
    config_path = tmp_path / "config.json"
    payload = {
        "terminal_path": "",
        "portable_mode": True,
        "artifacts_dir": str(tmp_path / "artifacts"),
        "results_dir": str(tmp_path / "results"),
    }
    if ai is not None:
        payload["ai"] = ai
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("MT5_AGENT_CONFIG", str(config_path))
    return config_path


def _fake_openai_transport(captured: dict):
    def transport(url, headers, payload, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = payload
        return {
            "choices": [{"message": {"content": "ok summary"}}],
            "usage": {"total_tokens": 120},
        }

    return transport


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #
def test_ai_disabled_by_default(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    config = load_ai_config()
    assert config.enabled is False
    assert config.provider == "none"


def test_save_ai_config_is_non_clobbering_and_keyless(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path, monkeypatch)
    save_ai_config({"provider": "openai", "model": "gpt-4o-mini", "enabled": True})
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    # Existing non-AI keys are preserved.
    assert raw["portable_mode"] is True
    assert raw["ai"]["provider"] == "openai"
    assert raw["ai"]["enabled"] is True
    # No secret is ever written into config.json.
    assert "api_key" not in raw["ai"]


def test_resolvers_use_provider_defaults() -> None:
    config = AIProviderConfig(provider="groq")
    assert resolve_base_url(config) == "https://api.groq.com/openai/v1"
    assert resolve_api_key_env(config) == "GROQ_API_KEY"
    assert resolve_api_style(config) == "openai"
    anthropic = AIProviderConfig(provider="anthropic")
    assert resolve_api_style(anthropic) == "anthropic"


# --------------------------------------------------------------------------- #
# complete() guards
# --------------------------------------------------------------------------- #
def test_complete_raises_when_disabled(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    try:
        complete("hi")
    except AIDisabledError as exc:
        assert "disabled" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected AIDisabledError")


def test_complete_requires_api_key_for_cloud_provider(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch, ai={"provider": "openai", "model": "gpt-4o-mini", "enabled": True})
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    try:
        complete("hi")
    except AIConfigError as exc:
        assert "OPENAI_API_KEY" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected AIConfigError")


def test_complete_openai_dispatch_injects_safety_and_records_usage(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch, ai={"provider": "openai", "model": "gpt-4o-mini", "enabled": True})
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    captured: dict = {}

    result = complete("Summarize run X", system="Be terse.", transport=_fake_openai_transport(captured))

    assert result.text == "ok summary"
    assert result.total_tokens == 120
    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    system_msg = captured["payload"]["messages"][0]["content"]
    assert "never place trades" in system_msg
    assert "Be terse." in system_msg
    usage = load_ai_usage()
    assert usage["calls"] == 1
    assert usage["total_tokens"] == 120


def test_complete_anthropic_dispatch(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch, ai={"provider": "anthropic", "model": "claude-haiku-4-5", "enabled": True})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ak-test")
    captured: dict = {}

    def transport(url, headers, payload, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = payload
        return {"content": [{"text": "claude says hi"}], "usage": {"input_tokens": 10, "output_tokens": 5}}

    result = complete("hello", transport=transport)
    assert result.text == "claude says hi"
    assert result.total_tokens == 15
    assert captured["url"].endswith("/messages")
    assert captured["headers"]["x-api-key"] == "ak-test"
    assert captured["payload"]["system"].startswith("You are an assistant")


def test_complete_ollama_is_keyless(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch, ai={"provider": "ollama", "model": "llama3", "enabled": True})
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    captured: dict = {}
    result = complete("hi", transport=_fake_openai_transport(captured))
    assert result.text == "ok summary"
    # No Authorization header when there is no key (local inference).
    assert "Authorization" not in captured["headers"]


def test_complete_enforces_call_budget(tmp_path: Path, monkeypatch) -> None:
    _write_config(
        tmp_path,
        monkeypatch,
        ai={"provider": "openai", "model": "gpt-4o-mini", "enabled": True, "max_calls": 1},
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    captured: dict = {}
    complete("first", transport=_fake_openai_transport(captured))
    try:
        complete("second", transport=_fake_openai_transport(captured))
    except BudgetError as exc:
        assert "budget" in str(exc).lower()
    else:  # pragma: no cover
        raise AssertionError("expected BudgetError on the second call")


# --------------------------------------------------------------------------- #
# CLI commands
# --------------------------------------------------------------------------- #
def test_ai_status_and_config_commands(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_config(tmp_path, monkeypatch)

    status_exit = run_ai_status_command()
    status_out = capsys.readouterr().out
    assert status_exit == 0
    assert "enabled: False" in status_out
    assert "deterministic CLI works without it" in status_out

    config_exit = run_ai_config_command(
        provider="openrouter",
        model="meta-llama/llama-3.1-8b-instruct",
        base_url=None,
        api_key_env=None,
        max_calls=10,
        max_cost_usd=1.0,
        usd_per_1k_tokens=None,
        enable=True,
        disable=False,
        allow_autonomous=False,
        no_autonomous=False,
    )
    config_out = capsys.readouterr().out
    assert config_exit == 0
    assert "ai config written" in config_out
    assert "enabled: True" in config_out
    assert "provider: openrouter" in config_out


def test_ai_complete_command_reports_disabled(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_config(tmp_path, monkeypatch)
    prompt = tmp_path / "p.md"
    prompt.write_text("hi", encoding="utf-8")
    exit_code = run_ai_complete_command(str(prompt), system=None)
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "disabled" in out


def test_ai_complete_command_runs_with_mocked_transport(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_config(tmp_path, monkeypatch, ai={"provider": "openai", "model": "gpt-4o-mini", "enabled": True})
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    captured: dict = {}
    monkeypatch.setattr(providers, "default_transport", _fake_openai_transport(captured))
    prompt = tmp_path / "p.md"
    prompt.write_text("Summarize the latest run.", encoding="utf-8")

    exit_code = run_ai_complete_command(str(prompt), system=None)
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "ok summary" in out
    assert "openai/gpt-4o-mini" in out
