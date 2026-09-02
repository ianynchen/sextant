"""The WSDL/XSD branch of the one interpreter (2G design §3, 2I design §3).
The only module in the system that reads a SOAP contract.

Read with the STANDARD LIBRARY's XML parser and nothing else — no new
dependency, and `tests/architecture/test_protobuf_confinement.py` holds that
line the way it holds the other three formats' runtimes. The two namespaces
matched below are the FORMAT's own grammar, named by the XML Schema and WSDL
1.1 specifications, so they are as neutral here as a protobuf descriptor's own
field names: no framework name enters the interpreter with them.

One format, two extensions. A WSDL declares its payload types by embedding XSD
in `<types>` — usually an `xsd:import` and nothing else — so the `.xsd` beside
it is the same schema split across a file boundary. They merge into ONE type
universe per module, for the reason the protobuf pool and the SDL merge do.

The branch says one thing no other format's does: which of the declared
elements ARE operations. In document/literal, an operation's identity IS its
input element's QName — it is what a SOAP dispatcher matches an incoming
payload's root element against — so the `role` mark lands on that element
declaration's own shape, and Task 4 derives one endpoint from the shape
itself.
"""

import io
import posixpath
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

from sextant.domain.facts import DeclaredFieldFact, DeclaredShapeFact, EmbeddedDescriptorFact
from sextant.ingress.interpret.wire import (
    evidence_for,
    item_of,
    shape_ref_of,
    wire_format_of,
    wire_type_of,
)

_XSD_NS = "http://www.w3.org/2001/XMLSchema"
_WSDL_NS = "http://schemas.xmlsoap.org/wsdl/"


def _xsd(tag: str) -> str:
    return f"{{{_XSD_NS}}}{tag}"


def _wsdl(tag: str) -> str:
    return f"{{{_WSDL_NS}}}{tag}"


# D00 §5b's wire vocabulary for the XSD built-in types, keyed by local name.
# Every built-in a payload can carry appears: one missing here would be a
# silent hole, so an unlisted name raises and becomes its file's gap instead.
# The integer widths are the type's own value space and not any language
# binding of it — `xs:unsignedInt` exceeds a signed 32-bit range, and is
# `int64` for that reason alone.
_XSD_SCALARS: dict[str, tuple[str, str | None]] = {
    "string": ("string", None),
    "normalizedString": ("string", None),
    "token": ("string", None),
    "language": ("string", None),
    "Name": ("string", None),
    "NCName": ("string", None),
    "NMTOKEN": ("string", None),
    "NMTOKENS": ("string", None),
    "ID": ("string", None),
    "IDREF": ("string", None),
    "IDREFS": ("string", None),
    "ENTITY": ("string", None),
    "ENTITIES": ("string", None),
    "NOTATION": ("string", None),
    "anyURI": ("string", None),
    "QName": ("string", None),
    "duration": ("string", "duration"),
    "dateTime": ("string", "date-time"),
    "date": ("string", "date"),
    "time": ("string", "time"),
    "gYear": ("string", None),
    "gYearMonth": ("string", None),
    "gMonth": ("string", None),
    "gMonthDay": ("string", None),
    "gDay": ("string", None),
    "boolean": ("boolean", None),
    # Arbitrary precision, so no fixed-width format names it honestly.
    "decimal": ("number", None),
    "float": ("number", "float"),
    "double": ("number", "double"),
    "integer": ("integer", "int64"),
    "nonPositiveInteger": ("integer", "int64"),
    "negativeInteger": ("integer", "int64"),
    "nonNegativeInteger": ("integer", "int64"),
    "positiveInteger": ("integer", "int64"),
    "long": ("integer", "int64"),
    "unsignedLong": ("integer", "int64"),
    "unsignedInt": ("integer", "int64"),
    "int": ("integer", "int32"),
    "short": ("integer", "int32"),
    "byte": ("integer", "int32"),
    "unsignedShort": ("integer", "int32"),
    "unsignedByte": ("integer", "int32"),
    "base64Binary": ("string", "byte"),
    "hexBinary": ("string", "byte"),
    "anyType": ("object", None),
    "anySimpleType": ("object", None),
}

