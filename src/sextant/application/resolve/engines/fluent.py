"""fluent engine for endpoint derivation (D02 §2's `fluent` style).

No single call carries the declaration here — the request is assembled
across several calls on a builder, so the derivation is a walk over one
caller's own `call_sites`, following each `result → receiver` link (D00 §5).
`matches` names `roots` (an owner+method pair that starts a chain, seeding
literal captures such as the verb), `steps` (a method name, owner-free by
default, whose captures fold into the running chain wherever it is reached,
last wins — an optional `owner` narrows a step to one type, needed only
where a library reuses a method name for two different roles on two
different types), and `terminal` (the method names — or, for the OkHttp
join, a `{method, terminal_via_argument}` entry, `true` or an `{owner,
method}` mapping that narrows the join — that make a chain executable).

`terminal` marks *executability*, not the walk's end: captures keep folding
past it, exactly as a real WebClient chain's `bodyToMono` follows `retrieve`.
The walk only stops, and derives one endpoint per path that ever reached a
terminal, once no further row's `receiver` matches the current row's own
chain key — a constructor row's key is its `receiver` (its `result` is void,
checkpoint ruling CP-3), every other row's key is its own `result`. A chain
that never reaches a terminal derives nothing (D02 §4's "the true answer").

Shares `argument_descriptor`, `url_of` and `supertypes_of` verbatim with
`single_call` (`shapes.arguments`) — the same D00 §5 argument grammar,
resolved here off a captured step argument rather than a `methods` row's
positional slot.
"""

import json
import re
from dataclasses import dataclass
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.shapes.arguments import (
    CallFacts,
    CarrierRules,
    _arg_at,
    _capture_resolved,
    argument_descriptor,
    supertypes_of,
    url_of,
)
from sextant.application.resolve.shapes.expansion import _enum_symbols, _rules_of
from sextant.application.resolve.shapes.rooting import _catalog_symbol

# The three capture fields whose declared value is an `argN` reference into
# the matched call site's own arguments, rather than a literal already known
# from the catalog (`http_method`, `response_is`).
_ARGUMENT_FIELDS = ("url", "body", "response")

_ARG_REFERENCE = re.compile(r"^arg(\d+)$")

# A `when` guard's own two keys (D02 §2b): `{arg: int, equals: str}` exactly.
_WHEN_KEYS = {"arg", "equals"}

# The D00 §5 compiler's own "unresolved" argument kind — what a `when` guard
# poisons a step's declared captures to when the guard's own argument cannot
# be read as a string literal. Every downstream reader already treats this
# kind as an honest read failure, never an omission: `url_of` falls through
# to its own unresolved answer, and `_capture_resolved` (Task 4's unified
# helper) reads a `kind != "unresolved"` argument as failed to resolve.
_UNRESOLVED_ARGUMENT = {"kind": "unresolved"}


