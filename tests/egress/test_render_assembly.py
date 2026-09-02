"""Add-only assembly (2K design §6).

The overlay's whole promise is that model output lands BESIDE machine output
and never inside it. These tests are that promise, stated four ways: the
machine half is byte-untouched, the claims land at their anchors, the order is
fixed by position rather than by content, and a claim whose referents are gone
is counted out loud instead of quietly dropped.
"""

import json

# The same machine document the rest of the render suite pins, so "the machine
# half is untouched" is checked against the very bytes those tests assert on.
from test_render import MODULE, REPORT

from sextant.application.enrich.validate import stale_claims, validate_overlay
from sextant.domain.enrichment import ENRICHMENT_FILE, EnrichmentOverlay, load_overlay
from sextant.domain.redaction import REDACTED, RedactionRules, Redactor
from sextant.egress.render.document import (
    EnrichmentSection,
    MachineSection,
    StaleNoticeSection,
    assemble_module_document,
    markdown_document,
    render_module_document,
)

PROVENANCE = {
    "model": "a-model",
    "agent": "an-agent",
    "instructions_hash": "sha256:aaa",
    "redaction_set_hash": "sha256:bbb",
    "run_at": "2026-09-02T00:00:00Z",
    "workspace_fingerprint": "sha256:ccc",
}

OPEN_QUESTIONS = [
    {
        "protocol": "sqs",
        "method": None,
        "path": "order-intake",
        "question": "payload_binding",
        "candidates": json.dumps(
            [{"payload_type": "com/acme/A#", "hops": "1", "seen_in": "R#r().", "why": "parseFrom"}]
        ),
        "evidence": "payload parsed beyond the one-hop horizon",
    },
    {
        "protocol": "sqs",
        "method": None,
        "path": "order-audit",
        "question": "payload_binding",
        "candidates": json.dumps(
            [{"payload_type": "com/acme/B#", "hops": "2", "seen_in": "S#s().", "why": "readValue"}]
        ),
        "evidence": "payload parsed beyond the one-hop horizon",
    },
]


def _claim(kind: str, anchor: str, **fields: object) -> dict[str, object]:
    return {"kind": kind, "evidence": "llm", "anchor": anchor, **fields}


def _component(anchor: str = "after-component-overview", name: str = "Ingestion edge"):
    return _claim(
        "component",
        anchor,
        name=name,
        purpose="Turns bytes off the wire into the domain's own types.",
        members=["com/acme/orders/Ingest#"],
    )


def _section(anchor: str = "end-of-document", title: str = "Extending the edge"):
    return _claim(
        "section",
        anchor,
        title=title,
        body="Add a listener.\n\nThen bind its payload.",
        cites=["src/main/java/com/acme/orders/Ingest.java"],
    )


def _diagram(anchor: str = "after-endpoint-table"):
    return _claim(
        "diagram",
        anchor,
        mermaid="classDiagram\n    class Ingest\n",
        elides="showing 1 of 40 classes; error paths elided",
    )


def _verdict(path: str = "order-intake", anchor: str = "beside-open-question"):
    return _claim(
        "verdict",
        anchor,
        question={"protocol": "sqs", "method": None, "path": path, "kind": "payload_binding"},
        assessment="likely `com/acme/A#`",
        because="`R#r()` parses it",
    )


def _overlay(*claims: dict[str, object]) -> EnrichmentOverlay:
    return EnrichmentOverlay.model_validate({"produced_by": PROVENANCE, "claims": list(claims)})


def _rendered(*claims: dict[str, object], stale: frozenset[int] = frozenset()) -> str:
    return render_module_document(
        MODULE,
        REPORT,
        "a3f91c",
        open_questions=OPEN_QUESTIONS,
        overlay=_overlay(*claims) if claims else None,
        stale=stale,
    )


def _machine_only() -> str:
    return render_module_document(MODULE, REPORT, "a3f91c", open_questions=OPEN_QUESTIONS)


def _position(text: str, needle: str) -> int:
    index = text.find(needle)
    assert index >= 0, f"not in the document: {needle}"
    return index


# --- the regression pin ---------------------------------------------------


def test_a_module_with_no_overlay_assembles_to_one_machine_section():
    """ "No overlay file → render behaves exactly as today" (2K design §6),
    made structural rather than hoped for: with nothing to interleave there is
    one section, it holds every line, and the serializer has no decision left
    to make."""
    sections = assemble_module_document(MODULE, REPORT, "a3f91c", open_questions=OPEN_QUESTIONS)
    assert len(sections) == 1
    assert isinstance(sections[0], MachineSection)
    assert markdown_document(sections) == _machine_only()


