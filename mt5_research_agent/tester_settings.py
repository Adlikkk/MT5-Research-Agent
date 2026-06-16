from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from mt5_research_agent.config import load_config
from mt5_research_agent.inputs import build_inputs_artifact_paths, find_mt5_window, find_tester_control
from mt5_research_agent.inspect import build_not_found_message, normalize_text, utc_timestamp
from mt5_research_agent.task import load_task, task_to_payload
from mt5_research_agent.tester import detect_tester_visibility, save_window_screenshot, write_json


SETTINGS_TAB_NAME = "Nastaveni"
MODEL_LABEL = "Modelovani:"
STRATEGY_LABEL = "Strategie:"
SYMBOL_LABEL = "Symbol:"
DATE_LABEL = "Datum:"
DEPOSIT_LABEL = "Vklad:"

MODEL_ALIASES = {
    "everytickbasedonrealticks": "Kazdy tick zalozen na realnych ticich",
    "everytick": "Kazdy tick",
    "1minuteohlc": "1 minuta OHLC",
    "openpricesonly": "Pouze oteviraci ceny",
    "mathematicalcalculations": "Matematicke vypocty",
}


@dataclass(slots=True)
class TesterSettingsState:
    ea: str
    symbol: str
    timeframe: str
    model: str
    period_from: str
    period_to: str
    deposit: str


@dataclass(slots=True)
class SettingsControlMap:
    ea_combo: Any
    symbol_combo: Any
    symbol_edit: Any
    timeframe_combo: Any
    date_mode_combo: Any
    date_from_picker: Any
    date_to_picker: Any
    model_combo: Any
    deposit_combo: Any
    deposit_edit: Any


def normalize_key(value: str) -> str:
    text = fold_text(value)
    text = text.replace("\\", "/")
    text = text.split("/")[-1]
    text = text.removesuffix(".ex5")
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def fold_text(value: str) -> str:
    text = normalize_text(value)
    folded = unicodedata.normalize("NFKD", text)
    return "".join(char for char in folded if not unicodedata.combining(char))


def normalize_symbol_aliases(value: str) -> list[str]:
    value = normalize_text(value)
    aliases = {
        value,
        value.replace("_", ".", 1),
        value.replace("_", "."),
        value.replace(".", "_"),
    }
    return [item for item in aliases if item]


def normalize_model_target(value: str) -> str:
    key = normalize_key(value)
    return MODEL_ALIASES.get(key, value)


def parse_task_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y.%m.%d")


def find_uia_tab_control(tester_uia):
    for child in tester_uia.children():
        try:
            texts = [fold_text(text) for text in child.texts()]
        except Exception:
            continue
        if child.class_name() == "SysTabControl32" and any("Nastav" in text for text in texts):
            return child
    return None


def select_settings_tab(window_uia, window_win32, tester_uia, tester_win32) -> str:
    tab_uia = find_uia_tab_control(tester_uia)
    if tab_uia is not None:
        try:
            texts = [fold_text(text) for text in tab_uia.texts()]
            for index, text in enumerate(texts):
                if "Nastav" in text:
                    tab_uia.select(index)
                    time.sleep(0.8)
                    labels = []
                    for control in tester_uia.descendants():
                        try:
                            if control.is_visible():
                                labels.append(fold_text(control.window_text()))
                        except Exception:
                            continue
                    if any(label == STRATEGY_LABEL for label in labels):
                        return "uia"
        except Exception:
            pass

    tab_win32 = None
    for child in tester_win32.children():
        try:
            if child.class_name() == "SysTabControl32":
                tab_win32 = child
                break
        except Exception:
            continue
    if tab_win32 is None:
        raise RuntimeError("Unable to locate the Strategy Tester settings tab control.")
    tab_win32.select(1)
    time.sleep(0.8)
    return "win32"


def visible_children(tester_win32) -> list[Any]:
    children = []
    for child in tester_win32.children():
        try:
            if child.is_visible():
                children.append(child)
        except Exception:
            continue
    return children


def next_visible_control(children: list[Any], start_index: int, class_name: str, occurrence: int = 1):
    seen = 0
    for child in children[start_index + 1 :]:
        try:
            if child.class_name() == class_name:
                seen += 1
                if seen == occurrence:
                    return child
        except Exception:
            continue
    return None


def label_index(children: list[Any], label: str) -> int:
    for index, child in enumerate(children):
        try:
            if child.class_name() == "Static" and fold_text(child.window_text()) == label:
                return index
        except Exception:
            continue
    raise RuntimeError(f"Unable to locate visible settings label '{label}'.")


