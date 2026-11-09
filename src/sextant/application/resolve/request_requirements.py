"""Inbound request requirements (spec 2026-09-19 §5): the headers, query parameters and
cookies an inbound endpoint's FRAMEWORK enforces, written to `endpoint_metadata` beside the
outbound entries W29 records — three mechanisms, one writer.

1. `request_params` — parameter annotations on the handler (§5b), read off
   `endpoints.handler_signature`.
2. Route-tree predicates (§5c): a mapping annotation's own requirement attributes
   (`mapping.request_requirement_attrs`) read here off the effective annotation set; the
   combinator's selector/predicate requirements arrive through the `route_requirements`
   stash the engine wrote and are joined to their rows here.
3. `request_reads` — reads in the handler body (§5d), one set-based pass over
   `effective_call_sites`.

Runs AFTER `apply_protocol_hints`: an entry names its row by the row's identity columns,
and `protocol` is final only there. The stash is joined to its rows by `row_id`, never by
those columns, which the path prefix has rewritten by then (ruling 7). `requirement` states what the framework enforces and
NULL where the code states nothing (A3).

Cost per resolve (GUIDELINES §8.7): one read of `endpoints`, one of the stash, one pass
over `effective_call_sites` (already built once per load) indexed by handler, one
`endpoint_metadata_insert` — none of them per catalog. Mechanism 1 reads what the handler
row already carries; mechanism 2 walks the effective annotation set once per catalog that
declares `request_requirement_attrs` and owns an inbound row (two shipped), the same walk
`routing_conflicts` makes for the same two.
"""

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from functools import partial
from itertools import product
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.effective_calls import effective_call_sites
from sextant.application.resolve.engines.annotation_driven import effective_annotation_uses
from sextant.application.resolve.parameter_markers import Marker
from sextant.application.resolve.routing_conflicts import _discriminators
from sextant.application.resolve.shapes.arguments import _all_string_channels, _arg_at
from sextant.application.resolve.shapes.contracts import body_calls
from sextant.application.resolve.shapes.inbound_routes import (
    MARKED_TWICE,
    PATH_VARIABLE_DEFAULT,
    PATH_VARIABLE_MARKED,
)
from sextant.application.resolve.shapes.rooting import _catalog_symbol
from sextant.application.resolve.values import argument_reference
from sextant.domain.redaction import REDACTED, Redactor
from sextant.domain.symbols import bare_descriptor, names_a_type

# The redactor every ORIGIN writer of `endpoint_metadata` holds, built as
# `engines/fluent.py` and `resolve/endpoint_attributes.py` build theirs: the built-ins
# alone, because no redactor reaches a resolve pass from the composition root (`OI-71`,
# stated on `fluent`).
#
# `storage/duckdb/schema.sql`'s `value` column states the invariant — a metadata value is
# masked AT THE ORIGIN, because nothing downstream masks one and `endpoint_metadata` is in
# `workspace.py`'s export map, which exports it whole on exactly that stated ground.
# `insert_endpoint_metadata.sql`'s own header repeats the claim. This pass was violating
# it: `@GetMapping(headers = "X-Api-Key=s3cret")` is ordinary Spring input — `spring-mvc.yml`
# and `spring-web.yml` both declare `request_requirement_attrs: {params: param, headers:
# header}` — and its value reached `graph/*.parquet` verbatim.
_REDACTOR = Redactor.from_rules()


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
    columns as they stand now, `caller` the handler (§5a).

    **The value is REDACTED here, and here is the only place it can be** — the column's own
    invariant, stated above. All four mechanisms funnel through this one function, so one
    call covers the stash, the parameter annotations, the mapping attributes and the body
    reads; two of the four pass `value=None` and are untouched by construction.

    This is the NAME/VALUE PAIR `redaction.py`'s `redact_json` docstring calls *how a
    credential actually reaches this grammar*, and unlike `endpoint_attributes` there is a
    real name to key on — a header name, a query-parameter name — which is precisely what
    `redact_value` was written for. `X-Api-Key` normalizes to `xapikey`, which carries the
    built-in `apikey`, so the value masks whole.

    **A value whose NAME could not be read is masked WHOLE**, `engines/fluent.py`'s rule
    verbatim and for its reason, which holds here for the same mechanical cause: the
    combinator's stash reads both literals off a CALL ARGUMENT (`_Requirement`: `name` NULL
    where the name was not a literal), so an unread name is an unanswerable question, and
    `redact_value("", literal)` would answer it *not a secret*. A header assembled from a
    constant field beside a literal credential is exactly that shape. This differs from
    `endpoint_attributes`, where the name is absent BY CONSTRUCTION on every row and
    masking whole would destroy the whole key — there the `kind` stands in as the name.

    `resolution` is the caller's and is untouched: it is read off the value as WRITTEN, and
    a masked value is still a value that was there.
    """
    literal = value if isinstance(value, str) else None
    return {
        "protocol": endpoint["protocol"],
        "direction": "inbound",
        "method": endpoint["method"],
        "path": endpoint["path"],
        "caller": endpoint["handler"],
        "kind": kind,
        "name": name,
        "value": value
        if literal is None
        else (REDACTED if not isinstance(name, str) else _REDACTOR.redact_value(name, literal)),
        "resolution": resolution,
        "evidence": evidence,
        "requirement": requirement,
    }


def _from_stash(workspace: Workspace, endpoints: list[dict[str, object]]) -> list[dict[str, Any]]:
    """The combinator's stash joined to its rows on `row_id`, which the stash bound when it
    was written, by the columns the engine minted the route with (ruling 7). Not on those
    columns here: the path prefix has run by now and moved every prefixed row's `path`. A
    stash row naming no live endpoint — the engine refused the route, or another catalog's
    row won its address — is dropped: an entry against a row that does not exist names
    nothing."""
    by_row = {e["row_id"]: e for e in endpoints}
    out = []
    for r in workspace.query("route_requirements"):
        e = by_row.get(r["row_id"])
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
    entry's, `name` the first written name attribute else the parameter's own (NULL
    where the entry's `fallback_spelling` respells that, `_name`), `value`
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
        variables = _path_variables(endpoint["path"])
        for parameter in signature.get("parameters", []):
            erased = parameter.get("erased_symbol")
            if not erased:
                continue
            for use in parameter.get("annotations", []):
                entry = entries.get(use["annotation"])
                if entry is None or erased in entry["skip_types"]:
                    continue
                # A use with NO `args` key is one the scanner did not read — D00 §5a's
                # `unresolved: depth_limit`, where an empty `args` would be
                # indistinguishable from an annotation written with none. Nothing read,
                # nothing written: `required` here would be a claim off an attribute
                # list that was never opened.
                if "args" not in use:
                    continue
                args = use["args"]
                name = _name(parameter, args, entry)
                # A name that is one of the row's own path variables is bound from the
                # path — Vert.x's `getParam` serves both alike (CP-25 row 12) — and is
                # not a query parameter; the entry says so with `skip_path_variables`.
                if entry["skip_path_variables"] and name in variables:
                    continue
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


def _path_variables(path: object) -> frozenset[str]:
    """The variables a row's `path` declares, spelled `{name}` (`{name: regex}`, or with
    the `?`/`...` suffixes a combinator's `{id?}`/`{rest...}` carry — A6) or `:name`
    (Vert.x). The same rule §5d's `skip_path_variables` gives handler reads."""
    if not isinstance(path, str):
        return frozenset()
    return frozenset(
        name.rstrip("?.") for pattern in _PATH_VARIABLES for name in pattern.findall(path)
    )


