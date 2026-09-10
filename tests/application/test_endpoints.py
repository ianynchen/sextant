import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from fixture_module import FIXTURE_CAPABILITIES, write_fixture_module_fact_with

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.endpoints import SkippedCatalog, derive_endpoints
from sextant.application.resolve.open_questions import reset_open_questions
from sextant.application.resolve.service_identity import record_service_identity_gaps
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
from sextant.domain.paths import canonical_http_path, serves_urls
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir
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


def test_the_loader_reads_detect_coordinates_and_the_framework_media_default():
    """Two keys D02 declared and the loader ignored until 2O Task 6
    (`docs/documented-not-implemented.md`, entries #1 and #6). `detect:` was
    declared by every shipped catalog and read by nothing; `default_produces`
    had been specified-not-used since 2E. Both are now values on the model,
    and `spring-data-rest` is the catalog that needs each."""
    catalogs = {catalog.id: catalog for catalog in YamlCatalogSource(CATALOGS).load()}

    data_rest = catalogs["spring-data-rest"]
    assert "org.springframework.boot:spring-boot-starter-data-rest" in data_rest.detect_coordinates
    assert data_rest.default_produces == ("application/hal+json",)
    # The three schema catalogs declare `coordinates: []` on purpose — their
    # evidence is a file in the repository, not a dependency — and an empty
    # tuple is what that says on the model.
    assert catalogs["graphql-schema"].detect_coordinates == ()
    # A catalog that declares no media default at all reads as none, never as
    # an invented one: an undeclared Spring mapping is negotiated at runtime.
    assert catalogs["spring-mvc"].default_produces == ()


def test_a_catalog_whose_detect_block_is_malformed_is_refused_by_file(tmp_path: Path):
    """The value reaches a comparison against the coordinates a module's build
    declared, and a coordinate in the wrong shape matches nothing while looking
    exactly like a framework that is absent."""
    catalog = tmp_path / "invented-detect.yml"
    catalog.write_text(
        "id: invented\nstyle: annotation_driven\nprotocol: http\ndirection: inbound\n"
        "detect:\n  coordinates: [org.springframework]\nmatches: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(CatalogError) as raised:
        YamlCatalogSource(tmp_path).load()

    assert "detect.coordinates" in str(raised.value)
    assert "invented-detect.yml" in str(raised.value)


def _catalog_naming(model: str, extra: str = "") -> str:
    return (
        "id: invented\nstyle: annotation_driven\nprotocol: http\ndirection: inbound\n"
        f"shape_model: {model}\nmatches: {{}}\n{extra}"
    )


def test_a_catalog_takes_the_shape_models_three_blocks(tmp_path: Path):
    """D02 §1b. The blocks reach `Catalog` exactly as they used to when the file
    declared them itself — the whole point of resolving the reference at the
    loader is that nothing downstream of this port learns the model exists."""
    (tmp_path / "shape-models").mkdir()
    (tmp_path / "shape-models" / "tiny.yml").write_text(
        "id: tiny\nserialization: {default_strategy: snake_case}\n"
        "nullability: {nullable: [com.acme.Nullable]}\n"
        "known_types:\n  - { type: com.acme.Money, wire: number }\n",
        encoding="utf-8",
    )
    (tmp_path / "invented-model-user.yml").write_text(_catalog_naming("tiny"), encoding="utf-8")

    [catalog] = YamlCatalogSource(tmp_path).load()

    assert catalog.serialization == {"default_strategy": "snake_case"}
    assert catalog.nullability == {"nullable": ["com.acme.Nullable"]}
    assert catalog.known_types == [{"type": "com.acme.Money", "wire": "number"}]


def test_a_catalog_naming_a_shape_model_that_does_not_ship_is_refused_by_file(tmp_path: Path):
    """A typo would silently strip the catalog of the serialisation,
    nullability and wire-type knowledge it believes it has — which is `A-C3`
    arriving through a misspelling instead of an omission."""
    (tmp_path / "invented-typo.yml").write_text(_catalog_naming("jsn"), encoding="utf-8")

    with pytest.raises(CatalogError) as raised:
        YamlCatalogSource(tmp_path).load()

    assert "shape_model" in str(raised.value)
    assert "invented-typo.yml" in str(raised.value)


def test_a_catalog_naming_a_model_and_declaring_a_block_beside_it_is_refused(tmp_path: Path):
    """The cheapest route back to forty-two copies is adding a block to a file
    that already references the model, and the two would then disagree with
    nothing to say which won. Refused at the edge, naming the file and the
    block."""
    (tmp_path / "shape-models").mkdir()
    (tmp_path / "shape-models" / "tiny.yml").write_text("id: tiny\n", encoding="utf-8")
    (tmp_path / "invented-both.yml").write_text(
        _catalog_naming("tiny", extra="known_types:\n  - { type: com.acme.Money, wire: string }\n"),
        encoding="utf-8",
    )

    with pytest.raises(CatalogError) as raised:
        YamlCatalogSource(tmp_path).load()

    assert "known_types" in str(raised.value)
    assert "invented-both.yml" in str(raised.value)


def test_a_catalog_declaring_no_model_and_no_block_still_loads(tmp_path: Path):
    """A repository's own catalog set (D02 §6) may ship no model at all, and
    thirteen shipped catalogs expand no shape and declare none of the three.
    Absence stays absence rather than becoming an error."""
    (tmp_path / "invented-bare.yml").write_text(
        "id: invented\nstyle: annotation_driven\nprotocol: http\ndirection: inbound\nmatches: {}\n",
        encoding="utf-8",
    )

    [catalog] = YamlCatalogSource(tmp_path).load()

    assert (catalog.serialization, catalog.nullability, catalog.known_types) == ({}, {}, [])


def test_catalog_declares_wrappers_nullability_serialization_and_known_types():
    """D02 §2a, §2e, §2f, §2g: `spring-web` and `spring-mvc` both need these
    four blocks before payload shapes can be derived (Tasks 9-11 read them).

    `wrappers` is still read off the raw file — it is the catalog's own, an
    envelope type belonging to the framework that defines it. The other three
    are read through the LOADER since F2 (D02 §1b): they come from
    `shape-models/json.yml` now, and reading the file for them would assert
    that a catalog holds a copy, which is exactly what F2 made impossible.
    """
    catalogs = {catalog.id: catalog for catalog in YamlCatalogSource(CATALOGS).load()}
    for name in ("spring-web", "spring-mvc"):
        raw = yaml.safe_load((CATALOGS / f"{name}.yml").read_text(encoding="utf-8"))
        catalog = catalogs[name]

        wrapper_types = {w["type"] for w in raw["wrappers"]}
        assert wrapper_types == {
            "org.springframework.http.ResponseEntity",
            "reactor.core.publisher.Mono",
            "reactor.core.publisher.Flux",
            "java.util.concurrent.CompletableFuture",
            "java.util.Optional",
            # 2H Task 6 (fix round 1): `ServerSentEvent<T>` is the per-EVENT
            # envelope an SSE stream carries, so the payload on that wire is
            # `T`. Without it `Flux<ServerSentEvent<OrderView>>` peeled its
            # outer `Flux` and published the envelope TYPE as the contract.
            "org.springframework.http.codec.ServerSentEvent",
        }

        # The JetBrains entries are not redundant with JSpecify/Spring: the
        # Kotlin compiler emits them directly onto fields as CLASS-retention
        # annotations, so they are what makes Kotlin nullability work through
        # the ordinary annotation path.
        assert "org.jetbrains.annotations.Nullable" in catalog.nullability["nullable"]
        assert "org.jetbrains.annotations.NotNull" in catalog.nullability["not_null"]
        # Both spellings of the FIELD rule, and only those (OI-48). JSpecify's was
        # declared alone, and Spring is the framework this reads most: 58
        # `package-info` classes in spring-web 6.1.6 carry Spring's, and
        # `HttpHeaders` declares 68 fields of which zero carry an annotation of
        # their own — a scope exists so that only the exceptions are marked.
        #
        # `@NonNullApi` is deliberately NOT here. Spring scopes parameters and
        # return values with it and fields with `@NonNullFields`, and this scope
        # is applied to field symbols and to nothing else. Measured over 1,672
        # cached jars: all 613 packages declaring `@NonNullFields` also declare
        # `@NonNullApi`, so listing it added no field scope anywhere, while 197
        # packages declare it ALONE and had every field wrongly resolved not-null.
        assert catalog.nullability["scope"] == [
            {"annotation": "org.jspecify.annotations.NullMarked", "means": "not_null_by_default"},
            {
                "annotation": "org.springframework.lang.NonNullFields",
                "means": "not_null_by_default",
            },
        ]

        assert catalog.serialization["name_from"] == [
            {"annotation": "com.fasterxml.jackson.annotation.JsonProperty", "arg": "value"}
        ]
        assert catalog.serialization["ignore"] == ["com.fasterxml.jackson.annotation.JsonIgnore"]
        assert catalog.serialization["default_strategy"] == "as_declared"

        # The four serialiser mappings these two catalogs used to declare, plus
        # the boxes the shared model also carries — which reached these two for
        # the first time with F2, and are the union rather than a new claim:
        # every one of them mirrors `WireTypes.objectLike`'s own projection
        # (`test_known_types_mirror_the_projection.py`), so they answer for a
        # bare `String.class` symbol and change no scanned field's reading.
        known_types = {t["type"] for t in catalog.known_types}
        assert known_types == {
            "java.time.Instant",
            "java.time.LocalDate",
            "java.math.BigDecimal",
            "java.util.UUID",
            "java.lang.String",
            "java.lang.Boolean",
            "java.lang.Byte",
            "java.lang.Short",
            "java.lang.Integer",
            "java.lang.Long",
            "java.lang.Character",
            "java.lang.Float",
            "java.lang.Double",
            "java.lang.Void",
        }


def test_every_catalog_carrying_the_reactive_wrapper_family_carries_it_verbatim():
    """The Spring/reactive `wrappers` family is duplicated VERBATIM by
    contract, and until now nothing enforced it (2H Task 6, fix round 1 — the
    `ServerSentEvent` entry is the second thing that has to be kept in step
    across six files).

    `spring-graphql.yml`'s own comment states the stakes: shape expansion is a
    GLOBAL, insert-if-absent pass keyed on the type symbol alone, so the first
    catalog to reach a shared payload type is the one that describes it for
    everyone — and these files are read in filename order. A copy that
    disagreed would not be a cosmetic difference; it would silently change what
    the OTHER catalogs' endpoints publish, depending only on which file sorts
    first.

    Scoped by MEMBERSHIP, not by a filename list: a catalog belongs to this
    family exactly when it declares the family's own marker entry, so a seventh
    catalog copying the block in is covered the day it is written. Catalogs
    with wrappers of their own and no reactive family — `retrofit.yml`'s
    `Call`, for one — are a different vocabulary and are correctly excluded."""
    marker = "reactor.core.publisher.Flux"
    blocks = {}
    for path in sorted(CATALOGS.glob("*.yml")):
        declared = yaml.safe_load(path.read_text(encoding="utf-8")).get("wrappers") or []
        if any(wrapper["type"] == marker for wrapper in declared):
            blocks[path.name] = declared

    assert len(blocks) > 1, "the pin is vacuous unless more than one catalog carries the family"
    assert len({json.dumps(block, sort_keys=True) for block in blocks.values()}) == 1, (
        f"catalogs disagree about the reactive `wrappers` family: {sorted(blocks)}"
    )


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

    All FOUR declare it, not one: the ladder unions the blocks across
    catalogs, so a module pulling in only DGS must still get the answer. The
    entries are identical by construction and a contradiction between two
    would be refused rather than resolved, which is what keeps four copies
    from drifting silently — the same rule `media_formats` already lives
    under on `spring-web.yml`/`spring-mvc.yml`.

    `graphql-schema` (2H Task 4) is the fourth, and the one that makes the
    rule bite rather than repeat: a schema-first module pulls in NONE of the
    three annotation libraries, so without its own copy its rows would reach
    rung 1 with nothing declared and fall to rung 4, where the declared
    shape's own `schema_format` would stamp `graphql` — a value D00's format
    set does not contain — into the column. It is also the only one of the
    four that is not `annotation_driven`: a schema belongs to no framework."""
    catalogs = YamlCatalogSource(CATALOGS).load()
    graphql = [c for c in catalogs if c.protocol == "graphql"]

    assert {c.id for c in graphql} == {
        "spring-graphql",
        "netflix-dgs",
        "microprofile-graphql",
        "graphql-schema",
    }
    assert all(c.format_fixed == {"graphql": "json"} for c in graphql)
    assert all(c.direction == "inbound" for c in graphql)
    assert {c.style for c in graphql} == {"annotation_driven", "schema_operations"}
    assert next(c for c in graphql if c.style == "schema_operations").id == "graphql-schema"


def test_every_soap_catalog_declares_the_protocols_fixed_format():
    """2G design §7, rung 1's SECOND live protocol (2I design §1), and the
    same rule the graphql test above pins: all FIVE catalogs owning `soap`
    declare the identical `format_fixed: {soap: xml}` entry, not one — the
    ladder unions the blocks across catalogs, so a module pulling in only
    `wsdl-schema` (no `@Endpoint`/`@WebService` annotation anywhere) must
    still get the answer, the same way a schema-first GraphQL module does.

    `wsdl-schema` (2I Task 4) is the third, and — like `graphql-schema`
    before it — the only one of the five that is not `annotation_driven` or
    `single_call`: a schema belongs to no framework, and without its own copy
    its rows would reach rung 1 with nothing declared and fall through with no
    rung to answer `xml` at all (its rows carry no bytecode type for rung 4 or
    rung 5 to read).

    2I Task 5 adds the two OUTBOUND ones — the protocol's first — and the
    direction assertion below splits accordingly. Each is a separate file
    rather than a block on its inbound twin because a catalog declares exactly
    one style and one direction (`yaml_source.py`), the registry constraint
    `graphql-schema.yml` proved and `wsdl-schema.yml` restated this phase."""
    catalogs = YamlCatalogSource(CATALOGS).load()
    soap = [c for c in catalogs if c.protocol == "soap"]

    assert {c.id for c in soap} == {
        "spring-ws",
        "jakarta-jws",
        "wsdl-schema",
        "spring-ws-template",
        "jakarta-jws-client",
    }
    assert all(c.format_fixed == {"soap": "xml"} for c in soap)
    assert {c.id for c in soap if c.direction == "outbound"} == {
        "spring-ws-template",
        "jakarta-jws-client",
    }
    assert all(c.direction == "inbound" for c in soap if c.direction != "outbound")
    assert {c.style for c in soap} == {
        "annotation_driven",
        "schema_operations",
        "single_call",
    }
    assert next(c for c in soap if c.style == "schema_operations").id == "wsdl-schema"


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
        fact_schema_version=2,
        scanner_id="asm",
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
        fact_schema_version=2,
        scanner_id="asm",
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
        fact_schema_version=2,
        scanner_id="asm",
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

    The two declarations that name nothing derive NO ROW here, and the set
    below is exactly the two that do. That is the addresses-nothing gate
    rather than the naming vocabulary: an absent attribute still defaults to
    `''`, and a row whose whole composed address is empty — with no peer
    naming an endpoint either — is an endpoint addressing nothing, so it is
    dropped instead of published. Before the gate, this same set carried a
    third member, the bare `''`. The next test shows the other route out —
    `path_fallback`, which gives such a declaration a real name instead of
    dropping it.
    """
    assert _paths_of(tmp_path, _naming_forms_catalog()) == {"named", "member"}


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


@pytest.mark.pins("derive_endpoints.qualifier-scope")
def test_a_scoped_annotation_with_no_scope_anywhere_derives_no_row_at_all(
    tmp_path: Path,
):
    """`requires_qualifier` — the rule that keeps a missing scope silent
    instead of wrong.

    It names the qualifier-scope guard, which the `spring-rabbit` near-miss
    used to name and does not reach — `spring-rabbit.yml` declares no
    `requires_qualifier` at all, so the conjunct is a no-op for that catalog.
    This input reaches it: `named` and `defaulted` would each publish a bare
    member name the moment the conjunct is relaxed, and `Parent.member` in the
    same assertion is the paired positive that stops this passing because the
    rule matched nothing.

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


@pytest.mark.parametrize(
    "separator",
    [
        # A YAML integer: truthy, so it passed the old `if not separator`
        # check outright — nothing downstream of that ever looked at its
        # type or length.
        5,
        # A YAML boolean: also truthy, same gap.
        True,
        # An explicitly empty string. Passes an `is None` check but is
        # falsy, so this one was already refused before this change — kept
        # here so the whole vocabulary of wrong shapes is pinned by one
        # parametrize rather than split across two tests.
        "",
        # Two characters: `qualifier_separator` composes with `||`, a single
        # piece of punctuation between a scope and the name it qualifies —
        # not a set of characters to dedupe, so nothing here would even
        # partially compensate for the extra character the way `path_separator`'s
        # `rtrim`/`ltrim` does.
        "..",
    ],
)
def test_a_non_single_character_qualifier_separator_is_refused_by_type_and_length(
    tmp_path: Path, separator: object
):
    """`qualifier_separator` must be a STRING of exactly one character, the
    same contract `path_separator` is held to. A truthy but wrong-typed
    value (an int, a bool) used to pass the bare `if not separator` check
    with nothing checking its shape; a multi-character string was never
    checked at all."""
    with pytest.raises(CatalogError) as raised:
        _paths_of(
            tmp_path,
            _naming_forms_catalog(
                path_fallback="construct_name",
                qualifier_from=["scope"],
                qualifier_separator=separator,
            ),
        )

    assert "qualifier_separator" in str(raised.value)
    assert "invented-naming.yml" in str(raised.value)


# --- the 2026-09-06 vocabulary pass, on an invented framework -------------
#
# Three words, three measurements, one style shared by twenty-one catalogs.
# Deliberately NOT spelled with `@KafkaListener` or `@Query`, the discipline
# every mechanism test in this file keeps: `container`, `path_from_siblings`
# and the per-annotation `path_fallback` are ENGINE vocabulary, and a test
# written against a shipped file would pin a framework rather than a mechanism
# — and would pass or fail because somebody edited YAML.
#
# The invented framework below is the shape all three measurements share and
# that the vocabulary could not express before: an annotation that may be
# written twice on one declaration (so javac folds it into a container and the
# class file carries no annotation at all), a name that may live on a SIBLING
# annotation rather than on the matched one, and two annotations of one family
# whose un-named fallback strips OPPOSITE accessor prefixes.

_ON_EVENT = "com/acme/messaging/annotation/OnEvent#"
_ON_EVENTS = "com/acme/messaging/annotation/OnEvents#"
_ON_ACTION = "com/acme/messaging/annotation/OnAction#"
_ALIAS = "com/acme/messaging/annotation/Alias#"
_LATE_ALIAS = "com/acme/messaging/annotation/LateAlias#"


def _vocabulary_catalog(**mapping: object) -> Catalog:
    """A gateless catalog over the invented annotations above, with whatever
    the pass's vocabulary a test layers on. Two mapping annotations, because
    every one of the three words is about a difference BETWEEN annotations of
    one family."""
    return Catalog(
        id="invented-vocabulary",
        style="annotation_driven",
        protocol="kafka",
        direction="inbound",
        requires=("annotation_args", "nested_annotation_args"),
        source=Path("tests/invented-vocabulary.yml"),
        matches={
            "mapping": {
                "path_from": ["value"],
                "prefix_from": [],
                "method_from": "method",
                "all_methods": [],
                "prefix_annotation": None,
                "annotations": [
                    {"fqn": "com.acme.messaging.annotation.OnEvent"},
                    {"fqn": "com.acme.messaging.annotation.OnAction"},
                ],
                **mapping,
            }
        },
    )


def _vocabulary_facts(root: Path) -> None:
    """One class and five declarations, each the smallest input that separates
    one of the three words from the behaviour it replaces.

    `folded` is the shape javac writes for TWO uses of one repeatable
    annotation (JLS 9.7.5): a single CONTAINER whose `value` is an array of
    annotations, and NO `@OnMessage` fact of its own. `misfolded` is the same
    container holding an annotation the catalog never named — the near-miss for
    the conjunct that stops any array-valued annotation contributing
    destinations.
    """
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/notify/Vocabulary.java",
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
    owner = "com/acme/notify/Vocabulary#"
    folded_uses = [
        AnnotationUse(annotation=_ON_EVENT, args={"value": ["orders.first"]}),
        AnnotationUse(annotation=_ON_EVENT, args={"value": ["orders.second"]}),
    ]
    declarations: dict[str, list[tuple[str, dict[str, object]]]] = {
        # An un-named declaration on each of the two mapping annotations,
        # named so the accessor strip has something to bite on — and named
        # ACROSS the two directions, so a rule that is right for one and wrong
        # for the other cannot pass.
        "getOrders": [(_ON_EVENT, {})],
        "setStatus": [(_ON_ACTION, {})],
        # Two sibling name sources present at once: the ORDER decides.
        "renamed": [
            (_ON_EVENT, {}),
            (_ALIAS, {"value": "by-alias"}),
            (_LATE_ALIAS, {"value": "by-late-alias"}),
        ],
        # Its own name AND a sibling carrying another: the matched annotation
        # wins, which is the order CP-15 row 1 measured.
        "selfNamed": [(_ON_EVENT, {"value": ["own-name"]}), (_ALIAS, {"value": "by-alias"})],
        # The container, and a container of something else.
        "folded": [(_ON_EVENTS, {"value": folded_uses})],
        "misfolded": [
            (_ON_EVENTS, {"value": [AnnotationUse(annotation=_ALIAS, args={"value": ["nope"]})]})
        ],
    }
    facts: list[object] = [
        SymbolFact(document_id="doc_1", symbol=owner, construct_kind=ConstructKind.CLASS)
    ]
    for name, uses in declarations.items():
        symbol = f"{owner}{name}(sig_3d92af60)."
        facts.append(
            SymbolFact(
                document_id="doc_1",
                symbol=symbol,
                construct_kind=ConstructKind.METHOD,
                enclosing=owner,
            )
        )
        facts.extend(
            AnnotationFact(
                document_id="doc_1",
                target=symbol,
                retention="runtime",
                use=AnnotationUse(annotation=annotation, args=args),
            )
            for annotation, args in uses
        )
    write_fact_file(root / "Vocabulary.jsonl", document, facts)


def _vocabulary_paths(tmp_path: Path, catalog: Catalog) -> set[str]:
    _vocabulary_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    derive_endpoints(
        workspace, [catalog], capabilities={"annotation_args", "nested_annotation_args"}
    )
    paths = {str(row["path"]) for row in workspace.query("endpoints")}
    workspace.close()
    return paths


def test_a_catalog_declaring_none_of_the_pass_words_derives_exactly_what_it_always_did(
    tmp_path: Path,
):
    """The inertness pin for all three words at once.

    Only the declaration that spells its own name derives anything: the two
    accessor declarations and the sibling one carry the annotation with no
    `value`, and the two container declarations carry no mapping annotation at
    all. So four of the five derive NOTHING — the addresses-nothing gate,
    exactly as before this pass — and every row the tests below assert is one
    this vocabulary ADDS rather than one it moves."""
    assert _vocabulary_paths(tmp_path, _vocabulary_catalog()) == {"own-name"}


@pytest.mark.pins("annotation_driven.folded-uses-are-read")
def test_two_uses_of_one_annotation_on_one_declaration_derive_both_destinations(
    tmp_path: Path,
):
    """`OI-36`, measured by CP-16 at six versions across three frameworks.

    javac writes the CONTAINER and not the annotation (JLS 9.7.5), so before
    this word the mapping join matched nothing and BOTH destinations vanished —
    silently, beside a single-use neighbour deriving normally. That is a
    silent under-report, the second sin and the harder of the two to notice,
    because the row is absent rather than wrong.

    Both are asserted, not one: reading only the first entry of the array would
    be a plausible half-fix that this exact input catches."""
    paths = _vocabulary_paths(
        tmp_path,
        _vocabulary_catalog(
            annotations=[
                {
                    "fqn": "com.acme.messaging.annotation.OnEvent",
                    "container": "com.acme.messaging.annotation.OnEvents",
                },
                {"fqn": "com.acme.messaging.annotation.OnAction"},
            ]
        ),
    )

    assert paths == {"orders.first", "orders.second", "own-name"}


@pytest.mark.pins("annotation_driven.folded-entry-is-the-declared-annotation")
def test_a_container_holding_some_other_annotation_contributes_no_destination(
    tmp_path: Path,
):
    """§10 near-miss on the conjunct that makes the container read safe.

    Every other condition holds: the catalog declares this container, the fact
    is present on a method, its `value` IS an array of annotations, and each
    entry carries a readable `value` that would compose a perfectly plausible
    destination. The one thing that is false is that the folded annotation is
    the one the catalog named.

    A container is an ordinary annotation whose `value` happens to be an array,
    so without this conjunct ANY array-of-annotations argument contributes
    destinations — `misfolded` would publish `nope`, an address nothing serves,
    at `resolved`/`compiler` where nothing downstream can tell it from an
    observation.
    """
    paths = _vocabulary_paths(
        tmp_path,
        _vocabulary_catalog(
            annotations=[
                {
                    "fqn": "com.acme.messaging.annotation.OnEvent",
                    "container": "com.acme.messaging.annotation.OnEvents",
                },
            ]
        ),
    )

    assert "nope" not in paths
    assert paths == {"orders.first", "orders.second", "own-name"}


@pytest.mark.pins("derive_endpoints.sibling-name-source-order")
def test_the_first_sibling_source_in_the_declared_order_supplies_the_name(
    tmp_path: Path,
):
    """`OI-35`, measured by CP-15 rows 1-2: the framework builds an array of
    name sources whose indices ARE the order and takes the FIRST with a value.

    `renamed` carries both sibling annotations at once, which is the only input
    that can tell an ordered list from a set — and a set is what the vocabulary
    had, which is why the register's close condition says "with the ORDER
    preserved". Reversing the two entries below reverses the answer, which is
    what the second assertion says."""
    mapping: dict[str, object] = {
        "path_from_siblings": [
            {"annotation": "com.acme.messaging.annotation.Alias", "arg": "value"},
            {"annotation": "com.acme.messaging.annotation.LateAlias", "arg": "value"},
        ]
    }
    assert _vocabulary_paths(tmp_path, _vocabulary_catalog(**mapping)) == {
        "by-alias",
        "own-name",
    }


def test_reversing_the_sibling_sources_reverses_which_one_names_the_declaration(
    tmp_path: Path,
):
    """The paired positive for the ordering above (§10's "a near-miss needs a
    positive PAIRED with it"): the answer follows the catalog's order rather
    than some incidental order of the facts, the annotations' own names, or
    whichever the query happened to read first."""
    mapping: dict[str, object] = {
        "path_from_siblings": [
            {"annotation": "com.acme.messaging.annotation.LateAlias", "arg": "value"},
            {"annotation": "com.acme.messaging.annotation.Alias", "arg": "value"},
        ]
    }
    assert _vocabulary_paths(tmp_path, _vocabulary_catalog(**mapping)) == {
        "by-late-alias",
        "own-name",
    }


def test_the_matched_annotations_own_alias_still_wins_over_every_sibling(
    tmp_path: Path,
):
    """CP-15 row 1 puts the operation annotation's own `value` at index 0 of
    the source array, ahead of all four siblings — so the sibling list is
    consulted only where every `path_from` alias was absent, and this is that
    order asserted rather than assumed.

    `selfNamed` declares its own name AND carries a sibling naming another; the
    name it declares is the one served, and `by-alias` appears only because
    `renamed` — which names nothing of its own — takes it."""
    paths = _vocabulary_paths(
        tmp_path,
        _vocabulary_catalog(
            path_from_siblings=[
                {"annotation": "com.acme.messaging.annotation.Alias", "arg": "value"}
            ]
        ),
    )

    assert paths == {"own-name", "by-alias"}


@pytest.mark.pins("derive_endpoints.path-fallback-is-per-annotation")
def test_two_annotations_of_one_family_fall_back_under_opposite_accessor_rules(
    tmp_path: Path,
):
    """`OI-5`, measured by CP-15 rows 3-5 with row 5 COMPILED AND RUN.

    The framework's un-named-operation fallback is direction-dependent and the
    direction is chosen by WHICH annotation matched: one strips `get`/`is`, the
    other strips `set`. `mapping.path_fallback` was one catalog-level word, so
    every single word made one of the two newly wrong — which is why `OI-5`
    shipped a measured-and-wrong address rather than a plausible fix.

    Both directions in one assertion, and each with the OTHER direction's
    accessor visible in the same class: `getOrders` must not be touched by the
    write rule and `setStatus` must not be touched by the read rule. A single
    shared word cannot produce this set."""
    paths = _vocabulary_paths(
        tmp_path,
        _vocabulary_catalog(
            path_fallback="construct_name",
            annotations=[
                {
                    "fqn": "com.acme.messaging.annotation.OnEvent",
                    "path_fallback": "read_accessor_property",
                },
                {
                    "fqn": "com.acme.messaging.annotation.OnAction",
                    "path_fallback": "write_accessor_property",
                },
            ],
        ),
    )

    # `renamed` takes the catalog-level default, which strips nothing — the
    # inertness of the per-annotation word where no entry declares one.
    assert paths == {"orders", "status", "renamed", "own-name"}


@pytest.mark.parametrize(
    ("name", "read_rule", "write_rule"),
    [
        # CP-15 row 5, verbatim, both columns. Each row is an edge of the
        # measured rule rather than an illustration of it.
        ("getOrders", "orders", "getOrders"),
        ("isActive", "active", "isActive"),
        ("setStatus", "setStatus", "status"),
        ("orders", "orders", "orders"),
        ("createOrder", "createOrder", "createOrder"),
        ("getX", "x", "getX"),
        # The LENGTH test: a name that is exactly the prefix is not an accessor.
        ("get", "get", "get"),
        # The SEAM test: no capital where the property name would start.
        ("gettotal", "gettotal", "gettotal"),
        # The case that tells "lowercase the remainder" from "lowercase its
        # FIRST CHARACTER" — and it is the second. Any encoding of this rule
        # that does not reproduce `uRL` is not this rule.
        ("getURL", "uRL", "getURL"),
    ],
)
@pytest.mark.pins("derive_endpoints.accessor-strip-is-the-measured-one")
def test_the_accessor_strip_reproduces_every_measured_edge(
    tmp_path: Path, name: str, read_rule: str, write_rule: str
):
    """CP-15 row 5's own table, run through this engine.

    The probe compiled `MethodHelper.getPropertyName` against
    smallrye-graphql-schema-builder 2.0.0 and 2.18.5 and RAN it; these are the
    strings that process printed. A table of names could agree with several
    rules, which is why the three edges — too short, no capital at the seam,
    and `getURL` — are each their own row here rather than being represented by
    `getOrders` alone."""
    _accessor_facts(tmp_path / "facts", name)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    derive_endpoints(
        workspace,
        [
            _vocabulary_catalog(
                annotations=[
                    {
                        "fqn": "com.acme.messaging.annotation.OnEvent",
                        "path_fallback": "read_accessor_property",
                    },
                    {
                        "fqn": "com.acme.messaging.annotation.OnAction",
                        "path_fallback": "write_accessor_property",
                    },
                ]
            )
        ],
        capabilities={"annotation_args", "nested_annotation_args"},
    )
    rows = {(str(row["path"])) for row in workspace.query("endpoints")}
    workspace.close()

    assert rows == {read_rule, write_rule}


def _accessor_facts(root: Path, name: str) -> None:
    """One method name, declared twice — once under each of the two mapping
    annotations, on two classes so the two rows cannot merge into one wire
    identity when the two rules agree."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/notify/Accessors.java",
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
    facts: list[object] = []
    for owner, annotation in (
        ("com/acme/notify/Reads#", _ON_EVENT),
        ("com/acme/notify/Writes#", _ON_ACTION),
    ):
        symbol = f"{owner}{name}(sig_3d92af60)."
        facts.append(
            SymbolFact(document_id="doc_1", symbol=owner, construct_kind=ConstructKind.CLASS)
        )
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
                use=AnnotationUse(annotation=annotation, args={}),
            )
        )
    write_fact_file(root / "Accessors.jsonl", document, facts)


