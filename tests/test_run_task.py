from mt5_research_agent.run_task import StartButtonSnapshot, is_ready_state, is_running_state, normalize_button_label


def test_normalize_button_label_folds_czech_text() -> None:
    assert normalize_button_label("Začátek") == "zacatek"


def test_is_ready_state_detects_start_button() -> None:
    snapshot = StartButtonSnapshot(text="Začátek", folded_text="zacatek", enabled=True, visible=True)

    assert is_ready_state(snapshot) is True
    assert is_running_state(snapshot) is False


def test_is_running_state_handles_stop_button() -> None:
    snapshot = StartButtonSnapshot(text="Stop", folded_text="stop", enabled=True, visible=True)

    assert is_running_state(snapshot) is True
