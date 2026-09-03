"""Add-only assembly (2K design §6).

The overlay's whole promise is that model output lands BESIDE machine output
and never inside it. These tests are that promise, stated four ways: the
machine half is byte-untouched, the claims land at their anchors, the order is
fixed by position rather than by content, and a claim whose referents are gone
is counted out loud instead of quietly dropped.
"""

import json
from pathlib import Path

import pytest

# The same machine document the rest of the render suite pins, so "the machine
# half is untouched" is checked against the very bytes those tests assert on.
from test_render import MODULE, REPORT

from sextant.application.enrich.validate import stale_claims, validate_overlay
from sextant.application.ports.detector import ModuleModel
from sextant.application.resolve.endpoints import SkippedCatalog
from sextant.application.resolve.pipeline import ResolveReport
from sextant.domain.enrichment import ENRICHMENT_FILE, EnrichmentOverlay, load_overlay
from sextant.domain.redaction import REDACTED, RedactionRules, Redactor
from sextant.egress.render.document import (
    ClaimRedactionError,
    DetailEntry,
    EnrichmentSection,
    MachineDiagram,
    MachineSection,
    MachineTable,
    StaleNoticeSection,
    _Anchors,
    _code,
    _interleave,
    _runs,
    _runs_to_markdown,
    _text,
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


# --- runs: the text/code split, and exactly how far its round-trip goes ---
# Fix round 1, IMPORTANT 1: `_runs` claimed to be lossless for ANY input. It
# was not — `if part` dropped an EMPTY *code* run (an odd-index part) right
# alongside a genuinely droppable empty *text* run, so a double backtick with
# nothing between it (an empty code span, or the boundary two adjacent spans
# share) silently vanished. Reachable through any repo-authored evidence text
# this renderer passes through `_runs` unvalidated: an unresolved-config
# reason, a `config_join` site, a candidate's `why`/`seen_in`.


def test_an_empty_code_span_round_trips_instead_of_vanishing():
    """The reviewer's own break: 'a``b' used to reconstruct as 'ab' — the
    empty code run between the two backtick pairs was dropped along with
    every genuinely-empty text run, losing two backticks outright rather than
    merely misplacing them."""
    assert _runs_to_markdown(_runs("a``b")) == "a``b"
    assert _runs("a``b") == (("text", "a"), ("code", ""), ("text", "b"))


def test_a_bare_empty_code_span_round_trips():
    assert _runs_to_markdown(_runs("``")) == "``"
    assert _runs("``") == (("code", ""),)


def test_two_empty_code_spans_round_trip():
    assert _runs_to_markdown(_runs("x``y``z")) == "x``y``z"


def test_an_odd_backtick_count_now_round_trips_too():
    """Fix round 2: `_runs` used to claim round-tripping only for an EVEN
    backtick count, and an unbalanced (odd) count reconstructed with a
    spurious extra closing backtick (`_runs_to_markdown(_runs("a`b"))` used
    to produce `` a`b` ``). `_runs` is now TOTAL — every input round-trips,
    balanced or not — by merging the trailing unmatched split back into one
    text part with its backtick put back in literally, rather than reading
    it as a code span this renderer never opened."""
    assert _runs_to_markdown(_runs("a`b")) == "a`b"
    assert _runs("a`b") == (("text", "a`b"),)


def test_several_stray_backticks_still_round_trip():
    """Beyond the single-stray case: a genuine balanced pair ahead of a
    trailing unmatched backtick still splits into its own code run, and only
    the LAST, unmatched cut is the one merged back."""
    assert _runs_to_markdown(_runs("a`b`c`d")) == "a`b`c`d"
    assert _runs("a`b`c`d") == (("text", "a"), ("code", "b"), ("text", "c`d"))
    assert _runs_to_markdown(_runs("`")) == "`"


# --- the regression pin ---------------------------------------------------

GOLDEN = Path(__file__).parent / "golden" / "architecture-minimal.md"

# A small synthetic module, deliberately NOT the live fixture: the golden below
# is a byte pin, and pinning bytes derived from a compiled fixture would make
# every fixture edit a golden edit. Small, but it exercises every region the
# assembler cuts at — a structure diagram, both endpoint tables, an open
# question, the gap lists, and a skipped catalog.
GOLDEN_MODULE = ModuleModel(
    module_id="com.example:golden",
    coordinates="com.example/golden",
    version="1.0.0",
    root=Path("golden"),
    kind="service",
    languages=frozenset({"java"}),
    source_roots=(),
    output_dirs=(),
    libraries_not_resolved=("com.example:absent: no archive resolved the coordinate",),
)
GOLDEN_REPORT = ResolveReport(
    facts_loaded=7,
    endpoints=[
        {
            "protocol": "http",
            "direction": "inbound",
            "method": "GET",
            "path": "/v1/orders",
            "handler": "s maven c 1 com/example/golden/Api#list().",
            "resolution": "resolved",
            "consumes": None,
            "produces": '["application/json"]',
            "format": "json",
            "format_resolution": "resolved",
        },
        {
            "protocol": "http",
            "direction": "outbound",
            "method": "POST",
            "path": "/billing/invoices",
            "peer": "https://billing.internal",
            "caller": "s maven c 1 com/example/golden/BillingClient#charge().",
            "resolution": "resolved",
            "format": None,
        },
    ],
    coverage={"documents": 2, "partial_documents": 0},
    shapes=[{"shape_id": "com/example/golden/OrderView#", "content_hash": "md5:0", "open": False}],
    unexpanded_types=("com/example/golden/Opaque#",),
    skipped_catalogs=[SkippedCatalog("a-catalog", ("a-capability",))],
)
GOLDEN_SHAPE_FIELDS = [
    {
        "shape_id": "com/example/golden/OrderView#",
        "ordinal": 0,
        "wire_name": "id",
        "wire_type": "string",
        "wire_format": None,
        "field_number": None,
        "required": True,
        "nullable": False,
        "item": None,
    }
]


def _golden_document() -> str:
    return render_module_document(
        GOLDEN_MODULE,
        GOLDEN_REPORT,
        "0d17e2",
        ("com/example/golden/Newer.class: metadata unreadable",),
        shape_fields=GOLDEN_SHAPE_FIELDS,
        open_questions=OPEN_QUESTIONS,
    )


def test_a_module_with_no_overlay_renders_the_checked_in_golden_document():
    """**The regression pin.** "No overlay file → render behaves exactly as
    today" (2K design §6) is a claim about BYTES, and the only thing that can
    falsify it is bytes written down before the change and compared after.
    Both sides of a same-run comparison move together; this file does not.

    It covers every region the assembler cuts at, so a stray blank line, a
    reordered section or a diagram that came back through `MachineDiagram`
    differently all fail here rather than in a reader's document. The file's
    own bytes were taken from the renderer as it stood BEFORE 2K Task 3
    (verified against commit `f019e44`'s `document.py` over this same input),
    so it guards the change that introduced it rather than recording it.

    Regenerating is deliberate, never automatic — a golden that a test rewrites
    pins nothing. When a machine-side change is intended (a new `_GAPS`
    sentence, a column added), inspect the diff and rewrite the file with:

        GOLDEN.write_text(_golden_document(), encoding="utf-8")
    """
    assert _golden_document() == GOLDEN.read_text(encoding="utf-8")


def test_a_module_with_no_overlay_assembles_to_machine_sections_alone():
    """The structural half of the pin above, which the bytes cannot state: with
    nothing to interleave, NO enrichment section exists — the serializer has no
    claim to place and no notice to print. The document is not one section any
    more, because a machine diagram is lifted out as its own typed section for
    the HTML emitter's sake, and that is exactly what the golden proves costs
    no bytes."""
    sections = assemble_module_document(MODULE, REPORT, "a3f91c", open_questions=OPEN_QUESTIONS)
    assert not any(
        isinstance(section, EnrichmentSection | StaleNoticeSection) for section in sections
    )
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
    machine = tuple(
        section
        for section in sections
        if not isinstance(section, EnrichmentSection | StaleNoticeSection)
    )
    assert markdown_document(machine) == _machine_only()


# --- the machine diagram, as data -----------------------------------------


def test_the_machine_structure_diagram_reaches_a_serializer_as_source():
    """2K design §6b: the HTML emitter wraps EVERY diagram in a pan-zoom
    container — the machine one and an overlay's alike. It can only do that
    without scanning markdown if this renderer, which built the fence itself,
    hands the source over as data."""
    sections = assemble_module_document(MODULE, REPORT, "a3f91c")
    diagrams = [section for section in sections if isinstance(section, MachineDiagram)]
    assert len(diagrams) == 1
    assert diagrams[0].mermaid.startswith("classDiagram")
    assert "```" not in diagrams[0].mermaid
    # And the fence appears in the rendered document exactly once — as the
    # `MachineDiagram` above, never a second time duplicated into some other
    # section's own text. (Assembly builds no `MachineSection` at all any
    # more — see `test_a_module_with_no_overlay_assembles_to_machine_sections_alone`
    # — so a loop over `sections` checking that type would now be vacuous.)
    assert markdown_document(sections).count("```mermaid") == 1


def test_a_module_with_no_shapes_has_no_diagram_section_at_all():
    """ "None derived." is prose, not an empty diagram: a serializer handed an
    empty `MachineDiagram` would render an empty pan-zoom container where the
    document says there is nothing to draw."""
    report = ResolveReport(facts_loaded=0, endpoints=[], coverage={"documents": 0})
    sections = assemble_module_document(MODULE, report, "a3f91c")
    assert not any(isinstance(section, MachineDiagram) for section in sections)
    assert "None derived." in markdown_document(sections)


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


def test_a_verdict_on_a_question_whose_path_redaction_changes_still_lands_beside_it():
    """2K final review, F3 — the drift the reviewer proved, pinned on both
    sides at once. The brief hands the model a `redact_text`-ed row, so a
    verdict can only ever name the STRIPPED spelling; validation canonicalized
    the workspace row the same way and accepted it, but assembly keyed its
    placement on the RAW `path`, so the two never met and the verdict fell
    through to the after-the-last-question fallback — validated, rendered, and
    nowhere near the question it answers. Both sides now key on the shared
    `domain.enrichment.open_question_identity`.

    The credentialled question is FIRST of two, so "beside its own question"
    and "at the fallback" are different positions in the file: the assertion
    would still pass at the fallback if it were last."""
    raw_path = "tcp://svc:hunter2@broker:61616/orders"
    questions = [
        {
            "protocol": "jms",
            "method": None,
            "path": raw_path,
            "question": "payload_binding",
            "candidates": json.dumps(
                [
                    {
                        "payload_type": "com/acme/A#",
                        "hops": "1",
                        "seen_in": "R#r().",
                        "why": "parseFrom",
                    }
                ]
            ),
            "evidence": "payload parsed beyond the one-hop horizon",
        },
        OPEN_QUESTIONS[1],
    ]
    verdict = _claim(
        "verdict",
        "beside-open-question",
        question={
            "protocol": "jms",
            "method": None,
            # The spelling the brief showed the model — never `raw_path`.
            "path": "tcp://broker:61616/orders",
            "kind": "payload_binding",
        },
        assessment="likely `com/acme/A#`",
        because="`R#r()` parses it",
    )
    overlay = _overlay(verdict)

    class _QuestionWorkspace:
        """The workspace as it really is: the row keeps the RAW path (D04's
        "the workspace stays verbatim"), which is the whole reason the two
        sides have to canonicalize rather than compare what they hold."""

        def query(self, name: str, **params: object) -> list[dict[str, object]]:
            if name == "declared_symbols":
                return []
            if name == "open_questions":
                return questions
            raise AssertionError(f"unexpected query: {name}")

    accepted, refusals = validate_overlay(overlay, _QuestionWorkspace(), Path("/nonexistent"))
    assert (len(accepted), refusals) == (1, ())

    text = render_module_document(
        MODULE, REPORT, "a3f91c", open_questions=questions, overlay=overlay
    )
    assert "hunter2" not in text
    assert _position(text, "`jms tcp://broker:61616/orders`") < _position(
        text, "**LLM assessment**"
    )
    assert _position(text, "**LLM assessment**") < _position(text, "`sqs order-audit`")


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


# --- a redaction rule wide enough to break a claim ------------------------


def test_a_redaction_rule_that_breaks_a_claims_schema_is_refused_by_name():
    """A repository can widen redaction into any value pattern it likes, and
    one wide enough to eat a required field — or the evidence marker itself —
    leaves a claim its own schema refuses. That is the repository's input
    written wrong (D04 §2a), so it comes back as `ClaimRedactionError` naming
    the claim and what happened, never as a pydantic traceback out of the
    middle of a renderer."""
    pathological = Redactor.from_rules(RedactionRules(value_patterns=("llm",)))
    with pytest.raises(ClaimRedactionError) as refused:
        render_module_document(
            MODULE, REPORT, "a3f91c", redactor=pathological, overlay=_overlay(_component())
        )
    assert "claim 0" in str(refused.value)
    assert "component" in str(refused.value)


def test_an_ordinary_rule_that_only_rewrites_prose_is_not_an_error():
    """The other side, so the check above is a real boundary and not a
    redactor that refuses whatever it touches: masking inside a claim's prose
    is the ordinary case and must go through silently."""
    ordinary = Redactor.from_rules(RedactionRules(value_patterns=(r"AKIA[A-Z0-9]+",)))
    leaky = _component()
    leaky["purpose"] = "Reads AKIAEXAMPLE0000 at boot."
    text = render_module_document(
        MODULE, REPORT, "a3f91c", redactor=ordinary, overlay=_overlay(leaky)
    )
    assert REDACTED in text


# --- the serializer's own edges -------------------------------------------


def test_the_serializer_survives_a_machine_section_carrying_no_lines():
    """Assembly never builds one, but the emitter looks AHEAD at the next
    section to decide whether to add a separating blank line, and looking at
    `lines[0]` of a section that has none is a crash waiting for the day a
    producer yields one. Guarded, and pinned here rather than trusted."""
    overlay = _overlay(_component())
    provenance = overlay.produced_by
    sections = (
        MachineSection(("# a module",)),
        EnrichmentSection(provenance, tuple(overlay.claims)),
        MachineSection(()),
    )
    assert markdown_document(sections).startswith("# a module\n\n> **Enrichment")


def test_an_enrichment_block_is_the_last_thing_in_the_document():
    """The other lookahead edge: nothing follows, so nothing is looked at. A
    document ending in a claim is the ordinary `end-of-document` anchor."""
    text = _rendered(_section())
    assert text.endswith("Cites: `src/main/java/com/acme/orders/Ingest.java`\n")


# --- fix round 1, MINOR 3: a claim anchored out of range is a loud failure -


def test_a_claim_anchored_outside_the_document_range_is_refused_not_dropped():
    """Unreachable through the public `assemble_module_document` path — every
    `_Anchors` field it builds is `len(sections)` at some point during
    assembly — so this drives `_interleave` directly with a broken one, the
    same way a future anchor kind might compute a bad index. This file's own
    discipline (NFR-7, the stale-claim notice) never drops a claim quietly;
    an out-of-range index must fail exactly as loudly."""
    machine = (MachineSection(("# a module",)),)
    broken_anchors = _Anchors(
        structure_end=99, endpoints_end=99, beside_question=(), questions_end=99, document_end=99
    )
    overlay = _overlay(_component())
    with pytest.raises(ValueError, match="outside the document's own"):
        _interleave(machine, broken_anchors, overlay, frozenset(), Redactor.from_rules())


# --- fix round 1, MINOR 7: a DetailEntry never carries both a body and a --
# --- table -------------------------------------------------------------


def test_a_detail_entry_refuses_to_carry_both_a_body_and_a_table():
    """The markdown renderer's `if entry.table is not None` branch would
    otherwise let a table silently win over a body the entry also carried —
    the same "no rendering rule silently wins" refusal
    `ClaimRedactionError`/the html emitter's unrecognised-kind checks already
    take elsewhere in this file."""
    with pytest.raises(ValueError, match="EITHER a body OR a table"):
        DetailEntry(_text("Request"), _text("string"), MachineTable(("Field",), ()))


def test_a_detail_entry_with_neither_a_body_nor_a_table_is_still_allowed():
    """The header entry every `MachineDetail` opens with — a bare title,
    deliberately neither — must not trip the new refusal."""
    DetailEntry(_code("GET /v1/orders"), None, None)
