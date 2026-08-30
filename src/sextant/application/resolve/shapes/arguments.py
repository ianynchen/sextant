"""Call-payload rooting (D02 §2h).

`single_call` (Task 9) and `fluent` (Task 11) both derive an endpoint from
a captured call-site argument rather than from a handler's declared
signature, and both need the very same answers: how a captured url splits
into peer and path and what that says about the row's own resolution, how
one D00 §5 argument roots at a payload descriptor, the one-hop D02 §2h
follow through a `call_wrappers` constructor or a `type_carriers`
supertype, and which declared type carries a PTR supertype. Shared here
rather than duplicated per style — and, since it depends on nothing in
Catalog orchestration, born in its own module rather than riding along
inside `contracts.py` (2E-prep design §1e).
"""

import json
import re
from dataclasses import dataclass
from typing import Any

from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.shapes.contracts import _payload_descriptor
from sextant.application.resolve.shapes.expansion import _Rules

_ABSOLUTE_URL = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://(?P<authority>[^/]*)(?P<path>/.*)?$")


def split_url(url: str) -> tuple[str | None, str]:
    """Checkpoint ruling CP-2: an absolute URL (a `scheme://` capture)
    splits generically into its authority — the peer — and its path
    component; a relative url string stays path-only, peer NULL, because the
    base address then lives in builder code no call-site literal ever names.
    """
    match = _ABSOLUTE_URL.match(url)
    if match is None:
        return None, url
    return match.group("authority"), match.group("path") or ""


def url_of(argument: dict[str, Any] | None) -> tuple[str | None, str | None, str]:
    """One row's `peer`, `path` and `resolution` from its url argument: a
    `string` argument's value is the template verbatim — placeholders and
    all, because the template is the wire identity — split into peer/path by
    CP-2's rule; anything else (never captured at all, or captured but the
    wrong kind — a `uri` step whose argument is a `lambda`, the uriBuilder
    form — or a positional slot the call site never filled) still derives
    the row, path NULL, resolution `unresolved`: D02 §2's "this method calls
    something over HTTP" is true and useful on its own."""
    if (
        argument is not None
        and argument.get("kind") == "string"
        and isinstance(argument.get("value"), str)
    ):
        peer, path = split_url(str(argument["value"]))
        return peer, path, "resolved"
    return None, None, "unresolved"


def _arg_at(arguments: list[dict[str, Any]], index: int | None) -> dict[str, Any] | None:
    """The argument at a call site's declared position, or None where the
    caller names no position at all (`body_arg`/`response_arg` are optional)
    or the real call site carries fewer arguments than the catalog expects —
    the varargs slot on `getForObject`/`exchange` is exactly this case (Task
    7 checkpoint): declared positions still read correctly, and the excess
    trailing argument is simply never addressed. Shared verbatim between
    `single_call` (a `methods` row's positional slot) and `fluent` (a step's
    own `argN` capture) — both read the same D00 §5 argument list the same
    way."""
    if index is None or index >= len(arguments):
        return None
    return arguments[index]


def _capture_resolved(declared: bool, argument: dict[str, Any] | None) -> bool:
    """Whether a DECLARED capture (checkpoint ruling I1) read something the
    scanner could resolve.

    A capture nothing ever declares — `put` names no `response_arg`, a chain
    that never reaches a step naming `response` — never fails: it never
    claimed a payload, so its absence is a genuine no-body/no-response, not a
    read failure. A declared capture with nothing at that position, or whose
    own kind is the compiler's `unresolved` (D00 §5: "anything else... a
    first-class honest answer, never an omission"), fails — and per I1, that
    drops the *row's* own `resolution`, even though the payload *column*
    itself stays NULL either way: NULL alone cannot say which case it was, so
    the row is what disambiguates "no payload" from "could not read it" (D01
    §3, amended).

    `declared` is each engine's own form of the same question: `single_call`
    asks whether its `methods` row named a position at all (`body_arg` is
    optional); `fluent` asks whether the chain ever reached a step naming
    the capture (a chain declares one by *reaching* it, not by a positional
    slot) — both collapse to this one bool before reaching here."""
    if not declared:
        return True
    return argument is not None and argument.get("kind") != "unresolved"


def channel_of(argument: dict[str, Any] | None) -> tuple[None, str | None, str]:
    """`url_of`'s counterpart for a DESTINATION capture (D02 §2's
    `channel_arg`) — a topic, a queue, a subscription. The grammar makes
    `channel_arg` an alias of `url_arg`, but the reader must not be shared:
    a destination is an opaque expression the broker resolves, not a URL
    with an authority to split off. SQS's canonical destination is a full
    queue URL (`https://sqs.us-east-1.amazonaws.com/123456789012/my-queue`),
    and `url_of` would split it into a fabricated `peer` plus a truncated
    `path` — recording a destination that could never be sent to, and
    asserting a peer no messaging fact ever carried. So the whole literal is
    the `path`, verbatim, and `peer` is unconditionally None (D02 §3:
    messaging peers stay NULL).

    Anything the scanner could not read as a string literal is the same
    honest answer `url_of` gives: path NULL, `unresolved` — the call was
    made, only its destination is unread."""
    if (
        argument is not None
        and argument.get("kind") == "string"
        and isinstance(argument.get("value"), str)
    ):
        return None, str(argument["value"]), "resolved"
    return None, None, "unresolved"


