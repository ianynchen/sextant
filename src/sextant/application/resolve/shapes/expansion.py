"""Expansion is computed here rather than in SQL for two reasons: it re-roots
every field through the same wrapper rules, and the `item` descriptor is
recursive — assembled bottom-up over a queue of shapes, which one statement
cannot express. The derivation is handed the finished rows."""

import dataclasses
import hashlib
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.dispatch import ancestry_of
from sextant.application.resolve.shapes.nullability import _nullability_of, _scope_prefixes
from sextant.application.resolve.shapes.rooting import _catalog_symbol, root_type
from sextant.domain.symbols import bare_descriptor, names_a_type, owner_of


@dataclass(frozen=True)
class ExpandedShapes:
    """What the pass could not expand: types with no field facts and no
    `known_types` entry. Returned rather than dropped because M04 reports
    them (D2) — a catalog grows from observation, and a gap nobody can see is
    a gap nobody closes."""

    unexpanded_types: tuple[str, ...]


def derive_shapes(workspace: Workspace, catalog: Catalog, roots: Sequence[str]) -> ExpandedShapes:
    """Expands each root into a `shapes` row and its `shape_fields`, following
    every reference it finds.

    Cycles terminate by construction: an `object` field holds a *reference* to
    another shape, never an inlining, so `Node { Node parent; }` needs no depth
    counter — only the discipline that each shape is expanded once.
    """
    rules = _rules_of(catalog)
    scope_prefixes = _scope_prefixes(workspace, rules)
    declared = _Fields(workspace=workspace)
    accessors = _Accessors(workspace=workspace, rules=rules)
    descriptors = _declared_shapes(workspace)
    parameters = _type_parameters(workspace)
    tiers = _origin_tiers(workspace)
    enums = _enum_symbols(workspace)
    shapes: list[dict[str, object]] = []
    fields: list[dict[str, object]] = []
    unexpanded: list[str] = []
    # A list, not a set: the order shapes are reached in decides the order rows
    # are written and the order the report names gaps (NFR-1).
    pending = list(dict.fromkeys(roots))
    expanded: set[str] = set()

    while pending:
        shape_id = pending.pop(0)
        if shape_id in expanded:
            continue
        expanded.add(shape_id)
        referenced: list[str] = []
        # A type owning a `declared_shape` takes ONLY its declared fields,
        # never bytecode ones (the never-a-blend rule, D01 §3): a compiled
        # schema class's own fields are serializer machinery — bitfields,
        # cached hash codes — not the wire contract the schema states, so
        # `declared.get(shape_id, [])` is never consulted once a descriptor
        # is found here.
        # F4 §5.2 (W25). A parameterised id names a type plus its bound arguments, and
        # everything the workspace holds is keyed on the type ALONE — its fields, its
        # declared shape, its formal parameters. So the base is what is looked up, and
        # the binding is applied to the fields that come back.
        base, arguments = bindings_of(shape_id)
        substitution = _substitution(parameters.get(base, []), arguments)
        descriptor = descriptors.get(base)
        # F4 §5.2 (W26). Fields first, accessors only when the fields produced NO wire
        # contract — which keeps this purely additive: every shape that had rows before
        # has the same rows now, and the fallback replaces an empty answer rather than
        # competing with a real one. The trigger is the empty ROW SET rather than an
        # absent field fact, so a type whose only fields are static or `@JsonIgnore`d
        # falls back too; those are the same "we found no contract" as an interface's
        # no fields at all, and a shape with neither fields nor accessors is still open.
        #
        # **A type whose accessors are ALL filtered out is CLOSED with zero fields**, and
        # that is the answer rather than a hole (W26 review raised it; measured and
        # rejected). `_rows_of`'s only filters are `static`/`transient` and the catalog's
        # own `ignore` list, and every one of those means the member is genuinely not on
        # the wire — a type whose every accessor carries `@JsonIgnore` serialises as `{}`,
        # and `{}` is a complete description. It is also exactly what the FIELD path does
        # one line up: a class whose fields are all ignored has `base in declared` and is
        # closed too. Making the accessor half report open would leave the two halves
        # disagreeing about one question.
        from_accessors = False
        if descriptor is not None:
            rows = _declared_rows_of(descriptor, referenced)
        else:
            rows = _rows_of(
                workspace,
                rules,
                scope_prefixes,
                _bound(declared.of(base), substitution),
                enums,
                referenced,
            )
            if not rows:
                from_accessors = bool(accessors.of(base))
                rows = _rows_of(
                    workspace,
                    rules,
                    scope_prefixes,
                    _bound(accessors.of(base), substitution),
                    enums,
                    referenced,
                )
        pending.extend(referenced)
        # Expansion needs field facts, and only scanned types have them, so a
        # type without them stops here whoever wrote it (ruling F4). Its
        # reference is still kept: an open, zero-field shape row (D2).
        # `declared.of(base)` rather than "does `base` declare a field of its own": a type
        # that declares none and inherits all of them IS described, and asking only about
        # its own facts reported `DetailedOrderResult extends OrderResult` unexpandable
        # while publishing both of its inherited fields. Same shape as the mistake
        # `_Accessors` records for accessors and `corpus_shapes.py` for resolvable calls.
        expandable = descriptor is not None or bool(declared.of(base)) or from_accessors
        if not expandable:
            unexpanded.append(shape_id)
        shapes.append(
            {
                "shape_id": shape_id,
                "content_hash": _content_hash(rows),
                # Direct, never transitive: a shape is open because a field of
                # its own stopped, not because something further down did.
                # A referenced type closes the field every way it can be
                # expanded — bytecode fields, a declared shape's own, or the bean
                # accessors W26 reads when a type has no fields. The third had to be
                # added here as well as at `expandable` above: `Page`'s `pageable`
                # field holds `Pageable`, an interface expansion now describes in
                # full, and a shape reported OPEN because of a field that is in fact
                # described is a gap report pointing at nothing.
                # F4 §5.2 (W25): where the declaring class file was read from. A
                # contract whose fields came from a neighbour's compiled output reads
                # exactly like one from this module unless the row says so.
                "origin_tier": tiers.get(base),
                "open": not expandable
                # F4 §5.2. An UNSCANNED superclass may declare fields nobody here can
                # see, so a subtype of one is not a complete description however many
                # fields of its own were read. Before this, a type extending a scanned
                # parent and one extending a vendor jar's base both read `open: false`.
                #
                # **Only where the fields came from BYTECODE.** A type owning a
                # `declared_shape` takes its contract from the schema and never from its
                # class file (the never-a-blend rule, D01 §3), so whatever its GENERATED
                # class happens to extend says nothing about the payload — every protobuf
                # message extends the runtime's `GeneratedMessage`, which is unscanned,
                # and counting it opened all four of the fixture's proto shapes while the
                # `.proto` describes them completely.
                or (descriptor is None and declared.reaches_an_unscanned_SUPERCLASS(base))
                or any(
                    held not in descriptors and not declared.of(held) and not accessors.of(held)
                    for held in referenced
                )
                # F4 §5.2 (W25). A field holding an UNBOUND type variable — a raw
                # `CommonResult`'s `data`, declared `T` and bound to nothing — gets no
                # shape id, because a variable's name means something only inside the
                # declaration that introduced it. The field is therefore undescribed,
                # and a shape with an undescribed field is OPEN. Without this the raw
                # envelope reported `open: false` while saying nothing about its own
                # payload, which is a stronger claim than the evidence supports.
                or any(_holds_an_undescribed_object(row) for row in rows),
            }
        )
        fields.extend(
            {"shape_id": shape_id, "ordinal": ordinal, **row} for ordinal, row in enumerate(rows)
        )

    # Fields first: the shape row is what marks a shape settled for a later
    # catalog, so it is written once its fields are in (D02 §5).
    workspace.derive("shape_fields", fields=fields)
    workspace.derive("shapes", shapes=shapes)
    return ExpandedShapes(unexpanded_types=tuple(unexpanded))


