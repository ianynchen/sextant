"""Parse-call payload binding (2G design §6).

Some channels carry bytes and nothing else. Their handler's signature says
`String` or `byte[]` — the wire's own shape, not the contract's — and the
only statement of what is actually on that wire is the parse call in the
code. This pass reads that call, and only that call.

**Two rungs, and the second is exactly one hop long:**

- **Rung A — the handler's own body.** A catalog-matched parse whose bytes
  argument NAMES the handler's payload parameter (D00 §5's `parameter` kind)
  binds the type that parse identifies.
- **Rung B — one delegation hop.** The handler passes that same parameter,
  bare, to a module-local method; the callee parses its own corresponding
  parameter. One hop, never further: past it the flow stops being a fact this
  pass observed and starts being a chain it assumed.

**Multi-caller is not ambiguity.** Two listeners delegating to one callee
both bind its parse — both channels' bytes provably reach it. **Real
ambiguity refuses to bind:** one payload parameter reaching two parses that
name two different types is two answers, so the pass records neither.

**What the horizon costs is written down rather than hidden.** A parse
reachable only at hop two is found, refused, and ledgered as an
`open_questions` row carrying the candidate it refused — the design's
`payload_parsed_beyond_horizon`. `payload_parse_ambiguous` is the same
discipline for the other refusal. 2K answers both at `evidence: llm`; nothing
here reads them back.

**A parameter is the only join, and it is a narrow one on purpose** (Phase 2G
checkpoint, Task 3): a value merged from a parameter and any other producer
reads `unresolved`, so a handler that conditionally delegates names no
parameter at any call and binds nothing. That is the honest answer — the
merge genuinely could have come from either branch — and this pass does not
try to widen it.

Every library, framework and type name this pass compares against is catalog
data (2G design §7). None appears below.
"""

import json
from dataclasses import dataclass
from typing import Any, cast

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.conditions import annotation_index, member_annotations_by_type
from sextant.application.resolve.effective_calls import effective_call_sites
from sextant.application.resolve.open_questions import record_open_questions
from sextant.application.resolve.shapes.arguments import _bare_reference, parameter_index
from sextant.application.resolve.shapes.contracts import (
    _body_parameter,
    _paths_by_owner,
    _payload_descriptor,
    declares_container,
)
from sextant.application.resolve.shapes.expansion import _enum_symbols, _rules_of, derive_shapes
from sextant.domain.symbols import bare_descriptor, method_name, type_descriptor

# D00 §5's argument kinds this pass reads. `parameter` is the whole join: it
# is the one kind that says "this argument is the value my own caller handed
# me", and `arguments.py` deliberately treats it as naming no value (its
# `_UNREAD_KINDS`) — the read itself is `arguments.parameter_index`, one
# primitive shared with the identity join `single_call` resolves through the
# same kind, so the two can never disagree about what "bare" means.
_CLASS_KIND = "class"

# Where a matched call keeps the payload type (2G design §7). `receiver_owner`
# is the parse whose receiver IS the payload type; `class_arg` is the parse
# handed a class literal.
_RECEIVER_OWNER = "receiver_owner"
_CLASS_ARG = "class_arg"
_PAYLOAD_SOURCES = (_RECEIVER_OWNER, _CLASS_ARG)

# How far a flow is followed. 0 is the handler's own body and 1 is the single
# delegation hop the design sanctions — both BIND. 2 is looked at and never
# bound: the pass has to reach it to be able to say a parse exists out there
# (the `payload_parsed_beyond_horizon` ledger row), and binding it would be
# the assumption the horizon exists to refuse.
_BINDS_UPTO = 1
_LOOKS_UPTO = 2

# The one question kind this pass writes (2G design §6's closed set;
# `resolve/open_questions.py` owns and checks it).
_QUESTION = "payload_binding"


