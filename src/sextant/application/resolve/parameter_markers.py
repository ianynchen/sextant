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
  whose body was not read).
- An annotation is `Annotated[T, m1, m2]` where its value is the static call
  `<form>#__class_getitem__` of `typing/Annotated#` or `typing_extensions/Annotated#` (ruling
  R8): the paths to that call, then each metadata argument's producing call, in written order.
  A first argument that is itself an `Annotated` form is flattened into it, as Python does:
  its metadata come first.

A path that ends anywhere else — a literal, a value the walk cannot read, a construction —
gives no marker, and its reason stays the walk's (`values._REASONS`).

**Built once per `ValueIndex` (R14)**, and kept on it, as `suffixes` is: `producer_paths`
reads `call_edges` and `value_edges`, which are derived, so `Workspace.once` cannot hold it,
and the index is the one built with the catalogs' arguments. The signature takes that index,
so nothing can reach this before it exists. The alias walks are shared across parameters
through the index's upward paths (R39), so each alias is read once."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

from sextant.application.resolve.values import (
    EXTERNAL,
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
    for key, values in index.parameter_values.items():
        if values.body is None:
            continue
        markers: list[Marker] = []
        if values.default is not None:
            ends = _ends(index, values.body, values.default, frozenset(), _DEFAULT_READER)
            for path, producer in enumerate(ends):
                site = _site(index, producer)
                if site is not None:
                    markers.append(Marker(site=site, where="default", order=0, path=path))
        if values.annotation is not None:
            forms = _ends(index, values.body, values.annotation, _ANNOTATED, _FORM_READER)
            for path, elements in enumerate(
                one for form in forms for one in _metadata(index, form)
            ):
                markers.extend(
                    Marker(site=site, where="annotation", order=order, path=path)
                    for order, site in enumerate(elements)
                    if site is not None
                )
        if markers:
            found[key] = tuple(markers)
    index.markers.append(found)
    return found


def _ends(
    index: ValueIndex,
    body: str,
    entry: Mapping[str, Any],
    declared: frozenset[tuple[str, str]],
    reader: str,
) -> list[Producer]:
    """Where each path of `entry`, a value of `body`'s frame, ends: `producer_paths` over the
    one-argument row that holds it (`held_at_end`)."""
    holder = held_at_end(body, entry)
    return [producer for producer, _ in producer_paths(index, holder, 0, declared, shared=reader)]


def _metadata(index: ValueIndex, form: Producer) -> list[list[Mapping[str, Any] | None]]:
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
        for producer, _ in producer_paths(index, site, 0, _ANNOTATED, shared=_FORM_READER)
        for nested in (_metadata(index, producer) or [[]])
    ]
    for slot in range(1, len(arguments)):
        made = [
            _site(index, producer)
            for producer, _ in producer_paths(
                index, site, slot, frozenset(), shared=_DEFAULT_READER
            )
        ]
        combined = [chosen + [one] for chosen in combined for one in made]
    return combined


def _site(index: ValueIndex, producer: Producer) -> Mapping[str, Any] | None:
    """The call a path ended at: a declared stop, or a library call whose body was not read
    (`Producer.made_by`). None for every other end."""
    if producer.caller is not None and producer.ordinal is not None:
        return index.sites.get((producer.caller, producer.ordinal))
    if producer.reason == EXTERNAL and producer.made_by is not None:
        return index.sites.get(producer.made_by)
    return None
