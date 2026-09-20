"""Effective call sites (spec 2026-09-19 §3): the `call_sites` facts as every ENGINE reads
them, with two projections applied once per load — a compiler-emitted `$default` bridge call
re-targeted to the function it stands for (§3a, T4) and a class-compiled lambda argument
read as the `lambda` it is (§3b, T5). Both join on shared fields the extractor publishes on
the declaration it scanned (`bridge_of`, `lambda_body`); nothing here names a language.

`call_sites` itself is untouched: the exported bundle, the graph/trace readers
(`call_edges`, `return_flow`, `format`) and every raw-fact test keep the bytecode's own
statement. This module is the ONE projection point (F10) — a reader that wants what the
engines see calls `effective_call_sites`, never `query("call_sites")` plus its own rewrite.
"""

from dataclasses import dataclass
from typing import Any

from sextant.application.ports.workspace import Workspace
from sextant.domain.symbols import (
    bare_descriptor,
    descriptor_slots,
    method_descriptor,
    owner_of,
)

# The name suffix a compiler-emitted default-argument bridge carries (`<fn>$default`,
# OI-81) and the marker type its last slot always is. Neither identifies a bridge on its
# own — only the extractor's `bridge_of` does — but a site whose name lacks the suffix is
# never one, and that test is what keeps the projection from hashing every site's symbol.
_DEFAULT_SUFFIX = "$default"
_MARKER = "Ljava/lang/Object;"
_MASK_SLOT = "I"
_MASK_BITS = 32


def effective_call_sites(workspace: Workspace) -> list[dict[str, Any]]:
    """`call_sites`, projected. Ordinal-ordered as the named query is (NFR-1); built once
    per load through `Workspace.once`, which also guards that only fact queries are read."""
    return workspace.once(_effective)


@dataclass(frozen=True)
class _Bridge:
    """The sibling a `$default` bridge stands for, settled (spec §3a): its name and JVM
    descriptor; `receiver` is 1 where it is an instance method and the bridge's slot 0 is
    its receiver, 0 for a static sibling; `slots` is its own parameter count; `extension`
    is 1 where its first slot is the receiver the author wrote (`receiver: true` on that
    parameter of its declaration) and 0 otherwise. The mask counts the parameters the
    author DECLARED — `slots - extension` of them — and bit *i* is slot `extension + i`.
    MEASURED on `fixtures/orders-ktor`'s `mount$default` (`javap -c -p`, 2026-09-20): a
    static `mount(Route, String, String, Function1)` whose slot 0 is its receiver is
    called with mask 2 when its `version`, slot 2, is defaulted, and the bridge's own
    body substitutes slot 2 — so bit 1 is slot 2, not slot 1."""

    name: str
    descriptor: str
    receiver: int
    slots: int
    extension: int

    @property
    def declared(self) -> int:
        """The parameters the author declared: the slots less the receiver among them."""
        return self.slots - self.extension


@dataclass(frozen=True)
class _Declaration:
    """What the projection reads off a sibling candidate's own declaration."""

    static: bool
    extension: int


def _masks(declared: int) -> int:
    """How many mask ints the compiler passes for `declared` parameters: one bit each."""
    return (declared + _MASK_BITS - 1) // _MASK_BITS


def _effective(workspace: Workspace) -> list[dict[str, Any]]:
    bridges = {
        bare_descriptor(str(row["symbol"])): str(row["bridge_of"])
        for row in workspace.query("bridge_declarations")
    }
    bodies = _lambda_bodies(workspace)
    sites = workspace.query("call_sites")
    if not bridges and not bodies:
        return list(sites)
    declared = (
        {
            bare_descriptor(str(row["symbol"])): _Declaration(
                _is_static(row["modifiers"]), _extension(row["signature"])
            )
            for row in workspace.query("method_declarations")
        }
        if bridges
        else {}
    )
    # A bridge is called from many sites; its sibling is settled once.
    settled: dict[str, _Bridge | None] = {}
    rows: list[dict[str, Any]] = []
    for site in sites:
        name = site["name"]
        row = site
        if bridges and isinstance(name, str) and name.endswith(_DEFAULT_SUFFIX):
            owner, descriptor = str(site["owner"]), str(site["descriptor"])
            symbol = method_descriptor(owner, name, descriptor)
            function = bridges.get(symbol)
            if function is not None:
                if symbol not in settled:
                    settled[symbol] = _sibling(owner, descriptor, function, declared)
                bridge = settled[symbol]
                if bridge is not None:
                    row = _through_bridge(site, bridge) or site
        if bodies:
            row = _with_lambdas(row, bodies)
        rows.append(row)
    return rows