def build_control_map(tester_win32) -> SettingsControlMap:
    children = visible_children(tester_win32)
    strategy_index = label_index(children, STRATEGY_LABEL)
    symbol_index = label_index(children, SYMBOL_LABEL)
    date_index = label_index(children, DATE_LABEL)
    model_index = label_index(children, MODEL_LABEL)
    deposit_index = label_index(children, DEPOSIT_LABEL)

    ea_combo = next_visible_control(children, strategy_index, "ComboBox", 1)
    symbol_combo = next_visible_control(children, symbol_index, "ComboBox", 1)
    symbol_edit = next_visible_control(children, symbol_index, "Edit", 1)
    timeframe_combo = next_visible_control(children, symbol_index, "ComboBox", 2)
    date_mode_combo = next_visible_control(children, date_index, "ComboBox", 1)
    date_from_picker = next_visible_control(children, date_index, "SysDateTimePick32", 1)
    date_to_picker = next_visible_control(children, date_index, "SysDateTimePick32", 2)
    model_combo = next_visible_control(children, model_index, "ComboBox", 1)
    deposit_combo = next_visible_control(children, deposit_index, "ComboBox", 1)
    deposit_edit = next_visible_control(children, deposit_index, "Edit", 1)

    required = {
        "ea_combo": ea_combo,
        "symbol_combo": symbol_combo,
        "symbol_edit": symbol_edit,
        "timeframe_combo": timeframe_combo,
        "date_mode_combo": date_mode_combo,
        "date_from_picker": date_from_picker,
        "date_to_picker": date_to_picker,
        "model_combo": model_combo,
        "deposit_combo": deposit_combo,
        "deposit_edit": deposit_edit,
    }
    missing = [name for name, control in required.items() if control is None]
    if missing:
        raise RuntimeError(f"Unable to map visible Strategy Tester settings controls: {', '.join(missing)}")

    return SettingsControlMap(**required)


def read_current_state(control_map: SettingsControlMap) -> TesterSettingsState:
    return TesterSettingsState(
        ea=normalize_text(control_map.ea_combo.window_text()),
        symbol=normalize_text(control_map.symbol_edit.window_text()),
        timeframe=normalize_text(control_map.timeframe_combo.window_text()),
        model=normalize_text(control_map.model_combo.window_text()),
        period_from=normalize_text(control_map.date_from_picker.window_text()),
        period_to=normalize_text(control_map.date_to_picker.window_text()),
        deposit=normalize_text(control_map.deposit_edit.window_text()),
    )


def resolve_combo_option(control, target: str, strict: bool = True) -> str | None:
    texts = [normalize_text(text) for text in control.texts()]
    normalized_target = normalize_key(target)
    for option in texts:
        if normalize_key(option) == normalized_target:
            return option
    if strict:
        return None
    for option in texts:
        if normalized_target and normalized_target in normalize_key(option):
            return option
    return None


def set_combo_value(control, target: str) -> None:
    control.select(target)
    time.sleep(0.4)


def set_edit_value(edit_control, value: str) -> None:
    edit_control.click_input()
    time.sleep(0.1)
    edit_control.type_keys("^a", set_foreground=True)
    time.sleep(0.1)
    edit_control.type_keys(value, with_spaces=True, set_foreground=True)
    time.sleep(0.1)
    edit_control.type_keys("{ENTER}", set_foreground=True)
    time.sleep(0.6)


def set_date_value(control, value: str) -> None:
    control.set_time(parse_task_date(value))
    time.sleep(0.4)


def verify_normalized(actual: str, expected: str) -> bool:
    return normalize_key(actual) == normalize_key(expected)


def prepare_settings_context():
    config = load_config()
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

    tab_backend = select_settings_tab(window_uia, window_win32, tester_uia, tester_win32)
    control_map = build_control_map(tester_win32)
    return config, window_win32, tester_win32, control_map, tab_backend


def print_settings_state(state: TesterSettingsState, tab_backend: str) -> None:
    print(f"tab selection backend: {tab_backend}")
    print(f"ea: {state.ea}")
    print(f"symbol: {state.symbol}")
    print(f"timeframe: {state.timeframe}")
    print(f"model: {state.model}")
    print(f"period_from: {state.period_from}")
    print(f"period_to: {state.period_to}")
    print(f"deposit: {state.deposit}")