@dataclass(frozen=True)
class ParseBindings:
    """What the pass rooted and could not open — the same answer
    `derive_endpoint_shapes` returns, for the same reason (D2): a payload
    type this pass bound is expanded here, so a type nothing could expand is
    this pass's gap to report, not the earlier pass's."""

    unexpanded_types: tuple[str, ...]


def bind_parse_calls(workspace: Workspace, catalogs: list[Catalog]) -> ParseBindings:
    """Binds `request_shape` on every bytes-only endpoint whose payload a
    catalog-matched parse names, and ledgers the ones it refuses.

    Runs after the shape pass (it needs the payload columns that pass wrote)
    and before the format ladder (rung 4 reads what this binds), between the
    `open_questions` reset and `resolve_format` — see `resolve/pipeline.py`.
    """
    vocabulary = _vocabulary(catalogs)
    if not vocabulary.calls:
        return ParseBindings(())
    facts = _facts(workspace)
    by_id = {catalog.id: catalog for catalog in catalogs}
    enums = _enum_symbols(workspace)
    rows: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    # Roots are collected per catalog and expanded once at the end: expansion
    # is keyed on the type symbol alone and is insert-if-absent
    # (`derive_shapes`), so a type two endpoints bind is one shape, and the
    # rules that describe it are the ones of whichever catalog reaches it
    # first — the same ordering property `derive_endpoint_shapes` already
    # records as a known gap.
    roots: dict[str, list[str]] = {}
    unexpanded: list[str] = []
    # The body rule's context, the same one `_contracts_of` hands it — the two
    # annotation folds once per load, an owner's composed paths once per
    # catalog that owns a row (GUIDELINES §8.7) — so the parameter this pass
    # rebinds is the one the shape pass picked, never a second reading.
    endpoints = workspace.query("endpoints")
    index = annotation_index(workspace)
    members = (
        member_annotations_by_type(workspace)
        if any(declares_container(catalog) for catalog in catalogs)
        else {}
    )
    paths_of: dict[str, dict[str, frozenset[str]]] = {}
    for endpoint in endpoints:
        catalog = by_id.get(str(endpoint.get("catalog_id")))
        if catalog is None:
            continue
        if catalog.id not in paths_of:
            paths_of[catalog.id] = _paths_by_owner(endpoints, catalog)
        parameter = _bytes_parameter(
            endpoint, catalog, vocabulary, paths=paths_of[catalog.id], index=index, members=members
        )
        if parameter is None:
            continue
        handler = str(endpoint["handler"])
        found = _parses_reached(handler, parameter, vocabulary, facts)
        bindable = [candidate for candidate in found if candidate.hops <= _BINDS_UPTO]
        types = {candidate.payload_type for candidate in bindable}
        if len(types) == 1:
            descriptor = _descriptor_of(
                types.pop(), _rules_of(catalog), enums, roots.setdefault(catalog.id, [])
            )
            if descriptor is not None:
                rows.append(_binding(endpoint, descriptor))
            continue
        if len(types) > 1:
            questions.append(_question(endpoint, bindable, _AMBIGUOUS))
            continue
        beyond = [candidate for candidate in found if candidate.hops > _BINDS_UPTO]
        if beyond:
            questions.append(_question(endpoint, beyond, _BEYOND_HORIZON))
    for catalog_id, rooted in roots.items():
        expanded = derive_shapes(workspace, by_id[catalog_id], list(dict.fromkeys(rooted)))
        unexpanded.extend(expanded.unexpanded_types)
    workspace.derive("bind_request_shape", rows=rows)
    record_open_questions(workspace, questions)
    return ParseBindings(unexpanded_types=tuple(dict.fromkeys(unexpanded)))


# --- the rungs ------------------------------------------------------------


@dataclass(frozen=True)
class _Candidate:
    """One parse a payload's bytes provably reach: the type it names, how many
    delegation hops away it was found, the method it sits in, and the catalog
    rule that matched it."""

    payload_type: str
    hops: int
    seen_in: str
    why: str