def _lambda_bodies(workspace: Workspace) -> dict[str, str]:
    """Every class-compiled lambda the facts mark, keyed the way an `instance` argument
    names its class (the bare descriptor), to the body method it stands for."""
    return {
        bare_descriptor(str(row["symbol"])): str(row["body"])
        for row in workspace.query("lambda_bodies")
    }


def _with_lambdas(row: dict[str, Any], bodies: dict[str, str]) -> dict[str, Any]:
    """`row` with each class-compiled lambda among its arguments read as the `lambda` it
    is (spec §3b), or `row` itself when none is — so a site untouched by either step is
    the cached dict, not a copy of it. A projected argument is a fresh dict and the row
    holding it a copy: the raw row's list and dicts are never written into."""
    arguments = [_as_lambda(argument, bodies) for argument in row["arguments"]]
    if all(after is before for after, before in zip(arguments, row["arguments"])):
        return row
    projected = dict(row)
    projected["arguments"] = arguments
    return projected


def _as_lambda(argument: dict[str, Any], bodies: dict[str, str]) -> dict[str, Any]:
    """The argument as the engines read it: an `instance` of a class whose type fact
    carries `lambda_body` becomes `{kind: lambda, symbol: <body>, captures: 0}` — exact,
    because constructor-captured values are fields of the class, never leading parameters
    of the body, so the interface's own parameters start at index 0 — keeping `source`
    where the instance carried one. A named constant (`enum` kind) whose OWNER is such a
    class is the same lambda: a closure that captures nothing is compiled to one shared
    instance its call sites read as a static constant of its own type (CP-23 Q7b), and
    the extractor emits that read as it emits every constant of its own type, leaving
    the join to the consumer. An `array`'s elements are read the same way, because
    `_expanded_arguments` reads them. Anything else is returned as it is, the same dict."""
    if argument.get("kind") == "array" and isinstance(argument.get("elements"), list):
        elements = [_as_lambda(element, bodies) for element in argument["elements"]]
        if all(after is before for after, before in zip(elements, argument["elements"])):
            return argument
        return {**argument, "elements": elements}
    if argument.get("kind") == "instance":
        owner: str | None = bare_descriptor(str(argument.get("symbol")))
    elif argument.get("kind") == "enum":
        owner = owner_of(bare_descriptor(str(argument.get("symbol"))))
    else:
        return argument
    body = None if owner is None else bodies.get(owner)
    if body is None:
        return argument
    projected: dict[str, Any] = {"kind": "lambda", "symbol": body, "captures": 0}
    if argument.get("source") is not None:
        projected["source"] = argument["source"]
    return projected


def _is_static(modifiers: object) -> bool:
    """D00 §5a's `modifiers.static`, off the decoded column; a fact from a scanner that
    reported no modifiers at all (`None`) has not said the method is static."""
    return isinstance(modifiers, dict) and bool(modifiers.get("static"))


def _extension(signature: object) -> int:
    """1 where the declaration's first parameter is flagged `receiver` (D00 §5a: the slot
    is the receiver the author wrote, only ever the first one the declaration owns), else
    0 — including a fact with no signature, which has not said so."""
    parameters = signature.get("parameters") if isinstance(signature, dict) else None
    if not isinstance(parameters, list) or not parameters:
        return 0
    first = parameters[0]
    return 1 if isinstance(first, dict) and bool(first.get("receiver")) else 0