def _name(parameter: dict[str, Any], args: dict[str, Any], entry: dict[str, Any]) -> str | None:
    """The first of `name_attrs` written as a non-empty string literal, else the
    parameter's declared name, else None — a parameter compiled without names whose
    annotation wrote none binds something it does not name (§5b).

    A declared name is refused where the entry's `fallback_spelling` respells it: the
    binder that falls back from the parameter's own name to its hyphenated form (CP-25
    row 18, `AbstractArgumentBinder.doResolve`) serves a request carrying EITHER
    spelling, so `pageSize required` would demand a name the framework does not
    require by itself — the row keeps the requirement and names nothing. Where the two
    spellings coincide (`tenant`; a header's `Tenant`, header names comparing
    case-insensitively — the framework's own `CaseInsensitiveMutableHttpHeaders`, the
    same row) the declared name stands."""
    for attribute in entry["name_attrs"]:
        written = args.get(attribute)
        if isinstance(written, str) and written:
            return written
    declared = parameter.get("name")
    if not (isinstance(declared, str) and declared):
        return None
    spelling = entry.get("fallback_spelling")
    if spelling is not None and _respelled(declared, _fallback(declared, spelling), entry["kind"]):
        return None
    return declared


def _respelled(declared: str, fallback: str, kind: str) -> bool:
    """Whether the binder's fallback names a DIFFERENT request value than the declared
    name: exact for a query parameter or cookie, case-insensitive for a header."""
    if kind == "header":
        return declared.casefold() != fallback.casefold()
    return declared != fallback


def _fallback(name: str, spelling: str) -> str:
    """The binder's second spelling of a parameter name (CP-25 row 18):
    `hyphenated` is `NameUtils.hyphenate(name)` — `hyphenate(name, true)`; and
    `hyphenated-capitalized` is `hyphenate(capitalize(name), false)`, the header
    binder's override. Both mirrored from micronaut-core 4.7.6's bytecode below."""
    if spelling == "hyphenated-capitalized":
        return _hyphenate(_capitalize(name), lower_case=False)
    return _hyphenate(name, lower_case=True)


def _capitalize(name: str) -> str:
    """`NameUtils.capitalize`: a name whose first letter is lower-case and whose second
    is upper-case is returned unchanged (`xTenant`); otherwise the first character is
    upper-cased (`contentType` → `ContentType`, `tenant` → `Tenant`)."""
    rest = name[1:]
    if name[0].islower() and rest and rest[0].isupper():
        return name
    return name[0].upper() + rest


def _hyphenate(name: str, *, lower_case: bool) -> str:
    """`NameUtils.hyphenate(String, boolean)`: a name that is already lower-case letters,
    digits and `-` starting with a letter (`isHyphenatedLowerCase`) only has `_` and
    space replaced by `-`; any other has that replacement and then `separateCamelCase`
    with `-` as the separator."""
    replaced = re.sub(r"[_ ]", "-", name)
    if _is_hyphenated_lower_case(name):
        return replaced
    return _separate_camel_case(replaced, lower_case, "-")


def _is_hyphenated_lower_case(name: str) -> bool:
    return bool(name) and all(c.islower() or c in "0123456789-" for c in name) and name[0].isalpha()


def _separate_camel_case(name: str, lower_case: bool, separator: str) -> str:
    """`NameUtils.separateCamelCase(String, boolean, char)`, both loops as compiled.
    With `lowerCase` false: an upper-case character after a non-upper-case one gets the
    separator before it and case is kept (`xTenant` → `x-Tenant`, `ContentType` →
    `Content-Type`); a `.` restarts the word. With `lowerCase` true: every letter is
    lower-cased, and an upper-case character gets the separator before it unless it
    follows an upper-case character, a `.`, or a digit that itself follows an
    upper-case character or the separator (`pageSize` → `page-size`, `apiKEY` →
    `api-key`); a run of separators collapses to one in both."""
    out: list[str] = []
    if not lower_case:
        first = True
        last = "0"
        for c in name:
            if first:
                if c != separator:
                    out.append(c)
                first = False
            elif c.isupper() and not last.isupper():
                if c != separator:
                    out.append(separator)
                out.append(c)
            else:
                if c == ".":
                    first = True
                if c != separator:
                    if last == separator:
                        out.append(separator)
                    out.append(c)
            last = c
        return "".join(out)
    first = True
    last = "0"
    second_last = separator
    for i, c in enumerate(name):
        if c.islower() or not c.isalpha():
            first = False
            if c != separator:
                if last == separator:
                    out.append(separator)
                out.append(c)
        else:
            lower = c.lower()
            if first:
                first = False
                out.append(lower)
            elif (
                last.isupper()
                or last == "."
                or (last.isdecimal() and (second_last.isupper() or second_last == separator))
            ):
                out.append(lower)
            else:
                out.append(separator)
                out.append(lower)
        if i > 1:
            second_last = last
        last = c
    return "".join(out)


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
    # A chain catalog's entries name a CALL, not an annotation (`request_param_calls`), and
    # its engine reads them off the decorators a handler passed: nothing here applies.
    if declared is None or catalog.style in _CALL_STYLES:
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
        skip_variables = entry.get("skip_path_variables", False)
        if not isinstance(skip_variables, bool):
            raise CatalogError(f"{where} `skip_path_variables` must be true or false: {entry!r}")
        if "fallback_spelling" in entry and entry["fallback_spelling"] not in _FALLBACK_SPELLINGS:
            raise CatalogError(
                f"{where} `fallback_spelling` must be one of {sorted(_FALLBACK_SPELLINGS)}, "
                f"got {entry['fallback_spelling']!r}"
            )
        # The two type lists, converted once to the descriptor form the facts spell
        # (`_catalog_symbol`), and always present so the readers above index them.
        read = dict(entry)
        read["skip_path_variables"] = skip_variables
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
# `skip_path_variables: true` is for an annotation whose read serves path and query
# parameters alike (reactive routes' `@Param`): a name that is one of the row's own path
# variables is a path parameter, not a query, and gets no row. `fallback_spelling` names
# the binder's SECOND spelling of an unwritten name — the one it retries with when the
# parameter's own name finds nothing (CP-25 row 18): a declared name the fallback respells
# is a name with two accepted spellings, and the row names nothing rather than one of them.
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
        "skip_path_variables",
        "fallback_spelling",
    }
)
# `hyphenated` is `NameUtils.hyphenate(name)`; `hyphenated-capitalized` is
# `hyphenate(capitalize(name), false)`, the header binder's override (CP-25 row 18).
_FALLBACK_SPELLINGS = frozenset({"hyphenated", "hyphenated-capitalized"})
# `{name}`, `{name: regex}`, `{name?}`, `{rest...}` — and Vert.x's `:name`.
_PATH_VARIABLES = (
    re.compile(r"\{\s*([A-Za-z_][A-Za-z0-9_]*(?:\?|\.\.\.)?)\s*(?::[^}]*)?\}"),
    re.compile(r":([A-Za-z_][A-Za-z0-9_]*)"),
)
# D01 §3's inbound `kind` set: `param` only for an API that cannot tell query from form
# (Spring's `@RequestParam`), said on the entry.
_KINDS = frozenset({"header", "query", "cookie", "param"})
# `absent` is a route-tree word (§5c), never an annotation's: an annotation binds a value
# and cannot demand its absence.
_REQUIREMENTS = frozenset({"binder", "optional"})


