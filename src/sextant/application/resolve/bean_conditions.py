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
  annotations are not consulted on that route — and a class constructed by a conditional
  factory AND registered or constructed any other way runs its code wherever either
  happens: every one of its rows is `unresolved`, the evidence naming the routes.

What it evaluates, and what it refuses (spec 2026-10-21 §3b, §4; unchanged by the move):

* `profile` — a bare name holds where the environment IS that profile (the config layer's
  own filename rule makes an environment a profile), `!name` where it is not; any expression
  carrying `&`, `|` or a parenthesis (CP-42 row 3) is `unresolved` in every environment —
  stated, never evaluated.
* `property` — the key's resolved value in that environment against `having_value`
  (case-insensitive; EMPTY means "not `false`", CP-43 row 2); an absent key is decided by
  `match_if_missing` (CP-43 row 3); a key whose value is a placeholder nobody filled is
  `unresolved` there.
* `other` — any annotation in the model's `conditions` block this pass has no rule for is
  written verbatim with `holds = unresolved`; nothing outside that block is read. The
  bean-presence conditions (`presence`) are among them until their own phase evaluates
  them (spec §2c).

Cost per resolve (GUIDELINES §8.7): the shared `annotation_index` (one decode per load), the
factory-method fold `beans.declared_beans` already keeps (one `method_declarations` read per
load, shared with `bean_via`), one `constructor_edges` read, one `type_hierarchy` read, one
`resolved_config` read and one insert — once per distinct bean model, none per catalog, per
bean or per row.
"""

import json
from dataclasses import dataclass
from typing import Any

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.beans import declared_beans
from sextant.application.resolve.conditions import annotation_index, enclosing_type_of
from sextant.domain.symbols import bare_descriptor, is_type_descriptor, method_name, type_descriptor

PROFILE = "profile"
PROPERTY = "property"
OTHER = "other"
HOLDS = "true"
FAILS = "false"
UNRESOLVED = "unresolved"
# The characters that make a profile string an EXPRESSION rather than a name (CP-42 row 3):
# a composition over several active profiles, which this analysis does not evaluate.
_COMPOSITION = set("&|()")
# `bean_kind`: where a condition on the bean was written (spec §2).
CLASS = "class"
FACTORY = "factory"
CONFIGURATION = "configuration"
# The route of a class constructed anywhere but a factory that returns it.
_CONSTRUCTED = "constructed"
# The JVM's own name for a constructor, which a member descriptor carries verbatim.
_CONSTRUCTOR = "<init>"


@dataclass(frozen=True)
class ConditionModel:
    """One `conditions` entry as a bean model declares it: the annotation (as the fact
    stream spells it, `org/springframework/context/annotation/Profile#`) and which members
    fill the structured expression."""

    kind: str
    annotation: str
    members: dict[str, Any]


@dataclass(frozen=True)
class _Route:
    """One way a class comes to exist at run time: scanned (`class`), returned by a factory
    method (`factory`, `via` the method), or constructed anywhere else (`via` the method
    whose body runs the `new`). `conditions` are the (bean_kind, model, args) the container
    evaluates on that route — empty for an unconditional one."""

    route: str
    via: str | None
    conditions: tuple[tuple[str, ConditionModel, dict[str, Any]], ...]

    def described(self) -> str:
        if self.route == CLASS:
            return "scanned"
        if self.route == FACTORY:
            return f"returned by factory {self.via}"
        return f"constructed in {self.via}"


def record_bean_conditions(workspace: Workspace, catalogs: list[Catalog]) -> None:
    vocabularies = _bean_models(catalogs)
    if not vocabularies:
        return
    index = annotation_index(workspace)
    config = _config_by_environment(workspace)
    environments = sorted(config) or ["default"]
    constructed = _constructed_by(workspace)
    ancestors = _ancestors(workspace)
    rows: list[dict[str, Any]] = []
    for model in vocabularies:
        routes = _routes(workspace, model, index, constructed, ancestors)
        for bean in sorted(routes):
            rows.extend(_rows_for(bean, routes[bean], config, environments))
    if rows:
        workspace.derive("bean_conditions_insert", rows=rows)


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
    return models


def _routes(
    workspace: Workspace,
    model: dict[str, Any],
    index: dict[str, list[tuple[str, dict[str, Any]]]],
    constructed: dict[str, list[str]],
    ancestors: dict[str, list[str]],
) -> dict[str, list[_Route]]:
    """Every class with at least one CONDITIONAL route, mapped to all of its routes —
    conditional or not, since a second route is what makes the first undecidable."""
    conditions = _models(model)
    stereotypes = {type_descriptor(str(name)) for name in model.get("stereotypes", ())}
    if model.get("configuration_annotation"):
        stereotypes.add(type_descriptor(str(model["configuration_annotation"])))

    def conditions_on(target: str | None, bean_kind: str) -> list[tuple[str, ConditionModel, Any]]:
        return [
            (bean_kind, conditions[bare_descriptor(descriptor)], args)
            for descriptor, args in index.get(target or "", ())
            if bare_descriptor(descriptor) in conditions
        ]

    routes: dict[str, list[_Route]] = {}
    for target, uses in index.items():
        if is_type_descriptor(target) and any(
            bare_descriptor(descriptor) in stereotypes for descriptor, _ in uses
        ):
            routes.setdefault(target, []).append(
                _Route(CLASS, None, tuple(conditions_on(target, CLASS)))
            )
    factories = declared_beans(workspace, model).by_method
    for caller, classes in constructed.items():
        factory = factories.get(caller)
        route_conditions = (
            ()
            if factory is None
            else (
                *conditions_on(caller, FACTORY),
                *conditions_on(enclosing_type_of(caller), CONFIGURATION),
            )
        )
        for built in classes:
            if (
                factory is not None
                and factory.erased_return is not None
                and _assignable(bare_descriptor(built), factory.erased_return, ancestors)
            ):
                routes.setdefault(built, []).append(_Route(FACTORY, caller, route_conditions))
            elif not _delegates(caller, built, ancestors):
                routes.setdefault(built, []).append(_Route(_CONSTRUCTED, caller, ()))
    return {
        bean: found for bean, found in routes.items() if any(route.conditions for route in found)
    }


def _rows_for(
    bean: str,
    routes: list[_Route],
    config: dict[str, dict[str, str | None]],
    environments: list[str],
) -> list[dict[str, Any]]:
    """One row per (route, condition, environment). A bean with ONE route is evaluated; a
    bean with several is `unresolved` on every row, the evidence naming each route."""
    distinct = sorted(
        {(route.route, route.via or ""): route for route in routes}.values(),
        key=lambda route: (route.route, route.via or ""),
    )
    reason = None
    if len(distinct) > 1:
        reason = "registered more than one way: " + "; ".join(
            route.described() for route in distinct
        )
    rows: list[dict[str, Any]] = []
    for route in distinct:
        for bean_kind, model, args in route.conditions:
            kind, expression = _expression(model, args)
            for environment in environments:
                if reason is None:
                    holds, resolution = _holds(
                        kind, expression, config.get(environment, {}), environment
                    )
                else:
                    holds, resolution = UNRESOLVED, UNRESOLVED
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
                        "evidence": reason or "compiler",
                    }
                )
    return rows


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
    kind: str, expression: dict[str, Any], config: dict[str, str | None], environment: str
) -> tuple[str, str]:
    """`(holds, resolution)` for one condition in one environment, by the framework's rule."""
    if kind == PROFILE:
        # ANY listed expression matching accepts (CP-42 row 2), so a plain name that matches
        # decides the whole condition whatever else is listed; a COMPOSED term (row 3) is one
        # this analysis does not evaluate, and it leaves the condition `unresolved` only
        # where no plain term already holds.
        verdicts = []
        composed = False
        for raw in expression["expressions"]:
            text = str(raw).strip()
            if any(char in _COMPOSITION for char in text):
                composed = True
                continue
            if text.startswith("!"):
                verdicts.append(environment != text[1:].strip())
            else:
                verdicts.append(environment == text)
        if any(verdicts):
            return HOLDS, "resolved"
        if composed:
            return UNRESOLVED, "unresolved"
        return FAILS, "resolved"
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
