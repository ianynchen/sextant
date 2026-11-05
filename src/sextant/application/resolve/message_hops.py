"""A message send lands on the handlers its message's class reaches (spec 2026-11-04 §3c,
§3d items 3, 4 and 7).

A send names no method of the receiver: it hands an object to a mailbox, and the receiver's
behavior picks the handler by the object's class, first match first (`message_handlers.
reachable_handlers`). `call_edges` therefore stops at the library's send method, and the
trace with it. This pass reads each declared send's message and writes, into `rpc_hops`, one
row per handler that message reaches, keyed at the send's own call site, so the trace walks
on into the handler exactly as it walks a gRPC self-call (`resolve/rpc_hops.py`, the table's
other writer). Nothing here names a framework type: every owner, method and argument position
is the catalog's (`Catalog.message_sends`), and every row carries that catalog's `protocol`.

## What the message is (D00 §5's argument kinds)

- `instance` — the class constructed there.
- `enum`, or a static `field` of a declared type — a constant, read by identity (rule 8):
  its class (an `enum` constant's own owner, a field's declared type) and its own symbol, so
  it reaches a value case for that constant and a class case for its class. `path` is the
  constant's symbol.
- `lambda` — a function that builds the message (an ask's request): each class its body
  returns, one per return (a `merge` of several `new`s, javac's ternary, is one per
  candidate); a constructor reference (`Get::new`) returns its own owner.
- anything else — **not read**: one row with no `path` and no `handler`, its `evidence`
  naming the argument kind. Never a hop to every handler.

A message no behavior handles (a reply its asker reads off a future, a command told to a
system actor) is one row with its class and no `handler`: the trace stops there, naming it.

## A handler that delivers continues

A case registered with `returns_message` (`messageAdapter`'s function, an ask's reply mapper)
does not handle its message: it maps it to another, delivered to its own actor. Each class
such a handler returns is a hop from that return's own `new` — the call site javac emits for
it, where the message comes to exist — so a two-`return` mapper gives two. A constructor
reference has no `return` of its own; its hop is at its super-constructor call, the first
thing it runs.

## An inbound key row names the same handlers (`record_key_handlers`, §3d item 6)

A key (a producer call taking both, `create(Command.class, "stock")`) is an address and a
message class. Its inbound row's handlers are every case a message of that class, any subtype
of it, reaches (`message_handlers.served_cases`, the hop rule asked once per candidate class),
one row per handler as a route with two handlers is two rows. The class is read where the address is:
the same walk from the registering call's key argument, with the catalog row's
`message_class_via` hops naming the producer's class argument. A class reaching nothing, or
not read, leaves one row with `handler` NULL; the registering method `single_call` wrote is
never kept. A row whose catalog reads no message class (a pub-sub subscription, which takes
any message) is not touched.

## Cost (GUIDELINES §8.7)

One lookup per declared send owner in the shared call-site index, one read each of
`message_handlers`, `method_returns` (fact, cached per load) and, only where a send passes a
field, `fields`. Rows are written once. The key rows add, per catalog declaring
`message_class_via`, two value walks per registering call site (on the resolve's shared
value index) and one read of `endpoints`; a module registering no key pays nothing past the
call-site index lookup.
"""

import json
from collections.abc import Mapping
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.dispatch import dispatch_of
from sextant.application.resolve.message_handlers import reachable_handlers, served_cases
from sextant.application.resolve.shapes.arguments import (
    _arg_at,
    call_site_index,
    channel_of_answer,
    declared_call_sites,
)
from sextant.application.resolve.values import (
    LITERAL,
    SYMBOL,
    Answer,
    cached_value_index,
    resolve_site,
)
from sextant.domain.closed_sets import Direction
from sextant.domain.symbols import bare_descriptor, member_name, owner_of, type_descriptor

# The constructor name D00 §5 normalises every language's to.
_CONSTRUCTOR = "<init>"
# The `single_call` method-row word naming where an inbound key's message class is read.
_CLASS_VIA = "message_class_via"
# A message read, as `(class, constant, call site in its method, what was not read)`: the
# class and the constant's own symbol where read, else `unread` names the argument kind.
_Message = tuple[str | None, str | None, int | None, str | None]


