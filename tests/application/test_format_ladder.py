"""Tests for the format ladder (2G design §5) and the `open_questions`
ledger the conflict half of it writes (§6).

Everything here is built by hand — invented MIME strings, invented serializer
class names, invented marker packages, invented protocols' vocabulary — for
the reason every other engine test in this directory states: a behaviour per
test, isolated and fast, with the shipped catalogs' own live answers pinned
once in `test_pipeline.py` against real bytecode. The invented vocabulary is
also the point: a test reaching for the real framework's spellings would not
prove the ladder reads catalog data rather than knowing them.

**One deliberate wording note.** 2G design §5 calls the strongest rung
"exact" in prose; the value asserted below is `resolved`, because §4 states
that `format_resolution` reuses the EXISTING resolution set and D00 §4's set
is closed at `resolved`/`narrowed`/`partial`/`unresolved` (NFR-5). The tier
these tests pin is the design's "exact": observed, never assumed.
"""

import json
from pathlib import Path

import pytest

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.format import resolve_format
from sextant.application.resolve.open_questions import (
    record_open_questions,
    reset_open_questions,
)
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    CallSiteFact,
    CallTarget,
    DeclaredFieldFact,
    DeclaredShapeFact,
    Document,
    Fact,
)
from sextant.domain.symbols import type_descriptor
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "

# Invented vocabulary. None of it is a real MIME type, class or package —
# every one is a value the catalogs below declare and the ladder looks up.
PARCEL_MIME = "application/x-parcel"
SCROLL_MIME = "application/x-scroll"
UNMAPPED_MIME = "application/x-unknown"
WRITER = "com.acme.serde.ParcelWriter"
READER = "com.acme.serde.ScrollReader"
MEDIA_KEY = "acme.channel.writer"
MARKER_2 = "com.acme.binder2"
MARKER_3 = "acme.binder3"
# The third marker FORM (2O design §7): a classpath coordinate rather than a
# package family. Invented, like every other value here.
COORDINATE = "com.acme:binder-runtime"

# The two payload types the tests bind. `SCHEMA_TYPE` owns a declared_shape
# fact (2G design §3's descriptor-described payload); `DTO_TYPE` is an
# ordinary declared class with no schema of its own.
SCHEMA_TYPE = "com/acme/contracts/Parcel#"
DTO_TYPE = "com/acme/contracts/Note#"

PARCEL_PAYLOAD = json.dumps(
    {"nullable": True, "shape_id": SCHEMA_TYPE, "wire_format": "", "wire_type": "object"},
    sort_keys=True,
    separators=(",", ":"),
)
NOTE_PAYLOAD = json.dumps(
    {"nullable": True, "shape_id": DTO_TYPE, "wire_format": "", "wire_type": "object"},
    sort_keys=True,
    separators=(",", ":"),
)
SCALAR_PAYLOAD = json.dumps(
    {"nullable": True, "wire_format": "", "wire_type": "string"},
    sort_keys=True,
    separators=(",", ":"),
)


def _document(
    document_id: str = "doc_1",
    path: str = "com/acme/contracts/Parcel.java",
    origin: str | None = None,
) -> Document:
    return Document(
        document_id=document_id,
        relative_path=path,
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
        # D00 §2: the artifact outside this module's own output the document
        # was read from, as its coordinate — rung 5's third presence source
        # (2O design §7).
        origin=origin,
    )


def _schema_shape(schema_format: str = "protobuf", evidence: str = "compiler") -> DeclaredShapeFact:
    return DeclaredShapeFact(
        document_id="doc_1",
        symbol=SCHEMA_TYPE,
        schema_name="acme.contracts.Parcel",
        schema_format=schema_format,
        origin="compiled" if evidence == "compiler" else "source",
        evidence=evidence,
        fields=[
            DeclaredFieldFact(
                name="id",
                wire_name="id",
                field_number=1,
                wire_type="string",
                required=True,
                nullable=False,
            )
        ],
    )


