from pathlib import Path

import pytest
import yaml

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.endpoints import SkippedCatalog, derive_endpoints
from sextant.cli.resources import catalogs_dir
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    Document,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CATALOGS = catalogs_dir()

# A second, invented annotation_driven shape — deliberately not Spring — so a
# test can hand `derive_endpoints` two catalogs that are genuinely different.
_INVENTED_LISTENER = Catalog(
    id="invented-listener",
    style="annotation_driven",
    protocol="kafka",
    direction="outbound",
    requires=("annotation_args",),
    source=Path("tests/invented.yml"),
    matches={
        "type_annotation": "com.acme.messaging.annotation.Listener",
        "mapping": {
            "path_from": ["value"],
            "prefix_from": ["value"],
            "method_from": "method",
            "all_methods": ["PUBLISH"],
            "prefix_annotation": "com.acme.messaging.annotation.Topic",
            "annotations": [
                {"fqn": "com.acme.messaging.annotation.OnMessage", "method": ["PUBLISH"]},
            ],
        },
    },
)


def test_catalog_declares_its_style_and_required_capabilities_when_loaded():
    catalogs = YamlCatalogSource(CATALOGS).load()
    spring = next(c for c in catalogs if c.id == "spring-web")
    assert spring.style == "annotation_driven"
    assert spring.protocol == "http"
    assert spring.direction == "inbound"
    assert "annotation_args" in spring.requires


def test_catalog_declares_wrappers_nullability_serialization_and_known_types():
    """D02 §2a, §2e, §2f, §2g: `spring-web` and `spring-mvc` both need these
    four blocks before payload shapes can be derived (Tasks 9-11 read them).
    The loader does not parse them into `Catalog` — they ride along in the
    raw file — so this reads the file directly, the same way the catalog
    itself is the source of truth for `matches`."""
    for name in ("spring-web", "spring-mvc"):
        raw = yaml.safe_load((CATALOGS / f"{name}.yml").read_text(encoding="utf-8"))

        wrapper_types = {w["type"] for w in raw["wrappers"]}
        assert wrapper_types == {
            "org.springframework.http.ResponseEntity",
            "reactor.core.publisher.Mono",
            "reactor.core.publisher.Flux",
            "java.util.concurrent.CompletableFuture",
            "java.util.Optional",
        }

        # The JetBrains entries are not redundant with JSpecify/Spring: the
        # Kotlin compiler emits them directly onto fields as CLASS-retention
        # annotations, so they are what makes Kotlin nullability work through
        # the ordinary annotation path.
        assert "org.jetbrains.annotations.Nullable" in raw["nullability"]["nullable"]
        assert "org.jetbrains.annotations.NotNull" in raw["nullability"]["not_null"]
        assert raw["nullability"]["scope"] == [
            {"annotation": "org.jspecify.annotations.NullMarked", "means": "not_null_by_default"}
        ]

        assert raw["serialization"]["name_from"] == [
            {"annotation": "com.fasterxml.jackson.annotation.JsonProperty", "arg": "value"}
        ]
        assert raw["serialization"]["ignore"] == ["com.fasterxml.jackson.annotation.JsonIgnore"]
        assert raw["serialization"]["default_strategy"] == "as_declared"

        known_types = {t["type"] for t in raw["known_types"]}
        assert known_types == {
            "java.time.Instant",
            "java.time.LocalDate",
            "java.math.BigDecimal",
            "java.util.UUID",
        }


def test_catalog_requires_type_annotations_for_nullability():
    """Nullability comes off `type_annotations`; a catalog that declares
    `nullability` without raising `requires` would run against a scanner
    lacking that capability and silently produce no nullability at all —
    the exact bypass capability gating exists to prevent (FR-17)."""
    catalogs = YamlCatalogSource(CATALOGS).load()
    for catalog_id in ("spring-web", "spring-mvc"):
        catalog = next(c for c in catalogs if c.id == catalog_id)
        assert "annotation_args" in catalog.requires
        assert "type_annotations" in catalog.requires


def test_catalog_maps_post_mapping_to_the_post_method():
    spring = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-web")
    annotations = spring.matches["mapping"]["annotations"]
    methods = {m["fqn"]: m.get("method") for m in annotations}
    assert methods["org.springframework.web.bind.annotation.PostMapping"] == ["POST"]


def test_catalog_leaves_request_mapping_without_a_preset_method():
    """`@RequestMapping` takes its method from its own argument, and means every
    method when it has none — so it must declare no default here, or the
    fallback that produces one endpoint per method can never be reached."""
    spring = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-web")
    annotations = spring.matches["mapping"]["annotations"]
    request_mapping = next(
        m
        for m in annotations
        if m["fqn"] == "org.springframework.web.bind.annotation.RequestMapping"
    )
    assert "method" not in request_mapping


def test_every_graphql_catalog_declares_the_protocols_fixed_format():
    """2G design §7, rung 1, owned by the catalogs that declare the protocol.

    All THREE declare it, not one: the ladder unions the blocks across
    catalogs, so a module pulling in only DGS must still get the answer. The
    entries are identical by construction and a contradiction between two
    would be refused rather than resolved, which is what keeps three copies
    from drifting silently — the same rule `media_formats` already lives
    under on `spring-web.yml`/`spring-mvc.yml`."""
    catalogs = YamlCatalogSource(CATALOGS).load()
    graphql = [c for c in catalogs if c.protocol == "graphql"]

    assert {c.id for c in graphql} == {"spring-graphql", "netflix-dgs", "microprofile-graphql"}
    assert all(c.format_fixed == {"graphql": "json"} for c in graphql)
    assert all(c.style == "annotation_driven" for c in graphql)
    assert all(c.direction == "inbound" for c in graphql)


def test_only_spring_graphql_needed_the_qualifier_form():
    """2H design §1's amended acceptance test, read off the catalogs
    themselves rather than off the derived rows.

    MicroProfile's non-root resolver is `@Source` on a PARAMETER — a
    genuinely different declaration shape that no shipped form reads — so it
    declares no qualifier and derives no resolver rows, which is silence
    rather than a wrong answer. DGS spells its scope on the operation
    annotation exactly as Spring does, so it rides the same form with a
    different attribute name and no engine change at all."""
    catalogs = {c.id: c for c in YamlCatalogSource(CATALOGS).load()}
    qualifiers = {
        catalog_id: catalogs[catalog_id].matches["mapping"].get("qualifier_from")
        for catalog_id in ("spring-graphql", "netflix-dgs", "microprofile-graphql")
    }

    assert qualifiers == {
        "spring-graphql": ["typeName"],
        "netflix-dgs": ["parentType"],
        "microprofile-graphql": None,
    }
    # All three share form 1 — every one of the three frameworks defaults its
    # name attribute to the method name (checkpoint answers 1, 2, 3), which is
    # what made it engine vocabulary instead of three catalog workarounds.
    assert all(
        catalogs[catalog_id].matches["mapping"]["path_fallback"] == "construct_name"
        for catalog_id in qualifiers
    )