# The model groups this projection reads. Anything else in a content model is
# unknown, and unknown is a gap: see `_Unprojectable`.
_XSD_GROUPS = frozenset({_xsd("sequence"), _xsd("all")})
_XSD_IMPORTS = frozenset({_xsd("import"), _xsd("include"), _xsd("redefine")})


class _Unprojectable(Exception):
    """A construct this branch has no word for (2I design §3): a `choice`
    group, an `xsd:any` wildcard, a substitution group, an attribute, a
    complex or simple content model, a `union`/`list` simple type, an
    `rpc`-style message part. Caught by `wsdl_shapes`, which turns it into
    that file's gap — never a guessed projection, because every one of these
    changes what may actually appear on the wire."""


@dataclass(frozen=True)
class _Contract:
    """One parsed contract file.

    `scopes` maps each of its elements to the namespace prefixes in scope
    there. The parser resolves `xmlns` bindings into `{uri}tag` and then drops
    them, and this format spends them: `type="tns:status"` is only a reference
    to something once `tns` is resolved, and a prefix may be rebound on any
    element — so the bindings have to be captured while parsing rather than
    read off the root afterwards.
    """

    fact: EmbeddedDescriptorFact
    root: Element
    scopes: Mapping[Element, Mapping[str, str]]


@dataclass(frozen=True)
class _Declaration:
    """One global declaration, and the contract that made it."""

    node: Element
    contract: _Contract


@dataclass(frozen=True)
class _WsdlUniverse:
    """The one type universe a module's contract files merge into.

    `shapes` is every global declaration that names a payload — an
    `xsd:element` and a named `xsd:complexType` alike, in ONE map, because both
    become a `declared_shape` keyed by its QName and this vocabulary has a
    single identity space where XSD has two. `simple_types` are separate: a
    restricted scalar names no payload, so it never becomes a shape and cannot
    collide with one. `messages` are separate again for the same reason, and
    because WSDL gives them a symbol space of their own.

    `operations` is the QName of every element some portType operation takes
    as its input — contributed only by files that survive, since a file
    publishing nothing must not publish an operation mark into someone else's
    shape either. `scopes` is every contract's prefix bindings merged, because
    a type is resolved against the prefixes of the file that DECLARED it, not
    the one referencing it.
    """

    shapes: Mapping[str, _Declaration]
    simple_types: Mapping[str, _Declaration]
    messages: Mapping[str, _Declaration]
    operations: frozenset[str]
    scopes: Mapping[Element, Mapping[str, str]]


@dataclass(frozen=True)
class _Held:
    """What one element holds: D01 §5's `{wire_type, wire_format, nullable,
    shape_id?}` descriptor, and — separately — the enum constants, which ride
    on the FIELD rather than inside the descriptor (D00 §5b, and the shape
    every other branch's element descriptors already keep)."""

    described: dict[str, object]
    enum_symbols: tuple[str, ...] | None = None


@dataclass(frozen=True)
class _WsdlReading:
    """One contract file being projected: the file, the module's universe, and
    the shapes found so far — collected as the recursion walks into the
    anonymous complex types nested inside an element declaration."""

    contract: _Contract
    universe: _WsdlUniverse
    shapes: list[DeclaredShapeFact]


