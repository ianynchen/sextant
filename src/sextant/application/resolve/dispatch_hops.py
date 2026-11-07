"""A dispatch send lands on the handlers its value's key reaches (spec 2026-11-05 §1, from
the actor design of 2026-11-04 §3c, §3d items 3, 4 and 7).

A send names no method of the receiver: it hands a value to a framework or a channel, and
the registrations pick the handler by the value's class (`dispatch_registrations.reached_by`,
each registration under its catalog's match rule). `call_edges` therefore stops at the
library's send method, and the trace with it. This pass reads each declared send's value and
writes, into `hops`, one row per handler that value reaches, keyed at the send's own call
site, so the trace walks on into the handler exactly as it walks a gRPC self-call
(`resolve/rpc_hops.py`, the table's other writer). A dispatch is a hop, never an endpoint row.
Nothing here names a framework type: every owner, method and argument position is the
catalog's (`Catalog.dispatch_sends`), and every row carries that catalog's `protocol`.

## What the value is (D00 §5's argument kinds)

- `instance` — the class constructed there.
- `enum`, or a static `field` of a declared type — a constant, read by identity (rule 8):
  its class (an `enum` constant's own owner, a field's declared type) and its own symbol, so
  it reaches a value registration for that constant and a class registration for its class.
  `path` is the constant's symbol.
- `lambda` — a function that builds the value (an ask's request): each class its body
  returns, one per return (a `merge` of several `new`s, javac's ternary, is one per
  candidate); a constructor reference (`Get::new`) returns its own owner.
- `unresolved` with a `source` — a call's result (a static factory, `Event.instance()`): where
  the call is static and the module declares the method, each class its body returns, read
  as a lambda's are (ruled 2026-11-02: follow the code we have). Any other call (an instance
  call, `new E().setA(a)`, a library method), and a return the body does not name, is read
  by the call's DECLARED return type (its descriptor's).
- `parameter`, or an instance `field` — the parameter's or the field's declared type.
- anything else (an array element, a `merge`, a primitive or array declared type) — **not
  read**: one row with no `path` and no `handler`. Never a hop to every handler.

## A value read by its declared type (ruled 2026-11-05, final review I-1)

A declared type `T` says the value is a `T` or a subtype of one, never which. So every
registration of `T` or a supertype of it is certainly reached under `match: all` and `one`,
and the hop is true; a registration of a subtype only is missed, never invented. Under
`first` it holds only in a group where no case names a strict subtype of `T`
(`dispatch_registrations.certain_cases`): elsewhere the value may be the subtype a case before
takes, so that group gives the send's one not-read row instead of a guessed hop.

A value no registration takes (a reply its asker reads off a future, a command told to a
system actor) is one row with its class and no `handler`: the trace stops there, naming it.

## A send keyed by its object (`dispatch: {key: object}`, spec 2026-11-05 §1, §3)

A catalog whose key is the OBJECT (a queue, a channel) hands the value to whatever takes from
the same object: the send's receiver is followed to the call that made it
(`dispatch_registrations.ObjectKeys`, the walk the receive sites' keys came from), and the send
is one row per receive registration of its mechanism with that same `key_object`, the value's
class never asked. `path` is the object, `<caller>#<ordinal>` of the call that made it. An
object nothing takes from is one row with that path and no handler; a path on which the object
was not read (a queue from outside the module) is one row with no path and no handler —
never a hop to every receive site.

## A handler that delivers continues

A registration declared with `returns_value` (`messageAdapter`'s function, an ask's reply
mapper) does not handle its value: it maps it to another, handed to its own receiver. Each
class such a handler returns is a hop from that return's own `new` — the call site javac emits
for it, where the value comes to exist — so a two-`return` mapper gives two. A constructor
reference has no `return` of its own; its hop is at its super-constructor call, the first
thing it runs.

## An inbound key row names the same handlers (`record_key_handlers`, 2026-11-04 §3d item 6)

A key (a producer call taking both, `create(Command.class, "stock")`) is an address and a
class. Its inbound row's handlers are every registration a value of that class, any subtype
of it, reaches (`dispatch_registrations.served_cases`, the hop rule asked once per candidate
class), one row per handler as a route with two handlers is two rows. The class is read where
the address is, in the same walk: the row's `channel_via` entry for the producer names its
`class_arg`, and the walk answers the key's name carrying the class that same call names on
the same path (`values.Answer.carried_class`). A class reaching nothing, or not read, leaves
one row with `handler` NULL; the registering method `single_call` wrote is never kept. A row
whose catalog reads no class (a pub-sub subscription, which takes any value) is not touched.

## Cost (GUIDELINES §8.7)

One lookup per declared send owner in the shared call-site index, one read each of
`dispatch_registrations`, `method_returns` (fact, cached per load) and, only where a send
passes a field, `fields`. Rows are written once. The key rows add, per catalog whose rows
name a `class_arg`, one value walk per registering call site (on the resolve's shared value
index) and one read of `endpoints`; a module registering no key pays nothing past the
call-site index lookup.
"""

