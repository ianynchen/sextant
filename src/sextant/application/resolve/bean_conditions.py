"""A bean that exists in some environments only (spec 2026-10-22-conditional-beans §2, §2a,
ruled 2026-10-22) — the general rule spec 2026-10-21-conditional-controllers was one case
of: the conditions the container evaluates when it REGISTERS a bean, stated on the bean as
structured data and evaluated per environment the module resolves — never deciding whether
any row derived from the bean exists.

The framework knowledge is the bean model's (`bean-models/spring.yml`, D02 §1c): which
annotations make a class a bean (`stereotypes`, `configuration_annotation`), which declares
a factory method (`declaring_annotation`), and the conditions (`conditions`), each citing the
probe that read the rule off the jar. This pass writes `bean_conditions`: one row per (bean,
registration route, condition, environment). Every row of every kind — an endpoint in either
direction, a scheduled job, an error handler — finds its bean through its own code's owner
class (`symbols.enclosing`); `endpoint_conditions` is the view of that join for endpoints.

Which classes are beans, and which conditions apply — the container's own rule (CP-44,
`scripts/probes/cp44_bean_registration_conditions.md`, rows 1-5):

* `class` — a class carrying a stereotype is registered by scanning, and the scanner
  evaluates the class's own conditions (row 4, `isConditionMatch`; row 5, the stereotypes).
* `factory` — a factory method is registered with its own conditions evaluated (row 4,
  `loadBeanDefinitionsForBeanMethod`), and the bean is the class it constructs — the classes
  its body runs `new` on that are assignable to its declared return type (`type_hierarchy`).
  A helper the body builds and hands to the bean is not assignable and is no bean: a
  structural rule, never a model of what a body does with what it builds.
* `configuration` — the factory method's own configuration class's conditions too: a
  skipped configuration registers none of its factory methods (row 4, the reader returns
  before it reads them).
* A class merely constructed is never handed to the evaluator (row 4), so its own
  annotations are not consulted on that route.
* `proxy` — an INTERFACE the framework registers and implements at run time (the bean
  model's `interface_registrations`; CP-46, `scripts/probes/cp46_repository_interface_beans.md`:
  Spring Data's repository scanner is the component scanner, its own filters admitting an
  interface assignable to `Repository` or carrying `@RepositoryDefinition`, refusing one
  carrying `@NoRepositoryBean`, and evaluating the interface's own conditions). The bean is
  the interface; every interface bean, conditional or not, is written to `interface_beans`
  with each type it is assignable to, which is how `candidate_presence` lists the
  framework's implementation as a candidate of a call naming one of them.
* A lambda body a factory method's own body creates (the `dynamic` call edge from it to a
  synthetic body, followed through lambdas it creates in turn) is that factory's code: its
  bean is the lambda body itself, on the factory's route, `via` the method — a functional
  route or a configurer the factory returns runs only where the factory registers.
  **Stated limits:** only a lambda the factory's OWN body creates is followed, not one created
  in a helper the body calls; and a lambda a compiler emits as a CLASS (named by the
  `lambda_bodies` read of `effective_calls`) is reached by a `new`, not by a `dynamic` call
  edge, so it is not on the factory's route here.

**A stereotype or a condition may arrive through a COMPOSED annotation** (CP-44 row 5: the
scanner matches meta-annotations). An annotation counts when it is one of the model's, or is
meta-annotated by one, transitively — through module-local annotation types and through
dependency annotation types whose class-level annotations the `type_header` read recorded
(D00 §5) — by the composition fold `effective_annotations.composed_mapping_rows` every
annotation-driven engine already uses; a composed condition's declared arguments are folded
under the use site's. **Stated limits:** an annotation type whose header was not read (no
classpath, or a type in no archive on it) composes nothing; a module class whose supertypes
`type_hierarchy` cannot reach (an ancestor in no archive) is assignable to nothing above
that point, so a factory declared to return such a supertype gets no route for it.

A class registered more than one way EXISTS wherever ANY of its routes registers it (ruled
2026-10-22: each scan, import or factory registers its own bean definition, and the code
runs wherever one exists). So every route of a class with at least one conditional route is
written: a conditional route as its evaluated conditions (AND within the route), an
unconditional bean route (a stereotype class or a factory method with no condition) as one
condition-less row per environment holding `true`, and a plain `new` outside any factory
body as one condition-less `constructed` row per environment, `unresolved` — which bean's
code path runs it is not known. The `bean_presence` view folds them per environment (OR
across routes); the per-condition rows stay what the documents spell.

What it evaluates, and what it refuses (spec 2026-10-21 §3b, §4; the profile rule changed by
spec 2026-10-22 §2d, below):

* `profile` — a bare name holds where that profile is ACTIVE, `!name` where it is not; any
  expression carrying `&`, `|` or a parenthesis (CP-42 row 3) is `unresolved` in every
  environment — stated, never evaluated. The active profiles are read from configuration as
  the container reads them (CP-45; Task 7b, ruled 2026-10-22), by `active_profiles`: in the
  base environment, the profiles its `active_keys` and `include_keys` list, else its
  `default_keys`', else the `default_profile`; in a profile file's environment `p`, `p` and
  the base's included ones — a profile named ONLY in the base's active list is `unresolved`
  there, since the activation selecting `p` replaces or extends that list and which it does
  is the deployment's; where either key holds a placeholder nothing fills, every profile not
  decided so is `unresolved`; a profile group (row 8) makes its members active wherever its
  name is, as certain as the name. A name active nowhere fails.
* `property` — the key's resolved value in that environment against `having_value`
  (case-insensitive; EMPTY means "not `false`", CP-43 row 2); an absent key is decided by
  `match_if_missing` (CP-43 row 3); a key whose value is a placeholder nobody filled is
  `unresolved` there.
* `presence` — the model's `presence` block, `@ConditionalOnMissingBean` / `@ConditionalOnBean`
  (spec §2c, decision 2 as ruled; CP-44 rows 1-3, 6): judged AFTER the others, from the
  module's own bean definitions — a competitor exists where its own conditions all hold —
  and published at `partial` with the reason `ON_MODULE_BEANS`, since the container's search
  sees what is registered so far and a library may register more (`_presence_verdicts`).
* `other` — any annotation in the model's `conditions` block this pass has no rule for is
  written verbatim with `holds = unresolved`; nothing outside that block is read.

**The `profile` and `property` readings above are the repository's, and since spec
2026-10-23-deployment-set-conditions (ruling 1) they are EVIDENCE, not the verdict**, for
every kind the bean model marks `set_by: deployment` (CP-47: an environment variable or a
command-line argument outranks every file the module ships). What is written is `_judged`'s:
such a condition is `unresolved` unless the environment's own definition decides it — in
profile environment `p`, a profile term naming `p` holds and `!p` fails — and nothing
decides one in the base environment. The presence phase judges competitors by the same
verdicts.

Cost per resolve (GUIDELINES §8.7): the shared `annotation_index` (one decode per load), the
factory-method fold `beans.declared_beans` already keeps (one `method_declarations` read per
load, shared with `bean_via`), one `constructor_edges` read, one `type_hierarchy` read, one
`interface_symbols` read (annotation types and plain interfaces, the composing types) and one
`interface_declarations` read (the plain interfaces: told apart from the annotation types for
composition, and the candidates of an interface registration), one `type_header_annotations`
read (the composing dependency types), one `method_declarations` read for the compiler's
`synthetic` mark and one `lambda_edges` read (the lambdas a factory creates), one
`resolved_config` read (each environment's active profiles computed from it once, in
memory, a placeholder's spelling taken from the shared per-load `config_entries` rows), one
`dispatched_bodies` read with one `Dispatch` built from the
cached fact reads for the inherited bodies (`_inherited_rows`; 10 ms + 46 ms on apollo-portal,
1,945 bodies), and one insert — once per distinct bean model, none per catalog, per
bean or per row. The presence phase reads nothing more: its competitors are the definitions
`_routes` already found, matched in memory (one scan of them per presence condition), and its
verdicts settle in rounds over (condition, environment) pairs.
"""

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.beans import declared_beans
from sextant.application.resolve.conditions import annotation_index, enclosing_type_of
from sextant.application.resolve.dispatch import Dispatch, dispatch_of
from sextant.application.resolve.effective_annotations import composed_mapping_rows
from sextant.domain.redaction import Redactor
from sextant.domain.symbols import (
    bare_descriptor,
    is_type_descriptor,
    method_name,
    short_class_name,
    type_descriptor,
)

