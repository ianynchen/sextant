"""Reads Sextant's own catalog files from a directory (D02 §1, §6).

Structural validation lives here, at the edge, because the values reach the
derivation as bound parameters. What this cannot check is whether an engine
implements the declared `style`: that is knowledge of `application/resolve`,
which this layer must not import, so the style is checked where the engines
are — carrying `Catalog.source` so the error still names the file."""

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.domain.closed_sets import Direction, Protocol, TargetKind, TerminalKind

# The safe loader, compiled where the interpreter has the C library and pure
# Python where it does not — the same YAML subset, the same Python objects
# for every shipped catalog and shape model (`test_the_two_safe_loaders_read_
# every_shipped_catalog_identically` pins that, because the two are known to
# disagree on a few YAML 1.1 corners none of ours use). Pure Python read the
# 79 catalogs in 0.18s on EVERY analyze, whichever module was being analysed
# (docs/performance.md C).
_SAFE_LOADER: type[yaml.SafeLoader] = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def _load(text: str) -> Any:
    return yaml.load(text, Loader=_SAFE_LOADER)


class YamlCatalogSource:
    """The CatalogSource port over a directory of `*.yml` files."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def _models(self, subdirectory: str) -> dict[str, dict[str, Any]]:
        """The models one subdirectory holds, by id — `shape-models` (D02 §1b),
        `bean-models` (D02 §1c) and `step-models` (spec 2026-09-21 §5), one read
        for each.

        A SUBDIRECTORY rather than more files beside the catalogs, because a
        model is not a catalog: it declares no `style`, no `matches` and
        no boundary, and thirteen places in this repository glob
        `catalogs/*.yml` expecting every hit to be one. Keeping it out of that
        glob means none of them has to learn an exception, and the two that DO
        need it — `api._catalog_hash`, so an edit here changes the analysis
        identity, and the projection ratchet, so the wire-type table is still
        checked against the extractor — say so where they read it.

        Absent directory is an empty mapping, not an error: a repository's own
        catalog set (D02 §6) may hold no model, and a catalog naming one it
        cannot see fails in `_named_model` with the file's name attached.
        """
        directory = self._directory / subdirectory
        models: dict[str, dict[str, Any]] = {}
        for path in sorted(directory.glob("*.yml")):
            raw = _load(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise CatalogError(f"loading model {path}: not a YAML mapping")
            models[str(_required(raw, "id", path))] = raw
        return models

    def load(self) -> list[Catalog]:
        """Reads every catalog in the directory, sorted by filename.

        Raises `CatalogError` naming the file and the offending value when a
        catalog omits a required field or declares a `protocol` or `direction`
        outside D00's closed sets.
        """
        shape_models = self._models("shape-models")
        bean_models = self._models("bean-models")
        step_models = self._models("step-models")
        catalogs = []
        for path in sorted(self._directory.glob("*.yml")):
            raw = _load(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise CatalogError(f"loading catalog {path}: not a YAML mapping")
            shape = _shape_model_of(raw, shape_models, path)
            catalogs.append(
                Catalog(
                    id=_required(raw, "id", path),
                    style=_required(raw, "style", path),
                    protocol=_closed_or_absent(raw, "protocol", Protocol, path),
                    direction=_closed_or_absent(raw, "direction", Direction, path),
                    requires=tuple(raw.get("requires", [])),
                    # Spec 2026-09-21 §5: the step model's `steps` and
                    # `undeclared_steps` merged in beside the catalog's own, so
                    # the engine reads one table; `matches` as written for a
                    # catalog naming no `step_model`.
                    matches=_with_step_model(
                        _required(raw, "matches", path), raw, step_models, path
                    ),
                    source=path,
                    detect_coordinates=_coordinates(raw, path),
                    detect_satisfied_by=_detect_satisfied_by(raw, path),
                    detect_superseded_by=_detect_superseded_by(raw, path),
                    slice_outside=_slice_outside(raw, path),
                    detect_required=_detect_required(raw, path),
                    # D02 §2a — optional, and framework-specific: an envelope
                    # type a payload sits inside belongs to the framework that
                    # defines it, so `wrappers` stays on the catalog while the
                    # three payload-TYPE blocks below come from the shared
                    # model (D02 §1b).
                    wrappers=raw.get("wrappers", []),
                    # D02 §2e, §2f, §2g — the shape model's, resolved above. A
                    # catalog naming no `shape_model` and declaring none of the
                    # three still loads and contributes none, which is the
                    # state of every catalog that expands no shape.
                    nullability=shape.get("nullability", {}),
                    serialization=shape.get("serialization", {}),
                    known_types=shape.get("known_types", []),
                    # D02 §2j (W30): a top-level, optional block. Not part of the
                    # shape model — it describes what a CALLEE is, never how a payload
                    # serialises, so a catalog naming a `shape_model` still declares its
                    # own terminals.
                    terminals=_terminals(raw, path),
                    # D02 §2i — optional, one per framework family.
                    config_model=raw.get("config_model", {}),
                    # 2G design §7 — optional format vocabulary, carried
                    # through unread here for the same reason `matches` is:
                    # the values are checked against D00's format set where
                    # the ladder reads them (`resolve/format.py`), which is
                    # also where the reserved value is refused.
                    # D02's framework-contract media default, read here for
                    # the first time (2O design §2b). Checked where it is
                    # used — `derived_resource` refuses a catalog of its own
                    # style that declares none — like every other block above.
                    default_produces=tuple(raw.get("default_produces", [])),
                    format_fixed=raw.get("format_fixed", {}),
                    media_formats=raw.get("media_formats", {}),
                    json_default_markers=raw.get("json_default_markers", []),
                    parse_calls=raw.get("parse_calls", {}),
                    # 2H design §6 — optional, checked where the pass reads it
                    # (`resolve/protocol_hint.py`), which is also where the
                    # target protocol is checked against D00's closed set.
                    protocol_hint=raw.get("protocol_hint", {}),
                    # D02 §2c — optional, checked where the engine reads it
                    # (`resolve/engines/annotation_driven.py`), which is also
                    # where the resolved direction is checked against D00's
                    # closed set and the condition against the engine's own
                    # closed vocabulary.
                    resolves=raw.get("resolves", {}),
                    # D02 §1c — the bean model's mapping, resolved above the
                    # way `shape_model` is; `{}` for a catalog naming none.
                    bean_model=_named_model(raw, "bean_model", bean_models, path) or {},
                )
            )
        return catalogs


# D02 §1b. The payload-TYPE blocks, which a catalog takes from the shared shape
# model instead of declaring itself. Named here rather than inline because the
# same tuple answers two questions — which keys the model supplies, and which
# keys a catalog naming a model may not also declare — and the two must not
# drift apart.
_SHAPE_MODEL_BLOCKS = ("serialization", "nullability", "known_types")


def _shape_model_of(
    raw: dict[str, Any], models: dict[str, dict[str, Any]], path: Path
) -> dict[str, Any]:
    """The three payload-type blocks this catalog uses (D02 §1b).

    A catalog names a model and takes all three, or names none and declares
    what it declares. **It may not do both**, and that refusal is the whole
    mechanism: `A-C3` was one `known_types` entry present in thirty-three
    copies and absent from nine, and a catalog that cannot hold a copy cannot
    hold a copy that has drifted.

    A `shape_model` naming no file in `shape-models/` is refused in
    `_named_model`, which both model keys share, for the reason every other
    value in this file is: it reaches the derivation as a bound parameter, and
    a typo would silently strip a catalog of the serialisation, nullability and
    wire-type knowledge it believes it has — which is `A-C3` again, arriving
    through a misspelling instead of an omission.
    """
    model = _named_model(raw, "shape_model", models, path)
    if model is None:
        return raw
    declared = [block for block in _SHAPE_MODEL_BLOCKS if block in raw]
    if declared:
        raise CatalogError(
            f"loading catalog {path}: names `shape_model: {raw['shape_model']}` and also declares "
            f"{', '.join(declared)} — a catalog takes the shared model or declares its own, "
            f"never both. Forty-two copies of these blocks is how `A-C3` shipped (D02 §1b)"
        )
    return model


# The three keys a catalog names a model with, each to the subdirectory that holds
# the files and the section that defines it — the refusal below names both.
_MODEL_DIRECTORIES = {
    "shape_model": ("shape-models", "D02 §1b"),
    "bean_model": ("bean-models", "D02 §1c"),
    "step_model": ("step-models", "spec 2026-09-21 §5"),
}


def _with_step_model(
    matches: Any, raw: dict[str, Any], models: dict[str, dict[str, Any]], path: Path
) -> Any:
    """`matches` with the named step model's `steps` and `undeclared_steps` merged in
    (spec 2026-09-21 §5, §6) — the table of a flow definition's members is the core
    library's, shared by every broker catalog that walks a flow, and declared once.

    The UNION, not a replacement: a broker catalog declares the steps on its own
    specs (`topic`, `exchangeName`) beside the shared table. A `(owner, method,
    descriptor)` both sides declare is refused here, by file — the engine's own
    same-name check would refuse it too, but after the union has hidden which side
    wrote it. `undeclared_steps` is one block, taken from the model or written by
    the catalog and never both, the `shape_model` rule for the same reason: two
    blocks would be two claims about the same unknown member.
    """
    model = _named_model(raw, "step_model", models, path)
    if model is None:
        return matches
    if not isinstance(matches, dict):
        raise CatalogError(f"loading catalog {path}: `matches` must be a mapping")
    own = list(matches.get("steps") or [])
    shared = list(model.get("steps") or [])
    seen = {_step_identity(step) for step in own}
    twice = sorted(str(step.get("method")) for step in shared if _step_identity(step) in seen)
    if twice:
        raise CatalogError(
            f"loading catalog {path}: names `step_model: {raw['step_model']}` and also "
            f"declares its steps `{'`, `'.join(twice)}` — one owner, method and descriptor "
            f"from both sides is two entries for one overload (spec 2026-09-21 §5)"
        )
    merged: dict[str, Any] = {**matches, "steps": [*own, *shared]}
    if "undeclared_steps" in model:
        if "undeclared_steps" in matches:
            raise CatalogError(
                f"loading catalog {path}: names `step_model: {raw['step_model']}` and also "
                f"declares `undeclared_steps` — a catalog takes the model's block or writes "
                f"its own, never both (spec 2026-09-21 §5)"
            )
        merged["undeclared_steps"] = model["undeclared_steps"]
    return merged


def _step_identity(step: Any) -> tuple[str, str, str]:
    """What makes one step entry the same overload as another: its owner (a list
    spelled as one, so `[A, B]` and `[A, B]` collide and `[A]` beside `[B]` do
    not), its method and its descriptor — the engine's own match key."""
    if not isinstance(step, dict):
        return (repr(step), "", "")
    owner = step.get("owner")
    return (
        ",".join(str(name) for name in owner) if isinstance(owner, list) else str(owner),
        str(step.get("method")),
        str(step.get("descriptor")),
    )


