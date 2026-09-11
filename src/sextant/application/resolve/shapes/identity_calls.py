"""A marked call site's own literal argument, read per caller's enclosing
type (2O design §1b/§1c, R11).

Shared by `supertype_derived` and `injected_client` (`resolve/engines/`): the
two styles are different SHAPES of evidence — supertype-plus-members against
annotated-field-injection — and D02's "a style is a shape of evidence, not a
framework" rule keeps them separate engines, but both read a wire identity
off the SAME kind of fact: a generated class's own call to a framework
"build my descriptor" method, whose argument the compiler inlined a
compile-time-constant string into (JLS 13.1/13.4.9). That is not a
gRPC-specific mechanism — it is "read the marker call's Nth argument, keyed
by the class that made the call" — so nothing here names gRPC, `io.grpc`, or
any generated type; the catalog supplies the marked owner/method, this module
supplies the read.

**Why this exists at all, and not a field-value read** — R11, superseding the
brief's original `identity_marker: {constant: SERVICE_NAME}` shape: D00 §5's
`constant` fact kind has no producer anywhere in this codebase (no
`ConstantFact` class, and `ClassScanner.visitField`'s own `Object value`
parameter is accepted and never read — `scripts/probes/cp3_cp8_grpc_facts.md`
CP-8(b)). A compile-time constant is nonetheless recoverable from bytecode
alone, because javac INLINES it at every use site rather than emitting a
field read — the literal reaches a `call_site` fact's own `arguments` today,
with no new extractor capability. The marker is therefore a call-site
argument read on the class that MAKES the call, never a read of the field
that merely names it.
"""

import json
from typing import Any

from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.shapes.rooting import _catalog_symbol
from sextant.domain.symbols import bare_descriptor, outer_type_of, owner_of


def split_call(declared: dict[str, Any]) -> tuple[str, str]:
    """A catalog's `{owner, method}` marker (2O design §1b/§1c's own
    `service_name_call`/`method_name_call` notation — the
    `interface_implementation`/`single_call` `registration`/`methods` two-key
    shape, restated here rather than a combined `Owner#method` string:
    `test_catalogs_use_one_fqn_notation` refuses any catalog value carrying
    `#`, which is reserved for the SCIP symbol form the fact stream uses, not
    a catalog's own dotted notation), converted to the SCIP owner symbol
    `call_sites.owner` carries and the bare method name `call_sites.name`
    carries — parsed once, here, so every reader of this notation reads it
    the same way."""
    return _catalog_symbol(declared["owner"]), str(declared["method"])


def caller_outer_class(caller: str) -> str | None:
    """The type that DECLARES a call site's own caller method, bare (D00
    §5a) — `owner_of` already gives exactly this for a caller symbol,
    module-prefixed or not (`bare_descriptor` is a no-op on an already-bare
    one), and it is already the class a marker call actually lives on: protoc
    emits every identity-building accessor (`getServiceDescriptor`,
    `get<Method>Method`) as a STATIC method declared directly on the
    top-level generated class, never on a nested type. `None` for a
    caller with no owning type at all (a free function), which a generated
    class's own method never is."""
    return owner_of(bare_descriptor(caller))


# `domain.symbols.outer_type_of` restated under this module's own name: where
# a class's OWN facts (its `superclass`, or a field's declared type) name a
# nested generated type — `<Service>Grpc$<Service>ImplBase`/
# `$<Service>BlockingStub` always are — this is the class whose own call
# sites `caller_outer_class` above finds a marker on. All symbol-grammar
# parsing (the `#`/`$` shapes themselves) lives in `domain/symbols.py`, the
# one seam (`tests/architecture/test_symbol_grammar_confinement.py`) — this
# is a plain re-export, not a second copy of the grammar.
outer_class = outer_type_of