def _controller_facts(root: Path) -> None:
    """Mirrors the exact shape the ASM extractor emits for a Spring
    controller (verified against fixtures/orders-service): a type-level
    RestController with no argument, a RequestMapping whose `value` is a
    one-element JSON array, one PostMapping and one GetMapping with no
    argument at all, and one GetMapping whose `value` is a one-element
    array. Method symbols carry the descriptor-hash disambiguator D00 §1
    requires on every method, because that is what the extractor writes."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/orders/OrderController.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    controller = "com/acme/orders/OrderController#"
    create = "com/acme/orders/OrderController#create(sig_1f0a4c2e)."
    get = "com/acme/orders/OrderController#get(sig_74b3d901)."
    list_ = "com/acme/orders/OrderController#list(sig_08c5be17)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=controller, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=create,
            construct_kind=ConstructKind.METHOD,
            enclosing=controller,
        ),
        SymbolFact(
            document_id="doc_1",
            symbol=get,
            construct_kind=ConstructKind.METHOD,
            enclosing=controller,
        ),
        SymbolFact(
            document_id="doc_1",
            symbol=list_,
            construct_kind=ConstructKind.METHOD,
            enclosing=controller,
        ),
        AnnotationFact(
            document_id="doc_1",
            target=controller,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/RestController#",
                args={},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=controller,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/RequestMapping#",
                args={"value": ["/v1/orders"]},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=create,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/PostMapping#",
                args={},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=get,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/GetMapping#",
                args={"value": ["/{id}"]},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=list_,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/GetMapping#",
                args={},
            ),
        ),
    ]
    write_fact_file(root / "OrderController.jsonl", document, facts)


def test_derive_endpoints_finds_the_three_annotated_routes_when_the_catalog_is_annotation_driven(
    tmp_path: Path,
):
    _controller_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    spring = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-web")

    skipped = derive_endpoints(
        workspace, [spring], capabilities={"annotation_args", "type_annotations"}
    )
    routes = {(e["method"], e["path"]) for e in workspace.query("endpoints")}
    workspace.close()

    assert skipped == []
    assert routes == {
        ("POST", "/v1/orders"),
        ("GET", "/v1/orders/{id}"),
        ("GET", "/v1/orders"),
    }


def _invented_listener_facts(root: Path) -> None:
    """A second, invented annotation_driven shape — deliberately not Spring —
    used only to prove that `protocol` and `direction` on the derived rows
    come from the catalog's own declared fields rather than from a literal
    baked into the SQL. D02 groups Spring Kafka and JMS listeners under this
    same style with `protocol: kafka`; a catalog like this one is exactly
    what would have silently come out labelled http/inbound before this fix."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/notify/OrderListener.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    listener = "com/acme/notify/OrderListener#"
    handle = "com/acme/notify/OrderListener#onOrderCreated(sig_3d92af60)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=listener, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=handle,
            construct_kind=ConstructKind.METHOD,
            enclosing=listener,
        ),
        AnnotationFact(
            document_id="doc_1",
            target=listener,
            retention="runtime",
            use=AnnotationUse(annotation="com/acme/messaging/annotation/Listener#", args={}),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=listener,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/messaging/annotation/Topic#",
                args={"value": ["orders."]},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=handle,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/messaging/annotation/OnMessage#",
                args={"value": ["created"]},
            ),
        ),
    ]
    write_fact_file(root / "OrderListener.jsonl", document, facts)


# --- 2H design §1: the two naming forms, on an invented framework ---------
#
# Deliberately NOT GraphQL, and deliberately not Spring: the forms are engine
# vocabulary, so a test that could only be written with `@QueryMapping` in it
# would be pinning a framework rather than a mechanism. The fixture below
# declares an annotation with a `scope` attribute and a `value` attribute and
# nothing else, which is the shape Spring GraphQL, Netflix DGS and
# MicroProfile all happen to share.


def _naming_forms_catalog(**mapping: object) -> Catalog:
    """A gateless catalog over the invented annotation below, with whatever
    naming vocabulary a test wants layered on."""
    return Catalog(
        id="invented-naming",
        style="annotation_driven",
        protocol="kafka",
        direction="inbound",
        requires=("annotation_args",),
        source=Path("tests/invented-naming.yml"),
        matches={
            "mapping": {
                "path_from": ["value"],
                "prefix_from": [],
                "method_from": "method",
                "all_methods": [],
                "prefix_annotation": None,
                "annotations": [{"fqn": "com.acme.messaging.annotation.OnMessage"}],
                **mapping,
            }
        },
    )


def _naming_forms_facts(root: Path, type_scope: str | None = None) -> None:
    """Four declarations covering every combination the two forms produce: a
    name spelled out, a name left to the construct, a scope with a spelled
    name, and a scope with a defaulted one.

    `type_scope` puts the same annotation on the enclosing TYPE carrying only
    a scope — the class-level shape, where a type states the scope once for
    every declaration it holds.
    """
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/notify/NamedHandlers.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    owner = "com/acme/notify/NamedHandlers#"
    facts: list[object] = [
        SymbolFact(document_id="doc_1", symbol=owner, construct_kind=ConstructKind.CLASS)
    ]
    if type_scope is not None:
        facts.append(
            AnnotationFact(
                document_id="doc_1",
                target=owner,
                retention="runtime",
                use=AnnotationUse(
                    annotation="com/acme/messaging/annotation/OnMessage#",
                    args={"scope": type_scope},
                ),
            )
        )
    # `args` mirrors what a real extractor emits: an ABSENT attribute is
    # absent from the map entirely — an annotation's declared default is
    # never written into the class file (2H checkpoint answer 1).
    declarations = {
        "explicit": {"value": ["named"]},
        "defaulted": {},
        "scoped": {"scope": "Parent", "value": ["member"]},
        "scopedDefaulted": {"scope": "Parent"},
    }
    for name, args in declarations.items():
        symbol = f"{owner}{name}(sig_3d92af60)."
        facts.append(
            SymbolFact(
                document_id="doc_1",
                symbol=symbol,
                construct_kind=ConstructKind.METHOD,
                enclosing=owner,
            )
        )
        facts.append(
            AnnotationFact(
                document_id="doc_1",
                target=symbol,
                retention="runtime",
                use=AnnotationUse(annotation="com/acme/messaging/annotation/OnMessage#", args=args),
            )
        )
    write_fact_file(root / "NamedHandlers.jsonl", document, facts)


def _paths_of(tmp_path: Path, catalog: Catalog, type_scope: str | None = None) -> set[str]:
    _naming_forms_facts(tmp_path / "facts", type_scope)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    derive_endpoints(workspace, [catalog], capabilities={"annotation_args"})
    paths = {str(row["path"]) for row in workspace.query("endpoints")}
    workspace.close()
    return paths


def test_a_catalog_declaring_no_naming_forms_derives_exactly_what_it_always_did(
    tmp_path: Path,
):
    """The inertness pin. Both forms are optional, and a catalog that declares
    neither must compose `prefix || suffix` and nothing else — which is what
    lets them ship without touching the behaviour of every catalog written
    before them.

    The empty paths below are the PRE-2H behaviour, recorded here rather than
    quietly fixed: an absent attribute defaulted to `''`. That is the bug the
    next test removes, and it is only reachable by a catalog that asks for
    none of the vocabulary that removes it.
    """
    assert _paths_of(tmp_path, _naming_forms_catalog()) == {"named", "member", ""}


