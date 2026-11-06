"""JVMS 5.4.3.3 resolution, and the reason it states (F3 §4.2, W22).

`Dispatch.resolve` is a four-way classifier whose SEARCH ORDER is the item's entire
correctness premise, and it shipped for review with nothing asserting any of it. The
review found the order wrong — a breadth-first frontier answered from a depth-1
interface while a depth-2 superclass held the body — and one three-type fixture would
have caught it. This file is that fixture, and the rest of the set beside it.

Hand-built facts rather than the compiled corpus: the cases that matter are shapes the
corpora happen not to contain (a method on both a superclass and an interface, an
unscanned link mid-chain), and a test that can only assert what today's corpus happens
to hold is a test that stops working the moment the corpus changes.
"""

from pathlib import Path

from fixture_build import compile_fixture
from sextant.application.resolve.call_edges import _record_resolution
from sextant.application.resolve.dispatch import Dispatch
from sextant.application.resolve.values import EXTERNAL, NOT_READABLE
from sextant.domain.symbols import bare_descriptor, method_descriptor

VOID = "()V"


def _dispatch(
    *,
    declares: dict[str, list[str]],
    ancestors: dict[str, list[tuple[str, str, bool]]],
    scanned: set[str] | None = None,
) -> Dispatch:
    """A workspace's resolution inputs, spelled directly.

    `scanned` defaults to every type named as a child or as a declarer, which is what
    the real index produces — a type has parent edges only because its own class file
    was read. A test needing an UNSCANNED ancestor names it in an edge and leaves it
    out of `declares`.
    """
    declared = {
        method_descriptor(owner, name, VOID) for owner, names in declares.items() for name in names
    }
    if scanned is None:
        scanned = set(declares) | set(ancestors)
    return Dispatch(bodies={}, declared=declared, subtypes={}, ancestors=ancestors, scanned=scanned)


def test_a_method_the_owner_declares_resolves_to_the_owner():
    dispatch = _dispatch(declares={"p/A#": ["foo"]}, ancestors={})

    assert dispatch.resolve("p/A#", "foo", VOID) == ("p/A#", None)


def test_a_method_on_a_scanned_superclass_resolves_to_it():
    """The shape the whole item exists for: `Owner#setId`, declared on `BaseEntity`."""
    dispatch = _dispatch(
        declares={"p/Base#": ["setId"], "p/Owner#": ["getName"]},
        ancestors={"p/Owner#": [("p/Base#", "extends", True)]},
    )

    assert dispatch.resolve("p/Owner#", "setId", VOID) == ("p/Base#", None)


def test_the_superclass_chain_is_exhausted_before_any_interface():
    """5.4.3.3 steps 2 and 3, and the defect this file was written for.

    `A extends B implements I`, `B extends C`, and BOTH `C` and `I` declare the method.
    The JVM runs `C`'s: the superclass chain is searched to exhaustion before any
    superinterface. A breadth-first frontier seeded with every direct supertype answers
    `I` — which is wrong twice over, because `candidates` then finds no body under `I`
    and returns empty, recreating this item's own defect one level deeper.
    """
    dispatch = _dispatch(
        declares={"p/C#": ["foo"], "p/I#": ["foo"]},
        ancestors={
            "p/A#": [("p/B#", "extends", True), ("p/I#", "implements", True)],
            "p/B#": [("p/C#", "extends", True)],
        },
    )

    assert dispatch.resolve("p/A#", "foo", VOID) == ("p/C#", None)


def test_an_interface_answers_when_no_superclass_declares_the_method():
    """The other half of the same rule: the interface arm is reached, just second."""
    dispatch = _dispatch(
        declares={"p/I#": ["foo"]},
        ancestors={
            "p/A#": [("p/B#", "extends", True), ("p/I#", "implements", True)],
            "p/B#": [],
        },
    )

    assert dispatch.resolve("p/A#", "foo", VOID) == ("p/I#", None)


def test_an_owner_this_workspace_never_read_is_the_third_party_boundary():
    dispatch = _dispatch(declares={"p/A#": ["foo"]}, ancestors={})

    assert dispatch.resolve("java/util/List#", "size", VOID) == (
        None,
        "java/util/List#",
    )


def test_an_unscanned_ancestor_is_told_apart_from_an_unscanned_owner():
    """The distinction the item is FOR, and the one a single word could not make.

    `Builder` was scanned; its superclass ships in a jar. We know more than "external":
    the body is inherited from something we did not open, and `type_hierarchy` names
    which type that is. 158 call sites in `fixtures/orders-service` are this — Avro and
    protobuf generated code — and every one of them used to be indistinguishable from a
    call into a library we had never heard of.
    """
    dispatch = _dispatch(
        declares={"p/Builder#": ["ownMethod"]},
        ancestors={
            "p/Builder#": [("org/apache/avro/SpecificRecordBuilderBase#", "extends", False)]
        },
        scanned={"p/Builder#"},
    )

    assert dispatch.resolve("p/Builder#", "fields", VOID) == (
        None,
        "org/apache/avro/SpecificRecordBuilderBase#",
    )


