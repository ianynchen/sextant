"""Dispatch registrations, read per group (spec 2026-11-05 §1-§3, from the actor design of
2026-11-04 §3b, §3d items 1-3).

In-process dispatch hands a value to a framework or a channel, and the framework calls the
handler(s) registered for it. A registration binds a key, the value's class (`class_arg`) or a
value equal to a constant (`value_arg`), to a handler, inside a group. The catalog's `dispatch`
setting says how many receive (`match`): `first`, the first registration in its group the value
matches (a behavior's cases, tried in order); `all`, every matching registration (listeners);
`one`, each value to one receiver decided at run time, so every matching registration is a
target. This pass reads the registrations into the `dispatch_registrations` table, one row per
registration with its place in its group; `reachable_handlers` is the match rule over those
rows, which the hop pass applies to a value's class and `served_cases` to every subtype of an
inbound key's class. Nothing here names a framework type: every owner, method and argument
position is the catalog's.

## A group is a chain

A catalog carrying `dispatch_registrations` is an ordinary `fluent` chain catalog (`roots`,
`steps`, `terminal`; D02 §2) whose chain ends are registrations rather than endpoint rows: the
endpoint loop leaves it out (`endpoints._reads_by_a_later_pass`) and this pass reads it. Under
`dispatch_registrations` it says what each registration call's arguments mean
(`Catalog.dispatch_registrations`), per exact overload. The chain is the shared walk
(`shapes/chains.chain_ends`), receiver to result: a registration returning a NEW builder is
followed through its result, one declared `returns_receiver: true` configures the builder it
is called on, so a builder held in a local and given its registrations statement by statement
is one chain. Each registration step carries its own call in the ONE `case` capture, and
`repeats` keeps the calls in chain order, so a registration's position is its place in that
capture and its meaning is looked up per call from the block (parallel per-field captures
would misalign where an overload has no such field). Each executable chain's end is one
group, named `<root's caller>#<root's ordinal>`.

**A registration no step names** (`messageAdapter(Class, f)`, an ask's reply mapper; spec
2026-11-04 §3d item 4) is no part of a chain: each of its call sites is a group of its own,
`<caller>#<ordinal>`, holding that one registration at position 0.

**A root inherited by the module's own class** (`this.newReceiveBuilder()`, which javac writes
as a call on the subclass) is matched by the shared walk itself: `chain_ends` widens every
root's owners with `Dispatch.heirs` (JVMS 5.4.3.3), for every chain catalog alike.

## What a row says

- `key_type` — the class literal at `class_arg` (a `class` argument's symbol); NULL for a
  value registration, a predicate-only one, or a class argument that is not a literal.
- `key_value` — the constant at `value_arg`, by identity (rule 8): the symbol of the `enum`
  or `field` argument the call reads. NULL for anything else.
- `key_object` — the channel object a receive site takes from (spec 2026-11-05 §3), as the call
  that made it, `<caller>#<ordinal>` (`ObjectKeys`); NULL for a type key, and for a receive
  whose object was not read.
- `predicated` — the registration declares a `predicate_arg`.
- `handler` — the method the handler argument names (`combinator._handler_of`: a method
  reference names the method, a constructor reference the constructor, a lambda its synthetic
  body), module-prefixed; NULL if not read.
- `delivers` — `returns_value`: the handler's return is a value handed to its own receiver.
- `match` — the catalog's `dispatch.match`.
- `mechanism` — the catalog's `dispatch.mechanism` (`dispatch_mechanism`); the hop pass asks a
  send's value only of its own mechanism's rows.

A registration the walk could not read (the builder handed to code we do not have, spec
2026-11-02 rule 2) keeps its position with every key column NULL: its class is unknown, so it
matches nothing and shadows nothing.

## A receive site is keyed by its object (`dispatch_receives`, spec 2026-11-05 §1, §3)

Under `dispatch: {key: object}` the code that receives a value is the code that takes from the
same channel object it was handed to, whatever the value's class. Each call site of a declared
receive is a group of its own, `<caller>#<ordinal>`, at position 0, its handler the method
making the call (`handler: enclosing`) or the function it hands the value to (`handler:
lambda_arg`, a receive given a function: `_function_handler`). Its key is the object it is called on (`object:
receiver`), followed to the call that MADE it (`ObjectKeys`): two sites act on one object
exactly when their receivers reach the same such call. One row per distinct object the walk
reaches; one row with `key_object` NULL where it reaches none, which matches nothing.

## Cost (GUIDELINES §8.7)

One object walk per receive site (`ObjectKeys`, on the resolve's shared value index, each
site's answer kept); a `lambda_arg` receive adds a dictionary lookup on the resolve's one read
of `method_declarations`. One `chain_ends` walk per declaring catalog, only where the module calls one of its roots'
owners or a type inheriting one (a module calling none pays one index lookup per owner each).
The heirs come from the resolve's one `Dispatch` (`Workspace.once`). A registration no step
names costs one index lookup per declared owner and heir.
"""