def _named_model(
    raw: dict[str, Any], key: str, models: dict[str, dict[str, Any]], path: Path
) -> dict[str, Any] | None:
    """The model `raw[key]` names, or None when the catalog names none.

    A name matching no file is refused here for the reason every other value
    in this file is: it reaches the derivation as a bound parameter, and a typo
    would silently strip a catalog of the knowledge it believes it has — the
    serialisation, nullability and wire-type blocks for a `shape_model` (`A-C3`
    arriving through a misspelling), the whole dependency-injection vocabulary
    for a `bean_model` (every `bean_via` capture unresolved, with nothing to say
    why).
    """
    named = raw.get(key)
    if named is None:
        return None
    subdirectory, section = _MODEL_DIRECTORIES[key]
    if not isinstance(named, str) or named not in models:
        raise CatalogError(
            f"loading catalog {path}: `{key}: {named!r}` names no file in "
            f"`{subdirectory}/` — known models: {sorted(models) or 'none'} ({section})"
        )
    return models[named]


def _required(raw: dict[str, Any], key: str, path: Path) -> Any:
    if key not in raw:
        raise CatalogError(
            f"loading catalog {path}: no `{key}` — every catalog declares one (D02 §1)"
        )
    return raw[key]


def _detect_required(raw: dict[str, object], path: Path) -> bool:
    """`detect.required` — whether the coordinates are a conjunct (F2 §3.6).

    Refused unless the catalog also declares coordinates: a catalog requiring a
    dependency it does not name would gate on nothing and derive nothing, which
    is the silent-disable shape rather than a strict one.
    """
    detect = raw.get("detect") or {}
    if not isinstance(detect, dict):
        return False
    required = detect.get("required", False)
    if not isinstance(required, bool):
        raise CatalogError(f"loading catalog {path}: `detect.required` must be true or false")
    if required and not detect.get("coordinates"):
        raise CatalogError(
            f"loading catalog {path}: `detect.required: true` with no `detect.coordinates` "
            f"gates on nothing and would derive nothing at all"
        )
    return required


