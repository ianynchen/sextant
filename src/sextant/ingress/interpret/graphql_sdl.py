"""The GraphQL SDL branch of the one interpreter (2G design §3). The only
module in the system that reads SDL, which is what
`tests/architecture/test_protobuf_confinement.py` enforces.

SDL is read module-wide for the reason the protobuf pool is, under a different
name: the runtime merges every `.graphqls` file under the schema root into one
schema before it serves anything.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from graphql import GraphQLSyntaxError, parse, print_ast
from graphql.language.ast import (
    DocumentNode,
    EnumTypeDefinitionNode,
    ExecutableDefinitionNode,
    FieldDefinitionNode,
    InputObjectTypeDefinitionNode,
    InputValueDefinitionNode,
    InterfaceTypeDefinitionNode,
    ListTypeNode,
    NamedTypeNode,
    NonNullTypeNode,
    ObjectTypeDefinitionNode,
    OperationType,
    ScalarTypeDefinitionNode,
    SchemaDefinitionNode,
    SchemaExtensionNode,
    TypeDefinitionNode,
    TypeExtensionNode,
    TypeNode,
    UnionTypeDefinitionNode,
)

from sextant.domain.facts import DeclaredFieldFact, DeclaredShapeFact, EmbeddedDescriptorFact
from sextant.ingress.interpret.wire import (
    evidence_for,
    item_of,
    shape_ref_of,
    wire_format_of,
    wire_type_of,
)

# D00 §5b's wire vocabulary for GraphQL's five built-in scalars — the only
# names the format itself commits to an encoding for (`Int` is signed 32-bit
# and `Float` is IEEE 754 double by the GraphQL spec; `ID` serializes as a
# string). A custom scalar is deliberately absent: see `_graphql_named_element`.
_GRAPHQL_SCALARS: dict[str, tuple[str, str | None]] = {
    "ID": ("string", None),
    "String": ("string", None),
    "Int": ("integer", "int32"),
    "Float": ("number", "double"),
    "Boolean": ("boolean", None),
}

# `DeclaredShapeFact.role` for each of the two ways SDL names an operation
# root: a `schema` block's explicit binding, and — only when no block binds
# anything — GraphQL's own default type names.
_GRAPHQL_OPERATIONS: dict[OperationType, Literal["query", "mutation", "subscription"]] = {
    OperationType.QUERY: "query",
    OperationType.MUTATION: "mutation",
    OperationType.SUBSCRIPTION: "subscription",
}
_GRAPHQL_ROOT_NAMES: dict[str, Literal["query", "mutation", "subscription"]] = {
    "Query": "query",
    "Mutation": "mutation",
    "Subscription": "subscription",
}


@dataclass(frozen=True)
class _GraphqlUniverse:
    """The one schema a module's SDL files merge into.

    `declared` is every type name the module names unambiguously — a name two
    files declare is in none of these, because nothing here can tell which
    declaration the runtime was meant to serve. `scalars` and `enums` are the
    two kinds of declared name that are not a reference to a payload's shape.
    `extensions` holds the fields an `extend type` contributes, keyed by the
    type they belong to, because the runtime merges them in before serving —
    contributed only by files that survive, since a file publishing nothing
    must not publish fields into someone else's type either. `roles` names the
    operation root each entry-point type serves.
    """

    declared: frozenset[str]
    scalars: frozenset[str]
    enums: Mapping[str, tuple[str, ...]]
    extensions: Mapping[str, tuple[FieldDefinitionNode | InputValueDefinitionNode, ...]]
    roles: Mapping[str, Literal["query", "mutation", "subscription"]]


def graphql_shapes(
    facts: Sequence[EmbeddedDescriptorFact],
) -> tuple[list[DeclaredShapeFact], list[str]]:
    """Every type the module's SDL declares, and the SDL files that could not
    be interpreted.

    Module-wide, like the protobuf pool and for the same reason: the runtime
    merges every `.graphqls` file under the schema root into ONE schema, so a
    type that one file's fields name is routinely declared in the next, and a
    per-file interpretation would report it as a dangling reference.

    No `GeneratedNaming` here, unlike either other format: SDL compiles into
    no class at all — source is the only origin an SDL payload has — so a
    shape's symbol IS the schema's own type name, and there is nothing for a
    language adapter to name.

    A file is the failure boundary: one that cannot be read publishes nothing
    at all rather than the types read before the trouble (2G's Avro rule),
    and every other file still interprets.

    A failed file takes its declarations with it, and that CASCADES by
    design: a file whose text does not parse declared nothing this module can
    see, so a sibling naming one of its types is naming a type the merged
    schema does not contain — which is exactly the state the runtime would
    refuse to start in, and so a gap of its own rather than a shape pointing
    at nothing. A file that parsed but could not be projected is the milder
    case: its names are in the universe, so a sibling's reference to one
    stays an ordinary `shape_ref` that this run published no shape for, and
    reads downstream as an unclosed reference rather than a second gap.
    """
    parsed: list[tuple[EmbeddedDescriptorFact, DocumentNode]] = []
    failed: list[str] = []
    for fact in facts:
        try:
            parsed.append((fact, parse(fact.payload)))
        except GraphQLSyntaxError:
            failed.append(fact.symbol)

    universe, unusable = _graphql_universe(parsed)
    failed.extend(sorted(unusable))
    shapes: list[DeclaredShapeFact] = []
    for fact, document in parsed:
        if fact.symbol in unusable:
            continue
        if all(isinstance(node, ExecutableDefinitionNode) for node in document.definitions):
            # An operations document — the queries a client sends, which
            # `.graphql` also spells — is not a schema and describes no
            # payload this service declares. Ignored outright, neither shape
            # nor gap: a gap would report a file that is not missing anything,
            # permanently, for as long as it sits beside the schema.
            continue
        try:
            found = _graphql_document_shapes(fact, document, universe)
        except (KeyError, TypeError):
            # KeyError: a field typed by a name nothing in the module declares
            # unambiguously — a schema the runtime itself would refuse to
            # build. TypeError: a type node in a form this projection does not
            # know. Either is this file's gap and no reason to lose the
            # others, and the types read before it are discarded rather than
            # published as half a schema.
            failed.append(fact.symbol)
            continue
        shapes.extend(found)
    return shapes, failed


def _graphql_universe(
    parsed: Sequence[tuple[EmbeddedDescriptorFact, DocumentNode]],
) -> tuple[_GraphqlUniverse, frozenset[str]]:
    """The merged schema, and the files that cannot contribute to it."""
    owners: dict[str, list[str]] = {}
    enums: dict[str, tuple[str, ...]] = {}
    scalars: set[str] = set()
    # Tagged with the file each contribution came from, so the ones belonging
    # to a file that turns out to be a gap can be dropped below.
    extensions: dict[str, list[tuple[str, FieldDefinitionNode | InputValueDefinitionNode]]] = {}
    extenders: dict[str, list[str]] = {}
    bound_roots: list[tuple[str, str, Literal["query", "mutation", "subscription"]]] = []
    unusable: set[str] = set()
    for fact, document in parsed:
        for node in document.definitions:
            if isinstance(node, UnionTypeDefinitionNode):
                # A union is one of several types, and this vocabulary has no
                # word for that: its members are separate shapes and it has no
                # field of its own to carry them, so a shape for it would be
                # an empty payload nobody sends. Its file is a gap — the same
                # answer `extend union` gets, for the same reason (2H design
                # §2's "a construct the branch cannot project").
                unusable.add(fact.symbol)
            elif isinstance(node, TypeDefinitionNode):
                owners.setdefault(node.name.value, []).append(fact.symbol)
                if isinstance(node, EnumTypeDefinitionNode):
                    enums[node.name.value] = tuple(value.name.value for value in node.values)
                elif isinstance(node, ScalarTypeDefinitionNode):
                    scalars.add(node.name.value)
            elif isinstance(node, TypeExtensionNode):
                fields = getattr(node, "fields", None)
                if fields is None:
                    # `extend enum`, `extend union`, `extend scalar`: an
                    # extension that adds members this projection has no field
                    # to carry. Its file is a gap rather than a silent partial.
                    unusable.add(fact.symbol)
                    continue
                extensions.setdefault(node.name.value, []).extend(
                    (fact.symbol, field) for field in fields
                )
                extenders.setdefault(node.name.value, []).append(fact.symbol)
            elif isinstance(node, SchemaDefinitionNode | SchemaExtensionNode):
                bound_roots.extend(
                    (
                        fact.symbol,
                        operation.type.name.value,
                        _GRAPHQL_OPERATIONS[operation.operation],
                    )
                    for operation in node.operation_types or ()
                )

    duplicated = {name for name, holders in owners.items() if len(holders) > 1}
    # A name two files declare is a schema Spring itself rejects, and nothing
    # here can pick a winner: every file declaring it is a gap.
    unusable.update(symbol for name in duplicated for symbol in owners[name])
    # An `extend type` whose base type no file declares (or that two do) adds
    # fields to nothing. Dropping them silently would omit real operations.
    unusable.update(
        symbol
        for name, holders in extenders.items()
        if name not in owners or name in duplicated
        for symbol in holders
    )
    # Two bindings of one operation to different types is the same ambiguity a
    # duplicate type name is, and has the same answer: no winner, both files
    # are gaps — never a fold whose result depends on which file arrived first
    # (NFR-1).
    bound_names: dict[str, set[str]] = {}
    for _, name, role in bound_roots:
        bound_names.setdefault(role, set()).add(name)
    unusable.update(symbol for symbol, _, role in bound_roots if len(bound_names[role]) > 1)
    declared = frozenset(owners) - duplicated
    universe = _GraphqlUniverse(
        declared=declared,
        scalars=frozenset(scalars),
        enums=enums,
        # A file that publishes no shape publishes no fields into anyone
        # else's type either — without this, a gapped file's `extend type`
        # would still reach the extended type's shape, which is exactly the
        # half-published schema the failure boundary exists to prevent.
        extensions={
            name: tuple(field for symbol, field in tagged if symbol not in unusable)
            for name, tagged in extensions.items()
        },
        roles=_graphql_roles(bound_roots, declared, unusable),
    )
    return universe, frozenset(unusable)


def _graphql_roles(
    bound_roots: Sequence[tuple[str, str, Literal["query", "mutation", "subscription"]]],
    declared: frozenset[str],
    unusable: frozenset[str] | set[str],
) -> Mapping[str, Literal["query", "mutation", "subscription"]]:
    """Which type answers each kind of operation.

    A `schema` block binds the roots by name, and renaming them is the whole
    reason it exists (`schema { query: MyQuery }`), so the binding cannot be
    recovered from a type's own name later — nothing downstream may parse SDL
    (the confinement rule), which is why the answer rides on the fact.

    Absent any binding, GraphQL's own defaults apply: `Query`, `Mutation` and
    `Subscription` are the roots because they are named that. A binding
    anywhere in the module turns the defaults off exactly as the GraphQL spec
    says it does — a schema block that names only a query root declares that
    the service has only that root.
    """
    bound = {name: role for symbol, name, role in bound_roots if symbol not in unusable}
    if bound:
        return {name: role for name, role in bound.items() if name in declared}
    return {name: role for name, role in _GRAPHQL_ROOT_NAMES.items() if name in declared}


def _graphql_document_shapes(
    fact: EmbeddedDescriptorFact, document: DocumentNode, universe: _GraphqlUniverse
) -> list[DeclaredShapeFact]:
    """One shape per type this file declares that names a payload: an object,
    an interface and an input each describe one something sends or receives,
    and an enum is a type fields reference by name — carrying no fields of its
    own, because a record of its constants is a payload nobody sends (D00
    §5b); they ride on every field that references it instead. The two
    declared types missing from that list are the two that describe no
    payload: a scalar, and a union (whose file `_graphql_universe` has already
    made a gap)."""
    shapes: list[DeclaredShapeFact] = []
    for node in document.definitions:
        if not isinstance(
            node,
            ObjectTypeDefinitionNode
            | InterfaceTypeDefinitionNode
            | InputObjectTypeDefinitionNode
            | EnumTypeDefinitionNode,
        ):
            continue
        name = node.name.value
        declared_fields = [
            *(getattr(node, "fields", None) or ()),
            *universe.extensions.get(name, ()),
        ]
        shapes.append(
            DeclaredShapeFact(
                document_id=fact.document_id,
                symbol=name,
                # The type's own name in both roles: SDL compiles to no class,
                # so there is no second naming for the schema name to bridge.
                schema_name=name,
                schema_format="graphql",
                origin=fact.origin,
                evidence=evidence_for(fact.origin),
                # NULL for every type but the two or three the schema names as
                # its operation roots.
                role=universe.roles.get(name),
                fields=[_graphql_field(field, universe) for field in declared_fields],
            )
        )
    return shapes


def _graphql_field(
    node: FieldDefinitionNode | InputValueDefinitionNode, universe: _GraphqlUniverse
) -> DeclaredFieldFact:
    """One field of a type. A field's arguments are not projected: they are
    what an operation takes, not what this payload carries."""
    described = _graphql_element(node.type, universe)
    non_null = isinstance(node.type, NonNullTypeNode)
    # Only an input field can carry one; an output field has no such attribute.
    default = getattr(node, "default_value", None)
    held = universe.enums.get(_graphql_named(node.type))
    name = node.name.value
    return DeclaredFieldFact(
        name=name,
        # GraphQL renames nothing: the declared name is the key in the JSON
        # response. An alias is the caller's choice per query, never the
        # schema's, so there is no second spelling to disagree with.
        wire_name=name,
        # The format has no field numbers — a response is keyed by name.
        field_number=None,
        wire_type=wire_type_of(described),
        wire_format=wire_format_of(described),
        # GraphQL's own rule, and the one Avro states too: `!` is what makes a
        # value non-null, and a default is what makes an input field omittable
        # in spite of it.
        required=non_null and default is None,
        nullable=not non_null,
        # Verbatim, the SDL's own spelling of the value (D00 §5c).
        default=None if default is None else print_ast(default),
        item=item_of(described),
        shape_ref=shape_ref_of(described),
        # Past the list, exactly as a repeated protobuf enum reports its
        # constants on the field rather than on the element.
        enum_symbols=None if held is None else list(held),
    )


def _graphql_element(node: TypeNode, universe: _GraphqlUniverse) -> dict[str, object]:
    """D01 §5's recursive `{wire_type, wire_format, nullable, shape_id?,
    item?}` descriptor for one SDL type node.

    Nullable by default, which is the opposite of the other two formats:
    every GraphQL type is nullable until a `!` says otherwise, and that `!`
    is stated separately for a list and for what it holds.
    """
    if isinstance(node, NonNullTypeNode):
        return {**_graphql_element(node.type, universe), "nullable": False}
    if isinstance(node, ListTypeNode):
        return {
            "wire_type": "array",
            "wire_format": None,
            "nullable": True,
            "item": _graphql_element(node.type, universe),
        }
    if isinstance(node, NamedTypeNode):
        return _graphql_named_element(node.name.value, universe)
    raise TypeError(f"unexpected graphql type node: {type(node).__name__}")


def _graphql_named_element(name: str, universe: _GraphqlUniverse) -> dict[str, object]:
    """What one type name means on the wire. Raises `KeyError` for a name
    nothing in the module declares — the caller turns that into this file's
    gap rather than a reference to a shape that does not exist."""
    scalar = _GRAPHQL_SCALARS.get(name)
    if scalar is not None:
        return {"wire_type": scalar[0], "wire_format": scalar[1], "nullable": True}
    if name not in universe.declared:
        raise KeyError(name)
    if name in universe.enums:
        return {"wire_type": "enum", "wire_format": None, "nullable": True}
    if name in universe.scalars:
        # A custom scalar states a name and nothing about the wire: its
        # encoding lives in a coercer written in the service's own code, and
        # `string` here would be a guess that reads as an observation.
        # `object` with no shape behind it is this vocabulary's
        # least-committal answer — the same one an Avro value with no encoding
        # of its own gets — and it leaves the field open and reported.
        return {"wire_type": "object", "wire_format": None, "nullable": True}
    return {"wire_type": "object", "wire_format": None, "nullable": True, "shape_id": name}


def _graphql_named(node: TypeNode) -> str:
    """The name of what a field actually holds: past the `!`, then past the
    list."""
    if isinstance(node, NonNullTypeNode | ListTypeNode):
        return _graphql_named(node.type)
    if isinstance(node, NamedTypeNode):
        return node.name.value
    raise TypeError(f"unexpected graphql type node: {type(node).__name__}")
