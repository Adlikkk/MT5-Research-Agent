from pathlib import Path

from mt5_research_agent.config import AppConfig
from mt5_research_agent.tester import (
    TESTER_KEYWORDS,
    build_tester_artifact_paths,
    control_matches_tester,
    detect_tester_visibility,
    serialize_control,
)


class FakeControl:
    def __init__(self, window_text: str, control_type: str, class_name: str) -> None:
        self.window_text = window_text
        self.control_type = control_type
        self.class_name = class_name


def test_control_matches_tester_uses_expected_keywords() -> None:
    control = FakeControl("Strategy Tester", "Pane", "")

    assert "strategy tester" in TESTER_KEYWORDS
    assert control_matches_tester(control) is True


def test_build_tester_artifact_paths_creates_targets(tmp_path: Path) -> None:
    config = AppConfig(
        terminal_path="",
        portable_mode=False,
        mt5_window_title_contains="MetaTrader",
        artifacts_dir=str(tmp_path / "artifacts"),
        results_dir=str(tmp_path / "results"),
        default_timeout_seconds=30,
    )

    artifact_paths = build_tester_artifact_paths(config, "20260611T120000Z")

    assert artifact_paths["before_screenshot"].parent.exists()
    assert artifact_paths["after_screenshot"].parent.exists()
    assert artifact_paths["open_log"].parent.exists()


def test_detect_tester_visibility_finds_matching_controls(monkeypatch) -> None:
    class FakeWindow:
        pass

    monkeypatch.setattr(
        "mt5_research_agent.tester.walk_visible_controls",
        lambda _window, max_depth: [
            type(
                "ControlSnapshot",
                (),
                {
                    "depth": 1,
                    "control_type": "Pane",
                    "class_name": "",
                    "window_text": "Strategy Tester",
                    "is_visible": True,
                    "is_enabled": True,
                    "rectangle": "(0, 0, 10, 10)",
                },
            )()
        ],
    )

    status = detect_tester_visibility(FakeWindow(), dump_depth=3)

    assert status.is_visible is True
    assert status.matched_controls[0]["window_text"] == "Strategy Tester"


def test_serialize_control_supports_non_dataclass_objects() -> None:
    payload = serialize_control(FakeControl("Strategy Tester", "Pane", ""))

    assert payload["window_text"] == "Strategy Tester"
    assert payload["control_type"] == "Pane"
