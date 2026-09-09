"""Two handlers a framework would REFUSE to register on one address (F5 §6.1, W28).

## What this is, and what it is not

DR-6: predict the framework's behaviour exactly, never our own. Spring MVC does not pick
between two identical mappings — it throws at startup, so the application does not run.
An analysis that quietly published one of the two rows, or folded them together, would
describe a service that cannot exist.

**It is not "two rows on one address".** That is ordinary in several frameworks and this
repo's own fixture has one: `@KafkaListener` on a class with `@KafkaHandler` on its
methods dispatches by PAYLOAD TYPE, so `order-polymorphic` is served by
`ClassLevelListener#onDefault` and `#onEvent` together and Spring Kafka is perfectly happy.
Reporting that would be the defect class this codebase keeps finding: a rule mirrored from
one framework and applied to a set that is not that framework's. So the rule is CATALOG
data — `mapping.duplicate: conflict` — and only the two catalogs whose annotations reach
`RequestMappingHandlerMapping` declare it.

## What Spring actually compares, read from Spring

`AbstractHandlerMethodMapping$MappingRegistry.validateMethodMapping` keys its registry on
the mapping object itself and throws `IllegalStateException` when a DIFFERENT handler
method is already registered under an equal one (spring-webmvc 6.1.6 bytecode). That
mapping is a `RequestMappingInfo`, and its `equals` compares **seven** conditions:
patterns, methods, params, headers, consumes, produces, and a custom condition.

Six of the seven are readable here: the endpoint row carries the path, the verb and both
media columns, and `params`/`headers` are attributes of the mapping annotation itself,
named by the catalog as `discriminators`. Class-level and method-level values are UNIONED,
because that is what `ParamsRequestCondition.combine` does — a `LinkedHashSet` of one
side's expressions with the other's added.

**The seventh is a stated boundary.** A custom `RequestCondition` is code on a
`RequestMappingHandlerMapping` subclass, not an attribute anywhere in the class file, so
two mappings separated only by one are indistinguishable from a genuine conflict here. A
module that declares such a subclass gets no conflict reported at all rather than a wrong
one — see `_declares_a_custom_condition`.

## Measured base rate

Across the orders-service fixture and `mall-admin`, `spring-petclinic-rest` and
`jhipster-sample-app`: **zero genuine conflicts**, one `@KafkaHandler` pair that must not
be reported, and **zero uses of `params=` or `headers=` anywhere**. So the discriminators
exist to keep a finding honest rather than to explain one that is already there — which
is the right way round: a detector's first duty is not to invent findings.
"""

import json
from typing import Any

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.open_questions import record_open_questions
from sextant.domain.closed_sets import Direction
from sextant.domain.symbols import bare_descriptor, owner_of, type_descriptor

# The one value `mapping.duplicate` may take. Absence means "several handlers on one
# address is ordinary for this framework", which is the answer for every catalog that
# does not name it — Kafka, JMS, SQS, AMQP, STOMP, GraphQL and the rest.
_CONFLICT = "conflict"


def record_routing_conflicts(workspace: Workspace, catalogs: list[Catalog]) -> None:
    """Files one question per address two different handlers claim, where the catalog
    that derived them says the framework refuses that."""
    declaring = {
        catalog.id: catalog
        for catalog in catalogs
        if str((catalog.matches.get("mapping") or {}).get("duplicate", "")) == _CONFLICT
    }
    if not declaring:
        return
    annotations = _annotation_args(workspace)
    claimed: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in workspace.query("endpoints"):
        catalog = declaring.get(str(row["catalog_id"]))
        if catalog is None or str(row["direction"]) != Direction.INBOUND:
            continue
        if row["path"] is None or row["handler"] is None:
            # An unresolved row names no address, and a row naming no handler names
            # nothing that could conflict with anything.
            continue
        handler = bare_descriptor(str(row["handler"]))
        mapping = catalog.matches.get("mapping") or {}
        # Everything the framework compares that this workspace can see. The four
        # columns are the row's own; the discriminators come off the annotation.
        identity = (
            str(row["protocol"]),
            None if row["method"] is None else str(row["method"]),
            str(row["path"]),
            None if row["consumes"] is None else str(row["consumes"]),
            None if row["produces"] is None else str(row["produces"]),
            _discriminators(mapping, annotations, handler),
        )
        claimed.setdefault(identity, []).append({"handler": handler, "catalog": catalog})
    rows: list[dict[str, object]] = []
    # Sorted so two runs file the ledger in one order (NFR-1).
    for identity in sorted(claimed, key=lambda key: tuple(str(part) for part in key)):
        holders = claimed[identity]
        handlers = sorted({holder["handler"] for holder in holders})
        if len(handlers) < 2:
            # One handler, however many rows it took to say so — a method carrying two
            # annotations of one address is one registration, not two.
            continue
        catalog = holders[0]["catalog"]
        if _declares_a_custom_condition(workspace, catalog):
            continue
        protocol, method, path, _consumes, _produces, _discriminators_of = identity
        rows.append(
            {
                "protocol": protocol,
                "method": method,
                "path": path,
                "question": "routing_conflict",
                "candidates": json.dumps([{"handler": handler} for handler in handlers]),
                "evidence": (
                    "one address, two handlers, and every condition this workspace can "
                    "read is equal: path, verb, consumes, produces and the catalog's own "
                    "discriminators. A custom RequestCondition is not readable from a "
                    "class file and no subclass registering one was found"
                ),
            }
        )
    record_open_questions(workspace, rows)