PROFILE = "profile"
PROPERTY = "property"
OTHER = "other"
PRESENCE = "presence"
HOLDS = "true"
FAILS = "false"
UNRESOLVED = "unresolved"
# Every bean-presence verdict's resolution and reason (spec §2c, decision 2 as ruled): the
# search sees the definitions registered so far (CP-44 row 3), and this pass sees only the
# module's own — a library, or the order the container reads the module in, may differ.
PARTIAL = "partial"
ON_MODULE_BEANS = (
    "decided from this module's beans only; a library or the processing order may differ"
)
# An open verdict says it is open, and why, before the competitor list names who left it so.
_NOT_DECIDED = "not decided from this module's beans"
_COMPETITOR_OPEN = "a competing bean's own existence here is open"
# The separator between a presence verdict's reason and its competitor list (JSON), so a
# machine splits the evidence once and the documents word the list.
COMPETITORS = "; competitors: "
# CP-44 row 1: with no type, name or annotation the type is deduced from a factory method's
# return type, and anywhere else `validate` refuses the use.
_NO_CRITERION = (
    "names no type, name or annotation, which the container refuses outside a factory method"
)
_TYPE_VARIABLE = "the factory method returns a type variable, so the type checked is not known"
# The characters that make a profile string an EXPRESSION rather than a name (CP-42 row 3):
# a composition over several active profiles, which this analysis does not evaluate.
_COMPOSITION = set("&|()")
# `bean_kind`: where a condition on the bean was written (spec §2) — or, on a condition-less
# row, the route itself.
CLASS = "class"
FACTORY = "factory"
CONFIGURATION = "configuration"
# The route of a class constructed outside any factory method's body.
CONSTRUCTED = "constructed"
# The route of an INTERFACE the framework registers and implements at run time (CP-46): the
# bean is the interface, its implementation a proxy the framework generates.
PROXY = "proxy"
# An inherited body no bean of the module resolves its method to (ruled 2026-10-22): it runs
# as part of no bean here, so where it exists is not decided.
INHERITED = "inherited"
NO_HEIR = "no bean of this module runs this inherited body"
# The JVM's own name for a constructor, which a member descriptor carries verbatim.
_CONSTRUCTOR = "<init>"
# A property condition's evidence quotes the value the module's own configuration sets
# (spec 2026-10-23-deployment-set-conditions §3b), and `bean_conditions` is exported whole,
# its evidence only through `redact_text`, which cannot see the key: so the value is masked
# HERE, by its own key, as every origin writer of a configured value masks it — the
# built-ins alone, because no redactor reaches a resolve pass from the composition root
# (`OI-71`, stated on `engines/fluent.py`).
_REDACTOR = Redactor.from_rules()


@dataclass(frozen=True)
class ConditionModel:
    """One `conditions` entry as a bean model declares it: the annotation (as the fact
    stream spells it, `org/springframework/context/annotation/Profile#`) and which members
    fill the structured expression."""

    kind: str
    annotation: str
    members: dict[str, Any]


@dataclass(frozen=True)
class ActiveProfiles:
    """The profiles active in one environment, as the container computes them (CP-45):
    `known` are active there; `unknown` are profiles whose activation there is the
    deployment's, each with why; `otherwise`, where a placeholder nothing fills supplies the
    list, is why every other profile is unknown there too."""

    known: frozenset[str]
    unknown: Mapping[str, str] = field(default_factory=dict)
    otherwise: str | None = None


@dataclass(frozen=True)
class _Route:
    """One way a class comes to exist at run time: scanned (`class`), returned by a factory
    method (`factory`, `via` the method), or constructed outside any factory body (`via` the
    method whose body runs the `new`). `conditions` are the (bean_kind, model, args) the
    container evaluates on that route — empty for an unconditional one."""

    route: str
    via: str | None
    conditions: tuple[tuple[str, ConditionModel, dict[str, Any]], ...]


@dataclass(frozen=True)
class _Registration:
    """One bean DEFINITION the container registers — a scanned class (`class`) or a factory
    method (`factory`), never a class merely constructed — as a bean-presence search sees it
    (CP-44 rows 2, 3, 6): the type it is matched by (the class, or the method's declared
    return type), its bean name (None where it is not known), the annotations of that type,
    and every condition the container evaluates on it as (holder, model, args), the holder
    being the class or method the annotation is on. `owner` is a factory's own class: a
    condition on that class is judged before the class's factory methods are read. `beans`
    are the module classes it registers — the class itself, or the classes a factory
    constructs and returns: two definitions sharing one never compete (ruled at review)."""

    route: str
    symbol: str
    owner: str | None
    registered: str | None
    name: str | None
    annotations: frozenset[str]
    conditions: tuple[tuple[str, ConditionModel, dict[str, Any]], ...]
    beans: frozenset[str] = frozenset()


@dataclass(frozen=True)
class _Presence:
    """One bean-presence condition, judged once per environment for every route it is on:
    the structured expression its rows carry and its verdict per environment."""

    expression: dict[str, Any]
    verdicts: dict[str, tuple[str, str, str]]


def record_bean_conditions(workspace: Workspace, catalogs: list[Catalog]) -> None:
    vocabularies = _bean_models(catalogs)
    if not vocabularies:
        return
    index = annotation_index(workspace)
    config = _config_by_environment(workspace)
    environments = sorted(config) or ["default"]
    active = _active_by_environment(workspace, catalogs, config, environments)
    default_environment = str(_profiles_model(catalogs).get("default_profile", "default"))
    reading = deployment_reading(
        active.get(default_environment, ActiveProfiles(known=frozenset())), default_environment
    )
    constructed = _constructed_by(workspace)
    created = _lambdas_created_by(workspace)
    ancestors = _ancestors(workspace)
    reached = _reached_bodies(workspace)
    dispatch = workspace.once(dispatch_of) if reached else None
    rows: list[dict[str, Any]] = []
    proxies: list[dict[str, str]] = []
    for model in vocabularies:
        every, registrations = _routes(workspace, model, index, constructed, created, ancestors)
        # Every interface bean, conditional or not, and each type it is assignable to: what a
        # call site names decides whether the framework's implementation answers it.
        proxies.extend(
            {"bean": bean, "type": supertype}
            for bean, found in sorted(every.items())
            if any(route.route == PROXY for route in found)
            for supertype in sorted(_supertypes_of(bare_descriptor(bean), ancestors))
        )
        routes = {
            bean: found for bean, found in every.items() if any(route.conditions for route in found)
        }
        presence = _presence_verdicts(
            registrations, ancestors, config, environments, active, default_environment, reading
        )
        written: dict[str, list[dict[str, Any]]] = {}
        for bean in sorted(routes):
            written[bean] = _rows_for(
                bean,
                routes[bean],
                config,
                environments,
                presence,
                active,
                default_environment,
                reading,
            )
            rows.extend(written[bean])
        if dispatch is not None:
            rows.extend(_inherited_rows(reached, dispatch, every, written, environments))
    if rows:
        workspace.derive("bean_conditions_insert", rows=rows)
    if proxies:
        workspace.derive("interface_beans_insert", rows=proxies)


def _reached_bodies(workspace: Workspace) -> dict[str, tuple[str, str, str]]:
    """Every body a virtual or interface call site dispatches to, with the method it names
    (`name`, `descriptor`, as the site wrote them) and the type that declares the body
    (`symbols.enclosing`) — one entry per body, the first in the query's order."""
    reached: dict[str, tuple[str, str, str]] = {}
    for row in workspace.query("dispatched_bodies"):
        reached.setdefault(
            str(row["body"]), (str(row["name"]), str(row["descriptor"]), str(row["enclosing"]))
        )
    return reached


