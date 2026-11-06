"""Effective call sites (spec 2026-09-19 §3): the `call_sites` facts as every ENGINE reads
them, with four projections applied once per load — a compiler-emitted `$default` bridge call
re-targeted to the function it stands for (§3a, T4), a class-compiled lambda argument
read as the `lambda` it is (§3b, T5), a boxed constant read as the constant the source
wrote, and a static call naming a type read as that type's construction (spec 2026-11-06
§3b). The first two join on shared fields the extractor publishes on the declaration it
scanned (`bridge_of`, `lambda_body`); the third on the boxing call's own site, whose
vocabulary is the compiler's (JLS 5.1.7), not a library's; the fourth on the types the
workspace holds. Nothing here names a language or a framework.

`call_sites` itself is untouched: the exported bundle, `format` and every raw-fact test
keep the bytecode's own statement. The graph/trace readers do NOT — `call_edges` and
`return_flow` read this projection (spec 2026-09-22 §1a, I-3), because a hop recorded
against a bridge names a body no caller reads. This module is the ONE projection point
(F10) — a reader that wants what the engines see calls `effective_call_sites`, never
`query("call_sites")` plus its own rewrite.
"""

from dataclasses import dataclass
from typing import Any

from sextant.application.ports.workspace import Workspace
from sextant.domain.symbols import (
    bare_descriptor,
    descriptor_slots,
    is_type_descriptor,
    member_field,
    member_type,
    method_descriptor,
    owner_of,
    returned_type,
)

# The name suffix a compiler-emitted default-argument bridge carries (`<fn>$default`,
# OI-81) and the marker type its last slot always is. Neither identifies a bridge on its
# own — only the extractor's `bridge_of` does — but a site whose name lacks the suffix is
# never one, and that test is what keeps the projection from hashing every site's symbol.
_DEFAULT_SUFFIX = "$default"
_MARKER = "Ljava/lang/Object;"
_MASK_SLOT = "I"
_MASK_BITS = 32

# The eight calls javac inserts to box a primitive (JLS 5.1.7, measured CP-55 row 22): each
# wrapper's `valueOf(<prim>)`, keyed by its descriptor — the owner is not repeated, because
# a boxing method returns its own owner — with the argument kinds that primitive's constant
# is published as. `byte`, `short` and `char` constants are `int` (constant instructions
# push an int), and `float`/`double` have no constant kind in D00 §5 yet, so theirs is
# empty and those calls are left as they are.
_BOXING_NAME = "valueOf"
# A construction's name at a call site (D00 §5), which a static call naming a type is read
# as, and the invoke kinds before and after.
_INIT = "<init>"
_STATIC = "static"
_SPECIAL = "special"
_BOXING: dict[str, tuple[str, ...]] = {
    "(Z)Ljava/lang/Boolean;": ("boolean",),
    "(B)Ljava/lang/Byte;": ("int",),
    "(C)Ljava/lang/Character;": ("int",),
    "(S)Ljava/lang/Short;": ("int",),
    "(I)Ljava/lang/Integer;": ("int",),
    "(J)Ljava/lang/Long;": ("long",),
    "(F)Ljava/lang/Float;": (),
    "(D)Ljava/lang/Double;": (),
}


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
    boxed = _boxed_constants(sites)
    classes = _class_calls(workspace, sites)
    if not bridges and not bodies and not boxed and not classes:
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
        if (
            bridges
            and isinstance(name, str)
            and name.endswith(_DEFAULT_SUFFIX)
            and site["owner"] is not None
        ):
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
        if boxed:
            row = _with_unboxed(row, boxed)
        if classes:
            row = _as_construction(row, classes)
        rows.append(row)
    return rows