def nest_hosts(workspace: Workspace) -> dict[str, str]:
    """Each nested type's TOP-LEVEL enclosing type, as the class file states it
    (W4b).

    JVMS 4.7.28's `NestHost` names exactly what `outer_class` derives by splitting
    a binary name on its first `$`, and it has been extracted since W7 — it was
    simply never projected out of `raw_facts`, so nothing downstream could read it
    and three engines went on splitting. A class file that states its nest host is
    TELLING us; a split is inferring, and infers correctly right up until a name
    carries a `$` that is not nesting. Several compilers targeting this runtime
    emit exactly that, and so does every code generator that mangles names.

    Only a nested type carries the attribute, and only above a certain class-file
    version — a top-level type states none, and neither does a nested one compiled
    for an older target. Absence is why `outer_of` below still falls back rather than treating
    a missing fact as "already top-level"."""
    return {
        str(row["symbol"]): bare_descriptor(str(row["nest_host"]))
        for row in workspace.query("nest_hosts")
    }


def outer_of(descriptor: str, hosts: dict[str, str]) -> str:
    """The stated nest host where the class file carries one, the `$` split where
    it does not (W4b).

    The two agree on every shape in this repository's corpora — which is the point
    of preferring the fact rather than a reason to skip it: they agree until they
    do not, and the day they disagree the split is the one that is wrong."""
    return (
        hosts.get(descriptor) or hosts.get(bare_descriptor(descriptor)) or outer_class(descriptor)
    )


def parsed_call_sites(workspace: Workspace) -> list[dict[str, Any]]:
    """`call_sites`, `arguments` decoded once — the `single_call`/
    `interface_implementation` precedent, shared here because both styles
    that read a marker call need the same parsed list."""
    return [
        {**site, "arguments": json.loads(str(site["arguments"]))}
        for site in workspace.query("call_sites")
    ]


def calling_classes(call_sites: list[dict[str, Any]], owner: str, name: str) -> set[str]:
    """Every caller outer class that MAKES the marked call at all — argument
    readability deliberately not consulted, which is the whole difference
    from the two reads below.

    A style that MATCHES on a marker must ask this question separately from
    the question of what the marker says, because the two answers mean
    opposite things: a class that never makes the call is not the kind of
    class this marker describes (no row, no gap — there is no evidence of
    anything), while a class that makes it with an argument nothing could
    read IS one, whose identity is merely unreadable (the unresolved answer,
    plus a gap). Folding them together — inferring "not a match" from "no
    readable argument" — is what turns an ordinary supertype into a
    fabricated boundary, or an unreadable one into silence."""
    return {
        outer
        for site in call_sites
        if site["owner"] == owner and site["name"] == name
        if (outer := caller_outer_class(str(site["caller"]))) is not None
    }


def first_string_arguments(
    call_sites: list[dict[str, Any]], owner: str, name: str, index: int
) -> dict[str, str]:
    """The FIRST resolved string argument at `index`, per caller outer class
    — CP-8(b)'s `ServiceDescriptor.newBuilder("<protoPackage>.<Service>")`
    read: one identity per generated class, so the first matching call site
    (`call_sites`'s own `caller, ordinal` order — NFR-1) is the whole
    answer. A call site whose argument at `index` is not a resolved string
    literal contributes nothing — the marker stays unread for that class,
    never a fabricated value."""
    found: dict[str, str] = {}
    for site in call_sites:
        if site["owner"] != owner or site["name"] != name:
            continue
        outer = caller_outer_class(str(site["caller"]))
        if outer is None or outer in found:
            continue
        value = _string_argument(site["arguments"], index)
        if value is not None:
            found[outer] = value
    return found


def all_string_arguments(
    call_sites: list[dict[str, Any]], owner: str, name: str, index: int
) -> dict[str, list[str]]:
    """Every resolved string argument at `index`, per caller outer class, in
    call-site order (NFR-1) — CP-8(d)'s
    `generateFullMethodName(SERVICE_NAME, "<Method>")` read: a generated
    class builds one such call per RPC method, so this is the class's own
    ordered method-name inventory, not a single answer the way the service
    identity above is."""
    found: dict[str, list[str]] = {}
    for site in call_sites:
        if site["owner"] != owner or site["name"] != name:
            continue
        outer = caller_outer_class(str(site["caller"]))
        if outer is None:
            continue
        value = _string_argument(site["arguments"], index)
        if value is not None:
            found.setdefault(outer, []).append(value)
    return found


def _string_argument(arguments: list[dict[str, Any]], index: int) -> str | None:
    if index >= len(arguments):
        return None
    argument = arguments[index]
    if argument.get("kind") == "string" and isinstance(argument.get("value"), str):
        return str(argument["value"])
    return None