def _parses_reached(
    method: str, parameter: int, vocabulary: "_Vocabulary", facts: "_Facts"
) -> list[_Candidate]:
    """Every catalog-matched parse this method's `parameter` reaches, within
    `_LOOKS_UPTO` hops, each labelled with how far away it was found.

    Rungs A and B are the same walk at two depths, deliberately: "the parse is
    here" and "the parse is in what I called with it" differ only in how far
    the value travelled, and writing them as two joins would let the two
    drift. The caller decides which depths may BIND — this only reports how
    far each answer was.

    **Breadth first, and that is load-bearing rather than a style choice.**
    The hop count is what separates a binding from a refusal, so every method
    must be reached at its SHORTEST distance: a callee that is both called
    directly and called again from another callee would otherwise be recorded
    at whichever distance a depth-first walk happened to arrive by, and an
    ordinary two-path delegation would bind or not bind depending on the
    order call sites were read in.

    The frontier keys on `(method, parameter)`, not on the method alone: a
    method reached with a different parameter is a different flow, while one
    reached twice with the same parameter answers the same thing twice.
    """
    found: list[_Candidate] = []
    frontier = [(method, parameter)]
    visited = {(method, parameter)}
    for hops in range(_LOOKS_UPTO + 1):
        following: list[tuple[str, int]] = []
        for current, index in frontier:
            sites = facts.sites.get(current, [])
            found.extend(
                _Candidate(
                    payload_type=payload, hops=hops, seen_in=bare_descriptor(current), why=why
                )
                for site in sites
                for payload, why in _parsed_here(site, index, vocabulary, facts)
            )
            if hops >= _LOOKS_UPTO:
                continue
            for site in sites:
                callee = facts.callee_of(site)
                if callee is None:
                    continue
                for position, argument in enumerate(site["arguments"]):
                    # The one new join (2G design §6): the caller's argument
                    # POSITION is the callee's own parameter index. True for a
                    # static call and an instance one alike — a call's
                    # `arguments` never include the receiver, and D00 §5's
                    # `parameter` value is the DECLARED index, never the local
                    # slot a JVM happens to keep it in.
                    step = (callee, position)
                    if not _names_parameter(argument, index) or step in visited:
                        continue
                    visited.add(step)
                    following.append(step)
        frontier = following
    return found


def _parsed_here(
    site: dict[str, Any], parameter: int, vocabulary: "_Vocabulary", facts: "_Facts"
) -> list[tuple[str, str]]:
    """The payload types one call site names, if it is a parse of this
    parameter's bytes, each with the CALL that named it.

    The trail names the call rather than the catalog entry that matched it —
    an owner symbol already carries its own member separator, so the pair
    reads as one name — because a reader of an `open_questions` row is
    looking for the line of code, and a hierarchy entry's own spelling is a
    list of markers that appears nowhere in the module.

    A list rather than an option only so the caller reads uniformly: a call
    matches at most one entry per payload it can name.
    """
    found = []
    for entry in vocabulary.calls:
        if not _matches(site, entry, facts):
            continue
        argument = _argument_at(site, entry.bytes_arg)
        if not _names_parameter(argument, parameter):
            continue
        payload = _payload_type_of(site, entry)
        if payload is not None:
            found.append((payload, f"{site['owner']}{site['name']}"))
    return found


def _matches(site: dict[str, Any], entry: "_ParseCall", facts: "_Facts") -> bool:
    """Whether a call site is the parse an entry describes: the method name,
    then the owner — by identity where the entry names one, by HIERARCHY where
    it names markers instead (2G design §7's protobuf rule, where the payload
    type IS the receiver and no name pattern may stand in for the type's
    ancestry)."""
    if str(site["name"]) != entry.method:
        return False
    owner = str(site["owner"])
    if entry.owner is not None:
        return owner == entry.owner
    return _reaches(owner, entry.hierarchy, facts)