def test_an_absent_name_attribute_falls_back_to_the_constructs_own_name(
    tmp_path: Path,
):
    """Form 1. `defaulted` and `scopedDefaulted` carry the annotation with no
    `value` at all, and each takes the name of the method it sits on.

    The two spelled names are asserted UNCHANGED in the same breath: the
    fallback fires on absence only, never as a rename of something declared.
    """
    paths = _paths_of(tmp_path, _naming_forms_catalog(path_fallback="construct_name"))

    assert paths == {"named", "member", "defaulted", "scopedDefaulted"}


def test_a_scope_attribute_composes_in_front_of_the_name_it_qualifies(
    tmp_path: Path,
):
    """Form 2, composing with form 1.

    `scoped` spells both halves; `scopedDefaulted` spells the scope and takes
    the name from the method — the two forms meeting, which is the case that
    would need its own bespoke rule if they were not separable. The two
    declarations carrying NO scope compose no separator either: a qualifier
    that is absent contributes nothing rather than a leading `.`.
    """
    paths = _paths_of(
        tmp_path,
        _naming_forms_catalog(
            path_fallback="construct_name",
            qualifier_from=["scope"],
            qualifier_separator=".",
        ),
    )

    assert paths == {"named", "defaulted", "Parent.member", "Parent.scopedDefaulted"}


def test_the_separator_is_catalog_data_rather_than_a_punctuation_the_engine_picked(
    tmp_path: Path,
):
    """Which character joins a scope to a member is a framework's convention —
    GraphQL's `.`, another framework's `#` or `/`. An engine that baked one in
    would be naming a framework in code, which D02 §2 forbids for exactly the
    reasons it forbids naming an annotation there.

    Asserts the WHOLE set, not membership: a membership check passes happily
    over a wrong row sitting beside the right one, which is how the dangling
    separator below survived the first round of this file.
    """
    paths = _paths_of(
        tmp_path,
        _naming_forms_catalog(
            path_fallback="construct_name",
            qualifier_from=["scope"],
            qualifier_separator="#",
        ),
    )

    assert paths == {"named", "defaulted", "Parent#member", "Parent#scopedDefaulted"}


def test_a_qualifier_without_a_name_fallback_is_refused_rather_than_left_dangling(
    tmp_path: Path,
):
    """A scope with no fallback composes the scope and the separator onto an
    EMPTY name — `Parent#` — published at `resolved`/`compiler`. That is the
    same confidently-wrong-address class the empty path was, one step along,
    so the two forms are declared together or not at all.

    Refused at validation rather than filtered at derivation: the catalog is
    the thing that is wrong, and a run that silently dropped those rows would
    leave a framework half-described with nothing saying so.
    """
    with pytest.raises(CatalogError) as raised:
        _paths_of(
            tmp_path,
            _naming_forms_catalog(qualifier_from=["scope"], qualifier_separator="#"),
        )

    assert "path_fallback" in str(raised.value)
    assert "invented-naming.yml" in str(raised.value)


def test_an_explicitly_empty_separator_is_refused_like_a_missing_one(tmp_path: Path):
    """`qualifier_separator: ""` passes an `is None` check and then composes
    `Parentmember` — precisely what the missing-separator refusal exists to
    prevent, reached by spelling the key rather than omitting it.

    An empty separator has no honest use: a framework that runs the two halves
    together has no composition to declare in the first place.
    """
    with pytest.raises(CatalogError) as raised:
        _paths_of(
            tmp_path,
            _naming_forms_catalog(
                path_fallback="construct_name",
                qualifier_from=["scope"],
                qualifier_separator="",
            ),
        )

    assert "qualifier_separator" in str(raised.value)
    assert "invented-naming.yml" in str(raised.value)


def test_a_scope_stated_on_the_enclosing_type_reaches_a_declaration_that_names_none(
    tmp_path: Path,
):
    """The class-level scope shape (2H design §1): a type states the scope once
    and its declarations name only their own member.

    Reads the SAME attribute one level out, through a join that mirrors the
    existing class-level prefix exactly — so a catalog spends no extra
    vocabulary on it. The declaration's own scope still wins where both are
    present: the nearer declaration is the more specific, which is the
    precedence every framework offering both levels keeps.
    """
    paths = _paths_of(
        tmp_path,
        _naming_forms_catalog(
            path_fallback="construct_name",
            qualifier_from=["scope"],
            qualifier_separator=".",
        ),
        type_scope="Enclosing",
    )

    assert paths == {
        # No scope of their own — they take the type's.
        "Enclosing.named",
        "Enclosing.defaulted",
        # Their own scope wins over the type's.
        "Parent.member",
        "Parent.scopedDefaulted",
    }


def test_a_scoped_annotation_with_no_scope_anywhere_derives_no_row_at_all(
    tmp_path: Path,
):
    """`requires_qualifier` — the rule that keeps a missing scope silent
    instead of wrong.

    An annotation that names a member OF something has no address until the
    something is known. Emitting the bare member name would publish a
    top-level identity for a declaration that is not one — a DIFFERENT
    endpoint from the one the code declares — at `resolved`/`compiler`, where
    nothing downstream could tell it from an observation. Silence is the
    honest answer: the declaration is real, but what it belongs to is stated
    somewhere these facts do not reach.
    """
    paths = _paths_of(
        tmp_path,
        _naming_forms_catalog(
            path_fallback="construct_name",
            qualifier_from=["scope"],
            qualifier_separator=".",
            annotations=[
                {
                    "fqn": "com.acme.messaging.annotation.OnMessage",
                    "requires_qualifier": True,
                }
            ],
        ),
    )

    # `named` and `defaulted` state no scope and no type states one for them,
    # so they derive NOTHING — not `named`, not `defaulted`.
    assert paths == {"Parent.member", "Parent.scopedDefaulted"}


def test_a_catalog_naming_an_unknown_name_fallback_is_refused_by_file(tmp_path: Path):
    """An unrecognised word must fail loudly rather than fall through to the
    empty default — a silent fall-through would restore the very empty-path
    row the form exists to remove, and nothing downstream could tell that
    address from an observed one (NFR-5)."""
    with pytest.raises(CatalogError) as raised:
        _paths_of(tmp_path, _naming_forms_catalog(path_fallback="parameter_name"))

    assert "parameter_name" in str(raised.value)
    assert "invented-naming.yml" in str(raised.value)


def test_a_qualifier_with_no_separator_is_refused_by_file(tmp_path: Path):
    """Declaring a scope but no separator would concatenate `Parent` onto
    `member` with nothing between them — a plausible-looking address that
    matches no caller."""
    with pytest.raises(CatalogError) as raised:
        _paths_of(tmp_path, _naming_forms_catalog(qualifier_from=["scope"]))

    assert "qualifier_separator" in str(raised.value)
    assert "invented-naming.yml" in str(raised.value)


def test_derive_endpoints_carries_the_catalogs_own_protocol_and_direction_when_non_http(
    tmp_path: Path,
):
    _invented_listener_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    skipped = derive_endpoints(workspace, [_INVENTED_LISTENER], capabilities={"annotation_args"})
    rows = workspace.query("endpoints")
    workspace.close()

    assert skipped == []
    assert len(rows) == 1
    assert rows[0]["protocol"] == "kafka"
    assert rows[0]["direction"] == "outbound"
    assert rows[0]["protocol"] != "http"
    assert rows[0]["direction"] != "inbound"


