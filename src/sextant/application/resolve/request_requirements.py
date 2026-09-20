"""Inbound request requirements (spec 2026-09-19 §5): the headers, query parameters and
cookies an inbound endpoint's FRAMEWORK enforces, written to `endpoint_metadata` beside the
outbound entries W29 records — three mechanisms, one writer.

1. `request_params` — parameter annotations on the handler (§5b), read off
   `endpoints.handler_signature`.
2. Route-tree predicates (§5c): Spring's `@RequestMapping(params=, headers=)` read here;
   the combinator's selector/predicate requirements arrive through the `route_requirements`
   stash the engine wrote and are joined to their rows here.
3. `request_reads` — reads in the handler body (§5d), one set-based pass over
   `effective_call_sites`.

Runs AFTER `apply_protocol_hints`: an entry names its row by the row's identity columns,
and `protocol` is final only there. `requirement` states what the framework enforces and
NULL where the code states nothing (A3).

Cost per resolve (GUIDELINES §8.7): one read of `endpoints`, one of the stash, one
`endpoint_metadata_insert` — none of them per catalog. The per-catalog mechanisms read
what the handler row already carries.
"""

import json
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.shapes.rooting import _catalog_symbol


def record_request_requirements(workspace: Workspace, catalogs: list[Catalog]) -> None:
    endpoints = [row for row in workspace.query("endpoints") if row["direction"] == "inbound"]
    rows: list[dict[str, Any]] = []
    rows.extend(_from_stash(workspace, endpoints))
    # One parse per handler across every catalog (GUIDELINES §8.7): several rows share
    # one handler, and two catalogs can own rows on the same handler.
    signatures = _Signatures()
    nullable = _nullable_spellings(catalogs)
    for catalog in catalogs:
        rows.extend(_from_parameters(endpoints, catalog, signatures, nullable))
        rows.extend(_from_mapping_attributes(endpoints, catalog, workspace))
    rows.extend(_from_reads(workspace, endpoints, catalogs))
    # An empty list writes nothing rather than a no-op statement — the
    # `record_open_questions` discipline.
    if rows:
        workspace.derive("endpoint_metadata_insert", rows=rows)


def _entry(
    endpoint: dict[str, object],
    *,
    kind: object,
    name: object,
    value: object,
    requirement: object,
    resolution: object,
    evidence: object,
) -> dict[str, Any]:
    """One `endpoint_metadata` row against an inbound endpoint: the row's own identity
    columns as they stand now, `caller` the handler (§5a)."""
    return {
        "protocol": endpoint["protocol"],
        "direction": "inbound",
        "method": endpoint["method"],
        "path": endpoint["path"],
        "caller": endpoint["handler"],
        "kind": kind,
        "name": name,
        "value": value,
        "resolution": resolution,
        "evidence": evidence,
        "requirement": requirement,
    }


def _from_stash(workspace: Workspace, endpoints: list[dict[str, object]]) -> list[dict[str, Any]]:
    """The combinator's stash joined to its rows on (caller, handler, method, path,
    catalog_id) — the columns the engine minted the route with. A stash row naming no
    live endpoint — the engine refused the route, or another catalog's row won its
    address — is dropped: an entry against a row that does not exist names nothing."""
    by_key = {
        (e["caller"], e["handler"], e["method"], e["path"], e["catalog_id"]): e for e in endpoints
    }
    out = []
    for r in workspace.query("route_requirements"):
        e = by_key.get((r["caller"], r["handler"], r["method"], r["path"], r["catalog_id"]))
        if e is not None:
            out.append(
                _entry(
                    e,
                    kind=r["kind"],
                    name=r["name"],
                    value=r["value"],
                    requirement=r["requirement"],
                    resolution=r["resolution"],
                    evidence=r["evidence"],
                )
            )
    return out


class _Signatures:
    """`handler_signature` parsed once per handler symbol and remembered: the column
    is the symbol fact's `signature` copied onto every row the handler owns, so a
    handler mapped to eight verbs is eight rows and one parse."""

    def __init__(self) -> None:
        self._parsed: dict[str, dict[str, Any] | None] = {}

    def of(self, endpoint: dict[str, object]) -> dict[str, Any] | None:
        """The handler's signature, or None where the row carries none (SQL NULL —
        `signature` is optional in D00 §5 — or JSON that is not a mapping)."""
        handler = str(endpoint["handler"] or "")
        if handler not in self._parsed:
            declared = endpoint.get("handler_signature")
            parsed = None if declared is None else json.loads(str(declared))
            self._parsed[handler] = parsed if isinstance(parsed, dict) else None
        return self._parsed[handler]