def record_message_hops(workspace: Workspace, catalogs: list[Catalog]) -> None:
    """Inserts the hops of every declared send, and of every delivering handler, into
    `rpc_hops`. Inserts only: the pipeline resets the table once before both of its writers
    (spec §3d item 7)."""
    sending = [catalog for catalog in catalogs if catalog.message_sends]
    delivering = [
        catalog
        for catalog in catalogs
        if any(registration["returns_message"] for registration in catalog.message_handlers)
    ]
    if not sending and not delivering:
        return
    for catalog in (*sending, *delivering):
        if not catalog.protocol:
            raise CatalogError(
                f"loading catalog {catalog.source}: it declares message sends or delivering "
                f"handlers and no `protocol`, which every hop it gives is written under "
                f"(spec 2026-11-04 §3c)"
            )
    reading = _Reading(workspace)
    rows: dict[tuple[Any, ...], dict[str, Any]] = {}
    for catalog in sending:
        for site, send in declared_call_sites(workspace, catalog.message_sends):
            argument = _arg_at(site["arguments"], send["message_arg"])
            for message in reading.sent(argument):
                for row in reading.hops(site["caller"], site["ordinal"], message, catalog.protocol):
                    rows.setdefault(tuple(row.values()), row)
    protocols = sorted({catalog.protocol for catalog in delivering})
    if len(protocols) > 1:
        raise CatalogError(
            f"loading catalogs {', '.join(str(c.source) for c in delivering)}: delivering "
            f"handlers are declared under protocols {protocols}; a handler's own delivery is "
            f"written under one (spec 2026-11-04 §3d item 4)"
        )
    for handler in reading.delivering_handlers() if protocols else []:
        for message in reading.returned(handler):
            for row in reading.hops(handler, message[2], message, protocols[0]):
                rows.setdefault(tuple(row.values()), row)
    if rows:
        workspace.derive("rpc_hops_insert", rows=list(rows.values()))


def record_key_handlers(workspace: Workspace, catalogs: list[Catalog]) -> None:
    """Names each inbound key row's handlers (spec 2026-11-04 §3a, §3d item 6): a row its
    catalog reads a message class for (`message_class_via`) becomes one row per handler that
    class reaches, as a route with two handlers is two rows; one row with `handler` NULL
    where it reaches none or the class was not read. The registering method `single_call`
    wrote is never one of them: registering a key is not handling its messages.

    Replaces rows, so it runs after `record_self_calls`, which reads "served" off these rows
    while every one of them still has its registering method as `handler`: a key no handler
    serves is still served here, and a call naming it stays a hop."""
    keyed = [catalog for catalog in catalogs if _keyed_methods(catalog)]
    if not keyed:
        return
    reading = _Reading(workspace)
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
                    for message_class in read
                    for handler in reading.key_handlers(message_class)
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
    """The `single_call` method rows declaring `message_class_via`, each refused unless it is
    well formed: a list of `{owner, method, arg}` hops on an inbound row that reads its key
    at `channel_arg`. Once one inbound row of a catalog declares it, every inbound row must:
    the pass replaces the catalog's inbound rows, and a row the word did not read would lose
    its handler to a class nothing read."""
    methods = [method for method in catalog.matches.get("methods") or [] if _CLASS_VIA in method]
    if not methods:
        return []
    for method in catalog.matches.get("methods") or []:
        inbound = method.get("direction", catalog.direction) == str(Direction.INBOUND)
        where = f"loading catalog {catalog.source}: `{method.get('name')}`"
        if _CLASS_VIA not in method:
            if inbound:
                raise CatalogError(
                    f"{where} is an inbound row declaring no `{_CLASS_VIA}` beside one that "
                    f"does; every inbound row of the catalog names its key's message class "
                    f"(spec 2026-11-04 §3d item 6)"
                )
            continue
        via = method[_CLASS_VIA]
        if not inbound or not isinstance(method.get("channel_arg"), int):
            raise CatalogError(
                f"{where} declares `{_CLASS_VIA}` on a row that is not inbound or reads no "
                f"`channel_arg`: the message class is read where an inbound key is "
                f"(spec 2026-11-04 §3d item 6)"
            )
        if (
            not isinstance(via, list)
            or not via
            or not all(
                isinstance(entry, dict)
                and set(entry) == {"owner", "method", "arg"}
                and isinstance(entry["arg"], int)
                for entry in via
            )
        ):
            raise CatalogError(
                f"{where}: `{_CLASS_VIA}` must be a non-empty list of `{{owner, method, arg}}` "
                f"entries, `arg` an argument index (D02 §2)"
            )
    return methods


