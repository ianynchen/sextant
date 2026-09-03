"""Validation by construction and staleness (2K design §6).

The overlay is the one place model output enters a Sextant document, and the
only thing standing between "the model wrote a class name" and "the document
names a class" is this module. Every test here is about a claim naming a
PHANTOM — a member, a node, a file, a question that does not exist — being
refused with a reason a person can act on, and about the checks the scan
deliberately cannot make being stated rather than faked.
"""

from pathlib import Path

from sextant.application.enrich.validate import stale_claims, validate_overlay
from sextant.domain.enrichment import EnrichmentOverlay
from sextant.domain.redaction import Redactor

PROVENANCE = {
    "model": "a-model",
    "agent": "an-agent",
    "instructions_hash": "sha256:aaa",
    "redaction_set_hash": "sha256:bbb",
    "run_at": "2026-09-02T00:00:00Z",
    "workspace_fingerprint": "sha256:ccc",
}

# Symbols as the workspace holds them: module coordinates, then the descriptor
# (D00 §5a). A claim may spell either form; only the descriptor is compared.
SYMBOLS = [
    "s maven com.acme/orders 1.0.0 com/acme/orders/Ingest#",
    "s maven com.acme/orders 1.0.0 com/acme/orders/Ingest#process(sig_1).",
    "s maven com.acme/orders 1.0.0 com/acme/orders/Relay#",
]
QUESTION = {
    "protocol": "a-protocol",
    "method": None,
    "path": "a-queue",
    "question": "a-question",
    "candidates": "[]",
    "evidence": "compiler",
}


class _Workspace:
    """The two named queries validation reads, and nothing else. A hand-built
    workspace rather than an analysed fixture: these tests are about which
    claims are refused, and a fixture would tie every assertion to whatever
    the fixture's own code happens to declare this month."""

    def __init__(
        self,
        symbols: list[str] | None = None,
        open_questions: list[dict[str, object]] | None = None,
    ) -> None:
        self._symbols = SYMBOLS if symbols is None else symbols
        self._open_questions = [QUESTION] if open_questions is None else open_questions

    def query(self, name: str, **params: object) -> list[dict[str, object]]:
        if name == "declared_symbols":
            return [{"symbol": symbol} for symbol in self._symbols]
        if name == "open_questions":
            return list(self._open_questions)
        raise AssertionError(f"validation asked for an unexpected query: {name}")


def _overlay(*claims: dict[str, object]) -> EnrichmentOverlay:
    return EnrichmentOverlay.model_validate({"produced_by": PROVENANCE, "claims": list(claims)})


def _component(**overrides: object) -> dict[str, object]:
    return {
        "kind": "component",
        "evidence": "llm",
        "anchor": "after-component-overview",
        "name": "Ingestion edge",
        "purpose": "Turns bytes off the wire into the domain's own types.",
        "members": ["com/acme/orders/Ingest#"],
        **overrides,
    }


def _diagram(mermaid: str) -> dict[str, object]:
    return {
        "kind": "diagram",
        "evidence": "llm",
        "anchor": "after-endpoint-table",
        "mermaid": mermaid,
        "elides": "showing 2 of 40 classes; error paths elided",
    }


def _section(cites: list[str]) -> dict[str, object]:
    return {
        "kind": "section",
        "evidence": "llm",
        "anchor": "end-of-document",
        "title": "Extending the ingestion edge",
        "body": "Add a listener, then bind its payload.",
        "cites": cites,
    }


def _verdict(**overrides: object) -> dict[str, object]:
    return {
        "kind": "verdict",
        "evidence": "llm",
        "anchor": "beside-open-question",
        "question": {
            "protocol": "a-protocol",
            "method": None,
            "path": "a-queue",
            "kind": "a-question",
        },
        "assessment": "likely OrderRequest",
        "because": "Ingest#process parses it",
        **overrides,
    }


