"""The overlay's schema (2K design §6).

The file is a program artifact, so the schema is the only thing standing
between a malformed write and a document that renders half a claim. Every
test here is about a refusal being LOUD rather than a value being coerced —
`extra: forbid`, a closed anchor set, a one-value `evidence`, and the two
shapes a verdict is allowed to take.
"""

import json

import pytest
from pydantic import ValidationError

from sextant.domain.closed_sets import Anchor
from sextant.domain.enrichment import (
    ComponentClaim,
    ConfigQuestionRef,
    EnrichmentOverlay,
    OpenQuestionRef,
    Provenance,
    VerdictClaim,
)

PROVENANCE = {
    "model": "a-model",
    "agent": "an-agent",
    "instructions_hash": "sha256:aaa",
    "redaction_set_hash": "sha256:bbb",
    "run_at": "2026-09-02T00:00:00Z",
    "workspace_fingerprint": "sha256:ccc",
}

COMPONENT = {
    "kind": "component",
    "evidence": "llm",
    "anchor": "after-component-overview",
    "name": "Ingestion edge",
    "purpose": "Turns bytes off the wire into the domain's own types.",
    "members": ["com/acme/orders/Ingest#"],
}
SECTION = {
    "kind": "section",
    "evidence": "llm",
    "anchor": "end-of-document",
    "title": "Extending the ingestion edge",
    "body": "Add a listener, then bind its payload.",
    "cites": ["src/main/java/com/acme/orders/Ingest.java"],
}
DIAGRAM = {
    "kind": "diagram",
    "evidence": "llm",
    "anchor": "after-endpoint-table",
    "mermaid": "classDiagram\n    class Ingest\n",
    "elides": "showing 1 of 40 classes; error paths elided",
}
VERDICT = {
    "kind": "verdict",
    "evidence": "llm",
    "anchor": "beside-open-question",
    "question": {"protocol": "a-protocol", "method": None, "path": "a-queue", "kind": "a-question"},
    "assessment": "likely OrderRequest",
    "because": "Ingest#process parses it",
}
UNANSWERED_VERDICT = {
    "kind": "verdict",
    "evidence": "llm",
    "anchor": "beside-open-question",
    "question": {"protocol": "a-protocol", "method": None, "path": "a-queue", "kind": "a-question"},
    "assessment": "unanswered",
    "searched": "read every listener in the module; none names a payload type",
}
CONFIG_VERDICT = {
    "kind": "verdict",
    "evidence": "llm",
    "anchor": "beside-open-question",
    "question": {
        "key": "spring.config.import",
        "source": "application.yml",
        "environment": "default",
        "kind": "remote_source",
    },
    "assessment": "likely a Config Server import",
    "because": "the profile declares `spring.config.import=configserver:`",
}
CONFIG_VERDICT_NULL_SOURCE = {
    "kind": "verdict",
    "evidence": "llm",
    "anchor": "beside-open-question",
    "question": {
        "key": "server.port",
        "source": None,
        "environment": "docker",
        "kind": "missing_key",
    },
    "assessment": "unanswered",
    "searched": "grepped every profile-scoped application-*.yml; the key is declared nowhere",
}
ALL_KINDS = [
    COMPONENT,
    SECTION,
    DIAGRAM,
    VERDICT,
    UNANSWERED_VERDICT,
    CONFIG_VERDICT,
    CONFIG_VERDICT_NULL_SOURCE,
]


def _overlay(*claims: dict[str, object]) -> dict[str, object]:
    return {"produced_by": PROVENANCE, "claims": list(claims)}


def test_every_claim_kind_round_trips_through_json_unchanged():
    """The overlay is written wholesale and read back by render — a field that
    does not survive the round trip is a claim that renders differently from
    the one the run produced (2K design §6, "exact round-trips")."""
    document = json.dumps(_overlay(*ALL_KINDS))
    overlay = EnrichmentOverlay.model_validate_json(document)
    assert EnrichmentOverlay.model_validate_json(overlay.model_dump_json()) == overlay
    # Field by field against what was written, not only model equality: a
    # field silently dropped on the way in would compare equal to itself on
    # the way out and the round trip would pass while the claim lost half its
    # content. The dump carries the two nullable verdict halves as explicit
    # nulls, which is why this is a subset check rather than an equality one.
    dumped = json.loads(overlay.model_dump_json())
    assert dumped["produced_by"] == PROVENANCE
    for written, read_back in zip(ALL_KINDS, dumped["claims"], strict=True):
        assert {key: read_back[key] for key in written} == written