def evaluate_task_support(control_map: SettingsControlMap, task) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    settings_plan: list[dict[str, Any]] = []

    ea_target = resolve_combo_option(control_map.ea_combo, task.ea, strict=False)
    settings_plan.append(
        {
            "setting": "ea",
            "requested": task.ea,
            "resolved": ea_target,
            "supported": ea_target is not None,
            "method": "combo_select",
            "reason": None if ea_target is not None else "EA not found in visible Strategy Tester expert list.",
        }
    )

    symbol_aliases = normalize_symbol_aliases(task.symbol)
    symbol_target = symbol_aliases[1] if len(symbol_aliases) > 1 else symbol_aliases[0]
    settings_plan.append(
        {
            "setting": "symbol",
            "requested": task.symbol,
            "resolved": symbol_target,
            "supported": True,
            "method": "edit_type",
            "reason": None,
        }
    )

    timeframe_target = resolve_combo_option(control_map.timeframe_combo, task.timeframe, strict=True)
    settings_plan.append(
        {
            "setting": "timeframe",
            "requested": task.timeframe,
            "resolved": timeframe_target,
            "supported": timeframe_target is not None,
            "method": "combo_select",
            "reason": None if timeframe_target is not None else "Timeframe option is not available in the current MT5 combo box.",
        }
    )

    model_requested = normalize_model_target(task.model)
    model_target = resolve_combo_option(control_map.model_combo, model_requested, strict=True)
    settings_plan.append(
        {
            "setting": "model",
            "requested": task.model,
            "resolved": model_target,
            "supported": model_target is not None,
            "method": "combo_select",
            "reason": None if model_target is not None else "Model option is not available in the current MT5 combo box.",
        }
    )

    settings_plan.append(
        {
            "setting": "period_from",
            "requested": task.period_from,
            "resolved": task.period_from,
            "supported": True,
            "method": "datetime_set",
            "reason": None,
        }
    )
    settings_plan.append(
        {
            "setting": "period_to",
            "requested": task.period_to,
            "resolved": task.period_to,
            "supported": True,
            "method": "datetime_set",
            "reason": None,
        }
    )

    deposit_target = str(int(task.deposit)) if float(task.deposit).is_integer() else str(task.deposit)
    settings_plan.append(
        {
            "setting": "deposit",
            "requested": task.deposit,
            "resolved": deposit_target,
            "supported": True,
            "method": "edit_type",
            "reason": None,
        }
    )

    unsupported = [item for item in settings_plan if not item["supported"]]
    return {"unsupported": unsupported}, settings_plan


def apply_setting(control_map: SettingsControlMap, setting_name: str, resolved_value: str) -> str:
    if setting_name == "ea":
        set_combo_value(control_map.ea_combo, resolved_value)
        return normalize_text(control_map.ea_combo.window_text())
    if setting_name == "symbol":
        set_edit_value(control_map.symbol_edit, resolved_value)
        return normalize_text(control_map.symbol_edit.window_text())
    if setting_name == "timeframe":
        set_combo_value(control_map.timeframe_combo, resolved_value)
        return normalize_text(control_map.timeframe_combo.window_text())
    if setting_name == "model":
        set_combo_value(control_map.model_combo, resolved_value)
        return normalize_text(control_map.model_combo.window_text())
    if setting_name == "period_from":
        set_date_value(control_map.date_from_picker, resolved_value)
        return normalize_text(control_map.date_from_picker.window_text())
    if setting_name == "period_to":
        set_date_value(control_map.date_to_picker, resolved_value)
        return normalize_text(control_map.date_to_picker.window_text())
    if setting_name == "deposit":
        set_edit_value(control_map.deposit_edit, resolved_value)
        return normalize_text(control_map.deposit_edit.window_text())
    raise RuntimeError(f"Unsupported setting '{setting_name}'.")


def verify_setting(setting_name: str, actual_value: str, expected_value: str) -> bool:
    if setting_name in {"ea", "symbol", "timeframe", "model"}:
        return verify_normalized(actual_value, expected_value)
    if setting_name == "deposit":
        return normalize_text(actual_value) == normalize_text(expected_value)
    return normalize_text(actual_value) == normalize_text(expected_value)


def run_tester_settings_status_command() -> int:
    config = load_config()
    timestamp = utc_timestamp()
    artifact_paths = build_inputs_artifact_paths(config, timestamp, action="tester_settings_status")
    try:
        _, window_win32, _, control_map, tab_backend = prepare_settings_context()
        save_window_screenshot(window_win32, artifact_paths["before_screenshot"])
        state = read_current_state(control_map)
        save_window_screenshot(window_win32, artifact_paths["after_screenshot"])
        payload = {
            "timestamp": timestamp,
            "matched_window_title": normalize_text(window_win32.window_text()),
            "process_id": int(window_win32.process_id()),
            "tab_backend": tab_backend,
            "state": asdict(state),
            "before_screenshot_path": str(artifact_paths["before_screenshot"]),
            "after_screenshot_path": str(artifact_paths["after_screenshot"]),
        }
        write_json(artifact_paths["log"], payload)
        print_settings_state(state, tab_backend)
        print(f"before screenshot: {artifact_paths['before_screenshot']}")
        print(f"after screenshot: {artifact_paths['after_screenshot']}")
        print(f"log: {artifact_paths['log']}")
        return 0
    except Exception as exc:
        payload = {
            "timestamp": timestamp,
            "error": str(exc),
            "after_screenshot_path": str(artifact_paths["after_screenshot"]),
        }
        write_json(artifact_paths["log"], payload)
        print(str(exc))
        print(f"log: {artifact_paths['log']}")
        return 1


