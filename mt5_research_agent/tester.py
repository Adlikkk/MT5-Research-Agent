from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any

from pywinauto.keyboard import send_keys

from mt5_research_agent.config import AppConfig, load_config
from mt5_research_agent.inspect import (
    build_not_found_message,
    ensure_directory,
    find_matching_window,
    normalize_text,
    utc_timestamp,
    walk_visible_controls,
)


TESTER_KEYWORDS = ("strategy tester", "tester", "backtest")


@dataclass(slots=True)
class TesterVisibility:
    is_visible: bool
    evidence: list[str]
    matched_controls: list[dict[str, Any]]


def build_tester_artifact_paths(config: AppConfig, timestamp: str) -> dict[str, Path]:
    screenshots_dir = ensure_directory(Path(config.artifacts_dir) / "screenshots")
    logs_dir = ensure_directory(Path(config.artifacts_dir) / "logs")
    return {
        "before_screenshot": screenshots_dir / f"open_tester_before_{timestamp}.png",
        "after_screenshot": screenshots_dir / f"open_tester_after_{timestamp}.png",
        "status_log": logs_dir / f"tester_status_{timestamp}.json",
        "open_log": logs_dir / f"open_tester_{timestamp}.json",
    }


def serialize_control(control: Any) -> dict[str, Any]:
    if is_dataclass(control):
        return asdict(control)  # type: ignore[arg-type]
    return {
        "depth": getattr(control, "depth", 0),
        "control_type": normalize_text(getattr(control, "control_type", "")),
        "class_name": normalize_text(getattr(control, "class_name", "")),
        "window_text": normalize_text(getattr(control, "window_text", "")),
        "is_visible": bool(getattr(control, "is_visible", False)),
        "is_enabled": bool(getattr(control, "is_enabled", False)),
        "rectangle": normalize_text(getattr(control, "rectangle", "")),
    }


def control_matches_tester(control) -> bool:
    haystacks = [
        normalize_text(getattr(control, "window_text", "")),
        normalize_text(getattr(control, "control_type", "")),
        normalize_text(getattr(control, "class_name", "")),
    ]
    combined = " ".join(haystacks).casefold()
    return any(keyword in combined for keyword in TESTER_KEYWORDS)


