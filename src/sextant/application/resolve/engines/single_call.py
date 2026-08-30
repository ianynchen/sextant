"""single_call engine for endpoint derivation (D02 §2's `single_call` style).

One call carries the whole outbound declaration — a `RestTemplate.postForObject`,
a `.exchange` — so this pass reads `call_sites` directly rather than joining
annotation facts: it matches each site against the catalog's declared
`methods` by name, resolves the verb (a literal or an `enum` argument's own
symbol), splits the url argument into peer and path (CP-2), and resolves the
request/response descriptors from the call's own arguments through
`shapes.contracts.argument_descriptor` (D02 §2h). Framework knowledge — the
owner type, which argument is which, the PTR/call-wrapper rules — arrives as
catalog data; this module never names a framework.
"""

import json
from typing import Any

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.shapes.contracts import (
    CallFacts,
    CarrierRules,
    argument_descriptor,
    split_url,
)
from sextant.application.resolve.shapes.expansion import _enum_symbols, _rules_of
from sextant.application.resolve.shapes.rooting import _catalog_symbol


def run(workspace: Workspace, catalog: Catalog) -> None:
    """Derives one endpoint row per matching call site, via `call_endpoints`
    — a parameterised insert-if-absent on the same wire identity every other
    style uses (D02 §5). `caller` is the calling method symbol; `handler` and
    `peer` are NULL unless the url argument is itself an absolute URL (CP-2);
    `direction` and `protocol` are the catalog's own declared fields, exactly
    as `annotation_driven` forwards them."""
    matches = catalog.matches
    owner = _catalog_symbol(matches["owner"])
    methods = {method["name"]: method for method in matches["methods"]}
    carrier_rules = CarrierRules(
        rules=_rules_of(catalog),
        enums=_enum_symbols(workspace),
        type_carriers=tuple(_catalog_symbol(t) for t in matches.get("type_carriers", [])),
        call_wrappers={
            _catalog_symbol(wrapper["type"]): wrapper["payload_ctor_arg"]
            for wrapper in matches.get("call_wrappers", [])
        },
    )
    supertypes = _supertypes_of(workspace)
    # `arguments` is parsed once, here, rather than once per reader: the
    # `call_sites` query returns it as raw JSON text, and both the matching
    # loop below and the `call_wrappers` one-hop (over a *different* call
    # site's own arguments, `contracts._linked_constructor`) need the parsed
    # list, never the text.
    call_sites = [
        {**site, "arguments": json.loads(str(site["arguments"]))}
        for site in workspace.query("call_sites")
    ]
    by_caller: dict[str, list[dict[str, Any]]] = {}
    for site in call_sites:
        by_caller.setdefault(str(site["caller"]), []).append(site)

    # A list, not a set: the order call sites reach a shape decides the
    # order shape rows are written (NFR-1) — the same discipline
    # derive_endpoint_shapes keeps for its own `referenced` accumulator.
    referenced: list[str] = []
    rows: list[dict[str, Any]] = []
    # Only a *resolved* wire identity dedups here: two unresolved calls carry
    # no path to compare, and SQL's `NULL = NULL` is unknown rather than
    # true, so each stays its own row (D02 §2's unresolved-is-an-answer).
    seen: set[tuple[str, str, str, str]] = set()
    for site in call_sites:
        if site["owner"] != owner:
            continue
        method = methods.get(site["name"])
        if method is None:
            continue
        arguments = site["arguments"]
        verb = _verb_of(method, arguments)
        if verb is None:
            continue
        peer, path, resolution = _url_of(_arg_at(arguments, method["url_arg"]))
        caller = str(site["caller"])
        if path is not None:
            key = (catalog.protocol, catalog.direction, verb, path)
            if key in seen:
                continue
            seen.add(key)
        facts = CallFacts(
            supertypes=supertypes,
            caller_call_sites=by_caller.get(caller, []),
            referenced=referenced,
        )
        rows.append(
            {
                "protocol": catalog.protocol,
                "direction": catalog.direction,
                "method": verb,
                "path": path,
                "handler": None,
                "caller": caller,
                "peer": peer,
                "handler_signature": None,
                "resolution": resolution,
                "evidence": "compiler",
                "request_shape": argument_descriptor(
                    _arg_at(arguments, method.get("body_arg")), facts, carrier_rules
                ),
                "response_shape": argument_descriptor(
                    _arg_at(arguments, method.get("response_arg")), facts, carrier_rules
                ),
            }
        )

    workspace.derive("call_endpoints", rows=rows)


def _arg_at(arguments: list[dict[str, Any]], index: int | None) -> dict[str, Any] | None:
    """The argument at a `methods` row's declared position, or None where the
    row names no position at all (`body_arg`/`response_arg` are optional) or
    the real call site carries fewer arguments than the catalog expects — the
    varargs slot on `getForObject`/`exchange` is exactly this case (Task 7
    checkpoint): declared positions still read correctly, and the excess
    trailing argument is simply never addressed."""
    if index is None or index >= len(arguments):
        return None
    return arguments[index]


def _verb_of(method: dict[str, Any], arguments: list[dict[str, Any]]) -> str | None:
    """D02 §2's two ways a `methods` row states the verb: `http_method` is a
    literal the catalog already knows (`postForObject` is always a POST, so
    the catalog states it once); `method_arg` is a position the call site
    carries instead (`exchange`'s verb is its own `HttpMethod` argument, an
    `enum`-kind entry) — the tail of the constant's symbol, after `#` and its
    trailing `.` (checkpoint-verified against the real emitted grammar:
    `org/springframework/http/HttpMethod#POST.` reads as `POST`)."""
    literal = method.get("http_method")
    if literal is not None:
        return str(literal)
    arg = _arg_at(arguments, method.get("method_arg"))
    if arg is None or arg.get("kind") != "enum" or not arg.get("symbol"):
        return None
    return str(arg["symbol"]).rpartition("#")[2].removesuffix(".")


def _url_of(arg: dict[str, Any] | None) -> tuple[str | None, str | None, str]:
    """The row's `peer`, `path` and `resolution` from the url argument: a
    `string` argument's value is the template verbatim — placeholders and
    all, because the template is the wire identity — split into peer/path by
    CP-2's rule; anything else still derives the row, path NULL, resolution
    `unresolved` (D02 §2: "this method calls something over HTTP" is true
    and useful on its own)."""
    if arg is not None and arg.get("kind") == "string" and isinstance(arg.get("value"), str):
        peer, path = split_url(str(arg["value"]))
        return peer, path, "resolved"
    return None, None, "unresolved"


def _supertypes_of(workspace: Workspace) -> dict[str, dict[str, Any]]:
    """Every declared type's own generic supertype reference (D00 §5a's PTR
    carrier), keyed by the type's bare descriptor — the form an `instance`
    argument's own `symbol` carries, never the module-prefixed identity a
    symbol fact's own `symbol` column holds (the same stripping
    `_enum_symbols` applies to its own rows, for the same reason: a symbol is
    module coordinates then a descriptor, D00 §5a, and only the descriptor is
    ever compared)."""
    return {
        str(row["symbol"]).rpartition(" ")[2]: json.loads(str(row["supertype"]))
        for row in workspace.query("supertypes")
    }