def test_a_component_member_that_is_not_a_symbol_is_refused_by_name(tmp_path: Path):
    """The claim the whole overlay rests on (2K design §6): a model naming a
    class that does not exist gets refused at ingest, never written. The
    reason names the member, because "component refused" tells nobody which of
    five members was invented."""
    overlay = _overlay(_component(members=["com/acme/orders/Ingest#", "com/acme/orders/Ghost#"]))
    accepted, refusals = validate_overlay(overlay, _Workspace(), tmp_path)
    assert accepted == ()
    assert len(refusals) == 1
    assert refusals[0].index == 0
    assert "com/acme/orders/Ghost#" in refusals[0].reason


def test_a_member_is_matched_on_its_descriptor_however_the_claim_spells_it(tmp_path: Path):
    """D00 §5a: a symbol is module coordinates then a descriptor, and only the
    descriptor is ever compared. A claim writing the full symbol and a claim
    writing the bare descriptor name the same type, so both are accepted —
    refusing one would make validation a test of notation."""
    overlay = _overlay(
        _component(members=["com/acme/orders/Ingest#", SYMBOLS[1]]),
    )
    accepted, refusals = validate_overlay(overlay, _Workspace(), tmp_path)
    assert refusals == ()
    assert len(accepted) == 1


def test_a_diagram_node_that_is_not_a_type_is_refused(tmp_path: Path):
    """Every node the scan CAN see must validate (2K design §6). The
    comparison is on simple names, because a mermaid node id is an identifier
    and a descriptor is not one."""
    overlay = _overlay(_diagram("classDiagram\n    class Ingest\n    class Ghost {\n    }\n"))
    _, refusals = validate_overlay(overlay, _Workspace(), tmp_path)
    assert len(refusals) == 1
    assert "Ghost" in refusals[0].reason


def test_a_sequence_participant_is_scanned_the_same_way(tmp_path: Path):
    """The extraction rule covers participant declarations as well as class
    ones: an invented participant is an invented type wearing a different
    keyword."""
    overlay = _overlay(_diagram("sequenceDiagram\n    participant Ghost\n"))
    _, refusals = validate_overlay(overlay, _Workspace(), tmp_path)
    assert len(refusals) == 1
    assert "Ghost" in refusals[0].reason


def test_a_participant_alias_validates_the_identifier_and_not_the_label(tmp_path: Path):
    """`participant Ingest as the ingestion edge` names one type and one
    human-readable label. Validating the label would refuse every correctly
    written alias."""
    overlay = _overlay(_diagram("sequenceDiagram\n    participant Ingest as the ingestion edge\n"))
    _, refusals = validate_overlay(overlay, _Workspace(), tmp_path)
    assert refusals == ()


def test_a_dotted_node_is_validated_on_its_last_segment(tmp_path: Path):
    """A model writing `participant com.acme.orders.Ingest` names a real type
    in the notation its own sources use. Scanning to the first dot would take
    `com` and refuse a VALID diagram as a phantom — the bug this widening
    fixes. Comparison stays on the simple name, so the dotted spelling is
    accepted exactly where the bare one is."""
    overlay = _overlay(_diagram("sequenceDiagram\n    participant com.acme.orders.Ingest\n"))
    accepted, refusals = validate_overlay(overlay, _Workspace(), tmp_path)
    assert refusals == ()
    assert len(accepted) == 1


def test_a_dotted_node_whose_last_segment_is_invented_is_still_refused(tmp_path: Path):
    """The other half: widening the identifier must not turn the check off.
    `com.acme.orders.Ghost` is a phantom however many packages precede it."""
    overlay = _overlay(_diagram("classDiagram\n    class com.acme.orders.Ghost\n"))
    _, refusals = validate_overlay(overlay, _Workspace(), tmp_path)
    assert len(refusals) == 1
    assert "Ghost" in refusals[0].reason


def test_a_backtick_quoted_dollar_node_validates_against_the_real_symbol(tmp_path: Path):
    """spec §5a: the diagram builder backtick-quotes an identifier the mermaid
    grammar refuses bare — a JVM `$` name, most often. The scan strips the
    quoting before comparing, so a machine-emitted `` class `Outer$Inner` ``
    validates against the real symbol the same way an unquoted name does."""
    overlay = _overlay(_diagram("classDiagram\n    class `Outer$Inner` {\n    }\n"))
    workspace = _Workspace(symbols=["s maven com.acme/orders 1.0.0 com/acme/orders/Outer$Inner#"])
    accepted, refusals = validate_overlay(overlay, workspace, tmp_path)
    assert refusals == ()
    assert len(accepted) == 1


