from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import win32clipboard
from pywinauto import Desktop
from pywinauto.keyboard import send_keys

from mt5_research_agent.config import AppConfig, load_config
from mt5_research_agent.inspect import build_not_found_message, normalize_text, utc_timestamp
from mt5_research_agent.task import load_task, task_to_payload
from mt5_research_agent.tester import detect_tester_visibility, save_window_screenshot, write_json


INPUTS_TAB_NAME = "Vstupní parametry"
INPUT_HEADERS = ("Proměnná", "Hodnota")


@dataclass(slots=True)
class InputParameter:
    row_index: int
    name: str
    current_value: str
    start_value: str
    step_value: str
    stop_value: str
    optimize_flag: str


@dataclass(slots=True)
class InputsGridDiscovery:
    headers: list[str]
    row_names_available: bool
    fallback_used: bool
    export_count: int


def sanitize_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "input"


def split_identifier_tokens(value: str) -> list[str]:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    parts = re.split(r"[^A-Za-z0-9]+", text)
    return [part.lower() for part in parts if part]


def normalized_identifier(value: str) -> str:
    return "".join(split_identifier_tokens(value))


def identifier_acronym(value: str) -> str:
    tokens = split_identifier_tokens(value)
    return "".join(token[0] for token in tokens if token)


def is_subsequence(needle: str, haystack: str) -> bool:
    if not needle:
        return False
    position = 0
    for char in haystack:
        if position < len(needle) and char == needle[position]:
            position += 1
        if position == len(needle):
            return True
    return False


def resolve_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def build_inputs_artifact_paths(config: AppConfig, timestamp: str, action: str, input_name: str | None = None) -> dict[str, Path]:
    screenshots_dir = Path(config.artifacts_dir).resolve() / "screenshots"
    logs_dir = Path(config.artifacts_dir).resolve() / "logs"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{sanitize_filename(input_name)}" if input_name else ""
    return {
        "before_screenshot": screenshots_dir / f"{action}{suffix}_before_{timestamp}.png",
        "after_screenshot": screenshots_dir / f"{action}{suffix}_after_{timestamp}.png",
        "log": logs_dir / f"{action}{suffix}_{timestamp}.json",
    }


def find_mt5_window(backend: str, config: AppConfig):
    for window in Desktop(backend=backend).windows():
        title = normalize_text(window.window_text())
        if title and config.mt5_window_title_contains.casefold() in title.casefold():
            return window
    return None


def find_tester_control(window):
    for control in window.descendants():
        try:
            if control.class_name().startswith("Afx:ControlBar") and normalize_text(control.window_text()) == "Tester strategie":
                return control
        except Exception:
            continue
    return None


def find_inputs_tab_control(tester_control):
    for child in tester_control.children():
        try:
            texts = [normalize_text(text) for text in child.texts()]
        except Exception:
            continue
        if child.class_name() == "SysTabControl32" and any(INPUTS_TAB_NAME in text for text in texts):
            return child
    return None


def select_inputs_tab(tab_control) -> None:
    texts = [normalize_text(text) for text in tab_control.texts()]
    for index, text in enumerate(texts):
        if INPUTS_TAB_NAME == text:
            tab_control.select(index)
            return
    raise RuntimeError(f"Unable to find '{INPUTS_TAB_NAME}' tab in Strategy Tester.")


def discover_inputs_grid_uia(tester_control) -> InputsGridDiscovery:
    headers: list[str] = []
    row_names_available = False
    for control in tester_control.descendants():
        try:
            text = normalize_text(control.window_text())
        except Exception:
            continue
        if text in INPUT_HEADERS and text not in headers:
            headers.append(text)
        if text == "TP_R" or text == "TakeProfit_R":
            row_names_available = True
    return InputsGridDiscovery(
        headers=headers,
        row_names_available=row_names_available,
        fallback_used=not row_names_available,
        export_count=0,
    )


def find_visible_inputs_listview(tester_control):
    candidates = []
    for control in tester_control.descendants():
        try:
            if control.class_name() != "SysListView32":
                continue
            if not control.is_visible():
                continue
            candidates.append(control)
        except Exception:
            continue

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item.item_count(), item.column_count()), reverse=True)
    return candidates[0]