import json
from collections.abc import Mapping
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.dispatch import dispatch_of
from sextant.application.resolve.dispatch_registrations import (
    ObjectKeys,
    certain_cases,
    dispatch_mechanism,
    reached_by,
    served_cases,
)
from sextant.application.resolve.shapes.arguments import (
    _arg_at,
    call_site_index,
    channel_of_answer,
    declared_call_sites,
)
from sextant.application.resolve.values import cached_value_index, resolve_site
from sextant.domain.closed_sets import Direction
from sextant.domain.symbols import (
    bare_descriptor,
    member_name,
    method_descriptor,
    owner_of,
    returned_type,
    slot_of_type,
    type_descriptor,
)

# The constructor name D00 §5 normalises every language's to.
_CONSTRUCTOR = "<init>"
# A conformance entry's subtype meaning every type (`type-models/conformance.yml`): its
# supertype is the root type, a supertype of every class.
_EVERY_TYPE = "*"
# The ancestry link naming a type's superclass (`dispatch.ancestry_of`): its target is a class.
_EXTENDS = "extends"
# A JVM descriptor slot naming a class or interface type (JVMS 4.3.2): the only declared type
# a value is read by.
_REFERENCE = "L"
# The call form that names exactly the method it runs (`dispatch.py`): no override can run
# in its place, so its body is the value's producer.
_STATIC = "static"
# The `single_call` row word whose entries name the producer of an inbound key, and the
# entry word naming which of that producer's arguments holds the key's class.
_CHANNEL_VIA = "channel_via"
_CLASS_ARG = "class_arg"
# The `dispatch.key` naming a channel object rather than the value's class.
_OBJECT_KEY = "object"
# A value read, as `(class, constant, call site in its method, what was not read, declared)`:
# the class and the constant's own symbol where read, else `unread` names the argument kind;
# `declared` where the class is a declared type, the value that class or any subtype of it.
_Value = tuple[str | None, str | None, int | None, str | None, bool]


def record_dispatch_hops(workspace: Workspace, catalogs: list[Catalog]) -> None:
    """Inserts the hops of every declared send, and of every delivering handler, into
    `hops`. Inserts only: the pipeline resets the table once before both of its writers
    (spec 2026-11-04 §3d item 7)."""
    sending = [catalog for catalog in catalogs if catalog.dispatch_sends]
    delivering = [
        catalog
        for catalog in catalogs
        if any(registration["returns_value"] for registration in catalog.dispatch_registrations)
    ]
    if not sending and not delivering:
        return
    reading = _Reading(workspace, catalogs[0].type_model)
    rows: dict[tuple[Any, ...], dict[str, Any]] = {}
    for catalog in sending:
        if (catalog.dispatch or {}).get("key") == _OBJECT_KEY:
            objects = ObjectKeys(workspace, catalog)
            for site, _ in declared_call_sites(workspace, catalog.dispatch_sends):
                for row in reading.object_hops(
                    site, objects.of(site), catalog.protocol, dispatch_mechanism(catalog)
                ):
                    rows.setdefault(tuple(row.values()), row)
            continue
        for site, send in declared_call_sites(workspace, catalog.dispatch_sends):
            argument = _arg_at(site["arguments"], send["value_arg"])
            for value in reading.sent(argument, str(site["caller"])):
                for row in reading.hops(
                    site["caller"],
                    site["ordinal"],
                    value,
                    catalog.protocol,
                    dispatch_mechanism(catalog),
                ):
                    rows.setdefault(tuple(row.values()), row)
    protocols = sorted({catalog.protocol for catalog in delivering})
    if len(protocols) > 1:
        raise CatalogError(
            f"loading catalogs {', '.join(str(c.source) for c in delivering)}: delivering "
            f"handlers are declared under protocols {protocols}; a handler's own delivery is "
            f"written under one (spec 2026-11-04 §3d item 4)"
        )
    for handler, mechanism in reading.delivering_handlers() if protocols else []:
        for value in reading.returned(handler):
            for row in reading.hops(handler, value[2], value, protocols[0], mechanism):
                rows.setdefault(tuple(row.values()), row)
    if rows:
        workspace.derive("hops_insert", rows=list(rows.values()))