def test_a_backtick_quoted_dollar_node_that_is_not_a_type_is_still_refused(tmp_path: Path):
    """The other half of the backtick-stripping widening: quoting must not
    become a way to smuggle a phantom past the scan — a quoted name that
    names no real symbol is refused exactly like an unquoted one."""
    overlay = _overlay(_diagram("classDiagram\n    class `Ghost$Inner` {\n    }\n"))
    _, refusals = validate_overlay(overlay, _Workspace(), tmp_path)
    assert len(refusals) == 1
    assert "Ghost$Inner" in refusals[0].reason


def test_a_participant_alias_is_accepted_by_either_spelling(tmp_path: Path):
    """`participant J as Real` names two spellings and the scan cannot tell
    which one is the real type: an LLM copying a machine-quoted name into the
    alias slot (`participant J as Real$Name`) must not be refused for it, so
    the conservative reading accepts a citation of EITHER side — the
    short id or the label."""
    workspace = _Workspace(symbols=["s maven com.acme/orders 1.0.0 com/acme/orders/Real#"])
    left = _overlay(_diagram("sequenceDiagram\n    participant J as Real\n"))
    accepted, refusals = validate_overlay(left, workspace, tmp_path)
    assert refusals == ()
    assert len(accepted) == 1


def test_a_participant_alias_with_neither_spelling_grounded_is_still_refused(tmp_path: Path):
    """The either-side widening is not a blanket pass: when NEITHER the
    identifier nor the alias names a real type, the phantom is still
    refused."""
    overlay = _overlay(_diagram("sequenceDiagram\n    participant J as Ghost\n"))
    _, refusals = validate_overlay(overlay, _Workspace(), tmp_path)
    assert len(refusals) == 1
    assert "Ghost" in refusals[0].reason or "J" in refusals[0].reason


def test_a_flowchart_style_assignment_is_not_read_as_a_type_declaration(tmp_path: Path):
    """`class A,B someStyle` applies a CSS class to nodes in a flowchart — it
    shares a keyword with `classDiagram` and names no type at all. Reading it
    as a declaration would refuse a valid flowchart over the styling line;
    the rule is to skip any `class` line carrying a comma, which means the
    nodes on it go unchecked rather than misread."""
    overlay = _overlay(_diagram("flowchart LR\n    Ingest --> Relay\n    class Ingest,Relay hot\n"))
    accepted, refusals = validate_overlay(overlay, _Workspace(), tmp_path)
    assert refusals == ()
    assert len(accepted) == 1


def test_a_node_the_scan_cannot_see_is_not_validated_and_not_refused(tmp_path: Path):
    """**The honest limit, pinned.** The scan reads declaration lines and
    nothing else, so a node introduced only by an edge passes unchecked. That
    is the deliberate side: a scan that guessed at mermaid's whole grammar
    would refuse TRUE claims when it guessed wrong, and a validator that
    rejects correct work teaches its user to stop running it. This test exists
    so the limit is a decision on record rather than a surprise."""
    overlay = _overlay(_diagram("classDiagram\n    class Ingest\n    Ingest --> Ghost\n"))
    accepted, refusals = validate_overlay(overlay, _Workspace(), tmp_path)
    assert refusals == ()
    assert len(accepted) == 1


def test_a_cited_file_that_does_not_exist_is_refused(tmp_path: Path):
    """`cites` is a claim's evidence trail, not decoration (2K design §5's
    "cite what you read"). A citation naming nothing is a trail that cannot be
    followed."""
    (tmp_path / "real.java").write_text("", encoding="utf-8")
    overlay = _overlay(_section(["real.java", "invented.java"]))
    _, refusals = validate_overlay(overlay, _Workspace(), tmp_path)
    assert len(refusals) == 1
    assert "invented.java" in refusals[0].reason