@dataclass(frozen=True)
class _Rules:
    """The catalog's serialisation and type knowledge, with every dotted name
    already converted — the binding seam, crossed once so no rule below has to
    remember which notation it is holding."""

    wrappers: list[dict[str, Any]]
    known_types: dict[str, dict[str, Any]]
    name_from: list[dict[str, str]]
    ignore: tuple[str, ...]
    default_strategy: str
    # D02 §2f's accessor prefixes (W26), each with the `wire_type` its return must
    # carry or None for "any". A model declaring none reads no accessor at all: the
    # fallback exists because a shape model said which methods name properties, and
    # inventing the prefixes here would be the same framework knowledge in code that
    # §1b moved out of forty-two catalogs.
    accessors: tuple[tuple[str, str | None], ...]
    # D02 §2e's three ways a catalog declares nullability, each already
    # converted at the binding seam like every other block here.
    nullable_annotations: tuple[str, ...]
    not_null_annotations: tuple[str, ...]
    # Scope annotation symbol -> the `nullable` value it implies for
    # everything the symbol it was found on claims (`_scope_prefixes`).
    scope_annotations: dict[str, bool]


def _origin_tiers(workspace: Workspace) -> dict[str, str]:
    """Where each declared type's class file was read from, by bare symbol (W25)."""
    tiers = {
        str(row["document_id"]): str(row["origin_tier"]) for row in workspace.query("documents")
    }
    return {
        bare_descriptor(str(row["symbol"])): tiers[str(row["document_id"])]
        for row in workspace.query("declared_symbols_with_documents")
        if str(row["document_id"]) in tiers
    }


def _type_parameters(workspace: Workspace) -> dict[str, list[str]]:
    """The formal type parameter NAMES each generic type declares, in declaration
    order, keyed by bare symbol (F4 §5.2, W25).

    Order is the binding: a reference's `arguments` are positional, so
    `CommonResult<UmsAdmin>` binds the first declared name to `UmsAdmin`. Only TYPE
    declarations are kept — a generic METHOD declares its own parameters under the same
    key, and binding a class's argument to a method's variable of the same name would
    substitute across two unrelated scopes.
    """
    found: dict[str, list[str]] = {}
    for row in workspace.query("type_parameters"):
        symbol = bare_descriptor(str(row["symbol"]))
        if "(" in symbol:
            continue
        # A list rather than an object, so `_json_object` does not fit — the same
        # absent-column reasoning applies and is spelled out here.
        raw = row["type_parameters"]
        declared = [] if raw is None else json.loads(str(raw))
        found[symbol] = [str(entry["name"]) for entry in declared if entry.get("name")]
    return found


def _substitution(names: list[str], arguments: list[str]) -> dict[str, str]:
    """`{variable name: bound shape id}`, positionally.

    A reference carrying fewer arguments than the declaration has parameters — a raw
    type — binds nothing rather than binding what it can: a partial binding would leave
    some fields substituted and others holding a variable, which reads as a real type to
    everything downstream.
    """
    if not names or len(names) != len(arguments):
        return {}
    return dict(zip(names, arguments, strict=True))


