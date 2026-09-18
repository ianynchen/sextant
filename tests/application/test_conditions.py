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

import pytest

from sextant.application.ports.catalogs import CatalogError
from sextant.application.resolve.conditions import (
    annotation_index,
    enclosing_type_of,
    holds,
    member_annotations_by_type,
    parse_condition,
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


KL = "org/springframework/kafka/annotation/KafkaListener#"
JL = "io/micronaut/jms/annotations/JMSListener#"


def test_equals_reads_the_owner_first():
    c = parse_condition(
        {
            "annotation_arg": {
                "annotation": "io.micronaut.jms.annotations.JMSListener",
                "name": "value",
                "equals": "sqsJmsConnectionFactory",
            }
        },
        "t",
    )
    index = {"m com/acme/A#on(sig_1).": [(JL, {"value": "sqsJmsConnectionFactory"})]}
    assert holds(c, "m com/acme/A#on(sig_1).", index)


def test_equals_falls_back_to_the_enclosing_type():
    c = parse_condition(
        {
            "annotation_arg": {
                "annotation": "io.micronaut.jms.annotations.JMSListener",
                "name": "value",
                "equals": "sqsJmsConnectionFactory",
            }
        },
        "t",
    )
    index = {"m com/acme/A#": [(JL, {"value": "sqsJmsConnectionFactory"})]}
    assert holds(c, "m com/acme/A#on(sig_1).", index)
    assert not holds(
        c,
        "m com/acme/A#on(sig_1).",
        {"m com/acme/A#": [(JL, {"value": "activeMqConnectionFactory"})]},
    )


def test_equals_is_case_sensitive_and_matches_any_array_element():
    c = parse_condition({"annotation_arg": {"annotation": "x.Y", "name": "v", "equals": "a"}}, "t")
    assert holds(c, "o", {"o": [("x/Y#", {"v": ["b", "a"]})]})
    assert not holds(c, "o", {"o": [("x/Y#", {"v": "A"})]})


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("true", True),
        ("TRUE", True),
        ("True", True),
        ("false", False),
        ("", False),
        ("${x}", False),
        (None, False),
    ],
)
def test_parses_true_is_boolean_parseboolean_after_hastext(value, expected):
    c = parse_condition(
        {
            "annotation_arg": {
                "annotation": "org.springframework.kafka.annotation.KafkaListener",
                "name": "batch",
                "parses_true": True,
            }
        },
        "t",
    )
    args = {} if value is None else {"batch": value}
    assert holds(c, "o", {"o": [(KL, args)]}) is expected


def test_name_aliases_first_present_wins():
    c = parse_condition(
        {"annotation_arg": {"annotation": "x.Y", "name": ["a", "b"], "equals": "1"}}, "t"
    )
    assert holds(c, "o", {"o": [("x/Y#", {"b": "1"})]})
    assert not holds(c, "o", {"o": [("x/Y#", {"a": "2", "b": "1"})]})


@pytest.mark.parametrize(
    "bad",
    [
        {"annotation_arg": {"annotation": "x.Y", "name": "v"}},  # no comparator
        {
            "annotation_arg": {"annotation": "x.Y", "name": "v", "equals": "1", "parses_true": True}
        },  # both
        {"annotation_arg": {"name": "v", "equals": "1"}},  # no annotation
        {"annotation_arg": {"annotation": "x.Y", "name": "v", "contains": "1"}},  # unknown key
        {"annotation_present": "x.Y"},  # unknown condition
        "annotation_arg",
    ],
)
def test_anything_else_is_refused_by_name(bad):
    with pytest.raises(CatalogError):
        parse_condition(bad, "t")
