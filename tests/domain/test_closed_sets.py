from sextant.domain.closed_sets import Evidence, precedence_of


def test_precedence_ranks_human_above_code_when_evidence_is_curated():
    assert precedence_of(Evidence.HUMAN) == 90


def test_precedence_ranks_model_below_code_when_evidence_is_llm():
    assert precedence_of(Evidence.LLM) == 10


def test_precedence_is_fifty_when_evidence_is_any_code_derived_value():
    for evidence in (Evidence.COMPILER, Evidence.SYNTAX, Evidence.NAME_MATCH, Evidence.DECLARED):
        assert precedence_of(evidence) == 50