def _class_calls(workspace: Workspace, sites: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    """Each static call `(owner, name)` whose name is a TYPE of the owner's module, to that
    type (spec 2026-11-06 §3b): `from app.a import Session; Session()` is written as the
    static call `app/a#Session`, because the file that makes it cannot see that `Session` is
    a class, and calling a class constructs it. A type is one the workspace declares or holds
    a header for. Empty where no static call names one, which is every JVM module: a JVM
    static call's owner is a class, and no type is named after a member of a class's own
    package path (`member_type`)."""
    named: dict[tuple[str, str], str] = {}
    for site in sites:
        owner, name = site["owner"], site["name"]
        if site["invoke_kind"] != _STATIC or owner is None or name is None:
            continue
        candidate = member_type(str(owner), str(name))
        if candidate is not None:
            named[(str(owner), str(name))] = candidate
    if not named:
        return {}
    declared = {bare_descriptor(str(row["symbol"])) for row in workspace.query("declared_symbols")}
    types = {symbol for symbol in declared if is_type_descriptor(symbol)} | {
        bare_descriptor(str(row["symbol"])) for row in workspace.query("type_headers")
    }
    # A name the module writes, or declares as a field, is a variable, whatever it held
    # first: `Session = Client` after `class Session` makes `Session()` a call of its value.
    variables = declared | {
        bare_descriptor(str(row["field"]))
        for row in workspace.query("field_writes")
        if row["field"] is not None
    }
    return {
        key: type_
        for key, type_ in named.items()
        if type_ in types and member_field(*key) not in variables
    }


def _as_construction(row: dict[str, Any], classes: dict[tuple[str, str], str]) -> dict[str, Any]:
    """`row` read as the construction it is where it is a static call naming a type
    (`_class_calls`): `special` `<init>` on that type, its `result` the constructed object,
    as `resolve/values.py` reads a construction with a result. `row` itself otherwise."""
    if row["invoke_kind"] != _STATIC or row["owner"] is None:
        return row
    constructed = classes.get((str(row["owner"]), str(row["name"])))
    if constructed is None:
        return row
    projected = dict(row)
    projected["owner"] = constructed
    projected["name"] = _INIT
    projected["invoke_kind"] = _SPECIAL
    return projected


def _boxed_constants(sites: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    """Each boxing call whose one argument is a constant of its primitive's kind, keyed by
    (caller, result) — value ids are per method — to that constant."""
    boxed: dict[tuple[str, int], dict[str, Any]] = {}
    for site in sites:
        if site["name"] != _BOXING_NAME or site["result"] is None:
            continue
        descriptor = str(site["descriptor"])
        kinds = _BOXING.get(descriptor)
        arguments = site["arguments"]
        # A boxing method is a static factory on the wrapper it returns.
        if (
            kinds
            and site["owner"] == returned_type(descriptor)
            and len(arguments) == 1
            and arguments[0].get("kind") in kinds
        ):
            boxed[(str(site["caller"]), int(site["result"]))] = arguments[0]
    return boxed


def _with_unboxed(
    row: dict[str, Any], boxed: dict[tuple[str, int], dict[str, Any]]
) -> dict[str, Any]:
    """`row` with each argument produced by a boxing call read as that call's constant,
    or `row` itself when none is — the copy-on-change discipline `_with_lambdas` keeps."""
    caller = str(row["caller"])
    arguments = [_as_constant(argument, caller, boxed) for argument in row["arguments"]]
    if all(after is before for after, before in zip(arguments, row["arguments"])):
        return row
    projected = dict(row)
    projected["arguments"] = arguments
    return projected


def _as_constant(
    argument: dict[str, Any], caller: str, boxed: dict[tuple[str, int], dict[str, Any]]
) -> dict[str, Any]:
    """The argument as the engines read it: an `unresolved` whose `source` is a boxing
    call's result becomes the constant that call was handed; an `array`'s elements are
    read the same way (a boxed varargs is an array of such results). Anything else is
    returned as it is, the same dict."""
    if argument.get("kind") == "array" and isinstance(argument.get("elements"), list):
        elements = [_as_constant(element, caller, boxed) for element in argument["elements"]]
        if all(after is before for after, before in zip(elements, argument["elements"])):
            return argument
        return {**argument, "elements": elements}
    source = argument.get("source")
    if argument.get("kind") != "unresolved" or source is None:
        return argument
    constant = boxed.get((caller, int(source)))
    return argument if constant is None else dict(constant)


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