# The styles whose `request_params` entries name a call (design 2026-11-06-reading-decorators
# §3d, approved): a decorator's own arguments say what the parameter is.
_CALL_STYLES = frozenset({"fluent"})
# The keys such an entry carries. `required_when`, `annotated_default` and `spelling` are read
# on an entry matched on a handler parameter's markers (plan 2026-11-08-python-fastapi-inbound
# N3); a decorator's own entry (click) never writes them.
_REQUEST_PARAM_CALL_KEYS = frozenset(
    {
        "owner",
        "method",
        "kind",
        "name_arg",
        "requirement",
        "required_arg",
        "default_arg",
        "flag_arg",
        "optional_when",
        "required_when",
        "annotated_default",
        "spelling",
    }
)
# The keys of the one `unmarked` entry (N4): what a parameter carrying none of the catalog's
# marker calls is.
_UNMARKED_KEYS = frozenset({"unmarked", "kind", "requirement", "scalar_only"})
# `annotated_default`'s one word: a marker written in `Annotated` takes the parameter's own
# default (FastAPI's `field_info.default = value`).
_PARAMETER_DEFAULT = "parameter"
# `name_arg`'s rule form (D02 §1f, §2): every string the call writes positionally.
ALL_STRINGS = "all_strings"
# What a command-line parameter is (D01 §3's inbound `kind` set, design §3d, approved): a
# positional word, a named value, or a named switch that takes no value. What an HTTP request
# parameter a marker call declares is (N3), on a catalog of routes: a header, a query parameter
# or a cookie (`_PARAMETER_KINDS`).
_CALL_KINDS = frozenset({"argument", "option", "flag"})
_PARAMETER_KINDS = frozenset({"header", "query", "cookie"})
# The keys only an entry matched on a parameter's markers reads.
_MARKER_KEYS = frozenset({"required_when", "annotated_default", "spelling"})
FLAG = "flag"
# The framework's default for an entry naming a call: it rejects a command line without the
# parameter, or it does not. `binder` is an annotation word, and `absent` a route-tree one.
_CALL_REQUIREMENTS = frozenset({"required", "optional"})


def request_param_calls(catalog: Catalog) -> dict[tuple[str, str], dict[str, Any]]:
    """A chain catalog's `request_params` entries, by the `(owner, method)` of the call each
    names (design 2026-11-06-reading-decorators §3d, approved): `{owner, method, kind,
    name_arg, requirement, required_arg?, default_arg?, flag_arg?}`, each `*_arg` an argument
    reference (a position, `{keyword: name}` or `{arg: N, keyword: name}`). On a catalog of
    routes the entries name the marker calls a handler's parameters carry (plan
    2026-11-08-python-fastapi-inbound N3): `kind` a request parameter's, `default_arg` one
    reference or a list, and `required_when`, `annotated_default`, `spelling` beside them; its
    `unmarked` entry is checked here and read by `unmarked_request_param`. Validated here,
    for the reason `_request_params` gives: a misspelt key read as absent turns the rule into
    another one silently. Empty where the catalog declares none."""
    declared = catalog.matches.get("request_params")
    if declared is None:
        return {}
    where = f"loading catalog {catalog.source}: `request_params`"
    if not isinstance(declared, list):
        raise CatalogError(f"{where} must be a list of entries, got {declared!r}")
    # A catalog of commands names the decorators a command passed (click); any other names the
    # marker calls a route handler's parameters carry (N3), with their own kinds and keys.
    commands = catalog.root_kind is not None
    kinds = _CALL_KINDS if commands else _PARAMETER_KINDS
    keys = _REQUEST_PARAM_CALL_KEYS - _MARKER_KEYS if commands else _REQUEST_PARAM_CALL_KEYS
    entries: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in declared:
        if not commands and isinstance(entry, dict) and "unmarked" in entry:
            _check_unmarked(entry, where)
            continue
        if not isinstance(entry, dict) or not set(entry) <= keys:
            raise CatalogError(
                f"{where} entries that name a call carry only "
                f"{'/'.join(sorted(keys))}, got {entry!r}"
            )
        for key in ("owner", "method", "kind", "name_arg", "requirement"):
            if key not in entry:
                raise CatalogError(f"{where} entry lacks `{key}`: {entry!r}")
        if entry["kind"] not in kinds:
            raise CatalogError(
                f"{where} `kind` must be one of {sorted(kinds)}, got {entry['kind']!r}"
            )
        if entry["requirement"] not in _CALL_REQUIREMENTS:
            raise CatalogError(
                f"{where} `requirement` must be one of {sorted(_CALL_REQUIREMENTS)}, "
                f"got {entry['requirement']!r}"
            )
        for key in ("name_arg", "required_arg", "default_arg", "flag_arg"):
            if key == "name_arg" and entry[key] == ALL_STRINGS:
                continue
            # `default_arg` may name several arguments, any of which written is a default
            # (N3: `default` and `default_factory`).
            references = (
                entry[key]
                if key == "default_arg" and isinstance(entry.get(key), list)
                else [entry.get(key)]
            )
            if key in entry and (
                not references
                or any(argument_reference(each, spelled=False) is None for each in references)
            ):
                raise CatalogError(
                    f"{where} `{key}` is a position, `{{keyword: name}}` or "
                    f"`{{arg: N, keyword: name}}`, got {entry[key]!r}"
                )
        when = entry.get("optional_when")
        if when is not None and not (
            isinstance(when, dict)
            and set(when) == {"arg", "equals"}
            and argument_reference(when["arg"], spelled=False) is not None
            and isinstance(when["equals"], str | int | float | bool)
        ):
            raise CatalogError(
                f"{where} `optional_when` is `{{arg: <reference>, equals: <literal>}}`, "
                f"got {when!r}"
            )
        _check_marker_keys(entry, where)
        call = (_catalog_symbol(str(entry["owner"])), str(entry["method"]))
        if call in entries:
            raise CatalogError(f"{where} names `{entry['owner']}.{entry['method']}` twice")
        entries[call] = dict(entry)
    return entries