def _workspace(
    tmp_path: Path,
    config: list[tuple[str, str, str | None]] | None = None,
    shapes: list[DeclaredShapeFact] | None = None,
    marked: str | None = None,
    called: str | None = None,
    origins: list[str] | None = None,
) -> DuckDbWorkspace:
    """A workspace holding already-resolved configuration, any declared-shape
    facts the test binds, and whichever of rung 5's three presence sources
    (2O design §7) the test supplies: `marked` puts one ANNOTATION from that
    package family in the module, `called` puts one CALL onto a type from it,
    and `origins` records one document per classpath COORDINATE."""
    facts: list[Fact] = list(shapes or [])
    if marked is not None:
        facts.append(
            AnnotationFact(
                document_id="doc_1",
                target=_MODULE + DTO_TYPE + "id.",
                use=AnnotationUse(annotation=type_descriptor(f"{marked}.Named")),
                retention="runtime",
            )
        )
    if called is not None:
        facts.append(
            CallSiteFact(
                document_id="doc_1",
                caller=_MODULE + DTO_TYPE + "write().",
                target=CallTarget(
                    owner=type_descriptor(f"{called}.Writer"), name="write", descriptor="sig_1"
                ),
                invoke_kind="virtual",
                ordinal=0,
            )
        )
    write_fact_file(tmp_path / "facts" / "Parcel.jsonl", _document(), facts)
    for index, origin in enumerate(origins or []):
        write_fact_file(
            tmp_path / "facts" / f"library_{index}.jsonl",
            _document(document_id=f"lib_{index}", path=f"lib/{index}/Type.java", origin=origin),
            [],
        )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    if config:
        workspace.derive(
            "resolved_config_insert",
            rows=[
                {
                    "key": key,
                    "value": value,
                    "source": "invented.yml" if value is not None else None,
                    "environment": environment,
                    "unresolved_reason": None if value is not None else "missing_key",
                }
                for key, environment, value in config
            ],
        )
    return workspace


def _seed(workspace: DuckDbWorkspace, *rows: dict) -> None:
    """Rows the endpoint engines already minted — what the ladder answers.
    Written through the same `call_endpoints` derive every style uses, so the
    rows are indistinguishable from real ones."""
    workspace.derive(
        "call_endpoints",
        rows=[
            {
                "protocol": "kafka",
                "direction": "inbound",
                "method": None,
                "path": None,
                "handler": None,
                "caller": None,
                "peer": None,
                "handler_signature": None,
                "resolution": "resolved",
                "evidence": "compiler",
                "catalog_id": "invented-other",
                "request_shape": None,
                "response_shape": None,
                "consumes": None,
                "produces": None,
                **row,
            }
            for row in rows
        ],
    )


def _catalog(
    format_fixed: dict[str, str] | None = None,
    media_formats: dict[str, str] | None = None,
    json_default_markers: list[str | dict[str, str]] | None = None,
    format_from: dict[str, str] | None = None,
    rules: list[dict] | None = None,
) -> Catalog:
    """A catalog carrying whichever of 2G design §7's four vocabularies the
    test needs. `matches` holds the `media_from_config` block only when a
    serializer table is asked for — the ladder reads that block's own rules
    rather than declaring a second copy of them."""
    matches: dict[str, object] = {}
    if format_from is not None:
        matches["media_from_config"] = {
            "rules": rules
            if rules is not None
            else [
                {
                    "key": MEDIA_KEY,
                    "fills": "produces",
                    "on": {"protocol": "kafka", "direction": "outbound"},
                }
            ],
            "values": {},
            "format_from": format_from,
        }
    return Catalog(
        id="invented-formats",
        style="config_join",
        protocol="kafka",
        direction="inbound",
        requires=(),
        matches=matches,
        source=Path("tests/invented-formats.yml"),
        format_fixed=format_fixed or {},
        media_formats=media_formats or {},
        json_default_markers=json_default_markers or [],
    )


def _run(workspace: DuckDbWorkspace, *catalogs: Catalog) -> list[dict]:
    """One resolve's worth of the two passes that touch the ledger, in the
    pipeline's own order: the reset, then the format pass."""
    reset_open_questions(workspace)
    resolve_format(workspace, list(catalogs))
    return workspace.query("endpoints")


def _formats(rows: list[dict]) -> dict[object, tuple[object, object]]:
    return {row["path"]: (row["format"], row["format_resolution"]) for row in rows}


# --- the rungs, in order --------------------------------------------------