def _reaches(symbol: str, targets: tuple[str, ...], facts: "_Facts") -> bool:
    """Whether a type's declared ancestry reaches any of `targets`, following
    the erased superclass edge, the generic-supertype references AND the
    implemented interfaces the facts carry (D00 §5a), transitively, within
    what was scanned.

    All three, and the third one used to be missing (`A-M12`). The sentence
    that stood here said *"a plain `extends` is NOT in the fact stream at all
    (`supertype` is emitted only for a GENERIC superclass)"* — true when it
    was written, and **falsified by capability 9.13**, whose
    `ClassScanner.erasedSuperclassJson` writes a `superclass` field for every
    non-`Object` superclass. `supertype` really is the generic-arguments
    carrier and really does miss a plain `extends`; the error was reading it
    as the class-inheritance edge when a second field carries exactly that,
    which is `A-C4`'s invented rule in a second engine. A payload whose only
    route to a protobuf marker is `extends GeneratedMessage` bound nothing:
    an under-report, not a wrong type, and silent.

    A type outside the module has no ancestry fact and simply ends the walk,
    which is why the markers are compared by name rather than followed into.
    """
    seen: set[str] = set()
    pending = [symbol]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        if current in targets:
            return True
        pending.extend(facts.ancestry.get(current, ()))
    return False


def _payload_type_of(site: dict[str, Any], entry: "_ParseCall") -> str | None:
    """The type a matched parse identifies: its own receiver's type, or the
    class literal it was handed. A `class_arg` position holding anything but a
    class literal names no type — an unread argument is not a payload (D00
    §5), and guessing one from the call's return type would describe the
    erased `Object` every such API declares."""
    if entry.payload_from == _RECEIVER_OWNER:
        return str(site["owner"])
    argument = _argument_at(site, entry.class_arg)
    if argument is None or argument.get("kind") != _CLASS_KIND:
        return None
    symbol = argument.get("symbol")
    return None if symbol is None else bare_descriptor(str(symbol))


def _names_parameter(argument: dict[str, Any] | None, parameter: int) -> bool:
    """Whether an argument IS the caller's parameter at this index, bare
    (D00 §5's `parameter` kind). Anything else is a no — including the
    `unresolved` a value merged from this parameter and a literal reads as,
    which is the honest answer the checkpoint pinned and not a case to work
    around."""
    return parameter_index(argument) == parameter


def _argument_at(site: dict[str, Any], index: int | None) -> dict[str, Any] | None:
    """The argument at a declared position, or None where the entry names none
    or the real call carries fewer — `arguments._arg_at`'s rule, restated for
    a site whose `arguments` this pass has already parsed."""
    arguments = site["arguments"]
    if index is None or index >= len(arguments):
        return None
    argument = arguments[index]
    return argument if isinstance(argument, dict) else None


# --- what a row is, and what it asks ---------------------------------------


def _bytes_parameter(
    endpoint: dict[str, Any],
    catalog: Catalog,
    vocabulary: "_Vocabulary",
    *,
    paths: dict[str, frozenset[str]],
    index: dict[str, list[tuple[str, dict[str, Any]]]],
    members: dict[str, set[str]],
) -> int | None:
    """The declared index of this endpoint's payload parameter, if that
    parameter carries the wire's BYTES rather than a decoded object.

    Three conditions, all of them refusals rather than filters. A row with no
    handler (an outbound call site) has no body to read a parse from. A row
    whose payload parameter the catalog's own body rule cannot find declares
    no payload at all. And a row whose payload parameter names a real type is
    already described by its signature — rebinding it would replace a
    declaration with an inference.
    """
    handler, declared = endpoint.get("handler"), endpoint.get("handler_signature")
    if handler is None or declared is None:
        return None
    signature = json.loads(str(declared))
    if not isinstance(signature, dict):
        return None
    owner = str(handler)
    found = _body_parameter(
        signature,
        catalog,
        owner=owner,
        paths=paths.get(owner, frozenset()),
        index=index,
        members=members,
    )
    if found is None:
        return None
    position, parameter = found
    # The descriptor's answer: `bytes_payloads` is catalog-declared type names, and a
    # type variable's name is scoped to its own declaration and matches none of them.
    symbol = parameter.get("erased_symbol") or parameter["type"].get("symbol")
    return position if symbol in vocabulary.bytes_payloads else None