def test_derive_endpoints_keeps_both_catalogs_results_when_two_catalogs_match(
    tmp_path: Path,
):
    """D02 §5: "Two catalogs may both match; both produce endpoints, and
    duplicates merge on wire identity." A derivation that replaces the table
    per catalog makes the last catalog the only catalog, and every endpoint
    the earlier ones found disappears with no skip, no gap, and no warning —
    the silent-loss failure capability gating exists to prevent."""
    _controller_facts(tmp_path / "facts")
    _invented_listener_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    spring = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-web")

    skipped = derive_endpoints(
        workspace,
        [spring, _INVENTED_LISTENER],
        capabilities={"annotation_args", "type_annotations"},
    )
    rows = workspace.query("endpoints")
    workspace.close()

    assert skipped == []
    assert {(r["protocol"], r["method"], r["path"]) for r in rows} == {
        ("http", "POST", "/v1/orders"),
        ("http", "GET", "/v1/orders/{id}"),
        ("http", "GET", "/v1/orders"),
        ("kafka", "PUBLISH", "orders.created"),
    }


def test_derive_endpoints_merges_on_wire_identity_when_two_catalogs_match_the_same_code(
    tmp_path: Path,
):
    """The other half of D02 §5: accumulating must not double-report. Two
    catalogs that describe the same annotations — the realistic case of a
    framework catalog and its umbrella — see the same routes, and the wire
    is where sameness is decided."""
    _controller_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    spring = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-web")
    twin = Catalog(**{**vars(spring), "id": "spring-web-twin"})

    derive_endpoints(
        workspace, [spring, twin], capabilities={"annotation_args", "type_annotations"}
    )
    rows = workspace.query("endpoints")
    workspace.close()

    assert len(rows) == 3


def test_derive_endpoints_skips_and_reports_when_a_required_capability_is_missing(
    tmp_path: Path,
):
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    catalog = Catalog(
        id="spring-web",
        style="annotation_driven",
        protocol="http",
        direction="inbound",
        requires=("annotation_args",),
        matches={},
        source=Path("tests/needs-a-capability.yml"),
    )

    skipped = derive_endpoints(workspace, [catalog], capabilities=set())
    workspace.close()

    assert skipped == [SkippedCatalog("spring-web", ("annotation_args",))]


def test_derive_endpoints_sql_names_no_framework_when_read():
    """D02's central claim — frameworks are data, engines are generic
    interpreters — is falsified the moment a framework's own identifier
    shows up as a literal in the engine's SQL. A second annotation_driven
    framework must be addable as one YAML file with no change here."""
    sql = (
        Path(__file__).parents[2]
        / "src"
        / "sextant"
        / "storage"
        / "duckdb"
        / "derive_endpoints.sql"
    )
    text = sql.read_text(encoding="utf-8").lower()
    assert "spring" not in text
    assert "org/springframework" not in text