from collections.abc import Iterator, Mapping
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.dispatch import dispatch_of
from sextant.application.resolve.effective_annotations import _synthesis_target
from sextant.application.resolve.engines import annotation_driven
from sextant.application.resolve.engines.combinator import _handler_of
from sextant.application.resolve.shapes.arguments import (
    _CAPTURED_AT,
    _arg_at,
    call_site_index,
    declared_call_sites,
)
from sextant.application.resolve.shapes.chains import _method_symbols, chain_ends
from sextant.application.resolve.shapes.rooting import catalog_symbols
from sextant.application.resolve.values import (
    CYCLE,
    RECEIVER,
    cached_value_index,
    producer_paths,
)
from sextant.domain.symbols import (
    bare_descriptor,
    descriptor_slots,
    method_descriptor,
    owner_of,
    parameter_types,
)

# The capture each registration step carries its own call in (the catalog's `case: argN`).
_CASE = "case"
# The match rule under which an unpredicated match ends its group's search.
_FIRST = "first"
# The argument kinds that name a constant by identity (D00 §5): a named constant of its own
# type, and any other static field.
_CONSTANT_KINDS = ("enum", "field")
# The style whose mapping a catalog declaring `dispatch` reads as registrations
# (`annotation_driven.registrations`): each annotated method one registration per key.
_ANNOTATION_STYLE = "annotation_driven"
# A receive site's handler word naming the method making the call (`dispatch_receives`).
_ENCLOSING = "enclosing"
# The constructor name D00 §5 normalises every language's to: a construction makes an object.
_CONSTRUCTOR = "<init>"
# A JVM descriptor slot naming a class or interface type (JVMS 4.3.2), the only kind a null
# check hands back an object of.
_REFERENCE = "L"
# A receive's `object` naming the receiver; anything else is `argN`.
_RECEIVER_OBJECT = "receiver"
# The argument kinds an object of a module class arrives as (D00 §5): a new instance, and a
# constant of its own type (the shared instance of a closure capturing nothing).
_INSTANCE = "instance"
_CONSTANT = "enum"
# The argument kind a compiled lambda arrives as, naming its body method (D00 §5a).
_LAMBDA = "lambda"


def record_dispatch_registrations(workspace: Workspace, catalogs: list[Catalog]) -> None:
    """Replaces `dispatch_registrations` whole, from every catalog declaring
    `dispatch_registrations`."""
    workspace.derive("dispatch_registrations_reset")
    declaring = [
        catalog
        for catalog in catalogs
        if catalog.dispatch_registrations
        or catalog.dispatch_implementations
        or catalog.dispatch_receives
        or _reads_annotations(catalog)
    ]
    if not declaring:
        return
    rows: list[dict[str, Any]] = []
    # Two ends of one chain that read the same registrations (two paths through one builder)
    # are one group's rows once.
    seen: set[tuple[Any, ...]] = set()
    for catalog in declaring:
        for row in (
            *_rows_of(workspace, catalog),
            *_standalone_rows(workspace, catalog),
            *(
                annotation_driven.registrations(workspace, catalog)
                if _reads_annotations(catalog)
                else ()
            ),
            *_implementation_rows(workspace, catalog),
            *_receive_rows(workspace, catalog),
        ):
            row = row | {"mechanism": dispatch_mechanism(catalog)}
            key = tuple(row.values())
            if key not in seen:
                seen.add(key)
                rows.append(row)
    if rows:
        workspace.derive("dispatch_registrations_insert", rows=rows)


def dispatch_mechanism(catalog: Catalog) -> str:
    """The dispatch mechanism `catalog` names (`dispatch.mechanism`, D02 §2m): a send, a
    delivering handler and an inbound key reach only the registrations of catalogs naming the
    same one, so one framework's value never lands on another's handler in a module running
    both. Declared, never derived: the loader requires it beside every dispatch block and on
    every key catalog, and refuses one no registering catalog names."""
    if catalog.dispatch is None:
        raise CatalogError(
            f"loading catalog {catalog.source}: it reads dispatch registrations and declares "
            f"no `dispatch.mechanism` saying whose (spec 2026-11-05 §2)"
        )
    return catalog.dispatch["mechanism"]


def _reads_annotations(catalog: Catalog) -> bool:
    """Whether `catalog`'s mapping is read as registrations: an annotation catalog declaring
    `dispatch` (spec 2026-11-05 §2), which the endpoint loop leaves out for the same reason
    (`endpoints._reads_by_a_later_pass`)."""
    return (
        catalog.style == _ANNOTATION_STYLE
        and catalog.dispatch is not None
        and "key" in catalog.dispatch
    )


