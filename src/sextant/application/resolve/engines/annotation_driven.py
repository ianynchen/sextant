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
    type_annotation = catalog.matches.get("type_annotation")
    prefix_annotation = mapping["prefix_annotation"]
    workspace.derive(
        "endpoints",
        protocol=catalog.protocol,
        direction=catalog.direction,
        # Optional (D02 §2, amended): absence means "no type-level gate".
        type_annotation=None if type_annotation is None else _catalog_symbol(type_annotation),
        # Optional too (Retrofit, spring-jms): no class-level prefix shape.
        prefix_annotation=(
            None if prefix_annotation is None else _catalog_symbol(prefix_annotation)
        ),
        # `method` is absent for an annotation that pre-sets none, and the
        # derivation reads that absence as "every method in all_methods".
        mapping_annotations=[
            {"fqn": _catalog_symbol(m["fqn"]), "methods": m.get("method")}
            for m in mapping["annotations"]
        ],
        path_from=list(mapping["path_from"]),
        prefix_from=list(mapping["prefix_from"]),
        peer_from=list(mapping.get("peer_from", [])),
        method_from=mapping["method_from"],
        all_methods=list(mapping["all_methods"]),
        catalog_id=catalog.id,
    )
    # Optional (D02 §2, amended): a catalog with no `reply` block declares no
    # second-row rule at all — the HTTP catalogs, which never see @SendTo.
    if "reply" in catalog.matches:
        _derive_replies(workspace, catalog)


def _derive_replies(workspace: Workspace, catalog: Catalog) -> None:
    """D02 §2's `reply` block: a listener's declared reply (`@SendTo` and
    its like) derives a second, OUTBOUND row per listed destination —
    `caller` the handler, payload the handler's own return type — plus one
    `path`-NULL `unresolved` row for a value-returning handler whose reply
    destination this catalog cannot name: the annotation absent altogether
    (the destination exists, just not where the annotations can see it — a
    `ReplyingKafkaTemplate` caller, say), or present but bare, listing no
    destination. A `void` handler (its return type's own `_payload_descriptor` is
    `None`) derives no reply row at all: there is nothing to reply with.

    Restricted to the handlers THIS catalog's own rows produced: `catalog_id`
    (2E-prep design §1a) names the derivation that produced each row, so
    filtering `endpoints` on `catalog_id == catalog.id` is already exactly
    this catalog's own handler set — no annotations re-scan needed.

    The return type comes off `handler_signature` on the matching endpoint
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
    # `_payload_descriptor` requires an accumulator, and this one is
    # DISCARDED: nothing reads it after `_derive_replies` returns, so it is
    # not what carries a reply payload into shape expansion. What does is the
    # inbound row this reply belongs to — a reply's payload IS its handler's
    # return type, which `shapes/contracts.py` roots as that same handler's
    # `response_shape` off `handler_signature`. That, not this list, is why
    # a reply payload is expanded today.
    referenced: list[str] = []

    # A dict first, then its keys sorted (NFR-1): one inbound row per
    # listened destination already means the same handler symbol can sit on
    # several endpoint rows (a multi-topic listener), and this pass owes
    # each handler exactly one reply decision, not one per inbound row it
    # happens to appear on. `setdefault` keeps the first-seen signature,
    # which is the same value every row for one handler carries regardless.
    signatures: dict[str, object] = {}
    for endpoint in workspace.query("endpoints"):
        if endpoint.get("catalog_id") == catalog.id and endpoint.get("handler"):
            signatures.setdefault(str(endpoint["handler"]), endpoint["handler_signature"])

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
        destinations = _destinations_of(args, destination_attr)
        # A BARE reply annotation — declared, but naming no destination at
        # all — lands on the very same path-NULL `unresolved` row the
        # no-annotation branch above emits (final review, CRITICAL). It used
        # to derive nothing: the loop below simply never ran, so a handler
        # that *declares* it replies produced strictly LESS than one that
        # declares nothing, inverting the evidence. Both bytecode forms of
        # bare reach here — `@SendTo`'s `value` defaults to `{}`, recorded
        # either as the attribute key absent or as an explicit empty array —
        # and neither is a fact about the handler, so neither may change the
        # answer.
        if not destinations:
            rows.append(_reply_row(catalog, handler, None, "unresolved", descriptor))
            continue
        # Destinations in listed order (NFR-1).
        for destination in destinations:
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
        "catalog_id": catalog.id,
        "request_shape": request_shape,
        "response_shape": None,
    }