@pytest.mark.parametrize(
    "declared",
    [
        # An unrecognised word, which read as "no fallback" restores the empty
        # address the form exists to remove.
        {"fqn": "com.acme.messaging.annotation.OnEvent", "path_fallback": "parameter_name"},
        # A container that is not a string at all.
        {"fqn": "com.acme.messaging.annotation.OnEvent", "container": 5},
        # An EMPTY container, which would match no annotation and silently
        # restore the under-report the key exists to close.
        {"fqn": "com.acme.messaging.annotation.OnEvent", "container": ""},
    ],
)
def test_a_malformed_annotation_entry_word_is_refused_by_file(
    tmp_path: Path, declared: dict[str, object]
):
    """NFR-5, one level down from `mapping`. Both new entry-level words are
    refused rather than read as absent, and the direction of the danger is
    what makes that the right choice: an unread `path_fallback` publishes the
    method's own name where the framework serves a stripped one, and an unread
    `container` drops both destinations of a two-use declaration while its
    single-use neighbour derives normally."""
    with pytest.raises(CatalogError) as raised:
        _vocabulary_paths(tmp_path, _vocabulary_catalog(annotations=[declared]))

    assert "invented-vocabulary.yml" in str(raised.value)


@pytest.mark.parametrize(
    "declared",
    [
        # An empty list: a key declared and saying nothing, which reads as
        # "consult these" while consulting none.
        [],
        # A bare string where a `{annotation, arg}` pair belongs — the shape
        # `path_from` takes, written in the key that does not take it.
        ["value"],
        # A pair naming an annotation and no attribute of it.
        [{"annotation": "com.acme.messaging.annotation.Alias"}],
        # A third key: the shape is closed, so a misspelling cannot pass for
        # one of the two.
        [{"annotation": "com.acme.messaging.annotation.Alias", "arg": "value", "of": "x"}],
    ],
)
def test_a_malformed_sibling_name_source_is_refused_by_file(tmp_path: Path, declared: object):
    """NFR-5 again, and the same asymmetry: a `path_from_siblings` read as
    absent leaves the operation published under a name the framework does not
    serve it at — a wrong address, which is the failure the key exists to
    remove, restored silently by a typo."""
    with pytest.raises(CatalogError) as raised:
        _vocabulary_paths(tmp_path, _vocabulary_catalog(path_from_siblings=declared))

    assert "path_from_siblings" in str(raised.value)
    assert "invented-vocabulary.yml" in str(raised.value)


# --- 2I design §2: the two QName forms, on an invented framework ----------
#
# Deliberately NOT Spring-WS and NOT JAX-WS, for the reason the 2H forms above
# are not GraphQL: `qualifier_format` and `namespace_default` are engine
# vocabulary, and a test spelled with `@PayloadRoot` or `@WebService` in it
# would pin a framework rather than a mechanism.
#
# The invented framework below is the shape both SOAP families share and that
# 2H's `qualifier_separator` cannot express: a scope and a name that compose
# into ONE bracketed token (`{scope}name`) rather than two halves joined by a
# separator, and a scope whose ABSENCE has a spec-defined derivation rather
# than meaning "no scope". The type-level annotation and the method-level one
# are deliberately DIFFERENT fqns here — unlike `_naming_forms_catalog`'s
# single annotation playing both roles — because the real catalogs need the
# scope read off an annotation named in `mapping.annotations` alongside the
# one carrying the name (that list being what lets a catalog name two
# spellings of the same gate at once; checkpoint item 4).


def _qname_catalog(**mapping: object) -> Catalog:
    """A gateless catalog over the invented annotations below, with whatever
    QName vocabulary a test layers on."""
    return Catalog(
        id="invented-qname",
        style="annotation_driven",
        protocol="soap",
        direction="inbound",
        requires=("annotation_args",),
        source=Path("tests/invented-qname.yml"),
        matches={
            "mapping": {
                "path_from": ["op"],
                "prefix_from": [],
                "method_from": "method",
                "all_methods": [],
                "prefix_annotation": None,
                "annotations": [
                    {"fqn": "com.acme.rpc.annotation.Service"},
                    {"fqn": "com.acme.rpc.annotation.Operation"},
                ],
                **mapping,
            }
        },
    )


def _qname_facts(
    root: Path,
    owner: str = "com/acme/rpc/OrderService#",
    namespace: str | None = None,
    scope_annotated: bool = True,
) -> None:
    """One method that always spells its own name, on a type that carries the
    scope annotation in one of the three shapes checkpoint item 4 tells apart.

    `scope_annotated` false means the annotation is ABSENT from the type
    altogether; true with `namespace` None means it is PRESENT with the
    attribute absent — which is the only shape a bytecode-defaulted attribute
    can take, since a declared default is never written into the class file.
    `owner` carries the package the reversed-package derivation reads, and is
    a parameter so a class in the DEFAULT package can be spelled.
    """
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/rpc/OrderService.java",
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
    place = f"{owner}place(sig_3d92af60)."
    facts: list[object] = [
        SymbolFact(document_id="doc_1", symbol=owner, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=place,
            construct_kind=ConstructKind.METHOD,
            enclosing=owner,
        ),
        AnnotationFact(
            document_id="doc_1",
            target=place,
            retention="runtime",
            # A SCALAR, not an array: checkpoint items 4 and 5 pin both SOAP
            # families' name attributes as plain strings in bytecode, unlike
            # every Spring mapping annotation's `String[]`.
            use=AnnotationUse(
                annotation="com/acme/rpc/annotation/Operation#", args={"op": "placeRequest"}
            ),
        ),
    ]
    if scope_annotated:
        facts.append(
            AnnotationFact(
                document_id="doc_1",
                target=owner,
                retention="runtime",
                use=AnnotationUse(
                    annotation="com/acme/rpc/annotation/Service#",
                    args={} if namespace is None else {"ns": namespace},
                ),
            )
        )
    write_fact_file(root / "OrderService.jsonl", document, facts)


def _qname_paths(tmp_path: Path, catalog: Catalog, **facts: object) -> set[str]:
    _qname_facts(tmp_path / "facts", **facts)  # type: ignore[arg-type]
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    derive_endpoints(workspace, [catalog], capabilities={"annotation_args"})
    paths = {str(row["path"]) for row in workspace.query("endpoints")}
    workspace.close()
    return paths


def _qname_mapping(**mapping: object) -> dict[str, object]:
    """The vocabulary every derivation test below shares: the scope read off
    the type's own attribute, composed as a QName in front of the name."""
    return {
        "path_fallback": "construct_name",
        "qualifier_from": ["ns"],
        "qualifier_format": "qname",
        **mapping,
    }


def test_a_qname_format_brackets_the_scope_in_front_of_the_name_it_qualifies(
    tmp_path: Path,
):
    """Word 1. `{namespace}localName` is ONE token, not two halves joined by
    punctuation: the braces are part of the notation, and the closing one has
    no separator equivalent at all. That is why it is a `qualifier_format`
    word rather than a two-character `qualifier_separator` — which
    `_validate_naming` refuses outright, and rightly, since `rtrim`-style
    dedupe over a `{`/`}` pair would compose a name nobody serves.
    """
    paths = _qname_paths(
        tmp_path,
        _qname_catalog(**_qname_mapping()),
        namespace="http://declared.example.com/ws",
    )

    assert paths == {"{http://declared.example.com/ws}placeRequest"}


def test_an_absent_scope_attribute_falls_back_to_the_reversed_package(tmp_path: Path):
    """Word 2, composing with word 1.

    The derivation is pinned to what JAX-WS actually computes (checkpoint item
    2, verified against BOTH `com.sun.xml.ws.model.RuntimeModeler#getNamespace`
    and Apache CXF's independent `PackageUtils#getNamespace`): `"http://"` +
    the package's dot-separated tokens REVERSED + a trailing `"/"`. The
    trailing slash is not decoration — it is in both implementations
    unconditionally, and an address missing it matches no caller.

    `com/acme/rpc` is deliberately not the namespace the test above declares:
    a derivation that silently fell through to the declared value, or an
    assertion that could not tell the two apart, would pass a wrong engine.
    """
    paths = _qname_paths(
        tmp_path,
        _qname_catalog(**_qname_mapping(namespace_default="reversed_package")),
        namespace=None,
    )

    assert paths == {"{http://rpc.acme.com/}placeRequest"}


def test_a_declared_scope_still_wins_over_the_reversed_package_default(tmp_path: Path):
    """The default fires on ABSENCE only, never as a rewrite of something
    declared — the rule `path_fallback` already keeps for names, restated for
    scopes because the two forms now compose."""
    paths = _qname_paths(
        tmp_path,
        _qname_catalog(**_qname_mapping(namespace_default="reversed_package")),
        namespace="http://declared.example.com/ws",
    )

    assert paths == {"{http://declared.example.com/ws}placeRequest"}


def test_an_absent_scope_with_no_default_declared_invents_no_namespace(tmp_path: Path):
    """The inertness pin for word 2, and the one that matters most: a catalog
    that declares no `namespace_default` must derive the BARE name rather than
    a namespace the engine picked. A guessed namespace would be published at
    `resolved`/`compiler`, where nothing downstream can tell it from an
    observation — the confidently-wrong-address class again, and the reason
    DR-6's answer to "the framework's default is unknown" is refusal rather
    than a plausible-looking string.
    """
    paths = _qname_paths(tmp_path, _qname_catalog(**_qname_mapping()), namespace=None)

    assert paths == {"placeRequest"}


def test_an_operation_needing_a_scope_with_none_derivable_derives_no_row(tmp_path: Path):
    """`requires_qualifier` composing with word 2: where the annotation only
    means anything inside a namespace and no namespace is declared OR
    derivable, silence is the honest answer — the bare local name would read
    as a top-level identity, which is a different endpoint from the one the
    code declares."""
    paths = _qname_paths(
        tmp_path,
        _qname_catalog(
            **_qname_mapping(
                annotations=[
                    {"fqn": "com.acme.rpc.annotation.Service"},
                    {"fqn": "com.acme.rpc.annotation.Operation", "requires_qualifier": True},
                ]
            )
        ),
        namespace=None,
    )

    assert paths == set()


def test_the_reversed_package_default_needs_the_scope_annotation_to_be_present(
    tmp_path: Path,
):
    """The default belongs to an ATTRIBUTE of a declared annotation, so the
    annotation has to be there. A type carrying no scope annotation at all is
    not a service with a defaulted namespace — it is not a service — and
    deriving its package's namespace anyway would mint an endpoint for any
    class that merely happens to hold a matching method.

    This is what lets a catalog whose gate is expressed as a qualifier scope
    still gate: no scope row, no default, no address. (A qualifier scope used to
    be the ONLY way to name two spellings of one gate, because `type_annotation`
    took a single string; §3.1 widened it to a list, so that is no longer the
    reason to reach for a scope — the reason is a scope carrying an attribute,
    which is what this test is about.)
    """
    paths = _qname_paths(
        tmp_path,
        _qname_catalog(**_qname_mapping(namespace_default="reversed_package")),
        scope_annotated=False,
    )

    assert paths == {"placeRequest"}


def test_a_class_in_the_default_package_derives_no_namespace_rather_than_an_empty_one(
    tmp_path: Path,
):
    """Both reference implementations return `null` for the empty package
    (checkpoint item 2) — there is no namespace to reverse. So the refusal is
    part of the pinned algorithm, not an extra rule bolted on: the row keeps
    its bare name rather than gaining `http:///`, which is neither a namespace
    nor an honest absence."""
    paths = _qname_paths(
        tmp_path,
        _qname_catalog(**_qname_mapping(namespace_default="reversed_package")),
        owner="OrderService#",
        namespace=None,
    )

    assert paths == {"placeRequest"}


def test_a_qualifier_format_and_a_qualifier_separator_are_mutually_exclusive(
    tmp_path: Path,
):
    """Two composition rules for one seam is one too many. Which of them the
    engine applied would decide the address, and a file declaring both states
    no preference — so it is refused rather than resolved by precedence
    nobody wrote down."""
    with pytest.raises(CatalogError) as raised:
        _qname_paths(
            tmp_path,
            _qname_catalog(**_qname_mapping(qualifier_separator=".")),
        )

    assert "qualifier_format" in str(raised.value)
    assert "qualifier_separator" in str(raised.value)
    assert "invented-qname.yml" in str(raised.value)


def test_a_catalog_naming_an_unknown_qualifier_format_is_refused_by_file(tmp_path: Path):
    """A closed vocabulary, for `path_fallback`'s reason: an unrecognised word
    would fall through to the separator composition, which for a catalog that
    declares no separator is the un-composed bare name — silently restoring
    the un-scoped address the form exists to remove."""
    with pytest.raises(CatalogError) as raised:
        _qname_paths(tmp_path, _qname_catalog(**_qname_mapping(qualifier_format="curie")))

    assert "curie" in str(raised.value)
    assert "invented-qname.yml" in str(raised.value)


def test_a_catalog_naming_an_unknown_namespace_default_is_refused_by_file(tmp_path: Path):
    """The same closed-vocabulary rule for the scope's default. A typo read as
    "no default" is the silent-fall-through failure again, and here it would
    be invisible: the rows still derive, just without the namespace the
    framework gives them."""
    with pytest.raises(CatalogError) as raised:
        _qname_paths(
            tmp_path,
            _qname_catalog(**_qname_mapping(namespace_default="package_name")),
        )

    assert "package_name" in str(raised.value)
    assert "invented-qname.yml" in str(raised.value)


@pytest.mark.parametrize(
    ("word", "value"),
    [
        # A format with nothing to format: `qualifier_format` states HOW a
        # scope composes, and a catalog reading no scope has none to compose.
        ("qualifier_format", "qname"),
        # A default for an attribute the catalog never reads. Inert rather
        # than wrong, but silently inert — a file whose author believed they
        # had asked for the JAX-WS default and got nothing.
        ("namespace_default", "reversed_package"),
    ],
)
def test_a_qname_form_declared_without_a_qualifier_from_is_refused_by_file(
    tmp_path: Path, word: str, value: str
):
    """Both new words describe the SCOPE — how it composes, and what it is
    when unstated. Neither has any meaning on a catalog that reads no scope
    at all, so declaring one alone is refused at load rather than accepted
    and ignored."""
    with pytest.raises(CatalogError) as raised:
        _qname_paths(
            tmp_path,
            _qname_catalog(path_fallback="construct_name", **{word: value}),
        )

    assert word in str(raised.value)
    assert "qualifier_from" in str(raised.value)
    assert "invented-qname.yml" in str(raised.value)


# --- 2I design §2: the class-gate member rule and the withdrawal filter ---
#
# Deliberately NOT JAX-WS, for the reason every section above is not the
# framework that motivated it: `members` and `unless` are engine vocabulary,
# and a test spelled with `@WebService`/`@WebMethod` in it would pin a
# framework rather than a mechanism.
#
# The invented framework below is the shape neither 2H nor the QName forms can
# express: a class gate that exposes its members WITHOUT marking them, and a
# member-level annotation that WITHDRAWS the very declaration it sits on.


def _member_catalog(**mapping: object) -> Catalog:
    """A catalog whose class gate is an ordinary `mapping.annotations` entry —
    the list-valued type-level role, which is the only one that could carry two
    spellings of one gate — plus a member-level rule that may withdraw itself.
    """
    return Catalog(
        id="invented-members",
        style="annotation_driven",
        protocol="soap",
        direction="inbound",
        requires=("annotation_args",),
        source=Path("tests/invented-members.yml"),
        matches={
            "mapping": {
                "path_from": ["op"],
                "prefix_from": [],
                "method_from": "method",
                "all_methods": [],
                "prefix_annotation": None,
                "path_fallback": "construct_name",
                "annotations": [
                    {"fqn": "com.acme.rpc.annotation.Service"},
                    {"fqn": "com.acme.rpc.annotation.Operation"},
                ],
                **mapping,
            }
        },
    )


def _member_facts(root: Path, gated: bool = True) -> None:
    """One gated class holding every member shape the rule has to tell apart.

    `bare` carries no annotation at all — the whole point of the member rule.
    `named` carries the member-level rule with a spelled name, `withdrawn`
    carries it with the withdrawing attribute set, and `defaulted` carries it
    bare. `hidden` is non-public, `helper` is static and `bridge$1` is
    synthetic — none of them is an exposed member, and each is excluded for a
    different reason. The constructor is here because a class always has one
    and it must never become an endpoint.
    """
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/rpc/MemberService.java",
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
    owner = "com/acme/rpc/MemberService#"
    facts: list[object] = [
        SymbolFact(
            document_id="doc_1",
            symbol=owner,
            construct_kind=ConstructKind.CLASS,
            # Capability 9.13's erased edge, always written — the base's own
            # facts are what decide whether the walk finds anything, and a
            # superclass no document declares simply ends it (`A-M15`).
            superclass="com/acme/rpc/AbstractMemberService#",
        )
    ]
    if gated:
        facts.append(
            AnnotationFact(
                document_id="doc_1",
                target=owner,
                retention="runtime",
                use=AnnotationUse(
                    annotation="com/acme/rpc/annotation/Service#", args={"ns": "urn:acme"}
                ),
            )
        )
    facts.append(
        SymbolFact(
            document_id="doc_1",
            symbol=f"{owner}<init>(sig_da8c82d5).",
            construct_kind=ConstructKind.CONSTRUCTOR,
            enclosing=owner,
        )
    )
    members = {
        "bare": {"visibility": "public", "modifiers": {}},
        "hidden": {"visibility": "other", "modifiers": {}},
        "helper": {"visibility": "public", "modifiers": {"static": True, "synthetic": False}},
        "bridge": {"visibility": "public", "modifiers": {"static": False, "synthetic": True}},
        "named": {"visibility": "public", "modifiers": {}},
        "withdrawn": {"visibility": "public", "modifiers": {}},
        "defaulted": {"visibility": "public", "modifiers": {}},
    }
    for name, shape in members.items():
        symbol = f"{owner}{name}(sig_3d92af60)."
        facts.append(
            SymbolFact(
                document_id="doc_1",
                symbol=symbol,
                construct_kind=ConstructKind.METHOD,
                enclosing=owner,
                visibility=str(shape["visibility"]),
                modifiers=dict(shape["modifiers"]),  # type: ignore[arg-type]
            )
        )
    # Only the three ANNOTATED members carry the member-level rule; `bare`,
    # `hidden`, `helper` and `bridge` carry nothing, which is what makes them
    # the member rule's own business.
    annotated = {
        "named": {"op": "namedOp"},
        "withdrawn": {"skip": True},
        "defaulted": {},
    }
    for name, args in annotated.items():
        facts.append(
            AnnotationFact(
                document_id="doc_1",
                target=f"{owner}{name}(sig_3d92af60).",
                retention="runtime",
                use=AnnotationUse(annotation="com/acme/rpc/annotation/Operation#", args=args),
            )
        )
    write_fact_file(root / "MemberService.jsonl", document, facts)


