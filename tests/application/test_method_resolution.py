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

from sextant.application.resolve.dispatch import Dispatch
from sextant.domain.closed_sets import MethodResolution
from sextant.domain.symbols import method_descriptor

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

    assert dispatch.resolve("p/A#", "foo", VOID) == ("p/A#", MethodResolution.DECLARED_HERE)


def test_a_method_on_a_scanned_superclass_resolves_to_it():
    """The shape the whole item exists for: `Owner#setId`, declared on `BaseEntity`."""
    dispatch = _dispatch(
        declares={"p/Base#": ["setId"], "p/Owner#": ["getName"]},
        ancestors={"p/Owner#": [("p/Base#", "extends", True)]},
    )

    assert dispatch.resolve("p/Owner#", "setId", VOID) == ("p/Base#", MethodResolution.INHERITED)


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

    assert dispatch.resolve("p/A#", "foo", VOID) == ("p/C#", MethodResolution.INHERITED)


def test_an_interface_answers_when_no_superclass_declares_the_method():
    """The other half of the same rule: the interface arm is reached, just second."""
    dispatch = _dispatch(
        declares={"p/I#": ["foo"]},
        ancestors={
            "p/A#": [("p/B#", "extends", True), ("p/I#", "implements", True)],
            "p/B#": [],
        },
    )

    assert dispatch.resolve("p/A#", "foo", VOID) == ("p/I#", MethodResolution.INHERITED)


def test_an_owner_this_workspace_never_read_is_the_third_party_boundary():
    dispatch = _dispatch(declares={"p/A#": ["foo"]}, ancestors={})

    assert dispatch.resolve("java/util/List#", "size", VOID) == (
        None,
        MethodResolution.OWNER_NOT_SCANNED,
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
        MethodResolution.ANCESTOR_NOT_SCANNED,
    )


def test_a_scanned_owner_whose_whole_closure_declares_nothing_says_so():
    """Not `owner_not_scanned`, which would claim a third-party boundary for a type we
    read. The first draft returned that word here — the set had no member for "we looked
    everywhere we could and found nothing", and a missing member invites the reuse."""
    dispatch = _dispatch(
        declares={"p/A#": ["other"], "p/Base#": ["another"]},
        ancestors={"p/A#": [("p/Base#", "extends", True)]},
    )

    assert dispatch.resolve("p/A#", "missing", VOID) == (
        None,
        MethodResolution.NO_DECLARATION_FOUND,
    )


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
        MethodResolution.NO_DECLARATION_FOUND,
    )
