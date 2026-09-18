"""Call-payload rooting (D02 §2h).

`single_call` (Task 9) and `fluent` (Task 11) both derive an endpoint from
a captured call-site argument rather than from a handler's declared
signature, and both need the very same answers: how a captured url splits
into peer and path and what that says about the row's own resolution, how
one D00 §5 argument roots at a payload descriptor, the one-hop D02 §2h
follow through a `call_wrappers` constructor or a `type_carriers`
supertype, which declared type carries a PTR supertype, and — 2F design
§4 — how an address argument that is a FIELD read rather than a literal
climbs the field ladder to the configuration expression behind it. Shared here
rather than duplicated per style — and, since it depends on nothing in
Catalog orchestration, born in its own module rather than riding along
inside `contracts.py` (2E-prep design §1e).
"""

import json
import re
from dataclasses import dataclass
from typing import Any, cast

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.shapes.contracts import _payload_descriptor
from sextant.application.resolve.shapes.expansion import _Rules
from sextant.application.resolve.shapes.rooting import _catalog_symbol
from sextant.domain.config_keys import normalize_key
from sextant.domain.symbols import bare_descriptor, member_name, owner_of

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


def parameter_index(argument: dict[str, Any] | None) -> int | None:
    """The caller parameter one argument names, BARE (D00 §5's `parameter`
    kind) — or None for anything else.

    The one primitive behind every pass that resolves a value living in
    whatever called this method: `parse_binding`'s parse join asks whether an
    argument is a KNOWN index, `single_call`'s argument-type identity asks
    WHICH index it is, and both are this one read. Bare only, and that
    narrowness is the soundness rule rather than a limitation to widen: a
    value merged from a parameter and anything else reads `unresolved` (Phase
    2G checkpoint), so a conditional producer names no parameter here and
    resolves to nothing — which is the honest answer, since either branch
    could have produced it."""
    if argument is None or argument.get("kind") != _PARAMETER_KIND:
        return None
    value = argument.get("value")
    return value if isinstance(value, int) else None


# D00 §5's argument kind naming a value the caller was handed. Spelled once
# here because two passes now compare against it.
_PARAMETER_KIND = "parameter"


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