def read_clipboard_text() -> str:
    win32clipboard.OpenClipboard()
    try:
        return str(win32clipboard.GetClipboardData())
    finally:
        win32clipboard.CloseClipboard()


def copy_inputs_export(listview) -> str:
    listview.set_focus()
    time.sleep(0.2)
    send_keys("^c")
    time.sleep(0.4)
    return read_clipboard_text()


def parse_inputs_export(export_text: str) -> list[InputParameter]:
    parameters: list[InputParameter] = []
    for row_index, line in enumerate(line for line in export_text.splitlines() if line.strip()):
        if "||" not in line or "=" not in line:
            continue
        name_part, rest = line.split("=", 1)
        parts = rest.split("||")
        if len(parts) < 5:
            continue
        parameters.append(
            InputParameter(
                row_index=row_index,
                name=name_part.strip(),
                current_value=parts[0].strip(),
                start_value=parts[1].strip(),
                step_value=parts[2].strip(),
                stop_value=parts[3].strip(),
                optimize_flag=parts[4].strip(),
            )
        )
    return parameters


def find_input_parameter(parameters: list[InputParameter], requested_name: str) -> InputParameter:
    requested_normalized = normalized_identifier(requested_name)
    requested_acronym = identifier_acronym(requested_name)

    exact_matches = [parameter for parameter in parameters if parameter.name == requested_name]
    if len(exact_matches) == 1:
        return exact_matches[0]

    normalized_matches = [
        parameter for parameter in parameters if normalized_identifier(parameter.name) == requested_normalized
    ]
    if len(normalized_matches) == 1:
        return normalized_matches[0]

    acronym_matches = [
        parameter for parameter in parameters if requested_normalized and requested_normalized == identifier_acronym(parameter.name)
    ]
    if len(acronym_matches) == 1:
        return acronym_matches[0]

    alias_matches = []
    for parameter in parameters:
        parameter_normalized = normalized_identifier(parameter.name)
        parameter_acronym = identifier_acronym(parameter.name)
        if requested_normalized and requested_normalized in parameter_normalized:
            alias_matches.append(parameter)
            continue
        if requested_normalized and is_subsequence(requested_normalized, parameter_normalized):
            alias_matches.append(parameter)
            continue
        if requested_acronym and requested_acronym == parameter_acronym:
            alias_matches.append(parameter)

    deduped = {parameter.name: parameter for parameter in alias_matches}
    if len(deduped) == 1:
        return next(iter(deduped.values()))
    if len(deduped) > 1:
        names = ", ".join(sorted(deduped))
        raise RuntimeError(f"Input name '{requested_name}' is ambiguous. Matches: {names}")
    raise RuntimeError(f"Input name '{requested_name}' was not found in the current Inputs grid export.")


def prepare_inputs_context(config: AppConfig) -> tuple[Any, Any, Any, Any]:
    window_win32 = find_mt5_window("win32", config)
    if window_win32 is None:
        raise RuntimeError(build_not_found_message(config, "win32"))

    status = detect_tester_visibility(window_win32, dump_depth=3)
    if not status.is_visible:
        raise RuntimeError("Strategy Tester is not visible. Run `python -m mt5_research_agent open-tester --allow-gui-clicks` first.")

    window_uia = find_mt5_window("uia", config)
    if window_uia is None:
        raise RuntimeError(build_not_found_message(config, "uia"))

    tester_uia = find_tester_control(window_uia)
    tester_win32 = find_tester_control(window_win32)
    if tester_uia is None or tester_win32 is None:
        raise RuntimeError("Unable to locate the Strategy Tester control.")

    tab_uia = find_inputs_tab_control(tester_uia)
    tab_win32 = find_inputs_tab_control(tester_win32)
    if tab_uia is None or tab_win32 is None:
        raise RuntimeError("Unable to locate the Strategy Tester tab control.")

    return window_uia, window_win32, tab_uia, tab_win32