def test_a_scanned_owner_whose_whole_closure_declares_nothing_says_so():
    """Not `external` for the owner, which would claim a third-party boundary for a type we
    read. The first draft returned that word here — the set had no member for "we looked
    everywhere we could and found nothing", and a missing member invites the reuse."""
    dispatch = _dispatch(
        declares={"p/A#": ["other"], "p/Base#": ["another"], "java/lang/Object#": []},
        ancestors={"p/A#": [("p/Base#", "extends", True)]},
    )

    assert dispatch.resolve("p/A#", "missing", VOID) == (
        None,
        None,
    )


def test_a_method_nothing_here_declares_ends_at_object_which_is_not_read():
    """JVMS 5.4.3.3 and 5.4.3.4 both end at `java/lang/Object`. The extractor writes no
    superclass fact for it, so the search names it as the first unread type. A module
    interface calling `equals` is `invokeinterface I.equals`, which real code produces."""
    dispatch = _dispatch(
        declares={"p/I#": ["other"]},
        ancestors={"p/C#": [("p/I#", "implements", True)]},
    )

    assert dispatch.resolve("p/I#", "equals", VOID) == (None, "java/lang/Object#")
    assert dispatch.resolve("p/C#", "hashCode", VOID) == (None, "java/lang/Object#")


def test_an_object_method_on_an_interface_is_external_naming_object():
    dispatch = _dispatch(declares={"p/I#": ["other"]}, ancestors={})
    recorder = _Recorder()

    for name in ("equals", "hashCode", "toString"):
        _record_resolution(recorder, dispatch, [_site("p/I#", name)])  # type: ignore[arg-type]
        (row,) = recorder.rows
        assert row["reason"] == EXTERNAL
        assert (
            row["detail"]
            == "p/I is read, but its ancestor java/lang/Object is not in the scanned code"
        )


def test_an_object_that_is_read_answers_with_its_own_declaration():
    dispatch = _dispatch(declares={"java/lang/Object#": ["equals"], "p/I#": []}, ancestors={})
    dispatch.scanned.add("p/I#")

    assert dispatch.resolve("p/I#", "equals", VOID) == ("java/lang/Object#", None)


def test_an_array_owner_is_named_as_an_array_in_the_detail():
    dispatch = _dispatch(declares={}, ancestors={})
    recorder = _Recorder()

    _record_resolution(recorder, dispatch, [_site("p/Role#[]", "clone")])  # type: ignore[arg-type]

    (row,) = recorder.rows
    assert row["detail"] == "p/Role[] is not in the scanned code"


def test_a_constructor_is_never_resolved_to_an_ancestors():
    """Constructors are not inherited (JLS 8.8), so walking ancestors for `<init>` could
    only ever produce a wrong answer. No corpus has contained a call that would, which
    is why this is asserted rather than left to be discovered."""
    dispatch = _dispatch(
        declares={"p/Base#": ["<init>"]},
        ancestors={"p/A#": [("p/Base#", "extends", True)]},
        scanned={"p/A#", "p/Base#"},
    )

    assert dispatch.resolve("p/A#", "<init>", VOID) == (
        None,
        None,
    )


class _Recorder:
    """What `_record_resolution` hands the workspace, kept instead of stored."""

    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    def derive(self, name: str, **arguments: object) -> None:
        if name == "method_resolution_insert":
            self.rows = list(arguments["rows"])  # type: ignore[call-overload]


def _site(owner: str, name: str) -> dict[str, object]:
    return {"owner": owner, "name": name, "descriptor": VOID, "invoke_kind": "virtual"}


def test_a_found_method_row_has_no_reason_and_no_detail():
    dispatch = _dispatch(
        declares={"p/Base#": ["setId"]}, ancestors={"p/Owner#": [("p/Base#", "extends", True)]}
    )
    recorder = _Recorder()

    _record_resolution(recorder, dispatch, [_site("p/Owner#", "setId")])  # type: ignore[arg-type]

    assert recorder.rows == [
        {
            "class": "p/Owner#",
            "name": "setId",
            "descriptor": VOID,
            "declaring_class": "p/Base#",
            "reason": None,
            "detail": None,
        }
    ]


def test_an_owner_never_read_is_external_and_the_detail_names_it():
    dispatch = _dispatch(declares={}, ancestors={})
    recorder = _Recorder()

    _record_resolution(recorder, dispatch, [_site("java/util/List#", "size")])  # type: ignore[arg-type]

    (row,) = recorder.rows
    assert row["declaring_class"] is None
    assert row["reason"] == EXTERNAL
    assert row["detail"] == "java/util/List is not in the scanned code"