def _nullable_spellings(catalogs: list[Catalog]) -> frozenset[str]:
    """Every `nullability.nullable` spelling any loaded catalog's shape model declares
    (D02 §2e), in descriptor form — the union, because a catalog with no shape model
    carries an empty block and a `Nullable` spelling is a `Nullable` spelling whichever
    model listed it (ruled 2026-09-20). Read off the same `Catalog.nullability` field
    `shapes/expansion.py` reads, never off the YAML a second way."""
    return frozenset(
        _catalog_symbol(name)
        for catalog in catalogs
        for name in catalog.nullability.get("nullable", [])
    )


def _from_parameters(
    endpoints: list[dict[str, object]],
    catalog: Catalog,
    signatures: _Signatures,
    nullable: frozenset[str],
) -> list[dict[str, Any]]:
    """§5b, `request_params`: for each row this catalog owns, each parameter of the
    handler's signature carrying an annotation an entry names is one row — `kind` the
    entry's, `name` the first written name attribute else the parameter's own, `value`
    NULL (an annotation names a parameter, it never demands a value), `requirement`
    what `_requirement` reads. A parameter of one of the entry's `skip_types` — the
    whole-map bindings that name nothing — is skipped, and a parameter the scanner could
    not type is a miss rather than a claim."""
    entries = _request_params(catalog)
    if not entries:
        return []
    out: list[dict[str, Any]] = []
    for endpoint in endpoints:
        if endpoint.get("catalog_id") != catalog.id:
            continue
        signature = signatures.of(endpoint)
        if signature is None:
            continue
        for parameter in signature.get("parameters", []):
            erased = parameter.get("erased_symbol")
            if not erased:
                continue
            for use in parameter.get("annotations", []):
                entry = entries.get(use["annotation"])
                if entry is None or erased in entry["skip_types"]:
                    continue
                args = use.get("args") or {}
                name = _name(parameter, args, entry)
                out.append(
                    _entry(
                        endpoint,
                        kind=entry["kind"],
                        name=name,
                        value=None,
                        requirement=_requirement(parameter, args, entry, erased, nullable),
                        resolution="resolved" if name is not None else "unresolved",
                        evidence="compiler",
                    )
                )
    return out


def _name(parameter: dict[str, Any], args: dict[str, Any], entry: dict[str, Any]) -> str | None:
    """The first of `name_attrs` written as a non-empty string literal, else the
    parameter's declared name, else None — a parameter compiled without names whose
    annotation wrote none binds something it does not name (§5b)."""
    for attribute in entry["name_attrs"]:
        written = args.get(attribute)
        if isinstance(written, str) and written:
            return written
    declared = parameter.get("name")
    return declared if isinstance(declared, str) and declared else None


def _requirement(
    parameter: dict[str, Any],
    args: dict[str, Any],
    entry: dict[str, Any],
    erased: str,
    nullable: frozenset[str],
) -> str:
    """`optional` always for an `optional` entry (JAX-RS, reactive routes: absent →
    null, CP-25 rows 9–12). For `binder` — Spring's `resolveArgument` and what
    `MethodParameter.isOptional()` reads (CP-25 rows 2–3, 5), Micronaut's route match
    minus the `required` attribute (rows 6–7) — `optional` when any disjunct holds,
    else `required`:

    - `required_attr` written as the literal `false` (the literal model, D00 §5a);
    - `default_attr` present in the annotation's `args` — a written `defaultValue`
      reaches the class file, an unwritten one does not (row 5);
    - the parameter's erased type is one of the entry's `optional_types` (the
      framework's optional-value container, named on the catalog because this module
      names no language's types);
    - a DECLARATION annotation on the parameter is one of the shape model's
      `nullability.nullable` spellings — Spring's `hasNullableAnnotation()` and the
      stereotype Micronaut maps its spellings onto; the type reference's own
      `nullable` flag is NOT read, because a language whose every reference type may
      be null records `true` there by rule (D00 §5) and the binder rejects such a
      parameter all the same;
    - the parameter `declares_default` (a declared default, R1).
    """
    if entry["requirement"] == "optional":
        return "optional"
    required_attr = entry.get("required_attr")
    if required_attr is not None and args.get(required_attr) is False:
        return "optional"
    default_attr = entry.get("default_attr")
    if default_attr is not None and default_attr in args:
        return "optional"
    if erased in entry["optional_types"]:
        return "optional"
    if any(use["annotation"] in nullable for use in parameter.get("annotations", [])):
        return "optional"
    if parameter.get("declares_default") is True:
        return "optional"
    return "required"


