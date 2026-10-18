"""The configured path prefix, applied to the rows it moves (spec 2026-10-18, `OI-148`).

A module that sets `server.servlet.context-path=/petclinic` serves EVERY endpoint under it,
and until this pass existed the document published them without it — 44 wrong routes in a
pinned corpus, recorded in its own field expectation. COVERAGE §5.1 stated the cause in its
own words: *"`annotation_driven` never touches `resolved_config` … a module that overrides
the base path is published under `/actuator` regardless."*

**Why a pass and not a rung in each engine.** The prefix is a property of the module's
SERVER, so it moves rows every engine derived — annotation-driven controllers, a
`config_join` route, `spring-data-rest` repositories, Actuator. One pass applies it once,
and a catalog written next year is covered without remembering anything. The alternative —
the same declaration in ten catalogs — puts a fact in ten files that none of them owns.

**Where it runs, and why there.** Immediately after `derive_endpoints`, before any pass that
copies a path: `record_roots`, `record_routing_conflicts` and `record_self_exchange` all key
on the address, and a prefix applied after them would leave a root and a conflict keyed on a
path the module does not serve — `OI-28`'s shape.

**What it will not do.** It never invents a prefix. A key no environment declares contributes
nothing; a key whose environments DISAGREE is refused outright and the row keeps the path it
had, because choosing one environment's value would publish an address the other does not
serve. That is the conservative half of the three outcomes `derived_resource._base_path`
already ships for `spring.data.rest.base-path`, and it is unexercised: no corpus has a
divergent prefix (CP-38's own scope note, and §5 of the spec measured all six pins).
"""

from typing import Any

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.domain.paths import canonical_http_path

# The identity columns a row is matched on, as `protocol_hint.py` matches them and for the
# same reason: `(protocol, direction, method, path)` is not unique — two listeners on one
# destination, several NULL-path call sites — and `handler`/`caller` are what separate them.
_MATCH_COLUMNS = ("protocol", "direction", "method", "path", "handler", "caller")


def apply_path_prefixes(workspace: Workspace, catalogs: list[Catalog]) -> None:
    """Prefixes every inbound row the module's own server configuration moves.

    Reads the server model (hoisted onto every catalog, so the first non-empty one is the
    whole table), `resolved_config` and the module fact's `dependency_versions`; writes one
    column, on rows that already existed.
    """
    model = next((catalog.server_model for catalog in catalogs if catalog.server_model), [])
    if not model:
        return
    config = _per_environment(workspace)
    if not config:
        return
    versions = _framework_versions(workspace)

    prefixes: dict[str, str] = {}
    for entry in model:
        if not _version_admits(entry, versions):
            continue
        prefix = _composed(entry["keys"], config)
        if not prefix:
            continue
        for protocol in entry["protocols"]:
            # Two entries claiming one protocol would be a contradiction in the model
            # rather than in the module — one server, one prefix per wire — so the first
            # declaration wins and the second is ignored rather than concatenated. The
            # shipped file has no such pair: its two entries differ by stack and their
            # keys cannot both be present (a module is servlet or reactive, not both).
            prefixes.setdefault(protocol, prefix)
    if not prefixes:
        return

    rows: list[dict[str, Any]] = []
    for endpoint in workspace.query("endpoints"):
        if str(endpoint.get("direction")) != "inbound":
            continue
        served_under = prefixes.get(str(endpoint.get("protocol")))
        path = endpoint.get("path")
        if served_under is None or not isinstance(path, str) or not path.startswith("/"):
            # A row with no path has no address to prefix, and one that does not start at
            # the root is not a path this server dispatches — both keep what they had.
            continue
        rows.append(
            {column: endpoint.get(column) for column in _MATCH_COLUMNS}
            | {"prefixed": canonical_http_path(f"{served_under}{path}")}
        )
    if rows:
        workspace.derive("prefix_endpoint_paths", rows=rows)


def _composed(keys: list[str], config: dict[str, dict[str, str | None]]) -> str:
    """The declared keys' values joined in declaration order, or `""`.

    `server.servlet.context-path=/petclinic/` with `spring.mvc.servlet.path=/api` composes
    to `/petclinic/api`. Separators are normalised here rather than assumed: the measured
    value in `spring-petclinic-rest` ends in `/` and the two must not join into `//`.
    """
    parts: list[str] = []
    for key in keys:
        value = _agreed(config, key)
        if value is None:
            continue
        trimmed = value.strip().strip("/")
        if trimmed:
            parts.append(trimmed)
    return "/" + "/".join(parts) if parts else ""