def run(workspace: Workspace, catalog: Catalog) -> None:
    """Derives one endpoint row per chain reaching a terminal, via the same
    `call_endpoints` insert-if-absent every style uses (D02 §5). `caller` is
    the calling method symbol; `handler` and `peer` follow the same rule
    `single_call` does — NULL unless the captured url is itself absolute
    (CP-2) — and `direction`/`protocol` are the catalog's own declared
    fields."""
    matches = catalog.matches
    roots = [
        {
            "owner": _catalog_symbol(root["owner"]),
            "method": root["method"],
            "captures": root.get("captures", {}),
        }
        for root in matches.get("roots", [])
    ]
    steps = [
        {
            "method": step["method"],
            # Steps stay owner-free by default (D02 §4) — `owner` is an
            # optional filter, needed only where a library reuses one method
            # name for two different roles on two different types (a
            # RestClient's `body(Object)` request-setter and its
            # `body(Class)` response-extractor).
            "owner": _catalog_symbol(step["owner"]) if "owner" in step else None,
            "captures": step.get("captures", {}),
            # D02 §2b: a step may declare a value guard on another argument
            # — None for the (default) unguarded step, read by `_walk`
            # (`_step_captures`) where `_matching_step` finds this row.
            "when": step.get("when"),
        }
        for step in matches.get("steps", [])
    ]
    _validate_steps(steps, catalog)
    _validate_captures(roots + steps, catalog)
    terminal_names, via_argument_names = _terminal_index(matches.get("terminal", []))
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
    # Parsed once, as single_call does, for the same reason: both the root
    # scan below and the shared `argument_descriptor`'s `call_wrappers`
    # one-hop need the parsed list, never the raw JSON text.
    call_sites = [
        {**site, "arguments": json.loads(str(site["arguments"]))}
        for site in workspace.query("call_sites")
    ]
    by_caller: dict[str, list[dict[str, Any]]] = {}
    for site in call_sites:
        by_caller.setdefault(str(site["caller"]), []).append(site)

    # A list, not a set — NFR-1, the same reason single_call's own
    # `referenced` accumulator is one.
    referenced: list[str] = []
    rows: list[dict[str, Any]] = []
    # Only a resolved wire identity dedups here, exactly as single_call:
    # two unresolved chains carry no path to compare, so each stays its own
    # row. Required by derive_call_endpoints.sql's own contract — it only
    # guards against what is already in the table, not against duplicates
    # arriving in the same `$rows` batch.
    seen: set[tuple[str, str, str, str]] = set()
    for caller, sites in by_caller.items():
        # Chain reconstruction is within-method only (D00 §5): `by_receiver`
        # is built fresh per caller, over that caller's own sites alone, so a
        # value id from one method can never be mistaken for a link in
        # another.
        by_receiver: dict[Any, list[dict[str, Any]]] = {}
        for site in sites:
            by_receiver.setdefault(site["receiver"], []).append(site)
        facts = CallFacts(supertypes=supertypes, caller_call_sites=sites, referenced=referenced)
        context = _ChainContext(
            caller=caller,
            sites=sites,
            by_receiver=by_receiver,
            steps=steps,
            terminal_names=terminal_names,
            via_argument_names=via_argument_names,
            catalog=catalog,
            facts=facts,
            carrier_rules=carrier_rules,
            rows=rows,
            seen=seen,
        )
        # Sites are already ordinal-ordered (the `call_sites` query), so a
        # fork — several rows sharing one receiver — is walked in ordinal
        # order too (NFR-1), via `by_receiver`'s own insertion order below.
        for site in sites:
            root = _matching_root(site, roots)
            if root is None:
                continue
            captures = _resolve_captures(root["captures"], site)
            _walk(site, captures, reached_terminal=False, context=context)

    workspace.derive("call_endpoints", rows=rows)


@dataclass(frozen=True)
class _ChainContext:
    """Everything one caller's walk shares across every root and every step
    reached from it — grouped so the recursive walker's own signature stays
    just the two things that change per row: the row itself and the captures
    folded so far."""

    caller: str
    sites: list[dict[str, Any]]
    by_receiver: dict[Any, list[dict[str, Any]]]
    steps: list[dict[str, Any]]
    terminal_names: set[str]
    via_argument_names: dict[str, dict[str, str] | None]
    catalog: Catalog
    facts: CallFacts
    carrier_rules: CarrierRules
    rows: list[dict[str, Any]]
    seen: set[tuple[str, str, str, str]]