def _inherited_rows(
    reached: dict[str, tuple[str, str, str]],
    dispatch: Dispatch,
    routes: dict[str, list[_Route]],
    written: dict[str, list[dict[str, Any]]],
    environments: list[str],
) -> list[dict[str, Any]]:
    """An INHERITED body — declared on a type the module registers as no bean (an abstract
    class, an interface's default method) above at least one bean — has no bean of its own:
    it runs as part of every bean whose class RESOLVES the method to it (ruled 2026-10-22),
    by the module's own JVMS 5.4.3.3 walk (`Dispatch.resolve`, the one `method_resolution`
    and every call edge use). So it exists wherever any of those beans does — OR across
    them, each bean's own routes copied under the body (`via` the bean's own route, or the
    bean class for a scanned one, so two heirs stay two routes in `bean_presence`). An
    unconditional heir makes it exist everywhere, which is no row at all, as for any
    unconditional bean; no heir at all leaves it `unresolved`, `NO_HEIR`.

    **Stated limits:** only a body some virtual or interface call site reaches is considered
    (a `super` call runs an overridden body as part of the overriding bean, which resolution
    does not see); an abstract type with no bean below it is no inherited body here."""
    beans = {
        bare_descriptor(bean): bean
        for bean, found in routes.items()
        if is_type_descriptor(bean)
        and any(route.route in (CLASS, FACTORY, PROXY) for route in found)
    }
    rows: list[dict[str, Any]] = []
    for body, (name, descriptor, enclosing) in sorted(reached.items()):
        declaring = bare_descriptor(enclosing)
        if declaring in beans or body in routes:
            continue
        below = [beans[sub] for sub in dispatch.subtypes.get(declaring, ()) if sub in beans]
        if not below:
            continue
        heirs = [
            bean
            for bean in below
            if dispatch.resolve(bare_descriptor(bean), name, descriptor)[0] == declaring
        ]
        if not heirs:
            rows.extend(
                {
                    "bean": body,
                    "bean_kind": INHERITED,
                    "via": None,
                    "kind": None,
                    "expression": None,
                    "environment": environment,
                    "holds": UNRESOLVED,
                    "resolution": UNRESOLVED,
                    "evidence": NO_HEIR,
                }
                for environment in environments
            )
        elif all(heir in written for heir in heirs):
            rows.extend(
                {**row, "bean": body, "via": row["via"] or heir}
                for heir in heirs
                for row in written[heir]
            )
    return rows


def _bean_models(catalogs: list[Catalog]) -> list[dict[str, Any]]:
    """The distinct bean models the catalogs name that carry a `conditions` block, once each
    however many catalogs name one — keyed by the model's own `id`, which is its file's."""
    models: dict[str, dict[str, Any]] = {}
    for catalog in catalogs:
        model = catalog.bean_model
        if model.get("conditions"):
            models.setdefault(str(model.get("id")), model)
    return [models[identity] for identity in sorted(models)]


def _models(model: dict[str, Any]) -> dict[str, ConditionModel]:
    """Every `conditions` entry of one bean model, keyed by the annotation's bare symbol.
    The loader has already refused a malformed block, naming the model's file and requiring
    a `by:` probe, because a rule nobody measured is a guess
    (`yaml_source._check_bean_model`)."""
    models: dict[str, ConditionModel] = {}
    for kind, entry in model["conditions"].items():
        if kind == OTHER:
            # The conditions this analysis NAMES and does not evaluate (spec §4): each is
            # code, not configuration — a `Condition` class, a bean's presence, a SpEL
            # expression — and a verdict would be a guess. One model per annotation, so
            # a row is written verbatim with `holds = unresolved` in every environment,
            # rather than the bean reading as unconditional.
            names = entry["annotations"]
            for name in names:
                symbol = type_descriptor(str(name))
                models[symbol] = ConditionModel(kind=OTHER, annotation=symbol, members={})
            continue
        symbol = type_descriptor(entry["annotation"])
        models[symbol] = ConditionModel(kind=kind, annotation=symbol, members=dict(entry))
    # The bean-presence conditions (spec §2c), each judged from the module's own beans by
    # `_presence_verdicts` — `mode` says which of the two (CP-44 row 2: `isAnyMatched` for
    # `missing`, `isAllMatched` for `present`).
    presence = model.get("presence") or {}
    for mode in ("missing", "present"):
        if presence.get(mode):
            symbol = type_descriptor(str(presence[mode]))
            models[symbol] = ConditionModel(
                kind=PRESENCE, annotation=symbol, members={**presence, "mode": mode}
            )
    return models


def _routes(
    workspace: Workspace,
    model: dict[str, Any],
    index: dict[str, list[tuple[str, dict[str, Any]]]],
    constructed: dict[str, list[str]],
    created: dict[str, list[str]],
    ancestors: dict[str, list[str]],
) -> tuple[dict[str, list[_Route]], list[_Registration]]:
    """Every class with a route, mapped to all of its routes — conditional or not, since an
    unconditional second route decides where it exists (the caller keeps those with at least
    one CONDITIONAL route, and reads the rest for which classes are beans at all) — and every
    bean definition of the module, conditional or not, for the bean-presence search."""
    conditions = _models(model)
    naming = {
        type_descriptor(str(name)): str(attr)
        for name, attr in (model.get("stereotype_name_attrs") or {}).items()
    }
    stereotypes = {type_descriptor(str(name)) for name in model.get("stereotypes", ())}
    if model.get("configuration_annotation"):
        stereotypes.add(type_descriptor(str(model["configuration_annotation"])))
    annotation_types = {str(row["symbol"]) for row in workspace.query("interface_symbols")}
    # That set holds plain interfaces beside annotation types (`interface_symbols`). Only an
    # annotation type composes; an interface carrying a composed annotation is its USER — the
    # one an interface registration (CP-46) reads.
    interfaces = [str(row["symbol"]) for row in workspace.query("interface_declarations")]
    raw = index
    interface_registrations = list(model.get("interface_registrations") or ())
    # The annotations an interface registration reads, so a composed one counts as for classes.
    registration_marks = {
        type_descriptor(str(entry[key]))
        for entry in interface_registrations
        for key in ("annotation", "excluded_by")
        if entry.get(key)
    }
    index = _effective_index(
        workspace,
        index,
        annotation_types - set(interfaces),
        {*stereotypes, *conditions, *registration_marks},
    )

    def conditions_on(target: str | None, bean_kind: str) -> list[tuple[str, ConditionModel, Any]]:
        return [
            (bean_kind, conditions[bare_descriptor(descriptor)], args)
            for descriptor, args in index.get(target or "", ())
            if bare_descriptor(descriptor) in conditions
        ]

    # The annotations each type carries, bare — what an `annotation` criterion asks of the
    # type a bean is matched by.
    annotated = {
        bare_descriptor(target): frozenset(bare_descriptor(descriptor) for descriptor, _ in uses)
        for target, uses in index.items()
        if is_type_descriptor(target)
    }
    routes: dict[str, list[_Route]] = {}
    registrations: list[_Registration] = []
    for target, uses in index.items():
        # An annotation or interface TYPE carrying a stereotype is a composed stereotype or a
        # type nothing instantiates — never a scanned bean itself.
        if target in annotation_types:
            continue
        if is_type_descriptor(target) and any(
            bare_descriptor(descriptor) in stereotypes for descriptor, _ in uses
        ):
            on_class = tuple(conditions_on(target, CLASS))
            routes.setdefault(target, []).append(_Route(CLASS, None, on_class))
            registrations.append(
                _Registration(
                    route=CLASS,
                    symbol=target,
                    owner=None,
                    registered=bare_descriptor(target),
                    name=_scanned_name(target, raw.get(target, ()), naming, conditions),
                    annotations=annotated.get(bare_descriptor(target), frozenset()),
                    conditions=tuple((target, found, args) for _, found, args in on_class),
                )
            )
    # An INTERFACE the framework registers and implements at run time (CP-46) is a route like
    # a scanned class's: the scanner evaluates the interface's own conditions (row 6).
    for interface in _registered_interfaces(
        interfaces, interface_registrations, annotated, ancestors
    ):
        on_interface = tuple(conditions_on(interface, PROXY))
        routes.setdefault(interface, []).append(_Route(PROXY, None, on_interface))
        registrations.append(
            _Registration(
                route=PROXY,
                symbol=interface,
                owner=None,
                registered=bare_descriptor(interface),
                # The name the framework gives its implementation was not measured.
                name=None,
                annotations=annotated.get(bare_descriptor(interface), frozenset()),
                conditions=tuple((interface, found, args) for _, found, args in on_interface),
            )
        )
    factories = declared_beans(workspace, model).by_method
    for declared in sorted(factories):
        bean = factories[declared]
        owner = enclosing_type_of(declared)
        registrations.append(
            _Registration(
                route=FACTORY,
                symbol=declared,
                owner=owner,
                registered=bean.erased_return,
                name=bean.name,
                annotations=annotated.get(bean.erased_return or "", frozenset()),
                conditions=(
                    *(
                        (declared, found, args)
                        for _, found, args in conditions_on(declared, FACTORY)
                    ),
                    *(
                        (owner or "", found, args)
                        for _, found, args in conditions_on(owner, CONFIGURATION)
                    ),
                ),
            )
        )
    # A lambda body a factory creates is that factory's code (ruled 2026-10-22), so a `new`
    # in it is the factory's construction too — the creating factory answers for it.
    creator: dict[str, str] = {}
    for creating in sorted(factories):
        for body in _created_from(creating, created):
            creator.setdefault(body, creating)

    def route_conditions_of(method: str) -> tuple[tuple[str, ConditionModel, Any], ...]:
        return (
            *conditions_on(method, FACTORY),
            *conditions_on(enclosing_type_of(method), CONFIGURATION),
        )

    for caller, classes in constructed.items():
        method = caller if caller in factories else creator.get(caller)
        factory = None if method is None else factories[method]
        for built in classes:
            if (
                method is not None
                and factory is not None
                and factory.erased_return is not None
                and _assignable(bare_descriptor(built), factory.erased_return, ancestors)
            ):
                routes.setdefault(built, []).append(
                    _Route(FACTORY, method, route_conditions_of(method))
                )
            elif method is None and not _delegates(caller, built, ancestors):
                # A `new` outside every factory body (the ruling's "plain `new`"). One inside
                # a factory body — or a lambda it creates — that does not return it is a
                # helper of that bean, no route.
                routes.setdefault(built, []).append(_Route(CONSTRUCTED, caller, ()))
    for body, creating in creator.items():
        routes.setdefault(body, []).append(_Route(FACTORY, creating, route_conditions_of(creating)))
    # Which classes each definition registers, read off the routes just built.
    registers: dict[str, set[str]] = {}
    for registered_class, found in routes.items():
        for route in found:
            if route.route in (CLASS, PROXY):
                registers.setdefault(registered_class, set()).add(registered_class)
            elif route.route == FACTORY and route.via is not None:
                registers.setdefault(route.via, set()).add(registered_class)
    registrations = [
        replace(registration, beans=frozenset(registers.get(registration.symbol, ())))
        for registration in registrations
    ]
    # A factory method's OWN body is that factory's code (ruled 2026-10-22), as the lambdas it
    # creates are: a row whose code symbol is the method itself — an inline adapter flow it
    # builds and returns — exists only where the factory registers. So each conditional
    # factory is written as a bean of its own, `via` itself, found by `symbol_beans`' own-symbol
    # rule. Added after `registers` so the method is no competitor of anything.
    for declared in sorted(factories):
        own = route_conditions_of(declared)
        if own:
            routes.setdefault(declared, []).append(_Route(FACTORY, declared, own))
    return routes, registrations