@dataclass(frozen=True)
class CarrierRules:
    """The catalog data `argument_descriptor` needs beyond the shared
    `_Rules` (D02 §2h): which `instance` types are PTR-shaped carriers whose
    own declared supertype names the payload, and which constructor argument
    a `call_wrappers` type's real payload sits at. Every dotted name already
    converted — the same binding-seam discipline `_Rules` itself keeps, so no
    rule below has to remember which notation it is holding."""

    rules: _Rules
    enums: set[str]
    type_carriers: tuple[str, ...]
    call_wrappers: dict[str, int]


@dataclass(frozen=True)
class CallFacts:
    """The workspace facts `argument_descriptor` needs beyond the argument
    itself, scoped to the one call site whose arguments are being described:
    every declared type's own supertype reference (D00 §5a's PTR carrier,
    keyed by its bare descriptor — never the module-prefixed identity a
    symbol fact's own `symbol` column holds), and the call sites sharing this
    call's own caller — the pool the `call_wrappers` one-hop searches for a
    matching `<init>`. Never call sites from a different caller: `receiver`/
    `result` ids are meaningless across methods (D00 §5), so the search must
    not reach outside this caller's own sites.

    `referenced` is the same accumulator `_described` already appends every
    object it meets to — threaded through here so a payload this pass roots
    is collected exactly like every other payload root, for the shape queue
    that expands it.
    """

    supertypes: dict[str, dict[str, Any]]
    caller_call_sites: list[dict[str, Any]]
    referenced: list[str]


def supertypes_of(workspace: Workspace) -> dict[str, dict[str, Any]]:
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


def argument_descriptor(
    argument: dict[str, Any] | None,
    workspace_types: CallFacts,
    catalog_rules: CarrierRules,
) -> str | None:
    """The wire descriptor a D00 §5 call argument names, or None when the
    argument carries no resolvable payload — an `unresolved` slot, a `null`,
    a `lambda`, or an `instance`/`class` this catalog's rules say nothing
    special about beyond its own type. Shared with Task 11's `fluent`
    engine, which resolves the very same argument grammar off a captured
    step argument rather than a `methods` row's positional slot.

    - a `class` argument roots at the object (or known-type) descriptor for
      its symbol — a class literal such as `OrderView.class`;
    - a literal argument (`string`, `int`, `long`, `boolean`) roots at the
      scalar its own kind names: a bare `String` body is a real contract,
      and NULL keeps exactly one meaning (D01 §3, amended);
    - an `instance` argument whose type's own declared supertype names a
      `type_carriers` entry roots at that supertype's own payload argument
      (D02 §2h's PTR follow) — a full D00 §5a type reference, fed to
      `_described` exactly as a field reference would be, so a PTR payload
      that is itself a collection or an envelope resolves exactly like one;
    - an `instance` of a declared `call_wrappers` type follows exactly one
      hop, to the linked constructor call site's `payload_ctor_arg` — never
      further, and never where no `call_wrappers` entry matches;
    - a bare `instance` roots at the object (or known-type) descriptor for
      its own concrete type;
    - anything else resolves to no payload — the row still derives (D02 §2's
      `single_call` rule), only the descriptor is absent.
    """
    reference = _reference_of(argument, workspace_types, catalog_rules)
    return _payload_descriptor(
        reference, catalog_rules.rules, catalog_rules.enums, workspace_types.referenced
    )


def _reference_of(
    argument: dict[str, Any] | None,
    workspace_types: CallFacts,
    catalog_rules: CarrierRules,
) -> dict[str, Any] | None:
    """The D00 §5a type reference one call argument names, before wrapper
    unwrapping — `argument_descriptor`'s own rules, split out so
    `argument_descriptor` itself stays a one-line call into the shared
    `_payload_descriptor` projection."""
    if argument is None:
        return None
    kind = argument.get("kind")
    if kind == "class":
        symbol = argument.get("symbol")
        return None if symbol is None else _bare_reference(str(symbol))
    if kind in _LITERAL_WIRE_TYPES:
        return _literal_reference(str(kind))
    if kind != "instance":
        # `unresolved`, `null`, `lambda`: none of these names a payload type
        # at all.
        return None
    symbol = argument.get("symbol")
    if symbol is None:
        return None
    symbol = str(symbol)
    supertype = workspace_types.supertypes.get(symbol)
    if supertype is not None and str(supertype.get("symbol")) in catalog_rules.type_carriers:
        carried = supertype.get("arguments") or []
        # A carrier declared with nothing at its own payload position — the
        # same "declared envelope, nothing visible inside it" case §2a's
        # `root_type` already names — is no payload, not a crash.
        return carried[0] if carried else None
    payload_ctor_arg = catalog_rules.call_wrappers.get(symbol)
    if payload_ctor_arg is not None:
        constructor = _linked_constructor(symbol, argument.get("source"), workspace_types)
        if constructor is None:
            return None
        ctor_arguments = constructor.get("arguments") or []
        if payload_ctor_arg >= len(ctor_arguments):
            return None
        # Exactly one hop (D02 §2h: "the engine follows exactly that one hop
        # and stops"): the ctor's own payload argument is read as a terminal
        # reference — never through `_reference_of` again, which would let a
        # ctor argument that happens to itself be a `type_carriers` or
        # `call_wrappers` instance chain into a second hop the catalog never
        # asked for.
        return _terminal_reference(ctor_arguments[payload_ctor_arg])
    return _bare_reference(symbol)