def _capture_resolved(
    declared: bool, argument: dict[str, Any] | None, resolved_to: str | None = None
) -> bool:
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
    slot) — both collapse to this one bool before reaching here.

    `field` (D00 §5, 2F) counts as unread here exactly as `unresolved` does
    (Task 6 checkpoint F-2): a field argument names the field, never the
    value behind it, and only the ladder below can turn one into an answer.
    Where the ladder fires, the engine has already replaced the argument
    with the string literal its expression names, so a resolved field never
    reaches this test as a `field` at all; where it does not, a payload
    column would stay NULL on a row still claiming `resolved` — the one
    thing D01 §3's amended disambiguation exists to prevent.

    **`resolved_to` is what the capture actually produced, and it is the whole
    of the exception** (W43's review, after `OI-77`). The paragraph above
    turns on "the payload column stays NULL either way, so the ROW is the only
    place to disambiguate". Once a body capture read from a `parameter` fills
    that column with a real descriptor, the premise is gone: the column says
    what was read, and a row still answering `unresolved` claims a read
    failure that did not happen. The estate proved it inconsistent in one
    fixture — `spring-ws-template` reads a parameter payload through
    `path_from_argument_type` and answers `resolved`, while every other
    outbound catalog answered `unresolved` for the identical fact.

    An ADDRESS capture is untouched — and by a different mechanism, which is worth
    saying because the obvious guess is wrong. This function has four callers and
    every one of them is a body or a response; no address capture ever reaches it.
    A destination read from a parameter is `unresolved` because `url_of` and
    `channel_of` resolve only a `kind: "string"` argument, which is a rule of their
    own. `_UNREAD_KINDS` is consulted here and nowhere else, so it is now, in fact,
    a set about body and response captures."""
    if not declared:
        return True
    if resolved_to is not None:
        return True
    return argument is not None and argument.get("kind") not in _UNREAD_KINDS


# The D00 §5 argument kinds that name no value a capture could have read:
# `concat` joins them (W4): it carries a TEMPLATE with a hole, not a
# value, so a capture cannot read one. Leaving it out let a body argument
# built by concatenation flip a row to `resolved` over a NULL payload —
# which is the exact thing `_capture_resolved` exists to prevent. Every
# kind added before it carried this rule explicitly in D00: an engine
# that does not consult the kind treats it as it always treated
# `unresolved`.
# the compiler's own honest read failure, a field read whose value lives
# wherever the field was assigned (2F design §4's ladder is the only thing
# that can answer it), and a parameter, whose value lives in whatever called
# this method (2G). `parameter` joined this set the day the kind existed: it
# is the same fact `unresolved` used to state less precisely.
#
# **Read only by `_capture_resolved`, and therefore only about BODY and RESPONSE
# captures.** An address capture never consults this set: `url_of`/`channel_of`
# resolve a `kind: "string"` argument and nothing else, which is their own rule.
# A body capture reading a parameter no longer fails, and that is not a change to
# this set either — it is `_capture_resolved`'s `resolved_to`, which asks what the
# capture PRODUCED rather than what kind it read.
_UNREAD_KINDS = ("unresolved", "field", "parameter", "concat")


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


def _array_elements(argument: dict[str, Any] | None) -> list[dict[str, Any]] | None:
    """The element arguments an `array`-kind slot carries (extractor
    capability 9.15's `elements`), or None for every other argument — the
    signal "this slot is not an array, read it as itself".

    ONE argument that happens to be an array, never N positional ones: the
    extractor deliberately does not unpack a varargs array, because unpacking
    would renumber every slot after it and make the call's own arity
    unreadable (`domain/facts.py`'s `array` kind). So the reading has to
    happen here, at the consumer, and this is the one place that decides a
    slot is one.

    **The `array` kind is the whole conjunct, and it is load-bearing.** An
    array the extractor could not read end to end never reaches this kind at
    all — it stays a bare `unresolved` (9.15's five rejection rules), so an
    `elements` list is always the array's COMPLETE contents and never a
    partial one. Reading `elements` off anything else would be reading a
    completeness claim the extractor did not make; an argument that is not an
    `array` therefore reads as itself, which is exactly what it is. The empty
    list is a real answer here rather than a missing one — a zero-length
    varargs call is a call — and stays distinct from the None above.
    """
    if argument is None or argument.get("kind") != "array":
        return None
    elements = argument.get("elements")
    return elements if isinstance(elements, list) else []


def _expanded_arguments(arguments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """`arguments` with every `array` slot replaced, in place, by its own
    elements — the shape a reader that wants VALUES rather than SLOTS needs.

    One level only, and that is the extractor's own bound rather than a
    choice made here: 9.15 never expands a nested array's elements, so an
    element that is itself an `array` carries no `elements` of its own and
    reads as the unreadable value it is.
    """
    expanded: list[dict[str, Any]] = []
    for argument in arguments:
        elements = _array_elements(argument)
        expanded.extend([argument] if elements is None else elements)
    return expanded


def channels_of(argument: dict[str, Any] | None) -> list[tuple[None, str | None, str]]:
    """`channel_of` over a slot that may hold a whole ARRAY of destinations
    (2O Task 13) — a varargs registration call, where one argument names
    several destinations at once.

    `WebSocketHandlerRegistry.addHandler(handler, String... paths)` is the
    shipped case: the paths collapse into ONE `array` argument for a
    single-path call as much as for a multi-path one (measured, descriptor
    sweep R6, spring-websocket 6.1.6), so `channel_of` alone — which resolves
    a `string` kind and nothing else — answered `unresolved` for every call
    anyone could write. Each registered path is its own destination and so
    its own row, the way each `urlPatterns` entry already is.

    A slot that is NOT an array reads exactly as it did before: one tuple,
    `channel_of`'s own verbatim answer. An array reads through
    `_all_string_channels`, so the partially-readable case degrades the same
    way `all_strings`' does — one tuple per readable element, plus one
    trailing unresolved tuple where any element could not be read, never one
    per failure.
    """
    elements = _array_elements(argument)
    if elements is None:
        return [channel_of(argument)]
    return _all_string_channels(elements)


def peer_of(argument: dict[str, Any] | None) -> tuple[str | None, str]:
    """`url_of`'s counterpart for an address that is NOT the wire identity.

    Some protocols name the operation somewhere other than the address: the
    identity is read off the payload or the declaration, and the address the
    call was sent to says only WHICH deployment answered it. For those, the
    address contributes exactly one column — `peer`, D01 §3's "outbound target
    hint … that the system tier later resolves against `participants`" — and
    the `path` it would otherwise have carried belongs to the identity
    instead.

    WHOLE, never split, and for `channel_of`'s reason restated: an address
    fed from configuration arrives as a `${...}` expression, which CP-2's
    split cannot touch at all (the authority half of an expression is not an
    authority), so splitting would answer one of the two shapes and silently
    drop the other. Whole also keeps two deployments on one host apart, which
    is the distinction a peer exists to draw. `resolved_peers` already reads a
    placeholder out of `peer` exactly as it does out of `path`, so an
    expression recorded here still resolves per environment.

    Anything the scanner could not read as a string literal is the same
    honest answer every other reader here gives: peer NULL, `unresolved`."""
    if (
        argument is not None
        and argument.get("kind") == "string"
        and isinstance(argument.get("value"), str)
    ):
        return str(argument["value"]), "resolved"
    return None, "unresolved"


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
    # The CALLER's own declared parameters, as D00 §5a type references in declaration
    # order (`OI-77`, W43's review). A payload handed straight through — `announce(OrderView
    # order)` calling `convertAndSend(dest, order)` — arrives as `{"kind": "parameter",
    # "value": 0}`, which names no type of its own; the type is stated in the caller's own
    # signature, and this is that signature. Empty where the caller is not a declaration
    # this module scanned, which is the same silence every other unread argument gives.
    caller_parameters: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class FieldSources:
    """The catalog data the field ladder reads (2F design §4's `field_sources`
    block): which annotation carries a placeholder expression on a field or a
    constructor parameter, which annotation binds a whole type to a
    configuration prefix, which of THAT annotation's own arguments spells the
    prefix, and the accessor prefixes a property getter is written with. Every
    dotted type name already converted to the symbol grammar — the same
    binding-seam discipline `CarrierRules` keeps, so no rung has to remember
    which notation it is holding."""

    value_annotation: str
    properties_annotation: str
    prefix_from: str
    getter_prefixes: tuple[str, ...]


@dataclass(frozen=True)
class FieldFacts:
    """The workspace facts the field ladder joins through, read ONCE per
    engine run (the `_rules_of`/`_enum_symbols` precedent) rather than once
    per address argument — and the four that depend on no catalog once per
    load (`FieldDeclarations`):

    - `value_expressions` — the expression the `value_annotation` carries on
      one field (rung 1);
    - `written_from_parameter` — D00 §5's `field_write`, the constructor
      parameter index a field was assigned straight from (rung 2);
    - `constructor_parameters` — each type's constructors' own parameter
      lists, where a parameter's annotations live and nowhere else (Task 6
      checkpoint (3): the `annotations` view never carries them);
    - `prefixes` — the configuration prefix the `properties_annotation` binds
      a type to (rung 3);
    - `declared_fields` — each type's own field names, what a getter relaxed-
      binds against so the expression carries the property's DECLARED
      spelling rather than the accessor's;
    - `declared_parameters` — every declared constructor's and method's own
      parameter list, keyed by the FULL symbol (unlike every other key here),
      because that is what a call site's `caller` holds: rung 2's terminal
      read, reached directly by an address argument that is the enclosing
      declaration's own parameter rather than a field written from one.

    Every key is a BARE descriptor (Task 6 checkpoint (2)'s join note): a
    `field` argument's own `symbol` and a `field_write`'s own `field` carry no
    module coordinates, while a symbol fact and an annotation `target` do, and
    only the descriptor is ever compared (D00 §5a)."""

    sources: FieldSources
    value_expressions: dict[str, str]
    written_from_parameter: dict[str, int]
    constructor_parameters: dict[str, list[list[dict[str, Any]]]]
    prefixes: dict[str, str]
    declared_fields: dict[str, list[str]]
    declared_parameters: dict[str, list[dict[str, Any]]]


# The annotation argument a single-valued annotation's own value arrives
# under (D00 §5's annotation `args` map). Not a framework name and not a
# catalog concern: it is the fact grammar's own spelling for "the argument
# written without naming it", which is how every `@Value("${…}")`-shaped
# expression reaches the facts.
_ANNOTATION_VALUE_ARG = "value"

# D01's own placeholder form — the expression an endpoint row carries until
# the per-environment join resolves it (`resolved_peers`, whose SQL matches on
# exactly this delimiter pair). Rungs 1 and 2 return an expression the facts
# already spell; rung 3 SYNTHESISES one from a prefix and a property name, so
# it is the one rung that has to write the delimiters itself.
#
# Written here rather than read from a `config_model` for the same reason the
# relaxed-binding rule below is applied unconditionally: `placeholders` and
# `key_matching` are declared on the framework FAMILY's base catalog, and a
# client catalog — the only thing this ladder is handed — cannot see them.
# `resolved_peers`' own SQL already hard-codes this same pair, so one form is
# assumed in exactly two places rather than one; a non-`${}` ecosystem has to
# thread the pair onto `field_sources` and into that query together.
_PLACEHOLDER = ("${", "}")


def carries_expression(text: str) -> bool:
    """Whether an address carries a D01 placeholder — an OPEN delimiter with
    a matching CLOSE after it, `resolve/config.py`'s own reading (an
    unterminated `${` is literal text there too).

    What it decides: an address containing one is unsplittable, whatever else
    it looks like (2F design §4). `https://${billing.host}/orders` matches
    CP-2's absolute-URL shape perfectly and splitting it would write
    `${billing.host}` into the `peer` column as if it were an authority —
    a peer no environment ever named, and one the per-environment join reads
    only from `path`/`peer` as WHOLE expressions. So the check runs BEFORE the
    split, never after."""
    open_, close = _PLACEHOLDER
    start = text.find(open_)
    return start != -1 and close in text[start + len(open_) :]


@dataclass(frozen=True)
class FieldDeclarations:
    """The four `FieldFacts` maps that depend on no catalog — `written_from_parameter`,
    `constructor_parameters`, `declared_parameters`, `declared_fields`, each as
    `FieldFacts` documents it — folded once per load (`Workspace.once`) and shared by
    every `FieldFacts` built after: read, never written into. The two maps that read
    the catalog's own annotation names stay with `field_facts`."""

    written_from_parameter: dict[str, int]
    constructor_parameters: dict[str, list[list[dict[str, Any]]]]
    declared_parameters: dict[str, list[dict[str, Any]]]
    declared_fields: dict[str, list[str]]


def field_declarations(workspace: Workspace) -> FieldDeclarations:
    """`FieldDeclarations` over `field_writes`, `constructor_declarations`,
    `method_declarations` and `fields` — the builder `Workspace.once` keys on."""
    written_from_parameter: dict[str, int] = {}
    for row in workspace.query("field_writes"):
        # First write wins, in the query's own (field, from_parameter) order:
        # two constructors assigning one field from different positions are
        # two candidate answers, and a deterministic first is the only honest
        # pick without a fact linking a write to its constructor.
        written_from_parameter.setdefault(str(row["field"]), int(str(row["from_parameter"])))
    constructor_parameters: dict[str, list[list[dict[str, Any]]]] = {}
    declared_parameters: dict[str, list[dict[str, Any]]] = {}
    for row in workspace.query("constructor_declarations"):
        enclosing = row["enclosing"]
        if enclosing is None:
            continue
        signature = json.loads(str(row["signature"] or "{}")) or {}
        parameters = list(signature.get("parameters") or [])
        constructor_parameters.setdefault(bare_descriptor(str(enclosing)), []).append(parameters)
        declared_parameters[str(row["symbol"])] = parameters
    # Methods as well as constructors: a template configured from a
    # `@Value`-annotated SETTER parameter is the same declaration shape as one
    # configured from a constructor parameter, and which construct holds it is
    # the framework's convention rather than a fact about the expression.
    for row in workspace.query("method_declarations"):
        signature = cast(dict[str, Any], row["signature"] or {})
        declared_parameters[str(row["symbol"])] = list(signature.get("parameters") or [])
    declared_fields: dict[str, list[str]] = {}
    for row in workspace.query("fields"):
        descriptor = bare_descriptor(str(row["symbol"]))
        owner = owner_of(descriptor)
        if owner is None:
            continue
        declared_fields.setdefault(owner, []).append(member_name(descriptor))
    return FieldDeclarations(
        written_from_parameter=written_from_parameter,
        constructor_parameters=constructor_parameters,
        declared_parameters=declared_parameters,
        declared_fields=declared_fields,
    )


def field_facts(workspace: Workspace, catalog: Catalog) -> FieldFacts | None:
    """The field ladder's own facts for one catalog, or None where the
    catalog declares no `field_sources` block at all — the gate: a catalog
    that never names which annotations carry configuration never consults the
    ladder, and every row it derives is exactly what it was before 2F.

    Absence is the ONLY gate (fix round 1): a `field_sources: {}` that is
    present but empty is a block that declares nothing it must declare, and it
    is refused below exactly as any other malformed one is. `if not declared`
    would have read the two as the same thing and turned a broken file into a
    silent no-op — which is the one outcome `ports/catalogs.py`'s own
    discipline exists to prevent."""
    declared = catalog.matches.get("field_sources")
    if declared is None:
        return None
    sources = _field_sources(declared, catalog)
    value_expressions: dict[str, str] = {}
    prefixes: dict[str, str] = {}
    for row in workspace.query("annotations"):
        annotation = str(row["annotation"])
        if annotation not in (sources.value_annotation, sources.properties_annotation):
            continue
        args = json.loads(str(row["args"] or "{}"))
        key = (
            _ANNOTATION_VALUE_ARG if annotation == sources.value_annotation else sources.prefix_from
        )
        value = args.get(key)
        if not isinstance(value, str):
            continue
        target = bare_descriptor(str(row["target"]))
        if annotation == sources.value_annotation:
            value_expressions.setdefault(target, value)
        else:
            prefixes.setdefault(target, value)
    declarations = workspace.once(field_declarations)
    return FieldFacts(
        sources=sources,
        value_expressions=value_expressions,
        written_from_parameter=declarations.written_from_parameter,
        constructor_parameters=declarations.constructor_parameters,
        prefixes=prefixes,
        declared_fields=declarations.declared_fields,
        declared_parameters=declarations.declared_parameters,
    )


def declared_parameters_of(workspace: Workspace) -> dict[str, tuple[dict[str, Any], ...]]:
    """Every declared method's and constructor's own parameter type references, keyed by
    FULL symbol (`OI-77`).

    The same two queries `field_facts` reads for its own `declared_parameters`, split out
    because they are needed by a catalog that declares no `field_sources` block at all —
    which `field_facts` returns `None` for, and which is most of them. Read through
    `Workspace.once` — the fold over 22,059 method rows ran 31 times on `mall-admin` — so
    the map is read and never written into.
    """
    found: dict[str, tuple[dict[str, Any], ...]] = {}
    for row in workspace.query("constructor_declarations"):
        signature = json.loads(str(row["signature"] or "{}")) or {}
        found[str(row["symbol"])] = tuple(signature.get("parameters") or [])
    # `signature` arrives decoded on this query (`_DECODED_COLUMNS`), text on the one above.
    for row in workspace.query("method_declarations"):
        signature = cast(dict[str, Any], row["signature"] or {})
        found[str(row["symbol"])] = tuple(signature.get("parameters") or [])
    return found


def _field_sources(declared: Any, catalog: Catalog) -> FieldSources:
    """Refuses a malformed `field_sources` block at run start, the
    `_validate_methods`/`_validate_steps` discipline (`ports/catalogs.py`: an
    unchecked value does not stay in the file) — a block naming no annotation,
    or naming one as something other than a dotted type, would make the whole
    ladder a silent no-op, which is indistinguishable from the gate above."""
    valid = (
        isinstance(declared, dict)
        and isinstance(declared.get("value_annotation"), str)
        and isinstance(declared.get("properties_annotation"), str)
        and isinstance(declared.get("prefix_from"), str)
        and isinstance(declared.get("getter_prefixes", []), list)
        and all(isinstance(prefix, str) for prefix in declared.get("getter_prefixes", []))
    )
    if not valid:
        raise CatalogError(
            f"loading catalog {catalog.source}: `field_sources` must be "
            f"`{{value_annotation, properties_annotation, prefix_from, "
            f"getter_prefixes?}}` with dotted type names and string keys, got {declared!r}"
        )
    return FieldSources(
        value_annotation=_catalog_symbol(declared["value_annotation"]),
        properties_annotation=_catalog_symbol(declared["properties_annotation"]),
        prefix_from=str(declared["prefix_from"]),
        getter_prefixes=tuple(declared.get("getter_prefixes", [])),
    )


def address_argument(
    argument: dict[str, Any] | None,
    facts: FieldFacts | None,
    workspace_types: CallFacts,
    caller: str | None = None,
) -> dict[str, Any] | None:
    """The argument a `base`/`url`/`channel` capture should be READ as: the
    argument itself, unless the field ladder could name the configuration
    expression behind it, in which case the synthetic string literal that
    expression spells (2F design §4). Everything downstream — CP-2's split,
    the verbless rules, dedup, `_capture_resolved` — then behaves for a
    resolved field exactly as it does for a url written as a literal, which
    is the whole point of returning an expression from every rung.

    `caller` is the symbol of the declaration making this call, needed only by
    the parameter rung below; omitting it leaves that rung silent and every
    other one exactly as it was."""
    expression = field_expression(argument, facts, workspace_types, caller)
    if expression is None:
        return argument
    return {"kind": "string", "value": expression}


def field_expression(
    argument: dict[str, Any] | None,
    facts: FieldFacts | None,
    workspace_types: CallFacts,
    caller: str | None = None,
) -> str | None:
    """2F design §4's four-rung ladder, in order, for an address argument the
    scanner read as a field (or as the result of a property getter):

    1. the field's own `value_annotation` expression, verbatim;
    2. the constructor parameter the field was assigned from (D00 §5's
       `field_write`) and ITS own `value_annotation` expression;
    2a. the enclosing declaration's OWN parameter, where the address argument
       is that parameter passed straight through (D00 §5's `parameter` kind),
       and ITS own `value_annotation` expression. Rung 2's terminal read,
       reached without the field: an injected value assigned to a field and an
       injected value handed straight to a configuring call are the same
       declaration, and only the second carries no `field_write` to follow.
       Bare parameter references only — `parameter_index`'s own soundness
       rule;
    3. a `properties_annotation` prefix plus the relaxed-bound property name —
       either the field's own name, where the address argument reads a
       properties field directly, or the name a zero-argument getter binds to,
       where the argument is that getter's own result (Task 6 checkpoint F-1:
       the realistic idiom is an injected properties bean read through its
       accessor, so the rung follows the D02 §2h one-hop precedent from the
       argument's `source` to the call site that produced it, within this same
       caller's own sites);
    4. nothing matches — None, and the argument stays exactly what it was.

    None too whenever the catalog declared no `field_sources` at all, which is
    what keeps every pre-2F catalog's rows byte-identical."""
    if facts is None or argument is None:
        return None
    kind = argument.get("kind")
    if kind == "field":
        symbol = argument.get("symbol")
        if symbol is None:
            return None
        field = bare_descriptor(str(symbol))
        return (
            facts.value_expressions.get(field)
            or _constructor_expression(field, facts)
            or _properties_field_expression(field, facts)
        )
    if kind == "unresolved":
        return _properties_getter_expression(argument.get("source"), facts, workspace_types)
    if kind == _PARAMETER_KIND:
        return _parameter_expression(argument, facts, caller)
    return None


def _parameter_expression(
    argument: dict[str, Any], facts: FieldFacts, caller: str | None
) -> str | None:
    """Rung 2a: the address argument IS the enclosing declaration's parameter
    N, and that parameter carries the expression on its own annotation — the
    very read rung 2 ends with, minus the `field_write` hop that gets there.

    None without a `caller`, and none where the declaration is not one this
    module scanned: a parameter's annotations live inside its declaration's
    signature and nowhere else (Task 6 checkpoint (3)), so a call whose caller
    left the fact stream names an expression nothing here can see."""
    index = parameter_index(argument)
    if index is None or caller is None:
        return None
    parameters = facts.declared_parameters.get(caller, [])
    if index >= len(parameters):
        return None
    for use in parameters[index].get("annotations") or []:
        if use.get("annotation") != facts.sources.value_annotation:
            continue
        expression = (use.get("args") or {}).get(_ANNOTATION_VALUE_ARG)
        if isinstance(expression, str):
            return expression
    return None


def _constructor_expression(field: str, facts: FieldFacts) -> str | None:
    """Rung 2: the field was assigned straight from constructor parameter N
    (D00 §5's `field_write`), and that parameter carries the expression. The
    `field_write` fact names the position but not WHICH constructor wrote it,
    so every constructor the owning type declares is tried in symbol order and
    the first carrying the annotation at that position answers — deterministic
    (NFR-1), and silent rather than a guess where none does."""
    index = facts.written_from_parameter.get(field)
    owner = owner_of(field)
    if index is None or owner is None:
        return None
    for parameters in facts.constructor_parameters.get(owner, []):
        if index >= len(parameters):
            continue
        for use in parameters[index].get("annotations") or []:
            if use.get("annotation") != facts.sources.value_annotation:
                continue
            expression = (use.get("args") or {}).get(_ANNOTATION_VALUE_ARG)
            if isinstance(expression, str):
                return expression
    return None


def _properties_field_expression(field: str, facts: FieldFacts) -> str | None:
    """Rung 3, the direct form: the address argument reads a field of a type
    the `properties_annotation` binds to a prefix, so the key is that prefix
    and the field's own declared name."""
    owner = owner_of(field)
    prefix = facts.prefixes.get(owner) if owner is not None else None
    if prefix is None:
        return None
    return _placeholder(prefix, member_name(field))


def _properties_getter_expression(
    source: Any, facts: FieldFacts, workspace_types: CallFacts
) -> str | None:
    """Rung 3, the getter form (Task 6 checkpoint F-1): the address argument
    is the RESULT of a zero-argument call — `baseUrl(properties.getUrl())` —
    so the one hop D02 §2h already sanctions follows `source` to the call site
    that produced it, within this same caller's own sites (value ids are
    meaningless across methods, D00 §5). Where that call's own owner is a type
    bound to a prefix, the key is that prefix plus the property the accessor
    names.

    Zero-argument only: an accessor takes none, and a call that does is not
    reading a property, whatever it is named."""
    if source is None:
        return None
    site = next(
        (
            candidate
            for candidate in workspace_types.caller_call_sites
            if candidate.get("result") == source and not (candidate.get("arguments") or [])
        ),
        None,
    )
    if site is None:
        return None
    owner = str(site["owner"])
    prefix = facts.prefixes.get(owner)
    if prefix is None:
        return None
    return _placeholder(prefix, _bound_property(str(site["name"]), owner, facts))


def _bound_property(accessor: str, owner: str, facts: FieldFacts) -> str:
    """The property name an accessor binds to: its own name with a declared
    getter prefix removed, matched against the owning type's DECLARED field
    names through the catalog's own relaxed-binding rule (`resolve/config.py`'s
    `normalize_key`, the very function §2i's `${...}` lookups use — reused,
    never a second copy of the same grammar), so the expression carries the
    spelling the configuration key itself is written in. The de-prefixed name
    stands on its own where the type declares no matching field: an accessor
    is evidence of a property either way, and a key spelled from it is a
    better answer than none.

    Relaxed UNCONDITIONALLY, never gated on the model's own `key_matching`
    (fix round 1, recorded rather than left implicit): that setting lives on
    the framework family's `config_model`, declared on the FAMILY's base
    catalog, and this ladder is only ever handed a CLIENT catalog, which
    cannot see it — the same constraint that makes `_PLACEHOLDER` above a
    written constant. The cost is bounded and one-directional: relaxing only
    ever finds a declared field an exact comparison would have missed, and
    where nothing matches the answer is the de-prefixed name either way, so
    an `exact` family gets a key it could equally have spelled itself."""
    name = _without_getter_prefix(accessor, facts.sources.getter_prefixes)
    normalized = normalize_key(name)
    for declared in facts.declared_fields.get(owner, []):
        if normalize_key(declared) == normalized:
            return declared
    return name


def _without_getter_prefix(accessor: str, prefixes: tuple[str, ...]) -> str:
    """An accessor name with the first declared prefix it carries removed, its
    now-leading character lowercased (`getUrl` → `url`) — the accessor-naming
    convention completed, with the prefixes themselves arriving as catalog
    data so no language's own spelling of them enters this module. Returned
    unchanged where it carries none: not every ecosystem prefixes accessors."""
    for prefix in prefixes:
        if accessor.startswith(prefix) and len(accessor) > len(prefix):
            rest = accessor[len(prefix) :]
            return rest[0].lower() + rest[1:]
    return accessor


def _placeholder(prefix: str, name: str) -> str:
    """The D01 placeholder expression one configuration key reads as — rung
    3's synthesised answer, so that EVERY rung yields an expression and
    everything downstream stays uniform (plan Task 8 Step 1's ruling)."""
    open_, close = _PLACEHOLDER
    return f"{open_}{prefix}.{name}{close}"


def linked_channels(
    argument: dict[str, Any] | None,
    facts: CallFacts,
    forms: list[dict[str, Any]],
) -> list[tuple[None, str | None, str]]:
    """D02 §2h's `channel_via` (Task 7): some destinations are never a
    literal at the consuming call's own argument position at all —
    `session.createProducer(session.createQueue("raw-audit"))`'s `Queue`
    argument is itself another call's return value, and the topic lives on
    THAT call's own argument. Checkpoint-verified against the real fixture:
    the scanner's `unresolved` kind — never `instance` — is what a
    static/interface factory's return value reaches its consumer as (only a
    `NEW` names a concrete type; `MethodInsnNode` producers never do), so
    this follows `source` alone, regardless of the argument's own `kind`.

    `forms` are the catalog's declared `channel_via` entries — `{owner,
    method, arg}`, tried in turn; the first whose `owner`+`method` reach the
    argument's actual linked call site (`_linked_constructor`'s generalised
    join, by owner symbol and method name rather than always `<init>`) wins
    — "matches at most one form", since a linked call is exactly one method
    and at most one form's owner+method can ever join it.

    `peer` is always None (`channel_of`'s own rule: a destination is opaque,
    never split into peer/path). `arg` an int reads that one position off
    the linked call's own arguments, verbatim, through `channel_of`. `arg`
    `"all_strings"` reads EVERY positional argument of the linked call as
    its own channel tuple — `List.of(a, b)` with <=10 elements binds
    FIXED-ARITY overloads (checkpoint ruling), so each element is its own
    literal argument, never an array to enumerate — one resolved tuple per
    string-kind element, plus one trailing `(None, None, "unresolved")`
    tuple if any element failed to resolve as a string. A genuinely varargs
    factory (`Arrays.asList`) hands over ONE array slot instead, and since
    extractor capability 9.15 that slot carries its own `elements`, which
    `_all_string_channels` reads as those positional arguments — so the two
    spellings answer alike. *This paragraph used to end "the scanner never
    unpacks an array argument into its elements, so a varargs factory's own
    single unresolved argument reads as zero resolved elements plus this one
    trailing tuple". That was true until 9.15 and is what 2O Task 13
    changed; an array the extractor still cannot read end to end never
    reaches the `array` kind, and degrades exactly as that sentence said.*

    A form may also name an `arity` (A2 Task 8 fix round 1): the linked
    call must then carry exactly that many arguments. Owner and method alone
    cannot tell overloads apart, and the platform's URI type declares a
    one-string constructor beside four multi-argument ones whose argument 0
    is the SCHEME — without the arity a `url_via` form on `<init>` read
    `https` as an address. A form declaring none matches every overload, as
    before.

    An unlinked argument (no `source` at all), one whose source names no
    real call site, or a linked call none of the declared forms' owner+name
    (and arity, where declared) reaches, all give the same one-tuple honest
    answer `channel_of` gives an unreadable destination: peer/path both
    None, `unresolved`."""
    source = argument.get("source") if argument is not None else None
    if source is None:
        return [(None, None, "unresolved")]
    for form in forms:
        site = _linked_constructor(
            form["owner"], source, facts, form["method"], arity=form.get("arity")
        )
        if site is not None:
            return _read_channels(site, form["arg"])
    return [(None, None, "unresolved")]


def valid_via_arity(form: object) -> bool:
    """Whether a via form's optional `arity` is well-formed: absent, or an
    int — the linked call's argument count `_linked_constructor` compares.
    One helper for the three engines that validate a `channel_via`/`url_via`
    form (`single_call`, `interface_implementation`, `fluent`), because the
    rule is the reader's, not any engine's, and three copies of it would
    drift the day the reader's changes."""
    return not isinstance(form, dict) or "arity" not in form or isinstance(form["arity"], int)


def _read_channels(site: dict[str, Any], arg: int | str) -> list[tuple[None, str | None, str]]:
    """The channel-shaped tuples a linked call site's own arguments read as
    (`channel_via`): a declared int position, verbatim through `channel_of`,
    or every string-kind positional argument at once (`"all_strings"`)."""
    site_arguments = site.get("arguments") or []
    if isinstance(arg, int):
        return [channel_of(_arg_at(site_arguments, arg))]
    return _all_string_channels(site_arguments)


def _all_string_channels(
    arguments: list[dict[str, Any]],
) -> list[tuple[None, str | None, str]]:
    """`all_strings`: one resolved tuple per string-kind positional
    argument, in call order, plus one trailing unresolved tuple if any
    positional argument failed to resolve as a string — never one unresolved
    tuple per failed element (D02 §2's unresolved-is-an-answer stays one
    honest fact, not a guess at how many elements were behind it) — and
    never zero rows for a call with no arguments at all, the same
    never-silently-drop-the-row discipline every other capture here keeps.

    A VARARGS call reads its one array slot's elements as those positional
    arguments (2O Task 13, `_expanded_arguments`). `Arrays.asList("t1",
    "t2")` is a genuine varargs call — one `anewarray` argument in bytecode,
    disassembled from a real probe, never several positional ones — so
    before extractor capability 9.15 it contributed a single unreadable slot
    and this reader answered one trailing unresolved tuple for the whole
    call. `List.of` with <=10 elements binds a FIXED-ARITY overload and has
    always arrived as positional literals, so it is untouched by the
    expansion: the two spellings of one topic list now answer alike."""
    entries = _expanded_arguments(arguments)
    resolved: list[tuple[None, str | None, str]] = [
        (None, str(entry["value"]), "resolved")
        for entry in entries
        if entry.get("kind") == "string" and isinstance(entry.get("value"), str)
    ]
    if resolved and len(resolved) == len(entries):
        return resolved
    return [*resolved, (None, None, "unresolved")]


@dataclass(frozen=True)
class CallSiteIndex:
    """`call_sites` indexed the ways the call-reading engines look it up, built once
    per load (`Workspace.once`) rather than once per catalog: `single_call` ran the
    same two folds over 24,815 rows for each of its 25 catalogs on `mall-admin`.

    Every list keeps the query's own order (caller, then ordinal — NFR-1's row order
    is read from it), and every value is shared by every catalog: read, never
    written into.

    - `by_caller` — each calling method's own sites, the pool `CallFacts.
      caller_call_sites` searches;
    - `bare_callers` — each bare descriptor's FULL caller symbols, for following a
      `lambda` argument into the synthetic method it names (`OI-74`);
    - `positions_by_owner` — the positions in `call_sites` of every site on one
      owner type, so a catalog reads the sites of the owners it declares instead of
      testing every site against them."""

    by_caller: dict[str, list[dict[str, Any]]]
    bare_callers: dict[str, set[str]]
    positions_by_owner: dict[str, list[int]]


def call_site_index(workspace: Workspace) -> CallSiteIndex:
    """`CallSiteIndex` over `call_sites` — the builder `Workspace.once` keys on."""
    by_caller: dict[str, list[dict[str, Any]]] = {}
    bare_callers: dict[str, set[str]] = {}
    positions_by_owner: dict[str, list[int]] = {}
    for position, site in enumerate(workspace.query("call_sites")):
        caller = str(site["caller"])
        by_caller.setdefault(caller, []).append(site)
        bare_callers.setdefault(bare_descriptor(caller), set()).add(caller)
        positions_by_owner.setdefault(str(site["owner"]), []).append(position)
    return CallSiteIndex(by_caller, bare_callers, positions_by_owner)


def supertypes_of(workspace: Workspace) -> dict[str, dict[str, Any]]:
    """Every declared type's own generic supertype reference (D00 §5a's PTR
    carrier), keyed by the type's bare descriptor — the form an `instance`
    argument's own `symbol` carries, never the module-prefixed identity a
    symbol fact's own `symbol` column holds (the same stripping
    `_enum_symbols` applies to its own rows, for the same reason: a symbol is
    module coordinates then a descriptor, D00 §5a, and only the descriptor is
    ever compared)."""
    return {
        bare_descriptor(str(row["symbol"])): json.loads(str(row["supertype"]))
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
    - a `parameter` roots at the type the CALLER's own signature declares for it
      (`OI-77`): a payload handed straight through names no type of its own, and the
      signature is where the type is stated. A DESTINATION read from a parameter is
      still unread — that asks for the value, and the value lives in whatever called
      this method;
    - anything else resolves to no payload — the row still derives (D02 §2's
      `single_call` rule), only the descriptor is absent.
    """
    reference = _reference_of(argument, workspace_types, catalog_rules)
    return _payload_descriptor(
        reference,
        catalog_rules.rules,
        catalog_rules.enums,
        workspace_types.referenced,
        catalog_rules.rules.wrappers,
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
    if kind == _PARAMETER_KIND:
        # **The payload was handed straight through from the caller's own signature**
        # (`OI-77`). The VALUE of a parameter lives in whatever called this method, which
        # is why `parameter` belongs in `_UNREAD_KINDS` and why a `channel_arg` reading one
        # stays `unresolved` — a destination IS its value. A payload is the other question:
        # what a contract needs is the TYPE, and the caller states it.
        #
        # Measured before it was written: 22 of the fixture's 25 outbound `single_call` rows
        # carried no contract at all, across six catalogs, and the three that did all passed
        # a `new` expression. **That is the measurement AT THE TIME this rung landed, not a
        # standing count** — the fixture keeps gaining rows (28 by W47), and a bare number in
        # a comment goes stale with nothing to notice. The declared type is the same claim
        # every shape derived from a signature already makes.
        index = parameter_index(argument)
        if index is None or index >= len(workspace_types.caller_parameters):
            return None
        # The `type` member, not the entry. A declared parameter is `{name, annotations,
        # erased_symbol, type, type_annotations}`; the D00 §5a reference every other rung
        # here roots is the `type`, and handing the whole entry to `root_type` raises on
        # the `symbol` it does not carry.
        declared = workspace_types.caller_parameters[index].get("type")
        return declared if isinstance(declared, dict) else None
    if kind != "instance":
        # `null`, `lambda`, `unresolved`, `field`, `concat`: none of these names a payload
        # type at all. A `field`'s type is knowable in the same way a parameter's is and is
        # NOT read here — the ladder that answers a field is `field_facts`', and reaching
        # into it from this projection would be a second opinion about the same fact.
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
    owner_symbol: str,
    source: int | None,
    workspace_types: CallFacts,
    name: str = "<init>",
    arity: int | None = None,
) -> dict[str, Any] | None:
    """D02 §2h's join: the call site — an `<init>` by default, or (Task 7's
    `channel_via`) any other named method — within this same caller, whose
    own produced value is the argument's `source`. An `<init>` has no
    `result` (D00 §5: "result is null for a void one"), so its own
    `receiver` — the constructed value's id — carries the join instead;
    every other named method's own `result` id is that produced value's id.
    Never a search by proximity: the id is what keeps two calls in one
    method apart. `arity`, when the form names one, is the linked call's
    argument count — the one thing that tells a one-string constructor from
    its four-string overload once owner and name agree."""
    if source is None:
        return None
    key = "receiver" if name == "<init>" else "result"
    return next(
        (
            site
            for site in workspace_types.caller_call_sites
            if site.get("name") == name
            and site.get("owner") == owner_symbol
            and site.get(key) == source
            and (arity is None or len(site.get("arguments") or []) == arity)
        ),
        None,
    )