def _member_base_facts(root: Path, base_visibility: str = "public") -> None:
    """`A-M15`: the gated class gains a plain, UNANNOTATED superclass declaring
    one public method of its own.

    A separate fact file rather than a parameter on `_member_facts`, so every
    test above sees exactly the facts it always did and the inheritance case
    differs from them in one addition."""
    document = Document(
        document_id="doc_base",
        relative_path="com/acme/rpc/AbstractMemberService.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:c",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    base = "com/acme/rpc/AbstractMemberService#"
    write_fact_file(
        root / "AbstractMemberService.jsonl",
        document,
        [
            SymbolFact(document_id="doc_base", symbol=base, construct_kind=ConstructKind.CLASS),
            SymbolFact(
                document_id="doc_base",
                symbol=f"{base}refund(sig_b17e0011).",
                construct_kind=ConstructKind.METHOD,
                enclosing=base,
                visibility=base_visibility,
                modifiers={},
            ),
        ],
    )


def _member_override_facts(root: Path, withdrawn: bool = False) -> None:
    """The gated class OVERRIDES the base's `refund` — same name, same
    parameter types, and therefore the same descriptor hash the extractor
    writes for both (`ClassScanner.disambiguatorOf` hashes the descriptor, so
    an override and the method it overrides share it by construction).

    `withdrawn=True` puts the member-level rule's own withdrawing attribute on
    the override, which is the shape the framework refuses to expose at all.

    A third fact file rather than a parameter on `_member_facts`, for
    `_member_base_facts`' own reason: every test written before this one sees
    exactly the facts it always did."""
    document = Document(
        document_id="doc_override",
        relative_path="com/acme/rpc/MemberService.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:d",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    owner = "com/acme/rpc/MemberService#"
    facts: list[object] = [
        SymbolFact(
            document_id="doc_override",
            symbol=f"{owner}refund(sig_b17e0011).",
            construct_kind=ConstructKind.METHOD,
            enclosing=owner,
            visibility="public",
            modifiers={},
        )
    ]
    if withdrawn:
        facts.append(
            AnnotationFact(
                document_id="doc_override",
                target=f"{owner}refund(sig_b17e0011).",
                retention="runtime",
                use=AnnotationUse(
                    annotation="com/acme/rpc/annotation/Operation#", args={"skip": True}
                ),
            )
        )
    write_fact_file(root / "MemberServiceOverride.jsonl", document, facts)


def _member_rows(
    tmp_path: Path,
    catalog: Catalog,
    gated: bool = True,
    base: str | None = None,
    override: bool | None = None,
) -> list[tuple[str, str]]:
    """`(path, handler)` for every derived row, in insertion order — the pair a
    set of paths cannot answer, since a rule that publishes ONE operation twice
    collapses into one entry there."""
    _member_facts(tmp_path / "facts", gated)
    if base is not None:
        _member_base_facts(tmp_path / "facts", base)
    if override is not None:
        _member_override_facts(tmp_path / "facts", override)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    derive_endpoints(workspace, [catalog], capabilities={"annotation_args"})
    rows = [(str(row["path"]), str(row["handler"])) for row in workspace.query("endpoints")]
    workspace.close()
    return rows


def _member_paths(
    tmp_path: Path,
    catalog: Catalog,
    gated: bool = True,
    base: str | None = None,
    override: bool | None = None,
) -> set[str]:
    return {path for path, _ in _member_rows(tmp_path, catalog, gated, base, override)}


def test_a_catalog_declaring_no_member_rule_derives_only_what_is_annotated(
    tmp_path: Path,
):
    """The inertness pin. `members` is optional, and a catalog declaring none
    must derive exactly the annotated declarations it always did — which is
    what lets the word ship without touching any catalog written before it.

    `withdrawn` and `defaulted` are here too: with no `unless` declared, the
    withdrawing attribute is just an attribute nobody reads, so all three
    annotated members derive."""
    assert _member_paths(tmp_path, _member_catalog()) == {
        "namedOp",
        "withdrawn",
        "defaulted",
    }


def test_a_class_gate_derives_every_public_member_that_no_rule_claims(tmp_path: Path):
    """Word 3. `bare` carries NO annotation at all and is still an endpoint,
    because the framework exposes what the class declares rather than what an
    author marked — the pattern no vocabulary before this could express (the
    2H class-level mechanism composes a PREFIX onto a row that a method-level
    annotation must already have minted).

    Its name comes from `path_fallback: construct_name`, which is required
    beside `members` precisely because a member has no name attribute to read.
    """
    paths = _member_paths(tmp_path, _member_catalog(members="public_methods"))

    assert "bare" in paths


def test_a_gated_classes_inherited_public_method_is_an_exposed_member(tmp_path: Path):
    """`A-M15`, the positive half. "The public methods of C" is not "the public
    methods DECLARED in C" (JLS 8.2), and the member join asked `s.enclosing`
    — so a gated class extending a plain base published none of the base's
    operations, silently, with no COVERAGE row.

    The catalog whose comment this contradicts is `jakarta-jws.yml`, which
    argues at length that an unannotated public method IS an operation — "a
    catalog that derived only the annotated methods would report a service
    missing one of its own operations" — and the join then made exactly that
    mistake one axis over.

    Measured, not read off the specification's wording (CP-13 Q3, jaxws-rt
    4.0.2): `RuntimeModeler.processClass` walks the implementor's
    `Class.getMethods()`, which returns inherited public methods, and drops
    only those declared by `java.lang.Object`.

    `refund` is on the base and carries no annotation; `bare` is on the class
    itself. Both derive, which is what says the widening ADDED the inherited
    member rather than replacing the declared one."""
    paths = _member_paths(tmp_path, _member_catalog(members="public_methods"), base="public")

    assert {"bare", "refund"} <= paths


def test_an_inherited_method_that_is_not_public_is_not_an_exposed_member(tmp_path: Path):
    """`A-M15`'s near-miss, and the conjunct a widened join is most likely to
    lose: the exclusions apply to an INHERITED member exactly as they do to a
    declared one. `refund` is the same method in the same place, one cell
    different — `visibility: other` — and it is not callable from outside the
    type, so it is not exposed.

    Identical to the positive in every other respect, so it measures the
    visibility filter and nothing else, and it discriminates: dropping
    `s.visibility = 'public'` from the member rule makes this fail with a
    `refund` operation the container does not serve. The class's own `bare` is
    asserted present in both, which is what stops this passing because the walk
    found nothing at all."""
    paths = _member_paths(tmp_path, _member_catalog(members="public_methods"), base="other")

    assert "bare" in paths
    assert "refund" not in paths


def test_an_overridden_inherited_member_is_one_exposed_member_and_not_two(tmp_path: Path):
    """`A-M15`'s regression, the first half. A type's members are one per
    SIGNATURE, never one per declaration of that signature — the ancestry walk
    enumerated both `MemberService#refund` and `AbstractMemberService#refund`
    and published the same operation twice, the second handled by a base class
    the framework never exposes.

    JLS 8.4.8.1: an instance method with the same name and parameter types
    OVERRIDES the one it inherits, and there is then one member. The framework
    agrees, and it is MEASURED rather than read off that sentence (CP-13 Q5,
    JDK 26): `Class.getMethods()` — the enumeration `RuntimeModeler.processClass`
    walks (Q3, jaxws-rt 4.0.2) — returns exactly one `refund`, the override's,
    for precisely this pair of classes.

    The handler assertion is the load-bearing half: the count alone would still
    pass if the walk kept the BASE's declaration and dropped the override's,
    which is the same wrong attribution one row further down."""
    rows = _member_rows(
        tmp_path, _member_catalog(members="public_methods"), base="public", override=False
    )

    assert [handler for path, handler in rows if path == "refund"] == [
        "com/acme/rpc/MemberService#refund(sig_b17e0011)."
    ]


@pytest.mark.pins("derive_endpoints.one-exposed-member-per-signature")
def test_an_override_that_withdraws_itself_withdraws_the_member_it_overrides(tmp_path: Path):
    """`A-M15`'s regression, the second half, and the worse one: the ancestry
    walk republished an operation the framework EXPLICITLY withdraws.

    `MemberService#refund` overrides `AbstractMemberService#refund` and carries
    the member-level rule's withdrawing attribute. The override is the one
    member (Q5 above), the rule claims it, and the rule's answer for it is
    nothing — so the operation is not exposed at all. Before the dedup the
    override was claimed by the annotated rule and withdrawn there, while the
    base's own declaration walked straight past the anti-join and published the
    withdrawn operation at `resolved`/`compiler`, attributed to the base.

    `bare` is asserted present in the same run, which is what stops this passing
    because the walk found nothing at all — the near-miss's paired positive is
    `test_an_overridden_inherited_member_is_one_exposed_member_and_not_two`
    above, the same input with the withdrawal removed, where the operation DOES
    derive."""
    paths = _member_paths(
        tmp_path,
        _member_catalog(
            members="public_methods",
            annotations=[
                {"fqn": "com.acme.rpc.annotation.Service"},
                {
                    "fqn": "com.acme.rpc.annotation.Operation",
                    "unless": {"attribute": "skip", "equals": True},
                },
            ],
        ),
        base="public",
        override=True,
    )

    assert "bare" in paths
    assert "refund" not in paths


def test_a_member_level_rule_overrides_the_member_rule_for_the_member_it_names(
    tmp_path: Path,
):
    """One row per member, never two. `named` is a public method of a gated
    class AND carries the member-level rule, so it derives ONCE, with the
    rule's own value (`namedOp`) — not also under its construct name.

    The override is by ANNOTATION, not by outcome: `withdrawn` is claimed by
    the rule too, and the rule's answer for it is nothing.
    """
    paths = _member_paths(
        tmp_path,
        _member_catalog(
            members="public_methods",
            annotations=[
                {"fqn": "com.acme.rpc.annotation.Service"},
                {
                    "fqn": "com.acme.rpc.annotation.Operation",
                    "unless": {"attribute": "skip", "equals": True},
                },
            ],
        ),
    )

    assert paths == {
        # The member rule's own row — no annotation anywhere.
        "bare",
        # The rule's value, and NOT a second `named` row beside it.
        "namedOp",
        # Annotated, bare attributes: the rule claims it, `path_fallback`
        # names it. Still one row, still the rule's answer.
        "defaulted",
        # NOT here: `withdrawn` (the framework withdrew it), `hidden`
        # (non-public), `helper` (static), `bridge` (synthetic), and the
        # constructor.
    }


def test_a_withdrawn_declaration_derives_nothing_even_inside_a_gated_class(
    tmp_path: Path,
):
    """Word 4, and its interaction with word 3 — the one that would have been
    a silent no-op if the override had been written the obvious way.

    `withdrawn` carries the member-level rule with the withdrawing attribute
    set, so the rule derives nothing for it. It is ALSO a public method of a
    gated class, so the member rule would happily re-derive the very row the
    framework withdrew — unless the override is keyed on carrying an
    annotation rather than on having produced a row. It is.
    """
    withdrawing = _member_catalog(
        members="public_methods",
        annotations=[
            {"fqn": "com.acme.rpc.annotation.Service"},
            {
                "fqn": "com.acme.rpc.annotation.Operation",
                "unless": {"attribute": "skip", "equals": True},
            },
        ],
    )

    assert "withdrawn" not in _member_paths(tmp_path, withdrawing)
    # …and with no filter declared, the SAME declaration derives: the row is
    # absent because the framework withdrew it, not because the fixture is
    # shaped so it could never appear.
    assert "withdrawn" in _member_paths(tmp_path / "b", _member_catalog(members="public_methods"))


def test_an_absent_attribute_is_not_the_withdrawing_value(tmp_path: Path):
    """An annotation's declared default is never written into the class file
    (checkpoint item 4: `@WebMethod(exclude = true)` emits the attribute,
    `@WebMethod` alone emits `{}`), so the withdrawing attribute reads NULL on
    every declaration that left it alone. Absence must therefore mean KEPT.

    `defaulted` carries the rule with no attributes at all and still derives;
    a comparison written `<>` instead of `IS DISTINCT FROM` would have made
    its NULL comparison NULL and dropped it — dropping, silently, every
    declaration that did not spell the flag out.
    """
    paths = _member_paths(
        tmp_path,
        _member_catalog(
            annotations=[
                {"fqn": "com.acme.rpc.annotation.Service"},
                {
                    "fqn": "com.acme.rpc.annotation.Operation",
                    "unless": {"attribute": "skip", "equals": True},
                },
            ]
        ),
    )

    assert paths == {"namedOp", "defaulted"}


@pytest.mark.parametrize(
    ("excluded", "why"),
    [
        ("hidden", "not public — not callable from outside the type"),
        ("helper", "static — bound to the type, not to an exposed instance"),
        ("bridge", "synthetic — compiler machinery nobody declared"),
        ("<init>", "a constructor is not a member the framework exposes"),
    ],
)
def test_the_member_rule_excludes_what_is_not_an_exposed_member(
    tmp_path: Path, excluded: str, why: str
):
    """Four exclusions, each a fact rather than a taste, and each pinned
    separately so a rule that lost one shows up as itself.

    The static and synthetic ones matter most in practice: a gated class
    holding a `public static void main` or a covariant-return bridge would
    otherwise publish it as an operation, at `resolved`/`compiler`, where
    nothing downstream could tell it from something observed. Synthetic
    methods reach the fact stream on purpose (the inheritance walk's bridge
    rule needs them), so this is a real filter, not a defensive one.
    """
    paths = _member_paths(tmp_path, _member_catalog(members="public_methods"))

    assert excluded not in paths, why


def test_the_member_rule_derives_nothing_for_a_class_the_gate_does_not_hold(
    tmp_path: Path,
):
    """The gate is the whole safety of the rule: without it, every public
    method in the module becomes an endpoint. The same class, with its
    type-level annotation removed, contributes no member rows at all — and
    its ANNOTATED members still derive, because their own rule never needed
    the gate."""
    paths = _member_paths(tmp_path, _member_catalog(members="public_methods"), gated=False)

    assert paths == {"namedOp", "withdrawn", "defaulted"}


def test_a_catalog_naming_an_unknown_member_rule_is_refused_by_file(tmp_path: Path):
    """A closed vocabulary, and the sharpest one in the mapping block: this is
    the only word that derives rows for declarations carrying no annotation,
    so a word read as something it is not mints endpoints out of ordinary
    methods."""
    with pytest.raises(CatalogError) as raised:
        _member_paths(tmp_path, _member_catalog(members="all_methods"))

    assert "all_methods" in str(raised.value)
    assert "invented-members.yml" in str(raised.value)


def test_a_member_rule_without_a_name_fallback_is_refused(tmp_path: Path):
    """A member carries no annotation and therefore no name attribute at all —
    every alias is absent by construction. Without `path_fallback` every member
    row would compose the EMPTY path: a resolved endpoint addressing nothing,
    which is the failure `path_from` and `qualifier_from` are both already
    checked for, reached by a third route."""
    catalog = _member_catalog(members="public_methods")
    del catalog.matches["mapping"]["path_fallback"]

    with pytest.raises(CatalogError) as raised:
        _member_paths(tmp_path, catalog)

    assert "path_fallback" in str(raised.value)
    assert "invented-members.yml" in str(raised.value)


def test_a_member_rule_with_no_class_gate_at_all_is_refused(tmp_path: Path):
    """A member rule enumerates the members OF something. Where nothing can
    name the class, the rule is not inert — it is catastrophic, since the only
    remaining filter would be "is a public method". Refused at load, where a
    catalog can still be fixed."""
    catalog = _member_catalog(members="public_methods")
    catalog.matches["mapping"]["annotations"] = []

    with pytest.raises(CatalogError) as raised:
        _member_paths(tmp_path, catalog)

    assert "class gate" in str(raised.value)
    assert "invented-members.yml" in str(raised.value)


@pytest.mark.parametrize(
    "declared",
    [
        # A misspelled key: the filter would read an attribute no annotation
        # carries, match nothing, and derive every declaration including the
        # ones the framework withdraws.
        {"attr": "skip", "equals": True},
        # `equals` missing entirely — a filter with no value to compare.
        {"attribute": "skip"},
        # `attribute` missing — a value with nothing to read it from.
        {"equals": True},
        # A third key: the shape is closed, so a key the engine does not read
        # is a rule the author believes is being applied and is not.
        {"attribute": "skip", "equals": True, "unless": "nested"},
        # Not a mapping at all.
        "skip",
        # `attribute` must be a NAME, not a YAML scalar of some other type.
        {"attribute": 5, "equals": True},
    ],
)
def test_a_malformed_withdrawal_filter_is_refused_by_file(tmp_path: Path, declared: object):
    """Exactly `attribute` and `equals`, and nothing else. Every shape here
    would leave the filter reading NULL and matching nothing — so the rule
    would derive every declaration including the ones the framework itself
    withdraws, which is a published endpoint nobody serves rather than a
    missing one."""
    with pytest.raises(CatalogError) as raised:
        _member_paths(
            tmp_path,
            _member_catalog(
                annotations=[
                    {"fqn": "com.acme.rpc.annotation.Service"},
                    {"fqn": "com.acme.rpc.annotation.Operation", "unless": declared},
                ]
            ),
        )

    assert "unless" in str(raised.value)
    assert "invented-members.yml" in str(raised.value)


# --- The prefix seam: `mapping.path_separator` ----------------------------
#
# Deliberately NOT Spring, for the reason the naming forms above are not
# GraphQL: how a TYPE-level prefix joins the address it prefixes is engine
# vocabulary driven by catalog data, and a test spelled with `@RequestMapping`
# in it would pin a framework rather than the mechanism. The live failure the
# mechanism closes IS Spring, and is pinned where a live failure belongs — on
# the fixture, through `spring-web.yml` (`tests/e2e/test_vertical_slice.py`).


def _seam_catalog(protocol: str = "http", direction: str = "inbound", **mapping: object) -> Catalog:
    """A gated catalog whose type-level annotation carries a prefix and whose
    method-level annotation carries a suffix — the two halves of one seam,
    with whatever composition vocabulary a test layers on.

    `protocol` and `direction` are parameters because 2O design §8 and ruling
    R8 made them the canonical-address gate (`domain/paths.py::serves_urls`).
    A composed address is canonicalized into the URL the framework serves only
    for an INBOUND HTTP catalog, so a test about the SEAM alone — what the
    join does and does not insert — asks one of the other three combinations.
    """
    return Catalog(
        id="invented-seam",
        style="annotation_driven",
        protocol=protocol,
        direction=direction,
        requires=("annotation_args",),
        source=Path("tests/invented-seam.yml"),
        matches={
            "mapping": {
                "path_from": ["value"],
                "prefix_from": ["value"],
                "method_from": "method",
                "all_methods": [],
                "prefix_annotation": "com.acme.rest.annotation.Resource",
                "annotations": [{"fqn": "com.acme.rest.annotation.Route"}],
                **mapping,
            }
        },
    )


def _seam_facts(root: Path, prefix: str, suffix: str) -> None:
    """One type carrying `prefix`, one method on it carrying `suffix`."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/rest/Seam.java",
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
    owner = "com/acme/rest/Seam#"
    route = f"{owner}route(sig_3d92af60)."
    write_fact_file(
        root / "Seam.jsonl",
        document,
        [
            SymbolFact(document_id="doc_1", symbol=owner, construct_kind=ConstructKind.CLASS),
            SymbolFact(
                document_id="doc_1",
                symbol=route,
                construct_kind=ConstructKind.METHOD,
                enclosing=owner,
            ),
            AnnotationFact(
                document_id="doc_1",
                target=owner,
                retention="runtime",
                use=AnnotationUse(
                    annotation="com/acme/rest/annotation/Resource#", args={"value": [prefix]}
                ),
            ),
            AnnotationFact(
                document_id="doc_1",
                target=route,
                retention="runtime",
                use=AnnotationUse(
                    annotation="com/acme/rest/annotation/Route#", args={"value": [suffix]}
                ),
            ),
        ],
    )


def _seam_row(tmp_path: Path, catalog: Catalog, prefix: str, suffix: str) -> dict[str, object]:
    """The whole derived row, for the tests that ask about a column the
    composed path is not — `resolution`, above all."""
    _seam_facts(tmp_path / "facts", prefix, suffix)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    derive_endpoints(workspace, [catalog], capabilities={"annotation_args"})
    [row] = workspace.query("endpoints")
    workspace.close()
    return dict(row)


def _seam_path(tmp_path: Path, catalog: Catalog, prefix: str, suffix: str) -> str:
    return str(_seam_row(tmp_path, catalog, prefix, suffix)["path"])


@pytest.mark.parametrize(
    ("prefix", "suffix", "composed"),
    [
        # Neither half spells the separator: one is inserted. The live
        # failure — spring-petclinic-microservices' api-gateway writes
        # `@RequestMapping("/api/gateway")` + `@GetMapping("owners/{ownerId}")`
        # and is served at `/api/gateway/owners/{ownerId}`; the bare
        # concatenation published `/api/gatewayowners/{ownerId}`.
        ("/api/gateway", "owners/{id}", "/api/gateway/owners/{id}"),
        # Both halves spell it: the seam is deduped to one, never doubled.
        ("/api/gateway", "/owners/{id}", "/api/gateway/owners/{id}"),
        # One half spells it — the shape every catalogued fixture path
        # already had, which is why the bug hid: unchanged by the fix.
        ("/api/gateway/", "owners/{id}", "/api/gateway/owners/{id}"),
        # A `"/"` prefix contributes nothing but the leading slash. The
        # second live failure — genai-service's `@RequestMapping("/")` +
        # `@PostMapping("/chatclient")` is served at `/chatclient`; the bare
        # concatenation published `//chatclient`.
        ("/", "/chatclient", "/chatclient"),
        ("/", "chatclient", "/chatclient"),
        # BOTH halves spell it at once — a prefix with a trailing slash AND a
        # suffix with a leading one, unlike the two-arg case above where only
        # one side ever carries it. `rtrim`/`ltrim` each strip their own side
        # independently, so composing them still dedupes to exactly one
        # separator at the seam rather than the two either half would leave
        # if the other's trim were skipped.
        ("/api/x/", "/y", "/api/x/y"),
    ],
)
def test_a_declared_separator_joins_the_two_halves_of_a_seam_with_exactly_one(
    tmp_path: Path, prefix: str, suffix: str, composed: str
):
    """Whichever half spelled the separator, the composed address carries one.
    A doubled or missing separator is an address nobody serves, published at
    `resolved`/`compiler` where nothing downstream can tell it from something
    observed — the same confidently-wrong-address class `path_fallback` closes
    from the other direction."""
    assert _seam_path(tmp_path, _seam_catalog(path_separator="/"), prefix, suffix) == composed


def test_an_empty_half_takes_no_separator_with_it(tmp_path: Path):
    """An absent prefix leaves the suffix exactly as written — a slashless
    name does NOT gain a leading `/` the JOIN would be inventing — and an
    empty suffix (a `@KafkaHandler`, an `@OnMessage`) leaves the prefix
    alone. Both halves are real: the catalogs riding the seam include ones
    whose method annotation carries no path attribute at all.

    The first assertion asks a NAMED-address catalog, and that is 2O design
    §8's doing rather than a weakening: on an HTTP catalog the composed
    address is canonicalized afterwards into the URL the framework serves,
    so `owners` does end up as `/owners` there (third assertion) — from the
    canonical gate, which knows it is looking at a URL, and never from the
    seam, which does not."""
    catalog = _seam_catalog(path_separator="/")
    named = _seam_catalog(protocol="kafka", path_separator="/")

    assert _seam_path(tmp_path, named, "", "owners") == "owners"
    assert _seam_path(tmp_path / "b", catalog, "/v1/orders", "") == "/v1/orders"
    assert _seam_path(tmp_path / "c", catalog, "", "owners") == "/owners"


def _seam_rows(tmp_path: Path, catalog: Catalog, prefix: str, suffix: str) -> list[dict]:
    """Every row the seam derived — zero of them included, which `_seam_row`'s
    single-row unpack cannot express and which is the whole question below."""
    _seam_facts(tmp_path / "facts", prefix, suffix)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    derive_endpoints(workspace, [catalog], capabilities={"annotation_args"})
    rows = [dict(row) for row in workspace.query("endpoints")]
    workspace.close()
    return rows


# --- Mechanism 3 (principles sweep §4, §7.7): the empty-address gate ---------


@pytest.mark.parametrize("separator", [None, "/"])
def test_an_empty_composed_destination_derives_nothing_whatever_the_separator(
    tmp_path: Path, separator: str | None
):
    """Whether an empty address means anything is a question about the
    PROTOCOL, and `path_separator` is a formatting property — how segments are
    joined. The gate used to be keyed on it (`WHERE NOT ($path_separator IS
    NULL AND d.path = '')`), which is why it protected `spring-rabbit` and not
    its structural twin `spring-stomp`: the twin's destinations contain
    slashes, so its author declared a separator, and declaring one switched the
    validity gate off. Seven shipped catalogs declare one and were all
    unguarded (§7.7); `A-C1` names three of them because three had a reachable
    bare-annotation path, not because the other four were safe.

    Parametrized over both spellings on purpose: a gate that says what it means
    cannot give two answers to the same question about the same protocol."""
    catalog = _seam_catalog(protocol="websocket", direction="inbound", **_separator(separator))

    assert _seam_rows(tmp_path, catalog, "", "") == []


@pytest.mark.parametrize("separator", [None, "/"])
def test_the_same_declaration_with_a_destination_still_derives(
    tmp_path: Path, separator: str | None
):
    """The paired positive, and it is not decoration: the near-miss above is
    satisfied by a rule that derives nothing at all, and a catalog silenced
    outright would pass it forever."""
    catalog = _seam_catalog(protocol="websocket", direction="inbound", **_separator(separator))

    [row] = _seam_rows(tmp_path, catalog, "/live", "")
    assert (row["path"], row["resolution"], row["evidence"]) == ("/live", "resolved", "compiler")


def test_a_served_http_root_route_is_a_real_address_and_still_derives(tmp_path: Path):
    """The one protocol for which the empty address DOES name something, and
    the reason the gate cannot simply be "drop the empty string" at the seam:
    a class prefix with an empty method mapping is served at `/` (CP-1 row 5).

    It survives because the canonical-address gate has already turned the
    empty composition into `/` by the time the validity gate runs — inbound
    HTTP is exactly `domain/paths.py::serves_urls`, so the two seams agree
    about which protocol this is without the validity gate having to ask
    twice."""
    [row] = _seam_rows(tmp_path, _seam_catalog(path_separator="/"), "", "")

    assert row["path"] == "/"
    assert row["resolution"] == "resolved"


def _separator(separator: str | None) -> dict[str, object]:
    return {} if separator is None else {"path_separator": separator}


def test_a_catalog_declaring_no_separator_concatenates_exactly_as_it_always_did(
    tmp_path: Path,
):
    """The inertness pin, and the reason the separator is catalog data rather
    than an engine default: `spring-kafka.yml`'s prefix is a class-level
    `@KafkaListener`'s TOPIC, and a topic name has no segments to join. A `/`
    inserted between two halves of one would invent a destination no broker
    carries, so a catalog that declares no separator keeps the bare
    concatenation every catalog had before this vocabulary existed.

    Asked of the protocol the claim is actually about, for 2O design §8's
    reason: a topic is not a URL, so no canonical-address gate stands between
    the concatenation and the recorded row."""
    assert (
        _seam_path(tmp_path, _seam_catalog(protocol="kafka"), "orders", "-retry") == "orders-retry"
    )


@pytest.mark.parametrize(
    "raw",
    [
        "users",  # CP-1: Spring serves this at /users
        "/users",
        "/api//users",  # one separator per boundary
        "/users/",  # Framework 6: a trailing slash is DISTINCT
        "",
        "https://billing.example/orders",  # a whole address, not a path half
        "https://${billing.host}/orders",  # placeholder-bearing composition
        "${service.base}/orders",
        # BOTH expression notations, not one (2O Task 7 review, Critical 4).
        # `_EXPRESSION_OPENS` lists `${` and `#{` together and the SQL's
        # `$canonical_path` gate mirrors the pair, but with only `${` cases
        # here the domain side could be reverted to `("${",)` and the whole
        # suite still passed — the pin the Task 7 report claimed existed did
        # not cover the notation Task 7 added. SpEL is what a Spring
        # `@JmsListener(destination = "#{…}")` actually carries.
        "#{orderProperties.topic}",
        "#{serviceBase}/orders",
    ],
)
@pytest.mark.parametrize("protocol", ["http", "kafka"])
@pytest.mark.parametrize("direction", ["inbound", "outbound"])
def test_the_sql_path_seam_answers_exactly_what_the_domain_seam_answers(
    tmp_path: Path, raw: str, protocol: str, direction: str
):
    """The anti-drift pin `domain/paths.py` and `derive_endpoints.sql` both
    name (2O design §8).

    `annotation_driven` composes its address in SQL, from columns the domain
    layer never sees, and `storage/` may not import a seam whose name is a
    protocol (ARCHITECTURE §10) — so the canonicalization is stated on both
    sides of that boundary, exactly as `_destinations_of` mirrors the SQL's
    own alias-reading rule one level down. This asserts the two answers
    against EACH OTHER rather than against a literal, so neither side can be
    edited into disagreement without a failure here.

    Run over all four protocol/direction combinations, because the GATE is as
    driftable as the rule: the SQL reads a `$canonical_path` bind and the
    domain side reads `serves_urls`, and a gate that disagreed would be
    invisible to a test pinning only the inbound-HTTP answers. `serves_urls`
    decides the expectation here too — deliberately, since it is the one
    place the gate is spelled and both implementations are being pinned to
    it.
    """
    catalog = _seam_catalog(protocol=protocol, direction=direction, path_separator="/")
    rows = _seam_rows(tmp_path, catalog, "", raw)

    expected = canonical_http_path(raw) if serves_urls(protocol, direction) else raw
    if expected == "":
        # `raw=""` on a protocol whose empty address names nothing: the two
        # seams still agree — both compose the empty string — and the
        # addresses-nothing gate then withholds the row (mechanism 3, §4).
        # Asserting emptiness IS the comparison's observable form here; the
        # inbound-HTTP row of the same parametrization is the paired positive,
        # where `serves_urls` makes the same composition the root route `/`.
        assert rows == []
    else:
        assert [row["path"] for row in rows] == [expected]


def test_a_client_side_http_path_keeps_the_separator_the_declaration_wrote(tmp_path: Path):
    """Ruling R8's boundary, pinned on its own so nobody "fixes" the
    inconsistency later.

    A CLIENT declaration is not a served URL. Retrofit's `@GET("legacy/
    invoices")` is resolved against the configured `baseUrl`'s own PATH, while
    `@GET("/legacy/invoices")` is root-relative: against a base of
    `https://host/v1/` the two name `https://host/v1/legacy/invoices` and
    `https://host/legacy/invoices`, which are different URLs on different
    services. Prefixing the first would therefore REWRITE an address rather
    than normalize a spelling — the approximation DR-6 forbids, reached by
    applying evidence about Spring's server side (CP-1) to client
    composition.

    §8's purpose is unharmed: it asks for one identity per route the module
    SERVES, so that dedup, the path-keyed anchors and L's cross-service joins
    agree. An outbound row's identity is a composed address the peer join
    governs, and it keeps the half the declaration actually wrote.
    """
    outbound = _seam_catalog(direction="outbound", path_separator="/")

    assert _seam_path(tmp_path, outbound, "", "legacy/invoices") == "legacy/invoices"
    # A client declaration that names NO path and no service either addresses
    # nothing at all, and derives no row (mechanism 3, §4). What the boundary
    # claims is that a client path is not canonicalized — never that an empty
    # one is an address — and the assertion above is where that is pinned. A
    # client whose type-level annotation DOES name the service keeps its
    # empty-path row: the peer is what makes the base address real.
    assert _seam_rows(tmp_path / "b", outbound, "", "") == []
    # And the inbound twin of the very same declaration IS canonicalized —
    # the pair is what makes the boundary a boundary rather than an omission.
    inbound = _seam_catalog(path_separator="/")
    assert _seam_path(tmp_path / "c", inbound, "", "legacy/invoices") == "/legacy/invoices"


@pytest.mark.parametrize(
    ("prefix", "suffix", "composed"),
    [
        # A SpEL expression on the method annotation. The live shape:
        # `@RabbitListener(queues = "#{ordersQueue.name}")`, where the queue's
        # real name is a bean property this workspace never sees.
        ("", "#{ordersQueue.name}", "#{ordersQueue.name}"),
        # A property placeholder — the same claim, a different notation.
        ("", "${orders.queue}", "${orders.queue}"),
        # On the PREFIX half, which is the same defect one level out: a
        # class-level annotation whose destination is an expression.
        ("#{prefixBean.name}", "", "#{prefixBean.name}"),
        # An expression EMBEDDED in an otherwise literal address. The address
        # is unknown as a whole, not merely decorated, so the whole row is
        # unresolved rather than resolved-with-a-hole.
        ("", "orders.#{env.suffix}", "orders.#{env.suffix}"),
    ],
)
def test_an_annotation_derived_path_carrying_an_expression_is_published_unresolved(
    tmp_path: Path, prefix: str, suffix: str, composed: str
):
    """§8: never assert what the evidence does not support.

    An annotation-derived row used to be stamped `resolved`/`compiler`
    unconditionally, so a destination the author wrote as an expression —
    a SpEL `#{…}`, a property `${…}` — was published as though the characters
    of the expression WERE the address. Nothing downstream can tell such a row
    from an observation, which is the confidently-wrong-address failure the
    composed-path guards already exist to prevent, reached by the one column
    those guards do not set.

    The expression is carried VERBATIM rather than dropped or resolved:
    unresolved is an answer, and the expression is the only true thing known
    about the address. Resolving it is not this pass's job and not any pass's
    job today — the config ladder is a call-site mechanism this engine never
    invokes, and its product is an expression rather than a value.
    """
    row = _seam_row(tmp_path, _seam_catalog(protocol="amqp"), prefix, suffix)

    assert row["path"] == composed
    assert row["resolution"] == "unresolved"
    # The row is still evidence that this method listens on something: the
    # handler, the protocol and the direction are all read, and only the
    # address is unknown. Dropping it would lose all four.
    assert row["evidence"] == "compiler"
    assert row["handler"] is not None


def test_an_expression_bearing_path_is_never_canonicalized_into_a_url(tmp_path: Path):
    """The verbatim half of the rule above, on the one catalog shape that
    would otherwise rewrite it.

    An INBOUND HTTP catalog canonicalizes its composed address into the URL
    the framework serves (2O design §8), and that rewrite must not touch an
    expression: `#{…}` is a whole address nobody has resolved yet, so
    prefixing a separator onto it would publish an address that is neither
    what was written nor what will be served. `${…}` was already left alone
    where the seam is stated; `#{…}` is the same claim in the other notation,
    and the two are spelled together so neither can drift from the other.
    """
    http = _seam_catalog(path_separator="/")

    assert _seam_path(tmp_path, http, "", "#{routeBean.path}") == "#{routeBean.path}"
    assert _seam_path(tmp_path / "b", http, "", "${route.path}") == "${route.path}"
    # The control: an ordinary address on the very same catalog IS
    # canonicalized, so the two assertions above pin a boundary rather than a
    # gate that has quietly stopped firing at all.
    assert _seam_path(tmp_path / "c", http, "", "orders") == "/orders"


def test_an_ordinary_annotation_derived_path_stays_resolved(tmp_path: Path):
    """The inertness pin for the gate above: an address with no expression in
    it is exactly as resolved as it always was. Without this, a gate that
    matched too widely — every path, say — would look like a passing suite."""
    row = _seam_row(tmp_path, _seam_catalog(protocol="amqp"), "", "orders.created")

    assert row["path"] == "orders.created"
    assert row["resolution"] == "resolved"


@pytest.mark.parametrize(
    ("constant", "prefix", "suffix", "composed"),
    [
        # The shipped shape: no type-level prefix at all, the whole address is
        # the framework's fixed base plus the name the declaration states.
        ("/actuator", "", "health", "/actuator/health"),
        # Either half spelling the separator still composes exactly one — the
        # constant is joined by the SAME deduping seam a type-level prefix is,
        # rather than by a concatenation of its own.
        ("/actuator/", "", "/health", "/actuator/health"),
        # A type-level prefix as well: the constant goes in FRONT of it, and
        # both seams dedupe.
        ("/actuator", "/admin/", "/health", "/actuator/admin/health"),
        # A declaration carrying no name of its own contributes nothing, and
        # takes no separator with it.
        ("/actuator", "/admin", "", "/actuator/admin"),
    ],
)
def test_a_constant_prefix_joins_the_front_of_every_address_the_catalog_composes(
    tmp_path: Path, constant: str, prefix: str, suffix: str, composed: str
):
    """A framework whose whole surface is served under one fixed base states
    that base nowhere on the declaration — there is no annotation attribute to
    read it from — so it is catalog data. Without it the derived address is
    the bare id, which is a URL the framework does not serve (CP-5 row 5:
    `/probe` is a 404 while `/actuator/probe` is a 200)."""
    catalog = _seam_catalog(path_separator="/", path_prefix=constant)

    assert _seam_path(tmp_path, catalog, prefix, suffix) == composed


def test_a_catalog_declaring_no_constant_prefix_composes_exactly_what_it_always_did(
    tmp_path: Path,
):
    """The inertness pin. Every catalog written before this word declares no
    `path_prefix`, and the seam must reduce to the expression it was — a
    parameter that changed the answer for a catalog that never asked for it
    would move forty shipped files' addresses at once."""
    catalog = _seam_catalog(path_separator="/")

    assert (
        _seam_path(tmp_path, catalog, "/api/gateway", "owners/{id}") == "/api/gateway/owners/{id}"
    )
    assert _seam_path(tmp_path / "b", catalog, "", "owners") == "/owners"


@pytest.mark.parametrize("declared", ["", 5, True, ["/actuator"]])
def test_a_constant_prefix_that_is_not_a_non_empty_string_is_refused_by_file(
    tmp_path: Path, declared: object
):
    """The value is bound straight into every address this catalog composes,
    so an unusable one prefixes characters nobody wrote — a wrong address
    rather than a missing one, published at `resolved`/`compiler`. An
    explicitly EMPTY prefix is refused rather than silently doing what
    omitting the key already does, the `path_separator` precedent."""
    with pytest.raises(CatalogError) as raised:
        _seam_path(tmp_path, _seam_catalog(path_separator="/", path_prefix=declared), "", "health")

    assert "path_prefix" in str(raised.value)
    assert "invented-seam.yml" in str(raised.value)


def test_a_constant_prefix_without_a_separator_is_refused_rather_than_concatenated_bare(
    tmp_path: Path,
):
    """`/actuator` + `health` is `/actuatorhealth` — an address the framework
    does not serve, and the confidently-wrong-address class again. The two
    words are declared together or not at all."""
    with pytest.raises(CatalogError) as raised:
        _seam_path(tmp_path, _seam_catalog(path_prefix="/actuator"), "", "health")

    assert "path_prefix" in str(raised.value)
    assert "path_separator" in str(raised.value)


def test_a_multi_character_separator_is_refused_by_file(tmp_path: Path):
    """The seam is deduped with `rtrim`/`ltrim`, which trim a SET of
    characters: a two-character separator would strip each of its characters
    individually from either half and compose an address the framework does
    not serve. Refused at load rather than read as something it is not — the
    same edge check `qualifier_separator` gets, for the same reason."""
    with pytest.raises(CatalogError) as raised:
        _seam_path(tmp_path, _seam_catalog(path_separator="::"), "/a", "/b")

    assert "path_separator" in str(raised.value)
    assert "invented-seam.yml" in str(raised.value)


@pytest.mark.parametrize(
    "separator",
    [
        # A YAML integer: the check used to be `len(str(separator)) != 1`,
        # which coerces `5` to the string `"5"` and passes — silently joining
        # paths with a digit nobody wrote.
        5,
        # A YAML boolean: `len(str(True))` is `len("True")`, which the old
        # check refused only by accident (length 4, not 1); `False` would
        # have coerced to `"False"` the same way.
        True,
        # An explicitly empty string. `path_separator` states what joins a
        # TYPE-level prefix to the address it prefixes — an empty value
        # contradicts that purpose, since there is nothing left to declare.
        # Omitting the key entirely is the supported way to say "no
        # separator, bare concatenation" — `spring-kafka.yml` does exactly
        # that for its topic prefix, which has no segments to join.
        "",
        # Two characters: `rtrim`/`ltrim` trim a SET of characters, so this
        # would strip each character individually rather than the pair.
        "::",
    ],
)
def test_a_non_single_character_path_separator_is_refused_by_type_and_length(
    tmp_path: Path, separator: object
):
    """`path_separator` must be a STRING of exactly one character — not
    merely something whose `str()` has length one. A wrong-typed or
    wrong-length value would compose an address the framework does not
    serve, published at `resolved`/`compiler` where nothing downstream can
    tell it from something observed."""
    with pytest.raises(CatalogError) as raised:
        _seam_path(tmp_path, _seam_catalog(path_separator=separator), "/a", "/b")

    assert "path_separator" in str(raised.value)
    assert "invented-seam.yml" in str(raised.value)


def test_the_qualifier_seam_keeps_its_own_separator_when_a_path_separator_is_declared(
    tmp_path: Path,
):
    """The two seams are separate rules and must not blend. A scope and a
    member are written by ONE author on ONE annotation, so neither half ever
    spells the separator and there is nothing to dedupe; a prefix and a path
    are written by two authors who each decide independently. A catalog
    declaring both composes `.` between scope and member and `/` at the
    prefix seam — and the GraphQL catalogs, which declare only the former,
    are untouched by the latter existing."""
    paths = _paths_of(
        tmp_path,
        _naming_forms_catalog(
            path_fallback="construct_name",
            qualifier_from=["scope"],
            qualifier_separator=".",
            path_separator="/",
        ),
    )

    assert paths == {"named", "defaulted", "Parent.member", "Parent.scopedDefaulted"}


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
        fact_schema_version=2,
        scanner_id="asm",
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
        fact_schema_version=2,
        scanner_id="asm",
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
        fact_schema_version=2,
        scanner_id="asm",
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
        fact_schema_version=2,
        scanner_id="asm",
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
        fact_schema_version=2,
        scanner_id="asm",
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
        fact_schema_version=2,
        scanner_id="asm",
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
        fact_schema_version=2,
        scanner_id="asm",
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
        fact_schema_version=2,
        scanner_id="asm",
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


def test_a_path_the_module_both_exposes_and_calls_stays_two_endpoints(tmp_path):
    """F5 §6.1 (W27). This used to be one row with `direction: both`, keeping the
    server's handler and gaining the client's caller.

    That row asserted the thing called IS the thing served — a claim about the far end of
    a call, which a module's own bytecode cannot show — and it was reached by comparing
    `(protocol, method, path)` alone, because `peer` is not part of endpoint identity
    (RC-5). So a path this module serves collided with the same path anywhere in the
    world. Measured on the shipped fixture, two of six merged rows were exactly that: a
    SOAP operation merged with a call to `${soap.billing.uri}`, and `POST /v1/orders`
    merged with a call to `orders-loop`.

    The two rows now stand, each keeping its own side, and `resolve/self_exchange.py`
    files the question (`test_self_exchange.py`). `Direction.BOTH` stays in D00 §4 for
    the linking tier, where a schema match or a person can justify the claim.
    """
    workspace = _two_direction_workspace(tmp_path)
    rows = [e for e in workspace.query("endpoints") if e["path"] == "/v1/orders"]
    workspace.close()

    assert sorted(str(row["direction"]) for row in rows) == ["inbound", "outbound"]
    [inbound] = [row for row in rows if row["direction"] == "inbound"]
    [outbound] = [row for row in rows if row["direction"] == "outbound"]
    assert inbound["handler"] is not None and inbound["caller"] is None
    assert outbound["caller"] is not None and outbound["handler"] is None


def _legacy_facts(root: Path) -> None:
    """A client interface with no type-level marker at all — the Retrofit
    shape: the mapping annotation on the method is the whole evidence."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/legacy/LegacyClient.java",
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
        fact_schema_version=2,
        scanner_id="asm",
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
        fact_schema_version=2,
        scanner_id="asm",
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


# --- 2H Task 5 review, fix round 1: `spring-stomp.yml`'s `reply` block is
# @SendTo-only — `annotation_driven.py::_derive_replies` reads a single
# `reply.annotation` fqn (D02 §2's block, never a list), the same forced
# single-valued constraint the catalog's own `prefix_annotation` runs into
# for jakarta/javax. `@SendToUser` is a DIFFERENT annotation
# (`org.springframework.messaging.handler.annotation.SendToUser`), so a
# handler carrying it instead of `@SendTo` is annotated but invisible to
# `reply_annotation`'s own equality check — this probes what that produces:
# not nothing, and not a wrong destination, but the same honest unresolved
# row a completely UNannotated value-returning handler already gets
# (`_derive_replies`'s own no-reply-annotation branch, the `board`/`escalate`
# precedent). No live fixture surface exists for this shape (Task 1 built
# none), so it is proved here over synthetic facts, on the REAL shipped
# catalog, the same discipline `single_call`'s own `addHandler` probe keeps.
def _sendtouser_facts(root: Path) -> None:
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/ws/StompUserHandler.java",
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
    handler_type = "com/acme/ws/StompUserHandler#"
    notify = "com/acme/ws/StompUserHandler#notify(sig_11112222)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=handler_type, construct_kind=ConstructKind.CLASS),
        # `@Controller`, because Spring STOMP's own handler test is
        # `AnnotatedElementUtils.hasAnnotation(beanType, Controller.class)`
        # (CP-11 Q5) and `spring-stomp.yml` gates on it since `A-C1`. These
        # facts described a class the container would never dispatch to, which
        # is exactly the shape the sweep found in the catalog.
        AnnotationFact(
            document_id="doc_1",
            target=handler_type,
            retention="runtime",
            use=AnnotationUse(annotation="org/springframework/stereotype/Controller#", args={}),
        ),
        SymbolFact(
            document_id="doc_1",
            symbol=notify,
            construct_kind=ConstructKind.METHOD,
            enclosing=handler_type,
            signature=Signature(
                parameters=[],
                returns=TypeRef(symbol="java/lang/String#", wire_type="string"),
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=notify,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/messaging/handler/annotation/MessageMapping#",
                args={"value": ["/notify"]},
            ),
        ),
        # NOT `@SendTo` — `@SendToUser`, a different fqn `reply.annotation`
        # never names.
        AnnotationFact(
            document_id="doc_1",
            target=notify,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/messaging/handler/annotation/SendToUser#",
                args={"value": ["/queue/notify"]},
            ),
        ),
    ]
    write_fact_file(root / "StompUserHandler.jsonl", document, facts)


def _spring_stomp_catalog() -> Catalog:
    return next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-stomp")


def test_an_sendtouser_handler_derives_the_same_honest_unresolved_reply_row_as_no_annotation(
    tmp_path: Path,
):
    _sendtouser_facts(tmp_path / "facts")
    # `spring-stomp` carries `detect.required` since F2 §3.6 — `@MessageMapping`
    # cannot say whether a `@Controller` serves STOMP or RSocket, so the build is
    # the only thing that can. This test is about `@SendToUser`, not about the
    # gate, so it declares the coordinate and moves on.
    write_fixture_module_fact_with(tmp_path / "facts", ("org.springframework:spring-websocket",))
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    skipped = derive_endpoints(
        workspace,
        [_spring_stomp_catalog()],
        capabilities={"annotation_args", "typed_signatures"},
    )
    assert skipped == []
    rows = list(workspace.query("endpoints"))
    workspace.close()

    # The inbound row derives normally — `@SendToUser` plays no role in
    # identity, only in the reply.
    [inbound] = [e for e in rows if e["direction"] == "inbound"]
    assert (inbound["method"], inbound["path"]) == (None, "/notify")
    assert inbound["resolution"] == "resolved"

    # Exactly ONE outbound reply row — never two (a wrongly-matched extra
    # row) and never zero (a silently dropped one): `_derive_replies` walks
    # every handler this catalog's own rows named exactly once, and
    # `notify`'s return type is a real payload (`String`), so it always
    # gets a reply decision, resolved or not.
    outbound = [e for e in rows if e["direction"] == "outbound"]
    assert len(outbound) == 1
    [reply] = outbound
    assert reply["catalog_id"] == "spring-stomp"
    assert reply["caller"] == "com/acme/ws/StompUserHandler#notify(sig_11112222)."
    # The honest answer: NOT the wrong destination (`/queue/notify` never
    # appears anywhere on this row — nothing in `reply.annotation`'s
    # single-valued equality check could have read it), and NOT no row at
    # all — `path` NULL, `unresolved`, the same tuple a completely bare
    # value-returning handler derives (`board`'s own live row, `escalate`'s
    # kafka precedent).
    assert reply["path"] is None
    assert reply["method"] is None
    assert reply["resolution"] == "unresolved"
    assert reply["request_shape"] is not None


# --- 2O Task 2, ruling R8: the reply row is OUTBOUND whatever its catalog is
# --------------------------------------------------------------------------
def _http_reply_facts(root: Path) -> None:
    """One inbound-HTTP-shaped handler carrying a slashless mapping AND a
    reply annotation naming a slashless destination — the contrast pair the
    test below turns on."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/rest/ReplyController.java",
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
    controller = "com/acme/rest/ReplyController#"
    handle = "com/acme/rest/ReplyController#handle(sig_33334444)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=controller, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=handle,
            construct_kind=ConstructKind.METHOD,
            enclosing=controller,
            signature=Signature(
                parameters=[],
                returns=TypeRef(symbol="java/lang/String#", wire_type="string"),
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=controller,
            retention="runtime",
            use=AnnotationUse(annotation="com/acme/rest/annotation/Api#"),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=handle,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/rest/annotation/Route#", args={"value": "orders"}
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=handle,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/rest/annotation/Answer#", args={"value": "reply-dest"}
            ),
        ),
    ]
    write_fact_file(root / "ReplyController.jsonl", document, facts)


