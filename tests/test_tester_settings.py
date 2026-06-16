from mt5_research_agent.tester_settings import (
    fold_text,
    normalize_key,
    normalize_model_target,
    normalize_symbol_aliases,
    resolve_combo_option,
)


class FakeCombo:
    def __init__(self, values: list[str]) -> None:
        self._values = values

    def texts(self) -> list[str]:
        return self._values


def test_fold_text_removes_czech_diacritics() -> None:
    assert fold_text("Nastavení") == "Nastaveni"


def test_normalize_symbol_aliases_include_dot_variant() -> None:
    aliases = normalize_symbol_aliases("XAUUSD_DUKA")

    assert "XAUUSD.DUKA" in aliases


def test_normalize_model_target_maps_english_name() -> None:
    assert normalize_model_target("Every tick based on real ticks") == "Kazdy tick zalozen na realnych ticich"


def test_resolve_combo_option_matches_normalized_text() -> None:
    combo = FakeCombo(["Každý tick založen na reálných ticích", "1 minuta OHLC"])

    result = resolve_combo_option(combo, "Kazdy tick zalozen na realnych ticich")

    assert result == "Každý tick založen na reálných ticích"


def test_normalize_key_strips_ea_path_and_extension() -> None:
    assert normalize_key(r"Advisors\GoldEA.ex5") == "goldea"