def test_a_protocol_with_a_fixed_format_answers_before_anything_else(tmp_path: Path):
    """Rung 1. A protocol whose wire is constant by definition is settled by
    the catalog that owns the protocol, and no property of the row can move
    it — the media declaration below is deliberately present and deliberately
    ignored.

    Exercised synthetically on an INVENTED pairing (`kafka` is not a
    fixed-format protocol), because the rung's own precedence is what this
    test is about and a synthetic catalog is the only way to put a media
    declaration underneath it that must lose. The rung is no longer without a
    live surface: since 2H the four catalogs owning `graphql` each declare
    `format_fixed: {graphql: json}`, and the live GraphQL rows answering
    `json`/`resolved` are pinned end to end in `tests/e2e/`."""
    workspace = _workspace(tmp_path)
    _seed(workspace, {"path": "a", "produces": json.dumps([SCROLL_MIME])})
    rows = _run(
        workspace,
        _catalog(format_fixed={"kafka": "protobuf"}, media_formats={SCROLL_MIME: "xml"}),
    )
    workspace.close()

    assert _formats(rows)["a"] == ("protobuf", "resolved")


def test_declared_media_beats_payload_hierarchy(tmp_path: Path):
    """Rung 2 over rung 4 — the precedence the whole design turns on. A
    schema-described payload has a JSON encoding too, so the CHANNEL's own
    declaration wins: a protobuf-typed payload under a JSON-meaning media
    type is on the wire as JSON, and reading it as protobuf because of the
    payload's type would be a wrong answer stated confidently."""
    workspace = _workspace(tmp_path, shapes=[_schema_shape()])
    _seed(
        workspace,
        {"path": "a", "produces": json.dumps([SCROLL_MIME]), "request_shape": PARCEL_PAYLOAD},
    )
    rows = _run(workspace, _catalog(media_formats={SCROLL_MIME: "json"}))
    workspace.close()

    assert _formats(rows)["a"] == ("json", "resolved")


def test_a_configured_serializer_states_the_wire_outright(tmp_path: Path):
    """Rung 3. The module's own configuration names the class that writes the
    bytes, so the answer is observed rather than assumed — the rung reaches
    rows no media declaration touched, which is exactly the messaging case
    where no MIME string was ever registered for the serializer at all."""
    workspace = _workspace(
        tmp_path, config=[(MEDIA_KEY, "default", WRITER), (MEDIA_KEY, "prod", WRITER)]
    )
    _seed(workspace, {"path": "a", "direction": "outbound"})
    rows = _run(workspace, _catalog(format_from={WRITER: "protobuf"}))
    workspace.close()

    assert _formats(rows)["a"] == ("protobuf", "resolved")


def test_a_serializer_the_environments_disagree_on_answers_nothing(tmp_path: Path):
    """Rung 3's agreement precondition, the same one the media stamp keeps
    (D02 §2d): `format` is single-valued, so a per-environment split cannot
    be folded into it without inventing an answer neither environment gave.
    The row falls through to the rungs below, and here there are none."""
    workspace = _workspace(
        tmp_path, config=[(MEDIA_KEY, "default", WRITER), (MEDIA_KEY, "prod", READER)]
    )
    _seed(workspace, {"path": "a", "direction": "outbound"})
    rows = _run(workspace, _catalog(format_from={WRITER: "protobuf", READER: "avro"}))
    workspace.close()

    assert _formats(rows)["a"] == (None, "unresolved")


def test_a_serializer_absent_from_the_table_answers_nothing(tmp_path: Path):
    """A class the catalog cannot name is a gap to grow the catalog from, not
    a guess — the same rule `values` keeps for an unmapped MIME type."""
    workspace = _workspace(
        tmp_path, config=[(MEDIA_KEY, "default", READER), (MEDIA_KEY, "prod", READER)]
    )
    _seed(workspace, {"path": "a", "direction": "outbound"})
    rows = _run(workspace, _catalog(format_from={WRITER: "protobuf"}))
    workspace.close()

    assert _formats(rows)["a"] == (None, "unresolved")