def _bound(members: list[dict[str, Any]], substitution: dict[str, str]) -> list[dict[str, Any]]:
    """`members` with the shape id's own type arguments substituted into each declared
    type — the one operation fields and accessors both need (W25 for the first, W26 for
    the second), written once rather than beside each caller.

    **Substitution is by variable NAME, across the whole ancestry.** `Page<T>` binds its
    own `T`, and `Slice`'s `getContent(): List<T>` is reached through the closure — so
    the binding lands because both declarations spell the variable `T`, which is what
    Spring's do. A hierarchy that RENAMES the variable (`interface Page<P> extends
    Slice<T>`) leaves `getContent`'s `T` bound to nothing, and an unbound variable gets
    no shape id at all (`_described`) — the field reads as undescribed and the shape
    stays open. That is the safe direction to be wrong in: the answer degrades to what
    it was before W26 rather than binding a variable to whatever sat at that position.
    """
    if not substitution:
        return members
    return [
        {**member, "returns": _substituted(member.get("returns"), substitution)}
        for member in members
    ]


def _substituted(returns: object, substitution: dict[str, str]) -> object:
    """One field's declared type with its variables replaced by what they are bound to.

    Recursive, because a variable can appear nested — `List<T>` inside `Page<T>`. The
    replacement carries the bound id in `symbol`; the wire attributes come from the
    variable's own reference, which is what the field's serialiser sees.
    """
    if not isinstance(returns, dict):
        return returns
    symbol = str(returns.get("symbol", ""))
    bound = substitution.get(symbol)
    replaced = dict(returns)
    if bound is not None:
        base, _ = bindings_of(bound)
        replaced["symbol"] = base
        replaced["arguments"] = returns.get("arguments") or []
        # `object` is what a bound type reference is; the variable's own `wire_type`
        # was already `object` for a class-bounded parameter, and this keeps a bound
        # scalar honest rather than asserting a wire mapping nobody measured.
        return replaced
    replaced["arguments"] = [
        _substituted(argument, substitution) for argument in (returns.get("arguments") or [])
    ]
    return replaced


def _rules_of(catalog: Catalog) -> _Rules:
    serialization = catalog.serialization
    nullability = catalog.nullability
    return _Rules(
        # Wrappers stay dotted: `root_type` crosses the same seam itself.
        wrappers=catalog.wrappers,
        known_types={_catalog_symbol(known["type"]): known for known in catalog.known_types},
        name_from=[
            {"annotation": _catalog_symbol(source["annotation"]), "arg": source["arg"]}
            for source in serialization.get("name_from", [])
        ],
        ignore=tuple(_catalog_symbol(name) for name in serialization.get("ignore", [])),
        # A catalog that declares no strategy renames nothing. Absence is not a
        # licence to invent one.
        default_strategy=serialization.get("default_strategy", "as_declared"),
        accessors=tuple(
            (str(entry["prefix"]), entry.get("wire_type"))
            for entry in serialization.get("accessors", [])
        ),
        nullable_annotations=tuple(
            _catalog_symbol(name) for name in nullability.get("nullable", [])
        ),
        not_null_annotations=tuple(
            _catalog_symbol(name) for name in nullability.get("not_null", [])
        ),
        scope_annotations={
            _catalog_symbol(entry["annotation"]): _SCOPE_MEANINGS[entry["means"]]
            for entry in nullability.get("scope", [])
        },
    )


# D02 §2e's one scope meaning. A catalog naming one that is not here is a
# broken file, and the KeyError above names it — the same discipline
# `_STRATEGIES` uses for serialisation strategies.
_SCOPE_MEANINGS: dict[str, bool] = {"not_null_by_default": False}