def test_an_unread_ancestor_is_external_and_the_detail_names_the_ancestor():
    dispatch = _dispatch(
        declares={"p/Builder#": ["ownMethod"]},
        ancestors={"p/Builder#": [("org/avro/Base#", "extends", False)]},
        scanned={"p/Builder#"},
    )
    recorder = _Recorder()

    _record_resolution(recorder, dispatch, [_site("p/Builder#", "fields")])  # type: ignore[arg-type]

    (row,) = recorder.rows
    assert row["reason"] == EXTERNAL
    assert (
        row["detail"]
        == "p/Builder is read, but its ancestor org/avro/Base is not in the scanned code"
    )


def test_a_read_closure_without_the_declaration_is_not_readable():
    dispatch = _dispatch(
        declares={"p/A#": ["other"], "p/Base#": ["another"], "java/lang/Object#": []},
        ancestors={"p/A#": [("p/Base#", "extends", True)]},
    )
    recorder = _Recorder()

    _record_resolution(recorder, dispatch, [_site("p/A#", "missing")])  # type: ignore[arg-type]

    (row,) = recorder.rows
    assert row["reason"] == NOT_READABLE
    assert row["detail"] == "no declaration of missing(..) in p/A or its scanned ancestors"


def test_the_coverage_distribution_counts_found_bodies_as_resolved(tmp_path: Path):
    from sextant.storage.duckdb.workspace import DuckDbWorkspace

    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    base = {"name": "m", "descriptor": VOID}
    rows = [
        {**base, "class": "p/A#", "declaring_class": "p/A#", "reason": None, "detail": None},
        {**base, "class": "p/B#", "declaring_class": "p/A#", "reason": None, "detail": None},
        {**base, "class": "p/C#", "declaring_class": None, "reason": EXTERNAL, "detail": "x"},
    ]
    workspace.derive("method_resolution_insert", rows=rows)

    counted = {
        row["bucket"]: row["methods"] for row in workspace.query("method_resolution_distribution")
    }
    workspace.close()

    assert counted == {"resolved": 2, EXTERNAL: 1}


# --- W23 / G-48: `return_flows` and the inherited accessor -------------------


def test_a_value_returned_from_an_inherited_getter_links_to_its_declaring_class(
    tmp_path: Path,
):
    """W23's whole deliverable, on real compiled bytecode.

    G-48: "the same defect as G-1 costs `return_flows` its in-module accessor links …
    every one of the 28 is an accessor inherited from `BaseEntity`/`Person`/
    `NamedEntity` — precisely the values a reader follows to see what a response is
    built from." The gap analysis ruled it **CORRECT (rides G-1)**, meaning fixing
    resolution fixes this, and measurement agrees: `spring-petclinic-rest` gained 78
    `return_flows` rows arising from inherited accessors the moment W22 landed, with no
    change to `return_flow.py` at all.

    That is exactly why this test exists. An item delivered as a side effect of another
    is an item with nothing holding it: `record_return_flows` reads `dispatch_of`, and a
    later change narrowing resolution would take these links away silently, in a file
    whose own tests all still pass. `CustomerRegistry#identify` returns
    `customer.getId()`, where `getId` is declared on `BaseEntity` and called through
    `Customer`.
    """

    from sextant.application.ports.scanner import ScanRequest
    from sextant.application.resolve.return_flow import record_return_flows
    from sextant.ingress.extract.jvm.scanner import AsmScanner
    from sextant.resources import extractor_jar
    from sextant.storage.duckdb.workspace import DuckDbWorkspace

    fixture = Path(__file__).parents[2] / "fixtures" / "orders-service"
    compile_fixture(fixture)
    facts = tmp_path / "facts"
    AsmScanner(extractor_jar()).scan(
        ScanRequest(
            module_id="com.acme:orders-service",
            coordinates="com.acme/orders-service",
            version="1.0.0",
            classes_dir=fixture / "target" / "classes",
            out_dir=facts,
        )
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    record_return_flows(workspace)

    linked = {
        (bare_descriptor(str(row["caller"])), bare_descriptor(str(row["callee"])))
        for row in workspace.query("return_flows")
        if row["callee"] is not None
    }
    workspace.close()

    assert ("com/acme/orders/model/CustomerRegistry#identify().", "") not in linked
    assert any(
        caller.startswith("com/acme/orders/model/CustomerRegistry#identify")
        and callee.startswith("com/acme/orders/model/BaseEntity#getId")
        for caller, callee in linked
    ), (
        "a getter declared on a scanned superclass must link to its declaring class; "
        "before W22 this call reached no body and the value chain stopped at it"
    )
