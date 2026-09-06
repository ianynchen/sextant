"""`scheduled_work` engine (D02 §2's `scheduled_work` style, 2O design §4a).

The first of two NON-WIRE styles. It derives into `scheduled_work`, a table of
its own, and never into `endpoints`: `endpoints` is wire-true (user ruling),
and a method the framework calls on a clock serves no protocol, no address and
no direction. A row claiming any of the three would be a boundary nothing
serves — the cardinal sin, reached by widening a table rather than by
misreading a fact.

**Scheduled handlers are deliberately not endpoints, and a row here IS a
root.** The two are separate claims and both hold. A method the framework
calls on a clock still serves no protocol and no address, so it never becomes
an `endpoints` row — but it starts work and contains business logic, so it is
one of [D00](docs/components/D00-fact-schema.md) §4's `root_kind` members and a
trace begins at it exactly as one begins at a served handler.

*This docstring said the opposite until 2Q's `I1`* — that `root_kind` "does
not exist anywhere in `src/`", entry #7 of
`docs/documented-not-implemented.md`, and that the omission "becomes wrong the
moment a `root_kind` producer ships". It shipped:
`resolve/roots.py` reads this table and writes one `roots` row per handler
here, so nothing in this file is half of a live mechanism any more. The engine
itself is unchanged by that — it still derives `scheduled_work` and nothing
else; what changed is that something downstream now walks from what it wrote.

**What is read, and what is not.** The catalog names one annotation, the
container javac folds repeats into, and which of the annotation's attributes
name a trigger at all. Each trigger attribute the declaration WRITES becomes
one row carrying the framework's own word for the schedule kind and the
expression VERBATIM. Nothing is evaluated: a `${...}` placeholder is carried
exactly as written and the row says `unresolved` beside it, because a
placeholder's value comes from configuration a deployment can overwrite (§8.2)
and substituting one here would publish a schedule this repository cannot
know.

**A declaration naming no trigger attribute derives nothing.** There is no
expression to carry, and a row with an empty schedule would claim work on a
clock nobody set. That is an absence, not a refusal: an attribute the catalog
does not name is not a schedule, which is what stops `initialDelay` — a real
attribute that delays the FIRST run of a schedule declared elsewhere — from
being published as the schedule itself.
"""

import json
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.shapes.rooting import _catalog_symbol

_ANNOTATION = "annotation"
_CONTAINER = "container"
_TRIGGERS = "triggers"
_REQUIRED_MATCHES = (_ANNOTATION, _CONTAINER, _TRIGGERS)

# The one form of expression this pass refuses to answer for. A property
# placeholder is resolved by the framework at startup out of configuration —
# environment variables, a ConfigMap, a command-line argument — none of which a
# repository can see (§8.2), so the expression is carried verbatim and the row
# says so. Spelled here rather than in the catalog because it is the SYNTAX of
# a placeholder shared by every property-driven framework this repository
# reads, exactly as `resolve/config.py` already treats it.
_PLACEHOLDER = "${"


def run(workspace: Workspace, catalog: Catalog) -> None:
    """One row per trigger attribute each claimed declaration writes.

    Rows are emitted in a deterministic order — declaration target, then the
    catalog's own attribute order sorted — so two runs over one workspace
    produce the same bytes (NFR-1). The insert appends; the table is emptied
    once per resolve by the pipeline, never here, because a second catalog
    (§4a's "Quartz: later catalog, same table") writes to the same table.
    """
    triggers = _validate_matches(catalog)
    rows: list[dict[str, Any]] = []
    for target, args in _declarations(workspace, catalog):
        for attribute in sorted(triggers):
            if attribute not in args:
                continue
            expression = _verbatim(args[attribute])
            if expression is None:
                # A trigger attribute whose value is not a literal this pass
                # can spell — an annotation-valued argument, or one the
                # extractor recorded as unread. There is no expression, so
                # there is no row: an attribute that was written and could not
                # be read must never become a schedule with an invented one.
                continue
            rows.append(
                {
                    "handler": target,
                    "trigger": str(triggers[attribute]),
                    "expression": expression,
                    "resolution": ("unresolved" if _PLACEHOLDER in expression else "resolved"),
                    "evidence": "compiler",
                    "catalog_id": catalog.id,
                }
            )
    workspace.derive("scheduled_work_insert", rows=rows)


