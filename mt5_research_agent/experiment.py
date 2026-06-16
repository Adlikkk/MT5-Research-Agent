from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mt5_research_agent.config import load_config
from mt5_research_agent.report_parser import normalize_line
from mt5_research_agent.result_store import update_leaderboard_csv, update_summary_md
from mt5_research_agent.run_task import execute_run_task
from mt5_research_agent.task import ResearchTask, load_task, task_to_payload


@dataclass(slots=True)
class ExperimentLimits:
    max_tests: int
    stop_after_failures: int


@dataclass(slots=True)
class ExperimentSpec:
    name: str
    base_task: str
    matrix: dict[str, list[str]]
    limits: ExperimentLimits
    id_prefix: str | None = None


def _require_non_empty_string(data: dict[str, Any], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Field '{field_name}' must be a non-empty string.")
    return value.strip()


def _validate_matrix(data: dict[str, Any]) -> dict[str, list[str]]:
    value = data.get("matrix")
    if not isinstance(value, dict) or not value:
        raise ValueError("Field 'matrix' must be a non-empty object.")
    matrix: dict[str, list[str]] = {}
    for key, items in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Every matrix key must be a non-empty string.")
        if not isinstance(items, list) or not items:
            raise ValueError(f"Matrix entry '{key}' must be a non-empty list.")
        normalized_items: list[str] = []
        for item in items:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"Matrix value for '{key}' must be a non-empty string.")
            normalized_items.append(item.strip())
        matrix[key.strip()] = normalized_items
    return matrix


def _validate_limits(data: dict[str, Any]) -> ExperimentLimits:
    value = data.get("limits")
    if not isinstance(value, dict):
        raise ValueError("Field 'limits' must be an object.")
    max_tests = value.get("max_tests")
    stop_after_failures = value.get("stop_after_failures")
    if not isinstance(max_tests, int) or max_tests <= 0:
        raise ValueError("Field 'limits.max_tests' must be a positive integer.")
    if not isinstance(stop_after_failures, int) or stop_after_failures <= 0:
        raise ValueError("Field 'limits.stop_after_failures' must be a positive integer.")
    return ExperimentLimits(max_tests=max_tests, stop_after_failures=stop_after_failures)


def validate_experiment_payload(payload: dict[str, Any]) -> ExperimentSpec:
    id_prefix = payload.get("id_prefix")
    if id_prefix is not None:
        if not isinstance(id_prefix, str) or not id_prefix.strip():
            raise ValueError("Field 'id_prefix' must be a non-empty string when provided.")
        id_prefix = id_prefix.strip()
    return ExperimentSpec(
        name=_require_non_empty_string(payload, "name"),
        base_task=_require_non_empty_string(payload, "base_task"),
        matrix=_validate_matrix(payload),
        limits=_validate_limits(payload),
        id_prefix=id_prefix,
    )


def load_experiment(experiment_path: str | Path) -> ExperimentSpec:
    path = Path(experiment_path)
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Experiment file must contain a JSON object.")
    return validate_experiment_payload(payload)


def experiment_prefix(name: str) -> str:
    token = normalize_line(name).split("_", 1)[0]
    token = "".join(char for char in token if char.isalnum()).upper()
    return token or "EXP"


def generated_tasks_dir() -> Path:
    config = load_config()
    path = Path(config.artifacts_dir).resolve() / "generated_tasks"
    path.mkdir(parents=True, exist_ok=True)
    return path


def experiment_state_path(experiment_name: str) -> Path:
    config = load_config()
    root = Path(config.results_dir).resolve() / "experiments"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{experiment_name}.json"


def build_generated_tasks(experiment: ExperimentSpec, base_task: ResearchTask) -> list[dict[str, Any]]:
    keys = list(experiment.matrix)
    values_product = list(itertools.product(*(experiment.matrix[key] for key in keys)))
    tasks: list[dict[str, Any]] = []
    prefix = experiment.id_prefix or experiment_prefix(experiment.name)
    for index, combo in enumerate(values_product[: experiment.limits.max_tests], start=1):
        test_id = f"{prefix}-{index:04d}"
        task_payload = task_to_payload(base_task)
        task_payload["test_id"] = test_id
        task_payload["name"] = f"{experiment.name}_{test_id.lower()}"
        inputs = dict(task_payload["inputs"])
        for key, value in zip(keys, combo, strict=True):
            inputs[key] = value
        task_payload["inputs"] = inputs
        tasks.append(task_payload)
    return tasks