def _request_params(catalog: Catalog) -> dict[str, dict[str, Any]]:
    """The catalog's `request_params` entries keyed by annotation descriptor, or
    empty where it declares none. Validated here, at the pass's first use, the way
    `request_body`'s block is where `shapes/contracts.py` reads it: a closed
    vocabulary, because a misspelt key read as absent turns the rule the author wrote
    into a different one silently — `requried_attr` would make every
    `required = false` parameter `required`."""
    declared = catalog.matches.get("request_params")
    if declared is None:
        return {}
    where = f"loading catalog {catalog.source}: `request_params`"
    if not isinstance(declared, list):
        raise CatalogError(f"{where} must be a list of entries, got {declared!r}")
    entries: dict[str, dict[str, Any]] = {}
    for entry in declared:
        if not isinstance(entry, dict) or not set(entry) <= _REQUEST_PARAMS_KEYS:
            raise CatalogError(
                f"{where} entries carry only {'/'.join(sorted(_REQUEST_PARAMS_KEYS))}, "
                f"got {entry!r}"
            )
        for key in ("annotation", "kind", "name_attrs", "requirement"):
            if key not in entry:
                raise CatalogError(f"{where} entry lacks `{key}`: {entry!r}")
        if entry["kind"] not in _KINDS:
            raise CatalogError(
                f"{where} `kind` must be one of {sorted(_KINDS)}, got {entry['kind']!r}"
            )
        if entry["requirement"] not in _REQUIREMENTS:
            raise CatalogError(
                f"{where} `requirement` must be one of {sorted(_REQUIREMENTS)}, "
                f"got {entry['requirement']!r}"
            )
        if not isinstance(entry["name_attrs"], list) or not all(
            isinstance(attribute, str) for attribute in entry["name_attrs"]
        ):
            raise CatalogError(f"{where} `name_attrs` must be a list of attribute names: {entry!r}")
        # The two type lists, converted once to the descriptor form the facts spell
        # (`_catalog_symbol`), and always present so the readers above index them.
        read = dict(entry)
        for key in ("optional_types", "skip_types"):
            declared_types = entry.get(key, [])
            if not isinstance(declared_types, list):
                raise CatalogError(f"{where} `{key}` must be a list of type names: {entry!r}")
            read[key] = frozenset(_catalog_symbol(str(name)) for name in declared_types)
        entries[_catalog_symbol(str(entry["annotation"]))] = read
    return entries


# Every key a `request_params` entry may carry (spec 2026-09-19 §5b). `required_attr`,
# `default_attr` are the binder's two attributes (Spring declares both, Micronaut only the
# second); `default_annotation` is JAX-RS's separate `@DefaultValue`, informational.
# `optional_types` names the binder's optional-value container and `skip_types` the
# whole-map bindings §5b skips — both TYPE names, so both live on the catalog: this
# module names no language's types (`tests/architecture/test_language_confinement.py`).
_REQUEST_PARAMS_KEYS = frozenset(
    {
        "annotation",
        "kind",
        "name_attrs",
        "requirement",
        "required_attr",
        "default_attr",
        "default_annotation",
        "optional_types",
        "skip_types",
    }
)
# D01 §3's inbound `kind` set: `param` only for an API that cannot tell query from form
# (Spring's `@RequestParam`), said on the entry.
_KINDS = frozenset({"header", "query", "cookie", "param"})
# `absent` is a route-tree word (§5c), never an annotation's: an annotation binds a value
# and cannot demand its absence.
_REQUIREMENTS = frozenset({"binder", "optional"})


def _from_mapping_attributes(
    endpoints: list[dict[str, object]], catalog: Catalog, workspace: Workspace
) -> list[dict[str, Any]]:
    """§5c, the mapping's own `params`/`headers` attributes — lands with its own task."""
    return []


def _from_reads(
    workspace: Workspace, endpoints: list[dict[str, object]], catalogs: list[Catalog]
) -> list[dict[str, Any]]:
    """§5d, `request_reads` — lands with its own task; nothing declares it yet."""
    return []