def _terminal_reference(argument: dict[str, Any] | None) -> dict[str, Any] | None:
    """The bare reference a `call_wrappers` one-hop stops on: the ctor
    argument's own type, read verbatim from a `class` or `instance` kind,
    with no further D02 §2h resolution — the one hop is the whole rule."""
    if argument is None or argument.get("kind") not in ("class", "instance"):
        return None
    symbol = argument.get("symbol")
    return None if symbol is None else _bare_reference(str(symbol))


# D00 §5's literal argument kinds, each projected into the one D00 §5b wire
# type it can be. The kind *is* the answer: a literal carries its own type,
# so this is the one payload projection needing neither a symbol nor a
# catalog's knowledge of one — `int` and `long` are the fact grammar's own
# names for the two integer widths, and `wire_format` is what keeps them
# apart on the wire.
_LITERAL_WIRE_TYPES: dict[str, tuple[str, str]] = {
    "string": ("string", ""),
    "int": ("integer", "int32"),
    "long": ("integer", "int64"),
    "boolean": ("boolean", ""),
}

# Descriptor grammar, not language knowledge (D00 §5a): an array symbol is
# its element's symbol with this suffix. Parsed here — and only here —
# because a `class`/`instance` argument carries a bare symbol and nothing
# else, so the element reference a scanned field already arrives with has to
# be rebuilt from the one thing the argument does carry.
_ARRAY_SUFFIX = "[]"


def _literal_reference(kind: str) -> dict[str, Any]:
    """A D00 §5a type reference synthesised from a literal argument's own
    kind. `symbol` is empty because a literal names no type — nothing keys a
    `known_types` entry or an enum on it, and nothing may root a shape at
    it. `nullable: False` for the same reason a primitive's own reference is
    not nullable: a literal is a value, and an absent one is D00 §5's `null`
    kind instead."""
    wire_type, wire_format = _LITERAL_WIRE_TYPES[kind]
    return {
        "symbol": "",
        "arguments": [],
        "wire_type": wire_type,
        "wire_format": wire_format,
        "nullable": False,
    }


def _bare_reference(symbol: str) -> dict[str, Any]:
    """A D00 §5a type reference synthesised from a bare symbol — a `class`
    literal or a constructed `instance` carries only its type, never the
    `wire_type`/`nullable` projection a typed signature reference does.
    `wire_type: object` is not a guess: both argument kinds name a concrete
    reference type. `nullable: True` is the same default a language whose
    every reference type permits null gives a `resolved` field absent any
    narrower answer (D00 §5a) — `_described` still overrides both from
    `known_types` or the enum set where the catalog names one, which is how
    a scalar type the serialiser flattens (and the `Void` that reaches no
    wire at all) stops being described as an object here.

    An array symbol keeps its element as its single type argument, exactly
    as a scanned `String[]` field's own reference does (D00 §5a): without
    it, `OrderView[].class` and `String[].class` are the same `array`
    holding nothing, which is the one thing `item` exists to prevent."""
    if symbol.endswith(_ARRAY_SUFFIX):
        return {
            "symbol": symbol,
            "arguments": [_bare_reference(symbol[: -len(_ARRAY_SUFFIX)])],
            "wire_type": "array",
            "wire_format": "",
            "nullable": True,
        }
    return {
        "symbol": symbol,
        "arguments": [],
        "wire_type": "object",
        "wire_format": "",
        "nullable": True,
    }


def _linked_constructor(
    owner_symbol: str, source: int | None, workspace_types: CallFacts
) -> dict[str, Any] | None:
    """D02 §2h's join: the `<init>` call site, within this same caller, whose
    `receiver` is the constructed value's own id — the argument's `source`.
    Never a search by proximity: the id is what keeps two constructors in one
    method apart."""
    if source is None:
        return None
    return next(
        (
            site
            for site in workspace_types.caller_call_sites
            if site.get("name") == "<init>"
            and site.get("owner") == owner_symbol
            and site.get("receiver") == source
        ),
        None,
    )
