"""The calls that mark each parameter (plan 2026-11-08-python-fastapi-inbound Task 4, N1, N2;
ruling R14).

A `def` evaluates a parameter's default and its annotation in the body that runs it (D00 §5a).
A framework that reads a parameter's meaning off those values reads the CALL that made each:
the call that produced the default, and the call that produced each `Annotated` metadata
element. This pass names those calls, one `Marker` per path, and nothing about what they
mean: which calls a framework reads is catalog data (Tasks 7 and 8).

**Every value is read through `values.producer_paths`**, the walk every reader takes, so an
alias is followed wherever it is (a module field, another file's field, an alias of an alias),
as is a helper that returns the call and each branch of a conditional. No other walk exists.

- The default's producing call: the path's end, where the walk ends at a call (a library call
  whose body was not read, or a construction: `fastapi.params.Depends(f)` makes its value as
  `fastapi.param_functions.Depends(f)` does, and the walk stops at every construction a site
  makes, `_constructions`).
- An annotation is `Annotated[T, m1, m2]` where its value is the static call
  `<form>#__class_getitem__` of `typing/Annotated#` or `typing_extensions/Annotated#` (ruling
  R8): the paths to that call, then each metadata argument's producing call, in written order.
  A first argument that is itself an `Annotated` form is flattened into it, as Python does:
  its metadata come first.

A path that ends anywhere else — a literal, a value the walk cannot read — gives no marker, and
its reason stays the walk's (`values._REASONS`).

**Built once per `ValueIndex` (R14)**, and kept on it, as `suffixes` is: `producer_paths`
reads `call_edges` and `value_edges`, which are derived, so `Workspace.once` cannot hold it,
and the index is the one built with the catalogs' arguments. The signature takes that index,
so nothing can reach this before it exists. The alias walks are shared across parameters
through the index's upward paths (R39), so each alias is read once."""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from sextant.application.resolve.values import (
    EXTERNAL,
    Path,
    Producer,
    ValueIndex,
    held_at_end,
    producer_paths,
)

# The type form whose subscript carries metadata (D00 §5a, ruling R8: both spellings).
_ANNOTATED = frozenset(
    {
        ("typing/Annotated#", "__class_getitem__"),
        ("typing_extensions/Annotated#", "__class_getitem__"),
    }
)
# The readers' keys in the index's shared upward paths (`producer_paths(..., shared=)`): one per
# stop set, since a path's end depends on it.
_DEFAULT_READER = "parameter_markers:default"
_FORM_READER = "parameter_markers:form"
_LIST_READER = "parameter_markers:list"


@dataclass(frozen=True)
class Marker:
    """One call that marks a parameter, on one path: `site` the producing call's row, `where`
    whether it made the `default` or an `Annotated` metadata element, `order` the element's
    written position among the metadata (its index after the type, the first argument; 0 for
    a default), and `path` the index of the path it was read on among that `where`'s paths.
    Markers sharing a `path` hold together; two paths are alternatives, never one list."""

    site: Mapping[str, Any]
    where: Literal["default", "annotation"]
    order: int
    path: int


def parameter_markers(index: ValueIndex) -> Mapping[tuple[str, int], tuple[Marker, ...]]:
    """Each parameter's markers, `(method, index)` -> defaults' then annotations', each by
    path and in written order, for every parameter that has one. Built once per `index`
    (module docstring)."""
    if index.markers:
        return cast(Mapping[tuple[str, int], tuple[Marker, ...]], index.markers[0])
    found: dict[tuple[str, int], tuple[Marker, ...]] = {}
    # Held while the pass runs: its own walks reach parameters, and a parameter reads its
    # recipe from here (`values._Walk._recipe_paths`). Those walks stop at a call, so what a
    # recipe hands a parameter is no part of where they end; they read none.
    index.markers.append({})
    stops = _constructions(index)
    for key, values in index.parameter_values.items():
        if values.body is None:
            continue
        markers: list[Marker] = []
        # What this parameter's markers are read through that a binding round can change
        # (`ValueIndex.marker_reads`): a walk that names its recipe depends on them too.
        reads: set[Any] = set()
        if values.default is not None:
            ends = _ends(index, values.body, values.default, stops, _DEFAULT_READER, reads)
            for path, producer in enumerate(ends):
                site = _site(index, producer)
                if site is not None:
                    markers.append(Marker(site=site, where="default", order=0, path=path))
        if values.annotation is not None:
            forms = _ends(index, values.body, values.annotation, _ANNOTATED, _FORM_READER, reads)
            for path, elements in enumerate(
                one for form in forms for one in _metadata(index, form, stops, reads)
            ):
                markers.extend(
                    Marker(site=site, where="annotation", order=order, path=path)
                    for order, site in enumerate(elements)
                    if site is not None
                )
        if markers:
            found[key] = tuple(markers)
        if reads:
            index.marker_reads[key] = frozenset(reads)
    index.markers[0] = found
    return found