def _detect_satisfied_by(raw: dict[str, object], path: Path) -> tuple[str, ...]:
    """`detect.satisfied_by` — the annotations that answer the dependency
    question on their own (F2 §3.6, `Catalog.detect_satisfied_by`).

    Refused unless the catalog also declares `required`: on an ungated catalog
    the key would describe a bypass of a gate that is not there, which reads to
    the next author as a rule and is not one.

    Shape-checked here for `_coordinates`' reason — a fully-qualified name
    written wrong matches nothing while looking exactly like an annotation
    nobody wrote.
    """
    detect = raw.get("detect") or {}
    if not isinstance(detect, dict):
        return ()
    declared = detect.get("satisfied_by")
    if declared is None:
        return ()
    if not isinstance(declared, list) or not all(isinstance(v, str) and v for v in declared):
        raise CatalogError(
            f"loading catalog {path}: `detect.satisfied_by` must be a list of "
            f"fully-qualified annotation names"
        )
    if not detect.get("required"):
        raise CatalogError(
            f"loading catalog {path}: `detect.satisfied_by` without `detect.required: true` "
            f"names a bypass of a gate this catalog does not have"
        )
    for name in declared:
        if "." not in name:
            raise CatalogError(
                f"loading catalog {path}: `detect.satisfied_by` entry {name!r} is not a "
                f"fully-qualified annotation name"
            )
    return tuple(declared)