def test_the_machine_half_is_byte_identical_with_an_overlay_present():
    """Add-only, checked at the bytes. Every machine line the overlay-free
    document holds appears in the enriched one, in the same order, unchanged —
    the claims are additions between them, never edits to them."""
    sections = assemble_module_document(
        MODULE,
        REPORT,
        "a3f91c",
        open_questions=OPEN_QUESTIONS,
        overlay=_overlay(_component(), _diagram(), _verdict(), _section()),
    )
    machine: list[str] = []
    for section in sections:
        if isinstance(section, MachineSection):
            machine += section.lines
    assert "\n".join(machine) + "\n" == _machine_only()


# --- placement ------------------------------------------------------------


def test_a_component_claim_lands_after_the_structure_section():
    """`after-component-overview`: `## Structure` is this document's component
    overview — the one place it draws the module's own types as a whole — so a
    claim about a component reads directly under it."""
    text = _rendered(_component())
    assert _position(text, "## Structure") < _position(text, "**Component: Ingestion edge**")
    assert _position(text, "**Component: Ingestion edge**") < _position(
        text, "## Inbound endpoints"
    )


def test_a_claim_anchored_after_the_endpoint_table_lands_after_both_tables():
    """The endpoint listing is one thing to a reader. A claim about "the
    endpoints" placed between the inbound and outbound halves would read as a
    claim about the inbound ones alone."""
    text = _rendered(_diagram())
    # The machine `## Structure` diagram is the other fence: an LLM diagram is
    # an ADDITION, so the document now carries both rather than one replacing
    # the other.
    assert text.count("```mermaid") == 2
    assert _position(text, "## Outbound endpoints") < text.rindex("```mermaid")
    assert _position(text, "Elides: showing 1 of 40") < _position(text, "## Open questions")


def test_a_verdict_renders_directly_under_the_question_it_answers():
    """The verification seat (2K design §7): the assessment sits beside its
    row, so a reader sees the open question and the model's reading of it
    together. Pinned against the SECOND question too, so the placement is a
    match on identity rather than "wherever the section starts"."""
    text = _rendered(_verdict(path="order-audit"))
    assert _position(text, "`sqs order-audit`") < _position(text, "**LLM assessment**")
    assert _position(text, "`sqs order-intake`") < _position(text, "`sqs order-audit`")
    assert _position(text, "`sqs order-intake`") < _position(text, "**LLM assessment**")


def test_a_non_verdict_claim_anchored_beside_the_questions_lands_after_them_all():
    """Only a verdict names a single row. A section anchored here is a claim
    about the open questions as a group, so it renders after the group rather
    than being attached to whichever one happens to be first."""
    text = _rendered(_section(anchor="beside-open-question", title="Reading the inbox"))
    assert _position(text, "`sqs order-audit`") < _position(text, "**Reading the inbox**")
    assert _position(text, "**Reading the inbox**") < _position(text, "## Known gaps")


def test_an_end_of_document_claim_is_the_last_thing_in_the_file():
    text = _rendered(_section())
    assert _position(text, "## Known gaps") < _position(text, "**Extending the edge**")
    assert text.rstrip().endswith("`src/main/java/com/acme/orders/Ingest.java`")


# --- the mark and the shapes ----------------------------------------------


def test_every_enrichment_block_sits_under_a_provenance_header():
    """ "Add-only, clearly marked" (2K design, the user ruling): a reader must
    see what produced the words before reading them, and the marker names the
    evidence tier and the run."""
    text = _rendered(_component(), _section())
    header = "> **Enrichment — evidence: llm** (model a-model, agent an-agent)"
    assert text.count(header) == 2


def test_each_claim_kind_renders_as_what_it_is():
    """A component with its members, prose with its citations, a mermaid fence
    with its elision statement, an assessment with its grounding. The elision
    line is not optional decoration: a simplified diagram that does not say it
    is simplified lies about the system's size."""
    text = _rendered(_component(), _section(), _diagram(), _verdict())
    assert "Members: `com/acme/orders/Ingest#`" in text
    assert "Cites: `src/main/java/com/acme/orders/Ingest.java`" in text
    assert "```mermaid\nclassDiagram\n    class Ingest\n```" in text
    assert "Elides: showing 1 of 40 classes; error paths elided" in text
    assert (
        "**LLM assessment** for `sqs order-intake` (payload_binding): "
        "likely `com/acme/A#` — because `R#r()` parses it"
    ) in text