def test_an_unknown_claim_kind_is_refused_by_name():
    """A kind outside the closed set is a schema change nobody made (NFR-5).
    The discriminator is what makes the error name the offending value rather
    than reporting four unrelated variant failures."""
    unknown = dict(COMPONENT, kind="diagram-ish")
    with pytest.raises(ValidationError, match="diagram-ish"):
        EnrichmentOverlay.model_validate(_overlay(unknown))


def test_an_unknown_anchor_is_refused():
    """Render places a claim by its anchor and by nothing else. An anchor it
    has no rule for is a claim it would have to guess a position for."""
    with pytest.raises(ValidationError, match="after-the-nice-bit"):
        EnrichmentOverlay.model_validate(_overlay(dict(COMPONENT, anchor="after-the-nice-bit")))


@pytest.mark.parametrize("field", ["kind", "evidence", "anchor", "name", "purpose", "members"])
def test_a_claim_missing_any_of_its_fields_is_refused(field: str):
    """Nothing is optional that render reads: a component with no purpose is
    the one thing a component claim exists to carry."""
    incomplete = {key: value for key, value in COMPONENT.items() if key != field}
    with pytest.raises(ValidationError):
        EnrichmentOverlay.model_validate(_overlay(incomplete))


def test_evidence_must_be_llm():
    """The overlay's whole reason for existing: model output stays marked as
    model output, and no claim can enter the document wearing the derived
    half's marker (2K design §6)."""
    with pytest.raises(ValidationError, match="evidence"):
        EnrichmentOverlay.model_validate(_overlay(dict(COMPONENT, evidence="compiler")))


def test_a_field_the_schema_does_not_know_is_refused():
    """`extra: forbid`. A field render never reads is half a claim that
    silently does not appear — and a program artifact has no reason to carry
    one."""
    with pytest.raises(ValidationError, match="confidence"):
        EnrichmentOverlay.model_validate(_overlay(dict(COMPONENT, confidence=0.9)))


def test_provenance_is_required_whole():
    """A document cannot say what produced the words a reader is about to
    trust if the block naming the run has a hole in it (2K design §6)."""
    partial = {key: value for key, value in PROVENANCE.items() if key != "instructions_hash"}
    with pytest.raises(ValidationError, match="instructions_hash"):
        EnrichmentOverlay.model_validate({"produced_by": partial, "claims": []})


def test_an_answered_verdict_must_carry_its_grounding():
    """Spec §7's label reads "likely X, because Y". Without the because it is
    an opinion typeset as a finding."""
    with pytest.raises(ValidationError, match="because"):
        EnrichmentOverlay.model_validate(
            _overlay({key: value for key, value in VERDICT.items() if key != "because"})
        )


def test_an_unanswered_verdict_must_say_what_was_searched():
    """`unanswered` beats a guess only when it says what was looked at — an
    unanswered verdict with no trail is indistinguishable from not looking
    (2K design §7)."""
    with pytest.raises(ValidationError, match="searched"):
        EnrichmentOverlay.model_validate(
            _overlay({key: value for key, value in UNANSWERED_VERDICT.items() if key != "searched"})
        )


def test_a_verdict_cannot_be_both_answered_and_unanswered():
    """The two shapes are exclusive: a claim carrying both halves says it
    answered the question and did not."""
    with pytest.raises(ValidationError):
        EnrichmentOverlay.model_validate(_overlay(dict(UNANSWERED_VERDICT, because="a reason")))


def test_an_overlay_with_no_claims_is_valid():
    """A run that grounded nothing still says so. "No overlay" and "an overlay
    claiming nothing" are different statements, and only the schema can keep
    them different."""
    assert EnrichmentOverlay.model_validate(_overlay()).claims == []