def wsdl_shapes(
    facts: Sequence[EmbeddedDescriptorFact],
) -> tuple[list[DeclaredShapeFact], list[str]]:
    """Every payload type the module's contracts declare, and the contract
    files that could not be interpreted.

    Module-wide, like the protobuf pool and the SDL merge, and for the same
    reason: a WSDL's `<types>` typically holds nothing but an `xsd:import`, so
    a per-file interpretation would report every one of its operations as a
    dangling reference.

    No `GeneratedNaming`, as for SDL and for the same reason: a contract file
    compiles into no class here — source is the only origin one has — so a
    shape's symbol IS the declaration's QName, and there is nothing for a
    language adapter to name.

    A file is the failure boundary: one that cannot be read publishes nothing
    at all rather than the types read before the trouble (2G's Avro rule), and
    every other file still interprets.
    """
    parsed: list[_Contract] = []
    failed: list[str] = []
    for fact in facts:
        try:
            root, scopes = _wsdl_parse(fact.payload)
        except ElementTree.ParseError:
            failed.append(fact.symbol)
            continue
        parsed.append(_Contract(fact=fact, root=root, scopes=scopes))

    universe, unusable = _wsdl_universe(parsed)
    failed.extend(sorted(unusable))
    shapes: list[DeclaredShapeFact] = []
    for contract in parsed:
        if contract.fact.symbol in unusable:
            continue
        try:
            found = _contract_shapes(contract, universe)
        except (KeyError, ValueError, _Unprojectable):
            # KeyError: a type, element or prefix nothing in the module
            # declares — a schema no XSD processor would accept either.
            # ValueError: an occurrence bound that is not a number.
            # _Unprojectable: a construct this branch has no word for. Each is
            # this file's gap and no reason to lose the others, and the types
            # read before it are discarded rather than published as half a
            # schema.
            failed.append(contract.fact.symbol)
            continue
        shapes.extend(found)
    return shapes, failed


def _wsdl_parse(payload: str) -> tuple[Element, dict[Element, dict[str, str]]]:
    """The document, and the namespace prefixes in scope at each element.

    Iterated rather than parsed in one call because the tree alone does not
    carry what this format needs: `xmlns` bindings become `{uri}tag` and are
    then dropped, while an attribute VALUE such as `type="tns:status"` keeps
    its prefix and is meaningless without them. `start-ns`/`end-ns` events are
    the standard library's own way to see the bindings, and a stack of them
    respects rebinding on an inner element. The tree is still built — the
    elements are filled in place as the walk proceeds — so it is complete by
    the time this returns.
    """
    scopes: dict[Element, dict[str, str]] = {}
    bindings: list[tuple[str, str]] = []
    root: Element | None = None
    # An event's payload is an element for `start` and a `(prefix, uri)` pair
    # for the namespace events, which is why the stream is untyped and each
    # payload is narrowed by its own event name below.
    for event, item in ElementTree.iterparse(
        io.StringIO(payload), events=("start-ns", "end-ns", "start")
    ):
        if event == "start-ns":
            bindings.append(item)
        elif event == "end-ns":
            bindings.pop()
        else:
            # The innermost binding of a prefix wins, which `dict` gives for
            # free because the stack is outermost-first.
            scopes[item] = dict(bindings)
            if root is None:
                root = item
    if root is None:
        # Unreachable for a document the parser accepted — every well-formed
        # one has a root — and stated rather than assumed, because the
        # alternative is an unexplained `None` reaching the walk below.
        raise ElementTree.ParseError("no root element")
    return root, scopes


def _xsd_schemas(root: Element) -> list[Element] | None:
    """Every XSD schema a contract file carries, or None when its root is
    neither of the two things a contract file may be. A WSDL embeds its
    schemas in `<types>`; an `.xsd` IS one."""
    if root.tag == _xsd("schema"):
        return [root]
    if root.tag == _wsdl("definitions"):
        return [
            schema
            for types in root.findall(_wsdl("types"))
            for schema in types.findall(_xsd("schema"))
        ]
    return None