def _http_reply_catalog() -> Catalog:
    """An INBOUND HTTP catalog that also declares a `reply` block. No shipped
    catalog is shaped this way today — the four with `reply` blocks are kafka
    and websocket — which is exactly why this is invented: R8's rule about the
    reply row must hold because of what the ROW is, not because of which
    catalogs happen to exist."""
    return Catalog(
        id="invented-http-reply",
        style="annotation_driven",
        protocol="http",
        direction="inbound",
        requires=("annotation_args",),
        source=Path("tests/invented-http-reply.yml"),
        matches={
            "type_annotation": "com.acme.rest.annotation.Api",
            "mapping": {
                "path_from": ["value"],
                "prefix_from": ["value"],
                "method_from": "method",
                "all_methods": [],
                "prefix_annotation": None,
                "annotations": [{"fqn": "com.acme.rest.annotation.Route"}],
            },
            "reply": {
                "annotation": "com.acme.rest.annotation.Answer",
                "destination_from": "value",
                "payload": "return",
            },
        },
    )


def test_a_reply_row_is_never_canonicalized_however_its_catalog_is_declared(tmp_path: Path):
    """Ruling R8, at the one minting site whose direction is a LITERAL.

    `_reply_row` writes `"direction": "outbound"` outright — a reply is always
    a client-side send, whatever direction its catalog declares — so the seam
    must not reach it. Asking the CATALOG's direction here would canonicalize
    an outbound address the moment an inbound HTTP catalog declared a `reply`
    block, which is precisely the rewrite R8 forbids.

    The contrast is the whole test: one handler, two rows, both addresses
    written without a leading separator. The INBOUND row is a route this
    module serves and becomes `/orders`; the OUTBOUND reply row keeps
    `reply-dest` exactly as the annotation wrote it.
    """
    _http_reply_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    skipped = derive_endpoints(
        workspace,
        [_http_reply_catalog()],
        capabilities={"annotation_args", "typed_signatures"},
    )
    assert skipped == []
    rows = list(workspace.query("endpoints"))
    workspace.close()

    [inbound] = [e for e in rows if e["direction"] == "inbound"]
    assert inbound["path"] == "/orders"

    [reply] = [e for e in rows if e["direction"] == "outbound"]
    assert reply["path"] == "reply-dest"
    assert reply["resolution"] == "resolved"


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


# --- 2I Task 5: `declared_on`, the construct gate -------------------------
#
# One annotation family can mark BOTH a served interface and the generated
# client stub of one — `@WebService` does exactly that — and the two are
# opposite DIRECTIONS of the same wire identity. Without a gate on the kind of
# construct the declaration sits on, each catalog derives both and a module is
# published as calling the very operations it serves. Invented framework, the
# section above's own discipline.