def request_param_rows(
    entry: Mapping[str, Any],
    arguments: list[dict[str, Any]],
    parameters: frozenset[str] | None,
) -> list[tuple[str, str | None, str | None, str]]:
    """`(kind, name, requirement, resolution)` of each input one decorator call an entry names
    declares, read off its own arguments (design 2026-11-06-reading-decorators §3d, §3f):

    - **the names.** With `name_arg` a reference, the string literal there, else NULL at
      `unresolved` (§5b's rule). With `name_arg: all_strings`, every string the call writes
      positionally (`shapes.arguments._all_string_channels`, the one reader of the rule),
      less each that is one of the handler's own `parameters`: such a string names the
      parameter the value lands in, which nobody types. Every other string is a spelling, one
      row each (an enumerable set is exact), and a positional argument not read as a string
      adds one row with no name, `unresolved`. `parameters` None is a handler that takes
      `**kwargs`: any string may name where a value lands, so none can be told to be a
      spelling, and the input is one row with no name, `unresolved`, its requirement as read;
    - **the requirement**, first answer wins: a `required_arg` written as a literal boolean
      (one written as anything else is not read, NULL); `optional_when`'s argument written
      with its value, `optional` (written with no literal value, not read, NULL); a
      `default_arg` that is written, `optional`; else the entry's default;
    - `kind` is `flag` where `flag_arg` is written as the literal `True`: the input takes no
      value."""
    names: list[str | None]
    if entry["name_arg"] == ALL_STRINGS:
        names = (
            [None]
            if parameters is None
            else [
                name
                for _, name, _ in _all_string_channels(arguments)
                if name is None or name not in parameters
            ]
        )
    else:
        names = [_literal(_arg_at(arguments, entry["name_arg"]), "string")]
    requirement = _requirement_of_call(entry, arguments)
    kind = str(entry["kind"])
    if "flag_arg" in entry and _literal(_arg_at(arguments, entry["flag_arg"]), "boolean") is True:
        kind = FLAG
    return [
        (kind, name, requirement, "resolved" if name is not None else "unresolved")
        for name in dict.fromkeys(names)
    ]


def _requirement_of_call(entry: Mapping[str, Any], arguments: list[dict[str, Any]]) -> str | None:
    """`request_param_rows`' requirement, in its order of precedence."""
    if "required_arg" in entry:
        required = _arg_at(arguments, entry["required_arg"])
        if required is not None:
            stated = _literal(required, "boolean")
            return None if stated is None else ("required" if stated else "optional")
    when = entry.get("optional_when")
    if when is not None:
        written = _arg_at(arguments, when["arg"])
        if written is not None:
            value = written.get("value") if written.get("kind") in _LITERAL_KINDS else None
            if value is None:
                return None
            if type(value) is type(when["equals"]) and value == when["equals"]:
                return "optional"
    required_when = entry.get("required_when")
    if required_when is not None:
        written = _arg_at(arguments, required_when["arg"])
        if written is not None and _is_field(written, required_when["equals_field"]):
            return "required"
    if "default_arg" in entry and any(
        _arg_at(arguments, reference) is not None for reference in _references(entry["default_arg"])
    ):
        return "optional"
    return str(entry["requirement"])


def _references(declared: Any) -> list[Any]:
    """A `*_arg` key's references: the list `default_arg` may be, else the one."""
    return list(declared) if isinstance(declared, list) else [declared]


def _is_field(argument: Mapping[str, Any], dotted: str) -> bool:
    """Whether an argument is written as the static field `dotted` names (`<owner>.<name>`, D00
    §5's `field` kind: `builtins.Ellipsis` is `...`)."""
    owner, _, name = dotted.rpartition(".")
    return argument.get("kind") == "field" and argument.get("symbol") == (
        f"{_catalog_symbol(owner)}{name}."
    )


def _check_marker_keys(entry: Mapping[str, Any], where: str) -> None:
    """The three keys an entry matched on a parameter's markers reads (N3), each in its one
    form: `required_when: {arg: <reference>, equals_field: <owner>.<name>}`, `annotated_default:
    parameter`, and `spelling: {replace: {<from>: <to>}, unless?: {arg: <reference>, equals:
    <literal>}}`."""
    when = entry.get("required_when")
    if when is not None and not (
        isinstance(when, dict)
        and set(when) == {"arg", "equals_field"}
        and argument_reference(when["arg"], spelled=False) is not None
        and isinstance(when["equals_field"], str)
        and "." in when["equals_field"]
    ):
        raise CatalogError(
            f"{where} `required_when` is `{{arg: <reference>, equals_field: <owner>.<name>}}`, "
            f"got {when!r}"
        )
    if "annotated_default" in entry and entry["annotated_default"] != _PARAMETER_DEFAULT:
        raise CatalogError(
            f"{where} `annotated_default` is `{_PARAMETER_DEFAULT}`, got "
            f"{entry['annotated_default']!r}"
        )
    spelling = entry.get("spelling")
    if spelling is None:
        return
    replace = spelling.get("replace") if isinstance(spelling, dict) else None
    unless = spelling.get("unless") if isinstance(spelling, dict) else None
    if not (
        isinstance(spelling, dict)
        and set(spelling) <= {"replace", "unless"}
        and isinstance(replace, dict)
        and replace
        and all(isinstance(key, str) and isinstance(to, str) for key, to in replace.items())
        and (
            unless is None
            or (
                isinstance(unless, dict)
                and set(unless) == {"arg", "equals"}
                and argument_reference(unless["arg"], spelled=False) is not None
                and isinstance(unless["equals"], str | int | float | bool)
            )
        )
    ):
        raise CatalogError(
            f"{where} `spelling` is `{{replace: {{<from>: <to>}}, unless?: {{arg: <reference>, "
            f"equals: <literal>}}}}`, got {spelling!r}"
        )


def _check_unmarked(entry: Mapping[str, Any], where: str) -> None:
    """The `unmarked` entry (N4), checked: `{unmarked: true, kind, requirement, scalar_only?}`,
    `kind` a request parameter's and `requirement` a call entry's."""
    if (
        not set(entry) <= _UNMARKED_KEYS
        or entry.get("unmarked") is not True
        or entry.get("kind") not in _PARAMETER_KINDS
        or entry.get("requirement") not in _CALL_REQUIREMENTS
        or not isinstance(entry.get("scalar_only", False), bool)
    ):
        raise CatalogError(
            f"{where} the `unmarked` entry is `{{unmarked: true, kind, requirement, "
            f"scalar_only?}}`, got {entry!r}"
        )


def unmarked_request_param(catalog: Catalog) -> Mapping[str, Any] | None:
    """The catalog's one `unmarked` entry (N4), or None; checked by `request_param_calls`, which
    every reader calls first. Two are refused."""
    found = [
        entry
        for entry in catalog.matches.get("request_params") or []
        if isinstance(entry, dict) and "unmarked" in entry
    ]
    if len(found) > 1:
        raise CatalogError(
            f"loading catalog {catalog.source}: `request_params` declares `unmarked` twice"
        )
    return found[0] if found else None


def body_field_requirement(
    declared: Mapping[str, Any], marker: Marker | None, parameter: Mapping[str, Any]
) -> str:
    """Whether one field of an embedded body is required (FastAPI's `analyze_param`, as for a
    request parameter): unmarked, `optional` where the parameter declares a default; marked in
    `Annotated` (`request_body.annotated_default: parameter`), the same; otherwise the marker's
    own arguments by `request_body.required_when` and `.default_arg` (`Body(None)` is
    optional, `Body()` and `Body(...)` required)."""
    defaulted = "optional" if parameter.get("declares_default") is True else "required"
    if marker is None:
        return defaulted
    if (
        marker.where == "annotation"
        and declared.get("annotated_default") == _PARAMETER_DEFAULT
        and parameter.get("declares_default") is True
    ):
        return "optional"
    entry = {
        "requirement": "required",
        **{key: declared[key] for key in ("required_when", "default_arg") if key in declared},
    }
    return str(_requirement_of_call(entry, list(marker.site.get("arguments") or [])))


# A parameter the body rule must take as bound for a reason of its own (`read_parameters`): a
# receiver, or one whose markers read differently on two paths.
BOUND = ("", "")