def _scanned_name(
    target: str,
    uses: Iterable[tuple[str, dict[str, Any]]],
    naming: dict[str, str],
    conditions: dict[str, ConditionModel],
) -> str | None:
    """A scanned class's bean name (CP-44 row 6): the text its stereotype's naming attribute
    gives, else its short name (`short_class_name`) uncapitalised unless its first two
    characters are both upper case. A class that is a bean only through a COMPOSED stereotype
    and carries an argument on any annotation may be named by it (an `@AliasFor` this analysis
    does not read): None, the name not known."""
    direct = False
    composing = []
    for descriptor, args in uses:
        attribute = naming.get(bare_descriptor(descriptor))
        if attribute is None:
            if bare_descriptor(descriptor) not in conditions:
                composing.append(args)
            continue
        direct = True
        value = args.get(attribute)
        if isinstance(value, list):
            value = value[0] if value else None
        if isinstance(value, str) and value.strip():
            return value
    if not direct and any(composing):
        return None
    short = short_class_name(target)
    if len(short) > 1 and short[0].isupper() and short[1].isupper():
        return short
    return short[:1].lower() + short[1:]


def _rows_for(
    bean: str,
    routes: list[_Route],
    config: dict[str, dict[str, str | None]],
    environments: list[str],
    presence: dict[tuple[str, str, str], _Presence],
    active: dict[str, ActiveProfiles],
    default_environment: str,
    reading: str,
) -> list[dict[str, Any]]:
    """One row per (route, condition, environment), evaluated; one condition-less row per
    (route, environment) for a route with no condition — `true` for a bean route,
    `unresolved` for a plain `new`. A bean-presence condition's rows carry the verdict its
    holder's condition was judged to (`_presence_verdicts`). `bean_presence` folds them."""
    distinct = sorted(
        {(route.route, route.via or ""): route for route in routes}.values(),
        key=lambda route: (route.route, route.via or ""),
    )
    rows: list[dict[str, Any]] = []
    for route in distinct:
        if not route.conditions:
            for environment in environments:
                constructed = route.route == CONSTRUCTED
                rows.append(
                    {
                        "bean": bean,
                        "bean_kind": route.route,
                        "via": route.via,
                        "kind": None,
                        "expression": None,
                        "environment": environment,
                        "holds": UNRESOLVED if constructed else HOLDS,
                        "resolution": UNRESOLVED if constructed else "resolved",
                        "evidence": (
                            f"also constructed outside any factory, in {route.via}"
                            if constructed
                            else "compiler"
                        ),
                    }
                )
            continue
        for bean_kind, model, args in route.conditions:
            if model.kind == PRESENCE:
                # The class or method the annotation is on, which `_presence_verdicts` keys by.
                holder = (
                    bean
                    if bean_kind in (CLASS, PROXY)
                    else route.via
                    if bean_kind == FACTORY
                    else enclosing_type_of(route.via or "")
                )
                judged = presence[_presence_key(holder or "", model, args)]
                for environment in environments:
                    holds, resolution, evidence = judged.verdicts[environment]
                    rows.append(
                        {
                            "bean": bean,
                            "bean_kind": bean_kind,
                            "via": route.via,
                            "kind": PRESENCE,
                            "expression": json.dumps(judged.expression, sort_keys=True),
                            "environment": environment,
                            "holds": holds,
                            "resolution": resolution,
                            "evidence": evidence,
                        }
                    )
                continue
            kind, expression = _expression(model, args)
            for environment in environments:
                # An open verdict's evidence says why it is open (Task 7b; spec 2026-10-23).
                holds, resolution, evidence = _judged(
                    model,
                    kind,
                    expression,
                    environment,
                    config.get(environment, {}),
                    active[environment],
                    default_environment,
                    reading,
                )
                rows.append(
                    {
                        "bean": bean,
                        "bean_kind": bean_kind,
                        "via": route.via,
                        "kind": kind,
                        "expression": json.dumps(expression, sort_keys=True),
                        "environment": environment,
                        "holds": holds,
                        "resolution": resolution,
                        "evidence": evidence,
                    }
                )
    return rows


def _presence_key(holder: str, model: ConditionModel, args: dict[str, Any]) -> tuple[str, str, str]:
    return holder, model.annotation, json.dumps(args, sort_keys=True)


def _listed(members: dict[str, Any], attrs: str, args: dict[str, Any]) -> list[str]:
    """Every value the use gives under any attribute `members[attrs]` names, once, sorted."""
    return sorted(
        {value for attr in members.get(attrs, ()) for value in _strings(args.get(str(attr)))}
    )


# A criterion's state against the competitors that match it: one exists there (`_MET`), none
# does or could (`_UNMET`), or which is not known (`UNRESOLVED`); None while a competitor's
# own verdict is still being decided.
_MET = "met"
_UNMET = "unmet"