def _sibling(
    owner: str, descriptor: str, function: str, declared: dict[str, _Declaration]
) -> _Bridge | None:
    """The sibling a bridge stands for, or None where it cannot be settled — neither
    candidate declared, or both (A5) — so its calls stay exactly as the bytecode said.

    The bridge's slots are `[receiver?] declared... mask... marker`, and `receiverSlots`
    is not published, so both readings are tried: with a receiver slot and without. For
    each, every parameter count whose trailing slots are all mask ints names a candidate
    descriptor, and the candidate exists when `owner#function(<those slots>)` is a
    declared method — the same arithmetic every call-to-callee join uses
    (`method_descriptor`) — whose masks, one per 32 DECLARED parameters (its slots less
    the receiver it may own as its first), fill the remaining slots exactly. Its
    static-ness and its own receiver are read off that declaration, never inferred from
    which reading won.
    """
    slots, returned = descriptor_slots(descriptor)
    if not slots or slots[-1] != _MARKER:
        return None
    candidates: list[_Bridge] = []
    for receiver in (1, 0):
        available = len(slots) - receiver - 1
        for count in range(1, available + 1):
            if any(slot != _MASK_SLOT for slot in slots[receiver + count : -1]):
                continue
            sibling = "(" + "".join(slots[receiver : receiver + count]) + ")" + returned
            declaration = declared.get(method_descriptor(owner, function, sibling))
            if declaration is None or count + _masks(count - declaration.extension) != available:
                continue
            # An instance sibling is reached through the receiver slot, a static one has
            # none: a reading whose static-ness contradicts its slot layout is not the
            # sibling, even when a method of that descriptor happens to be declared.
            if declaration.static == (receiver == 0):
                candidates.append(
                    _Bridge(function, sibling, receiver, count, declaration.extension)
                )
    if len(candidates) != 1:
        return None
    return candidates[0]


def _through_bridge(site: dict[str, Any], bridge: _Bridge) -> dict[str, Any] | None:
    """The call as the sibling sees it, or None where a mask is not an int literal — a
    wrong trimming is worse than the silence there is today (spec §3a). A copy: the raw
    row and its argument dicts belong to the cached `call_sites` list and are never
    written into."""
    arguments = list(site["arguments"])
    if len(arguments) != bridge.receiver + bridge.slots + _masks(bridge.declared) + 1:
        return None
    masks: list[int] = []
    for argument in arguments[bridge.receiver + bridge.slots : -1]:
        if argument.get("kind") != "int":
            return None
        masks.append(int(str(argument["value"])))
    # A fresh dict per defaulted slot: rows are shared by every engine, and one dict
    # standing in many rows would make a write into one a write into all of them. The
    # sibling's own receiver slot, where it has one, is no declared parameter and has no
    # bit: it passes through as the caller pushed it.
    projected = arguments[bridge.receiver : bridge.receiver + bridge.extension] + [
        {"kind": "unresolved", "reason": "defaulted"}
        if (masks[index // _MASK_BITS] >> (index % _MASK_BITS)) & 1
        else arguments[bridge.receiver + bridge.extension + index]
        for index in range(bridge.declared)
    ]
    row = dict(site)
    row["name"] = bridge.name
    row["descriptor"] = bridge.descriptor
    row["arguments"] = projected
    row["evidence_bridge"] = f"{site['owner']}{site['name']}{site['descriptor']}"
    if bridge.receiver:
        # D00 §5: `receiver` is the value id the receiver came from, `receiver_parameter`
        # the caller's parameter index when it is one; a slot carrying neither (`field`,
        # `unresolved`) leaves both NULL, which every origin check reads as "not the origin".
        receiver = arguments[0]
        row["invoke_kind"] = "virtual"
        row["receiver"] = receiver.get("source")
        row["receiver_parameter"] = (
            receiver.get("value") if receiver.get("kind") == "parameter" else None
        )
    return row
