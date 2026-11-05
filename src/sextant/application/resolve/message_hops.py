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

## Cost (GUIDELINES §8.7)

One lookup per declared send owner in the shared call-site index, one read each of
`message_handlers`, `method_returns` (fact, cached per load) and, only where a send passes a
field, `fields`. Rows are written once.
"""

import json
from collections.abc import Iterator, Mapping
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.dispatch import dispatch_of
from sextant.application.resolve.effective_calls import effective_call_sites
from sextant.application.resolve.message_handlers import reachable_handlers
from sextant.application.resolve.shapes.arguments import _arg_at, call_site_index
from sextant.domain.symbols import bare_descriptor, member_name, owner_of, parameter_types

# The constructor name D00 §5 normalises every language's to.
_CONSTRUCTOR = "<init>"
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
        for site, send in _send_sites(workspace, catalog):
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


def _send_sites(
    workspace: Workspace, catalog: Catalog
) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    """Each call site of a declared send, by owner, name and parameter types; a call made
    through a type inheriting the declared owner is matched by `Dispatch.heirs`."""
    index = workspace.once(call_site_index)
    dispatch = workspace.once(dispatch_of)
    sites = effective_call_sites(workspace)
    for send in catalog.message_sends:
        owner, method = send["owner"], send["method"]
        for called in (owner, *dispatch.heirs(owner, method)):
            for position in index.positions_by_owner.get(called, ()):
                site = sites[position]
                if (
                    site["name"] == method
                    and site.get("descriptor") is not None
                    and parameter_types(str(site["descriptor"]))
                    == parameter_types(send["descriptor"])
                ):
                    yield site, send


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
        no handler where it reaches none, one with no path where its class was not read.
        Nothing where the message was made at no call site the trace could step through."""
        if ordinal is None:
            return []
        message_type, message_value, _, unread = message
        row = {"caller": caller, "ordinal": ordinal, "protocol": protocol}
        if unread is not None:
            evidence = f"message class not read: {unread}"
            return [row | {"path": None, "handler": None, "evidence": evidence}]
        path = message_value or message_type
        reached = reachable_handlers(self._cases, message_type, message_value, self._supertypes)
        handlers = sorted({case["handler"] for case in reached}, key=lambda h: (h is None, h))
        return [
            row | {"path": path, "handler": handler, "evidence": "compiler"}
            for handler in handlers or [None]
        ]