@dataclass
class _Fields:
    """Each type's wire fields — its own and its scanned ancestors' — resolved on the
    first ask and remembered (F4 §5.2).

    **A payload class extending another published only its OWN fields, and said the
    description was CLOSED.** Measured on `mall-admin`: `dto/OmsOrderDetail extends
    model/OmsOrder` published two fields (`orderItemList`, `historyList`) with
    `open: false`, while the parent declares 45 more — `id`, `orderSn`, `totalAmount` —
    every one of them serialised in the real response. `PmsProductParam` published 7 of
    50, `SmsCouponParam` 2 of 21; `jhipster-sample-app`'s `ManagedUserVM` published 1 of
    15; this repo's own fixture had `DetailedOrderResult` at 2 of 4. A wire contract
    missing most of the payload, published as complete, is the over-claim NFR-2 rates
    worst, and DR-5 links services on exactly this comparison.

    It is the same walk `_Accessors` already did for the accessor half, and the two
    halves disagreeing about whether inheritance counts was the whole defect: W26 gave
    accessors an ancestry and left fields without one.

    First declaration of a field NAME wins, so a subtype shadowing an ancestor's field
    takes precedence, and the walk order is JVMS 5.4.3.3's — the superclass chain before
    interfaces — so which declaration that is never depends on iteration order (NFR-1).
    """

    workspace: Workspace
    _cache: dict[str, list[dict[str, Any]]] = dataclasses.field(default_factory=dict)
    _read: tuple[dict[str, list[dict[str, Any]]], dict[str, list[tuple[str, str, bool]]]] | None = (
        dataclasses.field(default=None)
    )

    def of(self, base: str) -> list[dict[str, Any]]:
        """What `base` declares on the wire, its ancestors' included."""
        remembered = self._cache.get(base)
        if remembered is not None:
            return remembered
        own, ancestry = self._declared()
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for holder in _closure_of(base, ancestry):
            for field in own.get(holder, []):
                if field["name"] in seen:
                    continue
                seen.add(field["name"])
                rows.append(field)
        self._cache[base] = rows
        return rows

    def reaches_an_unscanned_SUPERCLASS(self, base: str) -> bool:
        """Whether the closure above stops at a SUPERCLASS this workspace did not scan.

        An unscanned superclass may declare fields nobody here can see, so a subtype of
        one cannot claim a complete description (F7 §8.4's `<<open>>`, applied to the
        shape rather than only to the diagram). Before this, `PmsProductParam extends
        PmsProduct` and `SomeDto extends VendorBase` were indistinguishable in the output:
        both read `open: false`, one correctly and one not.

        **`extends` only, and the exclusion is the difference between a useful gap report
        and a flood.** An unscanned INTERFACE cannot contribute a wire field: an
        interface's own fields are constants, which `_rows_of` drops as `static` — so
        implementing a MARKER interface says nothing about the payload. Counting it opened
        30 of `mall-admin`'s 107 shapes for one such interface with no members at all,
        which is an under-claim in the other direction and buries the four real
        unscanned-base cases.
        """
        _own, ancestry = self._declared()
        return any(
            kind == "extends" and not is_scanned
            for holder in _closure_of(base, ancestry)
            for _parent, kind, is_scanned in ancestry.get(holder, [])
        )

    def _declared(
        self,
    ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[tuple[str, str, bool]]]]:
        """Every field each type declares ITSELF, keyed by owner, plus the ancestry to
        walk them through. Read once per instance."""
        if self._read is not None:
            return self._read
        ancestry, _scanned = ancestry_of(self.workspace)
        self._read = (_declared_fields(self.workspace), ancestry)
        return self._read


def _declared_fields(workspace: Workspace) -> dict[str, list[dict[str, Any]]]:
    """Every field fact grouped by the type that declares it, in declaration
    order — the `ordinal` source (NFR-1)."""
    owners: dict[str, list[dict[str, Any]]] = {}
    for row in workspace.query("fields"):
        symbol = str(row["symbol"])
        # A symbol is module coordinates then a descriptor (D00 §5a); shape ids
        # and type references are both keyed on the descriptor alone.
        descriptor = bare_descriptor(symbol)
        owner = owner_of(descriptor)
        if owner is None:
            # A field with no owning type belongs to no shape.
            continue
        owners.setdefault(owner, []).append(
            {
                "symbol": symbol,
                "name": descriptor[len(owner) :].removesuffix("."),
                # `_json_object`, not a bare `json.loads`: the `fields` query projects
                # `signature -> 'returns'` with no NOT NULL predicate, so a fact that
                # omitted it reads back as SQL NULL and `str(None)` is `"None"` — the
                # exact crash this helper exists for, on the path that carries every
                # field in the workspace. Left bare until W26's review pointed out that
                # the helper was guarding the accessor path and not this one.
                "returns": _json_object(row["returns"]),
                "static": bool(row["static"]),
                "transient": bool(row["transient"]),
            }
        )
    return owners


def _json_object(value: object) -> dict[str, Any]:
    """One optional JSON column read as a mapping, empty when the fact omitted it.

    `str(None)` is `"None"`, which `json.loads` rejects — so a column a scanner left
    unwritten took the whole expansion pass down rather than reading as "nothing was
    said". Absence means the fact stated nothing, never that the pass should stop.
    """
    if value is None:
        return {}
    parsed = json.loads(str(value))
    return parsed if isinstance(parsed, dict) else {}


def _property_name(method: str, prefix: str) -> str | None:
    """The property a bean accessor names, or None when the method names none.

    Jackson's `legacyManglePropertyName`, which is what runs unless a module turns on
    `MapperFeature.USE_STD_BEAN_NAMING` — read from jackson-databind 2.22.1's own
    bytecode rather than from its documentation (§5.3):

    * a bare `get()`/`is()` names nothing (the length-equals-offset arm returns null),
      which is why `Streamable`'s own `get()` is not a `Slice`'s wire field;
    * the leading RUN of upper-case letters is lowercased, not just the first, and the
      remainder is then appended WHOLE — `getURL` is `url` and `getURLValue` is
      `urlvalue`, not `urlValue`. Lowercasing only the first character would publish
      `uRL`; stopping the run at the first letter of the next word would publish
      `urlValue`. Both are names no Jackson on either side of the wire writes, and
      `urlValue` is what this looks like it should produce, which is why it is pinned.
      (`URLValue` is the answer under `MapperFeature.USE_STD_BEAN_NAMING`, which is off
      by default and is a different strategy, not a different reading of this one.)
    """
    if not method.startswith(prefix):
        return None
    rest = method[len(prefix) :]
    if not rest:
        return None
    if rest[0].islower():
        return rest
    lowered: list[str] = []
    for index, character in enumerate(rest):
        if character.lower() == character:
            return "".join(lowered) + rest[index:]
        lowered.append(character.lower())
    return "".join(lowered)