_GATE_DOCUMENT = Document(
    document_id="doc_1",
    relative_path="com/acme/wsish/Surface.java",
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


def _construct_gate_facts(root: Path) -> None:
    """One annotation on two constructs: a service CLASS and a stub
    INTERFACE, each declaring one operation."""
    service, stub = "com/acme/wsish/Service#", "com/acme/wsish/Stub#"
    facts = []
    for enclosing, kind, operation in (
        (service, ConstructKind.CLASS, "serve"),
        (stub, ConstructKind.INTERFACE, "call"),
    ):
        method = f"{enclosing}{operation}(sig_1)."
        facts += [
            SymbolFact(document_id="doc_1", symbol=enclosing, construct_kind=kind),
            SymbolFact(
                document_id="doc_1",
                symbol=method,
                construct_kind=ConstructKind.METHOD,
                enclosing=enclosing,
                signature=Signature(parameters=[], returns=TypeRef(symbol="void#")),
            ),
            AnnotationFact(
                document_id="doc_1",
                target=enclosing,
                retention="runtime",
                use=AnnotationUse(annotation="com/acme/wsish/Endpoint#", args={}),
            ),
            AnnotationFact(
                document_id="doc_1",
                target=method,
                retention="runtime",
                use=AnnotationUse(annotation="com/acme/wsish/Operation#", args={"name": operation}),
            ),
        ]
    write_fact_file(root / "Surface.jsonl", _GATE_DOCUMENT, facts)


def _construct_gate_catalog(declared_on: object, direction: str, catalog_id: str) -> Catalog:
    matches: dict = {
        "type_annotation": "com.acme.wsish.Endpoint",
        "mapping": {
            "path_from": ["name"],
            "prefix_from": [],
            "peer_from": [],
            "method_from": "method",
            "all_methods": [],
            "prefix_annotation": None,
            "annotations": [{"fqn": "com.acme.wsish.Operation"}],
        },
    }
    if declared_on is not None:
        matches["declared_on"] = declared_on
    return Catalog(
        id=catalog_id,
        style="annotation_driven",
        protocol="soap",
        direction=direction,
        requires=("annotation_args",),
        source=Path(f"tests/{catalog_id}.yml"),
        matches=matches,
    )


def _construct_gate_rows(tmp_path: Path, catalogs: list[Catalog]) -> list[tuple[str, str]]:
    _construct_gate_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    assert derive_endpoints(workspace, catalogs, capabilities={"annotation_args"}) == []
    rows = [(str(e["direction"]), str(e["path"])) for e in workspace.query("endpoints")]
    workspace.close()
    return sorted(rows)


def test_two_catalogs_partition_one_annotation_by_the_construct_it_sits_on(tmp_path: Path):
    """The whole point of the word: an inbound catalog claiming classes and an
    outbound one claiming interfaces divide the same annotation between them,
    and neither reaches the other's declarations. Without it both catalogs
    would derive both rows, the two identities would merge (D02 §3), and a
    served operation would read as one the module also calls."""
    rows = _construct_gate_rows(
        tmp_path,
        [
            _construct_gate_catalog("class", "inbound", "invented-gate-class"),
            _construct_gate_catalog("interface", "outbound", "invented-gate-interface"),
        ],
    )
    assert rows == [("inbound", "serve"), ("outbound", "call")]


def test_a_catalog_declaring_no_construct_gate_still_derives_both(tmp_path: Path):
    """The inert value, and the regression that matters: every catalog written
    before this word declares none, and NULL applies its rules to a
    declaration regardless of what encloses it."""
    rows = _construct_gate_rows(
        tmp_path, [_construct_gate_catalog(None, "inbound", "invented-gate-none")]
    )
    assert rows == [("inbound", "call"), ("inbound", "serve")]


def test_an_unrecognised_construct_gate_is_refused(tmp_path: Path):
    """Read as "no gate", a typo would republish every served operation as one
    the module calls — the confidently-wrong-row class this file's other
    refusals exist for. Refused at run start instead, naming the file."""
    with pytest.raises(CatalogError) as raised:
        _construct_gate_rows(
            tmp_path, [_construct_gate_catalog("klass", "outbound", "invented-gate-typo")]
        )
    assert "declared_on" in str(raised.value)
    assert "invented-gate-typo.yml" in str(raised.value)


# --- 2I Task 5, fix round 1: the SEI fence -------------------------------
#
# `declared_on: interface` says a catalog's declarations sit on interfaces; an
# OUTBOUND one saying that is describing client stubs. An interface the module
# itself implements is the opposite claim, and the annotation family that marks
# a generated stub marks a hand-written service endpoint interface too. The
# fence is what makes the gate's own meaning true.


def _sei_facts(root: Path, with_local_impl: bool) -> None:
    """One `@Endpoint`-marked interface declaring one operation, optionally
    implemented by a local class that carries the same marker — the shape a
    JAX-WS SEI plus its `@WebService` implementation takes."""
    port, impl = "com/acme/wsish/Port#", "com/acme/wsish/PortImpl#"
    port_method = f"{port}charge(sig_1)."
    facts: list = [
        SymbolFact(document_id="doc_1", symbol=port, construct_kind=ConstructKind.INTERFACE),
        SymbolFact(
            document_id="doc_1",
            symbol=port_method,
            construct_kind=ConstructKind.METHOD,
            enclosing=port,
            signature=Signature(parameters=[], returns=TypeRef(symbol="void#")),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=port,
            retention="runtime",
            use=AnnotationUse(annotation="com/acme/wsish/Endpoint#", args={}),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=port_method,
            retention="runtime",
            use=AnnotationUse(annotation="com/acme/wsish/Operation#", args={"name": "charge"}),
        ),
    ]
    if with_local_impl:
        impl_method = f"{impl}charge(sig_1)."
        facts += [
            SymbolFact(
                document_id="doc_1",
                symbol=impl,
                construct_kind=ConstructKind.CLASS,
                interfaces=[port],
            ),
            SymbolFact(
                document_id="doc_1",
                symbol=impl_method,
                construct_kind=ConstructKind.METHOD,
                enclosing=impl,
                signature=Signature(parameters=[], returns=TypeRef(symbol="void#")),
            ),
            AnnotationFact(
                document_id="doc_1",
                target=impl,
                retention="runtime",
                use=AnnotationUse(annotation="com/acme/wsish/Endpoint#", args={}),
            ),
            AnnotationFact(
                document_id="doc_1",
                target=impl_method,
                retention="runtime",
                use=AnnotationUse(annotation="com/acme/wsish/Operation#", args={"name": "charge"}),
            ),
        ]
    write_fact_file(root / "Sei.jsonl", _GATE_DOCUMENT, facts)


def _sei_rows(tmp_path: Path, with_local_impl: bool) -> list[tuple[str, str, str | None]]:
    _sei_facts(tmp_path / "facts", with_local_impl)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    catalogs = [
        _construct_gate_catalog("class", "inbound", "invented-sei-server"),
        _construct_gate_catalog("interface", "outbound", "invented-sei-client"),
    ]
    assert derive_endpoints(workspace, catalogs, capabilities={"annotation_args"}) == []
    rows = [
        (str(e["direction"]), str(e["path"]), e["handler"] and str(e["handler"]))
        for e in workspace.query("endpoints")
    ]
    workspace.close()
    return sorted(rows)


def test_an_interface_this_module_implements_derives_no_outbound_row(tmp_path: Path):
    """An SEI plus its implementation is a SERVER, twice stated. Without the
    fence the interface derives an outbound row, the class derives an inbound
    one, the two share a wire identity, the merge folds them into `both`, and
    the module is published as calling what it only serves.

    With it, the operation derives exactly ONCE — from the implementing class,
    inbound, handler intact — because a class-gated catalog is untouched by
    the fence."""
    rows = _sei_rows(tmp_path, with_local_impl=True)
    assert rows == [("inbound", "charge", "com/acme/wsish/PortImpl#charge(sig_1).")]


def test_the_same_interface_with_no_local_implementation_still_derives_outbound(
    tmp_path: Path,
):
    """The stub case, unchanged — and the proof the fence subtracts on the
    IMPLEMENTED fact rather than on being an interface at all. Identical
    facts minus the implementing class: the outbound row derives, with no
    handler, exactly as a generated stub in an opted-in jar will."""
    rows = _sei_rows(tmp_path, with_local_impl=False)
    assert rows == [("outbound", "charge", None)]


def test_the_soap_template_catalog_skips_visibly_without_annotation_arguments(
    tmp_path: Path,
):
    """`requires` is the mechanism that keeps degradation visible (D02 §1).
    `spring-ws-template.yml`'s PRIMARY identity read is annotation attributes
    — `path_from_argument_type` reads them off the payload type — so a scanner
    that cannot report them derives no operation from any of its calls. The
    catalog says so and is SKIPPED by name rather than running and quietly
    producing address-only rows."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    catalog = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-ws-template")
    skipped = derive_endpoints(
        workspace, [catalog], capabilities={"call_site", "string_constants", "typed_signatures"}
    )
    workspace.close()

    assert skipped == [SkippedCatalog("spring-ws-template", ("annotation_args",))]


# --- 2O Task 7: the messaging and annotation catalogs, proved against the
# REAL shipped files (no fixture module carries any of these annotations yet
# — the 2H Task 5 precedent for `spring-websocket.yml`).
#
# Every catalog here is paired: one test that the rule FIRES, and one §10
# near-miss per matcher asserting that NOTHING is derived. The near-miss is
# derived from the rule's own conjuncts — an input satisfying every condition
# but one — because a suite where every fixture demonstrates the rule firing
# cannot tell you the rule declines correctly. This phase's worst defect was
# exactly that shape: an engine fabricated an endpoint out of an ordinary
# `extends` pair, and the golden fixture missed it by luck.

_TASK_7_CAPABILITIES = frozenset(
    {
        "annotation_args",
        # Capability 9.16, and required by the three listener catalogs since
        # they learned to name their repeatable container (`OI-36`): a folded
        # use reaches the class file only as a nested annotation. Without it
        # here those catalogs would be SKIPPED rather than run, which is the
        # visible failure the `requires` entry is for.
        "nested_annotation_args",
        "type_annotations",
        "typed_signatures",
        "call_site",
        "string_constants",
        "implemented_interfaces",
        "superclass",
        "generic_interfaces",
        "chain_reconstruction",
        "resolved_config",
    }
)


def _shipped(catalog_id: str) -> Catalog:
    return next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == catalog_id)


def _annotated_facts(
    root: Path,
    class_symbol: str,
    method_symbol: str,
    class_annotations: dict[str, dict] | None = None,
    method_annotations: dict[str, dict] | None = None,
) -> None:
    """One class, one method on it, and whatever annotations each carries.

    Annotations are keyed by the SCIP symbol form the facts carry (D00 §5a) —
    the same form `_seam_facts` writes — so a test states the fqn once and the
    catalog's own `_catalog_symbol` conversion is what has to agree with it.
    """
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/task7/Subject.java",
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
    facts: list[object] = [
        SymbolFact(document_id="doc_1", symbol=class_symbol, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=method_symbol,
            construct_kind=ConstructKind.METHOD,
            enclosing=class_symbol,
            visibility="public",
            signature=Signature(parameters=[], returns=TypeRef(symbol="void")),
        ),
    ]
    for target, declared in (
        (class_symbol, class_annotations or {}),
        (method_symbol, method_annotations or {}),
    ):
        for annotation, args in declared.items():
            facts.append(
                AnnotationFact(
                    document_id="doc_1",
                    target=target,
                    retention="runtime",
                    use=AnnotationUse(annotation=annotation, args=args),
                )
            )
    write_fact_file(root / "Subject.jsonl", document, facts)


def _rows_from(tmp_path: Path, catalogs: list[Catalog], **facts: object) -> list[dict[str, object]]:
    _annotated_facts(tmp_path / "facts", **facts)  # type: ignore[arg-type]
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    derive_endpoints(workspace, catalogs, capabilities=set(_TASK_7_CAPABILITIES))
    rows = workspace.query("endpoints")
    workspace.close()
    return rows


_LISTENER_CLASS = "com/acme/task7/Subject#"
_LISTENER_METHOD = "com/acme/task7/Subject#onMessage(sig_7a1)."
_RABBIT_LISTENER = "org/springframework/amqp/rabbit/annotation/RabbitListener#"
_RABBIT_HANDLER = "org/springframework/amqp/rabbit/annotation/RabbitHandler#"


def test_a_rabbit_listener_derives_one_inbound_amqp_row_per_declared_queue(tmp_path: Path):
    """The queue names arrive as a `String[]` on `queues` (javap, spring-rabbit
    3.1.4), and a multi-queue listener is that many wire identities — one
    method serving two queues is two destinations, not one."""
    rows = _rows_from(
        tmp_path,
        [_shipped("spring-rabbit")],
        class_symbol=_LISTENER_CLASS,
        method_symbol=_LISTENER_METHOD,
        method_annotations={_RABBIT_LISTENER: {"queues": ["orders.q", "orders.dlq"]}},
    )

    assert {(r["protocol"], r["direction"], r["method"], r["path"]) for r in rows} == {
        ("amqp", "inbound", None, "orders.q"),
        ("amqp", "inbound", None, "orders.dlq"),
    }
    assert {r["handler"] for r in rows} == {_LISTENER_METHOD}


def test_a_class_level_rabbit_listener_gives_its_queue_to_every_rabbit_handler(tmp_path: Path):
    """The polymorphic shape: the class-level `@RabbitListener` carries no
    method of its own to map, so it doubles as the prefix, and a
    `@RabbitHandler` — which declares no queue attribute at all — reaches a
    destination only through it. The queue name is composed BARE, with no
    separator: a queue name has no segments, and a `/` here would invent a
    destination no broker carries."""
    rows = _rows_from(
        tmp_path,
        [_shipped("spring-rabbit")],
        class_symbol=_LISTENER_CLASS,
        method_symbol=_LISTENER_METHOD,
        class_annotations={_RABBIT_LISTENER: {"queues": ["orders.q"]}},
        method_annotations={_RABBIT_HANDLER: {}},
    )

    assert [(r["protocol"], r["path"], r["handler"]) for r in rows] == [
        ("amqp", "orders.q", _LISTENER_METHOD)
    ]


@pytest.mark.declines("spring-rabbit")
@pytest.mark.pins("derive_endpoints.addresses-nothing")
def test_a_rabbit_handler_on_a_class_carrying_no_listener_derives_nothing(tmp_path: Path):
    """§10 near-miss for the polymorphic matcher, negating its second
    conjunct: the method is annotated exactly as a real handler is, and the
    enclosing class carries no `@RabbitListener`.

    `@RabbitHandler` states no destination of its own, so the only thing such
    a row could carry is the EMPTY address — a resolved endpoint addressing
    nothing, which is mechanism 3's addresses-nothing gate. Spring itself
    derives nothing here: `@RabbitHandler` outside a class-level
    `@RabbitListener` is never registered with any container.

    **It names the addresses-nothing gate, and it used to name the qualifier
    scope.** `spring-rabbit.yml` declares no `requires_qualifier` at all, so
    that conjunct is a no-op for this catalog and the guard name was simply
    false — the same correction the harness forced on two of its own names.
    Measured both ways by `scripts/guard_check.py`: disabling the
    addresses-nothing gate ALONE fails this test; disabling the qualifier gate
    alone does not.

    Paired positive:
    `test_a_class_level_rabbit_listener_gives_its_queue_to_every_rabbit_handler`
    — the same `@RabbitHandler`, under a class that names the queue.
    """
    rows = _rows_from(
        tmp_path,
        [_shipped("spring-rabbit")],
        class_symbol=_LISTENER_CLASS,
        method_symbol=_LISTENER_METHOD,
        method_annotations={_RABBIT_HANDLER: {}},
    )

    assert rows == []


_PULSAR_LISTENER = "org/springframework/pulsar/annotation/PulsarListener#"


def test_a_pulsar_listener_derives_one_inbound_pulsar_row_per_declared_topic(tmp_path: Path):
    """`topics` is a `String[]` and `topicPattern` a scalar `String` (javap,
    spring-pulsar 1.2.11) — the `@KafkaListener` shape, so the same
    scalar-or-array, first-alias-wins read serves both."""
    rows = _rows_from(
        tmp_path,
        [_shipped("spring-pulsar")],
        class_symbol=_LISTENER_CLASS,
        method_symbol=_LISTENER_METHOD,
        method_annotations={_PULSAR_LISTENER: {"topics": ["persistent://public/default/orders"]}},
    )

    assert [(r["protocol"], r["direction"], r["path"]) for r in rows] == [
        ("pulsar", "inbound", "persistent://public/default/orders")
    ]


@pytest.mark.declines("spring-pulsar")
@pytest.mark.pins("derive_endpoints.handler-is-a-method")
def test_a_type_level_pulsar_listener_alone_derives_nothing(tmp_path: Path):
    """§10 near-miss for the Pulsar matcher, negating the conjunct that the
    annotation sits on a METHOD. `@PulsarListener` is
    `@Target({TYPE, METHOD, ANNOTATION_TYPE})`, but the framework ships no
    class-level handler annotation for it to dispatch to, so a type-level use
    registers no listener and names no destination for any method of the
    class. A row here would give every method of an annotated class the
    class's own topic — endpoints nobody serves."""
    rows = _rows_from(
        tmp_path,
        [_shipped("spring-pulsar")],
        class_symbol=_LISTENER_CLASS,
        method_symbol=_LISTENER_METHOD,
        class_annotations={_PULSAR_LISTENER: {"topics": ["persistent://public/default/orders"]}},
    )

    assert rows == []


_PULSAR_LISTENERS = "org/springframework/pulsar/annotation/PulsarListeners#"
_PULSAR_READER = "org/springframework/pulsar/annotation/PulsarReader#"


@pytest.mark.pins("spring-pulsar.container-is-the-frameworks-own")
def test_two_pulsar_listeners_held_in_the_container_derive_both_topics(tmp_path: Path):
    """`OI-38`. CP-17 rows 3a/3b read
    `org.springframework.pulsar.annotation.PulsarListeners` out of spring-pulsar
    1.2.11 and 2.0.7 declaring `value(): PulsarListener[]`, and rows 6a/6b show
    the post-processor adding every member of it to the listener set. Before
    the container was named, a method declaring its topics this way derived
    NOTHING — beside a single-listener neighbour deriving normally, which is
    the shape that makes an under-report hard to notice."""
    rows = _rows_from(
        tmp_path,
        [_shipped("spring-pulsar")],
        class_symbol=_LISTENER_CLASS,
        method_symbol=_LISTENER_METHOD,
        method_annotations={
            _PULSAR_LISTENERS: {
                "value": [
                    _folded_use(_PULSAR_LISTENER, {"topics": ["orders.v1"]}),
                    _folded_use(_PULSAR_LISTENER, {"topics": ["orders.dlq"]}),
                ]
            }
        },
    )

    assert {(str(r["protocol"]), str(r["path"])) for r in rows} == {
        ("pulsar", "orders.v1"),
        ("pulsar", "orders.dlq"),
    }


@pytest.mark.pins("spring-pulsar.container-is-the-frameworks-own")
def test_a_pulsar_container_beside_a_direct_listener_derives_the_union(tmp_path: Path):
    """**The case that cannot exist for a `@Repeatable` annotation**, and the
    reason this catalog's `container` entry means something slightly different
    from `spring-kafka.yml`'s. CP-17 rows 2a/2b measured NO `@Repeatable` on
    `@PulsarListener`, so javac never folds and a declaration may legally carry
    both a direct `@PulsarListener` AND a hand-written `@PulsarListeners`. Rows
    6a/6b are what say the framework registers the union of the two rather than
    one instead of the other:

        PulsarListener ann = findMergedAnnotation(method, PulsarListener.class);
        if (ann != null) { listeners.add(ann); }
        PulsarListeners anns = findAnnotation(method, PulsarListeners.class);
        if (anns != null) { listeners.addAll(...anns.value()...); }

    Three topics served, so three rows — the direct annotation's row survives
    beside the synthesized ones because the unfolding pass ADDS and never
    replaces."""
    rows = _rows_from(
        tmp_path,
        [_shipped("spring-pulsar")],
        class_symbol=_LISTENER_CLASS,
        method_symbol=_LISTENER_METHOD,
        method_annotations={
            _PULSAR_LISTENER: {"topics": ["orders.direct"]},
            _PULSAR_LISTENERS: {
                "value": [
                    _folded_use(_PULSAR_LISTENER, {"topics": ["orders.v1"]}),
                    _folded_use(_PULSAR_LISTENER, {"topics": ["orders.dlq"]}),
                ]
            },
        },
    )

    assert {(str(r["protocol"]), str(r["path"])) for r in rows} == {
        ("pulsar", "orders.direct"),
        ("pulsar", "orders.v1"),
        ("pulsar", "orders.dlq"),
    }


@pytest.mark.pins("spring-pulsar.reader-is-a-second-inbound-surface")
def test_a_pulsar_reader_derives_one_inbound_pulsar_row_per_declared_topic(tmp_path: Path):
    """`OI-39`. `@PulsarReader` is a second inbound surface of the same
    framework and this catalog named it nowhere. CP-17 rows 1c/1d read
    `topics(): java.lang.String[]` off its own class file at spring-pulsar
    1.2.11 and 2.0.7; rows 5c/5d show `PulsarReaderAnnotationBeanPostProcessor`
    reading `PulsarReader.topics()` and feeding
    `MethodPulsarReaderEndpoint.setTopics([Ljava/lang/String;)` before
    registering the endpoint. Every reader in a scanned module was absent from
    the export."""
    rows = _rows_from(
        tmp_path,
        [_shipped("spring-pulsar")],
        class_symbol=_LISTENER_CLASS,
        method_symbol=_LISTENER_METHOD,
        method_annotations={_PULSAR_READER: {"topics": ["persistent://public/default/audit"]}},
    )

    assert [(r["protocol"], r["direction"], r["path"]) for r in rows] == [
        ("pulsar", "inbound", "persistent://public/default/audit")
    ]


@pytest.mark.declines("spring-pulsar")
@pytest.mark.pins("derive_endpoints.handler-is-a-method")
def test_a_type_level_pulsar_reader_alone_derives_nothing(tmp_path: Path):
    """§10 near-miss for the reader entry above, negating the conjunct that the
    annotation sits on a METHOD. `@PulsarReader` is
    `@Target({TYPE, METHOD, ANNOTATION_TYPE})` (CP-17 rows 2c/2d) and its
    discovery method takes a `Method` and nothing else (rows 6c/6d), so a
    type-level use registers no reader. A row here would give every method of
    an annotated class the class's own topic."""
    rows = _rows_from(
        tmp_path,
        [_shipped("spring-pulsar")],
        class_symbol=_LISTENER_CLASS,
        method_symbol=_LISTENER_METHOD,
        class_annotations={_PULSAR_READER: {"topics": ["persistent://public/default/audit"]}},
    )

    assert rows == []


_LEGACY_SPRING_SQS = "org/springframework/cloud/aws/messaging/listener/annotation/SqsListener#"
_LEGACY_AWSPRING_SQS = "io/awspring/cloud/messaging/listener/annotation/SqsListener#"
_CURRENT_SQS = "io/awspring/cloud/sqs/annotation/SqsListener#"


@pytest.mark.parametrize("annotation", [_LEGACY_SPRING_SQS, _LEGACY_AWSPRING_SQS])
def test_both_legacy_sqs_spellings_derive_the_same_inbound_row(tmp_path: Path, annotation: str):
    """The annotation moved package twice and kept its shape: both legacy
    spellings declare exactly `value()` as `String[]` and `deletionPolicy()`
    and nothing else (CP-17 rows 1g/1h, at
    org.springframework.cloud:spring-cloud-aws-messaging 2.2.6.RELEASE and
    io.awspring.cloud:spring-cloud-aws-messaging 2.4.4). That is why the file
    is pure data — one more `annotations` entry, no engine word.

    Rows 5g/5h are what make `value` the destination rather than an attribute
    that resembles one: `QueueMessageHandler` reads `value()` and
    `deletionPolicy()` and no third attribute, in either generation."""
    rows = _rows_from(
        tmp_path,
        [_shipped("spring-sqs-legacy")],
        class_symbol=_LISTENER_CLASS,
        method_symbol=_LISTENER_METHOD,
        method_annotations={annotation: {"value": ["orders-queue"]}},
    )

    assert [(r["protocol"], r["direction"], r["path"]) for r in rows] == [
        ("sqs", "inbound", "orders-queue")
    ]


@pytest.mark.declines("spring-sqs-legacy")
@pytest.mark.pins("derive_endpoints.mapping-annotation-fqn")
def test_the_legacy_sqs_catalog_declines_the_current_annotation(tmp_path: Path):
    """§10 near-miss for the legacy matchers: the CURRENT 3.x annotation is
    the same simple name, the same `value` attribute and the same protocol —
    everything but the package. `spring-sqs.yml` is the file that describes
    it, and it is a different dependency coordinate; a legacy catalog that
    also matched it would claim a module declares an artifact it does not,
    and would double every current listener's row once the two catalogs
    both ran."""
    rows = _rows_from(
        tmp_path,
        [_shipped("spring-sqs-legacy")],
        class_symbol=_LISTENER_CLASS,
        method_symbol=_LISTENER_METHOD,
        method_annotations={_CURRENT_SQS: {"value": ["orders-queue"]}},
    )

    assert rows == []


_SQS_HANDLER = "io/awspring/cloud/sqs/annotation/SqsHandler#"


@pytest.mark.pins("spring-sqs.class-level-listener-is-the-prefix")
def test_a_class_level_sqs_listener_gives_its_queue_to_every_sqs_handler(tmp_path: Path):
    """`OI-40`. spring-cloud-aws-sqs **4.1.1** widened `@SqsListener`'s
    `@Target` from `{METHOD}` to `{METHOD, TYPE}` and shipped `@SqsHandler`
    (CP-17 rows 2e/2f and 4e/4f), and its post-processor grew the branch that
    builds a `MultiMethodSqsEndpoint` from the CLASS-level annotation's own
    `value()` and dispatches to every `@SqsHandler` method (row 6f, against row
    6e's same method at 3.1.1 which has no such branch at all).

    So this is the `spring-kafka.yml` polymorphic shape one framework over, and
    the catalog said in as many words that SQS has none — true at 3.1.1, false
    at 4.1.1, and every `@SqsHandler` method in a 4.x module was absent from the
    export. The queue name is composed BARE, with no separator: a queue name has
    no segments, and a `/` here would invent a destination no broker carries."""
    rows = _rows_from(
        tmp_path,
        [_shipped("spring-sqs")],
        class_symbol=_LISTENER_CLASS,
        method_symbol=_LISTENER_METHOD,
        class_annotations={_CURRENT_SQS: {"value": ["orders-queue"]}},
        method_annotations={_SQS_HANDLER: {}},
    )

    assert [(r["protocol"], r["path"], r["handler"]) for r in rows] == [
        ("sqs", "orders-queue", _LISTENER_METHOD)
    ]


@pytest.mark.declines("spring-sqs")
@pytest.mark.pins("derive_endpoints.addresses-nothing")
def test_an_sqs_handler_on_a_class_carrying_no_listener_derives_nothing(tmp_path: Path):
    """§10 near-miss for the polymorphic matcher above, negating its second
    conjunct: the method is annotated exactly as a real handler is, and the
    enclosing class carries no `@SqsListener`.

    `@SqsHandler` declares `isDefault(): boolean` and nothing else (CP-17 row
    4f/1n), so the only thing such a row could carry is the EMPTY address — a
    resolved endpoint addressing nothing. The framework derives nothing here
    either: row 6f registers the multi-method endpoint only under
    `hasClassLevelListeners`, so a handler with no class-level listener above it
    reaches no container at all.

    Paired positive:
    `test_a_class_level_sqs_listener_gives_its_queue_to_every_sqs_handler`."""
    rows = _rows_from(
        tmp_path,
        [_shipped("spring-sqs")],
        class_symbol=_LISTENER_CLASS,
        method_symbol=_LISTENER_METHOD,
        method_annotations={_SQS_HANDLER: {"isDefault": True}},
    )

    assert rows == []


_ENDPOINT = "org/springframework/boot/actuate/endpoint/annotation/Endpoint#"
_READ_OPERATION = "org/springframework/boot/actuate/endpoint/annotation/ReadOperation#"
_WRITE_OPERATION = "org/springframework/boot/actuate/endpoint/annotation/WriteOperation#"
_DELETE_OPERATION = "org/springframework/boot/actuate/endpoint/annotation/DeleteOperation#"


@pytest.mark.parametrize(
    ("operation", "verb"),
    [(_READ_OPERATION, "GET"), (_WRITE_OPERATION, "POST"), (_DELETE_OPERATION, "DELETE")],
)
def test_an_actuator_operation_is_served_under_the_constant_prefix_with_its_own_verb(
    tmp_path: Path, operation: str, verb: str
):
    """CP-5 rows 1-3, confirmed live on Boot 3.5.10 and 4.1.1: the address is
    `/actuator/<id>` and the verb is the operation annotation's own. The id
    lives on the TYPE and the verb on the METHOD, so neither half alone is an
    endpoint — which is exactly why the catalog gates on both."""
    rows = _rows_from(
        tmp_path,
        [_shipped("spring-actuator")],
        class_symbol=_LISTENER_CLASS,
        method_symbol=_LISTENER_METHOD,
        class_annotations={_ENDPOINT: {"id": "probe"}},
        method_annotations={operation: {}},
    )

    assert [(r["protocol"], r["direction"], r["method"], r["path"]) for r in rows] == [
        ("http", "inbound", verb, "/actuator/probe")
    ]


def test_an_endpoint_class_with_no_operation_annotation_derives_nothing(tmp_path: Path):
    """CP-5 row 6 measured rather than assumed: an `@Endpoint` class whose
    methods carry no operation annotation serves nothing — `GET
    /actuator/empty` was a 404 on both versions probed, and the endpoint did
    not appear in the discovery document at all.

    **It carries NO `declines` or `pins` marker, and that is a finding rather
    than an omission.** Its emptiness has two independent causes and pins
    neither. Making `@Endpoint` a mapping annotation of its own — the
    "class-level rule" this used to say it negated — mints a declaration whose
    target is a CLASS, and `@Endpoint` is `@Target(TYPE)` so it can sit nowhere
    else; every such declaration is dropped by the
    `construct_kind IN ('method', 'function')` join regardless of what the
    catalog says. So no single guard's absence makes a row appear here, and a
    marker would have declared coverage nothing verifies — which the guard
    harness measured and this docstring now records.

    `spring-actuator`'s declining coverage is
    `test_an_actuator_operation_outside_an_endpoint_class_derives_nothing`,
    which negates the other conjunct and does discriminate."""
    rows = _rows_from(
        tmp_path,
        [_shipped("spring-actuator")],
        class_symbol=_LISTENER_CLASS,
        method_symbol=_LISTENER_METHOD,
        class_annotations={_ENDPOINT: {"id": "empty"}},
    )

    assert rows == []


@pytest.mark.declines("spring-actuator")
@pytest.mark.pins("derive_endpoints.type-annotation-gate")
def test_an_actuator_operation_outside_an_endpoint_class_derives_nothing(tmp_path: Path):
    """§10 near-miss on the other conjunct: the operation annotation is
    present and the class gate is not. The operation annotations carry no
    address at all, so such a row could only ever be `/actuator` itself —
    the discovery document, which this method does not serve."""
    rows = _rows_from(
        tmp_path,
        [_shipped("spring-actuator")],
        class_symbol=_LISTENER_CLASS,
        method_symbol=_LISTENER_METHOD,
        method_annotations={_READ_OPERATION: {}},
    )

    assert rows == []


_KAFKA_LISTENER = "org/springframework/kafka/annotation/KafkaListener#"
_JMS_LISTENER = "org/springframework/jms/annotation/JmsListener#"


@pytest.mark.declines("spring-kafka")
@pytest.mark.pins("spring-kafka.path-from-is-the-topic-attributes")
def test_a_kafka_listener_declaring_only_a_group_id_derives_nothing(tmp_path: Path):
    """§10 near-miss on the alias set, `spring-scheduling`'s `initialDelay`
    shape one framework over. `groupId` is a real `@KafkaListener` attribute, a
    `String` exactly as `topicPattern` is, and CP-16 row 4 measures the
    post-processor reading it at spring-kafka 3.1.4 and 4.1.1 — but it names
    the CONSUMER GROUP a service joins, not a topic it consumes. Reading it
    would publish `orders-consumers` as a Kafka destination: an address no
    broker carries, at `resolved`/`compiler`, indistinguishable downstream from
    a topic somebody wrote.

    Every other conjunct holds — the shipped annotation, spelled in full, on a
    method, with an argument this pass can read."""
    rows = _rows_from(
        tmp_path,
        [_shipped("spring-kafka")],
        class_symbol=_LISTENER_CLASS,
        method_symbol=_LISTENER_METHOD,
        method_annotations={_KAFKA_LISTENER: {"groupId": "orders-consumers"}},
    )

    assert rows == []


@pytest.mark.declines("spring-jms")
@pytest.mark.pins("spring-jms.path-from-is-the-destination-attribute")
def test_a_jms_listener_declaring_only_a_subscription_derives_nothing(tmp_path: Path):
    """§10 near-miss on the alias set. `subscription` is a real `@JmsListener`
    attribute, it is a `String` exactly as `destination` is, it sits directly
    beside it in the annotation, and CP-16 row 4 measures the post-processor
    reading both at spring-jms 6.1.6 and 7.0.9. It names the DURABLE
    SUBSCRIPTION a consumer registers under, not the queue or topic a message
    arrives on — so reading it publishes a name the broker does not route to.

    `@JmsListener` declares six attributes and exactly one is an address (CP-16
    row 1), which is what makes the other five the near-miss set rather than
    one chosen example."""
    rows = _rows_from(
        tmp_path,
        [_shipped("spring-jms")],
        class_symbol=_LISTENER_CLASS,
        method_symbol=_LISTENER_METHOD,
        method_annotations={_JMS_LISTENER: {"subscription": "orders-durable"}},
    )

    assert rows == []


# --- `OI-36`: the repeatable container, against the three shipped catalogs --
#
# javac writes the CONTAINER and not the annotation when one is used twice on a
# declaration (JLS 9.7.5), so the class file below carries no listener
# annotation at all — which is why these read as "two destinations from a fact
# that mentions neither". CP-16 rows 2 and 4 measured the container and the
# post-processor's read of it at six versions across the three frameworks.


def _folded_use(annotation: str, args: dict[str, object]) -> AnnotationUse:
    return AnnotationUse(annotation=annotation, args=args)


@pytest.mark.pins("spring-kafka.container-is-the-frameworks-own")
def test_two_kafka_listeners_on_one_method_derive_both_topics(tmp_path: Path):
    """CP-16 rows 2a/2b and 4a/4b: `@KafkaListener` is
    `@Repeatable(KafkaListeners.class)` at 3.1.4 and 4.1.1, and the
    post-processor calls `KafkaListeners.value()`. So the framework registers
    both listeners while this repository saw nothing at all — a silent
    under-report beside a single-listener neighbour deriving normally, which is
    the shape that makes it hard to notice."""
    rows = _rows_from(
        tmp_path,
        [_shipped("spring-kafka")],
        class_symbol=_LISTENER_CLASS,
        method_symbol=_LISTENER_METHOD,
        method_annotations={
            "org/springframework/kafka/annotation/KafkaListeners#": {
                "value": [
                    _folded_use(_KAFKA_LISTENER, {"topics": ["orders.v1"]}),
                    _folded_use(_KAFKA_LISTENER, {"topics": ["orders.dlq"]}),
                ]
            }
        },
    )

    assert {(str(r["protocol"]), str(r["path"])) for r in rows} == {
        ("kafka", "orders.v1"),
        ("kafka", "orders.dlq"),
    }


@pytest.mark.pins("spring-jms.container-is-the-frameworks-own")
def test_two_jms_listeners_on_one_method_derive_both_destinations(tmp_path: Path):
    """CP-16 rows 2c/2d and 4c/4d: `@JmsListener` is
    `@Repeatable(JmsListeners.class)` at 6.1.6 and 7.0.9, and the post-processor
    calls `getMergedRepeatableAnnotations(element, JmsListener, JmsListeners)` —
    naming BOTH classes, which is the framework saying in its own words that the
    container is part of the rule."""
    rows = _rows_from(
        tmp_path,
        [_shipped("spring-jms")],
        class_symbol=_LISTENER_CLASS,
        method_symbol=_LISTENER_METHOD,
        method_annotations={
            "org/springframework/jms/annotation/JmsListeners#": {
                "value": [
                    _folded_use(_JMS_LISTENER, {"destination": "orders.queue"}),
                    _folded_use(_JMS_LISTENER, {"destination": "orders.retry"}),
                ]
            }
        },
    )

    assert {(str(r["protocol"]), str(r["path"])) for r in rows} == {
        ("jms", "orders.queue"),
        ("jms", "orders.retry"),
    }


@pytest.mark.pins("spring-rabbit.container-is-the-frameworks-own")
def test_two_rabbit_listeners_on_one_method_derive_both_queues(tmp_path: Path):
    """CP-16 rows 2e/2f and 4e: `@RabbitListener` is
    `@Repeatable(RabbitListeners.class)` at 3.1.4 and 4.1.1, and 3.1.4's
    post-processor streams `RabbitListener` out of a `MergedAnnotations` view,
    which is the container-aware read."""
    rows = _rows_from(
        tmp_path,
        [_shipped("spring-rabbit")],
        class_symbol=_LISTENER_CLASS,
        method_symbol=_LISTENER_METHOD,
        method_annotations={
            "org/springframework/amqp/rabbit/annotation/RabbitListeners#": {
                "value": [
                    _folded_use(_RABBIT_LISTENER, {"queues": ["orders.q"]}),
                    _folded_use(_RABBIT_LISTENER, {"queues": ["orders.dlq"]}),
                ]
            }
        },
    )

    assert {(str(r["protocol"]), str(r["path"])) for r in rows} == {
        ("amqp", "orders.q"),
        ("amqp", "orders.dlq"),
    }


_GRAPHQL_API = "org/eclipse/microprofile/graphql/GraphQLApi#"
_MP_QUERY = "org/eclipse/microprofile/graphql/Query#"
_MP_MUTATION = "org/eclipse/microprofile/graphql/Mutation#"
_MP_NAME = "org/eclipse/microprofile/graphql/Name#"


def test_a_microprofile_query_naming_its_own_operation_derives_that_name(tmp_path: Path):
    """The half CP-15 leaves untouched, and the reason `path_fallback` was
    carried rather than dropped: an operation that NAMES itself is read from
    its own `value` and reaches the same address SmallRye serves —
    `getOperationName` consults the operation annotation's value first, before
    every other source and before any transformation (CP-15 rows 1 and 3, at
    smallrye-graphql-schema-builder 2.0.0 and 2.18.5)."""
    rows = _rows_from(
        tmp_path,
        [_shipped("microprofile-graphql")],
        class_symbol=_LISTENER_CLASS,
        method_symbol=_LISTENER_METHOD,
        class_annotations={_GRAPHQL_API: {}},
        method_annotations={_MP_QUERY: {"value": "orders"}},
    )

    assert [(r["protocol"], r["direction"], r["method"], r["path"]) for r in rows] == [
        ("graphql", "inbound", "query", "orders")
    ]


@pytest.mark.pins("microprofile-graphql.fallback-direction-is-per-annotation")
def test_a_microprofile_operation_falls_back_to_the_name_smallrye_serves(tmp_path: Path):
    """**This assertion used to be the defect** (`OI-5`). It read
    `== ["getOrders"]` and was named
    `..._publishes_the_wrong_address`: a characterisation test of a known-wrong
    output, written so the defect was a fact in the suite rather than a
    paragraph in a register, with the register saying "the day the grammar can
    say it, this assertion is what changes". This is that day.

    CP-15 row 5 compiled `MethodHelper.getPropertyName` against both measured
    SmallRye jars and RAN it: `getOrders -> OUT orders`, `setStatus -> IN
    status`. And the direction is chosen by WHICH annotation matched — `@Query`
    takes `OUT`, `@Mutation` takes `IN` (row 3) — which is why both are asserted
    here together, on two methods whose names are each the OTHER direction's
    accessor. A catalog carrying one word for both cannot produce this pair: it
    publishes `getOrders` or `setStatus` unchanged, whichever way it leans."""
    rows = _rows_from(
        tmp_path,
        [_shipped("microprofile-graphql")],
        class_symbol="com/acme/task7/Orders#",
        method_symbol="com/acme/task7/Orders#getOrders(sig_mp1).",
        class_annotations={_GRAPHQL_API: {}},
        method_annotations={_MP_QUERY: {}},
    )
    mutations = _rows_from(
        tmp_path / "mutation",
        [_shipped("microprofile-graphql")],
        class_symbol="com/acme/task7/Orders#",
        method_symbol="com/acme/task7/Orders#setStatus(sig_mp2).",
        class_annotations={_GRAPHQL_API: {}},
        method_annotations={_MP_MUTATION: {}},
    )

    assert [r["path"] for r in rows] == ["orders"]
    assert [r["path"] for r in mutations] == ["status"]


@pytest.mark.pins("microprofile-graphql.name-sources-are-the-measured-annotations")
def test_a_microprofile_operation_renamed_by_a_sibling_annotation_takes_that_name(
    tmp_path: Path,
):
    """`OI-35`. `getOperationName` consults five sources in order and takes the
    first with a value (CP-15 rows 1-2), and the specification's own renaming
    annotation — `@Name` — is the second. So
    `@Query @Name("allOrders") List<Order> orders()` is SERVED as `allOrders`,
    while this catalog published `orders` until it could name a sibling source.

    The `@Query` here carries NO value of its own, which is what puts the
    sibling in play at all: CP-15 row 1 puts the matched annotation's own value
    first, and `test_a_microprofile_query_naming_its_own_operation_derives_that_name`
    above is the other half of that order."""
    rows = _rows_from(
        tmp_path,
        [_shipped("microprofile-graphql")],
        class_symbol="com/acme/task7/Orders#",
        method_symbol="com/acme/task7/Orders#getOrders(sig_mp1).",
        class_annotations={_GRAPHQL_API: {}},
        method_annotations={_MP_QUERY: {}, _MP_NAME: {"value": "allOrders"}},
    )

    assert [r["path"] for r in rows] == ["allOrders"]


@pytest.mark.declines("microprofile-graphql")
@pytest.mark.pins("derive_endpoints.type-annotation-gate")
def test_a_microprofile_query_outside_a_graphql_api_class_derives_nothing(tmp_path: Path):
    """§10 near-miss on the conjunct this catalog rests on. `@Query` carries no
    address of its own beyond a name, and `@GraphQLApi` on the enclosing type
    is the only thing separating an operation SmallRye scans from a method that
    merely borrowed the annotation's simple name — the sweep ranks this catalog
    in tier 3 for exactly that reason.

    Every other conjunct holds: the operation annotation is present, spelled in
    full, on a method, with a value it could publish. Without the type gate
    this class's method becomes a resolved GraphQL operation at `orders` that
    no schema declares."""
    rows = _rows_from(
        tmp_path,
        [_shipped("microprofile-graphql")],
        class_symbol=_LISTENER_CLASS,
        method_symbol=_LISTENER_METHOD,
        method_annotations={_MP_QUERY: {"value": "orders"}},
    )

    assert rows == []


def test_a_web_filter_derives_nothing_from_any_shipped_catalog(tmp_path: Path):
    """§10 near-miss for the STATED BOUNDARY rather than for one matcher.

    `@WebFilter` is a servlet-container registration carrying `urlPatterns` —
    an annotation that looks exactly like an address-bearing inbound mapping
    and is not one: a filter intercepts URLs that other components serve, and
    publishing its patterns as endpoints would invent a service surface out of
    cross-cutting plumbing. No shipped catalog claims it, and this asserts that
    against EVERY shipped catalog at once rather than against the one that
    might have — the check that would have caught this phase's worst defect,
    where an engine fabricated an endpoint out of an ordinary `extends` pair
    and the golden fixture missed it by luck.

    Servlet registration is Task 7b's subject, and `@WebFilter` is not in it.
    """
    rows = _rows_from(
        tmp_path,
        YamlCatalogSource(CATALOGS).load(),
        class_symbol="com/acme/task7/AuditFilter#",
        method_symbol="com/acme/task7/AuditFilter#doFilter(sig_7b2).",
        class_annotations={
            "jakarta/servlet/annotation/WebFilter#": {"urlPatterns": ["/api/*"]},
        },
    )

    assert rows == []


# --- `A-C7` (principles sweep §3.2): the handler gate is a predicate --------


def _stereotype_facts(root: Path, *, meta_annotated: bool) -> None:
    """A module-local stereotype and one controller wearing it.

    `@MyApi` is an ordinary annotation type this module compiles, so its own
    `@Controller` — or, in the near-miss, its absence — is sitting in the
    `annotations` facts like any other annotation-on-a-type row. The controller
    itself carries NO framework stereotype at all, which is the whole point:
    Spring's handler test is a predicate over the composition, so `@MyApi`
    alone makes this a handler.
    """
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/api/OrderApi.java",
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
    stereotype = "com/acme/api/MyApi#"
    controller = "com/acme/api/OrderApi#"
    list_ = "com/acme/api/OrderApi#list(sig_08c5be17)."
    facts: list = [
        # An annotation type is an interface in bytecode, which is what puts it
        # in `interface_symbols` — the module-local half of the composition
        # rule (a stereotype living in a jar is out of reach, D02 §7).
        SymbolFact(document_id="doc_1", symbol=stereotype, construct_kind=ConstructKind.INTERFACE),
        SymbolFact(document_id="doc_1", symbol=controller, construct_kind=ConstructKind.CLASS),
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
            use=AnnotationUse(annotation=stereotype, args={}),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=list_,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/GetMapping#",
                args={"value": ["/orders"]},
            ),
        ),
    ]
    if meta_annotated:
        facts.insert(
            3,
            AnnotationFact(
                document_id="doc_1",
                target=stereotype,
                retention="runtime",
                use=AnnotationUse(annotation="org/springframework/stereotype/Controller#", args={}),
            ),
        )
    write_fact_file(root / "OrderApi.jsonl", document, facts)