def _scalar_path_facts(root: Path) -> None:
    """A framework whose path arguments are declared `String`, not `String[]`.
    JAX-RS `@Path` is the real one: its `value()` is a plain String, so the
    compiled annotation argument is a bare JSON string and not a one-element
    array."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/rest/OrderResource.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    resource = "com/acme/rest/OrderResource#"
    find = "com/acme/rest/OrderResource#find(sig_5ea17c38)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=resource, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=find,
            construct_kind=ConstructKind.METHOD,
            enclosing=resource,
        ),
        AnnotationFact(
            document_id="doc_1",
            target=resource,
            retention="runtime",
            use=AnnotationUse(annotation="com/acme/rest/Resource#", args={}),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=resource,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/rest/Path#",
                args={"value": "/rest/orders"},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=find,
            retention="runtime",
            use=AnnotationUse(annotation="com/acme/rest/Get#", args={"value": "/{id}"}),
        ),
    ]
    write_fact_file(root / "OrderResource.jsonl", document, facts)


_SCALAR_PATH_CATALOG = Catalog(
    id="invented-scalar-path",
    style="annotation_driven",
    protocol="http",
    direction="inbound",
    requires=("annotation_args",),
    source=Path("tests/invented.yml"),
    matches={
        "type_annotation": "com.acme.rest.Resource",
        "mapping": {
            "path_from": ["value"],
            "prefix_from": ["value"],
            "method_from": "method",
            "all_methods": ["GET"],
            # Not a mapping annotation: this catalog is the JAX-RS shape, where
            # the type carries the path and the method carries the verb.
            "prefix_annotation": "com.acme.rest.Path",
            "annotations": [{"fqn": "com.acme.rest.Get", "method": ["GET"]}],
        },
    },
)


def test_derive_endpoints_reads_a_scalar_annotation_argument_when_it_is_not_an_array(
    tmp_path: Path,
):
    """Reading only element 0 of an array silently yields NULL on a scalar, and
    the path collapses to the prefix alone — a wrong route reported with full
    `resolved`/`compiler` confidence. Spring's `value()` is `String[]`, so this
    is invisible there and fatal for any catalog whose argument is a plain
    String."""
    _scalar_path_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    derive_endpoints(workspace, [_SCALAR_PATH_CATALOG], capabilities={"annotation_args"})
    rows = workspace.query("endpoints")
    workspace.close()

    assert [(r["method"], r["path"]) for r in rows] == [("GET", "/rest/orders/{id}")]


_MULTI_PATH_CATALOG = Catalog(
    id="invented-multi-path",
    style="annotation_driven",
    protocol="http",
    direction="inbound",
    requires=("annotation_args",),
    source=Path("tests/invented.yml"),
    matches={
        "mapping": {
            "path_from": ["value"],
            "prefix_from": ["value"],
            "method_from": "method",
            "all_methods": ["GET", "POST", "PUT", "DELETE"],
            "prefix_annotation": "com.acme.rest.Mapping",
            # No `method` key: the annotation pre-sets no verb, so the
            # derivation reads that absence as "every method in all_methods"
            # — and the row below hands it two of them explicitly instead.
            "annotations": [{"fqn": "com.acme.rest.Mapping", "method": ["GET", "POST"]}],
        },
    },
)


def test_a_mapping_naming_two_paths_and_two_methods_derives_all_four_identities(
    tmp_path: Path,
):
    """`derive_endpoints.sql` claims it in a comment — "a two-topic,
    two-method mapping is four identities" — and until now nothing pinned it.
    The claim is load-bearing and fragile: DuckDB ZIPS two `UNNEST`s that sit
    in the same SELECT rather than cross-joining them, so the naive spelling
    of this derivation would silently yield TWO rows (`GET /a`, `POST /b`),
    dropping `GET /b` and `POST /a` — two real routes gone, with the two that
    survived reported at full `resolved`/`compiler` confidence. The separate
    `mapped_methods` CTE is what makes it a cross product, and this is the
    test that fails if anyone folds it back into one SELECT.

    `@RequestMapping(value = {"/a", "/b"}, method = {GET, POST})` is the real
    Spring shape; the annotation here is invented so the pin holds on the
    generic engine rather than on one framework's catalog file."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/rest/OrderResource.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    resource = "com/acme/rest/OrderResource#"
    handle = "com/acme/rest/OrderResource#handle(sig_5ea17c38)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=resource, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=handle,
            construct_kind=ConstructKind.METHOD,
            enclosing=resource,
        ),
        AnnotationFact(
            document_id="doc_1",
            target=handle,
            retention="runtime",
            use=AnnotationUse(annotation="com/acme/rest/Mapping#", args={"value": ["/a", "/b"]}),
        ),
    ]
    write_fact_file(tmp_path / "facts" / "OrderResource.jsonl", document, facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    derive_endpoints(workspace, [_MULTI_PATH_CATALOG], capabilities={"annotation_args"})
    rows = workspace.query("endpoints")
    workspace.close()

    assert [(r["method"], r["path"]) for r in rows] == [
        ("GET", "/a"),
        ("GET", "/b"),
        ("POST", "/a"),
        ("POST", "/b"),
    ]


# --- Task 5: annotation-declared media (consumes/produces) ---

_MEDIA_CATALOG = Catalog(
    id="invented-media",
    style="annotation_driven",
    protocol="http",
    direction="inbound",
    requires=("annotation_args",),
    source=Path("tests/invented.yml"),
    matches={
        "mapping": {
            "path_from": ["value"],
            "prefix_from": ["value"],
            "consumes_from": ["consumes"],
            "produces_from": ["produces"],
            "method_from": "method",
            "all_methods": ["GET"],
            "prefix_annotation": "com.acme.rest.Mapping",
            "annotations": [{"fqn": "com.acme.rest.Get", "method": ["GET"]}],
        },
    },
)


def _media_reading_facts(root: Path) -> None:
    """Three handlers exercising the scalar-or-array read and the NULL rule:
    a scalar `consumes`, an out-of-order array `produces`, and neither
    attribute at all."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/rest/OrderResource.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    resource = "com/acme/rest/OrderResource#"
    scalar = "com/acme/rest/OrderResource#getScalar(sig_1a2b3c4d)."
    array = "com/acme/rest/OrderResource#getArray(sig_2b3c4d5e)."
    neither = "com/acme/rest/OrderResource#getNeither(sig_3c4d5e6f)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=resource, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=scalar,
            construct_kind=ConstructKind.METHOD,
            enclosing=resource,
        ),
        SymbolFact(
            document_id="doc_1",
            symbol=array,
            construct_kind=ConstructKind.METHOD,
            enclosing=resource,
        ),
        SymbolFact(
            document_id="doc_1",
            symbol=neither,
            construct_kind=ConstructKind.METHOD,
            enclosing=resource,
        ),
        AnnotationFact(
            document_id="doc_1",
            target=scalar,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/rest/Get#",
                args={"value": ["/scalar"], "consumes": "application/json"},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=array,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/rest/Get#",
                args={"value": ["/array"], "produces": ["b/y", "a/x"]},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=neither,
            retention="runtime",
            use=AnnotationUse(annotation="com/acme/rest/Get#", args={"value": ["/neither"]}),
        ),
    ]
    write_fact_file(root / "OrderResource.jsonl", document, facts)


def test_media_attributes_are_read_scalar_or_array_order_normalized_and_absence_stays_null(
    tmp_path: Path,
):
    """(i) a scalar `consumes` and an out-of-order array `produces` both read
    correctly — the same scalar-or-array pattern `path_from` already uses —
    and normalize to a sorted JSON array; (ii) a mapping declaring neither
    attribute derives both columns NULL, never a guessed default (D01 §4)."""
    _media_reading_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    derive_endpoints(workspace, [_MEDIA_CATALOG], capabilities={"annotation_args"})
    rows = {r["path"]: r for r in workspace.query("endpoints")}
    workspace.close()

    assert rows["/scalar"]["consumes"] == '["application/json"]'
    assert rows["/scalar"]["produces"] is None
    assert rows["/array"]["produces"] == '["a/x","b/y"]'
    assert rows["/array"]["consumes"] is None
    assert rows["/neither"]["consumes"] is None
    assert rows["/neither"]["produces"] is None


def _one_method_two_annotations_facts(root: Path) -> None:
    """One handler, two mapping-annotation uses on it — the same wire
    identity twice, differing only in `produces`. Contrived as Java source,
    but a legitimate pair of annotation facts, and exactly what the
    within-batch union (D01 §4) must fold into one row."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/rest/OrderResource.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    resource = "com/acme/rest/OrderResource#"
    handle = "com/acme/rest/OrderResource#handle(sig_4d5e6f70)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=resource, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=handle,
            construct_kind=ConstructKind.METHOD,
            enclosing=resource,
        ),
        AnnotationFact(
            document_id="doc_1",
            target=handle,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/rest/Get#",
                args={"value": ["/negotiate"], "produces": "b/y"},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=handle,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/rest/Get#",
                args={"value": ["/negotiate"], "produces": "a/x"},
            ),
        ),
    ]
    write_fact_file(root / "OrderResource.jsonl", document, facts)


def test_two_mapping_annotations_on_one_method_derive_one_row_with_the_media_union(
    tmp_path: Path,
):
    """(iii) two mapping annotations on ONE method — same path/method, rows
    differing only in media — derive ONE row whose `produces` is the sorted
    distinct union, not two rows and not either annotation's value alone."""
    _one_method_two_annotations_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    derive_endpoints(workspace, [_MEDIA_CATALOG], capabilities={"annotation_args"})
    rows = workspace.query("endpoints")
    workspace.close()

    assert len(rows) == 1
    assert rows[0]["produces"] == '["a/x","b/y"]'


def _content_negotiation_sibling_facts(root: Path) -> None:
    """Two DIFFERENT handlers mapped to the same path and method — a
    content-negotiation pair, distinguished only by their own `produces`.
    The within-batch union must not fold these together: `handler` is one of
    the grouped columns, not an aggregate, so it keeps them apart exactly as
    it did before this task."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/rest/OrderResource.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    resource = "com/acme/rest/OrderResource#"
    get_json = "com/acme/rest/OrderResource#getJson(sig_5e6f7081)."
    get_xml = "com/acme/rest/OrderResource#getXml(sig_6f708192)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=resource, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=get_json,
            construct_kind=ConstructKind.METHOD,
            enclosing=resource,
        ),
        SymbolFact(
            document_id="doc_1",
            symbol=get_xml,
            construct_kind=ConstructKind.METHOD,
            enclosing=resource,
        ),
        AnnotationFact(
            document_id="doc_1",
            target=get_json,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/rest/Get#",
                args={"value": ["/negotiate"], "produces": "application/json"},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=get_xml,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/rest/Get#",
                args={"value": ["/negotiate"], "produces": "application/xml"},
            ),
        ),
    ]
    write_fact_file(root / "OrderResource.jsonl", document, facts)


def test_content_negotiation_siblings_with_different_handlers_derive_exactly_as_today(
    tmp_path: Path,
):
    """(iv) two mappings on different methods sharing a wire identity still
    derive their own rows: the union groups on every non-media column, so
    differing handlers never collapse into one another's media."""
    _content_negotiation_sibling_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    derive_endpoints(workspace, [_MEDIA_CATALOG], capabilities={"annotation_args"})
    rows = workspace.query("endpoints")
    workspace.close()

    assert len(rows) == 2
    produces_by_handler = {r["handler"]: r["produces"] for r in rows}
    assert produces_by_handler["com/acme/rest/OrderResource#getJson(sig_5e6f7081)."] == (
        '["application/json"]'
    )
    assert produces_by_handler["com/acme/rest/OrderResource#getXml(sig_6f708192)."] == (
        '["application/xml"]'
    )