def test_the_anchor_set_is_exactly_the_four_the_spec_names():
    """Closed set (2K design §6). A fifth anchor is a schema change AND a
    placement rule in the assembler; this pin is what makes adding one without
    the other fail here rather than in a document."""
    assert [anchor.value for anchor in Anchor] == [
        "after-endpoint-table",
        "after-component-overview",
        "beside-open-question",
        "end-of-document",
    ]


def test_a_claim_is_frozen_once_validated():
    """The overlay is written wholesale and read many times; a claim mutated
    between the validation that accepted it and the assembly that renders it
    would be a claim nothing checked."""
    claim = ComponentClaim.model_validate(COMPONENT)
    with pytest.raises(ValidationError):
        claim.name = "something else"


def test_provenance_and_the_verdict_reference_reject_unknown_fields_too():
    """`extra: forbid` is not only on the claims: a provenance field nobody
    reads is a run detail the document does not carry, and a question
    reference with a spare column names a row identity that does not exist."""
    with pytest.raises(ValidationError, match="temperature"):
        Provenance.model_validate(dict(PROVENANCE, temperature=0.0))
    with pytest.raises(ValidationError, match="topic"):
        VerdictClaim.model_validate(
            dict(VERDICT, question=dict(VERDICT["question"], topic="orders"))  # type: ignore[call-overload]
        )


# --- 2N design §2: the identity union widens to config-shaped questions ---


def test_a_config_shaped_verdict_question_is_accepted():
    """A verdict about an unresolved `resolved_config` row is exactly as
    valid as one about an `open_questions` row (2N design §2) — the same
    claim kind, a different identity shape, so config-shaped uncertainty
    stops being unanswerable."""
    claim = VerdictClaim.model_validate(CONFIG_VERDICT)
    assert isinstance(claim.question, ConfigQuestionRef)
    assert claim.question.source == "application.yml"


def test_a_config_verdict_with_a_null_source_is_accepted():
    """A `missing_key` row was never declared in any file, so no file ever
    won it (D01) — `source` is nullable, and a verdict about such a row
    states that explicitly rather than being unable to name one."""
    claim = VerdictClaim.model_validate(CONFIG_VERDICT_NULL_SOURCE)
    assert claim.question.source is None


def test_an_endpoint_shaped_verdict_question_still_parses_as_the_endpoint_shape():
    """Widening `question` to a union must not change what the EXISTING
    endpoint shape parses as: an overlay written before this change still
    comes back as `OpenQuestionRef`, not the config shape wearing the same
    union — the whole reason every existing overlay validates unchanged."""
    claim = VerdictClaim.model_validate(VERDICT)
    assert isinstance(claim.question, OpenQuestionRef)


@pytest.mark.parametrize("field", ["key", "environment", "kind"])
def test_a_config_question_missing_any_of_its_fields_is_refused(field: str):
    """Nothing is optional that identity depends on: a config verdict with no
    `environment`, for one, could not be matched to the row that disambiguates
    by it alone — the live rows this shape was verified against
    (`spring.config.import`) differ from each other ONLY by environment."""
    incomplete = {k: v for k, v in CONFIG_VERDICT["question"].items() if k != field}
    with pytest.raises(ValidationError):
        VerdictClaim.model_validate(dict(CONFIG_VERDICT, question=incomplete))


def test_a_config_question_with_an_extra_field_is_refused():
    """`extra: forbid` on the config shape too: a spare column names a row
    identity that does not exist, the same rule the endpoint shape keeps."""
    with pytest.raises(ValidationError, match="profile"):
        VerdictClaim.model_validate(
            dict(CONFIG_VERDICT, question=dict(CONFIG_VERDICT["question"], profile="cloud"))
        )


def test_a_question_shaped_like_both_kinds_at_once_is_refused_not_guessed():
    """The ambiguity probe: `question`/`kind` vs `key`/`source`/`environment`
    are disjoint required-field sets, so a payload wearing both shapes' fields
    matches NEITHER member under `extra="forbid"` — pydantic's smart union
    refuses it rather than guessing which shape was meant."""
    ambiguous = dict(VERDICT["question"], key="spring.config.import", environment="default")
    with pytest.raises(ValidationError):
        VerdictClaim.model_validate(dict(VERDICT, question=ambiguous))
