"""A controller that exists in one environment only (spec 2026-10-21-conditional-controllers,
ruled 2026-10-22): the class-level condition an inbound endpoint's handler type carries,
STATED on the row as structured data and evaluated per environment the module resolves —
never deciding whether the row exists.

The framework knowledge is the catalog's (`matches.mapping.conditions`, D02): which
annotation, which of its members, and the probe that read the rule off the jar. This pass
reads two existing things — the handler type's class-level annotations
(`conditions.annotation_index`, one decode per load) and `resolved_config` — and writes
`endpoint_conditions`: one row per (inbound endpoint, condition, environment).

What it evaluates, and what it refuses (spec §3b, §4):

* `profile` — a bare name holds where the environment IS that profile (the config layer's
  own filename rule makes an environment a profile), `!name` where it is not; any expression
  carrying `&`, `|` or a parenthesis (CP-42 row 3) is `unresolved` in every environment —
  stated, never evaluated.
* `property` — the key's resolved value in that environment against `having_value`
  (case-insensitive; EMPTY means "not `false`", CP-43 row 2); an absent key is decided by
  `match_if_missing` (CP-43 row 3); a key whose value is a placeholder nobody filled is
  `unresolved` there.
* `other` — any class-level annotation in the catalog's `conditions` block this pass has no
  rule for is written verbatim with `holds = unresolved`; nothing outside that block is read.

Runs AFTER `apply_protocol_hints`: a row names its endpoint by the identity columns, and
`protocol` is final only there. Cost per resolve (GUIDELINES §8.7): one read of `endpoints`,
one `annotation_index` lookup per inbound handler TYPE, one read of `resolved_config`, one
insert — nothing per catalog beyond reading its block.
"""

import json
from dataclasses import dataclass
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.conditions import annotation_index, enclosing_type_of
from sextant.domain.symbols import bare_descriptor, type_descriptor

PROFILE = "profile"
PROPERTY = "property"
OTHER = "other"
HOLDS = "true"
FAILS = "false"
UNRESOLVED = "unresolved"
# The characters that make a profile string an EXPRESSION rather than a name (CP-42 row 3):
# a composition over several active profiles, which this analysis does not evaluate.
_COMPOSITION = set("&|()")


@dataclass(frozen=True)
class ConditionModel:
    """One `conditions` entry as a catalog declares it: the annotation (as the fact stream
    spells it, `org/springframework/context/annotation/Profile#`) and which members fill the
    structured expression."""

    kind: str
    annotation: str
    members: dict[str, Any]


def record_endpoint_conditions(workspace: Workspace, catalogs: list[Catalog]) -> None:
    models = _models(catalogs)
    if not models:
        return
    endpoints = [row for row in workspace.query("endpoints") if row["direction"] == "inbound"]
    if not endpoints:
        return
    index = annotation_index(workspace)
    config = _config_by_environment(workspace)
    environments = sorted(config) or ["default"]
    rows: list[dict[str, Any]] = []
    for endpoint in endpoints:
        handler = endpoint.get("handler")
        if handler is None:
            continue
        owner = enclosing_type_of(str(handler))
        if owner is None:
            continue
        for descriptor, args in index.get(owner, ()):
            model = models.get(bare_descriptor(descriptor))
            if model is None:
                continue
            kind, expression = _expression(model, args)
            for environment in environments:
                holds, resolution = _holds(
                    kind, expression, config.get(environment, {}), environment
                )
                rows.append(
                    {
                        "protocol": endpoint["protocol"],
                        "direction": endpoint["direction"],
                        "method": endpoint["method"],
                        "path": endpoint["path"],
                        "handler": handler,
                        "kind": kind,
                        "expression": json.dumps(expression, sort_keys=True),
                        "environment": environment,
                        "holds": holds,
                        "resolution": resolution,
                        "evidence": "compiler",
                    }
                )
    if rows:
        workspace.derive("endpoint_conditions_insert", rows=rows)


def _models(catalogs: list[Catalog]) -> dict[str, ConditionModel]:
    """Every `conditions` entry across the catalogs, keyed by the annotation's bare symbol.
    Refused naming the file where the block is malformed, as the requirements pass refuses
    its own block; `by:` is required, because a rule nobody measured is a guess."""
    models: dict[str, ConditionModel] = {}
    for catalog in catalogs:
        mapping = catalog.matches.get("mapping")
        if not isinstance(mapping, dict) or "conditions" not in mapping:
            continue
        declared = mapping["conditions"]
        where = f"loading catalog {catalog.source}: `mapping.conditions`"
        if not isinstance(declared, dict):
            raise CatalogError(f"{where} must be a mapping of kind to entry, got {declared!r}")
        for kind, entry in declared.items():
            if kind not in (PROFILE, PROPERTY, OTHER) or not isinstance(entry, dict):
                raise CatalogError(
                    f"{where}.{kind}: the kinds are `profile`, `property` and `other`, "
                    "each a mapping"
                )
            if kind == OTHER:
                # The conditions this analysis NAMES and does not evaluate (spec §4): each is
                # code, not configuration — a `Condition` class, a bean's presence, a SpEL
                # expression — and a verdict would be a guess. One model per annotation, so
                # a row is written verbatim with `holds = unresolved` in every environment,
                # rather than the endpoint reading as unconditional.
                names = entry.get("annotations")
                if not isinstance(names, list) or not names or not entry.get("by"):
                    raise CatalogError(
                        f"{where}.other needs `annotations` (a list) and a `by:` probe"
                    )
                for name in names:
                    symbol = type_descriptor(str(name))
                    models[symbol] = ConditionModel(kind=OTHER, annotation=symbol, members={})
                continue
            annotation = entry.get("annotation")
            if not isinstance(annotation, str) or not entry.get("by"):
                raise CatalogError(f"{where}.{kind} needs `annotation` and a `by:` probe")
            symbol = type_descriptor(annotation)
            models[symbol] = ConditionModel(kind=kind, annotation=symbol, members=dict(entry))
    return models


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
