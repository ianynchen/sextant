"""Two handlers a framework would REFUSE to register on one address (F5 §6.1, W28).

## Why almost every test here is a near-miss

Measured before a line was written, across the orders-service fixture and `mall-admin`,
`spring-petclinic-rest` and `jhipster-sample-app`: **zero genuine conflicts**, and one
pair that looks exactly like one and is not — `@KafkaListener` on a class with
`@KafkaHandler` on its methods, which dispatches by PAYLOAD TYPE, so `order-polymorphic`
is served by two methods and Spring Kafka is perfectly happy.

A detector whose first act on real code is to invent a finding is worse than no detector.
So the rule is catalog data (`mapping.duplicate: conflict`), only the two catalogs whose
annotations reach `RequestMappingHandlerMapping` declare it, and the comparison is
everything `RequestMappingInfo.equals` compares that a class file states.

## What Spring compares, read from Spring

`AbstractHandlerMethodMapping$MappingRegistry.validateMethodMapping` throws
`IllegalStateException` when a different handler is already registered under an equal
mapping (spring-webmvc 6.1.6 bytecode). `RequestMappingInfo.equals` compares seven
conditions: patterns, methods, params, headers, consumes, produces, custom. Six are
readable; the seventh silences the module rather than being guessed at.
"""

import json
from pathlib import Path

import pytest
from test_shapes import _MODULE, _document, _type, _write

from sextant.application.ports.catalogs import Catalog
from sextant.application.resolve.routing_conflicts import record_routing_conflicts
from sextant.domain.facts import AnnotationFact, AnnotationUse
from sextant.storage.duckdb.workspace import DuckDbWorkspace

GET_MAPPING = "com.acme.rest.Get"
CLASS_MAPPING = "com.acme.rest.Path"
CUSTOM_BASE = "com.acme.rest.CustomMapping"
OWNER = "com/acme/orders/Controller#"
FIRST = OWNER + "first(sig_00000001)."
SECOND = OWNER + "second(sig_00000002)."
OTHER_OWNER = "com/acme/orders/OtherController#"
ELSEWHERE = OTHER_OWNER + "third(sig_00000003)."


def _catalog(**mapping: object) -> Catalog:
    """One inbound catalog whose mapping block a test composes.

    Every name here is invented — an invented annotation, an invented base type — for the
    reason every engine test in this directory gives: a rule read from catalog data is
    only proved to be read from catalog data if the data is not Spring's own spellings.
    The shipped catalogs' live answer is pinned once in `test_pipeline.py`.
    """
    return Catalog(
        id="invented-rest",
        style="annotation_driven",
        protocol="http",
        direction="inbound",
        requires=(),
        matches={
            "mapping": {
                "annotations": [{"fqn": GET_MAPPING, "method": ["GET"]}],
                "prefix_annotation": CLASS_MAPPING,
                **mapping,
            }
        },
        source=Path("tests/invented.yml"),
        wrappers=[],
        nullability={},
        serialization={},
        known_types=[],
    )


def _annotation(target: str, annotation: str, args: dict[str, object]) -> dict:
    """One annotation use, as the extractor writes it: the annotation and its arguments
    sit inside `use`, not beside it (D00 §5a).

    Built through the domain model and dumped, rather than hand-written, so a fact shape
    this test invents cannot drift from the one the scanner emits — the first version
    here wrote them flat and the pass read nothing at all, silently.
    """
    return AnnotationFact(
        document_id="doc",
        target=_MODULE + target,
        retention="runtime",
        use=AnnotationUse(annotation=annotation.replace(".", "/") + "#", args=args),
    ).model_dump(mode="json")