def reachable_handlers(
    rows: list[dict[str, Any]],
    key_type: str | None,
    key_value: str | None,
    supertypes: Mapping[str, set[str]],
    match: str,
) -> list[dict[str, Any]]:
    """The registrations a value reaches under the `match` rule (spec 2026-11-05 §1). `first`:
    per group in `rows`' order, the first unpredicated registration it matches, and every
    predicated one before it that matches (a predicate may decline, so it never shadows, spec
    2026-11-04 §3d item 2). `all` and `one`: every registration it matches, in every group —
    every listener of its class, or every receiver one of which takes it. A class registration
    matches when the value's class is that class or any of its supertypes; a value
    registration when `key_value` is its constant; a predicate-only registration (no class, no
    value, predicated) matches every value whose class was read. A registration whose class is
    unknown matches nothing. `rows` are `dispatch_registrations` rows.

    `supertypes` maps a type to its supertypes, classes and interfaces alike; the closure is
    computed HERE, transitively, so a map of direct supertypes (`type_hierarchy`'s rows, or
    `Dispatch.ancestors` read as names) is enough, and a transitive one gives the same answer.
    A constant value is passed with BOTH its class and its value: a class registration takes it
    by class, a value registration by identity."""
    reached: list[dict[str, Any]] = []
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row["group"]), []).append(row)
    assignable = set[str]() if key_type is None else _ancestry(key_type, supertypes)
    for registrations in groups.values():
        for registration in sorted(registrations, key=lambda row: int(row["position"])):
            if not _matches(registration, assignable, key_value):
                continue
            reached.append(registration)
            if match == _FIRST and not registration["predicated"]:
                break
    return reached


def reached_by(
    rows: list[dict[str, Any]],
    key_type: str | None,
    key_value: str | None,
    supertypes: Mapping[str, set[str]],
) -> list[dict[str, Any]]:
    """`reachable_handlers` over rows of every match rule at once, each row under its own
    (`dispatch_registrations.match`): the registrations of each rule are asked by that rule,
    in the rules' first-seen order, so a hop pass reading one table never applies one
    catalog's rule to another's registrations."""
    by_match: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_match.setdefault(str(row["match"]), []).append(row)
    return [
        registration
        for match, matching in by_match.items()
        for registration in reachable_handlers(matching, key_type, key_value, supertypes, match)
    ]