@dataclass
class _Accessors:
    """Each type's bean accessors, its own and its scanned ancestors', resolved on the
    first ask and remembered (F4 §5.2, W26).

    **Nothing is read until something asks**, and `derive_shapes` runs once per catalog,
    so building the map eagerly scanned every method symbol and walked the whole type
    graph forty-odd times before knowing whether any answer was wanted. Measured on
    `mall-admin`: eager cost 15s of a 90s resolve.

    The saving is in the ORDER, not in rarity — this docstring used to add "which most
    catalogs never reach", and W26's review measured that as false. `of` is also asked
    from the `open` computation, once per referenced type that is neither declared nor a
    descriptor, which is the ordinary case on any corpus reporting unexpanded types. So
    the map really is built for most catalogs; it is built at the first ask rather than at
    construction, which is what the measurement above is about.

    **Resolved per type asked about rather than per type that DECLARES an accessor**, and
    that is why `of` walks rather than reading a prebuilt dict. A first attempt keyed the
    map on the types that declare one, which drops the purest form of the shape: a type
    that declares no accessor of its own and inherits every one of them — `interface
    OrderPage extends Page<OrderView> {}` — had no entry at all, so the fallback never
    fired for it. That is the same mistake `scripts/corpus_shapes.py` records making about
    resolvable calls, where "the owner declares at least one method of its own" dropped
    `PetType` and `Specialty` and understated the count by 27%. Membership in a declaring
    set is not the question; what the type PRESENTS is.
    """

    workspace: Workspace
    rules: "_Rules"
    # `dataclasses.field`, qualified: `field` is the loop variable two functions below,
    # and an unqualified import here shadows it.
    _cache: dict[str, list[dict[str, Any]]] = dataclasses.field(default_factory=dict)
    _read: tuple[dict[str, list[dict[str, Any]]], dict[str, list[tuple[str, str, bool]]]] | None = (
        dataclasses.field(default=None)
    )

    def of(self, base: str) -> list[dict[str, Any]]:
        """What `base` presents on the wire, in declaration order.

        First declaration of a property name wins, so an override on the subtype takes
        precedence over the ancestor it overrides — and the walk order is JVMS 5.4.3.3's
        (superclass chain before interfaces), so which declaration that is never depends
        on iteration order (NFR-1).
        """
        if not self.rules.accessors:
            return []
        remembered = self._cache.get(base)
        if remembered is not None:
            return remembered
        own, ancestry = self._declared()
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for holder in _closure_of(base, ancestry):
            for accessor in own.get(holder, []):
                if accessor["name"] in seen:
                    continue
                seen.add(accessor["name"])
                rows.append(accessor)
        self._cache[base] = rows
        return rows

    def _declared(
        self,
    ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[tuple[str, str, bool]]]]:
        """Every accessor each type declares ITSELF, keyed by owner, plus the ancestry to
        walk them through. Read once per instance.

        `symbol` is the accessor METHOD's symbol, not a field's, and that is deliberate:
        `_rows_of` looks up `annotations_of(symbol)`, and a naming or ignore annotation on
        a payload type with no fields is written on the getter. The method is where the
        annotation is, so the method is what is asked about.

        The query already returns only public, zero-argument methods that reach a wire
        type — the accessor's own definition, which a shape model can narrow but never
        widen. A return that reaches NO wire type is excluded there by its empty
        `wire_type` — the projection's own answer, which covers both the no-value return
        and the uninstantiable placeholder type beside it; the guard that tested the
        `returns` KEY instead let both through (W26 review). What is left here is what
        the DECLARED prefixes decide.
        """
        if self._read is not None:
            return self._read
        ancestry, _scanned = ancestry_of(self.workspace)
        own: dict[str, list[dict[str, Any]]] = {}
        for row in self.workspace.query("accessor_declarations"):
            if row["enclosing"] is None:
                continue
            # Optional on the fact and read back as SQL NULL when a scanner wrote none
            # (D00 §5a) — the ASM one always writes it for a method, but a reader that
            # assumed so crashed the whole pass on a fact that did not.
            modifiers = _json_object(row["modifiers"])
            # A bridge or other compiler-generated forwarder is not a method anyone wrote,
            # and it carries the same name as the one they did.
            if modifiers.get("static") or modifiers.get("synthetic"):
                continue
            returns = _json_object(row["signature"]).get("returns")
            if not isinstance(returns, dict):
                continue
            descriptor = bare_descriptor(str(row["symbol"]))
            owner = owner_of(descriptor)
            if owner is None:
                continue
            method = descriptor[len(owner) :].removesuffix(".").split("(")[0]
            for prefix, required_wire_type in self.rules.accessors:
                if (
                    required_wire_type is not None
                    and returns.get("wire_type") != required_wire_type
                ):
                    continue
                name = _property_name(method, prefix)
                if name is None:
                    continue
                own.setdefault(owner, []).append(
                    {
                        "symbol": str(row["symbol"]),
                        "name": name,
                        "returns": returns,
                        "static": False,
                        "transient": False,
                    }
                )
                break
        self._read = (own, ancestry)
        return self._read


def _closure_of(start: str, ancestry: dict[str, list[tuple[str, str, bool]]]) -> list[str]:
    """`start` and every ancestor above it, in JVMS 5.4.3.3's search order — the
    superclass chain to exhaustion, THEN the interfaces breadth-first.

    The order is the same one `dispatch.resolve` walks, and for the same reason W22's
    review found the hard way: answering from a depth-1 interface while a depth-2
    superclass holds the declaration recreates the defect one level deeper.
    """
    order: list[str] = []
    seen: set[str] = set()
    queue = [start]
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        order.append(current)
        parents = ancestry.get(current, [])
        queue = (
            [parent for parent, kind, _ in parents if kind == "extends"]
            + queue
            + [parent for parent, kind, _ in parents if kind == "implements"]
        )
    return order