def _walk(
    site: dict[str, Any],
    captures: dict[str, Any],
    reached_terminal: bool,
    context: _ChainContext,
) -> None:
    """Follows one row forward through its own chain key (CP-3), folding
    every branch's captures independently — "two rows may share a receiver"
    is exactly a fork, and each continuation derives on its own. Derivation
    happens only at a walk's true end (no row's `receiver` matches this row's
    own chain key), never merely on reaching a terminal, because captures
    still fold past it."""
    name = str(site["name"])
    if name in context.terminal_names or (
        name in context.via_argument_names
        and _has_execute_join(site, context.sites, context.via_argument_names[name])
    ):
        reached_terminal = True
    chain_key = _chain_key(site)
    # A void ordinary call (`result` null, D00 §5) has nothing a following
    # row's `receiver` could ever really match — `None` is not a value id,
    # and treating it as one would pull in every static call in this caller
    # (their own `receiver` is `None` too) as spurious continuations. The
    # chain honestly ends here instead, exactly as it does when nothing
    # matches a real id.
    if chain_key is None:
        nexts: list[dict[str, Any]] = []
    else:
        # A constructor's own chain key IS its own `receiver` (CP-3), so
        # `by_receiver` — grouped by that same field — trivially contains the
        # constructor row itself wherever its key is looked up; excluded
        # here so a `<init>` root never chains into itself.
        nexts = [s for s in context.by_receiver.get(chain_key, []) if s is not site]
    if not nexts:
        if reached_terminal:
            _derive(captures, context)
        return
    for next_site in nexts:
        next_captures = dict(captures)
        step = _matching_step(next_site, context.steps)
        if step is not None:
            # Last wins (D02 §4): a repeated step overwrites its own earlier
            # capture here, in visitation order, with no extra bookkeeping.
            # `next_site`'s own arguments are what a `when` guard (D02 §2b)
            # reads, so the guard is evaluated here, in `_resolve_captures`'s
            # caller, rather than inside it.
            next_captures.update(_step_captures(step, next_site))
        _walk(next_site, next_captures, reached_terminal, context)


def _derive(captures: dict[str, Any], context: _ChainContext) -> None:
    verb = captures.get("http_method")
    if verb is None:
        # No root ever seeded a verb — not a shape this catalog declares.
        return
    peer, path, url_resolution = url_of(captures.get("url"))
    body_argument = captures.get("body")
    response_argument = captures.get("response")
    # Checkpoint ruling I1, folded in from single_call: a capture that WAS
    # reached but which the scanner could not read drops the row's
    # resolution; a capture never reached at all is simply not part of this
    # chain's declaration and cannot fail it. Presence of the key is what
    # separates the two — a reached step always writes its declared field,
    # even when the slot it addresses is empty (I4), so `None` under a key
    # that exists is a read failure while an absent key is no claim at all.
    resolution = (
        "resolved"
        if url_resolution == "resolved"
        and _capture_resolved("body" in captures, body_argument)
        and _capture_resolved("response" in captures, response_argument)
        else "unresolved"
    )
    if path is not None:
        key = (context.catalog.protocol, context.catalog.direction, str(verb), path)
        if key in context.seen:
            return
        context.seen.add(key)
    context.rows.append(
        {
            "protocol": context.catalog.protocol,
            "direction": context.catalog.direction,
            "method": str(verb),
            "path": path,
            "handler": None,
            "caller": context.caller,
            "peer": peer,
            "handler_signature": None,
            "resolution": resolution,
            "evidence": "compiler",
            "catalog_id": context.catalog.id,
            "request_shape": argument_descriptor(
                body_argument, context.facts, context.carrier_rules
            ),
            "response_shape": _response_descriptor(
                response_argument,
                captures.get("response_is"),
                context.facts,
                context.carrier_rules,
            ),
        }
    )


def _response_descriptor(
    argument: dict[str, Any] | None,
    response_is: str | None,
    facts: CallFacts,
    carrier_rules: CarrierRules,
) -> str | None:
    """`response_is: array` (a `bodyToFlux`-shaped step) wraps the argument's
    own descriptor in a collection envelope — the same `{wire_type: array,
    item: …}` grammar `_described` builds for a declared `List<T>` field —
    rather than describing `argument_descriptor`'s own (scalar) answer for
    the element type alone."""
    descriptor_json = argument_descriptor(argument, facts, carrier_rules)
    if descriptor_json is None or response_is != "array":
        return descriptor_json
    wrapped = {
        "wire_type": "array",
        "wire_format": "",
        "nullable": True,
        "item": json.loads(descriptor_json),
    }
    return json.dumps(wrapped, sort_keys=True, separators=(",", ":"))


def _matching_root(site: dict[str, Any], roots: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (
            root
            for root in roots
            if site["owner"] == root["owner"] and site["name"] == root["method"]
        ),
        None,
    )