def _stereotype_rows(tmp_path: Path, *, meta_annotated: bool) -> list[tuple]:
    _stereotype_facts(tmp_path / "facts", meta_annotated=meta_annotated)
    catalog = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-mvc")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    derive_endpoints(workspace, [catalog], capabilities={"annotation_args", "type_annotations"})
    rows = [(r["method"], r["path"]) for r in workspace.query("endpoints")]
    workspace.close()
    return rows


def test_a_module_local_stereotype_meta_annotated_controller_is_a_handler(tmp_path: Path):
    """`A-C7`. Spring's server-side handler test is
    `AnnotatedElementUtils.hasAnnotation(beanType, Controller.class)` — a
    four-instruction body, identical across spring-webmvc 6.1.6, 6.2.15, 7.0.2
    and 7.0.9 (CP-11 Q2) — and `AnnotatedElementUtils.hasAnnotation` is
    meta-annotation aware. The catalogs encoded string equality against one
    FQN over the type's own direct annotations, so a controller wearing a
    module-local `@MyApi` composed from `@RestController` matched nothing and
    **every endpoint of that controller disappeared from the export**: a
    silent drop of a whole HTTP surface, which is the failure §8's second
    clause names.

    The composition pre-pass already answered exactly this question for
    METHOD-level mapping annotations and its own docstring said so. The type
    gate simply was never widened with it."""
    assert _stereotype_rows(tmp_path, meta_annotated=True) == [("GET", "/orders")]


def test_a_module_local_annotation_composed_from_nothing_is_not_a_handler(tmp_path: Path):
    """The paired near-miss, and the reason widening the gate is safe: the
    same controller wearing the same annotation, with the annotation's own
    `@Controller` removed, derives NOTHING. What makes the class a handler is
    the composition, never the fact that some module-local annotation is on
    it — a gate that matched any annotated class would publish every
    `@Component`, `@Service` and home-grown marker in the module as a
    controller."""
    assert _stereotype_rows(tmp_path, meta_annotated=False) == []


# --- `A-C1` / `A-C6`: the gates that say which declaration is real ----------


def _gate_facts(
    root: Path,
    *,
    owner_kind: ConstructKind,
    type_annotations: dict[str, dict],
    method_annotation: str,
    method_args: dict,
) -> None:
    """One type of the given construct kind carrying the given type-level
    annotations, and one method on it carrying one mapping annotation.

    Deliberately generic: the four gates below differ only in which of those
    three knobs the framework's own rule turns, and writing four near-identical
    fact builders is how a near-miss ends up differing from its positive in
    more than the one conjunct under test."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/gate/Subject.java",
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
    owner = "com/acme/gate/Subject#"
    handler = "com/acme/gate/Subject#onMessage(sig_5a5a5a5a)."
    facts: list = [
        SymbolFact(document_id="doc_1", symbol=owner, construct_kind=owner_kind),
        SymbolFact(
            document_id="doc_1",
            symbol=handler,
            construct_kind=ConstructKind.METHOD,
            enclosing=owner,
            # A void return, spelled rather than omitted: a catalog with a
            # `reply` block reads the handler's own signature, and a method
            # fact carrying none is a shape the extractor never emits.
            signature=Signature(parameters=[], returns=TypeRef(symbol="void#", wire_type="")),
        ),
    ]
    facts += [
        AnnotationFact(
            document_id="doc_1",
            target=owner,
            retention="runtime",
            use=AnnotationUse(annotation=fqn, args=args),
        )
        for fqn, args in type_annotations.items()
    ]
    facts.append(
        AnnotationFact(
            document_id="doc_1",
            target=handler,
            retention="runtime",
            use=AnnotationUse(annotation=method_annotation, args=method_args),
        )
    )
    write_fact_file(root / "Subject.jsonl", document, facts)


def _gate_rows(tmp_path: Path, catalog_id: str, **facts) -> list[tuple]:
    _gate_facts(tmp_path / "facts", **facts)
    catalog = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == catalog_id)
    # A catalog carrying `detect.required` needs the module fact its gate reads
    # (F2 §3.6). These tests are about a catalog's own MATCHING rules, so the
    # coordinate is written from the catalog's own declaration rather than
    # hard-coded — a test asserting what `spring-stomp` matches should not also
    # be asserting which coordinate gates it, and the test that IS about the gate
    # varies it explicitly.
    if catalog.detect_required:
        write_fixture_module_fact_with(tmp_path / "facts", catalog.detect_coordinates[:1])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    derive_endpoints(
        workspace,
        [catalog],
        capabilities={"annotation_args", "typed_signatures", "type_annotations"},
    )
    rows = [
        (r["protocol"], r["direction"], r["method"], r["path"])
        for r in workspace.query("endpoints")
    ]
    workspace.close()
    return rows


_ON_MESSAGE = "jakarta/websocket/OnMessage#"
_SERVER_ENDPOINT = "jakarta/websocket/server/ServerEndpoint#"
_CLIENT_ENDPOINT = "jakarta/websocket/ClientEndpoint#"
_MESSAGE_MAPPING = "org/springframework/messaging/handler/annotation/MessageMapping#"
_CONTROLLER = "org/springframework/stereotype/Controller#"
_GET_EXCHANGE = "org/springframework/web/service/annotation/GetExchange#"
_RETROFIT_GET = "retrofit2/http/GET#"


def test_a_websocket_client_endpoint_is_not_an_inbound_server_endpoint(tmp_path: Path):
    """`A-C1`, and the worst row in it: a `@ClientEndpoint` class — one that
    DIALS OUT — carrying the `@OnMessage` callback was published as an INBOUND
    WebSocket endpoint at the empty address. Direction inverted and address
    invented in one row.

    `@OnMessage` cannot mint anything on its own: it is `@Target(METHOD)`, it
    carries no address, and it ships in the CLIENT api jar, so it is the
    message callback for both kinds of endpoint (CP-11 Q3). `@ServerEndpoint`
    is what makes a class served."""
    assert (
        _gate_rows(
            tmp_path,
            "jakarta-websocket",
            owner_kind=ConstructKind.CLASS,
            type_annotations={_CLIENT_ENDPOINT: {"value": "ws://billing/live"}},
            method_annotation=_ON_MESSAGE,
            method_args={},
        )
        == []
    )


def test_a_websocket_server_endpoint_still_derives_its_destination(tmp_path: Path):
    """The paired positive. One annotation different from the near-miss above,
    and the row the container really does serve comes back — which is what
    stops the gate from being a rule that declines everything."""
    assert _gate_rows(
        tmp_path,
        "jakarta-websocket",
        owner_kind=ConstructKind.CLASS,
        type_annotations={_SERVER_ENDPOINT: {"value": "/live"}},
        method_annotation=_ON_MESSAGE,
        method_args={},
    ) == [("websocket", "inbound", None, "/live")]


def test_a_stomp_mapping_on_a_class_that_is_not_a_controller_derives_nothing(tmp_path: Path):
    """`A-C1`. With no type gate, a lone `@MessageMapping` minted a declaration
    — and with no class-level annotation to prefix it, at the empty
    destination. Spring dispatches to `@Controller` beans and nothing else
    (CP-11 Q5, the same predicate MVC runs)."""
    assert (
        _gate_rows(
            tmp_path,
            "spring-stomp",
            owner_kind=ConstructKind.CLASS,
            type_annotations={},
            method_annotation=_MESSAGE_MAPPING,
            method_args={"value": ["/place"]},
        )
        == []
    )


def test_a_stomp_mapping_on_a_controller_still_derives_its_destination(tmp_path: Path):
    """The paired positive: the same handler on a `@Controller`."""
    assert _gate_rows(
        tmp_path,
        "spring-stomp",
        owner_kind=ConstructKind.CLASS,
        type_annotations={_CONTROLLER: {}},
        method_annotation=_MESSAGE_MAPPING,
        method_args={"value": ["/place"]},
    ) == [("websocket", "inbound", None, "/place")]


def test_an_http_exchange_annotation_on_a_class_derives_no_outbound_call(tmp_path: Path):
    """`A-C1`. `HttpServiceProxyFactory` proxies through Spring AOP's
    `ProxyFactory`, which refuses a non-interface (CP-11 Q6), so an exchange
    annotation on a concrete class is not a client at all and the outbound row
    published for one was a dependency the module does not have."""
    assert (
        _gate_rows(
            tmp_path,
            "spring-http-interface",
            owner_kind=ConstructKind.CLASS,
            type_annotations={},
            method_annotation=_GET_EXCHANGE,
            method_args={"value": ["/orders"]},
        )
        == []
    )


def test_an_http_exchange_annotation_on_an_interface_still_derives(tmp_path: Path):
    """The paired positive: one construct kind different."""
    assert _gate_rows(
        tmp_path,
        "spring-http-interface",
        owner_kind=ConstructKind.INTERFACE,
        type_annotations={},
        method_annotation=_GET_EXCHANGE,
        method_args={"value": ["/orders"]},
    ) == [("http", "outbound", "GET", "/orders")]


def test_a_retrofit_annotation_on_a_concrete_class_derives_nothing(tmp_path: Path):
    """`A-C6`. `Retrofit.create` throws `IllegalArgumentException("API
    declarations must be interfaces.")` on anything else (CP-11 Q4), so a
    `@GET`-annotated method on a concrete class is a hand-written class in a
    codebase that also uses Retrofit, or a test double — never a call site.
    The row published for one was a plausible-looking outbound dependency that
    does not exist, which is the worst kind: nothing downstream can tell a
    plausible fabricated address from an observed one."""
    assert (
        _gate_rows(
            tmp_path,
            "retrofit",
            owner_kind=ConstructKind.CLASS,
            type_annotations={},
            method_annotation=_RETROFIT_GET,
            method_args={"value": ["/orders"]},
        )
        == []
    )


def test_a_retrofit_annotation_on_an_interface_still_derives(tmp_path: Path):
    """The paired positive: one construct kind different, and the real
    Retrofit shape comes back."""
    assert _gate_rows(
        tmp_path,
        "retrofit",
        owner_kind=ConstructKind.INTERFACE,
        type_annotations={},
        method_annotation=_RETROFIT_GET,
        method_args={"value": ["/orders"]},
    ) == [("http", "outbound", "GET", "/orders")]


# --- `A-M5` / `A-M8`: the annotation sets that were shorter than the framework's


_RETROFIT_OPTIONS = "retrofit2/http/OPTIONS#"
_RETROFIT_HTTP = "retrofit2/http/HTTP#"
_SQS_LISTENER = "io/awspring/cloud/sqs/annotation/SqsListener#"


@pytest.mark.declines("retrofit")
@pytest.mark.pins("retrofit.declared-request-methods")
def test_retrofits_generic_http_annotation_derives_nothing_and_that_is_stated(tmp_path: Path):
    """`A-M5`'s stated boundary, pinned so it cannot be half-implemented.

    `@HTTP(method = "REPORT", path = "/x")` is a real Retrofit request method
    (CP-12 Q5) and this catalog does not declare it, for a reason the engine
    makes unavoidable: `$method_from`'s read in `derive_endpoints.sql` runs
    `regexp_extract(v, '#([A-Za-z0-9_]+)\\.$')` over the attribute's value,
    because every other framework in scope holds its verb in an ENUM constant
    whose symbol ends that way. `@HTTP.method` is a plain `String`, so the
    extract returns the empty string and the row would ship with `method: ''` —
    a verb no evidence supports, which is the fabrication this whole sweep is
    about. Its path is in `path` rather than `value` as well, and `path_from`
    is one list for the whole catalog.

    So the honest answer is to derive nothing and say so in COVERAGE §5.2
    rather than derive half of it. This test is what stops the entry being
    added without the engine change: it goes red the moment `@HTTP` starts
    matching, which is the point at which somebody has to look at the verb.

    It stops being right when `method_from` can name a plain-string attribute
    and `path_from` can be declared per annotation."""
    assert (
        _gate_rows(
            tmp_path,
            "retrofit",
            owner_kind=ConstructKind.INTERFACE,
            type_annotations={},
            method_annotation=_RETROFIT_HTTP,
            method_args={"method": "REPORT", "path": "/orders"},
        )
        == []
    )


def test_retrofits_options_annotation_derives_the_call_it_names(tmp_path: Path):
    """`A-M5`, the positive half, and the paired control for the near-miss
    above: the SAME interface, the same shape of attribute, one annotation
    different. `retrofit2.http.OPTIONS` is one of Retrofit's eight
    request-method annotations, declares a scalar `String value()` exactly as
    `@GET` does (CP-12 Q5), and derived nothing — silently, with no COVERAGE
    row."""
    assert _gate_rows(
        tmp_path,
        "retrofit",
        owner_kind=ConstructKind.INTERFACE,
        type_annotations={},
        method_annotation=_RETROFIT_OPTIONS,
        method_args={"value": ["/orders"]},
    ) == [("http", "outbound", "OPTIONS", "/orders")]


def test_an_sqs_listener_naming_its_queue_the_way_aws_documents_it_derives(tmp_path: Path):
    """`A-M8`, the positive half. `@SqsListener` declares `value()` and
    `queueNames()`, and `queueNames` carries
    `@AliasFor(value = "value")` — Spring's own statement that they are ONE
    attribute under two spellings (CP-12 Q10, spring-cloud-aws-sqs 3.1.1). The
    catalog read `value` alone, so `queueNames` — the spelling AWS's own
    documentation uses — read as absent, the composed destination was empty,
    and the addresses-nothing gate withheld the row entirely.

    That is a silent under-report and not the fabrication `docs/COVERAGE.md`
    used to describe: the listener was ABSENT from the export, not present with
    a blank address, which is the harder of the two for a reader to notice
    (sweep §7.7)."""
    assert _gate_rows(
        tmp_path,
        "spring-sqs",
        owner_kind=ConstructKind.CLASS,
        type_annotations={},
        method_annotation=_SQS_LISTENER,
        method_args={"queueNames": ["orders"]},
    ) == [("sqs", "inbound", None, "orders")]


@pytest.mark.declines("spring-sqs")
@pytest.mark.pins("spring-sqs.path-from-is-the-destination-aliases")
def test_an_sqs_listener_naming_no_destination_at_all_still_derives_nothing(tmp_path: Path):
    """`A-M8`'s near-miss, and it is what keeps the alias pair from becoming
    "read any attribute". `maxConcurrentMessages` is a real `@SqsListener`
    attribute (CP-12 Q10) and it is not the destination under any spelling, so
    a listener declaring only that names no queue and must derive nothing.

    It discriminates: adding `maxConcurrentMessages` to `path_from` makes this
    fail with a row whose `path` is a thread count."""
    assert (
        _gate_rows(
            tmp_path,
            "spring-sqs",
            owner_kind=ConstructKind.CLASS,
            type_annotations={},
            method_annotation=_SQS_LISTENER,
            method_args={"maxConcurrentMessages": "10"},
        )
        == []
    )


# --- 2O Task 10: the `@HttpExchange` direction flip -------------------------
#
# `@HttpExchange` is the one annotation family in the estate whose DIRECTION is
# not a property of the annotation. The same interface is an outbound client
# when a proxy is built from it and an inbound API when a controller implements
# it — measured, CP-7: `RequestMappingHandlerMapping` builds a mapping from
# `@HttpExchange` through a `SearchStrategy.TYPE_HIERARCHY` search, so an
# implementing class inherits the interface's exchange annotations without
# repeating them.
#
# The condition is the CONTROLLER check, not "the module implements it". Spring
# serves a bean, and `isHandler` is one
# `AnnotatedElementUtils.hasAnnotation(beanType, Controller.class)` call with no
# `@RequestMapping` disjunct on any minor in scope (CP-7 Q1), so a `@Service`
# implementation is served by nothing and an inbound row for one would invent an
# endpoint (§8.1 rule 4).
#
# Proved against the REAL shipped catalogs, the Task 7 precedent: the flip's
# condition names Spring's own stereotype annotations, which are catalog data on
# `spring-mvc.yml` and `spring-web.yml`, and a test spelled with an invented
# framework could not show that the two files agree.


# MODULE-PREFIXED throughout, unlike most fixtures in this file, and the flip is
# the mechanism that makes it matter: it joins a declaring method to the method
# implementing it ACROSS a coordinate boundary — an interface scanned out of an
# opted-in dependency jar carries that jar's coordinates while the class
# implementing it carries the module's — so every comparison it makes is on the
# BARE descriptor and the published symbol is the prefixed one. A fixture
# spelled bare could not tell a correct join from one comparing two prefixed
# strings that happen to match, and the first version of this code got that
# exactly wrong (`handlers` keyed on the prefixed symbol, joined against a bare
# one: the handler silently fell back to the interface's own method on every
# real module and on no test here).
_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "
_EXCHANGE_INTERFACE = _MODULE + "com/acme/api/OrderApi#"
_EXCHANGE_METHOD = _MODULE + "com/acme/api/OrderApi#list(sig_0a1)."
_IMPLEMENTER = _MODULE + "com/acme/api/OrderController#"
_IMPLEMENTER_METHOD = _MODULE + "com/acme/api/OrderController#list(sig_0a1)."
_LOCAL_STEREOTYPE = _MODULE + "com/acme/api/ApiController#"
# The same type as a USE site names it. An annotation fact records its
# annotation as a bare fqn descriptor and its target as a module-prefixed
# symbol (D00 §5a), so a module-local stereotype appears in the facts under
# both spellings at once — which is the shape the composition pre-pass
# resolves and a bare-everywhere fixture cannot show.
_LOCAL_STEREOTYPE_FQN = "com/acme/api/ApiController#"
_HTTP_EXCHANGE = "org/springframework/web/service/annotation/HttpExchange#"
_REST_CONTROLLER = "org/springframework/web/bind/annotation/RestController#"
_GET_MAPPING = "org/springframework/web/bind/annotation/GetMapping#"
_SERVICE = "org/springframework/stereotype/Service#"


def _flip_facts(
    root: Path,
    *,
    implementer_annotations: dict[str, dict] | None,
    overrides: bool = True,
    implementer_method_annotations: dict[str, dict] | None = None,
    stereotype_meta: str | None = None,
) -> None:
    """One `@HttpExchange` interface declaring one exchange operation, and
    optionally a local class implementing it.

    Every knob is one conjunct of the flip's own rule, so a near-miss differs
    from its positive in exactly one of them: WHETHER a local class implements
    the interface (`implementer_annotations=None`), WHAT that class is annotated
    with, whether it OVERRIDES the operation or inherits a `default`, and
    whether its stereotype is a module-local annotation composed from a
    framework one.
    """
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/api/OrderApi.java",
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
    void = Signature(parameters=[], returns=TypeRef(symbol="void#", wire_type=""))
    facts: list = [
        SymbolFact(
            document_id="doc_1", symbol=_EXCHANGE_INTERFACE, construct_kind=ConstructKind.INTERFACE
        ),
        SymbolFact(
            document_id="doc_1",
            symbol=_EXCHANGE_METHOD,
            construct_kind=ConstructKind.METHOD,
            enclosing=_EXCHANGE_INTERFACE,
            signature=void,
        ),
        AnnotationFact(
            document_id="doc_1",
            target=_EXCHANGE_INTERFACE,
            retention="runtime",
            use=AnnotationUse(annotation=_HTTP_EXCHANGE, args={"value": "/orders"}),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=_EXCHANGE_METHOD,
            retention="runtime",
            use=AnnotationUse(annotation=_GET_EXCHANGE, args={"value": "/list"}),
        ),
    ]
    if stereotype_meta is not None:
        # An annotation type is an interface in bytecode, which is what puts it
        # in `interface_symbols` and makes the composition pre-pass follow it.
        facts += [
            SymbolFact(
                document_id="doc_1",
                symbol=_LOCAL_STEREOTYPE,
                construct_kind=ConstructKind.INTERFACE,
            ),
            AnnotationFact(
                document_id="doc_1",
                target=_LOCAL_STEREOTYPE,
                retention="runtime",
                use=AnnotationUse(annotation=stereotype_meta, args={}),
            ),
        ]
    if implementer_annotations is not None:
        facts.append(
            SymbolFact(
                document_id="doc_1",
                symbol=_IMPLEMENTER,
                construct_kind=ConstructKind.CLASS,
                interfaces=[_EXCHANGE_INTERFACE],
            )
        )
        facts += [
            AnnotationFact(
                document_id="doc_1",
                target=_IMPLEMENTER,
                retention="runtime",
                use=AnnotationUse(annotation=fqn, args=args),
            )
            for fqn, args in implementer_annotations.items()
        ]
        if overrides:
            facts.append(
                SymbolFact(
                    document_id="doc_1",
                    symbol=_IMPLEMENTER_METHOD,
                    construct_kind=ConstructKind.METHOD,
                    enclosing=_IMPLEMENTER,
                    signature=void,
                )
            )
            facts += [
                AnnotationFact(
                    document_id="doc_1",
                    target=_IMPLEMENTER_METHOD,
                    retention="runtime",
                    use=AnnotationUse(annotation=fqn, args=args),
                )
                for fqn, args in (implementer_method_annotations or {}).items()
            ]
    write_fact_file(root / "OrderApi.jsonl", document, facts)


def _flip_rows(tmp_path: Path, catalogs: list[Catalog], **facts: object) -> list[tuple]:
    _flip_facts(tmp_path / "facts", **facts)  # type: ignore[arg-type]
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    assert derive_endpoints(workspace, catalogs, capabilities=set(_TASK_7_CAPABILITIES)) == []
    rows = sorted(
        (
            str(row["direction"]),
            row["method"] and str(row["method"]),
            str(row["path"]),
            row["handler"] and str(row["handler"]),
            row["caller"] and str(row["caller"]),
        )
        for row in workspace.query("endpoints")
    )
    workspace.close()
    return rows


def test_an_http_exchange_interface_a_controller_implements_is_served_inbound(tmp_path: Path):
    """The defect this closes, in one row. A locally-implemented
    `@HttpExchange` interface published an OUTBOUND call — the module reported
    calling a service it actually serves — and its inbound routes were missed
    entirely; the SEI fence later turned the fabrication into silence, which is
    honest and still an under-report of a whole HTTP surface.

    Spring serves it (CP-7 Q2: the mapping builder accepts `@HttpExchange`
    through a type-hierarchy search), so the row is inbound, at the composed
    address, with the IMPLEMENTING class's method as handler and no caller."""
    assert _flip_rows(
        tmp_path,
        [_shipped("spring-http-interface")],
        implementer_annotations={_REST_CONTROLLER: {}},
    ) == [("inbound", "GET", "/orders/list", _IMPLEMENTER_METHOD, None)]


