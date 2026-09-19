"""Shared reads for rules conditional on annotations (spec 2026-09-18 §2, §4):
where an owner's and its type's annotations are, once per load, and the
`annotation_arg` condition built on top of them.

Built through `Workspace.once` so the `annotations` decode runs once per load
rather than once per catalog (`annotation_driven._annotation_rows`' reason).
Read by the body rule (`shapes/contracts.py`), the conditional wrapper filter
and the `protocol_hint` pass; written by none of them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sextant.application.ports.catalogs import CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.domain.symbols import bare_descriptor, is_type_descriptor, owner_of, type_descriptor

# `type_descriptor`, not `shapes/rooting.py`'s `_catalog_symbol` re-export of the
# same function: that name is `rooting`'s own private seam for `rooting`'s own
# callers, and this module already reaches `domain.symbols` directly for
# `is_type_descriptor`/`owner_of` above — a second entry point for the same
# conversion would be the ad hoc duplication the seam exists to prevent.
_catalog_symbol = type_descriptor


def enclosing_type_of(symbol: str) -> str | None:
    """The type a member symbol belongs to, `#` included — the coordinates
    prefix carries no `#`, so this holds for a full symbol and a bare
    descriptor alike (D00 §5a). None for a type or a free function. Read
    through the two `domain.symbols` questions rather than the marker itself:
    the grammar stays behind that seam."""
    return None if is_type_descriptor(symbol) else owner_of(symbol)


def annotation_index(workspace: Workspace) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    """target → [(annotation descriptor, args)], every annotation row once."""
    return workspace.once(_annotation_index)


def member_annotations_by_type(workspace: Workspace) -> dict[str, set[str]]:
    """enclosing type → the annotation descriptors any field or method declared
    in it carries — Quarkus's parameter-container rule reads exactly this
    (CP-19 row 4)."""
    return workspace.once(_member_annotations_by_type)


# The builders are module-level, not closures: `Workspace.once` keys its fold on
# the callable itself, and a function defined inside each call would be a new key
# every time — rebuilt per call and never found again.


def _annotation_index(workspace: Workspace) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    found: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for row in workspace.query("annotations"):
        args = json.loads(str(row["args"])) if row["args"] is not None else {}
        found.setdefault(str(row["target"]), []).append((str(row["annotation"]), args))
    for entries in found.values():
        entries.sort(key=lambda entry: entry[0])
    return found


def _member_annotations_by_type(workspace: Workspace) -> dict[str, set[str]]:
    # `located_symbols`, not `symbols`: the three columns this needs — symbol,
    # kind, enclosing type — over the same view, and a query `once` accepts
    # (`symbols` is not on the workspace's facts-only list, so a fold reading
    # it is refused).
    enclosing = {
        str(row["symbol"]): str(row["enclosing"])
        for row in workspace.query("located_symbols")
        if row.get("enclosing") and str(row["construct_kind"]) in ("field", "method")
    }
    # `bare_descriptor` on the KEY (fix, B/C Task 10 fix round 1): `located_symbols.enclosing`
    # carries the fact's own FULL symbol — module coordinates and all — while every caller
    # of this map (`shapes/contracts.py::_is_bound`, predicate 3) compares against a
    # parameter's `erased_symbol`/`type.symbol`, which a `Signature` always carries BARE
    # (D00 §5a: "a symbol is module coordinates then a descriptor... only the descriptor is
    # ever compared"). Left full, `found`'s keys never matched a real parameter's type —
    # `container` silently matched nothing outside a hand-built unit test using bare symbols
    # on both sides (`test_container_binding_reads_the_parameters_class_members`,
    # `test_shapes.py`), and a Quarkus module's own `@RestForm`-carrying parameter container
    # (`OrderResource#upload(Upload form)`, `fixtures/orders-quarkus`) was reported as the
    # request BODY rather than excluded, live, the first time this ran end to end.
    found: dict[str, set[str]] = {}
    for target, entries in annotation_index(workspace).items():
        owner = enclosing.get(target)
        if owner is not None:
            found.setdefault(bare_descriptor(owner), set()).update(
                annotation for annotation, _ in entries
            )
    return found


# The `annotation_arg` condition (spec §2): `when: {annotation_arg: {annotation,
# name, equals | parses_true}}`, read on the owner symbol and, only if the owner
# carries no such annotation at all, on its enclosing type. Two consumers land
# after this task: `wrappers[].when` (D02 §2a, shapes/contracts.py — Task 8) and
# `protocol_hint.hint_when` (Task 9). Neither exists yet, so nothing calls
# `parse_condition`/`holds` today.

_CONDITION_KEYS = frozenset({"annotation_arg"})
_ARG_KEYS = frozenset({"annotation", "name", "equals", "parses_true"})


@dataclass(frozen=True)
class AnnotationArg:
    """One parsed `annotation_arg` condition. `annotation` is already in
    descriptor form (`_catalog_symbol`, the comparison grammar `annotation_index`
    is keyed in); `names` is the alias list in the order the catalog wrote them,
    first present wins; exactly one of `equals`/`parses_true` is set — the other
    stays at its default (`None`/`False`), never read once the wrong one is."""

    annotation: str
    names: tuple[str, ...]
    equals: str | None
    parses_true: bool


def parse_condition(declared: object, where: str) -> AnnotationArg:
    """Parses a catalog's `when` block into an `AnnotationArg`, or refuses it by
    name (spec §2, NFR-5: the vocabulary is CLOSED). `where` is what the caller
    can say about the site — the catalog file and key — so a refusal names the
    place, not just the shape (§13.6)."""
    if not isinstance(declared, dict) or set(declared) != _CONDITION_KEYS:
        raise CatalogError(
            f"{where}: `when` must be exactly `{{annotation_arg: {{...}}}}` — got {declared!r} "
            "(spec 2026-09-18 §2, closed)"
        )
    arg = declared["annotation_arg"]
    if (
        not isinstance(arg, dict)
        or not set(arg) <= _ARG_KEYS
        or "annotation" not in arg
        or "name" not in arg
    ):
        raise CatalogError(
            f"{where}: `annotation_arg` takes `annotation`, `name` and exactly one of "
            f"`equals`/`parses_true` — got {arg!r}"
        )
    has_equals, has_parses = "equals" in arg, "parses_true" in arg
    if has_equals == has_parses:
        raise CatalogError(
            f"{where}: `annotation_arg` needs exactly one comparator, `equals` or `parses_true` — "
            f"got {arg!r}"
        )
    if has_parses and arg["parses_true"] is not True:
        raise CatalogError(
            f"{where}: `parses_true` is written `parses_true: true`; it names "
            "`Boolean.parseBoolean` after `hasText`, not a value to compare"
        )
    names = arg["name"] if isinstance(arg["name"], list) else [arg["name"]]
    if (
        not names
        or not all(isinstance(name, str) and name for name in names)
        or not isinstance(arg["annotation"], str)
        or not arg["annotation"]
    ):
        raise CatalogError(
            f"{where}: `annotation_arg.annotation` is one fqn and `name` one attribute or a "
            f"non-empty list of aliases — got {arg!r}"
        )
    return AnnotationArg(
        annotation=_catalog_symbol(arg["annotation"]),
        names=tuple(names),
        equals=None if not has_equals else str(arg["equals"]),
        parses_true=has_parses,
    )


def holds(
    condition: AnnotationArg, owner: str, index: dict[str, list[tuple[str, dict[str, Any]]]]
) -> bool:
    """Whether `condition` holds for `owner` — the owner symbol first and,
    only if the owner carries none of `condition.annotation` at all, its
    enclosing type (D02's precedence: the nearer declaration wins, so once the
    owner is found to carry the annotation the type is never consulted, even
    when the owner's own comparison then fails)."""
    for target in (owner, enclosing_type_of(owner)):
        if target is None:
            continue
        for annotation, args in index.get(target, []):
            if annotation != condition.annotation:
                continue
            value = next((args[name] for name in condition.names if name in args), None)
            return _compare(condition, value)
    return False


def _compare(condition: AnnotationArg, value: object) -> bool:
    """`equals` is an exact string-form comparison, case-sensitive — Micronaut's
    `Qualifiers.byName` is case-sensitive too, which is why `parses_true` is a
    separate word rather than a case-insensitive `equals` (spec §2). `parses_true`
    is exactly Spring's own predicate: `StringUtils.hasText` then
    `Boolean.parseBoolean`, measured on `KafkaListenerAnnotationBeanPostProcessor`
    at two versions (`scripts/probes/cp20_spring_kafka_batch.md` row 2) — no
    placeholder resolution, so `"${listener.batch}"` is `False` like any other
    non-`"true"` text. Either comparator matches an array attribute if any one
    element matches — the attribute's own form, not a container to unwrap first."""
    values = value if isinstance(value, list) else [value]
    if condition.parses_true:
        return any(isinstance(v, str) and v.strip() != "" and v.lower() == "true" for v in values)
    return any(v is not None and str(v) == condition.equals for v in values)