def test_a_citation_that_escapes_the_module_root_is_refused(tmp_path: Path):
    """Containment is checked AFTER resolution, so `..` cannot walk a citation
    out of the module and into whatever else is on the disk — the same rule
    the enrichment jail keeps (2K design §4)."""
    outside = tmp_path / "outside.java"
    outside.write_text("", encoding="utf-8")
    module_root = tmp_path / "module"
    module_root.mkdir()
    overlay = _overlay(_section(["../outside.java"]))
    _, refusals = validate_overlay(overlay, _Workspace(), module_root)
    assert len(refusals) == 1
    assert "outside.java" in refusals[0].reason


def test_a_citation_naming_a_directory_is_refused(tmp_path: Path):
    """A directory is not something anyone read. The check is `is_file`, not
    `exists`, so a citation of the source root does not pass as evidence."""
    (tmp_path / "src").mkdir()
    overlay = _overlay(_section(["src"]))
    _, refusals = validate_overlay(overlay, _Workspace(), tmp_path)
    assert len(refusals) == 1


def test_a_verdict_answering_a_question_nobody_asked_is_refused(tmp_path: Path):
    """The verification seat answers the ledger's own rows (2K design §7). A
    verdict about a question that is not open is an assessment of nothing,
    and it would render beside no line at all."""
    question = {
        "protocol": "a-protocol",
        "method": None,
        "path": "another-queue",
        "kind": "a-question",
    }
    overlay = _overlay(_verdict(question=question))
    _, refusals = validate_overlay(overlay, _Workspace(), tmp_path)
    assert len(refusals) == 1
    assert "another-queue" in refusals[0].reason


def test_a_verdict_matching_a_row_on_all_four_columns_is_accepted(tmp_path: Path):
    """Including a NULL method: a messaging destination has no verb, and the
    match has to compare absence to absence rather than coercing one side."""
    accepted, refusals = validate_overlay(_overlay(_verdict()), _Workspace(), tmp_path)
    assert refusals == ()
    assert len(accepted) == 1


def test_a_verdict_differing_only_in_question_kind_is_refused(tmp_path: Path):
    """Identity is all four columns. Two kinds of question about one wire are
    two different rows, and a verdict rendered against the wrong one answers
    something nobody asked."""
    question = {"protocol": "a-protocol", "method": None, "path": "a-queue", "kind": "other-kind"}
    _, refusals = validate_overlay(_overlay(_verdict(question=question)), _Workspace(), tmp_path)
    assert len(refusals) == 1


def test_a_userinfo_bearing_question_path_matches_after_the_same_redaction_the_brief_applied(
    tmp_path: Path,
):
    """2K Task 7 ruling 1, "the brief IS the wire": `application/enrich/
    brief.py`'s `_open_question_lines` redacts an `open_questions.path`
    before the model ever reads it (userinfo stripped, here — the built-in
    rule, live with no repo `redact:` additions needed), so a verdict
    answering that question can only ever echo the REDACTED spelling back.
    `validate_overlay` has to redact the WORKSPACE'S OWN (raw) row the same
    way before comparing, or a model that did exactly what the brief taught
    it — copy the row it was handed, verbatim — gets refused for a mismatch
    neither side actually made. Reverting `validate.py`'s own `_row_identity`
    (dropping its `redactor.redact_text(str(path))` call) breaks this test:
    the claim's redacted path would then compare against the workspace's raw
    one and never match."""
    redactor = Redactor.from_rules()
    raw_path = "https://user:pass@queue.example.com/orders"
    redacted_path = redactor.redact_text(raw_path)
    assert redacted_path != raw_path  # sanity: this redactor is not a no-op here

    row = {
        "protocol": "a-protocol",
        "method": None,
        "path": raw_path,
        "question": "a-question",
        "candidates": "[]",
        "evidence": "compiler",
    }
    claim = _verdict(
        question={
            "protocol": "a-protocol",
            "method": None,
            "path": redacted_path,
            "kind": "a-question",
        }
    )

    accepted, refusals = validate_overlay(
        _overlay(claim), _Workspace(open_questions=[row]), tmp_path, redactor
    )

    assert refusals == ()
    assert len(accepted) == 1