_SLICE_KINDS = ("method_names", "annotation_names", "type_names")


def _slice_outside(raw: dict[str, object], path: Path) -> tuple[dict[str, object], ...]:
    """D02's `slice.outside` (F2 §3.8), shape-checked here like every other value.

    Every entry names an `owner`, a `why`, and exactly ONE of `method_names`,
    `annotation_names` or `type_names`.

    **`method_names`, not `methods`, and the name is load-bearing.**
    `tests/architecture/test_catalog_descriptor_coverage.py` walks every catalog for
    any `methods:` key ANYWHERE and requires each row under one to declare a
    `descriptor:` — deliberately unfiltered, because "the one thing this rule must
    not do is stop seeing a row". A slice's list is bare names and not match rows, so
    reusing the key made all 109 of them read as undeclared match rows and broke that
    audit. Renaming here rather than teaching that walker an exception keeps it
    unfiltered, which is the property it exists for. The
    `why` is refused when absent rather than defaulted, because an entry without
    one records that a method is unread and not why — and "we do not model this"
    and "this is not a boundary" are different claims that a reader has to be able
    to tell apart.
    """
    declared = raw.get("slice")
    if declared is None:
        return ()
    if not isinstance(declared, dict):
        raise CatalogError(f"loading catalog {path}: `slice` must be a mapping")
    outside = declared.get("outside")
    if not isinstance(outside, list) or not outside:
        raise CatalogError(
            f"loading catalog {path}: `slice.outside` must be a non-empty list — a slice "
            f"that names nothing outside it is not a slice"
        )
    for entry in outside:
        if not isinstance(entry, dict):
            raise CatalogError(f"loading catalog {path}: each `slice.outside` entry is a mapping")
        missing = [key for key in ("owner", "why") if not entry.get(key)]
        if missing:
            raise CatalogError(
                f"loading catalog {path}: `slice.outside` entry for "
                f"{entry.get('owner', '(no owner)')!r} declares no {', '.join(missing)}"
            )
        kinds = [key for key in _SLICE_KINDS if entry.get(key)]
        if len(kinds) != 1:
            raise CatalogError(
                f"loading catalog {path}: `slice.outside` entry for {entry['owner']!r} must "
                f"declare exactly one of {', '.join(_SLICE_KINDS)} — it declares "
                f"{len(kinds)}. A method, an annotation and a type are checked against "
                f"different enumerations, so an entry naming none is unverifiable and one "
                f"naming two is ambiguous"
            )
        names = entry[kinds[0]]
        if not isinstance(names, list) or not all(isinstance(m, str) and m for m in names):
            raise CatalogError(
                f"loading catalog {path}: `slice.outside` `{kinds[0]}` must be a list of names"
            )
    return tuple(outside)


