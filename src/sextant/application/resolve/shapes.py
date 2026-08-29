"""Roots a shape by unwrapping declared envelope wrappers (D02 §2a).

A return or parameter type reference is often not the wire payload itself —
it is an envelope around it. Which types are envelopes, and where the payload
sits inside them, is framework knowledge, so it arrives as catalog data
(`Catalog.wrappers`) rather than being named here. This module is the generic
interpreter: it never names a framework, only follows what the catalog
declares."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RootedType:
    symbol: str
    # `semantics` values, outermost first — e.g. `("async", "http_envelope")`
    # for `Mono<ResponseEntity<T>>`.
    chain: tuple[str, ...]
    # True when unwrapping stopped at a generic type with no matching wrapper
    # rule, rather than at a genuine payload. D02 §2a: an incomplete catalog
    # must degrade visibly, not guess past a wrapper nobody declared.
    unmatched_wrapper: bool


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
            return RootedType(
                symbol=current["symbol"], chain=tuple(chain), unmatched_wrapper=unmatched
            )
        chain.append(wrapper["semantics"])
        current = current["arguments"][wrapper["payload_arg"]]


def _matching_wrapper(symbol: str, wrappers: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (wrapper for wrapper in wrappers if _catalog_symbol(wrapper["type"]) == symbol), None
    )


def _catalog_symbol(dotted_type: str) -> str:
    """Converts a catalog's dotted type name to the SCIP symbol form the facts
    use.

    Two forms exist for the same type on purpose: D02's catalogs write a
    dotted name (`reactor.core.publisher.Mono`) because that is how the spec
    and every catalog author spells a fully qualified type; the scanner emits
    SCIP symbols (`reactor/core/publisher/Mono#`, D00 §5a) because that is the
    grammar the rest of the fact stream is keyed on. Neither side should
    change to suit the other — the catalog stays readable in its source
    notation, the facts stay one grammar — so the conversion happens once,
    here, at the point of comparison.
    """
    return dotted_type.replace(".", "/") + "#"
