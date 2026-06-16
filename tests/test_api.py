import json
from pathlib import Path

import pytest

from mt5_research_agent.api import handle_api_request, serve_api


def _write_config(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "terminal_path": "",
                "portable_mode": False,
                "mt5_window_title_contains": "MetaTrader",
                "artifacts_dir": str(tmp_path / "artifacts"),
                "results_dir": str(tmp_path / "results"),
                "default_timeout_seconds": 30,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MT5_AGENT_CONFIG", str(config_path))


def test_health_endpoint(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    status, payload = handle_api_request("GET", "/health")
    assert status == 200
    assert payload["ok"] is True
    assert payload["service"] == "mt5_research_agent"


def test_config_endpoint_does_not_leak_secrets(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    status, payload = handle_api_request("GET", "/config")
    assert status == 200
    # Only operational fields, no raw terminal path string.
    assert "terminal_path" not in payload["config"]
    assert payload["config"]["terminal_path_configured"] is False


def test_runs_and_tools_endpoints(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    status, payload = handle_api_request("GET", "/runs")
    assert status == 200
    assert payload["ok"] is True
    status, tools = handle_api_request("GET", "/tools")
    assert "create_ea_from_prompt" in tools["tools"]


def test_research_request_requires_path(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    status, payload = handle_api_request("POST", "/research-requests", {})
    assert status == 400
    assert "request_path" in payload["error"]


def test_unknown_route_404(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    status, payload = handle_api_request("GET", "/nope")
    assert status == 404
    assert payload["ok"] is False


def test_serve_api_refuses_non_localhost() -> None:
    with pytest.raises(ValueError):
        serve_api(host="0.0.0.0", port=8765)


def test_options_preflight_returns_204(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    status, payload = handle_api_request("OPTIONS", "/runs")
    assert status == 204
    assert payload == {}


def test_ai_status_endpoint_reports_disabled_by_default(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    status, payload = handle_api_request("GET", "/ai/status")
    assert status == 200
    assert payload["ok"] is True
    assert payload["enabled"] is False
    assert payload["provider"] == "none"


def test_optimizations_endpoint_404_when_missing(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    status, payload = handle_api_request("GET", "/optimizations/DOES-NOT-EXIST")
    assert status == 404
    assert payload["ok"] is False


def test_tools_endpoint_includes_optimization_and_ai(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    _status, tools = handle_api_request("GET", "/tools")
    assert "plan_optimization" in tools["tools"]
    assert "ai_status" in tools["tools"]


def test_detect_endpoint(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    status, payload = handle_api_request("GET", "/detect")
    assert status == 200
    assert payload["ok"] is True
    labels = {c["label"] for c in payload["checks"]}
    assert "report path writable" in labels
    assert all(c["status"] in {"PASS", "WARN"} for c in payload["checks"])


def test_set_preview_endpoint(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    status, payload = handle_api_request(
        "POST", "/set-preview", {"ea": "MyEA", "symbol": "US30", "inputs": {"TP_R": "2.0", "ATR": "1.5"}}
    )
    assert status == 200
    assert "TP_R=2.0" in payload["set_text"]
    assert payload["task"]["ea"] == "MyEA"


def test_optimizer_preview_endpoint(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    spec = {
        "test_id": "OPT-UI",
        "ea": "Advisors\\Demo",
        "symbol": "US30",
        "timeframe": "M15",
        "period_from": "2020.01.01",
        "period_to": "2025.01.01",
        "ranges": [{"name": "TP_R", "start": 1.0, "step": 0.5, "stop": 3.0}],
    }
    status, payload = handle_api_request("POST", "/optimizer/preview", {"spec": spec})
    assert status == 200
    assert payload["grid_combinations"] == 5
    assert "TP_R=1||1||0.5||3||Y" in payload["set_text"]


def test_jobs_endpoints_submit_list_get_cancel(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    import mt5_research_agent.jobs as jobs

    # Register a fast fake handler on the process queue so no MT5 is launched.
    jobs.get_queue().register("ui_test", lambda ctx, params: {"echo": params.get("v")})

    status, payload = handle_api_request("POST", "/jobs", {"type": "ui_test", "params": {"v": 7}, "title": "t"})
    assert status == 200
    job_id = payload["job"]["id"]

    final = jobs.get_queue().wait(job_id, timeout=3.0)
    assert final is not None and final.status == "succeeded"

    status, got = handle_api_request("GET", f"/jobs/{job_id}")
    assert status == 200
    assert got["job"]["result"] == {"echo": 7}

    status, listing = handle_api_request("GET", "/jobs")
    assert status == 200
    assert any(j["id"] == job_id for j in listing["jobs"])


def test_jobs_submit_unknown_type_is_400(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    status, payload = handle_api_request("POST", "/jobs", {"type": "does_not_exist"})
    assert status == 400
    assert "Unknown job type" in payload["error"]


def test_detect_terminal_endpoint(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    import mt5_research_agent.maintenance as maintenance

    monkeypatch.setattr(maintenance, "detect_terminal_path", lambda: "")
    status, payload = handle_api_request("GET", "/detect-terminal")
    assert status == 200
    assert payload["ok"] is True
    assert payload["found"] is False


def test_config_save_endpoint_writes_and_returns_checks(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    config_path = tmp_path / "config.json"
    status, payload = handle_api_request("POST", "/config/save", {"terminal_path": "C:/x/terminal64.exe"})
    assert status == 200
    assert payload["ok"] is True
    import json as _json

    saved = _json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["terminal_path"] == "C:/x/terminal64.exe"
    # Detection checks are returned so the UI can re-render PASS/WARN immediately.
    assert any(c["label"] == "report path writable" for c in payload["checks"])


def test_session_status_endpoint(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    import mt5_research_agent.session as session

    monkeypatch.setattr(session, "mt5_process_status_payload", lambda config: {"matching_running": False, "processes": []})
    status, payload = handle_api_request("GET", "/session")
    assert status == 200
    assert payload["ok"] is True
    assert payload["session_active"] is False


def test_session_stop_without_confirm_does_not_touch_mt5(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    import mt5_research_agent.session as session

    monkeypatch.setattr(session, "mt5_process_status_payload", lambda config: {"matching_running": True, "processes": [{"pid": 1}]})

    def fail_stop(**kwargs):  # pragma: no cover - must not stop anything without confirm
        raise AssertionError("must not stop MT5 without confirm")

    monkeypatch.setattr(session, "stop_mt5_payload", fail_stop)
    status, payload = handle_api_request("POST", "/session/stop", {"confirm": False})
    assert status == 409
    assert payload["require_confirm"] is True