def test_a_descriptor_described_payload_is_narrowed_never_resolved(tmp_path: Path):
    """Rung 4. With nothing declared about the channel, the payload's own
    schema is the only evidence there is — and it is evidence about the TYPE,
    not about the bytes: a negotiation this pass cannot see may still put the
    JSON encoding on the wire. `narrowed` is the whole point of the rung; an
    answer at the resolved tier here would make an assumption look observed.
    """
    workspace = _workspace(tmp_path, shapes=[_schema_shape()])
    _seed(workspace, {"path": "a", "request_shape": PARCEL_PAYLOAD})
    rows = _run(workspace, _catalog())
    workspace.close()

    assert _formats(rows)["a"] == ("protobuf", "narrowed")


def test_a_source_declared_schema_also_describes_the_payload(tmp_path: Path):
    """Rung 4 reads the shape's EVIDENCE tier, not its origin: a schema file
    the repository declares (`declared`) describes the payload exactly as a
    schema the compiler embedded (`compiler`) does. Both are schema
    descriptions; neither is a claim about the wire, which is why both land at
    `narrowed`."""
    workspace = _workspace(tmp_path, shapes=[_schema_shape("avro", evidence="declared")])
    _seed(workspace, {"path": "a", "response_shape": PARCEL_PAYLOAD})
    rows = _run(workspace, _catalog())
    workspace.close()

    assert _formats(rows)["a"] == ("avro", "narrowed")


def test_a_schema_language_that_is_not_a_wire_format_answers_nothing_at_rung_4(
    tmp_path: Path,
):
    """`endpoints.format` is closed at D00's six values (NFR-5) and
    `stamp_format.sql` applies whatever this pass hands it without re-checking
    — so a rung that published its input verbatim could put a non-member into
    a closed column, where a reader cannot tell it from an observation.

    A `declared_shape`'s `schema_format` names the schema LANGUAGE, and only
    some schema languages are also encodings: protobuf and Avro define bytes,
    GraphQL states a type system and leaves the transport to say how it is
    written. So the rung is silent here, and the row falls through honestly.

    Rung 5 does NOT pick it up either, even with the default converter's
    family present: the payload is still schema-described, which is exactly
    what that rung's "ordinary declared payload" excludes. `unresolved` is the
    answer, and it is an answer.

    (2H Task 4 review, IMPORTANT 1. This was reachable the moment graphql
    `declared_shape` facts existed; on the live fixture rung 1's
    `format_fixed: {graphql: json}` answers first and masks it — a mask is not
    a rule, which is why the constraint lives in the rung.)
    """
    workspace = _workspace(
        tmp_path, shapes=[_schema_shape("graphql", evidence="declared")], marked=MARKER_2
    )
    _seed(workspace, {"path": "a", "response_shape": PARCEL_PAYLOAD})
    rows = _run(workspace, _catalog(json_default_markers=[MARKER_2]))
    workspace.close()

    assert _formats(rows)["a"] == (None, "unresolved")


@pytest.mark.parametrize("marker", [MARKER_2, MARKER_3])
def test_a_default_converter_on_the_classpath_narrows_an_ordinary_payload(
    tmp_path: Path, marker: str
):
    """Rung 5, for BOTH declared package families. The converter's presence
    is why it is the framework default at all, so the rung asks only whether
    the family appears in the module — not whether this payload uses it. A
    relocation between two package families of one library is therefore two
    catalog rows and zero code, which is what this parametrization pins.

    `narrowed`, never resolved: nothing was declared about this channel, and
    an assumption that looks observed is the one failure the design names."""
    workspace = _workspace(tmp_path, marked=marker)
    _seed(workspace, {"path": "a", "request_shape": NOTE_PAYLOAD})
    rows = _run(workspace, _catalog(json_default_markers=[MARKER_2, MARKER_3]))
    workspace.close()

    assert _formats(rows)["a"] == ("json", "narrowed")


def test_a_marker_family_the_module_only_CALLS_is_presence_evidence_too(tmp_path: Path):
    """Rung 5's second source (2O design §7). The doc has always described
    these markers as package families whose presence ANYWHERE in the module is
    the evidence; the code read annotation fqns alone, so a module that uses
    the converter's API and none of its annotations answered `unresolved` —
    the same jar, a different answer. The call's owner type is an fqn the
    module could not have compiled against unless the family was there, which
    is exactly the proof an annotation is."""
    workspace = _workspace(tmp_path, called=MARKER_2)
    _seed(workspace, {"path": "a", "request_shape": NOTE_PAYLOAD})
    rows = _run(workspace, _catalog(json_default_markers=[MARKER_2, MARKER_3]))
    workspace.close()

    assert _formats(rows)["a"] == ("json", "narrowed")


