from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pywinauto import Desktop

from mt5_research_agent.config import AppConfig, load_config


@dataclass(slots=True)
class ControlSnapshot:
    depth: int
    control_type: str
    class_name: str
    window_text: str
    is_visible: bool
    is_enabled: bool
    rectangle: str


@dataclass(slots=True)
class WindowInspection:
    timestamp: str
    backend: str
    matched_window_title: str
    process_id: int
    dump_depth: int
    screenshot_path: str
    visible_child_controls: list[ControlSnapshot]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_artifact_paths(config: AppConfig, timestamp: str) -> tuple[Path, Path]:
    screenshots_dir = ensure_directory(Path(config.artifacts_dir) / "screenshots")
    logs_dir = ensure_directory(Path(config.artifacts_dir) / "logs")
    screenshot_path = screenshots_dir / f"inspect_{timestamp}.png"
    log_path = logs_dir / f"inspect_{timestamp}.json"
    return screenshot_path, log_path


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def matches_title(title: str, title_contains: str) -> bool:
    return title_contains.casefold() in title.casefold()


def find_matching_window(title_contains: str, backend: str):
    desktop = Desktop(backend=backend)
    for window in desktop.windows():
        title = normalize_text(window.window_text())
        if title and matches_title(title, title_contains):
            return window
    return None


def snapshot_control(control, depth: int) -> ControlSnapshot:
    info = control.element_info
    control_type = normalize_text(getattr(info, "control_type", ""))
    class_name = normalize_text(getattr(info, "class_name", ""))
    window_text = normalize_text(control.window_text())
    rectangle = str(control.rectangle())
    return ControlSnapshot(
        depth=depth,
        control_type=control_type,
        class_name=class_name,
        window_text=window_text,
        is_visible=bool(control.is_visible()),
        is_enabled=bool(control.is_enabled()),
        rectangle=rectangle,
    )


def walk_visible_controls(root_control, max_depth: int, depth: int = 1) -> list[ControlSnapshot]:
    if depth > max_depth:
        return []

    controls: list[ControlSnapshot] = []
    for child in root_control.children():
        try:
            if not child.is_visible():
                continue
            controls.append(snapshot_control(child, depth))
            controls.extend(walk_visible_controls(child, max_depth=max_depth, depth=depth + 1))
        except Exception:
            continue
    return controls


def save_inspection_log(log_path: Path, payload: dict[str, Any]) -> None:
    log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def inspection_to_payload(result: WindowInspection) -> dict[str, Any]:
    payload = asdict(result)
    payload["visible_child_controls"] = [asdict(control) for control in result.visible_child_controls]
    return payload


def build_not_found_message(config: AppConfig, backend: str) -> str:
    return (
        f"No MT5 window found for backend '{backend}' with title containing "
        f"'{config.mt5_window_title_contains}'. Open MetaTrader 5 manually, confirm the expected "
        "terminal window is visible, then rerun inspect."
    )


def run_inspect_command(backend: str, dump_depth: int) -> int:
    config = load_config()
    window = find_matching_window(config.mt5_window_title_contains, backend)
    if window is None:
        print(build_not_found_message(config, backend))
        return 1

    timestamp = utc_timestamp()
    screenshot_path, log_path = build_artifact_paths(config, timestamp)
    controls = walk_visible_controls(window, max_depth=max(dump_depth, 0))

    window.capture_as_image().save(screenshot_path)
    result = WindowInspection(
        timestamp=timestamp,
        backend=backend,
        matched_window_title=normalize_text(window.window_text()),
        process_id=int(window.process_id()),
        dump_depth=dump_depth,
        screenshot_path=str(screenshot_path),
        visible_child_controls=controls,
    )
    save_inspection_log(log_path, inspection_to_payload(result))

    print(f"matched window title: {result.matched_window_title}")
    print(f"process id: {result.process_id}")
    print(f"backend used: {result.backend}")
    print("visible child controls:")
    if not controls:
        print("- none detected")
    else:
        for control in controls:
            label = control.window_text or "<no text>"
            kind = control.control_type or control.class_name or "unknown"
            print(f"- depth={control.depth} type={kind} text={label}")
    print(f"screenshot: {screenshot_path}")
    print(f"log: {log_path}")
    return 0