def _client_facts(root: Path, type_args: dict[str, object]) -> None:
    """A client interface in the outbound shape D02 §2 (amended) describes: a
    type-level marker that also carries the service name and address prefix
    — the exact @FeignClient hazard the prefix_from/peer_from split exists
    for — and a method-level mapping annotation with no argument beyond its
    own path."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/billing/BillingClient.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    client = "com/acme/billing/BillingClient#"
    submit = "com/acme/billing/BillingClient#submit(sig_9f1c2b47)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=client, construct_kind=ConstructKind.INTERFACE),
        SymbolFact(
            document_id="doc_1",
            symbol=submit,
            construct_kind=ConstructKind.METHOD,
            enclosing=client,
            signature=Signature(parameters=[], returns=TypeRef(symbol="void")),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=client,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/billing/annotation/ServiceClient#",
                args=type_args,
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=submit,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/billing/annotation/PostExchange#",
                args={"value": ["/invoices"]},
            ),
        ),
    ]
    write_fact_file(root / "BillingClient.jsonl", document, facts)


_OUTBOUND_CATALOG = Catalog(
    id="invented-outbound",
    style="annotation_driven",
    protocol="http",
    direction="outbound",
    requires=("annotation_args",),
    source=Path("tests/invented.yml"),
    matches={
        "type_annotation": "com.acme.billing.annotation.ServiceClient",
        "request_body": {"annotation": "com.acme.billing.annotation.Body", "fallback": "none"},
        "mapping": {
            "path_from": ["value"],
            # `path` carries the prefix; `name` (read by peer_from below)
            # never does — the leak the split exists to prevent.
            "prefix_from": ["path"],
            "peer_from": ["name", "value"],
            "method_from": "method",
            "all_methods": ["GET"],
            "prefix_annotation": "com.acme.billing.annotation.ServiceClient",
            "annotations": [
                {"fqn": "com.acme.billing.annotation.PostExchange", "method": ["POST"]},
            ],
        },
    },
)


def _outbound_workspace(tmp_path: Path, type_args: dict[str, object] | None = None):
    args = type_args if type_args is not None else {"name": "billing", "path": "/billing"}
    _client_facts(tmp_path / "facts", args)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    skipped = derive_endpoints(workspace, [_OUTBOUND_CATALOG], capabilities={"annotation_args"})
    assert skipped == []
    return workspace


def test_an_outbound_catalog_produces_caller_rows_with_peer_and_prefixed_path(tmp_path):
    workspace = _outbound_workspace(tmp_path)
    [endpoint] = [e for e in workspace.query("endpoints") if e["direction"] == "outbound"]
    assert endpoint["path"] == "/billing/invoices"
    assert endpoint["peer"] == "billing"
    assert endpoint["handler"] is None
    assert str(endpoint["caller"]).endswith("#submit(sig_") or "#" in str(endpoint["caller"])
    workspace.close()


def _orders_controller_facts(root: Path) -> None:
    """A controller exposing exactly one route, POST /v1/orders — deliberately
    narrower than `_controller_facts` (which also exposes two GET routes
    sharing the same path), so a path-only filter in the merge test names the
    merged row unambiguously."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/orders/OrderController.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    controller = "com/acme/orders/OrderController#"
    create = "com/acme/orders/OrderController#create(sig_1f0a4c2e)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=controller, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=create,
            construct_kind=ConstructKind.METHOD,
            enclosing=controller,
        ),
        AnnotationFact(
            document_id="doc_1",
            target=controller,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/RestController#",
                args={},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=controller,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/RequestMapping#",
                args={"value": ["/v1/orders"]},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=create,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/PostMapping#",
                args={},
            ),
        ),
    ]
    write_fact_file(root / "OrderController.jsonl", document, facts)


def _orders_client_facts(root: Path) -> None:
    """A client whose one method calls the same wire identity
    `_controller_facts` exposes (POST /v1/orders) — used only to prove the
    cross-direction merge, so the path is hard-coded on the method rather
    than assembled from a prefix."""
    document = Document(
        document_id="doc_2",
        relative_path="com/acme/billing/OrdersClient.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    client = "com/acme/billing/OrdersClient#"
    submit = "com/acme/billing/OrdersClient#submit(sig_9f1c2b47)."
    facts = [
        SymbolFact(document_id="doc_2", symbol=client, construct_kind=ConstructKind.INTERFACE),
        SymbolFact(
            document_id="doc_2",
            symbol=submit,
            construct_kind=ConstructKind.METHOD,
            enclosing=client,
            signature=Signature(parameters=[], returns=TypeRef(symbol="void")),
        ),
        AnnotationFact(
            document_id="doc_2",
            target=client,
            retention="runtime",
            use=AnnotationUse(annotation="com/acme/billing/annotation/ServiceClient#", args={}),
        ),
        AnnotationFact(
            document_id="doc_2",
            target=submit,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/billing/annotation/PostExchange#",
                args={"value": ["/v1/orders"]},
            ),
        ),
    ]
    write_fact_file(root / "OrdersClient.jsonl", document, facts)


def _two_direction_workspace(tmp_path: Path):
    """An inbound controller exposing POST /v1/orders and an outbound client
    calling the very same wire identity, resolved together so the merge in
    `endpoints_merge` has something to collapse."""
    _orders_controller_facts(tmp_path / "facts")
    _orders_client_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    spring = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-web")
    skipped = derive_endpoints(
        workspace,
        [spring, _OUTBOUND_CATALOG],
        capabilities={"annotation_args", "type_annotations"},
    )
    assert skipped == []
    return workspace


def test_a_path_the_module_both_exposes_and_calls_is_one_endpoint_with_both(tmp_path):
    """D02 §3: inbound runs first so the merged row keeps the server's handler
    and gains the client's caller — appearing twice would make every consumer
    re-implement the merge."""
    workspace = _two_direction_workspace(tmp_path)
    rows = [e for e in workspace.query("endpoints") if e["path"] == "/v1/orders"]
    assert len(rows) == 1
    [merged] = rows
    assert merged["direction"] == "both"
    assert merged["handler"] is not None and merged["caller"] is not None
    workspace.close()