def _key_classes(
    workspace: Workspace, catalog: Catalog
) -> dict[tuple[str | None, str | None], set[str | None]]:
    """Each inbound key a declared call registers, `(registering method, key)`, mapped to the
    message classes read for it (None: not read).

    The key and its class are two arguments of one producing call (`create(C.class, "stock")`
    on the key type), read by two walks from the registering call's key argument: the address
    through the catalog's identity table, exactly as `single_call` read the row's `path`,
    and the class through the same table with the row's `message_class_via` hops placed
    first, so the producer they name answers with the class argument instead. The walk
    answers a class literal as a `symbol` literal. Two walks give two sets of paths; a class
    belongs to a key where one path extends the other (the shared crossings are the nearest
    ones, the end of `Binding.path`), so two keys built in one helper stay apart."""
    values = cached_value_index(workspace, catalog.not_hand_offs, catalog.hand_off_effects)
    owner = type_descriptor(str(catalog.matches["owner"]))
    classes: dict[tuple[str | None, str | None], set[str | None]] = {}
    for method in _keyed_methods(catalog):
        slot = int(method["channel_arg"])
        identities = [
            {**entry, "owner": type_descriptor(str(entry["owner"]))} for entry in method[_CLASS_VIA]
        ] + list(catalog.value_model)
        entry = {"owner": owner, "method": method["name"], "descriptor": method["descriptor"]}
        for site, _ in declared_call_sites(workspace, [entry]):
            named = [
                (binding.path, channel_of_answer(binding.slots.get(slot))[1])
                for binding in resolve_site(workspace, site, values, catalog.value_model)
            ]
            read = [
                (binding.path, _class_of(binding.slots.get(slot)))
                for binding in resolve_site(workspace, site, values, identities)
            ]
            for name, message_classes in _paired(named, read).items():
                classes.setdefault((str(site["caller"]), name), set()).update(message_classes)
    return classes


def _paired(
    named: list[tuple[tuple[str, ...], str | None]],
    read: list[tuple[tuple[str, ...], str | None]],
) -> dict[str | None, set[str | None]]:
    """Each key the address walk read, mapped to the classes the class walk read on a path
    agreeing with the key's: one path extends the other, the crossings both made being the
    nearest ones (the end of `Binding.path`). A key no class agrees with maps to None, not
    read. No address path at all is one key, None, the one row `single_call` writes for such
    a site, taking every class read there."""
    paired: dict[str | None, set[str | None]] = {}
    for name_path, name in named or [((), None)]:
        agreeing = [
            message_class
            for class_path, message_class in read
            if _extends(name_path, class_path) or _extends(class_path, name_path)
        ]
        paired.setdefault(name, set()).update(agreeing or [None])
    return paired


def _class_of(answer: Answer | None) -> str | None:
    """A class literal the walk answered (`symbol`), or None for anything else."""
    if answer is None or answer.kind != LITERAL or answer.literal_kind != SYMBOL:
        return None
    return str(answer.value)


def _extends(longer: tuple[str, ...], shorter: tuple[str, ...]) -> bool:
    return len(longer) >= len(shorter) and longer[len(longer) - len(shorter) :] == shorter