def _wsdl_universe(parsed: Sequence[_Contract]) -> tuple[_WsdlUniverse, frozenset[str]]:
    """The merged type universe, and the files that cannot contribute to it."""
    owners: dict[str, list[str]] = {}
    simple_owners: dict[str, list[str]] = {}
    message_owners: dict[str, list[str]] = {}
    shapes: dict[str, _Declaration] = {}
    simple_types: dict[str, _Declaration] = {}
    messages: dict[str, _Declaration] = {}
    scopes: dict[Element, Mapping[str, str]] = {}
    unusable: set[str] = set()
    carried = {contract.fact.symbol for contract in parsed}

    for contract in parsed:
        scopes.update(contract.scopes)
        symbol = contract.fact.symbol
        schemas = _xsd_schemas(contract.root)
        if schemas is None:
            # Something harvested this file as a contract and it is not one.
            # Reported rather than dropped, because a payload that produces
            # neither a shape nor a gap is an omission dressed as success
            # (D00 §3).
            unusable.add(symbol)
            continue
        for schema in schemas:
            namespace = schema.get("targetNamespace", "")
            for node in schema:
                if node.tag in _XSD_IMPORTS:
                    if not _import_resolves(node, symbol, carried):
                        # Checked explicitly rather than left to surface as a
                        # dangling type reference: a WSDL whose `<types>` holds
                        # nothing BUT an import declares no type of its own, so
                        # a silently dropped import would leave it publishing
                        # no shape and no gap at all.
                        unusable.add(symbol)
                    continue
                name = node.get("name")
                if name is None:
                    continue
                qualified = _expand(namespace, name)
                if node.tag in (_xsd("element"), _xsd("complexType")):
                    owners.setdefault(qualified, []).append(symbol)
                    shapes.setdefault(qualified, _Declaration(node, contract))
                elif node.tag == _xsd("simpleType"):
                    simple_owners.setdefault(qualified, []).append(symbol)
                    simple_types.setdefault(qualified, _Declaration(node, contract))
        if contract.root.tag == _wsdl("definitions"):
            namespace = contract.root.get("targetNamespace", "")
            for node in contract.root.findall(_wsdl("message")):
                name = node.get("name")
                if name is None:
                    continue
                qualified = _expand(namespace, name)
                message_owners.setdefault(qualified, []).append(symbol)
                messages.setdefault(qualified, _Declaration(node, contract))

    # A name claimed twice in one identity space is an ambiguity nothing here
    # can settle, so every file claiming it is a gap — never a fold whose
    # result depends on which file arrived first (NFR-1).
    for claimed in (owners, simple_owners, message_owners):
        unusable.update(
            symbol for holders in claimed.values() if len(holders) > 1 for symbol in holders
        )

    marks = _operation_elements(parsed, shapes, messages, scopes, unusable)
    return (
        _WsdlUniverse(
            shapes=shapes,
            simple_types=simple_types,
            messages=messages,
            # A file that publishes no shape publishes no operation mark
            # either — without this, a gapped WSDL's operations would still
            # reach a surviving schema's shapes, which is exactly the
            # half-published contract the failure boundary exists to prevent.
            operations=frozenset(
                qualified for symbol, qualified in marks if symbol not in unusable
            ),
            scopes=scopes,
        ),
        frozenset(unusable),
    )


def _import_resolves(node: Element, symbol: str, carried: set[str]) -> bool:
    """Whether an `xsd:import`/`include`/`redefine` names a file the module
    actually carries. A `schemaLocation` is relative to the importing file,
    which is why the reader's `symbol` is the file's path under the schema
    root. An import with NO `schemaLocation` names no file at all — it
    declares a namespace the runtime resolves by catalog — so nothing about it
    can be missing, and a type it would have brought in still surfaces as an
    unresolvable reference."""
    location = node.get("schemaLocation")
    if location is None:
        return True
    return posixpath.normpath(posixpath.join(posixpath.dirname(symbol), location)) in carried


def _operation_elements(
    parsed: Sequence[_Contract],
    shapes: Mapping[str, _Declaration],
    messages: Mapping[str, _Declaration],
    scopes: Mapping[Element, Mapping[str, str]],
    unusable: set[str],
) -> list[tuple[str, str]]:
    """Which declared element each portType operation takes as its input,
    tagged with the file that said so.

    Resolved in a second pass because the chain crosses files: an operation
    names a message, the message names an element, and either may have been
    declared in a sibling. A link that does not resolve makes a gap of the
    WSDL that stated it — an operation quietly dropped is an endpoint that
    vanishes without a word.

    An operation with no `<input>` is a one-way notification: it has no
    request payload to be identified by, so it marks nothing and is no file's
    gap either — nothing about it is missing.
    """
    marks: list[tuple[str, str]] = []
    for contract in parsed:
        symbol = contract.fact.symbol
        if contract.root.tag != _wsdl("definitions") or symbol in unusable:
            continue
        for operation in contract.root.iterfind(f"{_wsdl('portType')}/{_wsdl('operation')}"):
            for node in operation.findall(_wsdl("input")):
                try:
                    marks.extend(_input_element(node, symbol, shapes, messages, scopes))
                except (KeyError, _Unprojectable):
                    unusable.add(symbol)
    return marks