def _legacy_facts(root: Path) -> None:
    """A client interface with no type-level marker at all — the Retrofit
    shape: the mapping annotation on the method is the whole evidence."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/legacy/LegacyClient.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    client = "com/acme/legacy/LegacyClient#"
    fetch = "com/acme/legacy/LegacyClient#fetch(sig_2a77e410)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=client, construct_kind=ConstructKind.INTERFACE),
        SymbolFact(
            document_id="doc_1",
            symbol=fetch,
            construct_kind=ConstructKind.METHOD,
            enclosing=client,
            signature=Signature(parameters=[], returns=TypeRef(symbol="void")),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=fetch,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/legacy/annotation/GET#",
                args={"value": "legacy/invoices"},
            ),
        ),
    ]
    write_fact_file(root / "LegacyClient.jsonl", document, facts)


_UNGATED_CATALOG = Catalog(
    id="invented-ungated",
    style="annotation_driven",
    protocol="http",
    direction="outbound",
    requires=("annotation_args",),
    source=Path("tests/invented.yml"),
    matches={
        # No type-level gate at all: absence, not a marker no fact ever
        # carries.
        "type_annotation": None,
        "mapping": {
            "path_from": ["value"],
            "prefix_from": ["path"],
            "peer_from": [],
            "method_from": "method",
            "all_methods": ["GET"],
            "prefix_annotation": "com.acme.legacy.annotation.Prefix",
            "annotations": [
                {"fqn": "com.acme.legacy.annotation.GET", "method": ["GET"]},
            ],
        },
    },
)


def _ungated_workspace(tmp_path):
    _legacy_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    skipped = derive_endpoints(workspace, [_UNGATED_CATALOG], capabilities={"annotation_args"})
    assert skipped == []
    return workspace


def test_a_catalog_with_no_type_gate_matches_on_method_annotations_alone(tmp_path):
    """A Retrofit interface has no type-level marker; the mapping annotation
    is the whole evidence."""
    workspace = _ungated_workspace(tmp_path)
    rows = [e for e in workspace.query("endpoints") if e["direction"] == "outbound"]
    assert [e["path"] for e in rows] == ["legacy/invoices"]
    workspace.close()


def _gateless_implementer_facts(root: Path) -> None:
    """The Task 7 review's own repro (Critical finding C1, style modelled
    on the Task 6 prefix-leak regression in `test_effective_annotations.py`):
    a gateless (Retrofit-shaped) interface method carrying the mapping,
    IMPLEMENTED by a second, unrelated class whose own override repeats no
    annotation of its own. A gated HTTP catalog would legitimately inherit
    the mapping onto that implementer (Task 7's own fixture); a gateless
    catalog must not — the interface method IS the client identity, and an
    implementer here is not a controller a mapping could plausibly belong
    to."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/legacy/ClientIface.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    iface = "com/acme/legacy/ClientIface#"
    iface_fetch = "com/acme/legacy/ClientIface#fetch(sig_2a77e410)."
    impl = "com/acme/legacy/ClientImpl#"
    impl_fetch = "com/acme/legacy/ClientImpl#fetch(sig_2a77e410)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=iface, construct_kind=ConstructKind.INTERFACE),
        SymbolFact(
            document_id="doc_1",
            symbol=iface_fetch,
            construct_kind=ConstructKind.METHOD,
            enclosing=iface,
            signature=Signature(parameters=[], returns=TypeRef(symbol="void")),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=iface_fetch,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/legacy/annotation/GET#",
                args={"value": "legacy/invoices"},
            ),
        ),
        SymbolFact(
            document_id="doc_1",
            symbol=impl,
            construct_kind=ConstructKind.CLASS,
            interfaces=[iface],
        ),
        SymbolFact(
            document_id="doc_1",
            symbol=impl_fetch,
            construct_kind=ConstructKind.METHOD,
            enclosing=impl,
            signature=Signature(parameters=[], returns=TypeRef(symbol="void")),
        ),
    ]
    write_fact_file(root / "ClientIface.jsonl", document, facts)


def test_a_gateless_catalog_never_synthesizes_onto_an_implementing_class(tmp_path):
    """Task 7 review, Critical finding C1: an interface method's mapping
    under a GATELESS catalog must derive exactly the one row the interface
    method itself already carries — never a second, synthesized row for a
    class that merely implements that interface. Before the fix,
    `annotation_driven.run` ran `inherited_rows` unconditionally, so this
    exact fixture minted a second row for `ClientImpl#fetch` with no
    annotation of its own."""
    _gateless_implementer_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    skipped = derive_endpoints(workspace, [_UNGATED_CATALOG], capabilities={"annotation_args"})
    assert skipped == []
    rows = [e for e in workspace.query("endpoints") if e["direction"] == "outbound"]
    workspace.close()

    assert len(rows) == 1
    [row] = rows
    assert row["path"] == "legacy/invoices"
    assert row["caller"] == "com/acme/legacy/ClientIface#fetch(sig_2a77e410)."


def test_the_service_name_never_leaks_into_the_path(tmp_path):
    """@FeignClient(name=…) with NO path attribute: the prefix is empty, not
    the name — the exact bug the prefix_from/peer_from split exists for."""
    workspace = _outbound_workspace(tmp_path, type_args={"name": "billing"})
    [endpoint] = [e for e in workspace.query("endpoints") if e["direction"] == "outbound"]
    assert endpoint["path"] == "/invoices"
    assert endpoint["peer"] == "billing"
    workspace.close()