def _discriminators(
    mapping: dict[str, Any], annotations: dict[str, list[dict[str, Any]]], handler: str
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """The declared discriminator attributes for one handler, class and method values
    UNIONED, as a sorted, hashable value.

    Union rather than override because that is what Spring does:
    `ParamsRequestCondition.combine` builds a `LinkedHashSet` of one side's expressions
    and adds the other's, and the condition's own equality is set equality. A rule that
    let the method's value replace the class's would report a conflict between two
    methods in one `@RequestMapping(params = "v=1")` class, which Spring registers
    happily.
    """
    names = [str(name) for name in mapping.get("discriminators") or []]
    if not names:
        return ()
    wanted = {type_descriptor(str(fqn)) for fqn in _mapping_annotations(mapping)}
    owner = owner_of(handler)
    found: dict[str, set[str]] = {name: set() for name in names}
    for target in (handler, owner):
        if target is None:
            continue
        for use in annotations.get(target, []):
            if use["annotation"] not in wanted:
                continue
            for name in names:
                value = use["args"].get(name)
                if value is None:
                    continue
                found[name].update(
                    str(entry) for entry in (value if isinstance(value, list) else [value])
                )
    return tuple((name, tuple(sorted(found[name]))) for name in sorted(names))


def _mapping_annotations(mapping: dict[str, Any]) -> list[str]:
    """Every annotation fqn this catalog's mapping block names — the per-verb ones and
    the class-level prefix annotation, which is where a class-wide `params` is written."""
    fqns = [str(entry["fqn"]) for entry in mapping.get("annotations") or []]
    prefix = mapping.get("prefix_annotation")
    if prefix is not None:
        fqns.append(str(prefix))
    return fqns


def _annotation_args(workspace: Workspace) -> dict[str, list[dict[str, Any]]]:
    """Every annotation use, by BARE target — the spelling a handler symbol reduces to,
    so a method and its enclosing type are both looked up the same way."""
    found: dict[str, list[dict[str, Any]]] = {}
    for row in workspace.query("annotations"):
        args = row["args"]
        found.setdefault(bare_descriptor(str(row["target"])), []).append(
            {
                "annotation": bare_descriptor(str(row["annotation"])),
                "args": {} if args is None else json.loads(str(args)),
            }
        )
    return found


def _declares_a_custom_condition(workspace: Workspace, catalog: Catalog) -> bool:
    """Whether this module registers a mapping handler of its own, which could carry the
    one condition of Spring's seven that no class file states.

    A custom `RequestCondition` reaches a mapping through a `RequestMappingHandlerMapping`
    subclass overriding `getCustomMethodCondition`/`getCustomTypeCondition`. The condition
    itself is code, so two mappings separated only by one look identical here — and a
    conflict reported against them would be a fabrication about a service that starts
    perfectly well.

    So the whole module goes quiet rather than reporting something it cannot check. That
    is the direction NFR-2 asks for, and the cost is visible: `mapping.custom_condition`
    names the type in the catalog, so a reader can see exactly what silences this.
    """
    base = (catalog.matches.get("mapping") or {}).get("custom_condition")
    if base is None:
        return False
    wanted = type_descriptor(str(base))
    return any(
        wanted in json.loads(str(row["interfaces"] or "[]"))
        for row in workspace.query("implementations")
    ) or any(
        bare_descriptor(str(row["superclass"])) == wanted for row in workspace.query("superclasses")
    )