def _input_element(
    node: Element,
    symbol: str,
    shapes: Mapping[str, _Declaration],
    messages: Mapping[str, _Declaration],
    scopes: Mapping[Element, Mapping[str, str]],
) -> list[tuple[str, str]]:
    message = messages[_qname(node, "message", scopes)]
    marks = []
    for part in message.node.findall(_wsdl("part")):
        if part.get("element") is None:
            # An `rpc`-style part is typed rather than element'd, so the
            # operation has no element QName to be identified by. A stated
            # boundary (2I design §3): inventing one would be a guess about
            # what actually goes on the wire.
            raise _Unprojectable(f"rpc-style message part in {symbol}")
        qualified = _qname(part, "element", scopes)
        if qualified not in shapes:
            raise KeyError(qualified)
        marks.append((symbol, qualified))
    return marks


def _contract_shapes(contract: _Contract, universe: _WsdlUniverse) -> list[DeclaredShapeFact]:
    """One shape per global declaration that names a payload: an `xsd:element`
    (what actually travels, and what an operation is identified by) and a
    named `xsd:complexType` (a payload a field can reference). A named
    `xsd:simpleType` is neither — it is a restricted scalar, and a record of
    its constants is a payload nobody sends (D00 §5b), so its constants ride
    on every field that references it instead."""
    reading = _WsdlReading(contract=contract, universe=universe, shapes=[])
    for schema in _xsd_schemas(contract.root) or ():
        namespace = schema.get("targetNamespace", "")
        for node in schema:
            name = node.get("name")
            if name is None:
                continue
            qualified = _expand(namespace, name)
            if node.tag == _xsd("element"):
                _element_shape(node, qualified, reading)
            elif node.tag == _xsd("complexType"):
                _add_shape(qualified, _complex_fields(node, qualified, reading), reading)
    return reading.shapes


def _element_shape(node: Element, qualified: str, reading: _WsdlReading) -> None:
    """A global element declaration's own shape. It is the only kind of shape
    that can carry the `operation` role: the wrapper element is the wire-true
    request, and the type behind it is a payload rather than an operation."""
    if node.get("substitutionGroup") is not None:
        # What arrives may be any member of the group, so this declaration's
        # own type is not what the payload contains.
        raise _Unprojectable(f"substitution group on {qualified}")
    _add_shape(
        qualified,
        _element_own_fields(node, qualified, reading),
        reading,
        role="operation" if qualified in reading.universe.operations else None,
    )


def _element_own_fields(
    node: Element, qualified: str, reading: _WsdlReading
) -> list[DeclaredFieldFact]:
    """What a global element's payload actually contains.

    An element typed by a NAMED complex type carries that type's fields rather
    than a reference to it: the element is what goes on the wire, and this
    vocabulary has no way to say "this shape IS that one" — so leaving the
    fields off would publish an empty payload nobody sends. The named type
    keeps its own shape as well, which is what a FIELD referencing it points
    at.

    An element typed by a scalar has no fields at all, and that is the honest
    answer: the payload is a single value, and this vocabulary describes a
    record.
    """
    inline = node.find(_xsd("complexType"))
    if inline is not None:
        return _complex_fields(inline, qualified, reading)
    if node.get("type") is not None:
        target = _qname(node, "type", reading.universe.scopes)
        declaration = reading.universe.shapes.get(target)
        if declaration is not None and declaration.node.tag == _xsd("complexType"):
            return _complex_fields(declaration.node, qualified, reading)
        # Resolved even though nothing is read off it, so a type nothing in
        # the module declares raises here: without this the element would
        # publish an EMPTY shape and no gap, which reads downstream as a
        # payload that genuinely carries nothing (D00 §3).
        _type_held(target, reading)
    return []


def _add_shape(
    qualified: str,
    fields: list[DeclaredFieldFact],
    reading: _WsdlReading,
    role: Literal["operation"] | None = None,
) -> None:
    fact = reading.contract.fact
    reading.shapes.append(
        DeclaredShapeFact(
            document_id=fact.document_id,
            # The QName in both roles: a contract file compiles to no class,
            # so there is no second naming for the schema name to bridge.
            symbol=qualified,
            schema_name=qualified,
            schema_format="wsdl",
            origin=fact.origin,
            evidence=evidence_for(fact.origin),
            role=role,
            fields=fields,
        )
    )