def detect_tester_visibility(window, dump_depth: int) -> TesterVisibility:
    matched_controls: list[dict[str, Any]] = []
    controls = walk_visible_controls(window, max_depth=max(dump_depth, 0))
    for control in controls:
        if control_matches_tester(control):
            matched_controls.append(serialize_control(control))

    evidence = [
        f"{item['control_type'] or item['class_name'] or 'unknown'}:{item['window_text'] or '<no text>'}"
        for item in matched_controls
    ]
    return TesterVisibility(
        is_visible=bool(matched_controls),
        evidence=evidence,
        matched_controls=matched_controls,
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def save_window_screenshot(window, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = window.capture_as_image()
    if image is None:
        raise RuntimeError(
            f"Unable to capture screenshot for '{normalize_text(window.window_text())}'. "
            "Install Pillow and confirm the MT5 window is visible."
        )
    image.save(path)


def print_tester_status(window_title: str, process_id: int, backend: str, status: TesterVisibility) -> None:
    print(f"matched window title: {window_title}")
    print(f"process id: {process_id}")
    print(f"backend used: {backend}")
    print(f"strategy tester visible: {'yes' if status.is_visible else 'no'}")
    if status.evidence:
        print("evidence:")
        for item in status.evidence:
            print(f"- {item}")
    else:
        print("evidence:")
        print("- no visible Strategy Tester controls matched")


def run_tester_status_command(backend: str, dump_depth: int) -> int:
    config = load_config()
    window = find_matching_window(config.mt5_window_title_contains, backend)
    if window is None:
        print(build_not_found_message(config, backend))
        return 1

    timestamp = utc_timestamp()
    artifact_paths = build_tester_artifact_paths(config, timestamp)
    status = detect_tester_visibility(window, dump_depth)
    write_json(
        artifact_paths["status_log"],
        {
            "timestamp": timestamp,
            "backend": backend,
            "matched_window_title": normalize_text(window.window_text()),
            "process_id": int(window.process_id()),
            "strategy_tester_visible": status.is_visible,
            "evidence": status.evidence,
            "matched_controls": status.matched_controls,
        },
    )
    print_tester_status(
        window_title=normalize_text(window.window_text()),
        process_id=int(window.process_id()),
        backend=backend,
        status=status,
    )
    print(f"log: {artifact_paths['status_log']}")
    return 0 if status.is_visible else 1


def wait_for_tester_visibility(window, dump_depth: int, timeout_seconds: int) -> TesterVisibility:
    deadline = time.monotonic() + timeout_seconds
    latest_status = detect_tester_visibility(window, dump_depth)
    while time.monotonic() < deadline:
        latest_status = detect_tester_visibility(window, dump_depth)
        if latest_status.is_visible:
            return latest_status
        time.sleep(0.5)
    return latest_status


def wait_for_tester_state(window, dump_depth: int, timeout_seconds: int, expected_visible: bool) -> TesterVisibility:
    deadline = time.monotonic() + timeout_seconds
    latest_status = detect_tester_visibility(window, dump_depth)
    while time.monotonic() < deadline:
        latest_status = detect_tester_visibility(window, dump_depth)
        if latest_status.is_visible is expected_visible:
            return latest_status
        time.sleep(0.5)
    return latest_status


def run_open_tester_command(allow_gui_clicks: bool, backend: str, dump_depth: int) -> int:
    if not allow_gui_clicks:
        print("Refusing to send Ctrl+R without --allow-gui-clicks.")
        return 2

    config = load_config()
    window = find_matching_window(config.mt5_window_title_contains, backend)
    if window is None:
        print(build_not_found_message(config, backend))
        return 1

    timestamp = utc_timestamp()
    artifact_paths = build_tester_artifact_paths(config, timestamp)
    matched_window_title = normalize_text(window.window_text())
    process_id = int(window.process_id())

    try:
        save_window_screenshot(window, artifact_paths["before_screenshot"])
    except RuntimeError as exc:
        write_json(
            artifact_paths["open_log"],
            {
                "timestamp": timestamp,
                "backend": backend,
                "matched_window_title": matched_window_title,
                "process_id": process_id,
                "action": "send_ctrl_r",
                "allow_gui_clicks": allow_gui_clicks,
                "error": str(exc),
                "before_screenshot_path": str(artifact_paths["before_screenshot"]),
            },
        )
        print(str(exc))
        print(f"log: {artifact_paths['open_log']}")
        return 1
    before_status = detect_tester_visibility(window, dump_depth)

    window.set_focus()
    send_keys("^r")
    time.sleep(1.0)

    after_status = wait_for_tester_visibility(window, dump_depth, timeout_seconds=config.default_timeout_seconds)
    recovery_attempted = False
    if before_status.is_visible and not after_status.is_visible:
        recovery_attempted = True
        send_keys("^r")
        time.sleep(1.0)
        after_status = wait_for_tester_state(
            window,
            dump_depth=dump_depth,
            timeout_seconds=config.default_timeout_seconds,
            expected_visible=True,
        )
    try:
        save_window_screenshot(window, artifact_paths["after_screenshot"])
    except RuntimeError as exc:
        write_json(
            artifact_paths["open_log"],
            {
                "timestamp": timestamp,
                "backend": backend,
                "matched_window_title": matched_window_title,
                "process_id": process_id,
                "action": "send_ctrl_r",
                "allow_gui_clicks": allow_gui_clicks,
                "before": {
                    "strategy_tester_visible": before_status.is_visible,
                    "evidence": before_status.evidence,
                    "matched_controls": before_status.matched_controls,
                    "screenshot_path": str(artifact_paths["before_screenshot"]),
                },
                "error": str(exc),
                "after_screenshot_path": str(artifact_paths["after_screenshot"]),
            },
        )
        print(str(exc))
        print(f"before screenshot: {artifact_paths['before_screenshot']}")
        print(f"log: {artifact_paths['open_log']}")
        return 1

    payload = {
        "timestamp": timestamp,
        "backend": backend,
        "matched_window_title": matched_window_title,
        "process_id": process_id,
        "action": "send_ctrl_r",
        "allow_gui_clicks": allow_gui_clicks,
        "recovery_attempted": recovery_attempted,
        "before": {
            "strategy_tester_visible": before_status.is_visible,
            "evidence": before_status.evidence,
            "matched_controls": before_status.matched_controls,
            "screenshot_path": str(artifact_paths["before_screenshot"]),
        },
        "after": {
            "strategy_tester_visible": after_status.is_visible,
            "evidence": after_status.evidence,
            "matched_controls": after_status.matched_controls,
            "screenshot_path": str(artifact_paths["after_screenshot"]),
        },
    }
    write_json(artifact_paths["open_log"], payload)

    if not after_status.is_visible:
        print("Strategy Tester was not confirmed visible after Ctrl+R.")
        print(f"before screenshot: {artifact_paths['before_screenshot']}")
        print(f"after screenshot: {artifact_paths['after_screenshot']}")
        print(f"log: {artifact_paths['open_log']}")
        return 1

    print_tester_status(
        window_title=matched_window_title,
        process_id=process_id,
        backend=backend,
        status=after_status,
    )
    print(f"before screenshot: {artifact_paths['before_screenshot']}")
    print(f"after screenshot: {artifact_paths['after_screenshot']}")
    print(f"log: {artifact_paths['open_log']}")
    return 0