def _declared_shapes(workspace: Workspace) -> dict[str, dict[str, Any]]:
    """Every `declared_shape` fact (2G design §3), keyed by its own `symbol` —
    the lookup a payload type reference meets once expansion reaches it.
    `bare_descriptor` normalizes the key the same way `_declared_fields`
    above normalizes its owners: a compiled shape's symbol is the generated
    class it travels as (bare today, since that is what `JvmGeneratedNaming`
    emits), but nothing here should depend on a naming implementation never
    prefixing one with module coordinates — normalizing both maps the same
    way is what makes "either map" below actually true rather than true by
    accident.

    A symbol may legitimately arrive more than once — a shared nested type is
    declared once per schema payload that inlines it (2G design §3's own
    interpreter docstring) — so later rows win; ordered by `(symbol,
    document_id)` first, the interpreter's own sort key, so which row that is
    never depends on read order (NFR-1).
    """
    return {
        bare_descriptor(str(row["symbol"])): {
            "evidence": str(row["evidence"]),
            "fields": json.loads(str(row["fields"])),
        }
        for row in workspace.query("declared_shapes")
    }


def _enum_symbols(workspace: Workspace) -> set[str]:
    """The declared types the facts call enumerations, as the descriptors a
    type reference is keyed on.

    Read once per pass rather than once per field, for the reason
    `_scope_prefixes` is: the answer is on the referenced type's own fact, not
    on the reference that reaches it.
    """
    return {bare_descriptor(str(row["symbol"])) for row in workspace.query("enum_types")}


def _rows_of(
    workspace: Workspace,
    rules: _Rules,
    scope_prefixes: list[tuple[str, bool]],
    declared: list[dict[str, Any]],
    enums: set[str],
    referenced: list[str],
) -> list[dict[str, object]]:
    """One projected row per field that reaches the wire, appending every shape
    the fields reference to `referenced`."""
    rows: list[dict[str, object]] = []
    for field in declared:
        # On no payload, whoever wrote it: a value bound to the type rather than
        # to an instance, or one the language declares as not serialized. Both
        # are ordinary declarations — the facts keep them — and only the
        # modifier the language recorded separates them from a contract field.
        # Filtered here rather than where the facts are grouped, so a type whose
        # every field is excluded stays a type the pass expanded rather than one
        # it reports as a gap. No row at all, for the reason the ignore rule
        # below gives.
        if field["static"] or field["transient"]:
            continue
        annotations = workspace.query("annotations_of", target=field["symbol"])
        # No row, not a row marked absent: DR-5 would compare a field the
        # catalog says is off the wire against a peer that correctly omits it.
        if any(use["annotation"] in rules.ignore for use in annotations):
            continue
        wire_name, evidence = _wire_name(rules, field["name"], annotations)
        # Rooted first: a field inside a declared envelope is described by what
        # the envelope holds, not by the envelope (D02 §2a).
        rooted = root_type(field["returns"], rules.wrappers)
        described = _described(rules, rooted.reference, enums, referenced)
        nullable, resolution = _nullability_of(
            rules,
            rooted.reference,
            described["nullable"],
            annotations,
            scope_prefixes,
            field["symbol"],
        )
        rows.append(
            {
                "wire_name": wire_name,
                # NULL: no schema format numbers a bytecode-derived field —
                # only a `declared_shape`'s own fields ever carry one.
                "field_number": None,
                "wire_type": described["wire_type"],
                "wire_format": described["wire_format"],
                # Presence machinery only, never nullability (D00 §5b): the
                # one source this phase has is the wrapper chain rooting
                # already recorded — an `optional` wrapper is what makes a
                # field omittable.
                "required": "optional" not in rooted.chain,
                "nullable": nullable,
                "resolution": resolution,
                "evidence": evidence,
                "item": _item_of(described),
            }
        )
    return rows


def _declared_rows_of(shape: dict[str, Any], referenced: list[str]) -> list[dict[str, object]]:
    """One projected row per `DeclaredFieldFact`, appending every shape a field
    references to `referenced` — `_rows_of`'s declared-shape counterpart.

    Nothing here is re-derived: `wire_name`, `wire_type`, `wire_format`,
    `field_number`, `required` and `nullable` already arrive in D00 §5b's wire
    vocabulary, projected by the interpreter that understands the schema
    format (2G design §3), so this only reshapes them into the row grammar
    `_rows_of` also produces — never re-answers a question the schema already
    settled. `resolution` is `"resolved"` throughout: a schema's own
    presence/nullability rule is as settled an answer as a known type's own
    override (`_nullability_of`'s same-named branch). `evidence` is the
    shape's own — `compiler` for a schema compiled into the artifact,
    `declared` for one read off a repository file (D00 §3) — one shape, one
    evidence tier, for every field it declares.
    """
    rows: list[dict[str, object]] = []
    for field in shape["fields"]:
        target = field.get("shape_ref")
        if target is not None:
            referenced.append(str(target))
        elif field.get("item") is not None:
            referenced.extend(_declared_referenced(field["item"]))
        rows.append(
            {
                "wire_name": field["wire_name"],
                "field_number": field.get("field_number"),
                "wire_type": field["wire_type"],
                "wire_format": field.get("wire_format"),
                "required": field["required"],
                "nullable": field["nullable"],
                "resolution": "resolved",
                "evidence": shape["evidence"],
                "item": _declared_item_of(field),
            }
        )
    return rows