def _inventory_facts(root: Path) -> None:
    """A type-level @HttpExchange("/v1/inventory") that is also, itself, one
    of the mapping annotations — @HttpExchange's shape: it carries the
    prefix and, on a method, a mapping in its own right. Without the
    construct-kind guard the type-level use would mint a phantom endpoint of
    its own."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/inventory/InventoryClient.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    client = "com/acme/inventory/InventoryClient#"
    levels = "com/acme/inventory/InventoryClient#levels(sig_6b4f9e02)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=client, construct_kind=ConstructKind.INTERFACE),
        SymbolFact(
            document_id="doc_1",
            symbol=levels,
            construct_kind=ConstructKind.METHOD,
            enclosing=client,
            signature=Signature(parameters=[], returns=TypeRef(symbol="void")),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=client,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/inventory/annotation/Exchange#",
                args={"value": ["/v1/inventory"]},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=levels,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/inventory/annotation/GetExchange#",
                args={"value": ["/levels"]},
            ),
        ),
    ]
    write_fact_file(root / "InventoryClient.jsonl", document, facts)


_UNGATED_PREFIXED_CATALOG = Catalog(
    id="invented-ungated-prefixed",
    style="annotation_driven",
    protocol="http",
    direction="outbound",
    requires=("annotation_args",),
    source=Path("tests/invented.yml"),
    matches={
        "type_annotation": None,
        "mapping": {
            "path_from": ["value"],
            "prefix_from": ["value"],
            "peer_from": [],
            "method_from": "method",
            "all_methods": ["GET"],
            "prefix_annotation": "com.acme.inventory.annotation.Exchange",
            "annotations": [
                {"fqn": "com.acme.inventory.annotation.Exchange"},
                {"fqn": "com.acme.inventory.annotation.GetExchange", "method": ["GET"]},
            ],
        },
    },
)


def _ungated_prefixed_workspace(tmp_path):
    _inventory_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    skipped = derive_endpoints(
        workspace, [_UNGATED_PREFIXED_CATALOG], capabilities={"annotation_args"}
    )
    assert skipped == []
    return workspace


def test_a_type_level_mapping_annotation_mints_no_endpoint_of_its_own(tmp_path):
    """In a catalog with no type gate, a prefix-carrying type-level annotation
    that is also in the mapping list (@HttpExchange's shape) must contribute
    the prefix and nothing else — its type symbol is not a method, and without
    the construct-kind guard it would mint one phantom endpoint per method in
    all_methods (pre-flight ruling R2)."""
    workspace = _ungated_prefixed_workspace(tmp_path)
    rows = [e for e in workspace.query("endpoints") if e["direction"] == "outbound"]
    assert [(e["method"], e["path"]) for e in rows] == [("GET", "/v1/inventory/levels")]
    workspace.close()


_UNKNOWN_STYLE_CATALOG = """id: invented
style: protocol_hint
protocol: http
direction: inbound
matches: {}
"""

_VALID_CATALOG = """id: invented
style: annotation_driven
protocol: http
direction: inbound
matches: {}
"""


def _catalog_dir(root: Path, text: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "invented.yml").write_text(text, encoding="utf-8")
    return root


def test_load_catalogs_names_the_file_and_the_value_when_a_protocol_is_not_a_closed_set_member(
    tmp_path: Path,
):
    """`protocol` and `direction` are closed sets in D00: a value outside one
    is a typo, not a new kind of endpoint. Unchecked, it does not stay in the
    file — it is bound into the derivation and published in metadata.json,
    where it is indistinguishable from something observed. The message names
    the file and the value, because that is what a reader needs (GUIDELINES
    §9)."""
    directory = _catalog_dir(tmp_path, _VALID_CATALOG.replace("http", "htpp"))

    with pytest.raises(CatalogError) as failure:
        YamlCatalogSource(directory).load()

    assert "htpp" in str(failure.value)
    assert "invented.yml" in str(failure.value)
    assert "http" in str(failure.value)


def test_load_catalogs_rejects_a_direction_outside_the_closed_set(tmp_path: Path):
    directory = _catalog_dir(tmp_path, _VALID_CATALOG.replace("inbound", "incoming"))

    with pytest.raises(CatalogError) as failure:
        YamlCatalogSource(directory).load()

    assert "incoming" in str(failure.value)
    assert "invented.yml" in str(failure.value)


def test_load_catalogs_names_the_missing_field_when_a_catalog_omits_one(tmp_path: Path):
    directory = _catalog_dir(tmp_path, _VALID_CATALOG.replace("style: annotation_driven\n", ""))

    with pytest.raises(CatalogError) as failure:
        YamlCatalogSource(directory).load()

    assert "style" in str(failure.value)
    assert "invented.yml" in str(failure.value)


def test_load_catalogs_accepts_a_catalog_whose_values_are_all_in_the_closed_sets(
    tmp_path: Path,
):
    catalog = YamlCatalogSource(_catalog_dir(tmp_path, _VALID_CATALOG)).load()[0]
    assert (catalog.protocol, catalog.direction) == ("http", "inbound")


def test_broker_family_protocols_load_and_message_is_retired(tmp_path):
    """D00's protocol set names four broker families — `kafka`, `jms`, `sqs`,
    `pubsub` — in place of the single `message` value they retired, and a
    catalog declaring any of them loads. The single value could not have said
    which broker a row addressed, and D01's wire identity is protocol-scoped,
    so the four are the answer, not a convenience. Loading order is by
    filename (NFR-1), which is why the assertion is a list rather than a
    set."""
    _minimal_catalog = """id: {id}
style: annotation_driven
protocol: {protocol}
direction: inbound
matches: {{}}
"""
    tmp_path.mkdir(parents=True, exist_ok=True)
    for protocol in ("kafka", "jms", "sqs", "pubsub"):
        filename = f"x-{protocol}.yml"
        content = _minimal_catalog.format(id=filename.replace(".yml", ""), protocol=protocol)
        (tmp_path / filename).write_text(content, encoding="utf-8")

    loaded = YamlCatalogSource(tmp_path).load()
    assert [c.protocol for c in loaded] == ["jms", "kafka", "pubsub", "sqs"]


def test_the_http_adjacent_protocols_load(tmp_path):
    """2H design §1's closed-set line: D00's protocol set gains `graphql`,
    `websocket` and `sse`, declared once and used across the phase.

    All three are added together even though only `graphql` has a catalog in
    this task. The set is closed on purpose (NFR-5) — a value outside it is a
    typo, not a new kind of endpoint — so the cost of a member the phase has
    not reached yet is one enum line, while the cost of adding them one task
    at a time is three schema changes to the same closed set. Loading order is
    by filename (NFR-1), which is why the assertion is a list rather than a
    set."""
    _minimal_catalog = """id: {id}
style: annotation_driven
protocol: {protocol}
direction: inbound
matches: {{}}
"""
    tmp_path.mkdir(parents=True, exist_ok=True)
    for protocol in ("graphql", "websocket", "sse"):
        filename = f"x-{protocol}.yml"
        content = _minimal_catalog.format(id=filename.replace(".yml", ""), protocol=protocol)
        (tmp_path / filename).write_text(content, encoding="utf-8")

    loaded = YamlCatalogSource(tmp_path).load()
    assert [c.protocol for c in loaded] == ["graphql", "sse", "websocket"]


def test_message_is_no_longer_a_protocol(tmp_path):
    """The 'message' protocol value is rejected as a closed-set violation.

    MESSAGE was removed from the Protocol closed set in favor of specific
    broker family protocols. Any catalog declaring protocol: message should
    raise CatalogError with a message about closed sets.
    """
    catalog_text = _VALID_CATALOG.replace("http", "message")
    directory = _catalog_dir(tmp_path, catalog_text)

    with pytest.raises(CatalogError, match="closed"):
        YamlCatalogSource(directory).load()


def test_catalog_naming_a_style_with_no_engine_is_refused_by_file(tmp_path: Path):
    """A style with no engine matches nothing, so it would yield no endpoints
    and no skip — indistinguishable from a framework that exposes none. D02 §2
    declares six styles and this codebase implements four (2E-prep's
    `interface_implementation` joins the original three), so the gap is
    real.

    The reader cannot check it: which engines exist is knowledge of
    `application/resolve`, which `ingress` must not import. So the catalog
    loads and the engine layer refuses it, naming the file — which is what
    `Catalog.source` is carried for."""
    catalogs = YamlCatalogSource(_catalog_dir(tmp_path, _UNKNOWN_STYLE_CATALOG)).load()

    with pytest.raises(CatalogError) as raised:
        derive_endpoints(_UnusedWorkspace(), catalogs, capabilities=set())

    assert "protocol_hint" in str(raised.value)
    assert "annotation_driven" in str(raised.value)
    assert "invented.yml" in str(raised.value)


class _UnusedWorkspace:
    """Refusal comes before any derivation, so a workspace that fails on
    contact proves the catalog was rejected rather than partly run."""

    def load_facts(self, fact_root: Path) -> int:
        raise AssertionError("no fact load for a refused catalog")

    def derive(self, name: str, **params: object) -> None:
        raise AssertionError(f"no derivation for a refused catalog: {name}")

    def query(self, name: str, **params: object) -> list[dict[str, object]]:
        raise AssertionError(f"no query for a refused catalog: {name}")

    def close(self) -> None: ...