def _descriptor_of(
    payload_type: str, rules: Any, enums: set[str], referenced: list[str]
) -> str | None:
    """The wire descriptor a bound payload type roots at, appending every
    shape it reaches to `referenced` so the binding's own types are expanded
    like any other root (Task 9 review, Finding C1: a `shape_id` with no
    `shapes` row behind it is a broken contract, not a degraded one).

    Read through the same `_bare_reference`/`_payload_descriptor` pair a
    captured call argument goes through, because that is exactly what this
    is: a type named by a call site rather than by a signature.
    """
    return _payload_descriptor(
        _bare_reference(payload_type), rules, enums, referenced, rules.wrappers
    )


def _binding(endpoint: dict[str, Any], descriptor: str) -> dict[str, Any]:
    """One compare-and-set row for `bind_request_shape.sql`: the row's
    identity, the bytes-shaped value this pass read, and the payload type it
    replaces it with. Carrying the value read is what makes the write
    first-writer-safe — see that file."""
    return {column: endpoint.get(column) for column in _MATCH_COLUMNS} | {
        "bytes_shape": endpoint.get("request_shape"),
        "request_shape": descriptor,
    }


# The row identity a binding is matched back onto. The same six columns
# `stamp_format.sql` uses for identity: `(protocol, direction, method, path)`
# is not unique in this table — two listeners on one destination, several
# NULL-path call sites — and `handler`/`caller` are what separate them.
_MATCH_COLUMNS = ("protocol", "direction", "method", "path", "handler", "caller")

# The two refusals, and the sentence each puts in front of its candidates.
# Prose, not a closed vocabulary: `open_questions.evidence` is a trail for a
# human and for 2K, telling them where to look rather than how much to trust
# an answer nobody gave.
_AMBIGUOUS = "payload parse ambiguous — one payload, more than one parse"
_BEYOND_HORIZON = "payload parsed beyond the one-hop horizon"


def _question(endpoint: dict[str, Any], candidates: list[_Candidate], trail: str) -> dict[str, Any]:
    """One `payload_binding` row for the 2K ledger (2G design §6): the wire
    identity, every candidate that was on the table, and why none of them was
    taken. Candidates are sorted and serialized here — the pass that builds a
    candidate is the one that knows its shape, and two runs must produce the
    same bytes (NFR-1)."""
    ordered = sorted(
        (
            {
                "payload_type": candidate.payload_type,
                "hops": str(candidate.hops),
                "seen_in": candidate.seen_in,
                "why": candidate.why,
            }
            for candidate in candidates
        ),
        key=lambda candidate: (
            candidate["payload_type"],
            candidate["hops"],
            candidate["seen_in"],
            candidate["why"],
        ),
    )
    named = ", ".join(
        f"{candidate['payload_type']} in {candidate['seen_in']} "
        f"via {candidate['why']} at {candidate['hops']} hop(s)"
        for candidate in ordered
    )
    return {
        "protocol": endpoint.get("protocol"),
        "method": endpoint.get("method"),
        "path": endpoint.get("path"),
        "question": _QUESTION,
        "candidates": json.dumps(ordered, sort_keys=True, separators=(",", ":")),
        "evidence": f"{trail}: {named}",
    }


# --- catalog vocabulary ---------------------------------------------------


@dataclass(frozen=True)
class _ParseCall:
    """One `parse_calls` entry, with every dotted name already converted — the
    binding-seam discipline `_Rules` and `CarrierRules` keep, so no rule above
    has to remember which notation it is holding.

    `owner` and `hierarchy` are exclusive: an entry names the receiver's type
    outright, or names the markers its ancestry must reach.
    """

    owner: str | None
    hierarchy: tuple[str, ...]
    method: str
    bytes_arg: int
    payload_from: str
    class_arg: int | None