def run_apply_tester_settings_command(task_path: str, dry_run: bool, allow_gui_clicks: bool) -> int:
    if not dry_run and not allow_gui_clicks:
        print("Refusing to apply tester settings without --allow-gui-clicks.")
        return 2

    config = load_config()
    timestamp = utc_timestamp()
    artifact_paths = build_inputs_artifact_paths(config, timestamp, action="apply_tester_settings")
    try:
        task = load_task(task_path)
        _, window_win32, _, control_map, tab_backend = prepare_settings_context()
        save_window_screenshot(window_win32, artifact_paths["before_screenshot"])
        state_before = read_current_state(control_map)
        support_summary, plan = evaluate_task_support(control_map, task)

        if support_summary["unsupported"]:
            save_window_screenshot(window_win32, artifact_paths["after_screenshot"])
            payload = {
                "timestamp": timestamp,
                "task_path": str(Path(task_path)),
                "task": task_to_payload(task),
                "tab_backend": tab_backend,
                "state_before": asdict(state_before),
                "plan": plan,
                "unsupported": support_summary["unsupported"],
                "before_screenshot_path": str(artifact_paths["before_screenshot"]),
                "after_screenshot_path": str(artifact_paths["after_screenshot"]),
                "status": "unsupported",
            }
            write_json(artifact_paths["log"], payload)
            first = support_summary["unsupported"][0]
            print(f"unsupported setting: {first['setting']}")
            print(first["reason"])
            print(f"after screenshot: {artifact_paths['after_screenshot']}")
            print(f"log: {artifact_paths['log']}")
            return 1

        results: list[dict[str, Any]] = []
        if not dry_run:
            for item in plan:
                actual = apply_setting(control_map, item["setting"], str(item["resolved"]))
                verified = verify_setting(item["setting"], actual, str(item["resolved"]))
                result = {
                    "setting": item["setting"],
                    "requested": item["requested"],
                    "resolved": item["resolved"],
                    "actual": actual,
                    "verified": verified,
                }
                results.append(result)
                if not verified:
                    save_window_screenshot(window_win32, artifact_paths["after_screenshot"])
                    payload = {
                        "timestamp": timestamp,
                        "task_path": str(Path(task_path)),
                        "task": task_to_payload(task),
                        "tab_backend": tab_backend,
                        "state_before": asdict(state_before),
                        "results": results,
                        "before_screenshot_path": str(artifact_paths["before_screenshot"]),
                        "after_screenshot_path": str(artifact_paths["after_screenshot"]),
                        "status": "verification_failed",
                    }
                    write_json(artifact_paths["log"], payload)
                    print(f"verification failed for setting: {item['setting']}")
                    print(f"after screenshot: {artifact_paths['after_screenshot']}")
                    print(f"log: {artifact_paths['log']}")
                    return 1

        state_after = read_current_state(control_map)
        save_window_screenshot(window_win32, artifact_paths["after_screenshot"])
        payload = {
            "timestamp": timestamp,
            "task_path": str(Path(task_path)),
            "task": task_to_payload(task),
            "tab_backend": tab_backend,
            "state_before": asdict(state_before),
            "state_after": asdict(state_after),
            "plan": plan,
            "results": results,
            "dry_run": dry_run,
            "before_screenshot_path": str(artifact_paths["before_screenshot"]),
            "after_screenshot_path": str(artifact_paths["after_screenshot"]),
            "status": "ok",
        }
        write_json(artifact_paths["log"], payload)
        print(f"task: {task.name}")
        print(f"dry run: {'yes' if dry_run else 'no'}")
        print_settings_state(state_after, tab_backend)
        print(f"before screenshot: {artifact_paths['before_screenshot']}")
        print(f"after screenshot: {artifact_paths['after_screenshot']}")
        print(f"log: {artifact_paths['log']}")
        return 0
    except Exception as exc:
        payload = {
            "timestamp": timestamp,
            "task_path": str(Path(task_path)),
            "dry_run": dry_run,
            "error": str(exc),
            "after_screenshot_path": str(artifact_paths["after_screenshot"]),
            "status": "failed",
        }
        write_json(artifact_paths["log"], payload)
        print(str(exc))
        print(f"log: {artifact_paths['log']}")
        return 1
