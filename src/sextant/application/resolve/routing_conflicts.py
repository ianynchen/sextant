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

**Five and a half of the seven are readable here**, and the half is the point. The
endpoint row carries the path and both media columns; `params`/`headers` are attributes
of the mapping annotation, named by the catalog as `discriminators`, and class-level and
method-level values are UNIONED because that is what `ParamsRequestCondition.combine`
does — a `LinkedHashSet` of one side's expressions with the other's added.

The methods condition is the half. What a row carries is not the DECLARED set Spring
compares but `derive_endpoints.sql`'s expansion of it, so a verbless mapping arrives as
eight verb rows. `_verbs_of` groups them back into the set, which recovers the comparison
for every case but one: a mapping that names all eight verbs explicitly expands to the
same eight rows as one that names none, and Spring holds those to be different
conditions.

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
from sextant.application.resolve.engines.annotation_driven import effective_annotation_uses
from sextant.application.resolve.open_questions import record_open_questions
from sextant.domain.closed_sets import Direction
from sextant.domain.symbols import bare_descriptor, owner_of, type_descriptor

# The one value `mapping.duplicate` may take. Absence means "several handlers on one
# address is ordinary for this framework", which is the answer for every catalog that
# does not name it — Kafka, JMS, SQS, AMQP, STOMP, GraphQL and the rest.
_CONFLICT = "conflict"


def record_routing_conflicts(workspace: Workspace, catalogs: list[Catalog]) -> None:
    """Files one question per address two different handlers claim, where the catalog
    that derived them says the framework refuses that.

    **One question per conflict, not one per verb.** The registration is grouped by
    handler first and the verbs it registered under are collected into a set, because
    that set — not any single member of it — is what Spring's own condition compares.
    """
    declaring = [
        catalog
        for catalog in catalogs
        if str((catalog.matches.get("mapping") or {}).get("duplicate", "")) == _CONFLICT
        # Hoisted out of the reporting loop, where it ran once per group though its
        # answer is a property of the catalog and the workspace alone. A catalog
        # silenced here also skips the annotation walk below, which is the expensive
        # half.
        and not _declares_a_custom_condition(workspace, catalog)
    ]
    if not declaring:
        return
    annotations = {
        catalog.id: effective_annotation_uses(workspace, catalog) for catalog in declaring
    }
    by_id = {catalog.id: catalog for catalog in declaring}
    # One entry per REGISTRATION — one handler's claim on one address under one set of
    # conditions — carrying the verbs that registration was fanned out to.
    registered: dict[tuple[Any, ...], set[str | None]] = {}
    for row in workspace.query("endpoints"):
        catalog = by_id.get(str(row["catalog_id"]))
        if catalog is None or str(row["direction"]) != Direction.INBOUND:
            continue
        if row["path"] is None or row["handler"] is None:
            # An unresolved row names no address, and a row naming no handler names
            # nothing that could conflict with anything.
            continue
        handler = bare_descriptor(str(row["handler"]))
        mapping = catalog.matches.get("mapping") or {}
        registration = (
            str(row["protocol"]),
            str(row["path"]),
            None if row["consumes"] is None else str(row["consumes"]),
            None if row["produces"] is None else str(row["produces"]),
            _discriminators(mapping, annotations[catalog.id], handler),
            handler,
            catalog.id,
        )
        registered.setdefault(registration, set()).add(
            None if row["method"] is None else str(row["method"])
        )
    claimed: dict[tuple[Any, ...], list[str]] = {}
    for registration, fanned in registered.items():
        protocol, path, consumes, produces, discriminators, handler, _catalog_id = registration
        # Everything the framework compares that this workspace can see, with the VERB
        # SET in the place a single verb used to hold. See `_verbs_of` for why the set
        # is the only faithful form.
        identity = (protocol, _verbs_of(fanned), path, consumes, produces, discriminators)
        claimed.setdefault(identity, []).append(handler)
    rows: list[dict[str, object]] = []
    # Sorted so two runs file the ledger in one order (NFR-1).
    for identity in sorted(claimed, key=lambda key: tuple(str(part) for part in key)):
        handlers = sorted(set(claimed[identity]))
        if len(handlers) < 2:
            # One handler, however many rows it took to say so — a method carrying two
            # annotations of one address is one registration, not two.
            continue
        protocol, verb_tuple, path, _consumes, _produces, _discriminators_of = identity
        verbs: tuple[str, ...] = tuple(str(verb) for verb in verb_tuple)
        rows.append(
            {
                "protocol": protocol,
                # The verb where the registration named exactly one, and NULL where it
                # named none — a verbless `@RequestMapping` answers at every verb, and
                # naming one of them here would say the conflict is narrower than it is.
                "method": verbs[0] if len(verbs) == 1 else None,
                "path": path,
                "question": "routing_conflict",
                "candidates": json.dumps([{"handler": handler} for handler in handlers]),
                "evidence": (
                    "one address, two handlers, and every condition this workspace can "
                    f"read is equal: path, the verb set ({', '.join(verbs) or 'none'}), "
                    "consumes, produces and the catalog's own discriminators. A custom "
                    "RequestCondition is not readable from a class file and no subclass "
                    "registering one was found"
                ),
            }
        )
    record_open_questions(workspace, rows)


