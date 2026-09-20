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
from sextant.domain.symbols import bare_descriptor, descriptor_slots, method_descriptor

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
    its receiver, 0 for a static sibling; `declared` is its own parameter count."""

    name: str
    descriptor: str
    receiver: int
    declared: int


def _masks(declared: int) -> int:
    """How many mask ints the compiler passes for `declared` parameters: one bit each."""
    return (declared + _MASK_BITS - 1) // _MASK_BITS


def _effective(workspace: Workspace) -> list[dict[str, Any]]:
    bridges = {
        bare_descriptor(str(row["symbol"])): str(row["bridge_of"])
        for row in workspace.query("bridge_declarations")
    }
    sites = workspace.query("call_sites")
    if not bridges:
        return list(sites)
    declared = {
        bare_descriptor(str(row["symbol"])): _is_static(row["modifiers"])
        for row in workspace.query("method_declarations")
    }
    # A bridge is called from many sites; its sibling is settled once.
    settled: dict[str, _Bridge | None] = {}
    rows: list[dict[str, Any]] = []
    for site in sites:
        name = site["name"]
        row = site
        if isinstance(name, str) and name.endswith(_DEFAULT_SUFFIX):
            owner, descriptor = str(site["owner"]), str(site["descriptor"])
            symbol = method_descriptor(owner, name, descriptor)
            function = bridges.get(symbol)
            if function is not None:
                if symbol not in settled:
                    settled[symbol] = _sibling(owner, descriptor, function, declared)
                bridge = settled[symbol]
                if bridge is not None:
                    row = _through_bridge(site, bridge) or site
        rows.append(row)
    return rows


def _is_static(modifiers: object) -> bool:
    """D00 §5a's `modifiers.static`, off the decoded column; a fact from a scanner that
    reported no modifiers at all (`None`) has not said the method is static."""
    return isinstance(modifiers, dict) and bool(modifiers.get("static"))


def _sibling(
    owner: str, descriptor: str, function: str, declared: dict[str, bool]
) -> _Bridge | None:
    """The sibling a bridge stands for, or None where it cannot be settled — neither
    candidate declared, or both (A5) — so its calls stay exactly as the bytecode said.

    The bridge's slots are `[receiver?] declared... mask... marker`, and `receiverSlots`
    is not published, so both readings are tried: with a receiver slot and without. For
    each, the one parameter count whose masks fill the remaining slots is the candidate,
    and the candidate exists when `owner#function(<those slots>)` is a declared method —
    the same arithmetic every call-to-callee join uses (`method_descriptor`). Its
    static-ness is read off that declaration, never inferred from which reading won.
    """
    slots, returned = descriptor_slots(descriptor)
    if not slots or slots[-1] != _MARKER:
        return None
    candidates: list[_Bridge] = []
    for receiver in (1, 0):
        available = len(slots) - receiver - 1
        for count in range(1, available + 1):
            if count + _masks(count) != available:
                continue
            if any(slot != _MASK_SLOT for slot in slots[receiver + count : -1]):
                break
            sibling = "(" + "".join(slots[receiver : receiver + count]) + ")" + returned
            static = declared.get(method_descriptor(owner, function, sibling))
            # An instance sibling is reached through the receiver slot, a static one has
            # none: a reading whose static-ness contradicts its slot layout is not the
            # sibling, even when a method of that descriptor happens to be declared.
            if static is not None and static == (receiver == 0):
                candidates.append(_Bridge(function, sibling, receiver, count))
            break
    if len(candidates) != 1:
        return None
    return candidates[0]


def _through_bridge(site: dict[str, Any], bridge: _Bridge) -> dict[str, Any] | None:
    """The call as the sibling sees it, or None where a mask is not an int literal — a
    wrong trimming is worse than the silence there is today (spec §3a). A copy: the raw
    row and its argument dicts belong to the cached `call_sites` list and are never
    written into."""
    arguments = list(site["arguments"])
    if len(arguments) != bridge.receiver + bridge.declared + _masks(bridge.declared) + 1:
        return None
    masks: list[int] = []
    for argument in arguments[bridge.receiver + bridge.declared : -1]:
        if argument.get("kind") != "int":
            return None
        masks.append(int(str(argument["value"])))
    # A fresh dict per defaulted slot: rows are shared by every engine, and one dict
    # standing in many rows would make a write into one a write into all of them.
    projected = [
        {"kind": "unresolved", "reason": "defaulted"}
        if (masks[index // _MASK_BITS] >> (index % _MASK_BITS)) & 1
        else arguments[bridge.receiver + index]
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