def navigate_to_inputs_tab(tab_uia, tab_win32) -> InputsGridDiscovery:
    select_inputs_tab(tab_uia)
    time.sleep(0.8)
    discovery = discover_inputs_grid_uia(tab_uia.parent())
    select_inputs_tab(tab_win32)
    time.sleep(0.8)
    return discovery


def export_inputs_parameters(tester_win32) -> tuple[list[InputParameter], str]:
    listview = find_visible_inputs_listview(tester_win32)
    if listview is None:
        raise RuntimeError("Unable to locate a visible Inputs grid/list view.")

    export_text = copy_inputs_export(listview)
    parameters = parse_inputs_export(export_text)
    if not parameters:
        raise RuntimeError(
            "The Inputs grid could not be read through UI automation. Save the screenshot and run `python -m mt5_research_agent calibrate-inputs`."
        )
    return parameters, export_text


def focus_input_row(listview, row_index: int) -> None:
    listview.set_focus()
    time.sleep(0.2)
    send_keys("{HOME}")
    time.sleep(0.2)
    for _ in range(row_index):
        send_keys("{DOWN}")
        time.sleep(0.02)


def set_input_value_via_keyboard(listview, row_index: int, value: str) -> None:
    focus_input_row(listview, row_index)
    send_keys("{F2}")
    time.sleep(0.4)
    send_keys("^a")
    time.sleep(0.1)
    send_keys(value, with_spaces=True)
    time.sleep(0.1)
    send_keys("{ENTER}")
    time.sleep(0.8)


def run_inputs_status_command() -> int:
    config = load_config()
    timestamp = utc_timestamp()
    artifact_paths = build_inputs_artifact_paths(config, timestamp, action="inputs_status")

    try:
        window_uia, window_win32, tab_uia, tab_win32 = prepare_inputs_context(config)
        save_window_screenshot(window_win32, artifact_paths["before_screenshot"])
        discovery = navigate_to_inputs_tab(tab_uia, tab_win32)
        tester_win32 = find_tester_control(window_win32)
        parameters, _ = export_inputs_parameters(tester_win32)
        discovery.export_count = len(parameters)
        save_window_screenshot(window_win32, artifact_paths["after_screenshot"])
        payload = {
            "timestamp": timestamp,
            "matched_window_title": normalize_text(window_win32.window_text()),
            "process_id": int(window_win32.process_id()),
            "inputs_tab": INPUTS_TAB_NAME,
            "headers": discovery.headers,
            "uia_row_names_available": discovery.row_names_available,
            "fallback_used": discovery.fallback_used,
            "input_count": len(parameters),
            "sample_inputs": [parameter.name for parameter in parameters[:10]],
            "before_screenshot_path": str(artifact_paths["before_screenshot"]),
            "after_screenshot_path": str(artifact_paths["after_screenshot"]),
        }
        write_json(artifact_paths["log"], payload)
        print(f"matched window title: {normalize_text(window_win32.window_text())}")
        print(f"process id: {int(window_win32.process_id())}")
        print("inputs tab accessible: yes")
        print(f"uia headers: {', '.join(discovery.headers) if discovery.headers else 'none'}")
        print(f"uia row names available: {'yes' if discovery.row_names_available else 'no'}")
        print(f"keyboard export fallback used: {'yes' if discovery.fallback_used else 'no'}")
        print(f"input count: {len(parameters)}")
        print(f"before screenshot: {artifact_paths['before_screenshot']}")
        print(f"after screenshot: {artifact_paths['after_screenshot']}")
        print(f"log: {artifact_paths['log']}")
        return 0
    except Exception as exc:
        try:
            if 'window_win32' in locals() and window_win32 is not None:
                save_window_screenshot(window_win32, artifact_paths["after_screenshot"])
        except Exception:
            pass
        payload = {
            "timestamp": timestamp,
            "error": str(exc),
            "after_screenshot_path": str(artifact_paths["after_screenshot"]),
        }
        write_json(artifact_paths["log"], payload)
        print(str(exc))
        print(f"log: {artifact_paths['log']}")
        return 1