@dataclass(frozen=True)
class _Vocabulary:
    bytes_payloads: frozenset[str]
    calls: tuple[_ParseCall, ...]


def _vocabulary(catalogs: list[Catalog]) -> _Vocabulary:
    """Every catalog's `parse_calls` block, unioned and validated before a
    single row is read — the "broken file, not a half-answered table"
    discipline `resolve_format` and `resolve_config` both keep.

    Unioned rather than scoped per catalog, for the reason `format.py`'s own
    tables are: a parse means the same thing whoever wrote it down, and the
    row being bound carries no catalog of its own once several engines have
    contributed to it. Entries are kept in catalog order (the loader's
    filename order) so two runs match a call in the same order (NFR-1).
    """
    payloads: set[str] = set()
    calls: list[_ParseCall] = []
    for catalog in catalogs:
        declared = catalog.parse_calls
        if not declared:
            continue
        if not isinstance(declared, dict):
            raise CatalogError(
                f"loading catalog {catalog.source}: `parse_calls` must be a mapping of "
                f"`bytes_payloads` and `calls`, got {declared!r}"
            )
        payloads.update(type_descriptor(name) for name in declared.get("bytes_payloads") or [])
        for entry in declared.get("calls") or []:
            calls.append(_parse_call(entry, catalog))
    return _Vocabulary(bytes_payloads=frozenset(payloads), calls=tuple(calls))


def _parse_call(entry: Any, catalog: Catalog) -> _ParseCall:
    """Refuses a malformed entry at run start. An entry naming no owner, no
    method, or a `payload_from` nothing implements would make the rung a
    silent no-op — indistinguishable from a catalog that declares no parses at
    all, which is the one outcome the loader's own discipline exists to
    prevent."""
    owner = entry.get("owner") if isinstance(entry, dict) else None
    hierarchy = entry.get("owner_hierarchy") if isinstance(entry, dict) else None
    valid = (
        isinstance(entry, dict)
        and (isinstance(owner, str)) != (isinstance(hierarchy, list) and bool(hierarchy))
        and isinstance(entry.get("method"), str)
        and entry.get("payload_from") in _PAYLOAD_SOURCES
        and isinstance(entry.get("bytes_arg", 0), int)
        and (entry.get("payload_from") != _CLASS_ARG or isinstance(entry.get("class_arg"), int))
    )
    if not valid:
        raise CatalogError(
            f"loading catalog {catalog.source}: a `parse_calls.calls` entry must name exactly "
            f"one of `owner`/`owner_hierarchy`, a `method`, and a `payload_from` of "
            f"{'/'.join(_PAYLOAD_SOURCES)} (with `class_arg` where it is "
            f"{_CLASS_ARG}), got {entry!r}"
        )
    return _ParseCall(
        owner=type_descriptor(owner) if isinstance(owner, str) else None,
        hierarchy=tuple(type_descriptor(name) for name in hierarchy or []),
        method=str(entry["method"]),
        # An entry with no declared bytes position names a parse whose payload
        # TYPE is readable and whose BYTES arrive somewhere else entirely (a
        # reader constructed from a class, decoding from a separately built
        # decoder). No rung can prove the channel's bytes reach it, so it is
        # kept out of every join by a position no call ever has, rather than
        # bound on the strength of being in the right method.
        bytes_arg=int(entry.get("bytes_arg", _NO_BYTES_ARGUMENT)),
        payload_from=str(entry["payload_from"]),
        class_arg=entry.get("class_arg"),
    )


# The `bytes_arg` an entry that declares none is given: past the end of every
# real argument list, so `_argument_at` answers None and the entry matches
# nothing. A sentinel rather than an optional field, so no rung has to carry
# a second "is this bindable" branch (see `_parse_call`).
_NO_BYTES_ARGUMENT = 1 << 30