@dataclass(frozen=True)
class ParameterRules:
    """What an inbound `fluent` catalog reads off its handlers' parameters (N3, N4): its entries
    matched on a marker call, by `(owner, method)`; its `unmarked` entry; every call it names as
    a marker (`markers`: the entries', `request_body.marker_calls` and `.bound_by_calls`); and
    the markers that claim a parameter for something other than the path (`claims`: the
    entries' and `marker_calls`), which a path variable cannot carry."""

    entries: Mapping[tuple[str, str], Mapping[str, Any]]
    unmarked: Mapping[str, Any] | None
    markers: frozenset[tuple[str, str]]
    claims: frozenset[tuple[str, str]]


def parameter_rules(catalog: Catalog) -> ParameterRules | None:
    """The catalog's `ParameterRules`, checked at the run's start; None where it declares no
    `request_params`."""
    if catalog.matches.get("request_params") is None:
        return None
    entries = request_param_calls(catalog)
    body = body_calls(catalog, "marker_calls")
    _check_body_embedding(catalog)
    return ParameterRules(
        entries=entries,
        unmarked=unmarked_request_param(catalog),
        markers=frozenset(entries) | body | body_calls(catalog, "bound_by_calls"),
        claims=frozenset(entries) | body,
    )


def _check_body_embedding(catalog: Catalog) -> None:
    """`request_body`'s embedding keys on a catalog of routes, checked at the run's start:
    `embed_markers: {calls: [<owner>.<method>, ...], unless_subtype_of: [<type>, ...]}`, and
    the requirement keys a field reads, in a request-parameter entry's forms (`_check_marker_keys`)."""
    declared = catalog.matches.get("request_body") or {}
    where = f"loading catalog {catalog.source}: `request_body`"
    markers = declared.get("embed_markers")
    if markers is not None and not (
        isinstance(markers, dict)
        and set(markers) == {"calls", "unless_subtype_of"}
        and all(
            isinstance(markers[key], list)
            and markers[key]
            and all(isinstance(name, str) and "." in name for name in markers[key])
            for key in ("calls", "unless_subtype_of")
        )
    ):
        raise CatalogError(
            f"{where} `embed_markers` is `{{calls: [<owner>.<method>, ...], unless_subtype_of: "
            f"[<type>, ...]}}`, got {markers!r}"
        )
    _check_marker_keys(declared, where)
    if "default_arg" in declared and any(
        argument_reference(each, spelled=False) is None
        for each in _references(declared["default_arg"])
    ):
        raise CatalogError(f"{where} `default_arg` is a reference or a list of them")


@dataclass(frozen=True)
class ParameterReading:
    """What one handler's parameters demand of a request on one row (`read_parameters`): the
    rows `(kind, name, requirement, resolution)`, each parameter's marker call by declared
    index as the body rule reads it (`contracts._body_parameter`'s `calls`), the marker itself
    where one reading names it (`marked`: an embedded body field reads its arguments), and the
    reason the framework refuses the registration, or None."""

    rows: tuple[tuple[str, str | None, str | None, str], ...]
    calls: Mapping[int, tuple[str, str]]
    refused: str | None
    marked: Mapping[int, Marker] = dataclass_field(default_factory=dict)


def read_parameters(
    rules: ParameterRules,
    parameters: Sequence[Mapping[str, Any]],
    markers: Callable[[int], Sequence[Marker]],
    variables: frozenset[str],
    scalar: Callable[[Mapping[str, Any]], bool | None],
    address: str = "resolved",
) -> ParameterReading:
    """Each handler parameter as the framework reads it on one row (N3, N4; FastAPI's
    `analyze_param`, quoted in `scripts/probes/fastapi_rules.md` §4):

    - **its marker** is the call the catalog names that made its default, and the LAST one in
      its `Annotated` metadata (`fastapi_specific_annotations[-1]`), a non-marker element
      changing nothing. `markers(i)` gives each path's markers (`parameter_markers`); two
      paths are two readings, each read on its own, a row any gives written once;
    - **refused** (the route has no row): a marker in `Annotated` beside a marker default
      (`marked_twice`), one on a path variable that also has a default (`path_variable_default`)
      and a marker on a path variable that claims it for something else (`path_variable_marked`),
      in the order FastAPI asserts them. A parameter refused on one path and not another is
      read on the paths that are not;
    - **marked** with an entry's call: one row, `parameter_request_row`; where its type is a
      class (an `object`), one row of the entry's kind naming nothing at `unresolved`, since the
      class's fields are the parameters; with another marker, none (the path's `Path`, the
      body's, a dependency);
    - **unmarked**: a path variable is the address's; else the `unmarked` entry where its type
      is a scalar (`scalar_only`), optional where it declares a default, at the row's `address`
      resolution: on a path not read whole, the parameter may name one of its variables, so the
      row is no surer than the path; else nothing here (the body rule reads it).

    A receiver is no request parameter."""
    rows: dict[tuple[str, str | None, str | None, str], None] = {}
    calls: dict[int, tuple[str, str]] = {}
    marked: dict[int, Marker] = {}
    for index, parameter in enumerate(parameters):
        if parameter.get("receiver") is True:
            calls[index] = BOUND
            continue
        found = markers(index)
        defaults = {
            marker.path: marker
            for marker in found
            if marker.where == "default" and _call_of(marker) in rules.markers
        }
        annotated: dict[int, Marker] = {}
        for marker in found:
            if marker.where == "annotation" and _call_of(marker) in rules.markers:
                held = annotated.get(marker.path)
                if held is None or marker.order > held.order:
                    annotated[marker.path] = marker
        default_paths: list[Marker | None] = [*defaults.values()] or [None]
        annotation_paths: list[Marker | None] = [*annotated.values()] or [None]
        pairs = list(product(default_paths, annotation_paths))
        readings = [
            _reading(rules, parameter, default, annotation, variables, scalar, address)
            for default, annotation in pairs
        ]
        kept = [reading for reading in readings if reading[0] is None]
        winning = [
            annotation or default
            for (default, annotation), reading in zip(pairs, readings, strict=True)
            if reading[0] is None
        ]
        if len(winning) == 1 and winning[0] is not None:
            marked[index] = winning[0]
        if not kept:
            return ParameterReading(rows=(), calls={}, refused=readings[0][0])
        winners = {winner for _, winner, _ in kept}
        if winners != {None}:
            winner = winners.pop() if len(winners) == 1 else None
            calls[index] = winner if winner is not None else BOUND
        for _, _, found_rows in kept:
            rows.update(dict.fromkeys(found_rows))
    return ParameterReading(rows=tuple(rows), calls=calls, refused=None, marked=marked)


@dataclass(frozen=True)
class Dependant:
    """What the recipes a route's framework runs before its handler demand of a request (plan
    2026-11-08 N5, N6, N11): their own parameters' rows, in `read_parameters`' form, and the
    recipe bodies that run, each once, in the order they were met."""

    rows: tuple[tuple[str, str | None, str | None, str], ...]
    recipes: tuple[str, ...]


