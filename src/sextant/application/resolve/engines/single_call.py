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
    supertypes_of,
    url_of,
)
from sextant.application.resolve.shapes.expansion import _enum_symbols, _rules_of
from sextant.application.resolve.shapes.rooting import _catalog_symbol


def run(workspace: Workspace, catalog: Catalog) -> None:
    """Derives one endpoint row per matching call site, via `call_endpoints`
    — a parameterised insert-if-absent on the same wire identity every other
    style uses (D02 §5). `caller` is the calling method symbol; `handler` and
    `peer` are NULL unless the url argument is itself an absolute URL (CP-2);
    `method` is NULL where the verb itself could not be read (I2);
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
    supertypes = supertypes_of(workspace)
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
        # NULL rather than dropped (I2): a call site matching the catalog's
        # own `owner` and `methods` IS an outbound call, and a verb the
        # scanner could not read — an `HttpMethod` arriving as a parameter
        # rather than as an enum constant — is one capture failing, exactly
        # like an unreadable url. Dropping the row would make "this method
        # calls something over HTTP" disappear on the strength of the one
        # column nobody could fill; `method` NULL on an `unresolved` row
        # says it instead (D02 §2's unresolved-is-an-answer).
        verb = _verb_of(method, arguments)
        url_argument = _arg_at(arguments, method["url_arg"])
        peer, path, url_resolution = url_of(url_argument)
        body_argument = _arg_at(arguments, method.get("body_arg"))
        response_argument = _arg_at(arguments, method.get("response_arg"))
        # Checkpoint ruling I1: any DECLARED capture that failed to resolve
        # drops the *row's* resolution, even when the url itself read fine —
        # `path` still carries the known template regardless (it is the
        # url's own answer, untouched by a body/response capture's own
        # failure), but a resolved row promises every declared capture was
        # read, not only the url. `path` stays NULL-safe: this only ever
        # narrows resolution from `resolved` to `unresolved`, never the
        # other way.
        resolution = (
            "resolved"
            if verb is not None
            and url_resolution == "resolved"
            and _capture_resolved(method.get("body_arg"), body_argument)
            and _capture_resolved(method.get("response_arg"), response_argument)
            else "unresolved"
        )
        caller = str(site["caller"])
        # Only a *whole* resolved wire identity dedups, so an unreadable verb
        # keeps each row its own for the same reason an unreadable url does:
        # `NULL = NULL` is unknown in the table this batch is inserted into,
        # and two calls whose verbs nobody could read are not known to be the
        # same call.
        if path is not None and verb is not None:
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
                "request_shape": argument_descriptor(body_argument, facts, carrier_rules),
                "response_shape": argument_descriptor(response_argument, facts, carrier_rules),
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


def _capture_resolved(declared_index: int | None, argument: dict[str, Any] | None) -> bool:
    """Whether a DECLARED capture (checkpoint ruling I1) read something the
    scanner could resolve.

    A capture the `methods` row never declares at all — `put` names no
    `response_arg` — never fails: it never claimed a payload, so its
    absence is a genuine no-body/no-response, not a read failure. A
    declared capture with nothing at that position, or whose own kind is
    the compiler's `unresolved` (D00 §5: "anything else... a first-class
    honest answer, never an omission" — the exact shape a passed-through
    method parameter takes, verified against the real fixture), fails —
    and per I1, that drops the *row's* own `resolution`, even though the
    payload *column* itself stays NULL either way: NULL alone cannot say
    which case it was, so the row is what disambiguates "no payload" from
    "could not read it" (D01 §3, amended)."""
    if declared_index is None:
        return True
    return argument is not None and argument.get("kind") != "unresolved"


def _verb_of(method: dict[str, Any], arguments: list[dict[str, Any]]) -> str | None:
    """D02 §2's two ways a `methods` row states the verb: `http_method` is a
    literal the catalog already knows (`postForObject` is always a POST, so
    the catalog states it once); `method_arg` is a position the call site
    carries instead (`exchange`'s verb is its own `HttpMethod` argument, an
    `enum`-kind entry) — the tail of the constant's symbol, after `#` and its
    trailing `.` (checkpoint-verified against the real emitted grammar:
    `org/springframework/http/HttpMethod#POST.` reads as `POST`).

    None where the declared `method_arg` slot holds anything else — a verb
    passed in as a parameter, the compiler's `unresolved`. The caller keeps
    the row with `method` NULL and `resolution: unresolved` (I2)."""
    literal = method.get("http_method")
    if literal is not None:
        return str(literal)
    arg = _arg_at(arguments, method.get("method_arg"))
    if arg is None or arg.get("kind") != "enum" or not arg.get("symbol"):
        return None
    return str(arg["symbol"]).rpartition("#")[2].removesuffix(".")