# --- workspace facts ------------------------------------------------------


@dataclass(frozen=True)
class _Facts:
    """The workspace facts the rungs join through, read ONCE per pass rather
    than once per endpoint (the `field_facts`/`_rules_of` precedent).

    - `sites` — every call site, `arguments` already parsed, grouped by the
      method that makes it. Keyed on the caller symbol exactly as the fact
      wrote it, which is also what `endpoints.handler` holds.
    - `ancestry` — each declared type's own declared supertype and interfaces,
      as bare descriptors: what `_reaches` walks.
    - `methods` — the module's own declared methods, keyed by
      `(owner descriptor, method name)` with each one's parameter count: how
      a call site's target becomes the callee symbol whose body rung B reads.
      A call reaching nothing here left the module, which is exactly where the
      one hop must stop.
    """

    sites: dict[str, list[dict[str, Any]]]
    ancestry: dict[str, tuple[str, ...]]
    methods: dict[tuple[str, str], list[tuple[str, int]]]

    def callee_of(self, site: dict[str, Any]) -> str | None:
        """The module-local method a call site targets, or None.

        None where the target is not the module's own, and none where the
        module declares SEVERAL methods of that owner and name taking the same
        number of parameters: the fact stream identifies a call's target by
        owner and name, and an overload set it cannot separate is two possible
        callees, not one — a rung that picked either would be guessing which
        overload the compiler bound.
        """
        declared = self.methods.get((str(site["owner"]), str(site["name"])), [])
        arity = len(site["arguments"])
        matching = [symbol for symbol, parameters in declared if parameters == arity]
        return matching[0] if len(matching) == 1 else None


def _facts(workspace: Workspace) -> _Facts:
    sites: dict[str, list[dict[str, Any]]] = {}
    for row in effective_call_sites(workspace):
        sites.setdefault(str(row["caller"]), []).append(row)
    ancestry: dict[str, list[str]] = {}
    for row in workspace.query("supertypes"):
        supertype = json.loads(str(row["supertype"]))
        symbol = supertype.get("symbol") if isinstance(supertype, dict) else None
        if symbol is not None:
            ancestry.setdefault(bare_descriptor(str(row["symbol"])), []).append(
                bare_descriptor(str(symbol))
            )
    for row in workspace.query("implementations"):
        ancestry.setdefault(bare_descriptor(str(row["symbol"])), []).extend(
            bare_descriptor(str(entry)) for entry in json.loads(str(row["interfaces"]))
        )
    # Capability 9.13's ERASED superclass edge (`A-M12`), added beside the two
    # above rather than replacing either: `supertypes` carries the
    # parameterised-type reference a generic `extends` produces, which this
    # walk still wants, and `superclass` carries the edge itself — emitted for
    # every non-`Object` superclass, generic or not. Reading only the first
    # gave `class Order extends GeneratedMessage` no route to its marker at
    # all, which is `A-C4`'s rule in this engine.
    for row in workspace.query("superclasses"):
        ancestry.setdefault(bare_descriptor(str(row["symbol"])), []).append(
            bare_descriptor(str(row["superclass"]))
        )
    methods: dict[tuple[str, str], list[tuple[str, int]]] = {}
    for row in workspace.query("method_declarations"):
        enclosing = row["enclosing"]
        if enclosing is None:
            continue
        signature = cast(dict[str, Any], row["signature"] or {})
        descriptor = bare_descriptor(str(row["symbol"]))
        key = (bare_descriptor(str(enclosing)), method_name(descriptor))
        methods.setdefault(key, []).append(
            (str(row["symbol"]), len(signature.get("parameters") or []))
        )
    return _Facts(
        sites=sites,
        ancestry={owner: tuple(reached) for owner, reached in ancestry.items()},
        methods=methods,
    )