class _Reading:
    """The reads a send's message and a handler's return need, taken once per resolve."""

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace
        self._cases = workspace.query("message_handlers")
        dispatch = workspace.once(dispatch_of)
        self._supertypes = {
            child: {ancestor for ancestor, _, _ in ancestors}
            for child, ancestors in dispatch.ancestors.items()
        }
        self._returns: dict[str, list[Any]] = {}
        for row in workspace.query("method_returns"):
            value = None if row["value"] is None else json.loads(str(row["value"]))
            self._returns.setdefault(str(row["method"]), []).append(value)
        self._by_bare: dict[str, str] = {
            bare_descriptor(method): method for method in self._returns
        }
        self._sites = workspace.once(call_site_index).by_caller
        self._field_types: dict[str, tuple[str | None, bool]] | None = None
        # `key_handlers`' per-run inputs (GUIDELINES §8.7): each value case's constant's class,
        # read once, and each message class's answer, so a key class many inbound rows share
        # walks the module's types once rather than once per row.
        self._constants: dict[str, str | None] | None = None
        self._key_handlers: dict[str | None, list[str | None]] = {}

    def key_handlers(self, message_class: str | None) -> list[str | None]:
        """The handlers a message of `message_class`, any subtype of it, reaches
        (`message_handlers.served_cases`); a case whose handler was not read gives None, as
        for a hop. Nothing for a class not read."""
        if message_class not in self._key_handlers:
            if self._constants is None:
                self._constants = {
                    str(case["message_value"]): self._constant_class(str(case["message_value"]))
                    for case in self._cases
                    if case["message_value"] is not None
                }
            reached = served_cases(self._cases, message_class, self._supertypes, self._constants)
            self._key_handlers[message_class] = list(
                dict.fromkeys(case["handler"] for case in reached)
            )
        return self._key_handlers[message_class]

    def _constant_class(self, symbol: str) -> str | None:
        """A value case's constant's class: the static field's declared type (an enum
        constant's is its enum), None where the field is not in the module's facts."""
        declared, static = self._field_type(symbol)
        return declared if static else None

    def delivering_handlers(self) -> list[str]:
        return sorted(
            {str(case["handler"]) for case in self._cases if case["delivers"] and case["handler"]}
        )

    def sent(self, argument: Mapping[str, Any] | None) -> list[_Message]:
        """What a send's message argument is, one entry per class it can be."""
        kind = None if argument is None else argument.get("kind")
        if argument is None or kind is None:
            return [(None, None, None, "absent")]
        symbol = argument.get("symbol")
        if kind == "instance" and symbol is not None:
            return [(str(symbol), None, None, None)]
        if kind == "enum" and symbol is not None:
            return [(owner_of(str(symbol)), str(symbol), None, None)]
        if kind == "field" and symbol is not None:
            declared, static = self._field_type(str(symbol))
            if declared is not None and static:
                return [(declared, str(symbol), None, None)]
            return [(None, None, None, kind)]
        if kind == "lambda" and symbol is not None:
            if member_name(str(symbol)).startswith(f"{_CONSTRUCTOR}("):
                return [(owner_of(str(symbol)), None, None, None)]
            body = self._by_bare.get(str(symbol))
            if body is None:
                return [(None, None, None, kind)]
            return [(type_, value, None, unread) for type_, value, _, unread in self.returned(body)]
        return [(None, None, None, str(kind))]

    def returned(self, method: str) -> list[_Message]:
        """Each message `method` returns, with the call site in it the message is made at:
        an `instance` return's own constructor call, any other return's producing call (no
        site where none produced it). A constructor returns its own class, made at its
        super-constructor call."""
        if member_name(method).startswith(f"{_CONSTRUCTOR}("):
            return [(owner_of(bare_descriptor(method)), None, self._super_call(method), None)]
        messages: list[_Message] = []
        for value in self._returns.get(method, []):
            messages.extend(self._returned_value(method, value))
        return messages

    def _returned_value(self, method: str, value: Mapping[str, Any] | None) -> list[_Message]:
        kind = None if value is None else value.get("kind")
        if value is None or kind is None:
            return [(None, None, None, "void")]
        if kind == "merge":
            return [
                message
                for candidate in value.get("candidates") or []
                for message in self._returned_value(method, candidate)
            ]
        source = value.get("source")
        if kind == "instance" and value.get("symbol") is not None:
            made = self._site(method, lambda site: site.get("receiver") == source, _CONSTRUCTOR)
            return [(str(value["symbol"]), None, made, None)]
        made = self._site(method, lambda site: source is not None and site.get("result") == source)
        return [(None, None, made, f"returned {kind}")]

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

    def hops(
        self, caller: str, ordinal: int | None, message: _Message, protocol: str
    ) -> list[dict[str, Any]]:
        """The rows one message gives at one call site: one per handler it reaches, one with
        no handler where it reaches none, one with no path and no handler where its class was
        not read. Nothing where the message was made at no call site the trace could step
        through. Every row's `evidence` is `compiler`, D00 §4's closed set: the send site is a
        compiler fact, and a class not read is said by the NULL `path`, not by the evidence."""
        if ordinal is None:
            return []
        message_type, message_value, _, unread = message
        row = {"caller": caller, "ordinal": ordinal, "protocol": protocol}
        if unread is not None:
            return [row | {"path": None, "handler": None, "evidence": "compiler"}]
        path = message_value or message_type
        reached = reachable_handlers(self._cases, message_type, message_value, self._supertypes)
        handlers = sorted({case["handler"] for case in reached}, key=lambda h: (h is None, h))
        return [
            row | {"path": path, "handler": handler, "evidence": "compiler"}
            for handler in handlers or [None]
        ]