def _presence_verdicts(
    registrations: list[_Registration],
    ancestors: dict[str, list[str]],
    config: dict[str, dict[str, str | None]],
    environments: list[str],
    active: dict[str, ActiveProfiles],
    default_environment: str,
    reading: str,
) -> dict[tuple[str, str, str], _Presence]:
    """Every bean-presence condition the module's bean definitions carry, judged per
    environment from those definitions alone (spec §2c, decision 2; CP-44 rows 1-3).

    A condition's CRITERIA are each type of `type_attrs` (one set, row 2), each name of
    `name_attrs` and each annotation of `annotation_attrs` — or, with none of them on a
    factory method, the method's declared return type (row 1). Its COMPETITORS are the
    module's other bean definitions that register a DIFFERENT class (ruled at review: the
    condition asks whether ANOTHER bean of the type exists; OR across one class's own routes
    is `bean_presence`'s): one matches a type when the type it is matched by is that type or
    a subtype (`type_hierarchy`), a name when its bean name is that name, an annotation when
    its type carries it. A condition on a class is judged before that class's own factory
    methods are read (row 4), so they are no competitor of it. A competitor EXISTS in an
    environment where every condition on it holds — its own presence conditions too — so the
    verdicts are decided together, in memory, in rounds until nothing changes:

    * `missing` (`isAnyMatched`) fails where some criterion has a competitor that exists,
      holds where no criterion has one that exists or could, and is `unresolved` otherwise;
    * `present` (`isAllMatched`) holds where every criterion has a competitor that exists,
      fails where some criterion has none that exists or could, `unresolved` otherwise.

    Conditions still undecided when nothing changes wait on each other through their
    competitors. Each closed loop of them (one waiting on nothing outside itself) is settled
    by its shape: a loop of `present` conditions alone FAILS — the first the container reads
    finds the others not yet registered (row 3), so no order lets one in — and is decided
    with the model's `present_cycle_reason`; a loop holding a `missing` one keeps whichever
    is read first, so it is `unresolved` with `order_reason`. Then the rounds resume.

    Every decided verdict is `partial`, with the stated reason; every verdict's evidence ends
    with `COMPETITORS` and a sorted JSON list of the competitors that decided it or left it
    open, each `{bean, via, holds}` and a `note` where its conditions name a profile no
    environment of the module is. Cost: one pass over the definitions per condition to find
    its competitors, then rounds over (condition, environment) pairs — no table read."""
    by_symbol = {registration.symbol: registration for registration in registrations}
    closure: dict[str, frozenset[str]] = {}

    def supertypes(bare: str) -> frozenset[str]:
        if bare not in closure:
            seen: set[str] = set()
            pending = [bare]
            while pending:
                current = pending.pop()
                if current not in seen:
                    seen.add(current)
                    pending.extend(ancestors.get(current, ()))
            closure[bare] = frozenset(seen)
        return closure[bare]

    # Each (definition, environment)'s verdict on the conditions this phase does not judge,
    # and the profiles its conditions name that no environment of the module is.
    base: dict[str, dict[str, str]] = {}
    unseen: dict[str, list[str]] = {}
    for registration in registrations:
        unjudged: dict[str, str] = {}
        others = [
            (found, *_expression(found, args))
            for _, found, args in registration.conditions
            if found.kind != PRESENCE
        ]
        for environment in environments:
            states = [
                _judged(
                    found,
                    kind,
                    expression,
                    environment,
                    config.get(environment, {}),
                    active[environment],
                    default_environment,
                    reading,
                )[0]
                for found, kind, expression in others
            ]
            unjudged[environment] = (
                FAILS
                if FAILS in states
                else HOLDS
                if all(state == HOLDS for state in states)
                else UNRESOLVED
            )
        base[registration.symbol] = unjudged
        unseen[registration.symbol] = sorted(
            {
                name
                for _, kind, expression in others
                if kind == PROFILE
                for raw in expression["expressions"]
                if not any(char in _COMPOSITION for char in str(raw))
                and (name := str(raw).strip().lstrip("!").strip())
                and name not in environments
                # A profile active, or possibly active, somewhere is no missing environment.
                and not any(
                    name in found.known or name in found.unknown or found.otherwise
                    for found in active.values()
                )
            }
        )

    expressions: dict[tuple[str, str, str], dict[str, Any]] = {}
    modes: dict[tuple[str, str, str], str] = {}
    criteria: dict[tuple[str, str, str], list[list[tuple[str, bool]]]] = {}
    reasons: dict[tuple[str, str, str], str] = {}
    # The model's wording for a closed loop, per shape (see above; CP-44 row 3).
    loop_reasons: dict[tuple[str, str, str], tuple[str, str]] = {}
    held: dict[str, list[tuple[str, str, str]]] = {}
    for registration in registrations:
        for holder, found, args in registration.conditions:
            if found.kind != PRESENCE:
                continue
            key = _presence_key(holder, found, args)
            held.setdefault(registration.symbol, []).append(key)
            if key in expressions:
                continue
            members = found.members
            types = [bare_descriptor(v) for v in _listed(members, "type_attrs", args)]
            names = _listed(members, "name_attrs", args)
            annotations = [bare_descriptor(v) for v in _listed(members, "annotation_attrs", args)]
            if not (types or names or annotations):
                factory = by_symbol.get(holder)
                if factory is None or factory.route != FACTORY:
                    reasons[key] = _NO_CRITERION
                elif factory.registered is None:
                    reasons[key] = _TYPE_VARIABLE
                else:
                    types = [factory.registered]
            modes[key] = str(members["mode"])
            expressions[key] = {
                "annotation": found.annotation,
                "mode": modes[key],
                "types": types,
                "names": names,
                "annotations": annotations,
            }
            loop_reasons[key] = (
                str(members["order_reason"]),
                str(members["present_cycle_reason"]),
            )
            # The definitions the condition is on — the holder itself, or a class and its
            # own factory methods — and the classes they register.
            own = [other for other in registrations if holder in (other.symbol, other.owner)]
            same = frozenset().union(*(other.beans for other in own))
            competitors = [
                other
                for other in registrations
                if holder not in (other.symbol, other.owner) and not (other.beans & same)
            ]
            criteria[key] = [
                *(
                    [
                        (other.symbol, True)
                        for other in competitors
                        if other.registered is not None and wanted in supertypes(other.registered)
                    ]
                    for wanted in types
                ),
                *(
                    [
                        (other.symbol, other.name is not None)
                        for other in competitors
                        if other.name is None or other.name == wanted
                    ]
                    for wanted in names
                ),
                *(
                    [(other.symbol, True) for other in competitors if wanted in other.annotations]
                    for wanted in annotations
                ),
            ]

    verdict: dict[tuple[str, str, str], dict[str, str | None]] = {
        key: {environment: UNRESOLVED if key in reasons else None for environment in environments}
        for key in expressions
    }
    # (condition, environment) pairs a closed loop settled, and which wording it took.
    looped: dict[tuple[tuple[str, str, str], str], str] = {}

    def exists(symbol: str, environment: str) -> str | None:
        states: list[str | None] = [base[symbol][environment]]
        states.extend(verdict[key][environment] for key in held.get(symbol, ()))
        if FAILS in states:
            return FAILS
        if None in states:
            return None
        return HOLDS if all(state == HOLDS for state in states) else UNRESOLVED

    def judge(key: tuple[str, str, str], environment: str, absent: bool = False) -> str | None:
        """The verdict where it is decided, None while a competitor is; `absent` reads every
        undecided competitor as not registered — a closed loop's own members, as the first
        one the container reads sees them."""
        states: list[str | None] = []
        for matches in criteria[key]:
            found = [(exists(symbol, environment), sure) for symbol, sure in matches]
            if absent:
                found = [(FAILS if state is None else state, sure) for state, sure in found]
            if any(state == HOLDS and sure for state, sure in found):
                states.append(_MET)
            elif all(state == FAILS for state, _ in found):
                states.append(_UNMET)
            elif any(state is None for state, _ in found):
                states.append(None)
            else:
                states.append(UNRESOLVED)
        decisive, needed = (_MET, _UNMET) if modes[key] == "missing" else (_UNMET, _MET)
        if decisive in states:
            return FAILS
        if all(state == needed for state in states):
            return HOLDS
        return None if None in states else UNRESOLVED

    def waits_on(key: tuple[str, str, str], environment: str) -> set[tuple[str, str, str]]:
        return {
            other
            for matches in criteria[key]
            for symbol, _ in matches
            if exists(symbol, environment) is None
            for other in held.get(symbol, ())
            if verdict[other][environment] is None
        }

    def closed_loops(environment: str, waiting: list[tuple[str, str, str]]) -> list[list[Any]]:
        """The loops among `waiting` that wait on nothing outside themselves."""
        reach: dict[tuple[str, str, str], set[tuple[str, str, str]]] = {}
        for start in waiting:
            seen = {start}
            frontier = [start]
            while frontier:
                for other in waits_on(frontier.pop(), environment):
                    if other not in seen:
                        seen.add(other)
                        frontier.append(other)
            reach[start] = seen
        loops: list[list[Any]] = []
        for start in waiting:
            loop = {other for other in reach[start] if start in reach[other]}
            if loop == reach[start] and sorted(loop) not in loops:
                loops.append(sorted(loop))
        return loops

    pending = sorted(
        (key, environment)
        for key, per_environment in verdict.items()
        for environment, state in per_environment.items()
        if state is None
    )
    while pending:
        decided = []
        for key, environment in pending:
            state = judge(key, environment)
            if state is not None:
                verdict[key][environment] = state
                decided.append((key, environment))
        if not decided:
            for environment in environments:
                waiting = [key for key, at in pending if at == environment]
                for loop in closed_loops(environment, waiting):
                    if all(modes[key] == "present" for key in loop):
                        settled = {key: judge(key, environment, absent=True) for key in loop}
                        for key, state in settled.items():
                            verdict[key][environment] = state or UNRESOLVED
                            if state == FAILS:
                                looped[(key, environment)] = loop_reasons[key][1]
                    else:
                        for key in loop:
                            verdict[key][environment] = UNRESOLVED
                            looped[(key, environment)] = loop_reasons[key][0]
                    decided.extend((key, environment) for key in loop)
        done = set(decided)
        pending = [item for item in pending if item not in done]

    def deciders(key: tuple[str, str, str], environment: str) -> list[dict[str, str | None]]:
        """The competitors that decided the verdict — those that exist where one existing
        decides it, every one matched where none existing decides it — or left it open."""
        final = verdict[key][environment]
        mode = modes[key]
        chosen: set[str] = set()
        for matches in criteria[key]:
            found = [(symbol, sure, exists(symbol, environment)) for symbol, sure in matches]
            present = [symbol for symbol, sure, state in found if state == HOLDS and sure]
            if final == UNRESOLVED:
                chosen.update(symbol for symbol, _, state in found if state != FAILS)
            elif (mode, final) in (("missing", FAILS), ("present", HOLDS)):
                chosen.update(present)
            elif mode == "missing" or not present:
                chosen.update(symbol for symbol, _, _ in found)
        entries: list[dict[str, str | None]] = []
        for symbol in chosen:
            other = by_symbol[symbol]
            state = exists(symbol, environment) or UNRESOLVED
            for bean in sorted(other.beans) or [other.registered or symbol]:
                entry: dict[str, str | None] = {
                    "bean": bean,
                    "via": symbol if other.route == FACTORY else None,
                    "holds": state,
                }
                notes = [
                    f"profile `{name}` is named but this module has no `{name}` environment"
                    for name in unseen[symbol]
                ]
                if notes:
                    entry["note"] = "; ".join(notes)
                entries.append(entry)
        return sorted(entries, key=lambda entry: (entry["bean"] or "", entry["via"] or ""))

    judged: dict[tuple[str, str, str], _Presence] = {}
    for key, per_environment in verdict.items():
        stated: dict[str, tuple[str, str, str]] = {}
        for environment, final in per_environment.items():
            listed = COMPETITORS + json.dumps(deciders(key, environment), sort_keys=True)
            loop_reason = looped.get((key, environment))
            if final in (HOLDS, FAILS):
                reason = ON_MODULE_BEANS + (f"; {loop_reason}" if loop_reason else "")
                stated[environment] = (str(final), PARTIAL, reason + listed)
                continue
            reason = reasons.get(key) or loop_reason or _COMPETITOR_OPEN
            stated[environment] = (UNRESOLVED, UNRESOLVED, f"{_NOT_DECIDED}: {reason}{listed}")
        judged[key] = _Presence(expression=expressions[key], verdicts=stated)
    return judged