def _verbs_of(verbs: set[str | None]) -> tuple[str, ...]:
    """The verbs one registration answers at, as a sorted, hashable value.

    **A set, because that is what Spring compares.** `RequestMethodsRequestCondition.
    equals` compares the DECLARED method set, and an empty set is not equal to `{GET}` —
    so `@RequestMapping("/x")` and `@GetMapping("/x")` are two different mappings, both
    register, and a GET request resolves to the more specific one. W28 compared the
    single fanned-out verb of an endpoint row instead: `derive_endpoints.sql` expands a
    verbless mapping to all eight verbs, so the two collided on the GET row and the
    detector reported an `IllegalStateException` against a module that starts. Grouping
    the row's verbs back into the set the annotation declared is what restores the
    framework's own comparison — and it is also why one conflict now files one question
    rather than eight.

    **The stated boundary**: a mapping that lists all eight verbs EXPLICITLY is a
    different condition from one that lists none, and both fan out to the same eight
    rows, so the two are indistinguishable here. That is the residual of reading a
    condition through its expansion, and it needs a handler declaring every verb by name
    beside a verbless one on the same address to matter.
    """
    return tuple(sorted(verb for verb in verbs if verb is not None))


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

    `annotations` is the EFFECTIVE set (`effective_annotation_uses`), so a discriminator
    reaches this whether it was written on the use site, composed into a module-local
    meta-annotation, folded into a repeatable container, or declared on an interface
    method the class implements without repeating. Reading the raw `annotations` view
    here made all three read as absent while the endpoint row still derived.
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


def _declares_a_custom_condition(workspace: Workspace, catalog: Catalog) -> bool:
    """Whether this ANALYSIS holds a mapping handler of its own, which could carry the
    one condition of Spring's seven that no class file states.

    Not "this module": `implementations` and `superclasses` are filtered by
    `selected_documents`, which includes `OriginTier.DEPENDENCY` documents. So a scanned
    dependency subclassing `RequestMappingHandlerMapping` — Spring Data REST's
    `BasePathAwareHandlerMapping` is one — silences the detector for the whole run. That
    is the safe direction and it is deliberate, since such a dependency really can carry
    a custom condition into the same registry; it is stated here because the scope is
    wider than a reader would assume.

    A custom `RequestCondition` reaches a mapping through a `RequestMappingHandlerMapping`
    subclass overriding `getCustomMethodCondition`/`getCustomTypeCondition`. The condition
    itself is code, so two mappings separated only by one look identical here — and a
    conflict reported against them would be a fabrication about a service that starts
    perfectly well.

    So the whole analysis goes quiet rather than reporting something it cannot check. That
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
