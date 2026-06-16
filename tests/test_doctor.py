from pathlib import Path

from mt5_research_agent.doctor import (
    check_config_exists,
    check_directory_exists,
    check_python_version,
    check_terminal_path,
    render_doctor_report,
)


def test_check_python_version_accepts_python_311() -> None:
    result = check_python_version((3, 11, 0))

    assert result.ok is True


def test_check_config_exists_reports_missing_file(tmp_path: Path) -> None:
    result = check_config_exists(tmp_path / "missing.json")

    assert result.ok is False


def test_check_terminal_path_allows_empty_configuration(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        """
        {
          "terminal_path": "",
          "portable_mode": false,
          "mt5_window_title_contains": "Strategy Tester",
          "artifacts_dir": "artifacts",
          "results_dir": "results",
          "default_timeout_seconds": 30
        }
        """.strip(),
        encoding="utf-8",
    )

    result = check_terminal_path(config_path)

    assert result.ok is False
    assert "terminal64.exe" in result.detail


def test_check_terminal_path_rejects_non_terminal64_exe(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        f"""
        {{
          "terminal_path": "{(tmp_path / "mt5.exe").as_posix()}",
          "portable_mode": false,
          "mt5_window_title_contains": "Strategy Tester",
          "artifacts_dir": "artifacts",
          "results_dir": "results",
          "default_timeout_seconds": 30
        }}
        """.strip(),
        encoding="utf-8",
    )

    result = check_terminal_path(config_path)

    assert result.ok is False
    assert "must end with terminal64.exe" in result.detail


def test_check_directory_exists_reports_existing_directory(tmp_path: Path) -> None:
    result = check_directory_exists(tmp_path, "results_dir")

    assert result.ok is True


def test_render_doctor_report_contains_status_lines() -> None:
    report = render_doctor_report([check_python_version((3, 11, 0))])

    assert "python_version" in report
    assert "[PASS]" in report