def certain_cases(
    rows: list[dict[str, Any]],
    key_type: str,
    supertypes: Mapping[str, set[str]],
    constant_classes: Mapping[str, str | None],
    known_classes: frozenset[str],
    declared: bool = True,
    key_value: str | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """The registrations a value is asked of, and whether the send is also NOT READ.

    **A keyless registration** (key, value and object all NULL, not predicated: a generic
    listener parameter, ruling 16, or a case the walk did not read) may take ANY value, its
    key being unknown, so it makes every send of its mechanism also not read (under `first`,
    when it comes before the group's first certain case), never a stop naming the value's
    class as handled by nobody. That holds for a value read exactly (`declared` False, `new
    Command()`, a constant `key_value`) as for one read by its declared type.

    The registrations a value read only by its DECLARED type (a call's declared return, a
    parameter's or a field's type) is asked of, and whether the send is also NOT READ. Such a
    value is `key_type` or any subtype of it, so every registration of `key_type` or a
    supertype of it is certainly reached, and those hops are true under every `match`
    (ruling 14 as corrected by the re-review, 2026-11-05). What the declared type cannot say:

    A registration not certainly reached may still take some subtype of the value: a class
    registration naming a strict subtype, or a type unrelated to `key_type` (neither above nor
    below it) unless both are classes (`known_classes`: a subtype of a class extends no
    unrelated class, and an interface-typed value's subtype may implement any interface), and
    a value registration whose constant's class is not such an unrelated class.

    - **Under `all` and `one`**, any such registration keeps the certain hops and makes the
      send also not read, never a stop naming `key_type` as if nobody handled it.
    - **Under `first`**, such a case before the group's first certain unpredicated case leaves
      the group out (not read there); a case after the first certain one is never reached. Finality is not read, so a final declared type is
      treated as one a subclass may extend (not read where it could have been, never false).

    Returns the registrations to ask (every row but the left-out groups) and whether the send
    adds the not-read row."""
    above = _ancestry(key_type, supertypes)

    def below(type_: str) -> bool:
        return type_ != key_type and key_type in _ancestry(type_, supertypes)

    def unrelated_class(type_: str) -> bool:
        return (
            type_ not in above
            and not below(type_)
            and type_ in known_classes
            and key_type in known_classes
        )

    def keyless(row: Mapping[str, Any]) -> bool:
        return (
            row["key_type"] is None
            and row["key_value"] is None
            and row.get("key_object") is None
            and not row["predicated"]
        )

    def may_take(row: Mapping[str, Any]) -> bool:
        """Whether a registration not certainly reached may still take some subtype of the
        value: a class key not above `key_type` and not a class unrelated to it, or a value
        key whose constant's class is not such a class."""
        if keyless(row):
            return True
        if not declared:
            return False
        if row["key_type"] is not None:
            return str(row["key_type"]) not in above and not unrelated_class(str(row["key_type"]))
        if row["key_value"] is not None:
            constant_class = constant_classes.get(str(row["key_value"]))
            return constant_class is None or not unrelated_class(constant_class)
        return False

    narrower = False
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row["match"] == _FIRST:
            groups.setdefault(str(row["group"]), []).append(row)
        elif may_take(row):
            narrower = True
    undecided: set[str] = set()
    for group, registrations in groups.items():
        for registration in sorted(registrations, key=lambda row: int(row["position"])):
            case_type = registration["key_type"]
            certain = (case_type is not None and str(case_type) in above) or (
                key_value is not None and registration["key_value"] == key_value
            )
            if certain:
                if not registration["predicated"]:
                    break
                continue
            if may_take(registration):
                undecided.add(group)
                break
    kept = [row for row in rows if row["match"] != _FIRST or str(row["group"]) not in undecided]
    return kept, narrower or bool(undecided)


def served_cases(
    rows: list[dict[str, Any]],
    key_class: str | None,
    supertypes: Mapping[str, set[str]],
    constant_classes: Mapping[str, str | None],
) -> list[dict[str, Any]]:
    """The registrations a value of `key_class` can reach, whichever subtype it is: an inbound
    key's handlers (spec 2026-11-04 §3d item 6), where the key names a class (`Command`) and a
    sender sends any instance of it.

    The hop rule, asked once per candidate class, so the two always agree: `reached_by` for
    `key_class` and for each type in `supertypes` that has it among its supertypes (a
    `Reserve`, a `Release`), and for each constant a value registration names whose class
    (`constant_classes`, the constant's declared type) is one of those types
    (`Tick.INSTANCE`). A registration shadowed for every one of them is not reached; a
    predicated one is, as for a hop. Reading "every registration under a subtype" instead
    would name one that a `Command` registration before it shadows, a handler no value can
    run, and would miss a `Command` registration taking a subtype it was not registered for.

    No class (`None`, not read) reaches nothing, never every registration. One entry per
    registration, in `(group, position)` order."""
    if key_class is None:
        return []
    classes = {key_class} | {
        candidate for candidate in supertypes if key_class in _ancestry(candidate, supertypes)
    }
    values: list[tuple[str, str | None]] = [(candidate, None) for candidate in sorted(classes)]
    for constant in sorted({str(row["key_value"]) for row in rows if row["key_value"]}):
        constant_class = constant_classes.get(constant)
        if constant_class in classes:
            values.append((str(constant_class), constant))
    reached: dict[tuple[str, int], dict[str, Any]] = {}
    for candidate, value in values:
        for registration in reached_by(rows, candidate, value, supertypes):
            reached.setdefault(
                (str(registration["group"]), int(registration["position"])), registration
            )
    return [reached[key] for key in sorted(reached)]


def _ancestry(start: str, supertypes: Mapping[str, set[str]]) -> set[str]:
    """`start` and every supertype of it, transitively: the classes a `start` is assignable
    to."""
    found = set[str]()
    pending = [start]
    while pending:
        current = pending.pop()
        if current not in found:
            found.add(current)
            pending.extend(supertypes.get(current, ()))
    return found


def _matches(registration: Mapping[str, Any], assignable: set[str], key_value: str | None) -> bool:
    if registration["key_type"] is not None:
        return registration["key_type"] in assignable
    if registration["key_value"] is not None:
        return key_value is not None and registration["key_value"] == key_value
    return bool(registration["predicated"])


def _rows_of(workspace: Workspace, catalog: Catalog) -> Iterator[dict[str, Any]]:
    """One catalog's registrations, group by group, in the walk's order."""
    registrations = catalog.dispatch_registrations
    if not registrations:
        return
    match = _match_of(catalog)
    _check_steps(catalog)
    index = workspace.once(call_site_index)
    dispatch = workspace.once(dispatch_of)
    if not any(
        called in index.positions_by_owner
        for root in catalog.matches.get("roots", [])
        for owner in catalog_symbols(root.get("owner"), f"{catalog.source}: roots[].owner")
        for called in (owner, *dispatch.heirs(owner, str(root.get("method"))))
    ):
        return
    method_symbols = workspace.once(_handler_symbols)
    for end in chain_ends(workspace, catalog):
        group = f"{end.root['caller']}#{end.root['ordinal']}"
        # A builder built with no registration on it (an immutable builder whose
        # registrations' results were dropped) is a group with nothing to write.
        cases = end.captures.get(_CASE)
        if cases is None:
            continue
        for position, captured in enumerate(cases if isinstance(cases, tuple) else (cases,)):
            site = _site_of(captured, index.by_caller)
            registration = None if site is None else _registration_of(site, registrations)
            if site is None or registration is None:
                yield _unread_case(group, position, match)
                continue
            yield _case(group, position, site, registration, method_symbols, match)


def _standalone_rows(workspace: Workspace, catalog: Catalog) -> Iterator[dict[str, Any]]:
    """The registrations made by a call no step of a chain names: each call site of such a
    registration is a group of its own, `<caller>#<ordinal>`, at position 0
    (`messageAdapter(C, f)`, an ask's reply mapper). A call made through a type inheriting
    the declared owner is matched by `Dispatch.heirs`, as a root is."""
    stepped = {
        (owner, str(step.get("method")), parameter_types(str(step.get("descriptor"))))
        for step in catalog.matches.get("steps", [])
        for owner in catalog_symbols(step.get("owner"), f"{catalog.source}: steps[].owner")
    }
    standalone = [
        registration
        for registration in catalog.dispatch_registrations
        if (
            registration["owner"],
            registration["method"],
            parameter_types(registration["descriptor"]),
        )
        not in stepped
    ]
    if not standalone:
        return
    method_symbols = workspace.once(_handler_symbols)
    match = _match_of(catalog)
    for site, registration in declared_call_sites(workspace, standalone):
        group = f"{site['caller']}#{site['ordinal']}"
        yield _case(group, 0, site, dict(registration), method_symbols, match)


def _implementation_rows(workspace: Workspace, catalog: Catalog) -> Iterator[dict[str, Any]]:
    """The registrations made by implementing an interface (`dispatch_implementations`, spec
    2026-11-05 §4 item 5): each module type below the declared `owner` (`Dispatch.subtypes`,
    transitively, through types the workspace has headers for) that declares the method
    itself registers it, keyed by the type of its parameter at `value_arg`, in a group of
    its own (the handler), at position 0.

    The method is joined by name AND the declared descriptor — the interface's, erased — so
    for a generic implementation (`ApplicationListener<OrderPlaced>`) what the join finds is
    the compiler's synthetic bridge, which keys `ApplicationEvent` and names a method nobody
    wrote. It is carried to the method it forwards to by the rule the inheritance walk
    applies to a mapping found through a bridge (`effective_annotations._synthesis_target`,
    OI-47: the same class's one same-name, same-arity method not synthetic); where that is
    not exactly one method, or the method has no parameter at `value_arg`, the row is kept
    with no key (it matches nothing, never every value), as an unread annotated method is; so
    is a method whose parameter is generic (`annotation_driven.generic_parameter`: a base
    class's `onApplicationEvent(E)`, which the framework dispatches by each subclass's binding
    of `E`, never by its erasure). A type inheriting the method
    rather than declaring it writes nothing: the type declaring it is below `owner` too.

    Cost (GUIDELINES §8.7): one read of `method_declarations` per resolve (cached), then a
    dictionary lookup per subtype of each declared interface."""
    if not catalog.dispatch_implementations:
        return
    match = _match_of(catalog)
    dispatch = workspace.once(dispatch_of)
    declared = workspace.once(_declarations)
    for entry in catalog.dispatch_implementations:
        for implementer in dispatch.subtypes.get(entry["owner"], ()):
            joined = method_descriptor(implementer, entry["method"], entry["descriptor"])
            siblings = declared.by_type.get(implementer, [])
            if joined not in declared.symbols:
                continue
            target = _synthesis_target(joined, siblings, declared.signatures, declared.modifiers)
            parameters = (
                [] if target is None else (declared.signatures.get(target) or {}).get("parameters")
            ) or []
            key = None
            if entry["value_arg"] < len(parameters):
                parameter = parameters[entry["value_arg"]]
                if not annotation_driven.generic_parameter(parameter):
                    key = parameter.get("erased_symbol") or (parameter.get("type") or {}).get(
                        "symbol"
                    )
            # A bridge forwarding to no ONE method, or a method with no parameter at
            # `value_arg`, is still a registration: kept with no key, so it matches nothing,
            # its handler the method the join found (the one the framework calls).
            handler = declared.symbols[joined if target is None else target]
            yield {
                "group": handler,
                "position": 0,
                "key_type": None if not key else bare_descriptor(str(key)),
                "key_value": None,
                "key_object": None,
                "predicated": False,
                "handler": handler,
                "delivers": False,
                "match": match,
            }


def _receive_rows(workspace: Workspace, catalog: Catalog) -> Iterator[dict[str, Any]]:
    """The registrations made by taking from a channel object (`dispatch_receives`, spec
    2026-11-05 §1, §3): each call site of a declared receive is a group of its own,
    `<caller>#<ordinal>`, at position 0, keyed by each object the position its `object` names
    reaches (the receiver, or `argN`; `ObjectKeys`), its handler the method making the call. One row with `key_object` NULL
    where no object was read: it matches nothing, never every send.

    A receive handing its value to a function argument (`handler: lambda_arg`) is handled by that function (`_function_handler`), never by its enclosing method,
    which is not the code that handles the value; one naming no method of it is refused."""
    if not catalog.dispatch_receives:
        return
    match = _match_of(catalog)
    objects = ObjectKeys(workspace, catalog)
    for site, receive in declared_call_sites(workspace, catalog.dispatch_receives):
        # The object the call takes from: its receiver, or the argument a static helper is
        # handed the channel at (`object: argN`).
        slot: int | str = (
            RECEIVER
            if receive["object"] == _RECEIVER_OBJECT
            else int(str(receive["object"])[len("arg") :])
        )
        handler: str | None = str(site["caller"])
        if receive["handler"] != _ENCLOSING:
            if receive.get("handler_method") is None or receive.get("handler_arg") is None:
                raise CatalogError(
                    f"loading catalog {catalog.source}: `{receive['method']}` declares "
                    f"`handler: {receive['handler']}` and names no `handler_arg` and "
                    f"`handler_method` saying which method of which argument handles the "
                    f"value (spec 2026-11-05 §2)"
                )
            handler = _function_handler(workspace, site, receive)
        group = f"{site['caller']}#{site['ordinal']}"
        made: list[str | None] = [key for key in objects.of(site, slot) if key is not None]
        for key in made or [None]:
            yield {
                "group": group,
                "position": 0,
                "key_type": None,
                "key_value": None,
                "key_object": key,
                "predicated": False,
                "handler": handler,
                "delivers": False,
                "match": match,
            }


def _function_handler(
    workspace: Workspace, site: Mapping[str, Any], receive: Mapping[str, Any]
) -> str | None:
    """The method handling the value a `handler: lambda_arg` receive hands to its function
    argument. A compiled lambda (the `lambda` kind, a body method the facts name) is handled by
    that body, read as every handler argument is (`combinator._handler_of`). Otherwise the
    argument at `handler_arg` is an object of a module class (a new instance, or
    the one shared instance of a closure that captures nothing, which the compiler reads as a
    constant of its own type), and the library calls `handler_method` `handler_descriptor` on
    it. That method is joined on the class by name and the declared, erased descriptor, and
    where the join finds the compiler's synthetic bridge (a generic implementation's) it is
    carried to the method it forwards to (`effective_annotations._synthesis_target`, as
    `_implementation_rows` does). None where the argument is any other kind (a parameter, a
    library object) or its class does not itself declare the method: the handler is not
    read, never guessed."""
    position = int(receive["handler_arg"])
    argument = _arg_at(site["arguments"], position)
    kind = None if argument is None else argument.get("kind")
    if kind == _LAMBDA:
        return _handler_of(
            site["arguments"], frozenset({position}), workspace.once(_handler_symbols)
        )
    if kind == _INSTANCE:
        named: str | None = bare_descriptor(str(argument["symbol"]))  # type: ignore[index]
    elif kind == _CONSTANT:
        named = owner_of(bare_descriptor(str(argument["symbol"])))  # type: ignore[index]
    else:
        return None
    declared = workspace.once(_declarations)
    joined = method_descriptor(
        str(named), str(receive["handler_method"]), str(receive["handler_descriptor"])
    )
    if joined not in declared.symbols:
        return None
    target = _synthesis_target(
        joined, declared.by_type.get(str(named), []), declared.signatures, declared.modifiers
    )
    return declared.symbols[joined if target is None else target]


class ObjectKeys:
    """Which channel object a call site acts on, as the call that made it (spec 2026-11-05 §3):
    `<caller>#<ordinal>` of each producer the object at a site's position (its receiver, or
    an argument a static helper is handed) reaches, None for each path that reaches none. Two
    sites act on one object exactly when they reach the same producer.

    The object is followed by the value walk's object reader (`values.producer_paths`,
    `which_object`: a call made ON the object does not make it another), through locals,
    parameters across callers, helper returns and fields (a field read answered by each write
    of that field, in its writer's frame). Where it ends is any call that makes an object: a
    construction (`<init>`, the module's or a library's), or a call whose body is not here
    (`ValueIndex.unscanned`, the unseen-object rule's producers: a library factory such as
    `Queues.newLinkedBlockingQueue()`, or a getter handing back an object we cannot follow
    further). A path ending anywhere else — a parameter nothing in the module calls, the
    object a container injects — is None: the object is not read.

    **A null check is not where an object is made.** A call the catalogs declare takes its
    value without handing it off (`not_hand_offs`, `value-models/compiler-null-checks.yml`:
    `Objects.requireNonNull`, a compiler's own null checks) and that returns a reference is
    followed on into its arguments of the type it returns, rather than ending at the call (a
    structural rule over the descriptor, never a model of one method). For a check returning
    its argument (`this.q = Objects.requireNonNull(q)`) that argument is the object. One entry
    returns null instead: the compiler's write of null into a spilled slot it read the value
    from (`nullOutSpilledVariable`, CP-59 finding 21). Followed into its argument, the walk
    comes back to that slot, a cycle adding no object, so it is never named as the object's
    maker either; it adds no object it was not already given. **Where every path past a null
    check ends at an object not read** (`this.q = Objects.requireNonNull(q)`, `q` a parameter
    a container fills), the check's own call is the key: every reference it hands back is the
    one object, so a put and a take through it still meet (final review, deferred minor).

    **A view is the object it views.** A call the catalog declares under `dispatch_views`
    (CP-59 finding 22: a read-only wrapper of a flow, a flow reading a channel) hands back
    another reference to the object at its declared position, so the walk continues into that
    position rather than ending at the call. Catalog data, so the walk names no library type. A null check no catalog declares (Guava's
    `Preconditions.checkNotNull`) still ends the walk: one queue becomes two keys, a missing
    hop.

    **A path that comes back to where it started adds no object** (`values.CYCLE`): a field
    copied back into itself — a compiled closure copying its captured value into a fresh
    instance of its own class, a copy constructor — carries only the values the other paths reaching
    that field bring, so it is skipped rather than read as an object not read. Where every path
    is one, no object was read.

    **Stated bounds** (D01 `hops`, D02 §2m, spec 2026-11-05 §4 item 7), each over-linking:
    a field read is answered by every write of that field, so two instances of one class each
    holding its own queue in that field are one object; two objects one module helper makes
    (`newQueue()` called twice) are one; and two objects one library call site hands back are
    one.

    Cost (GUIDELINES §8.7): the resolve's one shared value index, one walk per site and
    position asked (and one more per null check passed through), each answer kept."""

    def __init__(self, workspace: Workspace, catalog: Catalog) -> None:
        self._index = cached_value_index(workspace, catalog.not_hand_offs, catalog.hand_off_effects)
        self._made = self._index.unscanned | frozenset(
            (built, _CONSTRUCTOR) for built in self._index.constructed
        )
        self._keys: dict[tuple[str, int, int | str], tuple[str | None, ...]] = {}
        # The catalog's declared views, by owner, name and parameter types: the position of
        # the object each hands back a view of.
        self._views: dict[tuple[str, str, str], int | str] = {
            (view["owner"], view["method"], parameter_types(view["descriptor"])): (
                RECEIVER
                if view["object"] == _RECEIVER_OBJECT
                else int(str(view["object"])[len("arg") :])
            )
            for view in catalog.dispatch_views
        }

    def of(self, site: Mapping[str, Any], slot: int | str = RECEIVER) -> tuple[str | None, ...]:
        """Each object at `slot` of `site` (its receiver by default) can be, once each, in the
        walk's order."""
        at = (str(site["caller"]), int(site["ordinal"]), slot)
        if at not in self._keys:
            self._keys[at] = tuple(dict.fromkeys(self._ends(site, slot, frozenset()))) or (None,)
        return self._keys[at]

    def _ends(
        self, site: Mapping[str, Any], slot: int | str, passed: frozenset[tuple[str, int]]
    ) -> Iterator[str | None]:
        for producer, _ in producer_paths(self._index, site, slot, self._made, which_object=True):
            if producer.reason == CYCLE:
                continue
            if producer.caller is None or producer.ordinal is None:
                yield None
                continue
            at = (producer.caller, producer.ordinal)
            if at in passed:
                # Back at a null check this walk passed through: a cycle, adding no object.
                continue
            made = self._index.sites.get(at)
            viewed = () if made is None else self._viewed(made)
            checked = () if made is None or viewed else self._checked_arguments(made)
            if made is None or not (viewed or checked):
                yield f"{producer.caller}#{producer.ordinal}"
                continue
            ends = [
                end
                for argument in viewed or checked
                for end in self._ends(made, argument, passed | {at})
            ]
            # A null check over an object read on no path (a parameter a container fills) is
            # still one object on every reference it hands back: its own call is the key.
            if checked and ends and all(end is None for end in ends):
                yield f"{producer.caller}#{producer.ordinal}"
                continue
            yield from ends

    def _viewed(self, site: Mapping[str, Any]) -> tuple[int | str, ...]:
        """The position of the object a declared view call hands back a view of (class
        docstring), or nothing for any other call."""
        recorded = site.get("descriptor")
        if recorded is None:
            return ()
        key = (str(site.get("owner")), str(site["name"]), parameter_types(str(recorded)))
        return (self._views[key],) if key in self._views else ()

    def _checked_arguments(self, site: Mapping[str, Any]) -> tuple[int | str, ...]:
        """The arguments a declared null check hands back (class docstring): where `site`
        calls a `not_hand_offs` owner or method and returns a reference, each argument whose
        declared type is the type it returns. Empty for any other call."""
        owner, descriptor = str(site.get("owner")), site.get("descriptor")
        declared = self._index.not_hand_offs
        if descriptor is None or (
            owner not in declared and owner + str(site["name"]) not in declared
        ):
            return ()
        slots, returned = descriptor_slots(str(descriptor))
        if not returned.startswith(_REFERENCE):
            return ()
        return tuple(index for index, slot in enumerate(slots) if slot == returned)


class _Declarations:
    """The module's declared methods, read once per resolve: each bare symbol's own symbol
    as the fact wrote it, signature and modifiers, and each bare type's methods, bare."""

    def __init__(self, workspace: Workspace) -> None:
        self.symbols: dict[str, str] = {}
        self.signatures: dict[str, dict[str, Any] | None] = {}
        self.modifiers: dict[str, dict[str, Any] | None] = {}
        self.by_type: dict[str, list[str]] = {}
        for row in workspace.query("method_declarations"):
            bare = bare_descriptor(str(row["symbol"]))
            self.symbols[bare] = str(row["symbol"])
            self.signatures[bare] = row["signature"]  # type: ignore[assignment]
            self.modifiers[bare] = row["modifiers"]  # type: ignore[assignment]
            if row["enclosing"] is not None:
                self.by_type.setdefault(bare_descriptor(str(row["enclosing"])), []).append(bare)


def _declarations(workspace: Workspace) -> _Declarations:
    return _Declarations(workspace)


def _handler_symbols(workspace: Workspace) -> dict[str, str]:
    """The module's method symbols by bare descriptor (`chains._method_symbols`), and its
    constructors: a constructor reference (`messageAdapter(C, Wrapped::new)`, the samples'
    usual adapter) names the constructor as the handler, the body that makes the value."""
    symbols = dict(workspace.once(_method_symbols))
    for row in workspace.query("constructor_declarations"):
        symbols.setdefault(bare_descriptor(str(row["symbol"])), str(row["symbol"]))
    return symbols


def _match_of(catalog: Catalog) -> str:
    """The catalog's `dispatch.match`, which every row it registers carries. The loader
    requires the setting beside a `dispatch_registrations` block; a catalog built by hand
    without it is refused here rather than read under a rule it never stated."""
    if catalog.dispatch is None:
        raise CatalogError(
            f"loading catalog {catalog.source}: it declares `dispatch_registrations` and no "
            f"`dispatch` setting saying how they are matched (spec 2026-11-05 §2)"
        )
    return catalog.dispatch["match"]


def _case(
    group: str,
    position: int,
    site: Mapping[str, Any],
    registration: Mapping[str, Any],
    method_symbols: dict[str, str],
    match: str,
) -> dict[str, Any]:
    arguments = site["arguments"]
    key_type = None
    if registration["class_arg"] is not None:
        literal = _arg_at(arguments, registration["class_arg"])
        if literal is not None and literal.get("kind") == "class":
            key_type = literal.get("symbol")
    key_value = None
    if registration["value_arg"] is not None:
        constant = _arg_at(arguments, registration["value_arg"])
        if constant is not None and constant.get("kind") in _CONSTANT_KINDS:
            key_value = constant.get("symbol")
    return {
        "group": group,
        "position": position,
        "key_type": key_type,
        "key_value": key_value,
        "key_object": None,
        "predicated": registration["predicate_arg"] is not None,
        "handler": _handler_of(arguments, frozenset({registration["handler_arg"]}), method_symbols),
        "delivers": registration["returns_value"],
        "match": match,
    }


def _unread_case(group: str, position: int, match: str) -> dict[str, Any]:
    return {
        "group": group,
        "position": position,
        "key_type": None,
        "key_value": None,
        "key_object": None,
        "predicated": False,
        "handler": None,
        "delivers": False,
        "match": match,
    }


def _site_of(captured: Any, by_caller: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any] | None:
    """The registration call a `case` capture was read at, or None for a part the walk did
    not read (it carries no place)."""
    if not isinstance(captured, Mapping) or _CAPTURED_AT not in captured:
        return None
    caller, ordinal, _ = captured[_CAPTURED_AT]
    return next(
        (site for site in by_caller.get(caller, ()) if int(site["ordinal"]) == int(ordinal)),
        None,
    )


def _registration_of(
    site: Mapping[str, Any], registrations: tuple[dict[str, Any], ...]
) -> dict[str, Any] | None:
    """The declared registration `site` calls: its owner, its name and its parameter types."""
    recorded = site.get("descriptor")
    if recorded is None:
        return None
    return next(
        (
            registration
            for registration in registrations
            if registration["owner"] == site["owner"]
            and registration["method"] == site["name"]
            and parameter_types(registration["descriptor"]) == parameter_types(str(recorded))
        ),
        None,
    )


def _check_steps(catalog: Catalog) -> None:
    """Refuses a step carrying a `case` that names no single declared registration: its calls
    would be cases nothing says how to read, and a step and its registration spelled two ways
    would read every call of the overload as an unread case."""
    for step in catalog.matches.get("steps", []):
        if _CASE not in (step.get("captures") or {}):
            continue
        owners = catalog_symbols(step.get("owner"), f"{catalog.source}: steps[].owner")
        declared = step.get("descriptor")
        matching = [
            registration
            for registration in catalog.dispatch_registrations
            if registration["owner"] in owners
            and registration["method"] == step.get("method")
            and declared is not None
            and parameter_types(registration["descriptor"]) == parameter_types(str(declared))
        ]
        if len(owners) != len(matching):
            raise CatalogError(
                f"loading catalog {catalog.source}: step `{step.get('method')}` "
                f"`{declared}` captures `{_CASE}` but {len(matching)} `dispatch_registrations` "
                f"entries say how to read it on its {len(owners)} owner(s); each owner needs "
                f"exactly one (spec 2026-11-04 §3b)"
            )
