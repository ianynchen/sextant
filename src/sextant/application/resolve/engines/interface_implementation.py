"""`interface_implementation` engine for endpoint derivation (D02 §2's
`interface_implementation` style).

Unlike `single_call`/`fluent`, the boundary here is not one call's own
declaration but two facts joined together: a *registration* call site — the
framework binding a receiver to a channel, `Subscriber.newBuilder(name,
receiver)` — and, where the receiver is a named instance rather than a
lambda, that instance's own declared `interfaces` (D00 §5a's
`implemented_interfaces` capability). **The registration is the evidence**:
a class that implements the declared interface but is never handed to a
matching registration call derives nothing, exactly as D02 states — this
style needs no execute-terminal (fluent's `terminal`/`terminal_via_argument`)
because binding a receiver to a subscription already IS the intent a built,
unlogged HTTP request is not.

Framework knowledge — the interface, the registration owner+method, which
argument is the channel and which is the receiver — arrives as catalog data;
this module never names a framework."""

import json
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.shapes.arguments import (
    CallFacts,
    _arg_at,
    channel_of,
    linked_channels,
)
from sextant.application.resolve.shapes.rooting import _catalog_symbol

_REQUIRED_MATCHES = ("interface", "handler_method", "registration")
_REQUIRED_REGISTRATION = ("owner", "method", "channel_arg", "receiver_arg")


def run(workspace: Workspace, catalog: Catalog) -> None:
    """Derives one row per resolved channel tuple, per registration call
    site — the same `call_endpoints` insert-if-absent every style uses
    (D02 §5). Rows are verbless (`method` always NULL) and carry no shape
    (`request_shape`/`response_shape` always NULL — `PubsubMessage` is a
    declared no-shape envelope, the `jakarta.jms.Message` precedent): the
    registration names an identity and, where readable, a handler, nothing
    more. `caller`/`peer` are always NULL — the row's own method is a
    `handler` (inbound only, D02 §2's `interface_implementation` example) and a destination is never
    split into a peer (§2d)."""
    _validate_matches(catalog)
    matches = catalog.matches
    interface_symbol = _catalog_symbol(matches["interface"])
    handler_method = matches["handler_method"]
    registration = matches["registration"]
    owner = _catalog_symbol(registration["owner"])
    method_name = registration["method"]
    channel_arg = registration["channel_arg"]
    receiver_arg = registration["receiver_arg"]
    forms = _channel_via_forms(registration)
    implemented = _implemented_interfaces(workspace)

    # Parsed once, as every other engine does: `call_sites` returns
    # `arguments` as raw JSON text.
    call_sites = [
        {**site, "arguments": json.loads(str(site["arguments"]))}
        for site in workspace.query("call_sites")
    ]
    by_caller: dict[str, list[dict[str, Any]]] = {}
    for site in call_sites:
        by_caller.setdefault(str(site["caller"]), []).append(site)

    rows: list[dict[str, Any]] = []
    # Only a resolved wire identity dedups (D02 §2's unresolved-is-an-answer):
    # two unresolved registrations carry no path to compare, so each stays
    # its own row. `handler` is PART of that identity, not decoration: two
    # registrations of the SAME channel by two DIFFERENT receivers — two
    # `@KafkaHandler`-shaped methods sharing one subscription is the real
    # precedent (`test_pipeline.py`) — are two distinct facts, and a key that
    # dropped `handler` would silently discard the second one. Duplicate
    # registrations of the SAME handler on the SAME channel still collapse,
    # exactly as every other style's own wire-identity dedup does.
    seen: set[tuple[str, str, str, str]] = set()
    # `call_sites` is already ordered `caller, ordinal` (NFR-1); filtering it
    # in place, rather than grouping by owner first, keeps that order.
    for site in call_sites:
        if site["owner"] != owner or site["name"] != method_name:
            continue
        arguments = site["arguments"]
        caller = str(site["caller"])
        # `channel_via`'s linked-call join (`_linked_constructor`) searches
        # only this caller's own call sites (D00 §5's ids are meaningless
        # across methods) — `supertypes` and `referenced` are unused here
        # (this style roots no payload at all) but `CallFacts` still needs
        # them filled.
        facts = CallFacts(supertypes={}, caller_call_sites=by_caller.get(caller, []), referenced=[])
        channel_argument = _arg_at(arguments, channel_arg)
        # The capture ladder is a LADDER, not an either/or (D02 §2's
        # `channel_via` precedent, `single_call`'s own non-exclusive reading
        # of the two): a `channel_via`-declared row still tries the literal
        # read FIRST — `Subscriber.newBuilder(String, MessageReceiver)`
        # really exists alongside the `ProjectSubscriptionName` overload — and
        # only falls back to the linked call when the argument itself is not
        # a resolved string literal.
        literal = channel_of(channel_argument)
        if literal[2] != "resolved" and "channel_via" in registration:
            destinations = linked_channels(channel_argument, facts, forms)
        else:
            destinations = [literal]
        receiver_argument = _arg_at(arguments, receiver_arg)
        handler = _handler_of(receiver_argument, handler_method, interface_symbol, implemented)
        for peer, path, resolution in destinations:
            if path is not None:
                key = (catalog.protocol, catalog.direction, path, handler or "")
                if key in seen:
                    continue
                seen.add(key)
            rows.append(
                {
                    "protocol": catalog.protocol,
                    "direction": catalog.direction,
                    "method": None,
                    "path": path,
                    "handler": handler,
                    "caller": None,
                    "peer": peer,
                    "handler_signature": None,
                    "resolution": resolution,
                    "evidence": "compiler",
                    "catalog_id": catalog.id,
                    "request_shape": None,
                    "response_shape": None,
                }
            )

    workspace.derive("call_endpoints", rows=rows)