def record_key_handlers(workspace: Workspace, catalogs: list[Catalog]) -> None:
    """Names each inbound key row's handlers (spec 2026-11-04 §3a, §3d item 6): a row its
    catalog reads a key class for (a `channel_via` entry's `class_arg`) becomes one row per
    handler that class reaches, as a route with two handlers is two rows; one row with `handler` NULL
    where it reaches none or the class was not read. The registering method `single_call`
    wrote is never one of them: registering a key is not handling what it addresses.

    Replaces rows, so it runs after `record_self_calls`, which reads "served" off these rows
    while every one of them still has its registering method as `handler`: a key no handler
    serves is still served here, and a call naming it stays a hop."""
    keyed = [catalog for catalog in catalogs if _keyed_methods(catalog)]
    if not keyed:
        return
    reading = _Reading(workspace, keyed[0].type_model)
    dropped: list[dict[str, Any]] = []
    rows: dict[tuple[Any, ...], dict[str, Any]] = {}
    for catalog in keyed:
        classes = _key_classes(workspace, catalog)
        for row in workspace.query("endpoints"):
            if (
                row["catalog_id"] != catalog.id
                or row["protocol"] != catalog.protocol
                or row["direction"] != str(Direction.INBOUND)
            ):
                continue
            registering, path = row["handler"], row["path"]
            read = classes.get(
                (
                    None if registering is None else str(registering),
                    None if path is None else str(path),
                ),
                {None},
            )
            handlers = sorted(
                {
                    handler
                    for key_class in read
                    for handler in reading.key_handlers(key_class, dispatch_mechanism(catalog))
                },
                key=lambda handler: (handler is None, handler),
            )
            dropped.append({"row_id": row["row_id"]})
            for handler in handlers or [None]:
                kept = {column: row[column] for column in _KEPT_COLUMNS} | {"handler": handler}
                rows.setdefault(tuple(kept.values()), kept)
    if not dropped:
        return
    workspace.derive("self_call_endpoints_drop", rows=dropped)
    workspace.derive("endpoint_rows_follow")
    if rows:
        workspace.derive("call_endpoints", rows=list(rows.values()))


# The columns of an `endpoints` row `call_endpoints` writes, which a key row keeps whole but
# for its `handler` (`derive_call_endpoints.sql`'s `$rows`). Nothing after the engines and
# before this pass sets another column on a `single_call` row.
_KEPT_COLUMNS = (
    "protocol",
    "direction",
    "method",
    "path",
    "handler",
    "caller",
    "peer",
    "handler_signature",
    "resolution",
    "evidence",
    "catalog_id",
    "request_shape",
    "response_shape",
    "consumes",
    "produces",
    "path_kind",
    "method_kind",
)


def _keyed_methods(catalog: Catalog) -> list[dict[str, Any]]:
    """The `single_call` method rows whose key's class is read: every INBOUND row of a catalog
    one of whose `channel_via` entries names `class_arg` (its shape checked where the loader
    hoists it). `class_arg` is a fact about the producer, so it sits on every entry naming
    that producer — outbound rows' too — and reaches an inbound row through the hoisted table
    even where the row names only the key's first step (`init(Entity.of(KEY, …))`). Each such
    inbound row must read its key at `channel_arg`: the pass replaces every inbound row of the
    catalog, and a row with no key position would lose its handler to a class nothing read."""
    methods = catalog.matches.get("methods") or []
    if not any(_reads_class(method) for method in methods):
        return []
    keyed = []
    for method in methods:
        if method.get("direction", catalog.direction) != str(Direction.INBOUND):
            continue
        if not isinstance(method.get("channel_arg"), int):
            raise CatalogError(
                f"loading catalog {catalog.source}: `{method.get('name')}` is an inbound row "
                f"reading no `channel_arg` in a catalog whose keys name their class "
                f"(`{_CLASS_ARG}`): the class is read where an inbound key is "
                f"(spec 2026-11-04 §3d item 6)"
            )
        keyed.append(method)
    return keyed