def _matching_step(site: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The one declared step matching `site` — the whole entry, `captures`
    and its optional `when` guard together, since evaluating the guard
    (D02 §2b) needs `site`'s own arguments, read by `_step_captures` in
    `_walk` where they are at hand — or None where nothing does:
    "unmatched steps pass through uncaptured" (D02 §4). An owner-less step
    matches any owner; `_validate_steps` already refused any catalog where
    more than one entry could match the same row, so at most one candidate
    here ever applies."""
    name = str(site["name"])
    return next(
        (
            step
            for step in steps
            if step["method"] == name and step["owner"] in (None, site["owner"])
        ),
        None,
    )


def _validate_steps(steps: list[dict[str, Any]], catalog: Catalog) -> None:
    """Refuses a catalog where two step entries share a method name with no
    `owner` telling them apart — silent last-wins would hide exactly the bug
    it is meant to catch (`ports/catalogs.py`'s own discipline: an unchecked
    value does not stay in the file). Two entries are distinguishable only
    when BOTH declare an `owner` and the owners differ; an owner-less entry
    matches every owner, so it collides with any sibling regardless of what
    that sibling declares."""
    by_method: dict[str, list[dict[str, Any]]] = {}
    for step in steps:
        by_method.setdefault(step["method"], []).append(step)
    for method, group in by_method.items():
        if len(group) < 2:
            continue
        owners = [step["owner"] for step in group]
        if any(owner is None for owner in owners) or len(set(owners)) != len(owners):
            raise CatalogError(
                f"loading catalog {catalog.source}: steps named `{method}` need distinct "
                f"`owner`s to tell them apart (D02 §4's fluent style)"
            )


def _validate_captures(entries: list[dict[str, Any]], catalog: Catalog) -> None:
    """Refuses a catalog whose `url`/`body`/`response` capture does not name
    a call-site position (`ports/catalogs.py`'s own discipline again: an
    unchecked value does not stay in the file).

    These three fields address an argument by position, and anything that is
    not `argN` — a typo, a bare number, a field name — silently captures
    nothing: the row still derives, with the payload column NULL and the url
    unresolved, which is indistinguishable from a call site that genuinely
    carries neither. A capture out of *range* is a different answer and
    cannot be checked here, because the range belongs to each matched call
    site rather than to the catalog; ruling I1 already covers it at derive
    time, where the site is known.

    A step's own `when` guard (D02 §2b) must be `{arg: int, equals: str}`
    exactly — checked here too, at the same load-time pass, rather than
    only discovered the first time a call site reaches a malformed guard."""
    for entry in entries:
        for field, value in entry["captures"].items():
            if field in _ARGUMENT_FIELDS and not _ARG_REFERENCE.match(str(value)):
                raise CatalogError(
                    f"loading catalog {catalog.source}: `{entry['method']}` captures "
                    f"`{field}: {value}`, which is not a call-site position — an argument "
                    f"capture reads `argN` (D02 §4's fluent style)"
                )
        when = entry.get("when")
        if when is not None and not _valid_when(when):
            raise CatalogError(
                f"loading catalog {catalog.source}: `{entry['method']}` declares "
                f"`when: {when!r}`, which must be `{{arg: int, equals: str}}` exactly "
                f"(D02 §2b's value-guarded step)"
            )


def _valid_when(when: Any) -> bool:
    """Whether a declared `when` guard is exactly `{arg: int, equals:
    str}` — no missing key, no extra key, no wrong-typed value."""
    return (
        isinstance(when, dict)
        and set(when) == _WHEN_KEYS
        and isinstance(when.get("arg"), int)
        and isinstance(when.get("equals"), str)
    )


def _terminal_index(
    entries: list[Any],
) -> tuple[set[str], dict[str, dict[str, str] | None]]:
    """Splits `matches.terminal` into method names that end a chain on their
    own, and ones that only do so through the execute-join (checkpoint
    ruling: the catalog marks it `terminal_via_argument: true` on the
    terminal entry) — the OkHttp shape, where `build`'s own row carries no
    link to `newCall` except through a *different* row's argument `source`.
    A bare `true` joins to any row carrying the argument link; an
    `{owner, method}` mapping instead narrows the join to that one declared
    call, closing the fabrication a bare join leaves open — `Request r =
    builder.build(); log.debug("…", r)` consumes `build`'s own result too,
    and without a filter that non-executing use would complete the chain."""
    plain: set[str] = set()
    via_argument: dict[str, dict[str, str] | None] = {}
    for entry in entries:
        if isinstance(entry, str):
            plain.add(entry)
            continue
        marker = entry.get("terminal_via_argument")
        if not marker:
            plain.add(entry["method"])
            continue
        via_argument[entry["method"]] = (
            {"owner": _catalog_symbol(marker["owner"]), "method": marker["method"]}
            if isinstance(marker, dict)
            else None
        )
    return plain, via_argument


def _has_execute_join(
    site: dict[str, Any], sites: list[dict[str, Any]], join_filter: dict[str, str] | None
) -> bool:
    """Whether some row in this same caller carries an argument whose
    `source` names `site`'s own `result` — the OkHttp `build()` → `newCall()`
    split, joined through D00 §5's `arguments[].source` rather than through
    `receiver`/`result` chaining, because `newCall`'s own receiver is the
    client, not the request builder. `join_filter`, when the catalog
    declared one, additionally requires the joining row itself to be that
    exact owner+method — otherwise any consumer of the built value (a log
    statement, an equality check) would count as executing it."""
    result = site["result"]
    if result is None:
        return False
    for candidate in sites:
        if join_filter is not None and (
            candidate["owner"] != join_filter["owner"] or candidate["name"] != join_filter["method"]
        ):
            continue
        if any(argument.get("source") == result for argument in candidate["arguments"]):
            return True
    return False


def _chain_key(site: dict[str, Any]) -> Any:
    """The value id a following row's `receiver` must match to extend this
    row's own chain (checkpoint ruling CP-3): a constructor's `result` is
    void by construction, so its own `receiver` — the constructed value's id
    — is what the next call in the chain actually holds; every other call's
    own `result` is its answer, exactly as it is fed forward in real
    bytecode."""
    return site["receiver"] if site["name"] == "<init>" else site["result"]


def _step_captures(step: dict[str, Any], site: dict[str, Any]) -> dict[str, Any]:
    """The captures one matched step contributes for `site` — plain
    `_resolve_captures` where the step declares no `when`, and D02 §2b's
    three-way guard answer otherwise, read off `site`'s own arguments:

    - the guard argument is a string literal equal to `when["equals"]` —
      the step's own captures apply, exactly as an unguarded step's would;
    - the guard argument is a string literal, but a DIFFERENT one — the
      step still matched the chain (D02 §2b: "the step matches the chain
      either way"), only its captures do not apply, so nothing here
      overwrites whatever an earlier step already folded in;
    - anything else (no argument at that position, the wrong kind, or the
      compiler's own `unresolved`) poisons every capture this step
      declares to `_UNRESOLVED_ARGUMENT` — it might have been the guarded
      key, and an unreadable key must never let a chain preserve an
      earlier confident answer."""
    when = step.get("when")
    if when is None:
        return _resolve_captures(step["captures"], site)
    guard = _arg_at(site["arguments"], when["arg"])
    if guard is not None and guard.get("kind") == "string" and isinstance(guard.get("value"), str):
        if guard["value"] == when["equals"]:
            return _resolve_captures(step["captures"], site)
        return {}
    return {field: _UNRESOLVED_ARGUMENT for field in step["captures"]}


def _resolve_captures(declared: dict[str, Any], site: dict[str, Any]) -> dict[str, Any]:
    """One matched row's own captured values: `url`/`body`/`response` read
    the `argN`-addressed argument off `site` itself (the raw D00 §5 argument,
    resolved later exactly as `single_call` resolves a positional one);
    every other field (`http_method`, `response_is`) is the catalog's own
    literal, unchanged."""
    resolved: dict[str, Any] = {}
    for field, value in declared.items():
        if field in _ARGUMENT_FIELDS:
            resolved[field] = _arg_at(site["arguments"], _arg_index(value))
        else:
            resolved[field] = value
    return resolved


def _arg_index(value: Any) -> int | None:
    match = _ARG_REFERENCE.match(str(value))
    return int(match.group(1)) if match else None