def test_a_recorded_classpath_coordinate_is_presence_evidence_with_no_fqn_at_all(
    tmp_path: Path,
):
    """Rung 5's third source, and the one CP-6 confirmed against a live app:
    the framework auto-configures its JSON converter from the jar's MERE
    PRESENCE, with no annotation and no API call anywhere in the module. The
    marker is therefore a classpath coordinate rather than a package family —
    that is the evidence the framework itself acts on — and the module below
    names nothing at all from it.

    The recorded trail is the COORDINATE, not a package: `seen_in` is already
    "module" for this rung, and the coordinate is what was actually seen."""
    workspace = _workspace(tmp_path, origins=[COORDINATE])
    _seed(workspace, {"path": "a", "request_shape": NOTE_PAYLOAD})
    rows = _run(workspace, _catalog(json_default_markers=[{"coordinate": COORDINATE}]))
    workspace.close()

    assert _formats(rows)["a"] == ("json", "narrowed")


def test_a_coordinate_marker_no_recorded_coordinate_matches_answers_nothing(tmp_path: Path):
    """The other half: a coordinate nobody recorded is not evidence. Only a
    dependency this run actually read is recorded (D00 §2's `origin`), so a
    jar nobody opted into leaves the row `unresolved` — silence rather than a
    guess, which is the answer the design asks for."""
    workspace = _workspace(tmp_path, origins=["com.acme:something-else"])
    _seed(workspace, {"path": "a", "request_shape": NOTE_PAYLOAD})
    rows = _run(workspace, _catalog(json_default_markers=[{"coordinate": COORDINATE}]))
    workspace.close()

    assert _formats(rows)["a"] == (None, "unresolved")


def test_a_marker_entry_of_neither_form_is_refused_by_file(tmp_path: Path):
    """Rung 5 has two forms and no third. A marker nothing recognizes answers
    nothing, and a rung that answers nothing reads exactly like a converter
    that is genuinely absent — refused at the edge, the same discipline every
    other value in this vocabulary gets."""
    workspace = _workspace(tmp_path)
    _seed(workspace, {"path": "a", "request_shape": NOTE_PAYLOAD})

    with pytest.raises(CatalogError) as raised:
        _run(workspace, _catalog(json_default_markers=[{"artifact": COORDINATE}]))
    workspace.close()

    assert "json_default_markers" in str(raised.value)


def test_an_absent_default_converter_leaves_an_ordinary_payload_unresolved(tmp_path: Path):
    """The other half of rung 5: no marker family present, no default to
    assume. A DTO is not evidence of anything on its own."""
    workspace = _workspace(tmp_path)
    _seed(workspace, {"path": "a", "request_shape": NOTE_PAYLOAD})
    rows = _run(workspace, _catalog(json_default_markers=[MARKER_2, MARKER_3]))
    workspace.close()

    assert _formats(rows)["a"] == (None, "unresolved")


def test_a_row_with_no_payload_at_all_is_left_to_the_last_rung(tmp_path: Path):
    """Rung 5 needs a declared payload TYPE, not merely a converter. A
    channel carrying nothing this pass can see, and one carrying a bare
    scalar, are both cases where the default says nothing about the bytes —
    content negotiation decides a scalar response, and a channel with no
    payload has no encoding to name."""
    workspace = _workspace(tmp_path, marked=MARKER_2)
    _seed(
        workspace,
        {"path": "empty"},
        {"path": "scalar", "response_shape": SCALAR_PAYLOAD},
    )
    rows = _run(workspace, _catalog(json_default_markers=[MARKER_2]))
    workspace.close()

    assert _formats(rows)["empty"] == (None, "unresolved")
    assert _formats(rows)["scalar"] == (None, "unresolved")