def _agreed(config: dict[str, dict[str, str | None]], key: str) -> str | None:
    """The one value every environment gives `key`, or None — including for a key no
    environment declares, and for one the environments DISAGREE about.

    `derived_resource._agreed`'s rule, restated rather than shared for the reason that
    function already records about `config_join`'s copy: it is private to another style, and
    the cases it collapses are the same cases this one needs. The disagreement answer is
    None on purpose — a prefix is refused rather than chosen, because one environment's
    value is an address the others do not serve.
    """
    per_environment = config.get(key)
    if not per_environment:
        return None
    distinct = {value for value in per_environment.values() if value is not None}
    if len(distinct) != 1:
        return None
    return distinct.pop()


def _version_admits(entry: dict[str, Any], versions: dict[str, str]) -> bool:
    """Whether this entry's framework and version range admit the module.

    **An UNRECORDED version admits every entry for that framework**, and that is the
    fallback the user ruled on 2026-10-18: a module configures one framework generation, so
    at most one spelling of a key can be present in its configuration, and the configuration
    then decides. `module_dependencies`' own comment states the same rule from the other
    side — *"a reader scoping a rule to a version must treat the absence as
    unanswerable"*.

    It matters because the absence is common and not exotic: `ruoyi-vue-pro` records no Boot
    version at all, its versions coming from an imported BOM and a `${revision}` property
    that the detector follows through neither (`OI-139`, `OI-8`). The direction there is to
    follow the chain rather than cap at a level — `OI-149`'s principle one layer out — and
    until it does, this fallback is what keeps such a module working.
    """
    framework = str(entry["framework"]) + ":"
    found = [
        version for coordinate, version in versions.items() if coordinate.startswith(framework)
    ]
    if not found:
        return True
    return any(_in_range(version, str(entry["versions"])) for version in found)


def _in_range(version: str, specification: str) -> bool:
    """`>=2.0`, `>=2.0 <4.0` — the two forms the shipped model uses, compared on the leading
    numeric components.

    Deliberately not a full version-range grammar: this file reads what
    `server-models/*.yml` declares, the shipped declarations use these two forms, and a
    richer syntax with no consumer is a mechanism nobody has measured. A clause this cannot
    parse raises rather than passing silently, because a range read as "everything" would
    apply a prefix measured on Boot 2 to a Boot 1 module.
    """
    for clause in specification.split():
        operator = clause[:2]
        if operator not in (">=", "<="):
            operator, bound = clause[:1], clause[1:]
            if operator not in ("<", ">"):
                raise ValueError(f"server model: unreadable version clause {clause!r}")
        else:
            bound = clause[2:]
        left, right = _numeric(version), _numeric(bound)
        if operator == ">=" and not left >= right:
            return False
        if operator == "<=" and not left <= right:
            return False
        if operator == ">" and not left > right:
            return False
        if operator == "<" and not left < right:
            return False
    return True


def _numeric(version: str) -> tuple[int, ...]:
    """A version as its leading numeric components — `4.1.1` as `(4, 1, 1)`, `2.7.18-RC1`
    as `(2, 7, 18)`. A component that is not a number ends the tuple, which is what makes a
    qualifier compare as the release it qualifies rather than raising."""
    parts: list[int] = []
    for piece in version.split("."):
        digits = ""
        for character in piece:
            if not character.isdigit():
                break
            digits += character
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _per_environment(workspace: Workspace) -> dict[str, dict[str, str | None]]:
    """`resolved_config` as `key -> {environment: value}` — `config_join._config_values`'
    shape, read the same way for the same reason: the whole table is one small answer and
    every lookup here is a membership test against it."""
    values: dict[str, dict[str, str | None]] = {}
    for row in workspace.query("resolved_config"):
        environments = values.setdefault(str(row["key"]), {})
        value = row["value"]
        environments[str(row["environment"])] = None if value is None else str(value)
    return values


def _framework_versions(workspace: Workspace) -> dict[str, str]:
    """`coordinate -> version` from the module fact, which records it already (F1).

    A coordinate absent from the map is a version this analysis could not read, which is a
    different answer from a dependency with no version — so the absence travels to
    `_version_admits` as unanswerable rather than as a refusal.
    """
    import json

    versions: dict[str, str] = {}
    for row in workspace.query("module_dependencies"):
        recorded = row.get("dependency_versions")
        if recorded is None:
            continue
        parsed = json.loads(str(recorded)) if isinstance(recorded, str) else recorded
        if isinstance(parsed, dict):
            versions.update(
                {str(key): str(value) for key, value in parsed.items() if value is not None}
            )
    return versions