def test_an_unanswered_verdict_renders_as_the_honest_answer_it_is():
    """2K design §7: the unanswerable comes back `unanswered` with what was
    searched. It renders as such — never silently dropped, which would turn
    the honesty discipline into an invisible one."""
    unanswered = _claim(
        "verdict",
        "beside-open-question",
        question={
            "protocol": "sqs",
            "method": None,
            "path": "order-intake",
            "kind": "payload_binding",
        },
        assessment="unanswered",
        searched="read every listener; none names a payload type",
    )
    text = _rendered(unanswered)
    assert (
        "**LLM assessment** for `sqs order-intake` (payload_binding): unanswered — "
        "searched: read every listener; none names a payload type"
    ) in text


def test_a_blockquote_header_is_always_separated_from_the_line_after_it():
    """Markdown's lazy continuation: a blockquote followed immediately by a
    list item swallows that item. Without the blank line a claim rendered
    beside the first open question would eat the second one."""
    text = _rendered(_verdict(path="order-intake"))
    lines = text.split("\n")
    for index, line in enumerate(lines[:-1]):
        if line.startswith(">"):
            assert lines[index + 1] == "" or lines[index + 1].startswith(">")


# --- ordering -------------------------------------------------------------


def test_claims_are_ordered_by_document_position_then_by_file_order():
    """NFR-1. Anchors are visited in the order their positions occur in the
    document — not the order the overlay happens to list them — and within one
    position the file's own order decides. Nothing sorts on content, so the
    same overlay always assembles the same way."""
    text = _rendered(
        _section(),
        _component(name="Second"),
        _component(name="First"),
    )
    assert _position(text, "**Component: Second**") < _position(text, "**Component: First**")
    assert _position(text, "**Component: First**") < _position(text, "**Extending the edge**")


def test_two_claims_at_one_anchor_share_a_single_provenance_header():
    """One header per block, not per claim: the run is the same run, and
    repeating its provenance between two adjacent claims is noise that teaches
    a reader to stop seeing the mark."""
    text = _rendered(_component(name="First"), _component(name="Second"))
    assert text.count("> **Enrichment — evidence: llm**") == 1


def test_assembling_the_same_overlay_twice_is_byte_identical():
    """NFR-1's amendment note: brief composition, validation and overlay
    assembly are byte-deterministic; only the agent call itself is excluded."""
    claims = (_component(), _diagram(), _verdict(), _section())
    assert _rendered(*claims) == _rendered(*claims)


# --- staleness ------------------------------------------------------------


def test_a_stale_claim_is_excluded_and_counted_out_loud():
    """2K design §6: "N enrichment claims stale, not shown" — visible, never
    silent. A claim quietly dropped is a document that looks complete and is
    not (NFR-7), and the overlay file still keeps the claim."""
    text = _rendered(_component(), _section(), stale=frozenset({1}))
    assert "**Component: Ingestion edge**" in text
    assert "**Extending the edge**" not in text
    assert "1 enrichment claim stale, not shown" in text


def test_the_stale_count_reads_as_a_count():
    """Two stale claims say "claims". A notice whose grammar is wrong is one a
    reader stops trusting the arithmetic of."""
    text = _rendered(_component(), _section(), stale=frozenset({0, 1}))
    assert "2 enrichment claims stale, not shown" in text


def test_the_stale_notice_is_its_own_typed_section():
    """The HTML emitter styles the notice differently from a claim — it is a
    statement about the overlay, not a statement from it — so it reaches a
    serializer as its own section rather than as prose to be recognised."""
    sections = assemble_module_document(
        MODULE,
        REPORT,
        "a3f91c",
        open_questions=OPEN_QUESTIONS,
        overlay=_overlay(_component()),
        stale=frozenset({0}),
    )
    assert isinstance(sections[-1], StaleNoticeSection)
    assert sections[-1].count == 1
    # Nothing else was placed: the one claim there was is the stale one.
    assert not any(isinstance(section, EnrichmentSection) for section in sections)


def test_no_stale_claims_means_no_notice_at_all():
    """An absence with nothing to say says nothing. The notice is a report of
    exclusion, and reporting zero exclusions is noise."""
    assert "stale, not shown" not in _rendered(_component())