def run_set_input_command(name: str, value: str, dry_run: bool, allow_gui_clicks: bool) -> int:
    if not dry_run and not allow_gui_clicks:
        print("Refusing to edit an input without --allow-gui-clicks.")
        return 2

    config = load_config()
    timestamp = utc_timestamp()
    artifact_paths = build_inputs_artifact_paths(config, timestamp, action="set_input", input_name=name)

    try:
        window_uia, window_win32, tab_uia, tab_win32 = prepare_inputs_context(config)
        save_window_screenshot(window_win32, artifact_paths["before_screenshot"])
        discovery = navigate_to_inputs_tab(tab_uia, tab_win32)
        tester_win32 = find_tester_control(window_win32)
        parameters_before, export_before = export_inputs_parameters(tester_win32)
        discovery.export_count = len(parameters_before)
        parameter = find_input_parameter(parameters_before, name)

        result_payload: dict[str, Any] = {
            "timestamp": timestamp,
            "matched_window_title": normalize_text(window_win32.window_text()),
            "process_id": int(window_win32.process_id()),
            "requested_name": name,
            "resolved_name": parameter.name,
            "requested_value": value,
            "current_value_before": parameter.current_value,
            "dry_run": dry_run,
            "uia_headers": discovery.headers,
            "uia_row_names_available": discovery.row_names_available,
            "fallback_used": discovery.fallback_used,
            "before_screenshot_path": str(artifact_paths["before_screenshot"]),
        }

        if dry_run:
            save_window_screenshot(window_win32, artifact_paths["after_screenshot"])
            result_payload["status"] = "dry_run"
            result_payload["after_screenshot_path"] = str(artifact_paths["after_screenshot"])
            write_json(artifact_paths["log"], result_payload)
            print(f"resolved input name: {parameter.name}")
            print(f"current value: {parameter.current_value}")
            print(f"requested value: {value}")
            print("dry run: no changes applied")
            print(f"before screenshot: {artifact_paths['before_screenshot']}")
            print(f"after screenshot: {artifact_paths['after_screenshot']}")
            print(f"log: {artifact_paths['log']}")
            return 0

        listview = find_visible_inputs_listview(tester_win32)
        if listview is None:
            raise RuntimeError(
                "The Inputs grid is not safely addressable. Save the screenshot and run `python -m mt5_research_agent calibrate-inputs`."
            )

        window_win32.set_focus()
        set_input_value_via_keyboard(listview, parameter.row_index, value)
        parameters_after, export_after = export_inputs_parameters(tester_win32)
        after_parameter = find_input_parameter(parameters_after, parameter.name)
        save_window_screenshot(window_win32, artifact_paths["after_screenshot"])

        result_payload["after_screenshot_path"] = str(artifact_paths["after_screenshot"])
        result_payload["current_value_after"] = after_parameter.current_value
        result_payload["status"] = "updated"

        if after_parameter.current_value != value:
            result_payload["status"] = "verification_failed"
            write_json(artifact_paths["log"], result_payload)
            print(
                f"Verification failed for input '{parameter.name}': expected '{value}', "
                f"saw '{after_parameter.current_value}'."
            )
            print(f"after screenshot: {artifact_paths['after_screenshot']}")
            print(f"log: {artifact_paths['log']}")
            return 1

        if export_before == export_after and parameter.current_value != value:
            result_payload["status"] = "mismatch"
            write_json(artifact_paths["log"], result_payload)
            print("Input export did not change after the edit attempt.")
            print(f"after screenshot: {artifact_paths['after_screenshot']}")
            print(f"log: {artifact_paths['log']}")
            return 1

        write_json(artifact_paths["log"], result_payload)
        print(f"resolved input name: {parameter.name}")
        print(f"value before: {parameter.current_value}")
        print(f"value after: {after_parameter.current_value}")
        print(f"before screenshot: {artifact_paths['before_screenshot']}")
        print(f"after screenshot: {artifact_paths['after_screenshot']}")
        print(f"log: {artifact_paths['log']}")
        return 0
    except Exception as exc:
        try:
            if 'window_win32' in locals() and window_win32 is not None:
                save_window_screenshot(window_win32, artifact_paths["after_screenshot"])
        except Exception:
            pass
        payload = {
            "timestamp": timestamp,
            "requested_name": name,
            "requested_value": value,
            "dry_run": dry_run,
            "error": str(exc),
            "after_screenshot_path": str(artifact_paths["after_screenshot"]),
        }
        write_json(artifact_paths["log"], payload)
        print(str(exc))
        print(f"after screenshot: {artifact_paths['after_screenshot']}")
        print(f"log: {artifact_paths['log']}")
        return 1


