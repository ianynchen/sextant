"""A return or parameter type reference is often not the wire payload itself —
it is an envelope around it. Which types are envelopes, and where the payload
sits inside them, is framework knowledge, so it arrives as catalog data
(`Catalog.wrappers`) rather than being named here. This module is the generic
interpreter: it never names a framework, only follows what the catalog
declares."""

from dataclasses import dataclass
from typing import Any

# Two forms exist for the same type on purpose: D02's catalogs write a dotted
# name (`reactor.core.publisher.Mono`) because that is how the spec and every
# catalog author spells a fully qualified type; the scanner emits SCIP symbols
# (`reactor/core/publisher/Mono#`, D00 §5a) because that is the grammar the
# rest of the fact stream is keyed on. Neither side should change to suit the
# other — the catalog stays readable in its source notation, the facts stay
# one grammar — so the conversion happens once, at the point of comparison.
# A plain assignment, not `import ... as _catalog_symbol`: mypy's strict
# implicit-reexport rule only recognises the same-name `import X as X` form,
# and this module's own importers (unchanged by this task) reach the name
# through `rooting`, not through `domain.symbols`.
from sextant.application.ports.catalogs import CatalogError
from sextant.domain.symbols import type_descriptor

_catalog_symbol = type_descriptor


def catalog_symbols(declared: object, where: str = "a catalog site") -> tuple[str, ...]:
    """Every symbol one catalog site names, whether it names one or several (§3.1).

    A site may hold a scalar or a list, and a scalar stays valid — this is not a
    migration, and 42 shipped catalogs spell these as scalars today. The list form
    means ONE library reachable under more than one name: held by its interface
    (`JmsOperations` beside `JmsTemplate`), or under its old package. It does not
    mean two libraries — a javax/jakarta pair is two jars at two versions needing
    two measurements, and stays two catalogs (§3.3).

    The asymmetry that shows the scalar was accident rather than design:
    `error_advice` already takes PLURAL lists for its advice and controller types
    while its two annotation keys are scalar, in one file, for no stated reason.

    Returns a tuple so a caller can iterate without caring which form was written,
    and so the singular case costs one element rather than a branch at every site.

    `where` is what the caller can say about the site — the catalog file and the
    key, ideally. The refusal used to read "a catalog site must name a type…",
    which told a reader holding 42 catalogs neither which file to open nor which
    key to look at (§13.6: a loud failure that does not say WHERE is half of one).

    A list is accepted and a tuple is not: YAML produces lists, and the two shapes
    reaching here would mean two ways to spell one catalog. Callers converting
    their own already-built tuples would be the second way in.
    """
    if isinstance(declared, str):
        return (_catalog_symbol(declared),)
    if isinstance(declared, list):
        if not declared:
            raise CatalogError(f"{where} names an EMPTY list; name at least one type")
        return tuple(_catalog_symbol(name) for name in declared)
    raise CatalogError(
        f"{where} must name a type or a list of them, not {type(declared).__name__} ({declared!r})"
    )


@dataclass(frozen=True)
class RootedType:
    # The whole reference unwrapping stopped at, not only its symbol: what the
    # payload is on the wire — its `wire_type`, its own type arguments — lives
    # on that node, and re-finding it would mean walking the wrappers twice.
    reference: dict[str, Any]
    # `semantics` values, outermost first — e.g. `("async", "http_envelope")`
    # for `Mono<ResponseEntity<T>>`.
    chain: tuple[str, ...]
    # True when unwrapping stopped at a generic type with no matching wrapper
    # rule, rather than at a genuine payload. D02 §2a: an incomplete catalog
    # must degrade visibly, not guess past a wrapper nobody declared.
    unmatched_wrapper: bool

    @property
    def symbol(self) -> str:
        return str(self.reference["symbol"])


def root_type(type_ref: dict[str, Any], wrappers: list[dict[str, Any]]) -> RootedType:
    """Unwraps `type_ref` through `wrappers` recursively until it reaches a
    type no wrapper rule claims, or one with no type arguments to unwrap."""
    chain: list[str] = []
    current = type_ref
    while True:
        wrapper = _matching_wrapper(current["symbol"], wrappers)
        if wrapper is None:
            # A leaf with no type arguments (e.g. `OrderView`) is a payload,
            # not an unmatched wrapper — nothing about it looked like an
            # envelope. Only a still-generic type that no rule claims is the
            # "unfamiliar wrapper" D02 §2a means: it could be an envelope,
            # and unwrapping it anyway would be a guess presented as fact.
            unmatched = bool(current["arguments"])
            return RootedType(reference=current, chain=tuple(chain), unmatched_wrapper=unmatched)
        arguments = current["arguments"]
        if wrapper["payload_arg"] >= len(arguments):
            # A declared envelope holding nothing at the payload position:
            # ordinary code, not a broken catalog. A raw `ResponseEntity`, and
            # every envelope reached through an erased method descriptor,
            # arrives with its argument already gone. It is the same answer as
            # an envelope nobody declared — something that could be holding a
            # payload, left unopened and said so — because the two are the same
            # situation: the catalog claims an envelope and no payload is
            # visible inside it. The chain records envelopes actually peeled,
            # so this one is not added: a `semantics` recorded here would let
            # `required` be derived from an unwrapping that never happened.
            return RootedType(reference=current, chain=tuple(chain), unmatched_wrapper=True)
        chain.append(wrapper["semantics"])
        current = arguments[wrapper["payload_arg"]]


def _matching_wrapper(symbol: str, wrappers: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (wrapper for wrapper in wrappers if _catalog_symbol(wrapper["type"]) == symbol), None
    )