def read_dependant(
    rules: ParameterRules,
    calls: Sequence[tuple[Mapping[str, Any], tuple[str, int] | None]],
    bodies: Callable[[Mapping[str, Any], tuple[str, int] | None], Sequence[str]],
    parameters: Callable[[str], Sequence[Mapping[str, Any]] | None],
    markers: Callable[[str, int], Sequence[Marker]],
    recipe_calls: Callable[[Sequence[Marker]], Sequence[Mapping[str, Any]]],
    variables: frozenset[str],
    scalar: Callable[[Mapping[str, Any]], bool | None],
    address: str,
) -> Dependant:
    """The route's dependant flattened, as FastAPI flattens it (`get_flat_dependant`): each
    recipe call in `calls` (a handler parameter's marker, with that parameter, or a
    `dependencies=` entry, with none) names the bodies that run (`bodies`); each body's own
    parameters (`parameters`, the receiver aside) are read as a handler's are
    (`read_parameters`, on the same row's path variables and address), and each of those
    parameters' own recipe calls (`recipe_calls` over `markers`) is read in turn. A body met
    twice is read once, so a recipe that depends on itself ends. What a refused reading of a
    recipe's parameter would say is not read: the route's own reading decides refusal."""
    rows: dict[tuple[str, str | None, str | None, str], None] = {}
    ran: dict[str, None] = {}
    pending = list(calls)
    while pending:
        call, parameter = pending.pop(0)
        for body in bodies(call, parameter):
            if body in ran:
                continue
            ran[body] = None
            declared = parameters(body) or ()
            reading = read_parameters(
                rules,
                declared,
                partial(markers, body),
                variables,
                scalar,
                address,
            )
            rows.update(dict.fromkeys(reading.rows))
            for position in range(len(declared)):
                pending.extend(
                    (site, (body, position)) for site in recipe_calls(markers(body, position))
                )
    return Dependant(rows=tuple(rows), recipes=tuple(ran))


def _call_of(marker: Marker) -> tuple[str, str]:
    """A marker's call, as `(owner, method)`."""
    return (str(marker.site.get("owner")), str(marker.site["name"]))


def _reading(
    rules: ParameterRules,
    parameter: Mapping[str, Any],
    default: Marker | None,
    annotation: Marker | None,
    variables: frozenset[str],
    scalar: Callable[[Mapping[str, Any]], bool | None],
    address: str,
) -> tuple[str | None, tuple[str, str] | None, list[tuple[str, str | None, str | None, str]]]:
    """One reading of one parameter (`read_parameters`): the refusal, else None; its marker
    call, None where it has none; its rows."""
    variable = parameter.get("name") in variables
    if annotation is not None and variable and parameter.get("declares_default") is True:
        return PATH_VARIABLE_DEFAULT, None, []
    if annotation is not None and default is not None:
        return MARKED_TWICE, None, []
    marker = annotation or default
    if marker is None:
        unmarked = rules.unmarked
        if (
            variable
            or unmarked is None
            or (unmarked.get("scalar_only") is True and scalar(parameter["type"]) is not True)
        ):
            return None, None, []
        requirement = (
            "optional"
            if parameter.get("declares_default") is True
            else str(unmarked["requirement"])
        )
        return (
            None,
            None,
            [(str(unmarked["kind"]), str(parameter["name"]), requirement, address)],
        )
    call = _call_of(marker)
    if variable and call in rules.claims:
        return PATH_VARIABLE_MARKED, None, []
    entry = rules.entries.get(call)
    if entry is None:
        return None, call, []
    # A parameter of a class's type names no one value: the framework reads the class's fields
    # as the parameters (FastAPI's query, header and cookie models, `_get_flat_fields_from_
    # params`), which are not read here. One row of the entry's kind, its name and requirement
    # not read, so the row never names a parameter the request does not carry. So too for a
    # type written as text naming no type (a class defined in a function, polar's
    # `SortingGetter`): it may be such a class.
    kind = scalar(parameter["type"])
    if (kind is False and parameter["type"].get("wire_type") == "object") or (
        kind is None and not names_a_type(str(parameter["type"].get("symbol")))
    ):
        return None, call, [(str(entry["kind"]), None, None, "unresolved")]
    return None, call, [parameter_request_row(entry, marker, parameter)]


def parameter_request_row(
    entry: Mapping[str, Any], marker: Marker, parameter: Mapping[str, Any]
) -> tuple[str, str | None, str | None, str]:
    """`(kind, name, requirement, resolution)` of one parameter an entry's marker call marks (N3):

    - **the name**: the string literal at `name_arg` where it is written (NULL at `unresolved`
      where it is written as anything else), else the parameter's own name, respelled by
      `spelling` (`replace` each `from` with its `to`) unless its `unless` argument is written
      with its value — written with no literal value, the name is not read;
    - **the requirement**: a marker in `Annotated` of an `annotated_default: parameter` entry
      takes the parameter's own default, `optional` where it declares one; otherwise, and for
      a marker that is the default, `request_param_rows`' order with `required_when` before
      `default_arg`: `required` where that argument is written as the named static field."""
    arguments = list(marker.site.get("arguments") or [])
    written = _arg_at(arguments, entry.get("name_arg"))
    name: str | None
    if written is not None:
        name = _literal(written, "string")
    else:
        name = _spelled(str(parameter["name"]), entry.get("spelling"), arguments)
    if (
        marker.where == "annotation"
        and entry.get("annotated_default") == _PARAMETER_DEFAULT
        and parameter.get("declares_default") is True
    ):
        requirement: str | None = "optional"
    else:
        requirement = _requirement_of_call(entry, arguments)
    return (str(entry["kind"]), name, requirement, "resolved" if name is not None else "unresolved")


def _spelled(
    name: str, spelling: Mapping[str, Any] | None, arguments: list[dict[str, Any]]
) -> str | None:
    """A parameter's own name as an entry's `spelling` writes it on the wire (N3)."""
    if spelling is None:
        return name
    unless = spelling.get("unless")
    if unless is not None:
        written = _arg_at(arguments, unless["arg"])
        if written is not None:
            value = written.get("value") if written.get("kind") in _LITERAL_KINDS else None
            if value is None:
                return None
            if type(value) is type(unless["equals"]) and value == unless["equals"]:
                return name
    for old, new in spelling["replace"].items():
        name = name.replace(old, new)
    return name


# The literal kinds (D00 §5) an `optional_when` value is read from.
_LITERAL_KINDS = frozenset({"string", "int", "long", "float", "double", "boolean"})


def _literal(argument: Mapping[str, Any] | None, kind: str) -> Any:
    """The value of an argument written as a literal of `kind` (D00 §5), else None."""
    if argument is None or argument.get("kind") != kind:
        return None
    return argument.get("value")