def run_calibrate_inputs_command() -> int:
    print("calibrate-inputs is a placeholder in Phase 4. Coordinate-based calibration is not implemented yet.")
    print("If input editing cannot be verified safely, stop and use the current screenshots/logs for a later calibration phase.")
    return 0


def run_validate_task_command(task_path: str) -> int:
    try:
        task = load_task(task_path)
    except Exception as exc:
        print(str(exc))
        return 1

    print(f"name: {task.name}")
    print(f"ea: {task.ea}")
    print(f"symbol: {task.symbol}")
    print(f"timeframe: {task.timeframe}")
    print(f"inputs: {len(task.inputs)}")
    print("task validation: ok")
    return 0


def run_apply_inputs_command(task_path: str, dry_run: bool, allow_gui_clicks: bool) -> int:
    if not dry_run and not allow_gui_clicks:
        print("Refusing to apply task inputs without --allow-gui-clicks.")
        return 2

    config = load_config()
    timestamp = utc_timestamp()
    artifact_paths = build_inputs_artifact_paths(config, timestamp, action="apply_inputs")

    try:
        task = load_task(task_path)
        step_results: list[dict[str, Any]] = []
        failure: dict[str, Any] | None = None

        for index, (name, value) in enumerate(task.inputs.items(), start=1):
            exit_code = run_set_input_command(
                name=name,
                value=value,
                dry_run=dry_run,
                allow_gui_clicks=allow_gui_clicks,
            )
            step_result = {
                "step": index,
                "name": name,
                "value": value,
                "success": exit_code == 0,
                "exit_code": exit_code,
            }
            step_results.append(step_result)
            if exit_code != 0:
                failure = step_result
                break

        window = find_mt5_window("win32", config)
        if window is not None:
            save_window_screenshot(window, artifact_paths["after_screenshot"])

        payload = {
            "timestamp": timestamp,
            "task_path": str(Path(task_path)),
            "task": task_to_payload(task),
            "dry_run": dry_run,
            "applied_count": len([item for item in step_results if item["success"]]),
            "total_inputs": len(task.inputs),
            "steps": step_results,
            "failure": failure,
            "final_screenshot_path": str(artifact_paths["after_screenshot"]),
            "status": "failed" if failure else "ok",
        }
        write_json(artifact_paths["log"], payload)

        if failure:
            print(f"stopped on input: {failure['name']}")
            print(f"final screenshot: {artifact_paths['after_screenshot']}")
            print(f"log: {artifact_paths['log']}")
            return 1

        print(f"task: {task.name}")
        print(f"inputs processed: {len(step_results)}/{len(task.inputs)}")
        print(f"dry run: {'yes' if dry_run else 'no'}")
        print(f"final screenshot: {artifact_paths['after_screenshot']}")
        print(f"log: {artifact_paths['log']}")
        return 0
    except Exception as exc:
        window = find_mt5_window("win32", config)
        if window is not None:
            try:
                save_window_screenshot(window, artifact_paths["after_screenshot"])
            except Exception:
                pass
        payload = {
            "timestamp": timestamp,
            "task_path": str(Path(task_path)),
            "dry_run": dry_run,
            "error": str(exc),
            "final_screenshot_path": str(artifact_paths["after_screenshot"]),
            "status": "failed",
        }
        write_json(artifact_paths["log"], payload)
        print(str(exc))
        print(f"final screenshot: {artifact_paths['after_screenshot']}")
        print(f"log: {artifact_paths['log']}")
        return 1
