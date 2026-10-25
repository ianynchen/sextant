"""A gRPC client stub's call to an RPC this module serves lands on its handler (spec
2026-10-25 §3d, ruling 2).

The user's ruling: *"A service that calls its inbound endpoints is not an outbound call.
It's just a call hop that's traceable."* `resolve/self_calls.py` removes the outbound row;
this pass records where the call arrives. `call_edges` stops at the client-call API, a
library the workspace read no body of, so without this a trace from a REST method through
`GreeterBlockingStub#sayHello` ends at `ClientCalls#blockingUnaryCall` and never reaches
`HelloWorldService#sayHello` in the same module.

## The rule, all of it catalog data

A catalog carrying `client_stub_supertype` and `client_call_owner` in `matches` names the
client side; its own `supertype_marker` names the calls that
state a service identity and a wire method name. Nothing here names a gRPC type.

- **Stub classes:** every class whose `type_hierarchy` ancestry reaches
  `client_stub_supertype`, through the library rows (`scanned: false`) as well.
- **The wire method:** a stub method calls an accessor declared in the nest of a class
  that makes the `method_name_call` (`GreeterGrpc#getSayHelloMethod`), and that accessor's
  own body makes the call with the wire name as a string argument
  (`generateFullMethodName(SERVICE_NAME, "SayHello")`). Read per accessor, never per
  generated class: the class builds one name per RPC. Exactly one name, or no row.
- **The ordinal:** the stub method's first call whose target belongs to
  `client_call_owner`, where the call leaves for the wire. None, no row.
- **The path:** `<service identity of that class>/<wire method>`, the spelling of the
  inbound row it names.

A row is written only for a service the module serves (§3c, `served_handlers`): one per
handler of that path, or one with no handler when the module serves the service but has
none for this RPC, so the trace still carries the wire path when the outbound row is gone.
A call to a service the module does not serve keeps its outbound row and gets no hop.

## Cost (§5)

One read of `endpoints` (inbound, through `served_handlers`), one of `type_hierarchy`, and
one of `call_edges` filtered in SQL to the methods of the stub classes. The call sites and
nest hosts are the per-load reads `supertype_derived` already makes.
"""

from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.self_calls import served_handlers
from sextant.application.resolve.shapes.identity_calls import (
    all_string_arguments,
    caller_outer_class,
    calling_classes,
    first_string_arguments,
    nest_hosts,
    outer_of,
    parsed_call_sites,
    split_call,
)
from sextant.application.resolve.shapes.rooting import _catalog_symbol
from sextant.domain.symbols import owner_of

# The two `matches` keys that name the client side of a `supertype_derived` catalog.
_KEYS = ("client_stub_supertype", "client_call_owner")


def record_rpc_hops(workspace: Workspace, catalogs: list[Catalog]) -> None:
    """Replaces `rpc_hops` whole, from the one declared catalog that names a client stub."""
    workspace.derive("rpc_hops_reset")
    catalog = _stub_catalog(catalogs)
    if catalog is None:
        return
    served = served_handlers(workspace)
    if not served:
        return
    stubs = _stub_classes(workspace, _catalog_symbol(catalog.matches["client_stub_supertype"]))
    if not stubs:
        return
    marker = catalog.matches["supertype_marker"]
    service_owner, service_method = split_call(marker["service_name_call"])
    method_call = split_call(marker["method_name_call"])
    call_sites = parsed_call_sites(workspace)
    hosts = nest_hosts(workspace)
    marked = {outer_of(declaring, hosts) for declaring in calling_classes(call_sites, *method_call)}
    service_names = first_string_arguments(call_sites, service_owner, service_method, 0)
    sites_by_caller: dict[str, list[dict[str, Any]]] = {}
    for site in call_sites:
        sites_by_caller.setdefault(str(site["caller"]), []).append(site)
    client_call_owner = _catalog_symbol(catalog.matches["client_call_owner"])

    edges_by_caller: dict[str, list[dict[str, object]]] = {}
    for edge in workspace.query("stub_call_edges", classes=sorted(stubs)):
        edges_by_caller.setdefault(str(edge["caller"]), []).append(edge)

    rows: list[dict[str, object]] = []
    for caller in sorted(edges_by_caller):
        edges = edges_by_caller[caller]
        named = sorted(_wire_methods(edges, marked, hosts, sites_by_caller, method_call))
        if len(named) != 1:
            continue
        outer, wire = named[0]
        identity = service_names.get(outer)
        if identity is None or identity not in served:
            continue
        ordinal = next(
            (
                edge["ordinal"]
                for edge in edges
                if owner_of(str(edge["target"])) == client_call_owner
            ),
            None,
        )
        if ordinal is None:
            continue
        path = f"{identity}/{wire}"
        handlers: list[str | None] = [*sorted(served[identity].get(path, set()))]
        for handler in handlers or [None]:
            rows.append(
                {
                    "caller": caller,
                    "ordinal": ordinal,
                    "protocol": catalog.protocol,
                    "path": path,
                    "handler": handler,
                    "evidence": "compiler",
                }
            )
    if rows:
        workspace.derive("rpc_hops_insert", rows=rows)


