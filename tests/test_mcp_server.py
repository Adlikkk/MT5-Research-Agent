from __future__ import annotations

import io
import json
from pathlib import Path

from mt5_research_agent import __version__
from mt5_research_agent.mcp_server import (
    PROTOCOL_VERSION,
    handle_mcp_message,
    list_tools,
    serve_mcp,
)


def _write_config(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "terminal_path": "",
                "portable_mode": True,
                "artifacts_dir": str(tmp_path / "artifacts"),
                "results_dir": str(tmp_path / "results"),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MT5_AGENT_CONFIG", str(config_path))


def test_initialize_returns_protocol_and_server_info() -> None:
    response = handle_mcp_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert response is not None
    assert response["id"] == 1
    assert response["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert response["result"]["serverInfo"]["version"] == __version__
    assert "tools" in response["result"]["capabilities"]


def test_initialized_notification_has_no_response() -> None:
    response = handle_mcp_message({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert response is None


def test_tools_list_exposes_safe_tools_only() -> None:
    response = handle_mcp_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert response is not None
    names = {tool["name"] for tool in response["result"]["tools"]}
    assert "parse_report" in names
    assert "plan_optimization" in names
    # Safety: MT5-launching tools are intentionally NOT exposed via MCP.
    assert "run_task" not in names
    assert "run_optimization" not in names
    assert "run_batch" not in names
    # Every tool advertises a JSON input schema.
    for tool in response["result"]["tools"]:
        assert tool["inputSchema"]["type"] == "object"


def test_list_tools_helper_matches_registry() -> None:
    assert len(list_tools()) >= 10


def test_tools_call_parse_report_roundtrip(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    report = tmp_path / "r.htm"
    report.write_text(
        "<html><body><table>"
        "<tr><td>Net Profit:</td><td>1234.56</td></tr>"
        "<tr><td>Profit Factor:</td><td>1.8</td></tr>"
        "</table></body></html>",
        encoding="utf-8",
    )
    response = handle_mcp_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "parse_report", "arguments": {"report_path": str(report)}},
        }
    )
    assert response is not None
    result = response["result"]
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    assert payload["net_profit"] == 1234.56


def test_tools_call_missing_required_argument_is_error() -> None:
    response = handle_mcp_message(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "parse_report", "arguments": {}},
        }
    )
    assert response is not None
    result = response["result"]
    assert result["isError"] is True
    assert "report_path is required" in result["content"][0]["text"]


def test_tools_call_unknown_tool_is_error() -> None:
    response = handle_mcp_message(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "do_something_unsafe", "arguments": {}},
        }
    )
    assert response is not None
    assert response["result"]["isError"] is True


def test_unknown_method_returns_method_not_found() -> None:
    response = handle_mcp_message({"jsonrpc": "2.0", "id": 6, "method": "frobnicate"})
    assert response is not None
    assert response["error"]["code"] == -32601


def test_mcp_selfcheck_reports_healthy() -> None:
    from mt5_research_agent.mcp_server import mcp_selfcheck

    result = mcp_selfcheck()
    assert result["ok"] is True
    assert result["protocol_version"] == PROTOCOL_VERSION
    assert result["tool_count"] >= 10
    assert "parse_report" in result["tools"]


def test_serve_mcp_reads_and_writes_line_delimited_json(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    requests = "\n".join(
        [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
        ]
    )
    stdin = io.StringIO(requests + "\n")
    stdout = io.StringIO()
    exit_code = serve_mcp(stdin=stdin, stdout=stdout)
    assert exit_code == 0
    lines = [line for line in stdout.getvalue().splitlines() if line.strip()]
    # initialize + tools/list reply; the notification produces no line.
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["id"] == 1
    second = json.loads(lines[1])
    assert any(tool["name"] == "validate_environment" for tool in second["result"]["tools"])