def _coordinates(raw: dict[str, Any], path: Path) -> tuple[str, ...]:
    """D02 §1's `detect.coordinates`, checked here for the reason every other
    value in this file is: it reaches a comparison against the coordinates a
    module's build declared, and a coordinate written in the wrong shape
    matches nothing while looking exactly like a framework that is absent.

    Optional, and an absent block is an empty tuple — every catalog that
    declares `detect: {coordinates: []}` says the same thing explicitly: the
    evidence for this framework is not a dependency. The value is read by the
    two styles in `resolve/dependencies.py`'s `DEPENDENCY_GATED` and by any
    catalog setting `detect.required`, so a catalog declaring coordinates that
    neither applies to is not an error; it was the state of every one of the 41
    catalogs shipping when this was written, and it is the state of 48 of
    today's 57. **This function is a SHAPE check, not the gate**: it refuses a
    coordinate written in the wrong form for all 57 and compares none of them,
    so citing it as the consumer of `detect.coordinates` would satisfy
    GUIDELINES §5.3 falsely. The consumer is `dependencies.py`'s
    `unmet_dependency`.
    """
    detect = raw.get("detect", {})
    if not isinstance(detect, dict):
        raise CatalogError(
            f"loading catalog {path}: `detect` must be a mapping with `coordinates` "
            f"— got {detect!r} (D02 §1)"
        )
    declared = detect.get("coordinates", [])
    valid = isinstance(declared, list) and all(
        isinstance(entry, str) and entry.count(":") == 1 for entry in declared
    )
    if not valid:
        raise CatalogError(
            f"loading catalog {path}: `detect.coordinates` must be a list of "
            f"`groupId:artifactId` coordinates — got {declared!r} (D02 §1)"
        )
    return tuple(declared)


def _detect_superseded_by(raw: dict[str, Any], path: Path) -> tuple[str, ...]:
    """`detect.superseded_by` — `detect.coordinates`' negative twin
    (`Catalog.detect_superseded_by`, B/C Task 10 fix round 1): the coordinates
    whose presence in the module's build means another catalog is the real
    implementation of this catalog's rule.

    Refused unless the catalog also declares `detect.coordinates` — a catalog
    that YIELDS to something must say what it is FOR, the same reason
    `detect.satisfied_by` is refused without `detect.required`. Shape-checked
    the same way `_coordinates` is: a `groupId:artifactId` written wrong
    matches nothing while looking exactly like a real coordinate.
    """
    detect = raw.get("detect") or {}
    if not isinstance(detect, dict):
        return ()
    declared = detect.get("superseded_by")
    if declared is None:
        return ()
    valid = isinstance(declared, list) and all(
        isinstance(entry, str) and entry.count(":") == 1 for entry in declared
    )
    if not valid:
        raise CatalogError(
            f"loading catalog {path}: `detect.superseded_by` must be a list of "
            f"`groupId:artifactId` coordinates — got {declared!r}"
        )
    if not detect.get("coordinates"):
        raise CatalogError(
            f"loading catalog {path}: `detect.superseded_by` without `detect.coordinates` "
            f"names what this catalog yields to without saying what it is FOR"
        )
    return tuple(declared)