def _workspace(
    tmp_path: Path,
    rows: list[tuple[str, str, str | None]],
    annotations: list[dict] | None = None,
    supertypes: list[dict] | None = None,
) -> DuckDbWorkspace:
    """Endpoint rows as `(method, path, handler)` plus the annotation facts a
    discriminator is read from. `handler` None is a row naming none."""
    facts = tmp_path / "facts"
    _write(
        facts / "doc.jsonl",
        _document("doc", "Controller.java"),
        (annotations or []) + (supertypes or []),
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    for method, path, handler in rows:
        workspace._connection.execute(
            "INSERT INTO endpoints (row_id, protocol, direction, method, path, handler, catalog_id, "
            "consumes, produces) VALUES ((SELECT coalesce(max(row_id), 0) + 1 FROM endpoints), 'http', 'inbound', ?, ?, ?, 'invented-rest', NULL, NULL)",
            [method, path, None if handler is None else _MODULE + handler],
        )
    return workspace


def _conflicts(workspace: DuckDbWorkspace) -> list[dict[str, object]]:
    return [
        dict(row)
        for row in workspace.query("open_questions")
        if str(row["question"]) == "routing_conflict"
    ]


def test_two_handlers_on_one_address_are_a_conflict(tmp_path: Path):
    """The positive half (§10). Spring throws at startup rather than choosing, so a
    service with this in it does not run — which is why the two rows are reported rather
    than one of them being dropped."""
    workspace = _workspace(
        tmp_path,
        [("GET", "/orders", FIRST), ("GET", "/orders", SECOND)],
        [
            _annotation(FIRST, GET_MAPPING, {"value": ["/orders"]}),
            _annotation(SECOND, GET_MAPPING, {"value": ["/orders"]}),
        ],
    )

    record_routing_conflicts(workspace, [_catalog(duplicate="conflict")])
    conflicts = _conflicts(workspace)
    workspace.close()

    assert len(conflicts) == 1
    assert (conflicts[0]["method"], conflicts[0]["path"]) == ("GET", "/orders")
    assert [c["handler"] for c in json.loads(str(conflicts[0]["candidates"]))] == [FIRST, SECOND]


def test_a_catalog_that_does_not_declare_it_reports_nothing(tmp_path: Path):
    """The near-miss that matters most, and the one with a live instance.

    Several handlers on one address is ORDINARY in most frameworks. `@KafkaListener` on
    a class with `@KafkaHandler` on its methods dispatches by payload type, and this
    repo's fixture has exactly that on `order-polymorphic`. Reporting it would be a rule
    mirrored from one framework onto a set it does not describe — the defect class this
    codebase has found in W13, W14 and six times in W19's probes.
    """
    workspace = _workspace(
        tmp_path,
        [("GET", "/orders", FIRST), ("GET", "/orders", SECOND)],
        [
            _annotation(FIRST, GET_MAPPING, {"value": ["/orders"]}),
            _annotation(SECOND, GET_MAPPING, {"value": ["/orders"]}),
        ],
    )

    record_routing_conflicts(workspace, [_catalog()])
    conflicts = _conflicts(workspace)
    workspace.close()

    assert conflicts == []


@pytest.mark.parametrize("attribute", ["params", "headers"])
def test_a_declared_discriminator_separates_two_mappings(tmp_path: Path, attribute: str):
    """`RequestMappingInfo.equals` compares seven conditions and these are two of them,
    so two mappings differing in one are DIFFERENT mappings however identical their path
    and verb look.

    Both are parametrised rather than written once because a rule reading only the first
    name in the list would pass a test that used only that name — and the fixture's own
    `RoutingConditionsController` separates one pair by `params` and a third handler by
    `headers` for the same reason.
    """
    workspace = _workspace(
        tmp_path,
        [("GET", "/orders", FIRST), ("GET", "/orders", SECOND)],
        [
            _annotation(FIRST, GET_MAPPING, {"value": ["/orders"], attribute: ["view=summary"]}),
            _annotation(SECOND, GET_MAPPING, {"value": ["/orders"], attribute: ["view=full"]}),
        ],
    )

    record_routing_conflicts(
        workspace, [_catalog(duplicate="conflict", discriminators=["params", "headers"])]
    )
    conflicts = _conflicts(workspace)
    workspace.close()

    assert conflicts == []


def test_a_class_level_condition_is_unioned_not_overridden(tmp_path: Path):
    """`ParamsRequestCondition.combine` builds a `LinkedHashSet` of one side's
    expressions and adds the other's — a UNION — so a class-level `params` applies to
    every method in the class and separates none of them from each other.

    A rule that let the class value stand in for the method's would find both handlers
    carrying `v=1` and report no conflict, silently missing the one thing this detector
    is for.
    """
    workspace = _workspace(
        tmp_path,
        [("GET", "/orders", FIRST), ("GET", "/orders", SECOND)],
        [
            _annotation(OWNER, CLASS_MAPPING, {"value": ["/"], "params": ["v=1"]}),
            _annotation(FIRST, GET_MAPPING, {"value": ["/orders"]}),
            _annotation(SECOND, GET_MAPPING, {"value": ["/orders"]}),
        ],
    )

    record_routing_conflicts(
        workspace, [_catalog(duplicate="conflict", discriminators=["params", "headers"])]
    )
    conflicts = _conflicts(workspace)
    workspace.close()

    assert len(conflicts) == 1, (
        "a class-wide condition separates the class from other classes, never its own "
        "methods from each other"
    )


def test_a_class_level_condition_separates_two_classes(tmp_path: Path):
    """The half of the union rule that CHANGES an answer, and the one the sibling test
    above cannot reach.

    Two handlers in two different classes claim `/orders`, and one of those classes
    carries `params = "v=1"`. Spring combines the class condition into each of its
    methods' mappings, so the two are different mappings and both register. A rule that
    read only the METHOD's annotation would find `()` on both sides, call them equal, and
    report a conflict against a service that starts perfectly well.

    Written after a mutation showed the sibling test passing with the class level not
    read at all: there, both handlers lose the same value, so they stay equal and the
    conflict is still reported. The outcome was right for the wrong reason.
    """
    workspace = _workspace(
        tmp_path,
        [("GET", "/orders", FIRST), ("GET", "/orders", ELSEWHERE)],
        [
            _annotation(OWNER, CLASS_MAPPING, {"value": ["/"], "params": ["v=1"]}),
            _annotation(FIRST, GET_MAPPING, {"value": ["/orders"]}),
            _annotation(ELSEWHERE, GET_MAPPING, {"value": ["/orders"]}),
        ],
    )

    record_routing_conflicts(
        workspace, [_catalog(duplicate="conflict", discriminators=["params", "headers"])]
    )
    conflicts = _conflicts(workspace)
    workspace.close()

    assert conflicts == [], (
        "a class-level condition is part of every mapping in that class, so it separates "
        "them from mappings outside it"
    )


def test_one_handler_on_two_rows_is_not_a_conflict(tmp_path: Path):
    """A method reachable at one address through two annotations is one registration.
    The count that matters is DISTINCT handlers, and a rule counting rows would report
    every multi-annotation method in a codebase."""
    workspace = _workspace(
        tmp_path,
        [("GET", "/orders", FIRST), ("GET", "/orders", FIRST)],
        [_annotation(FIRST, GET_MAPPING, {"value": ["/orders"]})],
    )

    record_routing_conflicts(workspace, [_catalog(duplicate="conflict")])
    conflicts = _conflicts(workspace)
    workspace.close()

    assert conflicts == []


def test_rows_naming_no_address_or_no_handler_are_not_a_conflict(tmp_path: Path):
    """An unresolved row shares `path IS NULL` with every other unresolved row, and a
    row naming no handler names nothing that could claim anything. Pairing either would
    report a coincidence of absences as a defect in somebody's code."""
    workspace = _workspace(
        tmp_path,
        [("GET", None, FIRST), ("GET", None, SECOND), ("GET", "/x", None), ("GET", "/x", None)],
        [
            _annotation(FIRST, GET_MAPPING, {}),
            _annotation(SECOND, GET_MAPPING, {}),
        ],
    )

    record_routing_conflicts(workspace, [_catalog(duplicate="conflict")])
    conflicts = _conflicts(workspace)
    workspace.close()

    assert conflicts == []


def test_a_module_declaring_a_custom_condition_is_left_alone(tmp_path: Path):
    """The seventh condition, and the only one no class file states.

    A custom `RequestCondition` reaches a mapping through a subclass of the framework's
    handler mapping, and the condition itself is CODE. Two mappings separated only by one
    are indistinguishable from a genuine conflict here — so a module that registers such a
    subclass gets no conflict reported at all.

    Silence over a fabrication: a conflict named against a service that starts perfectly
    well is a claim, and a missing finding is not one (NFR-2).
    """
    workspace = _workspace(
        tmp_path,
        [("GET", "/orders", FIRST), ("GET", "/orders", SECOND)],
        [
            _annotation(FIRST, GET_MAPPING, {"value": ["/orders"]}),
            _annotation(SECOND, GET_MAPPING, {"value": ["/orders"]}),
        ],
        supertypes=[
            {
                "kind": "symbol",
                "document_id": "doc",
                "symbol": _MODULE + "com/acme/orders/MyMapping#",
                "construct_kind": "class",
                "enclosing": None,
                "superclass": CUSTOM_BASE.replace(".", "/") + "#",
                "visibility": "public",
                "line_start": 0,
                "line_end": 0,
            }
        ],
    )

    record_routing_conflicts(
        workspace, [_catalog(duplicate="conflict", custom_condition=CUSTOM_BASE)]
    )
    conflicts = _conflicts(workspace)
    workspace.close()

    assert conflicts == []


# The eight verbs `derive_endpoints.sql` fans a verbless mapping out to. Written here as
# the SQL's own output rather than re-derived, because that expansion is a separate,
# separately-tested mechanism and what this file has to pin is what the DETECTOR makes of
# it.
_ALL_VERBS = ("DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT", "TRACE")


def test_a_verbless_mapping_does_not_conflict_with_a_verb_specific_one(tmp_path: Path):
    """The false positive W28 shipped, and the reason the identity carries a verb SET.

    `RequestMethodsRequestCondition.equals` compares the DECLARED set, and an empty set is
    not equal to `{GET}` — so `@RequestMapping("/orders")` and `@GetMapping("/orders")` are
    two different mappings, Spring registers both, and a GET resolves to the more specific
    one. Comparing the single fanned-out verb collided them on the GET row and named an
    `IllegalStateException` against a module that starts perfectly well.

    Live-adjacent rather than hypothetical: `spring-petclinic-rest`'s
    `RootRestControllerV1` carries `@RequestMapping(value = "/")` and fans out to all
    eight, so one `@GetMapping("/")` beside it opened the detector with a false finding.
    """
    workspace = _workspace(
        tmp_path,
        [(verb, "/orders", FIRST) for verb in _ALL_VERBS] + [("GET", "/orders", SECOND)],
        [
            _annotation(FIRST, GET_MAPPING, {"value": ["/orders"]}),
            _annotation(SECOND, GET_MAPPING, {"value": ["/orders"]}),
        ],
    )

    record_routing_conflicts(workspace, [_catalog(duplicate="conflict")])
    conflicts = _conflicts(workspace)
    workspace.close()

    assert conflicts == []


def test_two_verbless_mappings_are_one_conflict_not_eight(tmp_path: Path):
    """The genuine conflict between two verbless mappings IS reported — once.

    One registration refused is one `IllegalStateException`, and eight questions naming
    the same two handlers would have a reader believe there are eight problems. The verb
    reads NULL because the registration names none: a verbless mapping answers at every
    verb, so naming one of them would say the conflict is narrower than it is.
    """
    workspace = _workspace(
        tmp_path,
        [(verb, "/orders", handler) for handler in (FIRST, SECOND) for verb in _ALL_VERBS],
        [
            _annotation(FIRST, GET_MAPPING, {"value": ["/orders"]}),
            _annotation(SECOND, GET_MAPPING, {"value": ["/orders"]}),
        ],
    )

    record_routing_conflicts(workspace, [_catalog(duplicate="conflict")])
    conflicts = _conflicts(workspace)
    workspace.close()

    assert len(conflicts) == 1
    assert conflicts[0]["method"] is None
    assert [c["handler"] for c in json.loads(str(conflicts[0]["candidates"]))] == [FIRST, SECOND]


def test_a_discriminator_composed_into_a_module_local_annotation_still_separates(
    tmp_path: Path,
):
    """The second false positive W28 shipped: discriminators read from the RAW annotation
    view while the endpoint row derived through the effective one.

    A module-local `@ApiGet` meta-annotated `@Get(params = "v=1")` mints its endpoint row
    through the composition pre-pass, but the annotation physically on the method is
    `ApiGet` — which the catalog does not name, so the `params` that separates it from the
    plain mapping beside it read as absent and the two compared equal. The fixture already
    ships a composed mapping annotation, so only the absence of `params` in that
    particular composition kept this green.
    """
    composed = "com.acme.rest.ApiGet"
    workspace = _workspace(
        tmp_path,
        [("GET", "/orders", FIRST), ("GET", "/orders", SECOND)],
        [
            _annotation(FIRST, composed, {}),
            _annotation(composed.replace(".", "/") + "#", GET_MAPPING, {"params": ["v=1"]}),
            _annotation(SECOND, GET_MAPPING, {"value": ["/orders"]}),
        ],
        [_type("doc", composed.replace(".", "/") + "#", "annotation")],
    )

    record_routing_conflicts(workspace, [_catalog(duplicate="conflict", discriminators=["params"])])
    conflicts = _conflicts(workspace)
    workspace.close()

    assert conflicts == []


def _subclass(symbol: str, parent: str) -> dict:
    """One `X extends Y` symbol fact, both spelled as bare descriptors."""
    return {
        "kind": "symbol",
        "document_id": "doc",
        "symbol": _MODULE + symbol,
        "construct_kind": "class",
        "enclosing": None,
        "superclass": parent,
        "visibility": "public",
        "line_start": 0,
        "line_end": 0,
    }


def test_a_custom_condition_two_levels_up_still_silences_the_detector(tmp_path: Path):
    """A multi-level chain is silenced, through its own intermediate.

    Spring Data REST ships exactly this: `RepositoryRestHandlerMapping` extends
    `BasePathAwareHandlerMapping` extends `RequestMappingHandlerMapping`. W28's review
    read the direct-edge test as missing it and proposed a transitive walk; measured, the
    two are the same question — a closure contains the base only if some direct edge
    points at it — and the middle link is what silences here.

    The near-miss below is where the boundary really stops.
    """
    workspace = _workspace(
        tmp_path,
        [("GET", "/orders", FIRST), ("GET", "/orders", SECOND)],
        [
            _annotation(FIRST, GET_MAPPING, {"value": ["/orders"]}),
            _annotation(SECOND, GET_MAPPING, {"value": ["/orders"]}),
        ],
        supertypes=[
            _subclass("com/acme/orders/Middle#", CUSTOM_BASE.replace(".", "/") + "#"),
            _subclass("com/acme/orders/Mine#", _MODULE + "com/acme/orders/Middle#"),
        ],
    )

    record_routing_conflicts(
        workspace, [_catalog(duplicate="conflict", custom_condition=CUSTOM_BASE)]
    )
    conflicts = _conflicts(workspace)
    workspace.close()

    assert conflicts == []


def test_a_custom_condition_reached_through_an_UNSCANNED_intermediate_is_not_silenced(
    tmp_path: Path,
):
    """The boundary's real edge, and an over-report this analysis cannot close.

    A module's own class extending a framework subclass that lives in an UNSCANNED jar
    has no fact saying what that intermediate extends, so nothing here can know the base
    is above it and the conflict IS reported. Same stop `resolve/terminals.py` documents
    for its supertype route, and closing it needs dependency scanning rather than a
    longer walk (W28 review, measured while checking whether transitivity would help —
    it does not).

    Asserted rather than left implicit because it is an over-report, the direction NFR-2
    rates worst: a reader meeting a `routing_conflict` on such a module is being told
    about a service that may well start.
    """
    workspace = _workspace(
        tmp_path,
        [("GET", "/orders", FIRST), ("GET", "/orders", SECOND)],
        [
            _annotation(FIRST, GET_MAPPING, {"value": ["/orders"]}),
            _annotation(SECOND, GET_MAPPING, {"value": ["/orders"]}),
        ],
        # `Middle` has no fact of its own — it is the unscanned jar's class.
        supertypes=[_subclass("com/acme/orders/Mine#", _MODULE + "com/acme/orders/Middle#")],
    )

    record_routing_conflicts(
        workspace, [_catalog(duplicate="conflict", custom_condition=CUSTOM_BASE)]
    )
    conflicts = _conflicts(workspace)
    workspace.close()

    assert len(conflicts) == 1