def _handler_of(
    argument: dict[str, Any] | None,
    handler_method: str,
    interface_symbol: str,
    implemented: dict[str, list[str]],
) -> str | None:
    """D02 §2's `interface_implementation` handler rule: a `lambda`-kind receiver resolves to its own
    synthetic body method symbol (D00 §5a), verbatim — the lambda IS the
    handler, whatever the declared interface's own method is named. An
    `instance`-kind receiver (a `NEW`-produced named class) resolves to
    `<type>#<handler_method>` only when that type's own declared
    `interfaces` include the declared interface — **direct implementers
    only**: the fact carries a class's own interface table, never a
    superclass's, so this is a one-hop check by construction, not an
    explicit walk this function has to refuse. Anything else — no receiver
    captured, an `unresolved` kind, a registered instance whose type does
    not implement the interface — resolves to None: the subscription still
    derives (the row above), only its handler is unread, never fabricated.
    """
    if argument is None:
        return None
    kind = argument.get("kind")
    if kind == "lambda":
        symbol = argument.get("symbol")
        return str(symbol) if symbol is not None else None
    if kind == "instance":
        symbol = argument.get("symbol")
        if symbol is None:
            return None
        symbol = str(symbol)
        if interface_symbol in implemented.get(symbol, []):
            # `symbol` already carries its own trailing `#` (D00 §5a's bare
            # descriptor form), so this is `<type>#<handler_method>` without
            # a second separator.
            return f"{symbol}{handler_method}"
    return None


def _implemented_interfaces(workspace: Workspace) -> dict[str, list[str]]:
    """Every class symbol's own directly declared interfaces (D00 §5a's
    `implemented_interfaces` capability), keyed by the type's bare
    descriptor — the form a `NEW`-produced `instance` argument's own
    `symbol` carries, never the module-prefixed identity the `implementations`
    query's own `symbol` column holds (the same stripping `supertypes_of`
    applies to its own rows, D02 §2h, for the same reason).

    CHECKPOINT FACT: each declared interface is itself module-prefixed in the
    real emitted fact (`ClassScanner`'s `interfaceSymbolsJson` runs every
    entry through the same `symbolOf` the class's own type symbol uses) —
    stripped here too, not only on the outer key, or a real registration's
    type would never be found to implement the catalog's declared
    interface."""
    return {
        str(row["symbol"]).rpartition(" ")[2]: [
            str(entry).rpartition(" ")[2] for entry in json.loads(str(row["interfaces"]))
        ]
        for row in workspace.query("implementations")
    }


def _validate_matches(catalog: Catalog) -> None:
    """Refuses a broken catalog before any call site is matched
    (`ports/catalogs.py`'s own discipline, the `single_call._validate_methods`
    precedent): a `matches` block missing `interface`/`handler_method`/
    `registration`, a `registration` missing one of its own required keys, or
    a malformed `channel_via` entry, is a broken file, not a degraded run."""
    matches = catalog.matches
    missing = [key for key in _REQUIRED_MATCHES if key not in matches]
    if missing:
        raise CatalogError(
            f"loading catalog {catalog.source}: `matches` is missing "
            f"{', '.join(missing)} — `interface_implementation` needs `interface`, "
            f"`handler_method` and `registration` (D02 §2's `interface_implementation` style)"
        )
    registration = matches["registration"]
    missing_registration = [key for key in _REQUIRED_REGISTRATION if key not in registration]
    if missing_registration:
        raise CatalogError(
            f"loading catalog {catalog.source}: `registration` is missing "
            f"{', '.join(missing_registration)} — `registration` needs `owner`, `method`, "
            f"`channel_arg` and `receiver_arg` (D02 §2's `interface_implementation` style)"
        )
    for entry in _channel_via_entries(registration):
        valid = (
            isinstance(entry, dict)
            and isinstance(entry.get("owner"), str)
            and isinstance(entry.get("method"), str)
            and (entry.get("arg") == "all_strings" or isinstance(entry.get("arg"), int))
        )
        if not valid:
            raise CatalogError(
                f"loading catalog {catalog.source}: `registration.channel_via` declares an "
                f'entry that must be `{{owner, method, arg: int|"all_strings"}}`, got {entry!r}'
            )


def _channel_via_entries(registration: dict[str, Any]) -> list[Any]:
    """`channel_via`'s `{owner, method, arg}` | `[{...}, ...]` grammar,
    normalized to a list without touching the entries themselves — the
    `single_call._channel_via_entries` precedent, shared in spirit rather
    than in code (this module owns its own `registration` shape, not a
    `methods` row)."""
    via = registration.get("channel_via")
    if via is None:
        return []
    return via if isinstance(via, list) else [via]


def _channel_via_forms(registration: dict[str, Any]) -> list[dict[str, Any]]:
    """`channel_via` entries, each declared `owner` converted to the SCIP
    symbol form once — only ever called on a `registration` block
    `_validate_matches` already passed, at `run` start."""
    return [
        {"owner": _catalog_symbol(entry["owner"]), "method": entry["method"], "arg": entry["arg"]}
        for entry in _channel_via_entries(registration)
    ]
