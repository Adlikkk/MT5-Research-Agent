from pathlib import Path

from mt5_research_agent.config import AppConfig
from mt5_research_agent.inspect import (
    build_artifact_paths,
    build_not_found_message,
    inspection_to_payload,
    matches_title,
    utc_timestamp,
    WindowInspection,
)


def test_matches_title_is_case_insensitive() -> None:
    assert matches_title("MetaTrader 5 Strategy Tester", "strategy tester") is True


def test_build_artifact_paths_creates_expected_targets(tmp_path: Path) -> None:
    config = AppConfig(
        terminal_path="",
        portable_mode=False,
        mt5_window_title_contains="Strategy Tester",
        artifacts_dir=str(tmp_path / "artifacts"),
        results_dir=str(tmp_path / "results"),
        default_timeout_seconds=30,
    )

    screenshot_path, log_path = build_artifact_paths(config, "20260611T120000Z")

    assert screenshot_path.parent.exists()
    assert log_path.parent.exists()
    assert screenshot_path.name == "inspect_20260611T120000Z.png"
    assert log_path.name == "inspect_20260611T120000Z.json"


def test_build_not_found_message_includes_guidance() -> None:
    config = AppConfig(
        terminal_path="",
        portable_mode=False,
        mt5_window_title_contains="Strategy Tester",
        artifacts_dir="artifacts",
        results_dir="results",
        default_timeout_seconds=30,
    )

    message = build_not_found_message(config, "uia")

    assert "No MT5 window found" in message
    assert "Open MetaTrader 5 manually" in message


def test_inspection_to_payload_contains_visible_controls() -> None:
    result = WindowInspection(
        timestamp=utc_timestamp(),
        backend="uia",
        matched_window_title="MetaTrader 5",
        process_id=1234,
        dump_depth=2,
        screenshot_path="artifacts/screenshots/inspect.png",
        visible_child_controls=[],
    )

    payload = inspection_to_payload(result)

    assert payload["backend"] == "uia"
    assert payload["process_id"] == 1234
    assert payload["visible_child_controls"] == []