def test_nothing_at_all_is_unresolved_and_still_an_answer(tmp_path: Path):
    """Rung 6. Every row leaves this pass stamped: NULL format beside an
    explicit `unresolved` is the answer for a channel nothing described —
    distinguishable from a row the pass never reached, which is what a NULL
    resolution would have meant."""
    workspace = _workspace(tmp_path)
    _seed(workspace, {"path": "a"})
    rows = _run(workspace, _catalog())
    workspace.close()

    assert _formats(rows)["a"] == (None, "unresolved")
    assert rows[0]["format_resolution"] == "unresolved"


def test_an_unmapped_media_type_falls_through_rather_than_guessing(tmp_path: Path):
    """A MIME string the catalogs cannot name contributes no candidate at
    all, so the row keeps descending — here into rung 4, which can answer
    it. A rung that treated "declared but unmapped" as an answer would stop
    the ladder on evidence it could not read."""
    workspace = _workspace(tmp_path, shapes=[_schema_shape()])
    _seed(
        workspace,
        {"path": "a", "consumes": json.dumps([UNMAPPED_MIME]), "request_shape": PARCEL_PAYLOAD},
    )
    rows = _run(workspace, _catalog(media_formats={PARCEL_MIME: "json"}))
    workspace.close()

    assert _formats(rows)["a"] == ("protobuf", "narrowed")


# --- conflicts and the hand-off ------------------------------------------


def test_consumes_and_produces_that_disagree_resolve_to_a_question(tmp_path: Path):
    """`format` is the wire identity, singular. A row consuming one format
    and producing another has two answers and no way to hold both, so it
    records `unresolved` and hands the impasse to 2K rather than picking the
    side that happens to sort first (2G design §5, §6).

    The ledger row carries the wire identity, both candidates with where each
    was seen, and the trail — everything the seat needs without re-deriving
    what this pass already read."""
    workspace = _workspace(tmp_path)
    _seed(
        workspace,
        {
            "path": "a",
            "consumes": json.dumps([PARCEL_MIME]),
            "produces": json.dumps([SCROLL_MIME]),
        },
    )
    rows = _run(workspace, _catalog(media_formats={PARCEL_MIME: "json", SCROLL_MIME: "xml"}))
    questions = workspace.query("open_questions")
    workspace.close()

    assert _formats(rows)["a"] == (None, "unresolved")
    [question] = questions
    assert question["question"] == "format_conflict"
    assert (question["protocol"], question["path"]) == ("kafka", "a")
    assert json.loads(str(question["candidates"])) == [
        {"format": "json", "seen_in": "consumes", "why": PARCEL_MIME},
        {"format": "xml", "seen_in": "produces", "why": SCROLL_MIME},
    ]
    assert "consumes" in str(question["evidence"]) and "produces" in str(question["evidence"])


def test_a_conflicted_row_does_not_fall_through_to_a_weaker_rung(tmp_path: Path):
    """A weaker rung must not break a tie a stronger one could not. The row
    below has a perfectly good rung-4 answer waiting underneath a rung-2
    disagreement; taking it would report a format the declared media
    contradicts, and would hide the disagreement entirely."""
    workspace = _workspace(tmp_path, shapes=[_schema_shape()])
    _seed(
        workspace,
        {
            "path": "a",
            "consumes": json.dumps([PARCEL_MIME]),
            "produces": json.dumps([SCROLL_MIME]),
            "request_shape": PARCEL_PAYLOAD,
        },
    )
    rows = _run(workspace, _catalog(media_formats={PARCEL_MIME: "json", SCROLL_MIME: "xml"}))
    workspace.close()

    assert _formats(rows)["a"] == (None, "unresolved")


def test_two_media_types_meaning_one_format_are_not_a_conflict(tmp_path: Path):
    """Agreement is about the FORMAT, not the string: a row declaring two
    spellings of one wire format has one answer, and asking 2K about it would
    be noise in the one place noise is most expensive."""
    workspace = _workspace(tmp_path)
    _seed(
        workspace,
        {
            "path": "a",
            "consumes": json.dumps([PARCEL_MIME]),
            "produces": json.dumps([SCROLL_MIME]),
        },
    )
    rows = _run(workspace, _catalog(media_formats={PARCEL_MIME: "json", SCROLL_MIME: "json"}))
    questions = workspace.query("open_questions")
    workspace.close()

    assert _formats(rows)["a"] == ("json", "resolved")
    assert questions == []