def write_generated_tasks(experiment: ExperimentSpec, tasks: list[dict[str, Any]]) -> list[Path]:
    output_dir = generated_tasks_dir() / experiment.name
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for task_payload in tasks:
        path = output_dir / f"{task_payload['test_id']}.json"
        path.write_text(json.dumps(task_payload, indent=2), encoding="utf-8")
        paths.append(path)
    return paths


def load_experiment_state(experiment_name: str) -> dict[str, Any]:
    path = experiment_state_path(experiment_name)
    if not path.exists():
        return {"completed": {}, "attempts": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_experiment_state(experiment_name: str, state: dict[str, Any]) -> Path:
    path = experiment_state_path(experiment_name)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return path


def run_validate_experiment_command(experiment_path: str) -> int:
    try:
        experiment = load_experiment(experiment_path)
    except Exception as exc:
        print(str(exc))
        return 1
    print(f"name: {experiment.name}")
    print(f"base_task: {experiment.base_task}")
    print(f"matrix_keys: {', '.join(experiment.matrix)}")
    print(f"max_tests: {experiment.limits.max_tests}")
    print("experiment validation: ok")
    return 0


def run_generate_tasks_command(experiment_path: str) -> int:
    try:
        experiment = load_experiment(experiment_path)
        base_task = load_task(experiment.base_task)
        tasks = build_generated_tasks(experiment, base_task)
        paths = write_generated_tasks(experiment, tasks)
    except Exception as exc:
        print(str(exc))
        return 1
    print(f"experiment: {experiment.name}")
    print(f"generated tasks: {len(paths)}")
    print(f"output dir: {paths[0].parent if paths else generated_tasks_dir() / experiment.name}")
    return 0


def run_experiment_command(experiment_path: str, allow_gui_clicks: bool, timeout_seconds: int = 1800) -> int:
    if not allow_gui_clicks:
        print("Refusing to run an experiment without --allow-gui-clicks.")
        return 2

    try:
        experiment = load_experiment(experiment_path)
        base_task = load_task(experiment.base_task)
        generated_tasks = build_generated_tasks(experiment, base_task)
        task_paths = write_generated_tasks(experiment, generated_tasks)
        state = load_experiment_state(experiment.name)
        completed: dict[str, Any] = state.get("completed", {})
        attempts: list[dict[str, Any]] = state.get("attempts", [])

        failures = 0
        processed = 0
        for task_payload, task_path in zip(generated_tasks, task_paths, strict=True):
            test_id = task_payload["test_id"]
            if test_id in completed:
                continue

            result = execute_run_task(str(task_path), allow_gui_clicks=True, timeout_seconds=timeout_seconds)
            attempt = {
                "test_id": test_id,
                "task_path": str(task_path),
                "status": result.status,
                "exit_code": result.exit_code,
                "log_path": result.log_path,
                "screenshot_path": result.screenshot_path,
            }
            attempts.append(attempt)
            completed[test_id] = attempt
            state["completed"] = completed
            state["attempts"] = attempts
            save_experiment_state(experiment.name, state)
            update_leaderboard_csv()
            update_summary_md()

            processed += 1
            if result.exit_code != 0:
                failures += 1
            if result.safety_ui_failure:
                print(f"experiment stopped on safety/UI failure at {test_id}")
                print(f"log: {result.log_path}")
                return 1
            if failures >= experiment.limits.stop_after_failures:
                print(f"experiment stopped after {failures} failures")
                print(f"state: {experiment_state_path(experiment.name)}")
                return 1

        print(f"experiment: {experiment.name}")
        print(f"processed this run: {processed}")
        print(f"completed total: {len(completed)}/{len(generated_tasks)}")
        print(f"state: {experiment_state_path(experiment.name)}")
        return 0
    except Exception as exc:
        print(str(exc))
        return 1