@pytest.mark.declines("spring-http-interface")
@pytest.mark.pins("annotation_driven.flip-implementer-is-a-controller")
def test_an_http_exchange_interface_a_plain_bean_implements_derives_nothing(tmp_path: Path):
    """The near-miss for the flip's SECOND conjunct, and the reason spec §6's
    `owner_implemented_in_module: true` could not ship: one annotation
    different from the positive above, and Spring serves nothing at all.

    `isHandler` is `AnnotatedElementUtils.hasAnnotation(beanType,
    Controller.class)` and carries no `@RequestMapping` disjunct on any minor
    CP-7 measured, so a `@Service` implementing an `@HttpExchange` interface is
    dispatched to by nothing. An inbound row here would invent an endpoint
    (§8.1 rule 4); the outbound row the SEI fence already subtracts stays
    subtracted, because the module does not call what it implements."""
    assert (
        _flip_rows(
            tmp_path,
            [_shipped("spring-http-interface")],
            implementer_annotations={_SERVICE: {}},
        )
        == []
    )


@pytest.mark.pins("derive_endpoints.direction-flip-is-owner-scoped")
def test_an_unimplemented_http_exchange_interface_still_derives_outbound(tmp_path: Path):
    """The near-miss for the flip's FIRST conjunct: the same interface with no
    local implementation at all is an ordinary HTTP-interface client, and must
    keep deriving exactly the outbound row it always did — caller intact,
    handler absent.

    A flip keyed on the catalog's rule rather than on the OWNER would rewrite
    every `@HttpExchange` client in the estate into an inbound endpoint, which
    is the largest fabrication available in this file."""
    assert _flip_rows(
        tmp_path,
        [_shipped("spring-http-interface")],
        implementer_annotations=None,
    ) == [("outbound", "GET", "/orders/list", None, _EXCHANGE_METHOD)]


def test_a_default_method_the_controller_never_overrides_is_still_served(tmp_path: Path):
    """CP-7 Q3, and the reason the flip is keyed on the OWNER rather than on
    the method join. `MethodIntrospector.selectMethods` walks the target type's
    own interfaces as well as the type itself, so a `default` method the
    controller never overrides IS mapped and served — by the interface's own
    method, which is the only method symbol there is.

    A flip that required a matching method on the implementing class would have
    dropped exactly those routes, silently."""
    assert _flip_rows(
        tmp_path,
        [_shipped("spring-http-interface")],
        implementer_annotations={_REST_CONTROLLER: {}},
        overrides=False,
    ) == [("inbound", "GET", "/orders/list", _EXCHANGE_METHOD, None)]


def test_a_module_local_stereotype_composed_from_a_controller_flips_the_interface(tmp_path: Path):
    """`A-C7`'s rule, applied to the flip's own condition. Spring's handler
    test is a PREDICATE over the composition, so a controller wearing a
    module-local `@ApiController` meta-annotated `@Controller` is a handler —
    and a flip encoded as string equality against two framework FQNs would
    leave that module's whole implemented API published as an outbound
    dependency it does not have."""
    assert _flip_rows(
        tmp_path,
        [_shipped("spring-http-interface")],
        implementer_annotations={_LOCAL_STEREOTYPE_FQN: {}},
        stereotype_meta=_CONTROLLER,
    ) == [("inbound", "GET", "/orders/list", _IMPLEMENTER_METHOD, None)]


@pytest.mark.parametrize("declared_first", ["spring-web", "spring-http-interface"])
def test_a_doubly_declared_route_merges_into_one_row_handled_by_the_class(
    tmp_path: Path, declared_first: str
):
    """Ruling R12's merge precedence, and it needs no collision detector —
    there is none in `src/`, and none is added here.

    A controller that implements an `@HttpExchange` interface AND writes its
    own `@GetMapping` for the same route derives that route twice: once from
    `spring-web`, once from the flipped `spring-http-interface` row. The two
    share `(protocol, direction, method, path)`, so the existing dedup folds
    them into ONE — and the survivor is handled by the implementing class's
    method, not the interface's.

    **What this test can and cannot show.** The catalogs' run order is not the
    caller's to choose: `resolve/endpoints.py` sorts them, and an
    inbound-DECLARED catalog runs before an outbound-declared one whatever
    order the list arrives in — which is why both parameters here produce the
    same answer, and why it is worth pinning that they do. So the surviving row
    is `spring-web`'s in both, and this test proves the merge and the
    ORDER-INDEPENDENCE rather than the flip's own handler rebind. That rebind
    is proved where it is the only source of a row at all —
    `test_an_http_exchange_interface_a_controller_implements_is_served_inbound`
    above, where the controller writes no mapping of its own and the handler on
    the one surviving row can only have come from the flip.

    The address is the thing that has to agree for any of this to happen, and
    it only does because a flipped row is canonicalized as the server-side row
    it became: composed one way it is `/orders/list`, composed the other it is
    the same string, and two spellings of one URL would have shipped as two
    endpoints."""
    order = ["spring-web", "spring-http-interface"]
    catalogs = [_shipped(c) for c in (order if declared_first == "spring-web" else order[::-1])]
    assert _flip_rows(
        tmp_path,
        catalogs,
        implementer_annotations={_REST_CONTROLLER: {}},
        implementer_method_annotations={_GET_MAPPING: {"value": ["/orders/list"]}},
    ) == [("inbound", "GET", "/orders/list", _IMPLEMENTER_METHOD, None)]


def _flip_catalog(**resolves: object) -> Catalog:
    """An invented outbound catalog carrying a `resolves` block — the engine
    vocabulary on its own, deliberately not Spring, for the reason every other
    invented catalog in this file is not: a refusal test spelled with
    `@HttpExchange` in it would pin a framework rather than the check."""
    return Catalog(
        id="invented-two-faced",
        style="annotation_driven",
        protocol="http",
        direction="outbound",
        requires=("annotation_args",),
        source=Path("tests/invented-two-faced.yml"),
        matches={
            "declared_on": "interface",
            "mapping": {
                "path_from": ["value"],
                "prefix_from": ["value"],
                "method_from": "method",
                "all_methods": ["GET"],
                "prefix_annotation": None,
                "annotations": [{"fqn": "com.acme.rpc.Call", "method": ["GET"]}],
            },
        },
        resolves=dict(resolves),
    )


def _flip_refusal(tmp_path: Path, catalog: Catalog) -> str:
    _flip_facts(tmp_path / "facts", implementer_annotations=None)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    with pytest.raises(CatalogError) as raised:
        derive_endpoints(workspace, [catalog], capabilities={"annotation_args"})
    workspace.close()
    return str(raised.value)


def test_a_resolves_block_naming_a_key_that_did_not_ship_is_refused(tmp_path: Path):
    """D02 §2c names `format` beside `direction` and says in the same section
    that the format half did NOT ship — it is answered by a late pass over the
    finished table instead. A catalog writing one here would be declaring a
    rule nothing runs, and silence about it is how a document becomes evidence
    for a mechanism that does not exist (§5.3)."""
    refusal = _flip_refusal(
        tmp_path, _flip_catalog(format=[{"when": {"whatever": True}, "then": "protobuf"}])
    )
    assert "format" in refusal and "invented-two-faced.yml" in refusal


def test_a_second_direction_rule_is_refused_rather_than_silently_dropped(tmp_path: Path):
    """D02 §2c's first-match-wins over several conditions is the section's
    stated semantics and is unimplemented. An engine honouring one rule while
    accepting a list of them would drop every rule after the first — a catalog
    author's second condition evaluating to nothing, with nothing saying so."""
    rule = {"when": {"owner_implemented_by_type_annotated": ["a.B"]}, "then": "inbound"}
    refusal = _flip_refusal(tmp_path, _flip_catalog(direction=[rule, rule]))
    assert "exactly one" in refusal and "invented-two-faced.yml" in refusal


def test_a_condition_the_engine_cannot_honour_is_refused(tmp_path: Path):
    """The closed vocabulary (NFR-5). Spec §6's own
    `owner_implemented_in_module: true` is the value this refuses by name, and
    the reason it must be refused rather than ignored: a condition read as "no
    rule" leaves a served API published as an outbound dependency, which is the
    exact defect the flip exists to close."""
    refusal = _flip_refusal(
        tmp_path,
        _flip_catalog(
            direction=[{"when": {"owner_implemented_in_module": True}, "then": "inbound"}]
        ),
    )
    assert "owner_implemented_by_type_annotated" in refusal


def test_a_resolved_direction_outside_the_closed_set_is_refused(tmp_path: Path):
    """D00's closed sets are closed, and this value reaches `endpoints.direction`
    on every flipped row — a typo there is published as a wire fact."""
    refusal = _flip_refusal(
        tmp_path,
        _flip_catalog(
            direction=[{"when": {"owner_implemented_by_type_annotated": ["a.B"]}, "then": "inound"}]
        ),
    )
    assert "inound" in refusal


def test_a_rule_resolving_to_the_catalogs_own_direction_is_refused(tmp_path: Path):
    """A rule that resolves nothing is a file claiming a flip it does not
    perform. Accepted as a no-op it would read, to anyone auditing the catalog,
    as the two-faced case being handled."""
    refusal = _flip_refusal(
        tmp_path,
        _flip_catalog(
            direction=[
                {"when": {"owner_implemented_by_type_annotated": ["a.B"]}, "then": "outbound"}
            ]
        ),
    )
    assert "resolves nothing" in refusal


def test_a_condition_naming_no_annotations_at_all_is_refused(tmp_path: Path):
    """An empty list is a condition that never holds — the catalog would
    declare a flip and never perform one, which reads exactly like a rule that
    works on a module where nothing happens to match."""
    refusal = _flip_refusal(
        tmp_path,
        _flip_catalog(
            direction=[{"when": {"owner_implemented_by_type_annotated": []}, "then": "inbound"}]
        ),
    )
    assert "non-empty list" in refusal


# --- W9/W10 review, M2/M3: `catalog_symbols` is the one function §3.1 added and
# nothing tested it directly. Its callers were tested through the shipped
# catalogs, which all happen to be well-formed, so every refusal branch in it was
# unreached.


def test_catalog_symbols_accepts_one_name_and_a_list_of_them():
    """A scalar stays valid — this is a widening, not a migration, and 42 shipped
    catalogs write scalars — and a list means ONE library under several names."""
    from sextant.application.resolve.shapes.rooting import catalog_symbols

    assert catalog_symbols("org.springframework.jms.core.JmsTemplate") == (
        "org/springframework/jms/core/JmsTemplate#",
    )
    assert catalog_symbols(
        ["org.springframework.jms.core.JmsTemplate", "org.springframework.jms.core.JmsOperations"]
    ) == (
        "org/springframework/jms/core/JmsTemplate#",
        "org/springframework/jms/core/JmsOperations#",
    )


@pytest.mark.parametrize(
    "declared",
    [
        pytest.param(None, id="null"),
        pytest.param(7, id="a number"),
        pytest.param({"owner": "a.B"}, id="a mapping"),
        pytest.param([], id="an empty list"),
    ],
)
def test_catalog_symbols_refuses_a_shape_that_is_not_a_name(declared):
    """Every one of these is a well-formed YAML value, so the loader admits it.
    The refusal has to name the FILE and the KEY: a reader holding 42 catalogs
    cannot act on "a catalog site must name a type"."""
    from sextant.application.ports.catalogs import CatalogError
    from sextant.application.resolve.shapes.rooting import catalog_symbols

    with pytest.raises(CatalogError) as refusal:
        catalog_symbols(declared, "spring-jms-template.yml: matches.owner")
    assert "spring-jms-template.yml: matches.owner" in str(refusal.value)


def test_every_shipped_alternate_owner_is_a_distinct_resolvable_symbol():
    """The list form across every shipped catalog, checked as a set rather than
    one catalog at a time: a repeated entry is a name that can never match twice
    and a typo is a name that can never match at all, and both are silent —
    `_matching_method` simply finds no call site with that owner.

    The measurement that these names EXIST in the libraries is CP-10's; this asks
    only that the catalog spells each one once and that it converts."""
    from sextant.application.resolve.shapes.rooting import catalog_symbols

    listed = 0
    for catalog in YamlCatalogSource(CATALOGS).load():
        declared = catalog.matches.get("owner") if isinstance(catalog.matches, dict) else None
        if not isinstance(declared, list):
            continue
        listed += 1
        symbols = catalog_symbols(declared, f"{catalog.source}: matches.owner")
        assert len(set(symbols)) == len(symbols), f"{catalog.source} repeats an owner: {symbols}"
        assert all(symbol.endswith("#") for symbol in symbols), symbols
    # §3.1 was applied to eight catalogs — seven, plus W43's `spring-stomp-template`,
    # whose `SimpMessagingTemplate`/`SimpMessageSendingOperations` pair is the same
    # class-and-interface shape the rule exists for. A test that silently found none would
    # pass forever once the key was renamed.
    assert listed == 8, f"expected eight catalogs with an owner list, found {listed}"