def _effective_index(
    workspace: Workspace,
    index: dict[str, list[tuple[str, dict[str, Any]]]],
    annotation_types: set[str],
    seeds: set[str],
) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    """`index` plus, for every use of an annotation that is meta-annotated by one of `seeds`
    (transitively, through module-local annotation types and dependency types whose header
    was read), a row naming the seed itself with the composition's arguments folded under
    the use site's — `composed_mapping_rows`' own fold, run once per seed so a composed type
    carrying two (a stereotype AND a condition) contributes both."""
    headers = [
        {
            "target": str(row["target"]),
            "annotation": bare_descriptor(str(row["annotation"])),
            "args": json.loads(str(row["args"])) if row["args"] is not None else {},
        }
        for row in workspace.query("type_header_annotations")
    ]
    header_types = {row["target"] for row in headers}
    # A seed is decided by its own model, never through what it is built on: the header of
    # `@ConditionalOnProperty` records `@Conditional(OnPropertyCondition)`, and composing
    # through it would add an unevaluated `other` row to every direct use.
    composing = {
        symbol for symbol in annotation_types | header_types if bare_descriptor(symbol) not in seeds
    }
    names = {bare_descriptor(symbol) for symbol in composing}
    # Only rows a composition can touch: a declaration ON an annotation type, or a USE of one.
    rows = [
        row
        for row in (
            *(
                {"target": target, "annotation": bare_descriptor(annotation), "args": args}
                for target, uses in index.items()
                for annotation, args in uses
            ),
            *headers,
        )
        if row["target"] in composing or row["annotation"] in names
    ]
    effective = {target: list(uses) for target, uses in index.items()}
    for seed in sorted(seeds):
        for row in composed_mapping_rows(rows, composing, {seed}):
            # A composing type's own declaration row comes back too; it is no bean's use.
            if row["target"] in composing:
                continue
            effective.setdefault(str(row["target"]), []).append(
                (str(row["annotation"]), dict(row["args"]))
            )
    return effective


def _lambdas_created_by(workspace: Workspace) -> dict[str, list[str]]:
    """Creating method -> the synthetic bodies (lambdas) its `dynamic` call sites create.
    `synthetic` is the compiler's own mark on a lambda body (D00 §5a); a method REFERENCE
    names a method someone wrote, which belongs to its own class, not to the creator."""
    synthetic = set()
    for row in workspace.query("method_declarations"):
        modifiers = row.get("modifiers")
        if isinstance(modifiers, dict) and modifiers.get("synthetic"):
            synthetic.add(str(row["symbol"]))
    created: dict[str, list[str]] = {}
    for row in workspace.query("lambda_edges"):
        if str(row["callee"]) in synthetic:
            created.setdefault(str(row["caller"]), []).append(str(row["callee"]))
    return created


def _created_from(method: str, created: dict[str, list[str]]) -> list[str]:
    """Every lambda body `method` creates, and every one those create in turn."""
    found: list[str] = []
    pending = list(created.get(method, ()))
    while pending:
        body = pending.pop()
        if body in found:
            continue
        found.append(body)
        pending.extend(created.get(body, ()))
    return sorted(found)


def _constructed_by(workspace: Workspace) -> dict[str, list[str]]:
    """Calling method -> the module classes its body constructs, each the owner of the
    constructor body the edge reaches — the full symbol `symbols.enclosing` spells it in."""
    constructed: dict[str, list[str]] = {}
    for row in workspace.query("constructor_edges"):
        owner = enclosing_type_of(str(row["callee"]))
        if owner is not None:
            constructed.setdefault(str(row["caller"]), []).append(owner)
    return constructed


def _ancestors(workspace: Workspace) -> dict[str, list[str]]:
    """Bare type -> its direct supertypes, bare (`type_hierarchy`, the JVM's search order)."""
    found: dict[str, list[str]] = {}
    for row in workspace.query("type_hierarchy"):
        found.setdefault(str(row["child"]), []).append(str(row["ancestor"]))
    return found


