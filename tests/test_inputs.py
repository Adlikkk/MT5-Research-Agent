from mt5_research_agent.inputs import (
    find_input_parameter,
    identifier_acronym,
    is_subsequence,
    normalized_identifier,
    parse_inputs_export,
    sanitize_filename,
)


SAMPLE_EXPORT = """MagicNumber=2026060911||2026060911||1||20260609110||N
TakeProfit_R=2.2||1.5||0.150000||15.000000||N
BreakEvenAtR=1.2||0.85||0.085000||8.500000||N
"""


def test_parse_inputs_export_reads_rows() -> None:
    parameters = parse_inputs_export(SAMPLE_EXPORT)

    assert len(parameters) == 3
    assert parameters[1].name == "TakeProfit_R"
    assert parameters[1].current_value == "2.2"
    assert parameters[1].row_index == 1


def test_find_input_parameter_matches_acronym() -> None:
    parameters = parse_inputs_export(SAMPLE_EXPORT)

    result = find_input_parameter(parameters, "TP_R")

    assert result.name == "TakeProfit_R"


def test_identifier_helpers_normalize_names() -> None:
    assert normalized_identifier("TakeProfit_R") == "takeprofitr"
    assert identifier_acronym("TakeProfit_R") == "tpr"
    assert is_subsequence("tpr", "takeprofitr") is True


def test_sanitize_filename_replaces_unsafe_characters() -> None:
    assert sanitize_filename("TP/R value") == "TP_R_value"