def test_a_malformed_owner_is_refused_before_the_endpoints_table_is_emptied(tmp_path):
    """W9/W10 review M1. The conversion lives in the call-site engine, which runs
    AFTER `endpoints_reset`, so a malformed `owner` raised with the previous run's
    rows already gone and none written — a broken file half-emptying the table,
    the exact outcome `derive_endpoints` resolves every style up front to
    prevent. The pre-flight refusal is what puts it back in front of the reset."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        workspace.derive("endpoints_reset")
        workspace._connection.execute(
            "INSERT INTO endpoints (protocol, direction, path) VALUES ('jms', 'outbound', '/prior')"
        )
        broken = next(
            catalog
            for catalog in YamlCatalogSource(CATALOGS).load()
            if catalog.style == "single_call"
        )
        object.__setattr__(broken, "matches", {**broken.matches, "owner": 7})

        with pytest.raises(CatalogError) as refusal:
            derive_endpoints(workspace, [broken], set())

        assert "matches.owner" in str(refusal.value)
        # The row the previous run wrote is still there: nothing was emptied.
        assert [row["path"] for row in workspace.query("endpoints")] == ["/prior"]
    finally:
        workspace.close()


def test_a_type_annotation_written_as_a_list_gates_on_every_spelling(tmp_path: Path):
    """§3.1 at the one widened key that reaches SQL rather than Python.

    `$type_annotation` was compared with `=` inside `derive_endpoints.sql`, so
    widening it meant changing the SQL too (`list_contains`), which no Python-level
    test would have exercised. The real annotation is put SECOND in the list on
    purpose: a comparison that still read the parameter as one string would match
    nothing, and putting it first would let a first-element read pass by accident.

    The pair here is a realistic one — Spring gates on `@Controller` and
    `@RestController`, and a codebase writes either — but the assertion is the
    mechanism, not the pair.
    """
    _controller_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    spring = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-web")
    scalar = spring.matches["type_annotation"]
    listed = Catalog(
        **{
            **vars(spring),
            "matches": {
                **spring.matches,
                "type_annotation": ["org.springframework.stereotype.Controller", scalar],
            },
        }
    )

    derive_endpoints(workspace, [listed], capabilities={"annotation_args", "type_annotations"})
    rows = workspace.query("endpoints")
    workspace.close()

    assert {(r["method"], r["path"]) for r in rows} == {
        ("POST", "/v1/orders"),
        ("GET", "/v1/orders/{id}"),
        ("GET", "/v1/orders"),
    }


def test_catalog_symbols_returns_every_name_a_list_declares(tmp_path: Path):
    """`catalog_symbols` returns ALL of them, in order, and a one-element list is
    the same tuple as the bare scalar.

    This does NOT exercise any engine — it names no catalog and derives no row. It
    was called `..._a_field_annotation_written_as_a_list_matches_either_spelling`,
    which claimed coverage of `injected_client`'s key that it does not have; the
    end-to-end coverage each widened key does or does not have is OI-55.
    """
    from sextant.application.resolve.shapes.rooting import catalog_symbols

    both = catalog_symbols(["com.acme.First", "com.acme.Second"], "test: field_annotation")
    assert both == ("com/acme/First#", "com/acme/Second#")
    # A one-element list and the bare scalar are the same tuple: the widening adds
    # a spelling, never a second behaviour for the singular case.
    assert catalog_symbols(["com.acme.First"], "test") == catalog_symbols("com.acme.First", "test")


def test_a_prefix_annotation_written_as_a_list_gates_on_every_spelling(tmp_path: Path):
    """The second widened key that reaches SQL rather than Python.

    `$prefix_annotation` is compared with `list_contains` in
    `derive_endpoints.sql` exactly as `$type_annotation` is, and had no test:
    changing that one comparison back to `a.annotation = $prefix_annotation[1]`
    left 1,423 tests passing. The real annotation goes SECOND for the same reason
    as in the test above — a comparison reading the parameter as one string, or
    reading only its first element, matches nothing.

    The prefix is what makes these paths `/v1/orders` rather than `/orders`, so
    the assertion is on the composed path and not merely on the row's existence.
    """
    _controller_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    spring = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-web")
    scalar = spring.matches["mapping"]["prefix_annotation"]
    listed = Catalog(
        **{
            **vars(spring),
            "matches": {
                **spring.matches,
                "mapping": {
                    **spring.matches["mapping"],
                    "prefix_annotation": ["com.acme.rest.NoSuchMapping", scalar],
                },
            },
        }
    )

    derive_endpoints(workspace, [listed], capabilities={"annotation_args", "type_annotations"})
    rows = workspace.query("endpoints")
    workspace.close()

    assert {(r["method"], r["path"]) for r in rows} == {
        ("POST", "/v1/orders"),
        ("GET", "/v1/orders/{id}"),
        ("GET", "/v1/orders"),
    }


def test_every_widened_key_a_shipped_catalog_declares_honours_a_second_spelling(
    tmp_path: Path, fixture_facts: Path
):
    """§3.1 across every key at once, on the real fixture and the real catalogs.

    Sixteen of the twenty widened keys had no test that would fail if the
    widening were reverted at the CONSUMER: mutating `catalog_symbols` to return
    only its first element failed four tests out of 2,407, and two of those four
    were unit tests of `catalog_symbols` itself. Writing sixteen near-identical
    end-to-end tests would test one mechanism sixteen times; this drives the
    mechanism once, over whatever the shipped catalogs actually declare.

    Every widened key in every shipped catalog is rewritten from `X` to
    `[<a name nothing declares>, X]` — the real name SECOND, so a consumer that
    reads one element, or reads the first, matches nothing — and the fixture is
    resolved twice. The endpoint rows must be identical.

    `_WIDENED_KEYS` is `endpoints.py`'s own list, the same one the pre-flight
    walks, so a key added there without a consumer that iterates lands here
    automatically rather than needing this test to be remembered.
    """
    from sextant.application.resolve.endpoints import _WIDENED_KEYS, _at

    # A DISTINCT absent name per occurrence. One shared name made two `fluent`
    # steps that previously had distinct owners collide, and `_validate_steps`
    # refused the catalog — its overlap rule working exactly as intended, and
    # not the question this test asks.
    minted = iter(f"com.acme.no.such.Type{n}" for n in range(10_000))

    def widened(value: object) -> object:
        """The real name in the MIDDLE, absent names either side.

        Prepending alone left the real name last, so a consumer reading only the
        LAST element still passed; appending alone has the mirror hole. Wrapping
        it catches both ends, which is what "reads every element" actually means.
        """
        return [next(minted), value, next(minted)]

    def rewrite(holder: object, path: tuple[str, ...]) -> None:
        """Rewrites in place, mirroring `_at`'s own walk so the two cannot drift."""
        if not path:
            return
        key, rest = path[0], path[1:]
        if key == "[]":
            if isinstance(holder, list):
                for element in holder:
                    rewrite(element, rest)
            return
        if not isinstance(holder, dict) or key not in holder:
            return
        if rest:
            rewrite(holder[key], rest)
        elif isinstance(holder[key], list):
            # WRAP, never skip. Seven shipped catalogs already write a list at
            # `matches.owner`, and `spring-ws-template.yml` writes one at the SOAP
            # identity key — skipping those left the very keys §3.1 was applied to
            # as the ones this test did not drive.
            holder[key] = [next(minted), *holder[key], next(minted)]
        elif holder[key] is not None:
            holder[key] = widened(holder[key])

    shipped = YamlCatalogSource(CATALOGS).load()
    listed = []
    touched = 0
    for original in shipped:
        matches = copy.deepcopy(original.matches)
        for path in _WIDENED_KEYS:
            before = len(_at(matches, path))
            rewrite(matches, path)
            touched += before
        listed.append(Catalog(**{**vars(original), "matches": matches}))

    # The test is worthless if it rewrote nothing — which is what a renamed key
    # would silently produce.
    # 19 of the 20 keys in `_WIDENED_KEYS`, measured: `media_values.owner` is
    # declared by NO shipped catalog and so cannot be reached from here — the one
    # key whose consumer this test does not drive (OI-55). The floor is on
    # occurrences, not keys, and is deliberately well under the ~55 the shipped
    # catalogs currently hold: it fails a rename that silently rewrites nothing
    # without failing every time a catalog is added or removed.
    assert touched >= 40, f"only {touched} widened key occurrences found across the catalogs"

    def rows(catalogs: list[Catalog]) -> set:
        workspace = DuckDbWorkspace(tmp_path / f"ws{len(catalogs)}{id(catalogs)}.duckdb")
        workspace.load_facts(fixture_facts)
        derive_endpoints(workspace, catalogs, capabilities=FIXTURE_CAPABILITIES)
        found = {
            (r["catalog_id"], r["protocol"], r["direction"], r["method"], r["path"], r["peer"])
            for r in workspace.query("endpoints")
        }
        workspace.close()
        return found

    scalar_rows = rows(shipped)
    assert scalar_rows, "the fixture derived nothing; this test would pass on any change"
    assert rows(listed) == scalar_rows


# --- F2 §3.5's relationship conjunct (W14/W15) -----------------------------

_KAFKA_LISTENER = "org/springframework/kafka/annotation/KafkaListener#"
_KAFKA_HANDLER = "org/springframework/kafka/annotation/KafkaHandler#"


def _kafka_class_facts(root: Path, class_topic: str | None, members: tuple) -> None:
    """A class carrying an optional class-level `@KafkaListener`, plus one method
    per `(annotation, topic)`."""
    owner = "com/acme/orders/Orders#"
    facts: list = [
        SymbolFact(document_id="doc_k", symbol=owner, construct_kind=ConstructKind.CLASS)
    ]
    if class_topic is not None:
        facts.append(
            AnnotationFact(
                document_id="doc_k",
                target=owner,
                retention="runtime",
                use=AnnotationUse(annotation=_KAFKA_LISTENER, args={"topics": [class_topic]}),
            )
        )
    for index, (annotation, topic) in enumerate(members):
        method = f"{owner}onEvent{index}(sig_{index})."
        facts.append(
            SymbolFact(
                document_id="doc_k",
                symbol=method,
                construct_kind=ConstructKind.METHOD,
                enclosing=owner,
                signature=Signature(parameters=[], returns=TypeRef(symbol="V")),
            )
        )
        facts.append(
            AnnotationFact(
                document_id="doc_k",
                target=method,
                retention="runtime",
                use=AnnotationUse(
                    annotation=annotation, args={} if topic is None else {"topics": [topic]}
                ),
            )
        )
    write_fact_file(
        root / "Orders.jsonl",
        Document(
            document_id="doc_k",
            relative_path="com/acme/orders/Orders.java",
            module_id="com.acme:orders-service",
            language="java",
            sextant_version="0.1.0",
            fact_schema_version=2,
            scanner_id="asm",
            content_hash="sha256:a",
            origin_entry="target/classes",
            origin_tier=OriginTier.MODULE_OUTPUT,
            redaction_set_hash="sha256:b",
        ),
        facts,
    )


def _kafka_paths(tmp_path: Path, class_topic: str | None, members: tuple) -> set[str]:
    root = tmp_path / "facts"
    _kafka_class_facts(root, class_topic, members)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    kafka = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-kafka")
    derive_endpoints(
        workspace,
        [kafka],
        capabilities={"annotation_args", "typed_signatures", "nested_annotation_args"},
    )
    paths = {str(row["path"]) for row in workspace.query("endpoints")}
    workspace.close()
    return paths


def test_a_class_and_a_method_listener_are_two_registrations_not_a_composed_one(tmp_path: Path):
    """F2 §3.5, and the row it exists to change.

    A class-level `@KafkaListener(topics="orders")` and a method-level
    `@KafkaListener(topics="payments")` are TWO independent registrations —
    measured in `scripts/probes/w14_listener_registration.md`: the annotation is
    `@Target(TYPE, METHOD)`, declares `topics` at both levels, and Spring's
    registrar declares two paths (one taking a `Class`, one a `Method`) with
    neither excluding the other.

    Composed, they published **`orderspayments`** — a topic no broker carries —
    at `resolved`. Two readable destinations became one unreadable one.

    The THREE-member shape is the one asserted, not the two-member one: a class
    listener, a `@KafkaHandler` serving it, and a method listener of its own.
    That is what distinguishes "the class topic is no longer composed onto the
    method's" from "the class topic is gone" — the silent loss §3.5 rejects as
    firmly as it rejects the fabrication.
    """
    assert _kafka_paths(
        tmp_path, "orders", ((_KAFKA_HANDLER, None), (_KAFKA_LISTENER, "payments"))
    ) == {"orders", "payments"}


def test_a_kafka_handler_still_takes_the_class_level_topic(tmp_path: Path):
    """The paired positive, and the reason the conjunct is a rule rather than a
    special case: a `@KafkaHandler` declares exactly one attribute, `isDefault()`,
    and NO destination — so it names none of its own and takes the class's under
    either value of `class_level`. `sibling` distinguishes "this member names a
    destination" from "this member names none", which is the distinction the
    framework itself makes; it does not distinguish Kafka from HTTP."""
    assert _kafka_paths(tmp_path, "orders", ((_KAFKA_HANDLER, None),)) == {"orders"}


def test_an_http_class_level_mapping_still_composes(tmp_path: Path):
    """The other half: `prefix` is the default and HTTP still composes. A rule
    that silenced composition everywhere would pass both tests above."""
    _controller_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    spring = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-web")
    derive_endpoints(workspace, [spring], capabilities={"annotation_args", "type_annotations"})
    paths = {str(row["path"]) for row in workspace.query("endpoints")}
    workspace.close()

    # `/v1` on the class, `/orders` on the methods — composed, as they must be.
    assert paths == {"/v1/orders", "/v1/orders/{id}"}


def test_a_catalog_declaring_an_unknown_class_level_value_is_refused(tmp_path: Path):
    """The vocabulary is closed. A typo (`siblings`, `PREFIX`) would otherwise
    fall through to the default and compose silently — the failure the conjunct
    exists to stop, reintroduced by a spelling mistake.

    Refused in `derive_endpoints`'s PRE-FLIGHT, not inside the engine, and the
    capabilities passed here are what proves it: they are deliberately too few
    for `spring-kafka` to run at all. A check inside the engine would not fire
    for a skipped catalog, so a typo would sit unnoticed until the day the
    capability arrived — and would then raise after `endpoints_reset`, taking
    the previous run's rows with it."""
    kafka = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-kafka")
    broken = Catalog(
        **{
            **vars(kafka),
            "matches": {
                **kafka.matches,
                "mapping": {**kafka.matches["mapping"], "class_level": "siblings"},
            },
        }
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        workspace.derive("endpoints_reset")
        workspace._connection.execute(
            "INSERT INTO endpoints (protocol, direction, path) VALUES ('kafka','inbound','/prior')"
        )
        with pytest.raises(CatalogError) as refusal:
            derive_endpoints(workspace, [broken], capabilities=set())
        assert "class_level" in str(refusal.value)
        # Refused BEFORE the reset: the previous run's row is still there.
        assert [row["path"] for row in workspace.query("endpoints")] == ["/prior"]
    finally:
        workspace.close()


# --- F2 §3.6: RSocket versus STOMP, told apart by the build ------------------

_MESSAGE_MAPPING = "org/springframework/messaging/handler/annotation/MessageMapping#"
_SPRING_CONTROLLER = "org/springframework/stereotype/Controller#"


_CONNECT_MAPPING = "org/springframework/messaging/rsocket/annotation/ConnectMapping#"


def _messaging_controller_facts(root: Path, method_annotation: str = _MESSAGE_MAPPING) -> None:
    """A `@Controller` with one `@MessageMapping("/place")` method — the shape
    BOTH frameworks scan, with the same predicate, and which therefore says
    nothing about which of them serves it.

    `method_annotation` varies for the one case where the annotation DOES say
    which framework serves it: `@ConnectMapping` is RSocket's and STOMP ships no
    counterpart (F2 §3.6, `detect.satisfied_by`)."""
    owner = "com/acme/orders/LiveController#"
    method = f"{owner}place(sig_p)."
    document = Document(
        document_id="doc_ws",
        relative_path="com/acme/orders/LiveController.java",
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
    write_fact_file(
        root / "LiveController.jsonl",
        document,
        [
            SymbolFact(document_id="doc_ws", symbol=owner, construct_kind=ConstructKind.CLASS),
            SymbolFact(
                document_id="doc_ws",
                symbol=method,
                construct_kind=ConstructKind.METHOD,
                enclosing=owner,
                signature=Signature(parameters=[], returns=TypeRef(symbol="V")),
            ),
            AnnotationFact(
                document_id="doc_ws",
                target=owner,
                retention="runtime",
                use=AnnotationUse(annotation=_SPRING_CONTROLLER, args={}),
            ),
            AnnotationFact(
                document_id="doc_ws",
                target=method,
                retention="runtime",
                use=AnnotationUse(annotation=method_annotation, args={"value": ["/place"]}),
            ),
        ],
    )


def _messaging_rows(
    tmp_path: Path,
    coordinates: tuple[str, ...] | None,
    method_annotation: str = _MESSAGE_MAPPING,
) -> set:
    root = tmp_path / "facts"
    _messaging_controller_facts(root, method_annotation)
    if coordinates is not None:
        write_fixture_module_fact_with(root, coordinates)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    catalogs = [
        c for c in YamlCatalogSource(CATALOGS).load() if c.id in ("spring-stomp", "spring-rsocket")
    ]
    derive_endpoints(workspace, catalogs, capabilities={"annotation_args", "typed_signatures"})
    found = {(str(row["protocol"]), str(row["path"])) for row in workspace.query("endpoints")}
    workspace.close()
    return found


@pytest.mark.declines("spring-rsocket")
@pytest.mark.pins("dependencies.detect-required-is-a-conjunct")
def test_a_message_mapping_controller_in_a_websocket_module_is_not_an_rsocket_row(
    tmp_path: Path,
):
    """F2 §3.6's near-miss, and it is the discriminator itself.

    EVERY conjunct of `spring-rsocket.yml`'s rule holds — the class carries
    `@Controller`, the method carries `@MessageMapping`, and Spring's own RSocket
    handler would scan exactly this class, because its bean predicate is
    `hasAnnotation(beanType, Controller.class)`, byte for byte STOMP's
    (`scripts/probes/w16_rsocket_versus_stomp.md`, section 1).

    Only the BUILD differs. That is the whole finding: no fact about the class
    separates an RSocket controller from a STOMP one, so the rule cannot be a
    conjunct over evidence and has to be a conjunct over the module's
    dependencies.
    """
    assert _messaging_rows(tmp_path, ("org.springframework:spring-websocket",)) == {
        ("websocket", "/place")
    }


@pytest.mark.declines("spring-stomp")
@pytest.mark.pins("dependencies.detect-required-is-a-conjunct")
def test_the_same_controller_in_an_rsocket_module_is_not_a_websocket_row(tmp_path: Path):
    """The mirror, and the row this wave exists to stop. Before W16 this module
    derived `websocket` — a wrong-PROTOCOL fabrication, and `protocol` is identity,
    so DR-5 linked it in another consumer's graph to endpoints this module never
    speaks to."""
    assert _messaging_rows(tmp_path, ("io.rsocket:rsocket-core",)) == {("rsocket", "/place")}


def test_both_starters_present_derives_both_rows(tmp_path: Path):
    """§3.6: "Both present → two rows. Both handlers scan the same beans; the
    method really does serve both. This is a correct answer, not an ambiguity."

    Nothing implements it — the two catalogs are independently gated and neither
    suppresses the other — which is why it is asserted rather than assumed."""
    assert _messaging_rows(
        tmp_path,
        ("org.springframework:spring-websocket", "io.rsocket:rsocket-core"),
    ) == {("websocket", "/place"), ("rsocket", "/place")}


@pytest.mark.pins("dependencies.satisfied-by-answers-the-gate")
def test_a_connect_mapping_derives_rsocket_whatever_the_build_says(tmp_path: Path):
    """F2 §3.6: "`@ConnectMapping` anywhere is positive RSocket evidence
    regardless of the build."

    The build here says the OPPOSITE of the annotation — `spring-websocket`
    declared, no RSocket coordinate anywhere — and the annotation wins, because
    it names one framework and the build's silence names none. `@ConnectMapping`
    lives in `messaging/rsocket/annotation`, STOMP ships no counterpart, and
    `spring-stomp.yml` does not claim it
    (`scripts/probes/w16_rsocket_versus_stomp.md` section 2).

    Until `detect.satisfied_by` shipped this sentence was unreachable: the gate
    answers before any matching runs, so this exact module derived NOTHING and
    asked nothing — silent, in the one case the sentence was written for.
    """
    assert _messaging_rows(
        tmp_path, ("org.springframework:spring-websocket",), _CONNECT_MAPPING
    ) == {("rsocket", "/place")}


@pytest.mark.pins("dependencies.satisfied-by-answers-the-gate")
def test_a_connect_mapping_derives_rsocket_with_no_module_fact_at_all(tmp_path: Path):
    """ "Regardless of the build" includes a build that recorded nothing — the
    ordinary Maven case, where a starter's own transitives never reach the
    module fact. `spring-stomp` is still skipped here, because nothing answers
    ITS question; the point is that RSocket's is answered by evidence."""
    assert _messaging_rows(tmp_path, None, _CONNECT_MAPPING) == {("rsocket", "/place")}


def test_a_message_mapping_is_not_satisfied_by_an_annotation(tmp_path: Path):
    """The paired near-miss, and the reason `detect.satisfied_by` is a DECLARED
    list rather than "any annotation this catalog names". `@MessageMapping` is on
    `spring-rsocket.yml`'s `mapping.annotations` exactly as `@ConnectMapping` is,
    and it must not answer the gate: it is the annotation both frameworks share,
    which is the whole reason the gate exists."""
    assert _messaging_rows(tmp_path, ("org.springframework:spring-websocket",)) == {
        ("websocket", "/place")
    }


def test_a_build_that_records_nothing_earns_a_question_rather_than_a_guess(tmp_path: Path):
    """§3.6's last clause: "Neither resolvable (parent-POM inheritance, a stated
    refusal that survives F1) → open question, not a guess."

    A module whose build records NO coordinates cannot be asked whether it
    declares `spring-websocket` or `rsocket-core` — and F1 does not resolve
    transitives, so a starter would not settle it either. Both catalogs decline,
    so no row is derived on either protocol; without a question the module's
    messaging surface would vanish silently, which is the same absence a module
    with no handlers at all produces.

    The guess this refuses is the one that stood until W16: whichever catalog
    claimed `@MessageMapping` first published the class on ITS protocol, and
    `spring-stomp` claimed it, so every RSocket controller in the estate read as
    `websocket`.
    """
    root = tmp_path / "facts"
    _messaging_controller_facts(root)
    # No module fact at all — the case the gate calls unanswerable, as distinct
    # from a build that records coordinates and names neither library.
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    catalogs = [
        c for c in YamlCatalogSource(CATALOGS).load() if c.id in ("spring-stomp", "spring-rsocket")
    ]
    derive_endpoints(workspace, catalogs, capabilities={"annotation_args", "typed_signatures"})
    reset_open_questions(workspace)
    record_service_identity_gaps(workspace, catalogs)
    rows = workspace.query("endpoints")
    questions = workspace.query("open_questions")
    workspace.close()

    assert rows == []
    # One per catalog: each says its own framework could not be confirmed, and a
    # reader closing either closes the question for both.
    assert {q["question"] for q in questions} == {"handler_protocol"}
    assert {str(q["path"]) for q in questions} == {"com/acme/orders/LiveController#"}
    assert all(q["protocol"] is None for q in questions)


# --- F2 §3.7 (G-38): a WebFlux `@Controller`. ---------------------------------
_WEBFLUX_COORDINATE = "org.springframework:spring-webflux"
_WEBMVC_COORDINATE = "org.springframework:spring-webmvc"


def _webflux_controller_facts(root: Path) -> None:
    """`@Controller` on the class, `@GetMapping("/orders")` on a method — the
    plainest HTTP controller there is, and the one shape both Spring web stacks
    serve identically."""
    owner = "com/acme/orders/OrderController#"
    method = f"{owner}list()."
    document = Document(
        document_id="doc_flux",
        relative_path="com/acme/orders/OrderController.java",
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
    write_fact_file(
        root / "OrderController.jsonl",
        document,
        [
            SymbolFact(document_id="doc_flux", symbol=owner, construct_kind=ConstructKind.CLASS),
            SymbolFact(
                document_id="doc_flux",
                symbol=method,
                construct_kind=ConstructKind.METHOD,
                enclosing=owner,
                signature=Signature(parameters=[], returns=TypeRef(symbol="Ljava/lang/String;")),
            ),
            AnnotationFact(
                document_id="doc_flux",
                target=owner,
                retention="runtime",
                use=AnnotationUse(annotation=_SPRING_CONTROLLER, args={}),
            ),
            AnnotationFact(
                document_id="doc_flux",
                target=method,
                retention="runtime",
                use=AnnotationUse(annotation=_GET_MAPPING, args={"value": ["/orders"]}),
            ),
        ],
    )


def _controller_rows(
    tmp_path: Path, coordinates: tuple[str, ...], catalog: Catalog | None = None
) -> set:
    root = tmp_path / "facts"
    _webflux_controller_facts(root)
    write_fixture_module_fact_with(root, coordinates)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    catalogs = (
        [c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-mvc"]
        if catalog is None
        else [catalog]
    )
    derive_endpoints(workspace, catalogs, capabilities=FIXTURE_CAPABILITIES)
    found = {(str(row["method"]), str(row["path"])) for row in workspace.query("endpoints")}
    workspace.close()
    return found


def test_a_controller_in_a_webflux_module_derives_its_routes(tmp_path: Path):
    """F2 §3.7's acceptance, and the run that says G-38 predicted a bug the code
    does not have.

    G-38 read `spring-mvc.yml`'s `detect.coordinates: [spring-webmvc]` and
    concluded a WebFlux module derives nothing. THIS catalog's coordinates are
    read by nothing — `DEPENDENCY_GATED` holds two other styles, and it sets no
    `detect.required` — so the gate G-38 described has never existed and the row
    derives. (Style is not what decides it: `spring-stomp` and `spring-rsocket`
    are `annotation_driven` too and their coordinates ARE read, because they set
    `detect.required`.)

    The coordinate list is now TRUE as well as inert: both stacks ship a
    `RequestMappingHandlerMapping` whose bean predicate is
    `hasAnnotation(beanType, Controller.class)`, byte for byte the same in each at
    6.1.6 and 7.0.2 (`scripts/probes/w17_webflux_controller.md` section 1). This
    test is what fails if someone narrows it back and sets `detect.required` —
    the one-line change that would have made G-38's prediction true.
    """
    assert _controller_rows(tmp_path, (_WEBFLUX_COORDINATE,)) == {("GET", "/orders")}


def test_the_same_controller_in_an_mvc_module_derives_the_same_routes(tmp_path: Path):
    """The paired positive (GUIDELINES §10). Identical facts, the other stack's
    coordinate: the two builds are not merely both non-empty, they derive the SAME
    row, which is what "WebFlux's handler gate is byte-for-byte identical" means
    for output rather than for bytecode."""
    assert _controller_rows(tmp_path, (_WEBMVC_COORDINATE,)) == {("GET", "/orders")}


def test_the_shipped_coordinate_list_names_both_web_stacks():
    """What the widening actually pins, asserted offline against the shipped file.

    The two tests above pass whatever this list says, because nothing reads it for
    this catalog — so neither of them pins its CONTENT, and a review found the
    design claiming they did. This one does: the list is a statement about which
    builds serve `@Controller`, both stacks serve it (measured, byte for byte, at
    two versions each — `scripts/probes/w17_webflux_controller.md` section 1), and
    a list naming one of them is false whether or not anything reads it.
    """
    catalog = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-mvc")
    assert set(catalog.detect_coordinates) == {_WEBMVC_COORDINATE, _WEBFLUX_COORDINATE}


def test_narrowing_the_list_and_gating_on_it_is_what_would_lose_the_webflux_rows(
    tmp_path: Path,
):
    """The near-miss (GUIDELINES §10), and the one-line change it guards against.

    G-38's prediction was not true of any tree that ever shipped, but it is one
    line from being true: `detect.required` (F2 §3.6) is a key a catalog author
    can add, and adding it to a list naming only `spring-webmvc` deletes every
    WebFlux `@Controller` route in the estate. Both halves are needed and this
    asserts exactly that pair — the shipped list with the gate on still derives,
    the narrowed list with the gate on derives NOTHING.

    Built by replacing the two fields on the shipped catalog rather than by
    editing the file, so what is under test is the shipped rule with one field
    changed, not a catalog invented here.
    """
    shipped = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-mvc")
    gated = replace(shipped, detect_required=True)
    narrowed = replace(shipped, detect_required=True, detect_coordinates=(_WEBMVC_COORDINATE,))
    assert _controller_rows(tmp_path / "widened", (_WEBFLUX_COORDINATE,), gated) == {
        ("GET", "/orders")
    }
    assert _controller_rows(tmp_path / "narrowed", (_WEBFLUX_COORDINATE,), narrowed) == set()


# --- F2 §3.8 (W19): `slice.outside` refuses a slice that says nothing. -------
@pytest.mark.parametrize(
    ("block", "expected"),
    [
        pytest.param("slice: []\n", "must be a mapping", id="not a mapping"),
        pytest.param("slice:\n  outside: []\n", "non-empty list", id="outside is empty"),
        pytest.param(
            "slice:\n  outside:\n    - {owner: a.B, method_names: [x]}\n",
            "declares no why",
            id="no reason given",
        ),
        pytest.param(
            "slice:\n  outside:\n    - {owner: a.B, why: because}\n",
            "must declare exactly one of",
            id="no kind of name given",
        ),
        pytest.param(
            "slice:\n  outside:\n"
            "    - {owner: a.B, method_names: [x], annotation_names: [y], why: because}\n",
            "must declare exactly one of",
            id="two kinds of name given",
        ),
        pytest.param(
            "slice:\n  outside:\n    - {owner: a.B, method_names: x, why: because}\n",
            "must be a list of names",
            id="methods not a list",
        ),
        pytest.param(
            "slice:\n  outside:\n    - {owner: a.B, annotation_names: [1], why: because}\n",
            "`annotation_names` must be a list of names",
            id="annotations not names",
        ),
        pytest.param(
            "slice:\n  outside:\n    - {owner: a.B, type_names: x, why: because}\n",
            "`type_names` must be a list of names",
            id="types not a list",
        ),
    ],
)
def test_a_slice_that_states_nothing_is_refused(tmp_path: Path, block: str, expected: str):
    """Each refusal in `_slice_outside`, exercised — the review that added this file
    found all four unreached, and the review of the NEXT change found the two rules
    that replaced them unreached as well (§10, twice).

    The "exactly one of" rule is the one that needs both arms. Zero kinds means the
    entry names nothing and is unverifiable; two kinds means the audit cannot tell
    which enumeration to check it against — a method, an annotation and a repository
    contract are measured by different probes.

    The `why` is the one worth spelling out. A slice entry without it records that
    a method is unread and not WHY, and "this is not a boundary" and "this is a
    boundary we do not model" are different claims — a reader deciding whether this
    catalog covers their code needs to know which. Defaulting it would let the
    cheaper of the two answers be the silent one.
    """
    directory = _catalog_dir(tmp_path, _VALID_CATALOG + block)

    with pytest.raises(CatalogError) as failure:
        YamlCatalogSource(directory).load()

    assert expected in str(failure.value)
    assert "invented.yml" in str(failure.value)