def _assignable(child: str, declared: str, ancestors: dict[str, list[str]]) -> bool:
    """Whether `child` (bare) is `declared` (bare) or a subtype of it."""
    seen: set[str] = set()
    pending = [child]
    while pending:
        current = pending.pop()
        if current == declared:
            return True
        if current in seen:
            continue
        seen.add(current)
        pending.extend(ancestors.get(current, ()))
    return False


def _supertypes_of(bare: str, ancestors: dict[str, list[str]]) -> set[str]:
    """`bare` and every type it is a subtype of (`type_hierarchy`, transitively)."""
    seen: set[str] = set()
    pending = [bare]
    while pending:
        current = pending.pop()
        if current not in seen:
            seen.add(current)
            pending.extend(ancestors.get(current, ()))
    return seen


def _registered_interfaces(
    interfaces: list[str],
    entries: list[dict[str, Any]],
    annotated: dict[str, frozenset[str]],
    ancestors: dict[str, list[str]],
) -> list[str]:
    """The module's interfaces the framework registers as beans (CP-46): one assignable to an
    entry's `supertypes` (row 4), or carrying its `annotation` on itself or an interface it
    extends (row 2) — never one carrying `excluded_by` itself (rows 2, 3). Composed
    annotations count, as for classes. **Stated limits:** whether scanning runs, and from
    which packages, is the module's configuration and not read; a nested interface is not
    refused; an annotation on a DEPENDENCY interface it extends is not read."""
    if not entries:
        return []
    found: list[str] = []
    for interface in interfaces:
        bare = bare_descriptor(interface)
        above = _supertypes_of(bare, ancestors)
        own = annotated.get(bare, frozenset())
        for entry in entries:
            excluded = entry.get("excluded_by")
            if excluded and type_descriptor(str(excluded)) in own:
                continue
            marker = entry.get("annotation")
            if any(type_descriptor(str(name)) in above for name in entry["supertypes"]) or (
                marker and any(type_descriptor(str(marker)) in annotated.get(t, ()) for t in above)
            ):
                found.append(interface)
                break
    return sorted(set(found))


def _delegates(caller: str, built: str, ancestors: dict[str, list[str]]) -> bool:
    """Whether `caller` is a constructor handing off to `built`'s — `this(…)` in the same
    class or `super(…)` from a subclass. The same `invokespecial` a `new` compiles to, and it
    constructs nothing: read as a route, every conditional base class with a subclass would
    turn `unresolved`."""
    if method_name(bare_descriptor(caller)) != _CONSTRUCTOR:
        return False
    owner = enclosing_type_of(caller)
    return owner is not None and _assignable(
        bare_descriptor(owner), bare_descriptor(built), ancestors
    )