def _complex_fields(
    node: Element, qualified: str, reading: _WsdlReading
) -> list[DeclaredFieldFact]:
    """One complex type's fields. `qualified` is the shape being built, and
    the name an anonymous type nested inside it is reached by."""
    fields: list[DeclaredFieldFact] = []
    for particle in node:
        if particle.tag == _xsd("annotation"):
            continue
        if particle.tag not in _XSD_GROUPS:
            # An attribute, a `choice`, a content model, a group reference,
            # `anyAttribute` — each changes what the payload may carry, and
            # none of them has a word in this vocabulary.
            raise _Unprojectable(f"{particle.tag} in {qualified}")
        fields.extend(_group_fields(particle, qualified, reading))
    return fields


def _group_fields(node: Element, qualified: str, reading: _WsdlReading) -> list[DeclaredFieldFact]:
    """The elements one `sequence`/`all` model group declares, flattening the
    groups nested inside it — nesting a sequence changes the order rules, not
    what the payload carries."""
    fields: list[DeclaredFieldFact] = []
    for child in node:
        if child.tag == _xsd("annotation"):
            continue
        if child.tag == _xsd("element"):
            fields.append(_wsdl_field(child, qualified, reading))
        elif child.tag in _XSD_GROUPS:
            fields.extend(_group_fields(child, qualified, reading))
        else:
            # `choice` is one of several elements and `any` is anything at
            # all; projecting the fields around either would report a closed
            # payload that is open (2I design §3).
            raise _Unprojectable(f"{child.tag} in {qualified}")
    return fields


def _wsdl_field(node: Element, qualified: str, reading: _WsdlReading) -> DeclaredFieldFact:
    """One local element declaration, as a field."""
    if node.get("ref") is not None:
        target = _qname(node, "ref", reading.universe.scopes)
        name = target.rpartition("}")[2]
        held = _referenced_held(target, reading)
    else:
        declared = node.get("name")
        if declared is None:
            raise KeyError("element with neither name nor ref")
        name = declared
        # XSD gives an anonymous inline type no name. The containing shape's
        # QName plus the element name is the only identity the schema itself
        # states, and `/` cannot appear in an NCName — so a synthesized name
        # can never collide with a QName a schema actually declared.
        held = _element_held(node, f"{qualified}/{name}", reading)
    described = held.described
    # `maxOccurs` defaults to 1 and is a bound, not a keyword: `5` repeats
    # exactly as `unbounded` does, and reading only the word would report a
    # list as a scalar.
    bound = node.get("maxOccurs", "1")
    repeated = bound == "unbounded" or int(bound) > 1
    # XSD states presence and nil-ness separately and outright, so neither is
    # inferred from the other (D00 §5b's trap): `minOccurs` decides whether
    # the element may be absent, `nillable` whether a present one may be nil.
    return DeclaredFieldFact(
        name=name,
        # Verbatim: an element's declared name IS its name on the wire, so
        # there is no second spelling for a wire name to disagree with.
        wire_name=name,
        # XSD has no field numbers — an element is matched by name.
        field_number=None,
        wire_type="array" if repeated else wire_type_of(described),
        wire_format=None if repeated else wire_format_of(described),
        required=node.get("minOccurs", "1") != "0",
        nullable=node.get("nillable") == "true",
        # Verbatim, always a string (D00 §5c's rule for a declared value).
        default=node.get("default"),
        item=described if repeated else item_of(described),
        shape_ref=None if repeated else shape_ref_of(described),
        # Past the repeat, exactly as a repeated protobuf enum reports its
        # constants on the field rather than on the element.
        enum_symbols=None if held.enum_symbols is None else list(held.enum_symbols),
    )