def _from_mapping_attributes(
    endpoints: list[dict[str, object]], catalog: Catalog, workspace: Workspace
) -> list[dict[str, Any]]:
    """§5c, the mapping's own `params`/`headers` attributes
    (`mapping.request_requirement_attrs`, attribute → kind): every expression written on
    the handler's mapping annotation OR its type's is one row — `ParamsRequestCondition.
    combine` UNIONS the two sets, and so does this. The expressions are read exactly where
    `routing_conflicts` reads them for the conflict check — `_discriminators` over the
    EFFECTIVE annotation set, so a composed or inherited mapping's attributes count here
    as they count there — with the catalog's attribute names in the place of its
    `discriminators`. Each expression is parsed as the framework's own constructor parses
    it (`_expression`, CP-25 row 13); a header expression naming `Accept` or
    `Content-Type` is skipped (A4, CP-25 row 4: the framework routes those two into
    produces/consumes and never registers them as header conditions)."""
    attrs = _request_requirement_attrs(catalog)
    if not attrs:
        return []
    mine = [
        endpoint
        for endpoint in endpoints
        if endpoint.get("catalog_id") == catalog.id and endpoint.get("handler") is not None
    ]
    if not mine:
        return []
    annotations = effective_annotation_uses(workspace, catalog)
    mapping = {**catalog.matches["mapping"], "discriminators": sorted(attrs)}
    out: list[dict[str, Any]] = []
    # One read per handler (GUIDELINES §8.7): a verbless mapping is one handler and eight
    # rows.
    expressions_of: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {}
    for endpoint in mine:
        handler = bare_descriptor(str(endpoint["handler"]))
        if handler not in expressions_of:
            expressions_of[handler] = _discriminators(mapping, annotations, handler)
        for attribute, expressions in expressions_of[handler]:
            kind = attrs[attribute]
            for expression in expressions:
                parsed = _expression(expression)
                if parsed is None:
                    continue
                name, value, requirement = parsed
                if kind == "header" and name.lower() in _NEGOTIATION_HEADERS:
                    continue
                out.append(
                    _entry(
                        endpoint,
                        kind=kind,
                        name=name,
                        value=value,
                        requirement=requirement,
                        resolution="resolved",
                        evidence="compiler",
                    )
                )
    return out


def _expression(expression: str) -> tuple[str, str | None, str] | None:
    """`(name, value, requirement)` for one `params`/`headers` expression, parsed as
    `AbstractNameValueExpression(String)` parses it (spring-webmvc 6.1.6, CP-25 row 13):
    the FIRST `=` splits name from value; with no `=`, a leading `!` negates; with one, a
    `!` immediately before it negates. Un-negated is `required` — with the value where one
    is written, the empty string included. Negated with no value is `absent`: the
    framework refuses a request that carries the name. Negated with a value is
    `optional`: the framework serves the request whenever the value is not the one
    written, an absent name included, and the excluded value has no column (stated on
    the catalogs). None for an expression with no name — the framework constructs it and
    it can match nothing a client sends; writing it would be a nameless requirement."""
    separator = expression.find("=")
    if separator == -1:
        negated = expression.startswith("!")
        name, value = (expression[1:] if negated else expression), None
    else:
        negated = separator > 0 and expression[separator - 1] == "!"
        name = expression[: separator - 1] if negated else expression[:separator]
        value = expression[separator + 1 :]
    if not name:
        return None
    if not negated:
        return name, value, "required"
    return name, None, "absent" if value is None else "optional"


def _request_requirement_attrs(catalog: Catalog) -> dict[str, str]:
    """The catalog's `mapping.request_requirement_attrs` — attribute name → `kind` — or
    empty where the mapping declares none. Closed vocabulary, refused naming the file, as
    `request_params` is."""
    mapping = catalog.matches.get("mapping")
    if not isinstance(mapping, dict) or "request_requirement_attrs" not in mapping:
        return {}
    declared = mapping["request_requirement_attrs"]
    where = f"loading catalog {catalog.source}: `mapping.request_requirement_attrs`"
    if not isinstance(declared, dict):
        raise CatalogError(f"{where} must be a mapping of attribute name to kind, got {declared!r}")
    attrs: dict[str, str] = {}
    for attribute, kind in declared.items():
        if not isinstance(attribute, str) or not attribute:
            raise CatalogError(f"{where} keys are attribute names, got {attribute!r}")
        if kind not in _KINDS:
            raise CatalogError(f"{where} `kind` must be one of {sorted(_KINDS)}, got {kind!r}")
        attrs[attribute] = str(kind)
    return attrs


# The two header names `HeadersRequestCondition.parseExpressions` drops (A4, CP-25 row 4),
# compared case-insensitively as it compares them. Media negotiation is the endpoint row's
# own `consumes`/`produces`, never a header requirement.
_NEGOTIATION_HEADERS = frozenset({"accept", "content-type"})


def _from_reads(
    workspace: Workspace, endpoints: list[dict[str, object]], catalogs: list[Catalog]
) -> list[dict[str, Any]]:
    """§5d, `request_reads`: what each inbound row's HANDLER BODY reads off the request,
    one row per read. The entries of every loaded catalog are unioned and matched against
    every inbound row's handler — by handler, not by catalog (§5d): a framework declares
    its list once and the rows a sibling catalog derives on the same handler type get the
    same reads. A body calling another framework's read API matches that framework's
    entry too — a Spring handler taking `HttpServletRequest` gets its `getParameter`/
    `getHeader` calls recorded through the Servlet catalogs' entries, every catalog
    loading on every resolve — and the row is true: the handler reads the value,
    `requirement` NULL (CP-25 rows 16–17). A WRONG cross-framework row cannot happen,
    `owner`/`via` naming the API type the read is made on. The body is scanned ONCE per
    handler and its sites are indexed by caller ONCE for the whole pass (GUIDELINES §8.7).

    A read's `requirement` is the entry's, NULL where the entry declares none (A3: a
    bare read states that the handler reads the value and nothing about what the
    framework does without it); `then` lifts it where the read's result reaches the
    named method — the framework's own throwing accessor. A name that is not a string
    literal is a row with `name` NULL, `resolution: unresolved` (§5a). The handler body
    only, never a method it delegates to — stated on the catalogs."""
    entries = _request_reads(catalogs)
    if not entries:
        return []
    handlers = {str(e["handler"]) for e in endpoints if e.get("handler") is not None}
    if not handlers:
        return []
    by_caller: dict[str, list[dict[str, Any]]] = {}
    for site in effective_call_sites(workspace):
        caller = str(site["caller"])
        if caller in handlers:
            by_caller.setdefault(caller, []).append(site)
    out: list[dict[str, Any]] = []
    reads_of: dict[str, list[_Read]] = {}
    for endpoint in endpoints:
        handler = endpoint.get("handler")
        if handler is None:
            continue
        if str(handler) not in reads_of:
            reads_of[str(handler)] = _scan(by_caller.get(str(handler), []), entries)
        variables = _path_variables(endpoint["path"])
        for read in reads_of[str(handler)]:
            if read.skip_path_variables and read.name in variables:
                continue
            out.append(
                _entry(
                    endpoint,
                    kind=read.kind,
                    name=read.name,
                    value=None,
                    requirement=read.requirement,
                    resolution="resolved" if read.name is not None else "unresolved",
                    evidence="compiler",
                )
            )
    return out


@dataclass(frozen=True)
class _Read:
    """One matched read in a handler body, before the row's own path is consulted."""

    kind: str
    name: str | None
    requirement: str | None
    skip_path_variables: bool