def _unanswered(**overrides: object) -> dict[str, object]:
    claim = _verdict(
        assessment="unanswered",
        searched="read every listener in the module; none names a payload type",
        **overrides,
    )
    del claim["because"]
    return claim


def test_an_unanswered_verdict_needs_no_grounding_for_its_answer(tmp_path: Path):
    """ "`unanswered` beats a guess" (2K design §5/§7) only if the honest
    answer survives validation. Nothing is demanded of the assessment itself —
    the model looked and could not ground one, and refusing it would delete the
    one outcome the instructions ask for."""
    accepted, refusals = validate_overlay(_overlay(_unanswered()), _Workspace(), tmp_path)
    assert refusals == ()
    assert len(accepted) == 1


def test_an_unanswered_verdict_still_has_to_answer_a_real_question(tmp_path: Path):
    """**`unanswered` exempts the ANSWER, not the REFERENT** (Task 3 review,
    ruled). The claim still names a question, still renders beside it, and
    still counts as a claim in the file — so a verdict against a row nobody
    raised is a phantom whichever way it is answered. Exempting the referent
    too would leave the one channel by which an invented open question could
    reach the document."""
    invented = {"protocol": "a-protocol", "method": None, "path": "gone", "kind": "a-question"}
    accepted, refusals = validate_overlay(
        _overlay(_unanswered(question=invented)), _Workspace(), tmp_path
    )
    assert accepted == ()
    assert len(refusals) == 1
    assert "gone" in refusals[0].reason


def test_refusals_carry_the_position_of_the_claim_in_the_file(tmp_path: Path):
    """The overlay is written wholesale and read as a list, so a position is
    what locates the offending object in the file a person would go and open.
    Accepted claims keep the file's own order, because that order is part of
    what the document renders deterministically (NFR-1)."""
    overlay = _overlay(
        _component(),
        _component(name="Phantom", members=["com/acme/orders/Ghost#"]),
        _component(name="Relay", members=["com/acme/orders/Relay#"]),
    )
    accepted, refusals = validate_overlay(overlay, _Workspace(), tmp_path)
    assert [refusal.index for refusal in refusals] == [1]
    assert [claim.name for claim in accepted] == ["Ingestion edge", "Relay"]  # type: ignore[union-attr]


def test_one_refusal_per_claim_however_many_ways_it_is_wrong(tmp_path: Path):
    """A claim is checked until its first failure. Five reasons for one
    invented component is five ways of saying the same thing, and a report
    that repeats itself is one a reader stops reading."""
    overlay = _overlay(_component(members=["com/acme/orders/Ghost#", "com/acme/orders/Wraith#"]))
    _, refusals = validate_overlay(overlay, _Workspace(), tmp_path)
    assert len(refusals) == 1


def test_a_claim_valid_at_ingest_goes_stale_when_its_referents_vanish(tmp_path: Path):
    """Staleness IS "would not be accepted today" (2K design §6), which is why
    `stale_claims` re-runs the ingest checks rather than owning a second copy
    of them: two implementations of one rule disagree eventually, and the
    disagreement is silent in exactly the direction that matters.

    The mechanism here is the workspace, not the claim: the same overlay is
    validated against a full workspace (accepted) and then against a REDUCED
    one standing for a re-analyze in which the type was deleted."""
    overlay = _overlay(_component(name="Relay", members=["com/acme/orders/Relay#"]))
    accepted, refusals = validate_overlay(overlay, _Workspace(), tmp_path)
    assert (len(accepted), refusals) == (1, ())

    reduced = _Workspace(symbols=[SYMBOLS[0]])
    stale = stale_claims(overlay, reduced, tmp_path)
    assert [refusal.index for refusal in stale] == [0]
    assert "com/acme/orders/Relay#" in stale[0].reason


def test_nothing_is_stale_while_every_referent_still_exists(tmp_path: Path):
    """The other half of the pin: an unchanged workspace makes no claim stale,
    so the count line render prints is zero and the notice never appears."""
    overlay = _overlay(_component(), _verdict())
    assert stale_claims(overlay, _Workspace(), tmp_path) == ()