def _declared_item_of(field: dict[str, Any]) -> str | None:
    """`_item_of`'s declared-shape counterpart: a collection field's `item`
    already carries D01 §5's recursive descriptor verbatim (the interpreter
    built it); a singular object field has no such descriptor of its own —
    only `shape_ref`, its bare symbol — so one is assembled here from the
    field's own wire columns, the same shape `_item_of` gives a bytecode
    object field."""
    if field.get("item") is not None:
        return json.dumps(field["item"], sort_keys=True, separators=(",", ":"))
    if field.get("shape_ref") is None:
        return None
    held = {
        "wire_type": field["wire_type"],
        "wire_format": field.get("wire_format"),
        "nullable": field["nullable"],
        "shape_id": field["shape_ref"],
    }
    return json.dumps(held, sort_keys=True, separators=(",", ":"))


def _declared_referenced(item: dict[str, Any]) -> list[str]:
    """Every shape a collection's `item` chain reaches, walking `item.item`
    the way `_shape_roots_of` (contracts.py) walks a finished descriptor
    column — needed here because a declared collection can nest (Avro's
    array-of-array), and each level's own `shape_id` must still reach the
    expansion queue."""
    found: list[str] = []
    node: dict[str, Any] | None = item
    while node is not None:
        shape_id = node.get("shape_id")
        if shape_id is not None:
            found.append(str(shape_id))
        held = node.get("item")
        node = held if isinstance(held, dict) else None
    return found


def _wire_name(
    rules: _Rules, declared_name: str, annotations: list[dict[str, object]]
) -> tuple[str, str]:
    """The wire name and the evidence behind it (D02 §2f). `wire_name` is the
    identity (D01 §5), so the source name is only ever the fallback."""
    for source in rules.name_from:
        use = next((a for a in annotations if a["annotation"] == source["annotation"]), None)
        given = json.loads(str(use["args"])).get(source["arg"]) if use and use["args"] else None
        if given:
            return str(given), "compiler"
    # A strategy is a declaration a module's own configuration may override, so
    # a name derived from it is never presented as observed.
    return _STRATEGIES[rules.default_strategy](declared_name), "declared"


