"""The enrich stage (2K design §5/§8): `compose`'s refuse-if-unrendered gate,
and `validate_and_finish`'s honest turn from raw answer text into a written
overlay — refusals reported and excluded (2K design §6, spec §10), partial
carried through unchanged (2K Task 7 ruling 4)."""

import json
from pathlib import Path

import pytest

from sextant.application.stages import enrich as stage
from sextant.domain.redaction import Redactor

SYMBOLS = ["s maven com.acme/orders 1.0.0 com/acme/orders/Ingest#"]


class _Workspace:
    def __init__(self, symbols: list[str] | None = None) -> None:
        self._symbols = SYMBOLS if symbols is None else symbols

    def query(self, name: str, **params: object) -> list[dict[str, object]]:
        if name == "declared_symbols":
            return [{"symbol": symbol} for symbol in self._symbols]
        if name in ("open_questions", "endpoints", "resolved_config"):
            return []
        raise AssertionError(f"unexpected query: {name}")


def _component(name: str = "Ingestion edge", **overrides: object) -> dict[str, object]:
    return {
        "kind": "component",
        "evidence": "llm",
        "anchor": "after-component-overview",
        "name": name,
        "purpose": "Turns bytes off the wire into the domain's own types.",
        "members": ["com/acme/orders/Ingest#"],
        **overrides,
    }


def test_compose_refuses_a_missing_rendered_document(tmp_path: Path):
    """2K design §8: enrich needs a rendered doc to compose a brief from, and
    refuses loudly, naming the command, rather than composing around a
    document that is not there. `architecture_md=None` is how the caller (the
    composition root — `application` reads no files) says "there is none"."""
    with pytest.raises(stage.NotRenderedError) as raised:
        stage.compose(
            _Workspace(), tmp_path, "instructions", None, {}, Redactor.from_rules(), (), ()
        )
    assert "sextant module render" in str(raised.value)
    assert str(tmp_path) in str(raised.value)


def test_compose_succeeds_once_a_rendered_document_is_supplied(tmp_path: Path):
    brief = stage.compose(
        _Workspace(),
        tmp_path,
        "instructions",
        "# a module\n",
        {"module": {"id": "a-module"}, "gaps": []},
        Redactor.from_rules(),
        (),
        (),
    )
    assert "# a module" in brief.prompt
    assert brief.instructions == "instructions"


def test_a_malformed_answer_is_refused_as_a_whole_run_not_a_partial_overlay():
    """Distinct from `validate.Refusal`: this is the answer not being a JSON
    array of claims at all, so nothing here can be validated claim by claim."""
    with pytest.raises(stage.MalformedAnswersError):
        stage.validate_and_finish(
            "not json at all",
            _Workspace(),
            Path("/module"),
            Redactor.from_rules(),
            "an-agent",
            "a-model",
            "sha256:instructions",
            "sha256:workspace",
        )


def test_a_refused_claim_is_reported_and_excluded_from_the_written_overlay():
    """spec §10's refused-at-ingest case, at the stage level: the phantom
    member is refused with a reason, and the overlay that gets WRITTEN never
    carries it — "never written" (validate.py's own docstring) all the way
    through to what `cli/app.py` puts on disk."""
    answers = json.dumps(
        [_component(), _component(name="Phantom", members=["com/acme/orders/Ghost#"])]
    )
    result = stage.validate_and_finish(
        answers,
        _Workspace(),
        Path("/module"),
        Redactor.from_rules(),
        "an-agent",
        "a-model",
        "sha256:instructions",
        "sha256:workspace",
    )
    assert [claim.name for claim in result.overlay.claims] == ["Ingestion edge"]  # type: ignore[union-attr]
    assert len(result.refusals) == 1
    assert "com/acme/orders/Ghost#" in result.refusals[0].reason


def test_provenance_carries_every_field_the_caller_supplied():
    result = stage.validate_and_finish(
        json.dumps([_component()]),
        _Workspace(),
        Path("/module"),
        Redactor.from_rules(),
        "claude-api",
        "claude-x",
        "sha256:instructions",
        "sha256:workspace",
        run_at="2026-09-02T00:00:00Z",
    )
    produced_by = result.overlay.produced_by
    assert produced_by.model == "claude-x"
    assert produced_by.agent == "claude-api"
    assert produced_by.instructions_hash == "sha256:instructions"
    assert produced_by.workspace_fingerprint == "sha256:workspace"
    assert produced_by.run_at == "2026-09-02T00:00:00Z"
    assert produced_by.redaction_set_hash == Redactor.from_rules().rule_set_hash


def test_partial_and_its_reason_carry_through_to_the_result_unchanged():
    """2K Task 7 ruling 4: an honest record of how the run ended has to reach
    the caller — the stage never launders a truncated run into a clean one."""
    result = stage.validate_and_finish(
        json.dumps([_component()]),
        _Workspace(),
        Path("/module"),
        Redactor.from_rules(),
        "claude-api",
        "claude-x",
        "sha256:instructions",
        "sha256:workspace",
        partial=True,
        partial_reason="max_turns",
        transcript=({"name": "read_file", "args": {}, "result": "ok"},),
    )
    assert (result.partial, result.partial_reason) == (True, "max_turns")
    assert result.transcript == ({"name": "read_file", "args": {}, "result": "ok"},)


def test_a_textless_partial_is_a_loud_failure_naming_the_reason_not_a_malformed_answer():
    """2N design §1: a capped run that produced no final text is reported
    naming WHY it ended early, never laundered into `MalformedAnswersError`
    — there is no JSON here that failed to parse, only an honest absence."""
    with pytest.raises(stage.EmptyPartialAnswerError) as raised:
        stage.validate_and_finish(
            "",
            _Workspace(),
            Path("/module"),
            Redactor.from_rules(),
            "an-agent",
            "a-model",
            "sha256:instructions",
            "sha256:workspace",
            partial=True,
            partial_reason="no_progress",
        )
    assert "no_progress" in str(raised.value)


def test_a_whitespace_only_partial_is_also_treated_as_textless():
    with pytest.raises(stage.EmptyPartialAnswerError):
        stage.validate_and_finish(
            "   \n",
            _Workspace(),
            Path("/module"),
            Redactor.from_rules(),
            "an-agent",
            "a-model",
            "sha256:instructions",
            "sha256:workspace",
            partial=True,
            partial_reason="max_turns",
        )


def test_a_non_empty_partial_answer_is_still_validated_normally():
    """The textless ruling only fires on EMPTY text — a partial run that did
    produce a real (if incomplete-context) answer is validated exactly as a
    clean run's answer would be, `partial`/`partial_reason` carried through
    unchanged (the existing `test_partial_and_its_reason_carry_through_to_
    the_result_unchanged` pin)."""
    result = stage.validate_and_finish(
        json.dumps([_component()]),
        _Workspace(),
        Path("/module"),
        Redactor.from_rules(),
        "an-agent",
        "a-model",
        "sha256:instructions",
        "sha256:workspace",
        partial=True,
        partial_reason="stop:max_tokens",
    )
    assert (result.partial, result.partial_reason) == (True, "stop:max_tokens")


def test_an_ingested_answer_defaults_to_a_clean_non_partial_record():
    result = stage.validate_and_finish(
        json.dumps([_component()]),
        _Workspace(),
        Path("/module"),
        Redactor.from_rules(),
        "a-human",
        "n/a",
        "sha256:instructions",
        "sha256:workspace",
    )
    assert (result.partial, result.partial_reason) == (False, None)