def _closed_or_absent(raw: dict[str, Any], key: str, values: type[StrEnum], path: Path) -> str:
    """`protocol`/`direction`: one of D00's closed sets, or the empty string
    where the catalog declares the key at all (2O design §4).

    Absence is a CLAIM — "this catalog derives nothing with a wire identity" —
    and it is checked where the claim can be judged, not here. This layer knows
    which values are legal; it does not know which catalogs need one, because
    that is knowledge of `application/resolve`, which this layer must not
    import. `resolve/endpoints.py` refuses a catalog that MINTS ENDPOINT ROWS
    and declares no protocol, and one that mints none and declares one,
    carrying `Catalog.source` so either error still names the file — exactly
    the split the module docstring above states for `style` itself.

    A key written with a value outside the set is still refused right here: a
    typo is not an absence, and `protocol: htp` must never be read as "no wire
    identity".
    """
    if key not in raw:
        return ""
    return _closed(raw, key, values, path)


def _closed(raw: dict[str, Any], key: str, values: type[StrEnum], path: Path) -> str:
    """Checks one field against a closed set of D00 (`domain/closed_sets.py`).

    The sets are closed on purpose: adding a value is a schema change, never
    an implementation choice (NFR-5). So a value outside one is not a new
    kind of endpoint, it is a mistake, and the only place it is still cheap
    to name is the file it came from.
    """
    value = _required(raw, key, path)
    allowed = sorted(member.value for member in values)
    if value not in allowed:
        raise CatalogError(
            f"loading catalog {path}: `{key}: {value}` is not one of "
            f"{', '.join(allowed)} — D00's closed sets are closed (NFR-5)"
        )
    return str(value)


# The three ways one `terminals` rule may name a callee (D02 §2j). Exactly one
# per rule: a rule naming none reaches nothing and would sit in the catalog
# looking like a rule, and a rule naming two says two different things about
# the same answer.
_TERMINAL_ROUTES = ("owner", "supertype", "scanned_by")


def _terminals(raw: dict[str, Any], path: Path) -> list[dict[str, Any]]:
    """The `terminals` block, with every rule checked HERE (D02 §2j, W30).

    `kind` and `target` are written straight into closed columns of `call_edges`
    and out into the exported bundle, so they take the same check `protocol` and
    `direction` take and for the reason `_closed` gives: `kind: persistance`
    is not a new kind of terminal, it is a typo, and the file it came from is
    the last place naming it is cheap. Unchecked, it reached the column, the
    rendered `Reaches` cell and the bundle without a word.

    The route check is the same argument one level up. A rule naming none of
    the three matched nothing and said so nowhere; a missing `kind` raised a
    bare `KeyError` at resolve time, with no catalog path in it.
    """
    declared = raw.get("terminals", [])
    if not isinstance(declared, list):
        raise CatalogError(f"loading catalog {path}: `terminals` must be a list of rules")
    for rule in declared:
        if not isinstance(rule, dict):
            raise CatalogError(f"loading catalog {path}: each `terminals` rule must be a mapping")
        routes = [name for name in _TERMINAL_ROUTES if name in rule]
        if len(routes) != 1:
            raise CatalogError(
                f"loading catalog {path}: a `terminals` rule names "
                f"{', '.join(routes) or 'none'} — exactly one of "
                f"{', '.join(_TERMINAL_ROUTES)} is required (D02 §2j)"
            )
        _closed(rule, "kind", TerminalKind, path)
        if "target" in rule:
            _closed(rule, "target", TargetKind, path)
    return list(declared)