# --- redaction ------------------------------------------------------------


def test_claim_prose_passes_the_redactor_on_its_way_into_the_document():
    """Belt and braces (2K design §1): claim bodies are model output that
    already came back through Sextant's own redacting tools, but `--ingest`
    accepts answers from an agent that ran outside that jail, and render is a
    publishing exit. Applied at ASSEMBLY, so both serializers inherit it."""
    leaky = _section(title="Extending the edge")
    leaky["body"] = "It calls https://user:pass@billing.internal/charge on every order."
    text = _rendered(leaky)
    assert "user:pass@" not in text
    assert "https://billing.internal/charge" in text


def test_a_repo_value_pattern_masks_inside_a_claim_too():
    """The repo's own additions apply here as everywhere else: a redactor is
    one rule set at every exit, not a per-surface set that a claim could slip
    past."""
    leaky = _component()
    leaky["purpose"] = "Reads the key AKIAEXAMPLE0000 at boot."
    text = render_module_document(
        MODULE,
        REPORT,
        "a3f91c",
        redactor=Redactor.from_rules(RedactionRules(value_patterns=(r"AKIA[A-Z0-9]+",))),
        overlay=_overlay(leaky),
    )
    assert "AKIAEXAMPLE0000" not in text
    assert REDACTED in text


def test_the_redaction_reaches_the_section_model_not_only_the_markdown():
    """The HTML emitter reads the claims, never these bytes. Masking in the
    markdown serializer alone would leave the second output unmasked, which is
    exactly the failure a single assembly exists to prevent."""
    leaky = _section()
    leaky["body"] = "See https://user:pass@billing.internal/charge."
    sections = assemble_module_document(MODULE, REPORT, "a3f91c", overlay=_overlay(leaky))
    enrichment = [section for section in sections if isinstance(section, EnrichmentSection)]
    assert "user:pass@" not in enrichment[0].claims[0].body  # type: ignore[union-attr]


# --- the golden stale variant, whole path ---------------------------------


class _Workspace:
    """The two queries validation reads. The stale test needs a workspace it
    can REDUCE, which no analysed fixture offers: the golden overlay shipped
    in `fixtures/` is grounded against the live workspace by design, and
    making one of its referents vanish would mean deleting fixture code that
    every other pin depends on. So the mechanism is the workspace, not the
    file — the same overlay is validated against a full symbol set (accepted)
    and then against a reduced one standing for a re-analyze in which the type
    was deleted."""

    def __init__(self, symbols: list[str]) -> None:
        self._symbols = symbols

    def query(self, name: str, **params: object) -> list[dict[str, object]]:
        if name == "declared_symbols":
            return [{"symbol": symbol} for symbol in self._symbols]
        if name == "open_questions":
            return []
        raise AssertionError(f"unexpected query: {name}")


def test_a_golden_overlay_file_travels_from_disk_to_the_stale_count_line(tmp_path):
    """The whole path in one test: a written overlay file is loaded and
    schema-validated, its claims are grounded against the workspace of the day
    it was written, and a later render against a workspace missing one of
    those referents excludes that claim and says so on the page (2K design
    §6). Everything between the file and the line is under test — nothing here
    hands the assembler a pre-decided answer."""
    written = {
        "produced_by": PROVENANCE,
        "claims": [_component(name="Kept"), _component(name="Doomed")],
    }
    written["claims"][1]["members"] = ["com/acme/orders/Doomed#"]
    (tmp_path / ENRICHMENT_FILE).write_text(json.dumps(written, indent=2), encoding="utf-8")

    overlay = load_overlay(tmp_path)
    assert overlay is not None

    at_ingest = _Workspace(["com/acme/orders/Ingest#", "com/acme/orders/Doomed#"])
    accepted, refusals = validate_overlay(overlay, at_ingest, tmp_path)
    assert (len(accepted), refusals) == (2, ())

    today = _Workspace(["com/acme/orders/Ingest#"])
    stale = stale_claims(overlay, today, tmp_path)
    assert [refusal.index for refusal in stale] == [1]

    text = render_module_document(
        MODULE,
        REPORT,
        "a3f91c",
        overlay=overlay,
        stale=frozenset(refusal.index for refusal in stale),
    )
    assert "**Component: Kept**" in text
    assert "**Component: Doomed**" not in text
    assert "1 enrichment claim stale, not shown" in text