def _wire_methods(
    edges: list[dict[str, object]],
    marked: set[str],
    hosts: dict[str, str],
    sites_by_caller: dict[str, list[dict[str, Any]]],
    method_call: tuple[str, str],
) -> set[tuple[str, str]]:
    """Every (marked outer class, wire method) one stub method reaches: through a callee in
    that class's nest whose own body makes the `method_name_call` with a readable name."""
    named: set[tuple[str, str]] = set()
    for edge in edges:
        callee = edge["callee"]
        if callee is None:
            continue
        declaring = caller_outer_class(str(callee))
        if declaring is None or (outer := outer_of(declaring, hosts)) not in marked:
            continue
        own_sites = sites_by_caller.get(str(callee), [])
        for names in all_string_arguments(own_sites, *method_call, 1).values():
            named.update((outer, name) for name in names)
    return named


def _stub_catalog(catalogs: list[Catalog]) -> Catalog | None:
    """The one declared catalog naming the client side, or None. Refuses a second one:
    two could name two different stubs, and nothing here chooses between them."""
    carrying = [c for c in catalogs if any(key in c.matches for key in _KEYS)]
    if len(carrying) > 1:
        raise CatalogError(
            f"loading catalogs {', '.join(str(c.source) for c in carrying)}: more than one "
            f"names `{_KEYS[0]}`/`{_KEYS[1]}`; one catalog names the gRPC client side "
            f"(spec 2026-10-25 §3d)"
        )
    if not carrying:
        return None
    catalog = carrying[0]
    for key in _KEYS:
        if not isinstance(catalog.matches.get(key), str):
            raise CatalogError(
                f"loading catalog {catalog.source}: `matches.{key}` must name one type, "
                f"got {catalog.matches.get(key)!r} (spec 2026-10-25 §3d)"
            )
    if not isinstance(catalog.matches.get("supertype_marker"), dict):
        raise CatalogError(
            f"loading catalog {catalog.source}: `{_KEYS[0]}` needs the `supertype_marker` "
            f"that names the identity calls (spec 2026-10-25 §3d)"
        )
    return catalog


def _stub_classes(workspace: Workspace, supertype: str) -> set[str]:
    """Every class whose ancestry reaches `supertype`, bare, library rows included."""
    parents: dict[str, list[str]] = {}
    for row in workspace.query("type_hierarchy"):
        parents.setdefault(str(row["child"]), []).append(str(row["ancestor"]))
    return {child for child in parents if _reaches(child, supertype, parents)}


def _reaches(start: str, target: str, parents: dict[str, list[str]]) -> bool:
    """Whether `target` is a supertype of `start`, transitively."""
    seen = {start}
    pending = [start]
    while pending:
        for parent in parents.get(pending.pop(), []):
            if parent == target:
                return True
            if parent not in seen:
                seen.add(parent)
                pending.append(parent)
    return False