def _expression(model: ConditionModel, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """The structured expression (spec §2) read off one annotation use's arguments."""
    if model.kind == PROFILE:
        expressions = _strings(args.get(str(model.members.get("expressions", "value"))))
        return PROFILE, {"expressions": expressions}
    if model.kind == PROPERTY:
        # CP-43 row 4 (`Spec.getPrefix`): trimmed, and `.` appended only where the prefix
        # does not already end in one — `prefix = "orders."` and `"orders"` both name
        # `orders.legacy`.
        prefix = str(args.get(str(model.members.get("prefix", "prefix")), "") or "").strip()
        if prefix and not prefix.endswith("."):
            prefix += "."
        names: list[str] = []
        for member in model.members.get("names", ["name", "value"]):
            names.extend(_strings(args.get(str(member))))
        keys = [prefix + name for name in names]
        having = str(args.get(str(model.members.get("having_value", "havingValue")), "") or "")
        missing = args.get(str(model.members.get("match_if_missing", "matchIfMissing")), False)
        return PROPERTY, {
            "keys": keys,
            "having_value": having,
            "match_if_missing": bool(missing)
            if isinstance(missing, bool)
            else str(missing).lower() == "true",
        }
    return OTHER, {"annotation": model.annotation, "args": args}


def _holds(
    kind: str,
    expression: dict[str, Any],
    config: dict[str, str | None],
    environment: str,
    active: ActiveProfiles | None = None,
) -> tuple[str, str]:
    """`(holds, resolution)` for one condition in one environment, by the framework's rule.
    A `profile` is judged against the environment's `active` profiles — the environment's own
    name alone where none are given, which is what configuration naming no profile makes it."""
    if kind == PROFILE:
        found = active or ActiveProfiles(known=frozenset({environment}))
        holds, resolution, _ = _profile_holds(expression, found)
        return holds, resolution
    if kind == PROPERTY:
        # Several names are several keys the framework requires ALL of (CP-43: one Spec per
        # annotation, every name checked); a key this environment never saw is decided by
        # `match_if_missing`; a placeholder nobody filled is unresolved here.
        having = str(expression["having_value"])
        for key in expression["keys"]:
            if key not in config:
                if not expression["match_if_missing"]:
                    return FAILS, "resolved"
                continue
            value = config[key]
            if value is None:
                return UNRESOLVED, "unresolved"
            matched = value.lower() == having.lower() if having else value.lower() != "false"
            if not matched:
                return FAILS, "resolved"
        return HOLDS, "resolved"
    return UNRESOLVED, "unresolved"


def _judged(
    model: ConditionModel,
    kind: str,
    expression: dict[str, Any],
    environment: str,
    config: dict[str, str | None],
    active: ActiveProfiles,
    default_environment: str,
    reading: str,
) -> tuple[str, str, str]:
    """`(holds, resolution, evidence)` for one condition in one environment — the verdict the
    pass PUBLISHES (spec 2026-10-23-deployment-set-conditions §3b). `_holds` and
    `_profile_holds` stay the repository's reading by the framework's rule (CP-42, CP-43,
    CP-45); for a kind the bean model marks `set_by: deployment` (CP-47: an environment
    variable or a command-line argument outranks every file the module ships) that reading is
    evidence, never the verdict (ruled 2026-10-23, ruling 1):

    * `profile` — decided only by the environment's own definition: in profile environment
      `p`, a term naming `p` holds and `!p` fails; nothing decides anything in
      `default_environment`. Every other term is `unresolved`, its evidence `reading`: one
      string per module, the same in every environment (`deployment_reading`);
    * `property` — `unresolved` in every environment, its evidence the value each key's
      environment configuration resolves (masked by its key, `_REDACTOR`), a placeholder
      the module does not fill, or that it sets none.

    A kind without `set_by` keeps the framework rule's verdict, `active` being the
    environment's active profiles by that rule."""
    if model.members.get("set_by") == "deployment":
        if kind == PROFILE:
            own = frozenset() if environment == default_environment else frozenset({environment})
            return _profile_holds(expression, ActiveProfiles(known=own, otherwise=reading))
        if kind == PROPERTY:
            return (
                UNRESOLVED,
                "unresolved",
                "; ".join(
                    f"`{key}` is set by the deployment; this module's `{environment}` "
                    "configuration sets "
                    + (
                        "nothing"
                        if key not in config
                        else "a placeholder this module does not fill"
                        if config[key] is None
                        else f"`{_REDACTOR.redact_value(key, str(config[key]))}`"
                    )
                    for key in expression["keys"]
                ),
            )
    if kind == PROFILE:
        return _profile_holds(expression, active)
    holds, resolution = _holds(kind, expression, config, environment)
    return holds, resolution, "compiler"


def deployment_reading(base: ActiveProfiles, default_profile: str) -> str:
    """The evidence of every `profile` condition a deployment sets, ONE string per module and
    the same in every environment (spec 2026-10-23-deployment-set-conditions §3b, §3c, as
    ruled at review): the module's own activation as read for its BASE environment (`base`,
    CP-45) — the reason a placeholder leaves it unknown, or the profiles it activates. The
    reserved `default_profile`, active there only because the module names none (CP-45 row
    5), is no activation the module makes."""
    prefix = "active profiles are set by the deployment; "
    if base.otherwise:
        return prefix + base.otherwise
    names = sorted(base.known)
    if names == [default_profile]:
        names = []
    if not names:
        return prefix + "this module activates none"
    return prefix + f"this module's own default is `{','.join(names)}`"


def _profile_holds(expression: dict[str, Any], active: ActiveProfiles) -> tuple[str, str, str]:
    """`(holds, resolution, evidence)` for one `profile` condition against one environment's
    active profiles. ANY listed expression matching accepts (CP-42 row 2), so a plain term
    that holds decides the whole condition whatever else is listed; else one that is open
    leaves it `unresolved`, its evidence saying why; a COMPOSED term (row 3) is one this
    analysis does not evaluate, and it leaves the condition `unresolved` where nothing holds.
    `!name` inverts its name's verdict, an open one staying open."""
    states: list[str] = []
    reasons: set[str] = set()
    composed = False
    for raw in expression["expressions"]:
        text = str(raw).strip()
        if any(char in _COMPOSITION for char in text):
            composed = True
            continue
        negated = text.startswith("!")
        name = text[1:].strip() if negated else text
        reason = active.unknown.get(name) or active.otherwise
        if name in active.known:
            state = FAILS if negated else HOLDS
        elif reason is not None:
            state = UNRESOLVED
            reasons.add(reason)
        else:
            state = HOLDS if negated else FAILS
        states.append(state)
    if HOLDS in states:
        return HOLDS, "resolved", "compiler"
    if UNRESOLVED in states:
        return UNRESOLVED, "unresolved", "; ".join(sorted(reasons))
    if composed:
        return UNRESOLVED, "unresolved", "compiler"
    return FAILS, "resolved", "compiler"


def active_profiles(
    config: dict[str, dict[str, str | None]],
    profiles: Mapping[str, Any],
    environments: list[str],
    unfilled: Mapping[str, list[str]],
) -> dict[str, ActiveProfiles]:
    """Each environment's active profiles (CP-45), from the BASE environment's resolved
    configuration alone — a profile-specific file may not set the keys (row 7). `profiles`
    is the config model's `profiles` block: `active_keys`, `include_keys` and `default_keys`
    name the keys, `default_profile` the base environment and the reserved default profile.
    A key's value is a comma-separated list with whitespace removed, or a list flattened to
    `key[0]`, `key[1]` (row 4); one resolved to no value (`None`) is a placeholder nothing
    fills, named by `unfilled`'s raw spelling of it where the configuration gives one.

    * the base environment: the profiles the active and include keys list, else (neither
      naming one, row 5) those the default keys list, else `default_profile`;
    * a profile file's environment `p`: `p` and the included ones (row 6); a profile named
      only in the base's active list is unknown there — the activation selecting `p` decides;
    * a placeholder in the active or include keys leaves every other profile unknown
      (`otherwise`); one in the default keys does, in the base, where nothing else is listed;
    * a GROUP (row 8, `expandProfiles`): `group_prefix` + `.<name>` lists profiles active
      wherever `<name>` is, `<name>` staying active itself — followed transitively, each
      profile expanded once, so a cycle ends. A member takes the certainty of the profile that
      activates it: active where that is, unknown (with the reason naming the group) where
      that is. **Stated limit:** a group whose value is a placeholder nothing fills adds no
      member."""
    default = str(profiles.get("default_profile", "default"))
    base = config.get(default, {})
    groups: dict[str, list[str]] = {}
    prefix = profiles.get("group_prefix")
    if prefix:
        member = re.compile(re.escape(str(prefix)) + r"\.(?P<name>.+?)(?:\[\d+\])?")
        for key in sorted(base):
            grouped = member.fullmatch(key)
            value = base[key]
            if grouped is not None and value is not None:
                listed_here = "".join(value.split()).split(",")
                groups.setdefault(grouped["name"], []).extend(n for n in listed_here if n)

    def expanded(names: Iterable[str]) -> frozenset[str]:
        """`names` and every member of their groups, transitively (row 8)."""
        reached: set[str] = set()
        pending = list(names)
        while pending:
            name = pending.pop()
            if name not in reached:
                reached.add(name)
                pending.extend(groups.get(name, ()))
        return frozenset(reached)

    def listed(keys: Any) -> tuple[list[tuple[str, str]], list[str]]:
        """(each profile listed, with the key listing it; the spelling of each placeholder
        nothing fills that one of the keys holds instead)."""
        names: list[tuple[str, str]] = []
        placeholders: list[str] = []
        for key in keys or ():
            element = re.compile(re.escape(str(key)) + r"(?:\[\d+\])?")
            for found in sorted(k for k in base if element.fullmatch(k)):
                value = base[found]
                if value is None:
                    placeholders.extend(f"`{text}`" for text in unfilled.get(found) or [found])
                    continue
                names.extend((name, str(key)) for name in "".join(value.split()).split(",") if name)
        return names, placeholders

    actives, active_open = listed(profiles.get("active_keys"))
    includes, include_open = listed(profiles.get("include_keys"))
    defaults, default_open = listed(profiles.get("default_keys"))

    def unknown_because(placeholders: list[str]) -> str | None:
        if not placeholders:
            return None
        spelled = ", ".join(dict.fromkeys(placeholders))
        return f"the active profiles here come from {spelled}, which this module does not fill"

    included = frozenset(name for name, _ in includes)
    opened = unknown_because(active_open + include_open)
    found: dict[str, ActiveProfiles] = {}
    for environment in environments:
        if environment == default:
            named = frozenset(name for name, _ in actives) | included
            if named or opened:
                found[environment] = ActiveProfiles(known=expanded(named), otherwise=opened)
            else:
                fallback = frozenset(name for name, _ in defaults)
                found[environment] = ActiveProfiles(
                    known=expanded(
                        fallback or (frozenset() if default_open else frozenset({default}))
                    ),
                    otherwise=unknown_because(default_open),
                )
            continue
        known = expanded(frozenset({environment}) | included)
        # Worded without the environment's name, so the reason is one string wherever it
        # applies and the document states the environments it leaves open on one line.
        unknown = {
            name: (
                f"named only in the base's `{key}`; the activation selecting this "
                "environment decides it"
            )
            for name, key in actives
            if name not in known
        }
        for name, reason in list(unknown.items()):
            for joined in sorted(expanded([name]) - known):
                unknown.setdefault(joined, f"a member of the group `{name}`, which is {reason}")
        found[environment] = ActiveProfiles(known=known, unknown=unknown, otherwise=opened)
    return found


def _active_by_environment(
    workspace: Workspace,
    catalogs: list[Catalog],
    config: dict[str, dict[str, str | None]],
    environments: list[str],
) -> dict[str, ActiveProfiles]:
    """`active_profiles` for this module, with the keys its family's config model names (the
    first catalog carrying a `profiles` block — the family's base catalog) and, for a key
    nothing fills, its raw spelling from the configuration the module ships."""
    profiles = _profiles_model(catalogs)
    unfilled: dict[str, list[str]] = {}
    for row in workspace.query("config_entries"):
        if row["value"] is not None:
            unfilled.setdefault(str(row["key_path"]), []).append(str(row["value"]))
    return active_profiles(config, profiles, environments, unfilled)


def _profiles_model(catalogs: list[Catalog]) -> Mapping[str, Any]:
    """The config model's `profiles` block: the first catalog carrying one, the family's
    base catalog."""
    return next(
        (c.config_model["profiles"] for c in catalogs if c.config_model.get("profiles")), {}
    )


def _config_by_environment(workspace: Workspace) -> dict[str, dict[str, str | None]]:
    """`resolved_config` as environment -> key -> value; a key resolved to no value (a
    placeholder nobody filled, a `missing_key` row) is present with `None`, which
    `_holds` reads as `unresolved` for a `property` — distinct from a key never seen."""
    config: dict[str, dict[str, str | None]] = {}
    for row in workspace.query("resolved_config"):
        environment = str(row["environment"])
        key = str(row["key"])
        value = row["value"]
        reason = row.get("unresolved_reason")
        bucket = config.setdefault(environment, {})
        if value is None and reason == "missing_key" and row.get("source") is None:
            # The config layer writes one row per key per environment even where that
            # environment never defines it, so the gap is visible; here "never defined" is
            # the ABSENT case `match_if_missing` decides, not an unfilled value. `source`
            # tells the two apart (D01: NULL only when no file ever declared the key): a
            # DECLARED key whose `${REF}` nobody filled resolves `missing_key` too, with
            # its file as `source`, and the framework would see SOME value there — so it
            # stays, as `None`, and reads `unresolved`.
            continue
        bucket[key] = None if value is None else str(value)
    return config


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]