def _declarations(workspace: Workspace, catalog: Catalog) -> list[tuple[str, dict[str, Any]]]:
    """Every claimed declaration as `(method symbol, arguments)`, sorted.

    Two shapes reach this, and both are one annotation as far as the framework
    is concerned. A single use arrives as an ordinary annotation fact. TWO OR
    MORE uses on one method do not: the repeatable annotation is folded by
    javac into a single CONTAINER whose `value` is an array of the folded uses,
    so a method with two schedules carries no `@Scheduled` fact at all and only
    the container's own nested arguments (capability 9.16) can see them. The
    catalog names both, and this reads both into one list.

    **The target must be a METHOD**, and that is a conjunct rather than
    housekeeping. Spring's scheduling annotation is also `@Target`-legal on an
    ANNOTATION TYPE, which is how a module composes its own
    `@NightlySchedule` — that declaration is a composition, not a scheduled
    method, and publishing it would report work on a type the framework never
    invokes. `derive_endpoints.sql`'s own `handler-is-a-method` join is the
    same conjunct on the wire side.
    """
    annotation = _catalog_symbol(str(catalog.matches[_ANNOTATION]))
    container = _catalog_symbol(str(catalog.matches[_CONTAINER]))
    methods = {str(row["symbol"]) for row in workspace.query("method_symbols")}
    found: list[tuple[str, dict[str, Any]]] = []
    for row in workspace.query("annotations"):
        target = str(row["target"])
        if target not in methods:
            continue
        name = str(row["annotation"])
        args = _arguments(row["args"])
        if name == annotation:
            found.append((target, args))
        elif name == container:
            found.extend((target, folded) for folded in _folded(args, annotation))
    # `workspace.query("annotations")` is already ordered by (target,
    # annotation, type_path, args), and the folded uses keep the array order
    # javac wrote — which is the declaration order the source had. Sorting on
    # the target alone would therefore be a no-op; it is spelled anyway so the
    # order is a property of this pass rather than of a query it does not own
    # (NFR-1), and `key` names only the target so the folded order survives.
    return sorted(found, key=lambda entry: entry[0])


def _folded(args: dict[str, Any], annotation: str) -> list[dict[str, Any]]:
    """The container's own folded uses, in the order javac wrote them.

    Every entry is checked against the annotation the catalog names rather than
    taken on position: a container is an ordinary annotation whose `value`
    happens to be an array, and reading whatever it holds would let some other
    array-valued annotation contribute schedules.

    An entry the extractor recorded as unread (`unresolved`, capability 9.16's
    depth bound) carries no arguments and contributes nothing here. It cannot
    be reached by this shape — a folded use sits one level below the outermost
    annotation and the bound is five — and it is filtered rather than assumed
    away, because an entry with no `args` key would otherwise read as an
    annotation genuinely written with no arguments.
    """
    value = args.get("value")
    if not isinstance(value, list):
        return []
    return [
        entry["args"]
        for entry in value
        if isinstance(entry, dict)
        and entry.get(_ANNOTATION) == annotation
        and isinstance(entry.get("args"), dict)
    ]


def _arguments(raw: object) -> dict[str, Any]:
    """One annotation's arguments, decoded — an empty mapping where the fact
    carries none, which is what an annotation written with no arguments is."""
    if raw is None:
        return {}
    decoded = json.loads(str(raw))
    return decoded if isinstance(decoded, dict) else {}


def _verbatim(value: object) -> str | None:
    """The declared expression exactly as it was written, or None where the
    value is not one this pass can spell.

    A cron expression arrives as a string and a rate or delay as a number; both
    are the expression the framework schedules on and both are carried
    unchanged. A boolean, an array, or an annotation-valued argument is none of
    those — no framework spells a schedule that way, and turning one into text
    would publish a schedule nobody wrote. `bool` is checked before `int`
    deliberately: Python's `bool` IS an `int`, so an `isinstance(value, int)`
    test alone would spell `True` as `1`.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, int | float):
        return str(value)
    return None


def _validate_matches(catalog: Catalog) -> dict[str, object]:
    """Refuses a broken catalog before any declaration is read — the
    `injected_client._validate_matches` precedent, and the same reason: the
    values reach a published column, where a typo is indistinguishable from an
    observation."""
    matches = catalog.matches
    missing = [key for key in _REQUIRED_MATCHES if key not in matches]
    if missing:
        raise CatalogError(
            f"loading catalog {catalog.source}: `matches` is missing "
            f"{', '.join(missing)} — `scheduled_work` needs `annotation`, `container` and "
            f"`triggers` (2O design §4a)"
        )
    triggers = matches[_TRIGGERS]
    valid = (
        isinstance(triggers, dict)
        and bool(triggers)
        and all(isinstance(key, str) and isinstance(kind, str) for key, kind in triggers.items())
    )
    if not valid:
        raise CatalogError(
            f"loading catalog {catalog.source}: `triggers` must be a non-empty mapping of "
            f"`attribute: trigger kind`, got {triggers!r} (2O design §4a)"
        )
    return dict(triggers)