def _reads_class(method: Mapping[str, Any]) -> bool:
    via = method.get(_CHANNEL_VIA)
    return isinstance(via, list) and any(
        isinstance(entry, dict) and _CLASS_ARG in entry for entry in via
    )


def _key_classes(
    workspace: Workspace, catalog: Catalog
) -> dict[tuple[str | None, str | None], set[str | None]]:
    """Each inbound key a declared call registers, `(registering method, key)`, mapped to the
    classes read for it (None: not read).

    ONE walk per registering call site, exactly the one `single_call` read the row's `path`
    with (the catalog's identity table, `channel_via` hoisted into it): where it reaches the
    producing call, the entry naming `class_arg` makes it answer the key's name carrying the
    class that same call names, on the same path (`values.Answer.carried_class`). So a key
    and its class are one answer, and two keys built in one helper stay apart without any
    pairing afterwards."""
    values = cached_value_index(
        workspace,
        catalog.not_hand_offs,
        catalog.hand_off_effects,
        catalog.bean_models,
        catalog.value_annotations,
        returns_arguments=catalog.returns_arguments,
    )
    owner = type_descriptor(str(catalog.matches["owner"]))
    classes: dict[tuple[str | None, str | None], set[str | None]] = {}
    for method in _keyed_methods(catalog):
        slot = int(method["channel_arg"])
        entry = {"owner": owner, "method": method["name"], "descriptor": method["descriptor"]}
        for site, _ in declared_call_sites(workspace, [entry]):
            # No path at all is one key, None: the one row `single_call` writes for such a site.
            answers = [
                binding.slots.get(slot)
                for binding in resolve_site(workspace, site, values, catalog.value_model)
            ] or [None]
            for answer in answers:
                name = channel_of_answer(answer)[1]
                key_class = None if answer is None else answer.carried_class
                classes.setdefault((str(site["caller"]), name), set()).add(key_class)
    return classes