def _element_held(node: Element, anonymous: str, reading: _WsdlReading) -> _Held:
    """What a locally-declared element holds. An inline complex type becomes a
    shape of its own under `anonymous`, the way a nested protobuf message is
    its own shape — each is a payload something sends."""
    if node.get("type") is not None:
        return _type_held(_qname(node, "type", reading.universe.scopes), reading)
    inline = node.find(_xsd("complexType"))
    if inline is not None:
        _add_shape(anonymous, _complex_fields(inline, anonymous, reading), reading)
        return _Held(
            {"wire_type": "object", "wire_format": None, "nullable": False, "shape_id": anonymous}
        )
    simple = node.find(_xsd("simpleType"))
    if simple is not None:
        return _simple_held(simple, reading)
    # No type at all is `xs:anyType`: an open payload this vocabulary has no
    # shape for, and `object` with nothing behind it is its least-committal
    # answer — the same one a GraphQL custom scalar gets.
    return _Held({"wire_type": "object", "wire_format": None, "nullable": False})


def _referenced_held(target: str, reading: _WsdlReading) -> _Held:
    """What an element declared by `ref` holds: whatever the global
    declaration it names holds. That declaration already has a shape of its
    own, so an inline complex type there is referenced rather than re-emitted
    under a second name."""
    node = reading.universe.shapes[target].node
    if node.get("type") is not None:
        return _type_held(_qname(node, "type", reading.universe.scopes), reading)
    if node.find(_xsd("complexType")) is not None:
        return _Held(
            {"wire_type": "object", "wire_format": None, "nullable": False, "shape_id": target}
        )
    simple = node.find(_xsd("simpleType"))
    if simple is not None:
        return _simple_held(simple, reading)
    return _Held({"wire_type": "object", "wire_format": None, "nullable": False})


def _type_held(qualified: str, reading: _WsdlReading) -> _Held:
    """What one type name means on the wire. Raises `KeyError` for a name
    nothing in the module declares — the caller turns that into this file's
    gap rather than a reference to a shape that does not exist."""
    if qualified.startswith(f"{{{_XSD_NS}}}"):
        scalar = _XSD_SCALARS[qualified.rpartition("}")[2]]
        return _Held({"wire_type": scalar[0], "wire_format": scalar[1], "nullable": False})
    simple = reading.universe.simple_types.get(qualified)
    if simple is not None:
        return _simple_held(simple.node, reading)
    declaration = reading.universe.shapes[qualified]
    if declaration.node.tag != _xsd("complexType"):
        # A `type` attribute naming an ELEMENT is not a type reference at all.
        raise KeyError(qualified)
    return _Held(
        {"wire_type": "object", "wire_format": None, "nullable": False, "shape_id": qualified}
    )


def _simple_held(node: Element, reading: _WsdlReading) -> _Held:
    """What a simple type means on the wire. Enumeration facets close the
    value set, and D00 §5b says a closed set reaches the wire as `enum`
    carrying its constants; any other restriction only qualifies a type this
    vocabulary already has a name for, so it reads as its base does."""
    restriction = node.find(_xsd("restriction"))
    if restriction is None:
        # A `union` is several types at once and a `list` is a whitespace-
        # separated encoding of one — neither has a word here.
        raise _Unprojectable("simple type that is not a restriction")
    symbols = tuple(str(value.get("value")) for value in restriction.findall(_xsd("enumeration")))
    if symbols:
        return _Held(
            {"wire_type": "enum", "wire_format": None, "nullable": False}, enum_symbols=symbols
        )
    return _type_held(_qname(restriction, "base", reading.universe.scopes), reading)


def _qname(node: Element, attribute: str, scopes: Mapping[Element, Mapping[str, str]]) -> str:
    """One prefixed QName attribute, expanded against the prefixes in scope at
    the element that wrote it. Raises `KeyError` for a missing attribute or an
    undeclared prefix — a reference this file cannot even name."""
    value = node.get(attribute)
    if value is None:
        raise KeyError(attribute)
    prefix, separator, local = value.partition(":")
    if not separator:
        prefix, local = "", value
    namespace = scopes[node].get(prefix)
    if namespace is None:
        raise KeyError(value)
    return _expand(namespace, local)


def _expand(namespace: str, local: str) -> str:
    """W3C QName notation — the spelling annotation-derived rows meet these on
    (2I design §1). A declaration in no target namespace is its local name
    alone, which is that notation's own rule."""
    return f"{{{namespace}}}{local}" if namespace else local
