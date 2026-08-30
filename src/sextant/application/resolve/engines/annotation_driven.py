"""Annotation-driven engine for endpoint derivation (D02 §2).

Framework knowledge — which annotation marks a controller, which annotation
maps to which HTTP method, where the path argument lives — is data, read
from `matches` and carried, unmodified, through to the derivation as bound
parameters. No framework name appears in this module.
"""

import json
from typing import Any

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.shapes.contracts import _payload_descriptor
from sextant.application.resolve.shapes.expansion import _enum_symbols, _rules_of
from sextant.application.resolve.shapes.rooting import _catalog_symbol


def run(workspace: Workspace, catalog: Catalog) -> None:
    """Passes the catalog's own protocol, direction, annotation identifiers and
    mapping declaration through to the derivation as bound parameters. The
    engine here is generic: it never names a framework or a protocol, only
    forwards what the catalog declares."""
    mapping = catalog.matches["mapping"]
    workspace.derive(
        "endpoints",
        protocol=catalog.protocol,
        direction=catalog.direction,
        # Optional (D02 §2, amended): absence means "no type-level gate".
        type_annotation=catalog.matches.get("type_annotation"),
        prefix_annotation=mapping["prefix_annotation"],
        # `method` is absent for an annotation that pre-sets none, and the
        # derivation reads that absence as "every method in all_methods".
        mapping_annotations=[
            {"fqn": m["fqn"], "methods": m.get("method")} for m in mapping["annotations"]
        ],
        path_from=list(mapping["path_from"]),
        prefix_from=list(mapping["prefix_from"]),
        peer_from=list(mapping.get("peer_from", [])),
        method_from=mapping["method_from"],
        all_methods=list(mapping["all_methods"]),
    )
    # Optional (D02 §2, amended): a catalog with no `reply` block declares no
    # second-row rule at all — the HTTP catalogs, which never see @SendTo.
    if "reply" in catalog.matches:
        _derive_replies(workspace, catalog)


def _derive_replies(workspace: Workspace, catalog: Catalog) -> None:
    """D02 §2's `reply` block: a listener's declared reply (`@SendTo` and
    its like) derives a second, OUTBOUND row per listed destination —
    `caller` the handler, payload the handler's own return type — plus one
    `path`-NULL `unresolved` row for a value-returning handler that never
    declared the annotation at all (the reply destination exists, just not
    where the annotations can name it — a `ReplyingKafkaTemplate` caller,
    say). A `void` handler (its return type's own `_payload_descriptor` is
    `None`) derives no reply row at all: there is nothing to reply with.

    Restricted to the handlers THIS catalog's own inbound derivation just
    produced, above, in this same `run` call — `workspace.query("endpoints")`
    filtered to this catalog's own `protocol` and an inbound-bearing
    `direction` — so a method that happens to carry the reply annotation but
    was never mapped to an inbound row by this catalog (no listener
    annotation on it at all) is never reached here (D02 §2, amended).

    The return type comes off `handler_signature` on that very endpoint
    row — the same signature `derive_endpoints.sql` already read for it
    (`s.signature`) and the same column `shapes/contracts.py`'s own
    `_contracts_of` reads for the *response* half of an inbound row's
    contract — rather than a fresh lookup, since a reply row's payload IS
    that response type.
    """
    reply = catalog.matches["reply"]
    reply_annotation = _catalog_symbol(reply["annotation"])
    destination_attr = reply["destination_from"]
    rules = _rules_of(catalog)
    enums = _enum_symbols(workspace)
    # `_payload_descriptor` appends every object it meets to this, exactly as
    # every other pass's own `referenced` accumulator does — so a reply
    # payload type reached only here still reaches shape expansion.
    referenced: list[str] = []

    # A dict first, then its keys sorted (NFR-1): one inbound row per
    # listened destination already means the same handler symbol can sit on
    # several endpoint rows (a multi-topic listener), and this pass owes
    # each handler exactly one reply decision, not one per inbound row it
    # happens to appear on. `setdefault` keeps the first-seen signature,
    # which is the same value every row for one handler carries regardless.
    signatures: dict[str, object] = {}
    for endpoint in workspace.query("endpoints"):
        handler = endpoint["handler"]
        if (
            endpoint["protocol"] == catalog.protocol
            and endpoint["direction"] in ("inbound", "both")
            and handler
        ):
            signatures.setdefault(str(handler), endpoint["handler_signature"])

    rows: list[dict[str, Any]] = []
    for handler in sorted(signatures):
        declared = signatures[handler]
        if declared is None:
            continue
        signature = json.loads(str(declared))
        descriptor = _payload_descriptor(signature.get("returns"), rules, enums, referenced)
        if descriptor is None:
            continue
        uses = workspace.query("annotations_of", target=handler)
        reply_use = next((use for use in uses if use["annotation"] == reply_annotation), None)
        if reply_use is None:
            rows.append(_reply_row(catalog, handler, None, "unresolved", descriptor))
            continue
        args = json.loads(str(reply_use["args"])) if reply_use["args"] is not None else {}
        # Destinations in listed order (NFR-1).
        for destination in _destinations_of(args, destination_attr):
            rows.append(_reply_row(catalog, handler, destination, "resolved", descriptor))

    workspace.derive("call_endpoints", rows=rows)


def _destinations_of(args: dict[str, Any], name: str) -> list[str]:
    """The reply annotation's destination attribute, read scalar-or-array —
    the Python mirror of `derive_endpoints.sql`'s own alias-reading pattern
    for `path_from`. CHECKPOINT FACT: the reply annotation's own destination
    attribute (`@SendTo`'s `value`) always arrives as a `String[]` in
    bytecode, even for a bare-string source declaration — but the scalar
    form is still read here, for a reply annotation on a framework not yet
    catalogued that might not share that emission quirk."""
    value = args.get(name)
    if isinstance(value, list):
        return [str(entry) for entry in value]
    if value is not None:
        return [str(value)]
    return []


def _reply_row(
    catalog: Catalog,
    handler: str,
    destination: str | None,
    resolution: str,
    request_shape: str,
) -> dict[str, Any]:
    """One reply row's fixed shape (D01 §3, amended): a reply is always
    outbound and verbless; the handler that produced the payload lands in
    `caller`, never `handler` — a reply row has no consuming method of its
    own for this pass to see — and `response_shape` is always absent (a
    reply carries no response of its own)."""
    return {
        "protocol": catalog.protocol,
        "direction": "outbound",
        "method": None,
        "path": destination,
        "handler": None,
        "caller": handler,
        "peer": None,
        "handler_signature": None,
        "resolution": resolution,
        "evidence": "compiler",
        "request_shape": request_shape,
        "response_shape": None,
    }
