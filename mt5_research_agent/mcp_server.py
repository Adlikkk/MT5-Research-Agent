"""MCP server (Phase 7) over stdio.

A dependency-free Model Context Protocol server that exposes the **safe** agent
surface: read-only inspection, deterministic file generation, request/plan, and
report parsing. It speaks JSON-RPC 2.0 over stdin/stdout.

Safety choice: MT5-launching tools (run-task, run-batch, run-optimization
``--run``, split-validate, improve-ea) are deliberately **not** exposed here.
Those start the Strategy Tester and stay on the explicit CLI so an automated
agent can never trigger an MT5 launch through this server. Everything reachable
via MCP is non-destructive and never places trades.

The routing lives in :func:`handle_mcp_message`, a pure function over a single
JSON-RPC message, so the protocol and every tool are unit-testable without any
stdio plumbing.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable, TextIO

from mt5_research_agent import __version__


PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "mt5-research-agent", "version": __version__}

# JSON-RPC error codes.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


def _tool_validate_environment(arguments: dict[str, Any]) -> dict[str, Any]:
    from mt5_research_agent.doctor import run_doctor

    checks = run_doctor()
    return {
        "ok": all(check.ok for check in checks),
        "checks": [{"name": check.name, "ok": check.ok, "detail": check.detail} for check in checks],
    }


def _tool_get_leaderboard(arguments: dict[str, Any]) -> dict[str, Any]:
    from mt5_research_agent.result_store import fetch_runs, update_leaderboard_csv

    path = update_leaderboard_csv()
    limit = int(arguments.get("limit", 15))
    rows = fetch_runs()[:limit]
    return {
        "ok": True,
        "leaderboard_csv": str(path),
        "runs": [
            {
                "test_id": row["test_id"],
                "run_status": row.get("effective_run_status", row.get("run_status", "")),
                "pass_fail": "PASS" if row.get("effective_pass_fail", row.get("pass_fail")) else "FAIL",
                "ea": row.get("ea", ""),
                "symbol": row.get("symbol", ""),
            }
            for row in rows
        ],
    }


def _tool_get_task_status(arguments: dict[str, Any]) -> dict[str, Any]:
    from mt5_research_agent.background_runner import build_task_status_payload

    test_id = str(arguments.get("test_id", "")).strip()
    if not test_id:
        raise ValueError("test_id is required")
    return build_task_status_payload(test_id)


def _tool_parse_report(arguments: dict[str, Any]) -> dict[str, Any]:
    from mt5_research_agent.report_parser import parse_report_file, parsed_report_to_payload

    report_path = str(arguments.get("report_path", "")).strip()
    if not report_path:
        raise ValueError("report_path is required")
    return parsed_report_to_payload(parse_report_file(report_path))


def _tool_locate_ea(arguments: dict[str, Any]) -> dict[str, Any]:
    from mt5_research_agent.mt5_diagnostics import locate_ea_payload

    ea_name = str(arguments.get("ea_name", "")).strip()
    if not ea_name:
        raise ValueError("ea_name is required")
    return locate_ea_payload(ea_name)


def _tool_validate_research_request(arguments: dict[str, Any]) -> dict[str, Any]:
    from mt5_research_agent.research_workflow import parse_research_request

    request_path = str(arguments.get("request_path", "")).strip()
    if not request_path:
        raise ValueError("request_path is required")
    request = parse_research_request(request_path)
    return {
        "ok": not request.todos,
        "slug": request.slug,
        "ea": request.ea,
        "symbol": request.symbol,
        "timeframe": request.timeframe,
        "parameter_keys": list(request.parameter_space),
        "todos": request.todos,
    }


def _tool_create_research_request(arguments: dict[str, Any]) -> dict[str, Any]:
    from mt5_research_agent.research_workflow import scaffold_research_request

    prompt_path = str(arguments.get("prompt_path", "")).strip()
    if not prompt_path:
        raise ValueError("prompt_path is required")
    return {"ok": True, "request_path": str(scaffold_research_request(prompt_path))}


def _tool_plan_next(arguments: dict[str, Any]) -> dict[str, Any]:
    from mt5_research_agent.planner import build_next_plan
    from mt5_research_agent.research_workflow import parse_research_request

    request_path = str(arguments.get("request_path", "")).strip()
    if not request_path:
        raise ValueError("request_path is required")
    request = parse_research_request(request_path)
    plan_path, experiment_path = build_next_plan(request)
    return {"ok": True, "plan_path": str(plan_path), "experiment_path": str(experiment_path)}


def _tool_plan_optimization(arguments: dict[str, Any]) -> dict[str, Any]:
    from mt5_research_agent.optimizer import load_optimization_spec, run_optimization

    spec_path = str(arguments.get("spec_path", "")).strip()
    if not spec_path:
        raise ValueError("spec_path is required")
    spec = load_optimization_spec(spec_path)
    result = run_optimization(spec, launch=False)
    return {
        "ok": True,
        "test_id": result.test_id,
        "grid_combinations": result.grid_combinations,
        "set_path": result.set_path,
        "ini_path": result.ini_path,
    }


def _tool_parse_optimization(arguments: dict[str, Any]) -> dict[str, Any]:
    from mt5_research_agent.optimizer import parse_optimization_report_file, ranked_pass_to_payload, rank_passes

    report_path = str(arguments.get("report_path", "")).strip()
    if not report_path:
        raise ValueError("report_path is required")
    limit = int(arguments.get("limit", 10))
    report = parse_optimization_report_file(report_path)
    ranked = rank_passes(report.passes, None)
    return {
        "ok": True,
        "total_passes": len(ranked),
        "columns": report.columns,
        "top_passes": [ranked_pass_to_payload(item) for item in ranked[:limit]],
    }


def _tool_create_ea_from_prompt(arguments: dict[str, Any]) -> dict[str, Any]:
    from mt5_research_agent.ea_lab import create_ea_from_prompt

    prompt_path = str(arguments.get("prompt_path", "")).strip()
    if not prompt_path:
        raise ValueError("prompt_path is required")
    return create_ea_from_prompt(prompt_path)


# name -> (description, inputSchema, handler)
TOOLS: dict[str, tuple[str, dict[str, Any], ToolHandler]] = {
    "validate_environment": (
        "Run local environment checks (doctor).",
        {"type": "object", "properties": {}},
        _tool_validate_environment,
    ),
    "get_leaderboard": (
        "Refresh and return the top stored runs.",
        {"type": "object", "properties": {"limit": {"type": "integer"}}},
        _tool_get_leaderboard,
    ),
    "get_task_status": (
        "Return the latest stored status for one test_id.",
        {"type": "object", "properties": {"test_id": {"type": "string"}}, "required": ["test_id"]},
        _tool_get_task_status,
    ),
    "parse_report": (
        "Parse one MT5 HTML report into structured metrics.",
        {"type": "object", "properties": {"report_path": {"type": "string"}}, "required": ["report_path"]},
        _tool_parse_report,
    ),
    "locate_ea": (
        "Locate matching .mq5/.ex5 files for an EA name.",
        {"type": "object", "properties": {"ea_name": {"type": "string"}}, "required": ["ea_name"]},
        _tool_locate_ea,
    ),
    "create_research_request": (
        "Scaffold a structured research request from a prompt file.",
        {"type": "object", "properties": {"prompt_path": {"type": "string"}}, "required": ["prompt_path"]},
        _tool_create_research_request,
    ),
    "validate_research_request": (
        "Validate a research request and report TODOs.",
        {"type": "object", "properties": {"request_path": {"type": "string"}}, "required": ["request_path"]},
        _tool_validate_research_request,
    ),
    "plan_next": (
        "Propose the next explainable batch for a request.",
        {"type": "object", "properties": {"request_path": {"type": "string"}}, "required": ["request_path"]},
        _tool_plan_next,
    ),
    "plan_optimization": (
        "Preview optimizer files and grid size for a spec (no MT5 launch).",
        {"type": "object", "properties": {"spec_path": {"type": "string"}}, "required": ["spec_path"]},
        _tool_plan_optimization,
    ),
    "parse_optimization": (
        "Parse and rank an MT5 optimization report (.xml).",
        {"type": "object", "properties": {"report_path": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["report_path"]},
        _tool_parse_optimization,
    ),
    "create_ea_from_prompt": (
        "Generate a safe-by-default EA from a prompt file.",
        {"type": "object", "properties": {"prompt_path": {"type": "string"}}, "required": ["prompt_path"]},
        _tool_create_ea_from_prompt,
    ),
}


def list_tools() -> list[dict[str, Any]]:
    return [
        {"name": name, "description": description, "inputSchema": schema}
        for name, (description, schema, _handler) in TOOLS.items()
    ]


def _result(message_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _error(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    entry = TOOLS.get(name)
    if entry is None:
        return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True}
    _description, _schema, handler = entry
    try:
        payload = handler(arguments or {})
    except Exception as exc:  # surfaced to the client as an error result, never hidden
        return {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True}
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}], "isError": False}


def handle_mcp_message(message: dict[str, Any]) -> dict[str, Any] | None:
    """Handle a single JSON-RPC message. Returns None for notifications."""

    if message.get("jsonrpc") != "2.0":
        return _error(message.get("id"), INVALID_REQUEST, "Only JSON-RPC 2.0 is supported.")

    method = message.get("method")
    message_id = message.get("id")
    params = message.get("params")
    if not isinstance(params, dict):
        params = {}

    # Notifications (no id) get no response.
    if message_id is None and isinstance(method, str) and method.startswith("notifications/"):
        return None

    if method == "initialize":
        return _result(
            message_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": SERVER_INFO,
                "capabilities": {"tools": {"listChanged": False}},
            },
        )

    if method == "ping":
        return _result(message_id, {})

    if method == "tools/list":
        return _result(message_id, {"tools": list_tools()})

    if method == "tools/call":
        name = str(params.get("name", ""))
        arguments = params.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        if not name:
            return _error(message_id, INVALID_PARAMS, "tools/call requires a tool name.")
        return _result(message_id, _call_tool(name, arguments))

    if message_id is None:
        return None
    return _error(message_id, METHOD_NOT_FOUND, f"Unknown method: {method}")


def serve_mcp(stdin: TextIO | None = None, stdout: TextIO | None = None) -> int:
    """Read line-delimited JSON-RPC messages from stdin and reply on stdout."""

    source = stdin or sys.stdin
    sink = stdout or sys.stdout
    for line in source:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            sink.write(json.dumps(_error(None, PARSE_ERROR, "Invalid JSON.")) + "\n")
            sink.flush()
            continue
        if not isinstance(message, dict):
            sink.write(json.dumps(_error(None, INVALID_REQUEST, "Message must be a JSON object.")) + "\n")
            sink.flush()
            continue
        response = handle_mcp_message(message)
        if response is not None:
            sink.write(json.dumps(response) + "\n")
            sink.flush()
    return 0


def mcp_selfcheck() -> dict[str, Any]:
    """Run the MCP handshake in-process and report health (no stdio loop)."""

    init = handle_mcp_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    tools = handle_mcp_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    ok = (
        isinstance(init, dict)
        and init.get("result", {}).get("protocolVersion") == PROTOCOL_VERSION
        and isinstance(tools, dict)
        and bool(tools.get("result", {}).get("tools"))
    )
    tool_names = [t["name"] for t in (tools or {}).get("result", {}).get("tools", [])] if tools else []
    return {
        "ok": ok,
        "protocol_version": PROTOCOL_VERSION,
        "server": SERVER_INFO,
        "tool_count": len(tool_names),
        "tools": tool_names,
    }


def run_serve_mcp_command(selfcheck: bool = False) -> int:
    if selfcheck:
        result = mcp_selfcheck()
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1
    return serve_mcp()