def _separated(name: str, separator: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", separator, name).lower()


# D02 §2f's four strategies. A catalog naming one that is not here is a broken
# file, and the KeyError names it.
_STRATEGIES: dict[str, Callable[[str], str]] = {
    "as_declared": lambda name: name,
    "snake_case": lambda name: _separated(name, "_"),
    "kebab_case": lambda name: _separated(name, "-"),
    "upper_camel": lambda name: name[:1].upper() + name[1:],
}

# The two wire types that hold something other than themselves (D00 §5b).
_COLLECTIONS = ("array", "map")


def _described(
    rules: _Rules, reference: dict[str, Any], enums: set[str], referenced: list[str]
) -> dict[str, Any]:
    """The recursive `{wire_type, wire_format, nullable, shape_id?, item?}`
    descriptor for one type reference (D01 §5)."""
    known = rules.known_types.get(reference["symbol"])
    if known is not None:
        # Mapped and never expanded: a type the serialiser turns into a scalar
        # has no field list on the wire, and expanding it would invent one
        # (D02 §2g). A known type may also declare its own `nullable` (D02
        # §2g) — a wrapper type such as protobuf's, whose wire behaviour the
        # reference's own flag does not describe — which then overrides the
        # reference's answer for this field or element.
        return {
            "wire_type": known["wire"],
            "wire_format": known.get("format", ""),
            "nullable": known.get("nullable", reference["nullable"]),
        }
    described = {
        "wire_type": reference["wire_type"],
        "wire_format": reference["wire_format"],
        "nullable": reference["nullable"],
    }
    if reference["symbol"] in enums:
        # A closed set of constants is one value on the wire, which is why D00
        # §5b keeps `enum` in the vocabulary — so it is mapped and never
        # expanded, exactly as a known type is. Expanded, its constants become
        # fields of a payload nobody sends; left as the `object` the reference
        # says it is, it marks its owner open and is reported as a gap the
        # catalog cannot close, because nothing is missing. The overridden
        # answer comes from the referenced type's own construct kind, which is
        # fact data every language produces, not knowledge of one of them.
        return {**described, "wire_type": "enum"}
    if described["wire_type"] in _COLLECTIONS:
        # What a collection holds is its last type argument: a keyed
        # collection's keys are strings on the wire, so only its value
        # argument describes the payload, and a sequence has just the one.
        if reference["arguments"]:
            described["item"] = _described(rules, reference["arguments"][-1], enums, referenced)
    elif described["wire_type"] == "object":
        # F4 §5.2 (W25). The id carries the BOUND ARGUMENTS where the reference has
        # any, so `CommonResult<UmsAdmin>` and `CommonResult<List<UmsRole>>` are two
        # shapes rather than one envelope standing for both. Identity is the point:
        # DR-5 gates stitching on payload equality, and one id for every
        # parameterisation says two services exchange the same payload when they do
        # not. Measured on `mall-admin`: 59 distinct parameterisations collapsed onto
        # one id.
        #
        # A reference with NO arguments keeps the bare symbol, unchanged — 100 of
        # `mall-admin`'s 160 handlers return raw `CommonResult`, which states no
        # payload type, and inventing one would be the fabrication §8 forbids.
        if not names_a_type(str(reference["symbol"])):
            # An UNBOUND type variable. `CommonResult`'s `data` is declared `T`, and a
            # raw `CommonResult` binds nothing — so this field holds a variable, not a
            # type. Rooting it would publish `shape_id: "T"`, and every unrelated `T`
            # in the module collides onto that one id: one shape claiming to describe
            # several unrelated payloads, which is this module's own stated rule
            # (`_body_reference`, §8.1 rule 2). The field keeps its wire type and gets
            # no shape, which marks its owner OPEN — the honest answer, and visible.
            #
            # Newly reachable with W24/W25: before the module edge was crossed, a raw
            # `CommonResult` had no fields at all, so nothing here could hold a variable.
            return described
        described["shape_id"] = parameterised_id(reference)
        referenced.append(described["shape_id"])
    return described


def parameterised_id(reference: dict[str, Any]) -> str:
    """A shape id carrying the reference's own bound arguments (F4 §5.2).

    `com/x/CommonResult#<com/x/UmsAdmin#>`, nested for a nested argument. No spaces,
    deliberately: `bare_descriptor` splits a symbol on its last space to drop module
    coordinates, and an id containing one would be silently truncated wherever that
    helper is applied to a shape id.

    A type VARIABLE argument contributes its own name — an unbound `CommonResult<T>`
    is a distinct thing from `CommonResult`, and the 10 such handlers on `mall-admin`
    should not silently join either group.
    """
    arguments = reference.get("arguments") or []
    symbol = str(reference["symbol"])
    if not arguments:
        return symbol
    return symbol + "<" + ",".join(parameterised_id(argument) for argument in arguments) + ">"


def bindings_of(shape_id: str) -> tuple[str, list[str]]:
    """A parameterised id split back into its base symbol and its arguments.

    The inverse of `parameterised_id`, and it has to be a parse rather than a lookup
    because the id is what travels: a `shapes` row, an endpoint's payload column and an
    exported bundle carry the id and nothing beside it."""
    if not shape_id.endswith(">") or "<" not in shape_id:
        return shape_id, []
    base, _, rest = shape_id.partition("<")
    inner = rest[:-1]
    arguments: list[str] = []
    depth = 0
    current = ""
    for character in inner:
        if character == "<":
            depth += 1
        elif character == ">":
            depth -= 1
        if character == "," and depth == 0:
            arguments.append(current)
            current = ""
            continue
        current += character
    if current:
        arguments.append(current)
    return base, arguments


def _holds_an_undescribed_object(row: dict[str, Any]) -> bool:
    """Whether a field row holds an object this expansion could not name.

    An `object` field normally carries a `shape_id` pointing at the shape holding its
    fields. One that does not is a field whose type we have no name for — today, an
    unbound type variable — and its owner cannot claim to be a closed description.

    **Through the element chain, not only at the top.** W25 tested the row's own
    `wire_type` alone, so a field declared `List<T>` on a raw type came out `array`
    holding an undescribed `object` and its owner was reported CLOSED — a complete
    description of a payload whose element type is unnamed. A generic type declaring a
    collection of its own parameter is the ordinary source that reaches it, and W26's own
    `Slice<T>.getContent()` is the same shape one hierarchy up. An over-claim is the direction NFR-2 rates worst, and this
    one also hides itself: `open` is what puts a shape in the gap report at all.
    """
    # `_item_of` returns the descriptor itself for an object that HAS a `shape_id`, so
    # a described object always carries an item. An `object` row with none is precisely
    # the case where nothing could be named.
    if row.get("wire_type") == "object" and row.get("item") is None:
        return True
    held = row.get("item")
    if held is None:
        # An ARRAY with no element descriptor is a RAW collection — `List` written with
        # no type argument — and its element type is exactly as unnamed as the unbound
        # variable above (W26 review). Every other `wire_type` genuinely holds nothing:
        # a `string` or an `integer` has no element to describe and is complete as it is.
        # Zero live instances across the fixture and the three corpora, so this closes a
        # hole rather than changing a published answer.
        return bool(row.get("wire_type") == "array")
    return _describes_no_object(json.loads(str(held)))


def _describes_no_object(described: dict[str, Any]) -> bool:
    """Whether an `item` descriptor, or anything it holds in turn, describes no object it
    could name — `List<List<T>>` is why this recurses rather than looking once."""
    if described.get("wire_type") == "object" and "shape_id" not in described:
        return True
    held = described.get("item")
    if held is None:
        # The nested twin of the raw-collection case above: `List<List>` is as unnamed
        # one level down as `List` is at the top.
        return bool(described.get("wire_type") == "array")
    return isinstance(held, dict) and _describes_no_object(held)


def _item_of(described: dict[str, Any]) -> str | None:
    """What the field holds, as JSON — a collection's element, or the shape an
    object field points at (ruling F3). Without it nothing links a field to the
    shape carrying its fields, and one `wire_type` cannot tell a sequence of
    strings from a sequence of records.

    D01 §5 states one grammar, `{wire_type, wire_format, nullable, shape_id?,
    item?}`, so an object field's descriptor is the whole one and not a shorter
    variant: two shapes of `item` would make every consumer detect which it was
    holding before it could read a single key.
    """
    held = described.get("item")
    if held is None and "shape_id" in described:
        held = described
    return None if held is None else json.dumps(held, sort_keys=True, separators=(",", ":"))


def _content_hash(rows: list[dict[str, object]]) -> str:
    """Change detection, never identity (ruling F1): `item` points at other
    shapes by `shape_id`, so a content-derived identity for a type that refers
    to itself would depend on itself. Taken over the rows in order, because
    two runs that disagree on field order are two different answers (NFR-1)."""
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "md5:" + hashlib.md5(payload, usedforsecurity=False).hexdigest()