def test_the_ledger_is_emptied_once_per_resolve(tmp_path: Path):
    """The reset is the pipeline's, not the pass's (2G design §6): two passes
    write these rows, so a resolve that asks fewer questions than the last
    one must not keep the last one's. Running the pair twice leaves exactly
    one row, never two."""
    workspace = _workspace(tmp_path)
    _seed(
        workspace,
        {
            "path": "a",
            "consumes": json.dumps([PARCEL_MIME]),
            "produces": json.dumps([SCROLL_MIME]),
        },
    )
    catalog = _catalog(media_formats={PARCEL_MIME: "json", SCROLL_MIME: "xml"})
    _run(workspace, catalog)
    _run(workspace, catalog)
    questions = workspace.query("open_questions")
    workspace.close()

    assert len(questions) == 1


def test_a_question_kind_outside_the_closed_set_is_refused(tmp_path: Path):
    """2G design §6's question set is closed (NFR-5). The value is bound
    straight into a published artifact, where a typo is indistinguishable
    from a kind of question nobody implemented."""
    workspace = _workspace(tmp_path)
    reset_open_questions(workspace)

    with pytest.raises(ValueError, match="payload_binding, format_conflict"):
        record_open_questions(
            workspace,
            [
                {
                    "protocol": "kafka",
                    "method": None,
                    "path": "a",
                    "question": "format_guess",
                    "candidates": "[]",
                    "evidence": "invented",
                }
            ],
        )
    workspace.close()


# --- catalog validation ---------------------------------------------------


def test_a_catalog_declaring_the_reserved_format_is_refused(tmp_path: Path):
    """2G design §4, §11: `json_schema` is named by the design and
    implemented by nothing (JSON Schema and XSD are out of scope this phase).
    A catalog writing it must fail loudly rather than be silently read as
    `json`, which is the adjacent value it is NOT — the same refusal 2F
    gives `config_model.profiles.from_key_prefix`."""
    workspace = _workspace(tmp_path)
    _seed(workspace, {"path": "a"})

    with pytest.raises(CatalogError, match="RESERVED"):
        resolve_format(workspace, [_catalog(media_formats={PARCEL_MIME: "json_schema"})])
    workspace.close()


def test_a_catalog_declaring_a_format_outside_the_closed_set_is_refused(tmp_path: Path):
    """D00's closed sets are closed (NFR-5). The value is stamped into a
    published column, where a typo is indistinguishable from an
    observation."""
    workspace = _workspace(tmp_path)
    _seed(workspace, {"path": "a"})

    with pytest.raises(CatalogError, match="not one of"):
        resolve_format(workspace, [_catalog(format_from={WRITER: "yaml"})])
    workspace.close()


def test_two_catalogs_contradicting_each_other_on_one_key_are_refused(tmp_path: Path):
    """The design ships one MIME table on several catalogs of a family (each
    owns its own protocol), so a contradiction between two copies is a real,
    reachable editing mistake. Picking either side silently would make the
    answer depend on filename order — the failure NFR-1 exists to prevent."""
    workspace = _workspace(tmp_path)
    _seed(workspace, {"path": "a"})

    with pytest.raises(CatalogError, match="contradicts"):
        resolve_format(
            workspace,
            [
                _catalog(media_formats={PARCEL_MIME: "json"}),
                _catalog(media_formats={PARCEL_MIME: "xml"}),
            ],
        )
    workspace.close()


def test_nothing_is_stamped_when_a_catalog_is_refused(tmp_path: Path):
    """Every catalog is validated before any row is answered — a broken file
    is a broken file, not a half-answered table (the `resolve_config`
    precedent). The good catalog listed first must not stamp its rows before
    the bad one is reached."""
    workspace = _workspace(tmp_path)
    _seed(workspace, {"path": "a", "consumes": json.dumps([PARCEL_MIME])})

    with pytest.raises(CatalogError):
        resolve_format(
            workspace,
            [_catalog(media_formats={PARCEL_MIME: "json"}), _catalog(format_from={WRITER: "yaml"})],
        )
    rows = workspace.query("endpoints")
    workspace.close()

    assert (rows[0]["format"], rows[0]["format_resolution"]) == (None, None)