class _Reading:
    """The reads a send's value and a handler's return need, taken once per resolve."""

    def __init__(self, workspace: Workspace, conformance: list[dict[str, Any]]) -> None:
        self._workspace = workspace
        self._cases = workspace.query("dispatch_registrations")
        dispatch = workspace.once(dispatch_of)
        self._supertypes = {
            child: {ancestor for ancestor, _, _ in ancestors}
            for child, ancestors in dispatch.ancestors.items()
        }
        # The declared conformance of types nothing scans (`type-models/`, the same table
        # every catalog carries as `type_model`): a value's ancestry reaches past a JDK
        # class to a registration of its supertype. The entry whose subtype is `*` is the
        # root type every class conforms to (JLS 4.10.2), which no fact names — a class
        # extending it directly carries no `superclass` (D00 §5a) — so it is added to every
        # value's class as it is asked (`_rooted`): a listener of the root receives them all.
        self._roots: set[str] = set()
        for entry in conformance:
            if entry["subtype"] == _EVERY_TYPE:
                self._roots.add(type_descriptor(entry["supertype"]))
                continue
            self._supertypes.setdefault(type_descriptor(entry["subtype"]), set()).add(
                type_descriptor(entry["supertype"])
            )
        self._returns: dict[str, list[Any]] = {}
        for row in workspace.query("method_returns"):
            value = None if row["value"] is None else json.loads(str(row["value"]))
            self._returns.setdefault(str(row["method"]), []).append(value)
        self._by_bare: dict[str, str] = {
            bare_descriptor(method): method for method in self._returns
        }
        self._sites = workspace.once(call_site_index).by_caller
        self._field_types: dict[str, tuple[str | None, bool]] | None = None
        self._parameter_types: dict[str, list[str | None]] | None = None
        self._known_classes: frozenset[str] | None = None
        # `key_handlers`' per-run inputs (GUIDELINES §8.7): each value registration's constant's
        # class, read once, and each key class's answer, so a key class many inbound rows
        # share walks the module's types once rather than once per row.
        self._constants: dict[str, str | None] | None = None
        self._key_handlers: dict[tuple[str | None, str], list[str | None]] = {}
        # Each mechanism's registrations (`dispatch_registrations.dispatch_mechanism`): a send
        # or an inbound key is asked only of its own catalog's, never of another framework's.
        self._by_mechanism: dict[str, list[dict[str, Any]]] = {}
        for case in self._cases:
            self._by_mechanism.setdefault(str(case["mechanism"]), []).append(case)

    def key_handlers(self, key_class: str | None, mechanism: str) -> list[str | None]:
        """The handlers a value of `key_class`, any subtype of it, reaches
        (`dispatch_registrations.served_cases`); a registration whose handler was not read
        gives None, as for a hop. Nothing for a class not read."""
        if (key_class, mechanism) not in self._key_handlers:
            self._rooted(key_class)
            reached = served_cases(
                self._by_mechanism.get(mechanism, []),
                key_class,
                self._supertypes,
                self._constant_classes(),
            )
            self._key_handlers[(key_class, mechanism)] = list(
                dict.fromkeys(case["handler"] for case in reached)
            )
        return self._key_handlers[(key_class, mechanism)]

    def _classes(self) -> frozenset[str]:
        """The types known to be classes, not interfaces, read once per resolve: each type the
        module declares (`Dispatch.scanned`, its own class files, never a dependency's header)
        that is no interface (`interface_symbols`), and each type some class extends (a
        superclass, D00 §5a; only a class is extended). Any other type, a dependency's
        interface among them, may be an interface; `certain_cases` treats it so."""
        if self._known_classes is None:
            dispatch = self._workspace.once(dispatch_of)
            interfaces = {
                bare_descriptor(str(row["symbol"]))
                for row in self._workspace.query("interface_symbols")
            }
            extended = {
                ancestor
                for ancestors in dispatch.ancestors.values()
                for ancestor, kind, _ in ancestors
                if kind == _EXTENDS
            }
            self._known_classes = frozenset((dispatch.scanned - interfaces) | extended)
        return self._known_classes

    def _constant_classes(self) -> dict[str, str | None]:
        """Each value registration's constant's class, read once per resolve."""
        if self._constants is None:
            self._constants = {
                str(case["key_value"]): self._constant_class(str(case["key_value"]))
                for case in self._cases
                if case["key_value"] is not None
            }
        return self._constants

    def _constant_class(self, symbol: str) -> str | None:
        """A value registration's constant's class: the static field's declared type (an enum
        constant's is its enum), None where the field is not in the module's facts."""
        declared, static = self._field_type(symbol)
        return declared if static else None

    def _rooted(self, key_class: str | None) -> None:
        """Gives `key_class` the root type among its supertypes (JLS 4.10.2), once."""
        if key_class is not None and self._roots and key_class not in self._roots:
            self._supertypes.setdefault(key_class, set()).update(self._roots)

    def delivering_handlers(self) -> list[tuple[str, str]]:
        """Each delivering handler with its registration's mechanism, whose registrations
        the values it returns are asked of."""
        return sorted(
            {
                (str(case["handler"]), str(case["mechanism"]))
                for case in self._cases
                if case["delivers"] and case["handler"]
            }
        )

    def sent(self, argument: Mapping[str, Any] | None, caller: str) -> list[_Value]:
        """What a send's value argument is, one entry per class it can be. `caller` is the
        method making the send, whose call sites an `unresolved` value's `source` names."""
        kind = None if argument is None else argument.get("kind")
        if argument is None or kind is None:
            return [(None, None, None, "absent", False)]
        symbol = argument.get("symbol")
        if kind == "unresolved" and argument.get("source") is not None:
            return self._made_by_a_call(caller, argument)
        if kind == "instance" and symbol is not None:
            return [(str(symbol), None, None, None, False)]
        if kind == "enum" and symbol is not None:
            return [(owner_of(str(symbol)), str(symbol), None, None, False)]
        if kind == "field" and symbol is not None:
            declared, static = self._field_type(str(symbol))
            if declared is not None and static:
                return [(declared, str(symbol), None, None, False)]
        if kind == "lambda" and symbol is not None:
            if member_name(str(symbol)).startswith(f"{_CONSTRUCTOR}("):
                return [(owner_of(str(symbol)), None, None, None, False)]
            body = self._by_bare.get(str(symbol))
            if body is None:
                return [(None, None, None, kind, False)]
            return [(*one[:2], None, *one[3:]) for one in self.returned(body)]
        declared_type = self._declared(caller, argument)
        if declared_type is not None:
            return [(declared_type, None, None, None, True)]
        return [(None, None, None, str(kind), False)]

    def _made_by_a_call(self, caller: str, argument: Mapping[str, Any]) -> list[_Value]:
        """A value a call in `caller` returned (D00 §5: an `unresolved` argument's `source` is
        the producing call's `result`), read through that call's body where the call names
        the method it runs and the module declares its body: a static call (no override can
        run instead, `dispatch.py`), each class the method returns (`returned`). Anything
        else — an instance call (`new E().setA(a)`), a library method — and a return the body
        does not name is read by the call's declared return type (`_declared`); not read
        where that is no class either (spec 2026-11-02 rule 2: unknown only where the code is
        absent)."""
        source = argument["source"]
        made = next(
            (
                site
                for site in self._sites.get(caller, ())
                if site.get("result") == source and site.get("invoke_kind") == _STATIC
            ),
            None,
        )
        body = (
            None
            if made is None or made.get("name") is None or made.get("descriptor") is None
            else self._by_bare.get(
                method_descriptor(
                    bare_descriptor(str(made["owner"])),
                    str(made["name"]),
                    str(made["descriptor"]),
                )
            )
        )
        declared_type = self._declared(caller, argument)
        by_type: _Value = (
            (None, None, None, "unresolved", False)
            if declared_type is None
            else (declared_type, None, None, None, True)
        )
        if body is None:
            return [by_type]
        return [
            by_type if one[3] is not None else (*one[:2], None, *one[3:])
            for one in self.returned(body)
        ]

    def _declared(self, method: str, value: Mapping[str, Any]) -> str | None:
        """The declared type of a value `method` holds (ruled 2026-11-05, final review I-1): a
        call's result, its descriptor's return type; a `parameter`, the method's own declared
        parameter type; a `field`, the field's declared type. None for any other kind, and
        for a declared type that is not a class or interface (a primitive, an array)."""
        kind = value.get("kind")
        declared: str | None = None
        if kind == "unresolved" and value.get("source") is not None:
            made = next(
                (
                    site
                    for site in self._sites.get(method, ())
                    if site.get("result") == value["source"]
                ),
                None,
            )
            descriptor = None if made is None else made.get("descriptor")
            declared = None if descriptor is None else returned_type(str(descriptor))
        elif kind == "parameter" and value.get("value") is not None:
            parameters = self._parameters(method)
            index = int(value["value"])
            declared = parameters[index] if 0 <= index < len(parameters) else None
        elif kind == "field" and value.get("symbol") is not None:
            declared = self._field_type(str(value["symbol"]))[0]
        if declared is None or not slot_of_type(declared).startswith(_REFERENCE):
            return None
        return declared

    def _parameters(self, method: str) -> list[str | None]:
        """`method`'s declared parameter types, erased (`method_declarations`, read once)."""
        if self._parameter_types is None:
            self._parameter_types = {}
            for row in self._workspace.query("method_declarations"):
                signature: dict[str, Any] = row["signature"] or {}  # type: ignore[assignment]
                self._parameter_types[bare_descriptor(str(row["symbol"]))] = [
                    (parameter.get("erased_symbol") or (parameter.get("type") or {}).get("symbol"))
                    for parameter in signature.get("parameters") or []
                ]
        return self._parameter_types.get(bare_descriptor(method), [])

    def returned(self, method: str) -> list[_Value]:
        """Each value `method` returns, with the call site in it the value is made at:
        an `instance` return's own constructor call, any other return's producing call (no
        site where none produced it). A constructor returns its own class, made at its
        super-constructor call."""
        if member_name(method).startswith(f"{_CONSTRUCTOR}("):
            return [
                (owner_of(bare_descriptor(method)), None, self._super_call(method), None, False)
            ]
        returned: list[_Value] = []
        for value in self._returns.get(method, []):
            returned.extend(self._returned_value(method, value))
        return returned

    def _returned_value(self, method: str, value: Mapping[str, Any] | None) -> list[_Value]:
        kind = None if value is None else value.get("kind")
        if value is None or kind is None:
            return [(None, None, None, "void", False)]
        if kind == "merge":
            return [
                one
                for candidate in value.get("candidates") or []
                for one in self._returned_value(method, candidate)
            ]
        source = value.get("source")
        if kind == "instance" and value.get("symbol") is not None:
            made = self._site(method, lambda site: site.get("receiver") == source, _CONSTRUCTOR)
            return [(str(value["symbol"]), None, made, None, False)]
        made = self._site(method, lambda site: source is not None and site.get("result") == source)
        declared_type = self._declared(method, value)
        if declared_type is not None:
            return [(declared_type, None, made, None, True)]
        return [(None, None, made, f"returned {kind}", False)]

    def _site(self, method: str, test: Any, name: str | None = None) -> int | None:
        return next(
            (
                int(site["ordinal"])
                for site in self._sites.get(method, ())
                if (name is None or site["name"] == name) and test(site)
            ),
            None,
        )

    def _super_call(self, constructor: str) -> int | None:
        """The constructor's call of its superclass's, or a sibling's, constructor: the one
        `<init>` it makes on no value of its own (D00 §5: a `new`'s constructor call has the
        constructed value as its `receiver`; the object under construction has no id)."""
        return self._site(
            constructor,
            lambda site: site.get("invoke_kind") == "special" and site.get("receiver") is None,
            _CONSTRUCTOR,
        )

    def _field_type(self, symbol: str) -> tuple[str | None, bool]:
        if self._field_types is None:
            self._field_types = {}
            for row in self._workspace.query("fields"):
                returns = row["returns"]
                declared = None if returns is None else json.loads(str(returns)).get("symbol")
                self._field_types[bare_descriptor(str(row["symbol"]))] = (
                    None if declared is None else str(declared),
                    bool(row["static"]),
                )
        return self._field_types.get(symbol, (None, False))

    def object_hops(
        self,
        site: Mapping[str, Any],
        objects: tuple[str | None, ...],
        protocol: str,
        mechanism: str,
    ) -> list[dict[str, Any]]:
        """The rows one object-keyed send gives (module docstring): for each object its
        receiver can be, one per receive registration of `mechanism` on that object, or one
        with no handler where none takes from it; one with no path and no handler for a path
        on which the object was not read. `evidence` is `compiler`, as for every hop."""
        row = {"caller": site["caller"], "ordinal": site["ordinal"], "protocol": protocol}
        rows: list[dict[str, Any]] = []
        for key in objects:
            if key is None:
                rows.append(row | {"path": None, "handler": None, "evidence": "compiler"})
                continue
            takers = sorted(
                {
                    case["handler"]
                    for case in self._by_mechanism.get(mechanism, [])
                    if case["key_object"] == key
                },
                key=lambda handler: (handler is None, handler),
            )
            rows.extend(
                row | {"path": key, "handler": taker, "evidence": "compiler"}
                for taker in takers or [None]
            )
        return rows

    def hops(
        self, caller: str, ordinal: int | None, value: _Value, protocol: str, mechanism: str
    ) -> list[dict[str, Any]]:
        """The rows one value gives at one call site, asked of `mechanism`'s registrations
        only (the sending catalog's): one per handler it reaches, one with
        no handler where it reaches none, one with no path and no handler where its class was
        not read. A class read by its declared type is asked only of the groups it certainly
        reaches (`certain_cases`); a group it may not, under `first`, adds the not-read row. Nothing where the value was made at no call site the trace could step
        through. Every row's `evidence` is `compiler`, D00 §4's closed set: the send site is a
        compiler fact, and a class not read is said by the NULL `path`, not by the evidence."""
        if ordinal is None:
            return []
        key_type, key_value, _, unread, declared = value
        row = {"caller": caller, "ordinal": ordinal, "protocol": protocol}
        unread_row = row | {"path": None, "handler": None, "evidence": "compiler"}
        if unread is not None:
            return [unread_row]
        path = key_value or key_type
        self._rooted(key_type)
        cases = self._by_mechanism.get(mechanism, [])
        undecided = False
        if key_type is not None:
            for case in cases:
                self._rooted(case["key_type"])
            cases, undecided = certain_cases(
                cases,
                key_type,
                self._supertypes,
                self._constant_classes(),
                self._classes(),
                declared=declared,
                key_value=key_value,
            )
        reached = reached_by(cases, key_type, key_value, self._supertypes)
        handlers = sorted({case["handler"] for case in reached}, key=lambda h: (h is None, h))
        rows = [
            row | {"path": path, "handler": handler, "evidence": "compiler"}
            for handler in handlers or ([] if undecided else [None])
        ]
        return rows + [unread_row] if undecided else rows