def recipe_sites(
    markers: Sequence[Marker], calls: Collection[tuple[str, str]]
) -> tuple[Mapping[str, Any], ...]:
    """The recipe calls (`calls`, `beans.RecipeCalls`, N5) a parameter's `markers` name, as
    FastAPI reads a parameter (`analyze_param`): the last one in its `Annotated` metadata on
    each path, else its default's on each path. Each call once."""
    annotated: dict[int, Marker] = {}
    for marker in markers:
        if marker.where == "annotation" and _call_of(marker) in calls:
            held = annotated.get(marker.path)
            if held is None or marker.order > held.order:
                annotated[marker.path] = marker
    chosen = list(annotated.values()) or [
        marker for marker in markers if marker.where == "default" and _call_of(marker) in calls
    ]
    return tuple(
        {
            (str(one.site["caller"]), int(str(one.site["ordinal"]))): one.site for one in chosen
        }.values()
    )


def producing_calls(
    index: ValueIndex, site: Mapping[str, Any], slot: int, within: Path | None = None
) -> tuple[Mapping[str, Any], ...]:
    """The call each path of `site`'s argument at `slot` ends at (`_site`), the walk stopping
    at every construction and every recipe call (`ValueIndex.recipes`): each element of a list
    written there is a path of its own, so `dependencies=[Depends(a), Depends(b)]` gives both
    calls. `within`, a path the reader already took, keeps only the paths agreeing with it.
    Each call once."""
    found: dict[tuple[str, int], Mapping[str, Any]] = {}
    stops = _constructions(index) | frozenset(index.recipes.calls)
    for producer, path in producer_paths(index, site, slot, stops, shared=_LIST_READER):
        if within is not None and path.joined(within) is None:
            continue
        made = _site(index, producer)
        if made is not None:
            found[(str(made["caller"]), int(str(made["ordinal"])))] = made
    return tuple(found.values())


def _call_of(marker: Marker) -> tuple[str, str]:
    """A marker's call, as `(owner, method)`."""
    return (str(marker.site.get("owner")), str(marker.site["name"]))


def _ends(
    index: ValueIndex,
    body: str,
    entry: Mapping[str, Any],
    declared: frozenset[tuple[str, str]],
    reader: str,
    reads: set[Any] | None = None,
) -> list[Producer]:
    """Where each path of `entry`, a value of `body`'s frame, ends: `producer_paths` over the
    one-argument row that holds it (`held_at_end`)."""
    holder = held_at_end(body, entry)
    return [
        producer
        for producer, _ in producer_paths(index, holder, 0, declared, shared=reader, reads=reads)
    ]


def _metadata(
    index: ValueIndex,
    form: Producer,
    stops: frozenset[tuple[str, str]],
    reads: set[Any] | None = None,
) -> list[list[Mapping[str, Any] | None]]:
    """For one path to an `Annotated` form, each path through its metadata: one entry per
    written element, in written order, the element's producing call or None where that path
    ends at no call. One list per combination of the elements' paths, so two paths are two
    lists, never one merged list. A path that ends at no form gives none."""
    if form.caller is None or form.ordinal is None or form.identity not in _ANNOTATED:
        return []
    site = index.sites.get((form.caller, form.ordinal))
    if site is None:
        return []
    arguments = site.get("arguments") or []
    # The first argument is the type; where it is an `Annotated` form itself, Python flattens
    # it, and its metadata come first. A path to anything else adds no element.
    combined: list[list[Mapping[str, Any] | None]] = [
        nested
        for producer, _ in producer_paths(
            index, site, 0, _ANNOTATED, shared=_FORM_READER, reads=reads
        )
        for nested in (_metadata(index, producer, stops, reads) or [[]])
    ]
    for slot in range(1, len(arguments)):
        made = [
            _site(index, producer)
            for producer, _ in producer_paths(
                index, site, slot, stops, shared=_DEFAULT_READER, reads=reads
            )
        ]
        combined = [chosen + [one] for chosen in combined for one in made]
    return combined


def _constructions(index: ValueIndex) -> frozenset[tuple[str, str]]:
    """Every construction a site makes, as the walk's stops: a value an object's construction
    made ends its path at that call, which is the marker, as a call of a function is. The same
    set on every walk, so the readers' shared upward paths hold one answer."""
    return frozenset((owner, _INIT) for owner in index.constructed)


# A construction's name at a call site (D00 §5).
_INIT = "<init>"


def _site(index: ValueIndex, producer: Producer) -> Mapping[str, Any] | None:
    """The call a path ended at: a declared stop, or a library call whose body was not read
    (`Producer.made_by`). None for every other end."""
    if producer.caller is not None and producer.ordinal is not None:
        return index.sites.get((producer.caller, producer.ordinal))
    if producer.reason == EXTERNAL and producer.made_by is not None:
        return index.sites.get(producer.made_by)
    return None
