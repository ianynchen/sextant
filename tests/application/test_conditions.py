"""`resolve/conditions.py`'s shared reads (spec 2026-09-18 §2, §4) — the index
half Task 6 lands and the body rule's `container` binding reads; Task 7 adds
the condition itself on top of these three.

What is pinned here and why: the two folds are built ONCE per load through
`Workspace.once`, which keys on the builder callable — a builder defined inside
each call would be a fresh key every time, rebuilt per catalog and never found
again, which is exactly the per-catalog decode GUIDELINES §8.7 refuses. The
identity assertion is what catches that shape.
"""

from pathlib import Path

from sextant.application.resolve.conditions import (
    annotation_index,
    enclosing_type_of,
    member_annotations_by_type,
)
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import AnnotationFact, AnnotationUse, Document, SymbolFact
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_UPLOAD = "com/acme/Upload#"
_FILE = "com/acme/Upload#file."
_SETTER = "com/acme/Upload#setName()."
_RESOURCE = "com/acme/R#"
_CREATE = "com/acme/R#create()."
_REST_FORM = "org/jboss/resteasy/reactive/RestForm#"
_POST = "jakarta/ws/rs/POST#"


def test_enclosing_type_of_reads_the_type_off_a_member_symbol():
    """The coordinates prefix carries no `#`, so the first `#` ends the type for
    a full symbol and a bare descriptor alike; a type or a free function has
    none to belong to."""
    assert enclosing_type_of("com/acme/Upload#file.") == "com/acme/Upload#"
    assert enclosing_type_of("maven com.acme:orders 1.0 com/acme/Upload#file.") == (
        "maven com.acme:orders 1.0 com/acme/Upload#"
    )
    assert enclosing_type_of("com/acme/Upload#") is None
    assert enclosing_type_of("helper().") is None


def _loaded(tmp_path: Path) -> DuckDbWorkspace:
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/Upload.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    facts = [
        SymbolFact(document_id="doc_1", symbol=_UPLOAD, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1", symbol=_FILE, construct_kind=ConstructKind.FIELD, enclosing=_UPLOAD
        ),
        SymbolFact(
            document_id="doc_1",
            symbol=_SETTER,
            construct_kind=ConstructKind.METHOD,
            enclosing=_UPLOAD,
        ),
        SymbolFact(document_id="doc_1", symbol=_RESOURCE, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=_CREATE,
            construct_kind=ConstructKind.METHOD,
            enclosing=_RESOURCE,
        ),
        AnnotationFact(
            document_id="doc_1",
            target=_FILE,
            retention="runtime",
            use=AnnotationUse(annotation=_REST_FORM, args={"value": "file"}),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=_SETTER,
            retention="runtime",
            use=AnnotationUse(annotation=_REST_FORM, args={}),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=_CREATE,
            retention="runtime",
            use=AnnotationUse(annotation=_POST, args={}),
        ),
        # On the TYPE itself: not a member, so it reaches no type's member set.
        AnnotationFact(
            document_id="doc_1",
            target=_RESOURCE,
            retention="runtime",
            use=AnnotationUse(annotation="jakarta/ws/rs/Path#", args={"value": "/r"}),
        ),
    ]
    write_fact_file(tmp_path / "facts" / "Upload.jsonl", document, facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    return workspace


def test_annotation_index_groups_every_annotation_row_by_its_target(tmp_path):
    workspace = _loaded(tmp_path)
    index = annotation_index(workspace)
    workspace.close()

    assert index[_FILE] == [(_REST_FORM, {"value": "file"})]
    assert index[_CREATE] == [(_POST, {})]
    assert _UPLOAD not in index


def test_member_annotations_are_grouped_by_the_declaring_type(tmp_path):
    """Quarkus's parameter-container rule (CP-19 row 4): a class whose FIELD or
    METHOD carries a binding annotation. The type's own annotation is not a
    member's and must not put `@Path` into `R`'s set."""
    workspace = _loaded(tmp_path)
    members = member_annotations_by_type(workspace)
    workspace.close()

    assert members[_UPLOAD] == {_REST_FORM}
    assert members[_RESOURCE] == {_POST}


def test_both_folds_are_built_once_per_load(tmp_path):
    """The same object back on the second call — `Workspace.once` keyed on a
    module-level builder, not a closure minted per call."""
    workspace = _loaded(tmp_path)
    assert annotation_index(workspace) is annotation_index(workspace)
    assert member_annotations_by_type(workspace) is member_annotations_by_type(workspace)
    workspace.close()
