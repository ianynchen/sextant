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

from sextant.application.ports.catalogs import Catalog, CatalogError
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
from sextant.domain.closed_sets import Direction

_DIRECTIONS = sorted(member.value for member in Direction)


def run(workspace: Workspace, catalog: Catalog) -> None:
    """Derives one endpoint row per matching call site, via `call_endpoints`
    — a parameterised insert-if-absent on the same wire identity every other
    style uses (D02 §5). `caller` is the calling method symbol, unless the
    matched row's own `direction` is `inbound`, in which case it lands in
    `handler` instead (D02 §2); `peer` is NULL unless the url argument is
    itself an absolute URL (CP-2); `method` is NULL where the verb itself
    could not be read (I2) or the row is verbless by declaration; `protocol`
    is the catalog's own declared field, exactly as `annotation_driven`
    forwards it, and `direction` is the catalog's own declared field unless
    the matched row overrides it."""
    matches = catalog.matches
    owner = _catalog_symbol(matches["owner"])
    # A list, not a dict-by-name (Task 6): `arity` lets two rows share a
    # `name` — `send(topic, payload)` and `send(topic, key, payload)` — and a
    # dict keyed by name would let the second overwrite the first.
    # `_matching_method` scans it per call site instead.
    methods = list(matches["methods"])
    _validate_methods(methods, catalog)
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
        arguments = site["arguments"]
        method = _matching_method(methods, site["name"], arguments)
        if method is None:
            continue
        # A row declaring neither `http_method` nor `method_arg` is verbless
        # by declaration (D02 §2) — a topic has no verb. Its `verb` reads
        # None too (`_verb_of` finds neither key), but that must not read as
        # I2's "the verb could not be captured": `verbless` tells the two
        # apart wherever `verb is not None` alone would otherwise stand in
        # for "a verb was declared and read".
        verbless = "http_method" not in method and "method_arg" not in method
        # NULL rather than dropped (I2): a call site matching the catalog's
        # own `owner` and `methods` IS an outbound call, and a verb the
        # scanner could not read — an `HttpMethod` arriving as a parameter
        # rather than as an enum constant — is one capture failing, exactly
        # like an unreadable url. Dropping the row would make "this method
        # calls something over HTTP" disappear on the strength of the one
        # column nobody could fill; `method` NULL on an `unresolved` row
        # says it instead (D02 §2's unresolved-is-an-answer).
        verb = _verb_of(method, arguments)
        # `channel_arg` is `url_arg`'s alias for a destination-shaped
        # identity (D02 §2) — `_validate_methods` already refused a row
        # declaring both, so at most one of the two is ever present here.
        url_argument = _arg_at(arguments, method.get("url_arg", method.get("channel_arg")))
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
            if (verb is not None or verbless)
            and url_resolution == "resolved"
            and _capture_resolved(method.get("body_arg"), body_argument)
            and _capture_resolved(method.get("response_arg"), response_argument)
            else "unresolved"
        )
        caller = str(site["caller"])
        # `direction` on a row overrides the catalog's own declared
        # direction (D02 §2) — Pub/Sub's `subscribe` is inbound even inside
        # an otherwise outbound file.
        row_direction = method.get("direction", catalog.direction)
        # Only a *whole* resolved wire identity dedups, so an unreadable verb
        # keeps each row its own for the same reason an unreadable url does:
        # `NULL = NULL` is unknown in the table this batch is inserted into,
        # and two calls whose verbs nobody could read are not known to be the
        # same call. A verbless row dedups on `(protocol, row_direction,
        # path)` alone — there is no method to distinguish them by — hence
        # `verb or ""` rather than `verb`: every shipped HTTP row declares
        # `http_method` or `method_arg`, so `verbless` is always False and
        # `verb` is never None wherever this key is built for them, making
        # `verb or ""` equal to `verb` and this change a no-op for those
        # catalogs; likewise no shipped row declares its own `direction`, so
        # `row_direction` is always `catalog.direction` there too.
        if path is not None and (verb is not None or verbless):
            key = (catalog.protocol, row_direction, verb or "", path)
            if key in seen:
                continue
            seen.add(key)
        facts = CallFacts(
            supertypes=supertypes,
            caller_call_sites=by_caller.get(caller, []),
            referenced=referenced,
        )
        # An inbound row's deriving method is the consumer, not the caller
        # (D02 §2): it lands in `handler`, and `caller` stays NULL — the
        # same handler/caller split `derive_endpoints.sql` keeps for the
        # annotation-driven styles, applied here per row rather than per
        # catalog.
        inbound = row_direction == "inbound"
        rows.append(
            {
                "protocol": catalog.protocol,
                "direction": row_direction,
                "method": verb,
                "path": path,
                "handler": caller if inbound else None,
                "caller": None if inbound else caller,
                "peer": peer,
                "handler_signature": None,
                "resolution": resolution,
                "evidence": "compiler",
                "request_shape": argument_descriptor(body_argument, facts, carrier_rules),
                "response_shape": argument_descriptor(response_argument, facts, carrier_rules),
            }
        )

    workspace.derive("call_endpoints", rows=rows)


def _matching_method(
    rows: list[dict[str, Any]], name: str, arguments: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """The one `methods` row matching a call site's own name and argument
    count (D02 §2's `arity`) — first match wins. A row without `arity`
    matches every overload, so the shipped 2C catalogs (none of which
    declare it) parse unchanged; a catalog that needs to tell
    `send(topic, payload)` from `send(topic, key, payload)` apart writes one
    row per arity instead, and this is the scan that replaces the old
    dict-by-name (`:40` before Task 6), which could only ever keep one row
    per name."""
    for row in rows:
        if row["name"] != name:
            continue
        arity = row.get("arity")
        if arity is not None and arity != len(arguments):
            continue
        return row
    return None


def _validate_methods(rows: list[dict[str, Any]], catalog: Catalog) -> None:
    """Refuses a broken `methods` row before any call site is matched — the
    `fluent._validate_steps` precedent: an unchecked value does not stay in
    the file (`ports/catalogs.py`'s own discipline), so this runs once, at
    `run` start, over every declared row, rather than lazily on whichever
    row a call site happens to reach first.

    `url_arg` and `channel_arg` name the same capture (D02 §2); a row
    declaring both is a broken catalog, not two pieces of evidence. A row's
    own `direction`, where declared, still has to be one of D00's closed
    Direction values — the catalog-level `direction` is checked at load time
    (`yaml_source.py`'s `_closed`), but a row's override lives inside
    `matches`, opaque to that loader-level check, so it is checked here
    instead."""
    for row in rows:
        if "url_arg" in row and "channel_arg" in row:
            raise CatalogError(
                f"loading catalog {catalog.source}: `{row['name']}` declares both "
                f"`url_arg` and `channel_arg` — they name the same capture (D02 §2's "
                f"single_call style)"
            )
        direction = row.get("direction")
        if direction is not None and direction not in _DIRECTIONS:
            raise CatalogError(
                f"loading catalog {catalog.source}: `{row['name']}` declares "
                f"`direction: {direction}`, which is not one of {', '.join(_DIRECTIONS)} "
                f"— D00's closed sets are closed (NFR-5)"
            )


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