def _scan(body: list[dict[str, Any]], entries: list[dict[str, Any]]) -> list[_Read]:
    """Every read in one handler body an entry names. An `owner` entry matches on the
    site's own `(owner, name, arity)`; a `via` entry on `(name, arity)` plus the site
    whose `result` is this site's `receiver` — the call that PRODUCED the value being
    read, one step (`_producing_site`), the way the combinator's `_scope_of` keys a
    body's values. `then` asks the reverse question of the matched site's own `result`:
    is it the receiver of a later call named `then.method`? `required_when_thrown` asks a
    third: does this body construct the named exception type with this read's own name
    as its first argument — the shape an INLINED throwing read leaves behind (the
    framework's `get ; ifnonnull ; new MissingRequestParameterException(name) ; athrow`
    compiled into the caller). The name must be EQUAL: a body throwing for another name
    says nothing about this read."""
    by_result: dict[int, dict[str, Any]] = {}
    receivers_of: dict[int, set[str]] = {}
    # exception type → the string literals its constructors are handed at position 0
    # in this body (`required_when_thrown`): an inlined throwing read leaves the
    # framework's own `new <Exception>(name)` in the handler, with the read's name.
    thrown_for: dict[str, set[str]] = {}
    for site in body:
        if site["result"] is not None:
            by_result.setdefault(int(site["result"]), site)
        if site["receiver"] is not None and site["name"] is not None:
            receivers_of.setdefault(int(site["receiver"]), set()).add(str(site["name"]))
        if site["name"] == "<init>" and site["arguments"]:
            first = site["arguments"][0]
            if first.get("kind") == "string" and isinstance(first.get("value"), str):
                thrown_for.setdefault(str(site["owner"]), set()).add(first["value"])
    reads: list[_Read] = []
    for site in body:
        if site["name"] is None:
            continue
        arity = len(site["arguments"])
        for entry in entries:
            if entry["method"] != site["name"] or entry["arity"] != arity:
                continue
            if "owner" in entry:
                if entry["owner"] != site["owner"]:
                    continue
            else:
                producer = (
                    None if site["receiver"] is None else by_result.get(int(site["receiver"]))
                )
                if producer is None or (producer["owner"], producer["name"]) != entry["via"]:
                    continue
            requirement = entry.get("requirement")
            then = entry.get("then")
            if (
                then is not None
                and site["result"] is not None
                and then["method"] in receivers_of.get(int(site["result"]), ())
            ):
                requirement = then["requirement"]
            argument = site["arguments"][entry["name_arg"]]
            name = argument.get("value") if argument.get("kind") == "string" else None
            if not isinstance(name, str):
                name = None
            thrown = entry.get("required_when_thrown")
            if thrown is not None and name is not None and name in thrown_for.get(thrown, ()):
                requirement = "required"
            reads.append(
                _Read(
                    kind=entry["kind"],
                    name=name,
                    requirement=requirement,
                    skip_path_variables=entry["skip_path_variables"],
                )
            )
    return reads


def _request_reads(catalogs: list[Catalog]) -> list[dict[str, Any]]:
    """Every loaded catalog's `request_reads` entries, validated and converted to the
    descriptor forms the facts spell (`owner` a type descriptor, `via` — the producing
    call, written `{ owner, method }` — an `(owner descriptor, name)` pair), in catalog
    order. Closed vocabulary, refused naming the file, for
    `request_params`' reason: a misspelt `name_args` read as absent would make every
    read nameless."""
    entries: list[dict[str, Any]] = []
    for catalog in catalogs:
        declared = catalog.matches.get("request_reads")
        if declared is None:
            continue
        where = f"loading catalog {catalog.source}: `request_reads`"
        if not isinstance(declared, list):
            raise CatalogError(f"{where} must be a list of entries, got {declared!r}")
        for entry in declared:
            entries.append(_request_read(entry, where))
    return entries


def _request_read(entry: object, where: str) -> dict[str, Any]:
    if not isinstance(entry, dict) or not set(entry) <= _REQUEST_READS_KEYS:
        raise CatalogError(
            f"{where} entries carry only {'/'.join(sorted(_REQUEST_READS_KEYS))}, got {entry!r}"
        )
    for key in ("method", "arity", "name_arg", "kind"):
        if key not in entry:
            raise CatalogError(f"{where} entry lacks `{key}`: {entry!r}")
    if ("owner" in entry) == ("via" in entry):
        raise CatalogError(f"{where} entry names exactly one of `owner`/`via`: {entry!r}")
    if entry["kind"] not in _KINDS:
        raise CatalogError(f"{where} `kind` must be one of {sorted(_KINDS)}, got {entry['kind']!r}")
    if not isinstance(entry["method"], str) or not entry["method"]:
        raise CatalogError(f"{where} `method` must be a method name: {entry!r}")
    thrown = entry.get("required_when_thrown")
    if thrown is not None and (not isinstance(thrown, str) or not thrown):
        raise CatalogError(
            f"{where} `required_when_thrown` must be an exception type name: {entry!r}"
        )
    for key in ("arity", "name_arg"):
        if not isinstance(entry[key], int) or isinstance(entry[key], bool) or entry[key] < 0:
            raise CatalogError(f"{where} `{key}` must be a non-negative integer: {entry!r}")
    if entry["name_arg"] >= entry["arity"]:
        raise CatalogError(f"{where} `name_arg` must be below `arity`: {entry!r}")
    requirement = entry.get("requirement")
    if requirement is not None and requirement not in _READ_REQUIREMENTS:
        raise CatalogError(
            f"{where} `requirement` must be one of {sorted(_READ_REQUIREMENTS)}, "
            f"got {requirement!r}"
        )
    skip_variables = entry.get("skip_path_variables", False)
    if not isinstance(skip_variables, bool):
        raise CatalogError(f"{where} `skip_path_variables` must be true or false: {entry!r}")
    then = entry.get("then")
    if then is not None and (
        not isinstance(then, dict)
        or set(then) != {"method", "requirement"}
        or not isinstance(then["method"], str)
        or then["requirement"] not in _READ_REQUIREMENTS
    ):
        raise CatalogError(
            f"{where} `then` is `{{ method, requirement }}` with a requirement in "
            f"{sorted(_READ_REQUIREMENTS)}: {entry!r}"
        )
    read: dict[str, Any] = {
        "method": entry["method"],
        "arity": entry["arity"],
        "name_arg": entry["name_arg"],
        "kind": str(entry["kind"]),
        "requirement": requirement,
        "then": then,
        "required_when_thrown": None if thrown is None else _catalog_symbol(thrown),
        "skip_path_variables": skip_variables,
    }
    if "owner" in entry:
        read["owner"] = _catalog_symbol(str(entry["owner"]))
    else:
        via = entry["via"]
        if (
            not isinstance(via, dict)
            or set(via) != {"owner", "method"}
            or not all(isinstance(part, str) and part for part in via.values())
        ):
            raise CatalogError(f"{where} `via` is `{{ owner, method }}`, got {via!r}")
        read["via"] = (_catalog_symbol(via["owner"]), via["method"])
    return read


# Every key a `request_reads` entry may carry (spec 2026-09-19 §5d). `owner` names the
# call's own type, `via` (`{ owner, method }`) the call that produced its receiver — one
# or the other. `arity` because one name can read the request and set the response at two
# argument counts (F7). `requirement` only where the API itself refuses the request;
# `then` where a later call on the read's result does (Javalin's `Validator#get()`);
# `required_when_thrown` where the throwing accessor is INLINED into the caller and only
# the exception it constructs, with the read's name, remains (Ktor's `getOrFail`).
_REQUEST_READS_KEYS = frozenset(
    {
        "owner",
        "via",
        "method",
        "arity",
        "name_arg",
        "kind",
        "requirement",
        "then",
        "required_when_thrown",
        "skip_path_variables",
    }
)
# What a read may state about the framework: `required` or `optional`, never `binder` (an
# annotation's word) and never `absent` (a route-tree word — no read API demands absence).
_READ_REQUIREMENTS = frozenset({"required", "optional"})
