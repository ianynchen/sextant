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
from sextant.domain.symbols import parameter_types, type_descriptor

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
            if subdirectory == "bean-models":
                _check_bean_model(raw, path)
        return models

    def server_model(self) -> list[dict[str, Any]]:
        """The SERVER's own path prefix, as configuration keys per framework and version
        (`server-models/*.yml`, spec 2026-10-18 §3).

        **Not on a catalog, because it is not a catalog's fact.** A context path belongs to
        the embedded container: a module that sets one serves every endpoint under it,
        including rows `spring-data-rest` and `spring-actuator` derive. Catalogs are flat —
        no `family:` key — so per-catalog declaration would be the same block in ten files,
        each holding a fact none of them owns, and the next catalog written would forget it
        and publish unprefixed paths with nothing failing.

        **Each row carries a framework and a VERSION RANGE because both narrower gates
        rot.** A build coordinate rots: Boot 4 renamed `spring-boot-starter-web` to
        `spring-boot-starter-webmvc`, so a gate on the old spelling is inert on
        `spring-petclinic-rest`, the one corpus that sets a prefix. A bare key rots too:
        `server.context-path` became `server.servlet.context-path` in Boot 2. Picking by the
        framework version the module actually uses is the only shape that stays correct
        rather than going quiet — ruled by the user 2026-10-18.

        Read whole and interpreted by `resolve/path_prefix.py`, as `value_model` and
        `type_model` above are read by their own consumers. Validated HERE, loudly, because
        a `.yml` under `catalogs/` is an instruction written for Sextant and a typo that
        read as "prefix nothing" would be indistinguishable from a module that configures
        none.
        """
        model: list[dict[str, Any]] = []
        for path in sorted((self._directory / "server-models").glob("*.yml")):
            raw = _load(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise CatalogError(f"loading server model {path}: not a YAML mapping")
            entries = raw.get("prefixes")
            if not isinstance(entries, list):
                raise CatalogError(f"loading server model {path}: `prefixes` must be a list")
            for entry in entries:
                required = {"framework", "versions", "measured", "keys", "protocols"}
                if not isinstance(entry, dict) or not required <= set(entry):
                    raise CatalogError(
                        f"loading server model {path}: each entry is a mapping with "
                        f"`framework`, `versions`, `measured` — the versions whose own "
                        f"metadata was read (§5.4) — `keys` and `protocols`, got {entry!r}"
                    )
                keys = entry["keys"]
                protocols = entry["protocols"]
                measured = entry["measured"]
                for name, value in (
                    ("keys", keys),
                    ("protocols", protocols),
                    ("measured", measured),
                ):
                    if not isinstance(value, list) or not value:
                        raise CatalogError(
                            f"loading server model {path}: `{name}` must be a non-empty list, "
                            f"got {value!r}"
                        )
                model.append(
                    {
                        "framework": str(entry["framework"]),
                        "versions": str(entry["versions"]),
                        "measured": [str(one) for one in measured],
                        # ORDERED: the keys compose left to right.
                        "keys": [str(key) for key in keys],
                        "protocols": [str(one) for one in protocols],
                    }
                )
            # **The per-package prefix declaration** (spec 2026-10-18 §4), a sibling block
            # rather than another `prefixes` entry: it names framework SYMBOLS instead of
            # configuration keys, so one shape would have to carry two unrelated sets of
            # required fields. Validated with the same loudness for the same reason.
            installed = raw.get("class_path_prefixes")
            if installed is not None:
                required = {
                    "framework",
                    "measured",
                    "protocols",
                    "installer",
                    "entry",
                    "matcher",
                    "package_of",
                    "package_name",
                    "annotation_test",
                }
                if not isinstance(installed, dict) or not required <= set(installed):
                    raise CatalogError(
                        f"loading server model {path}: `class_path_prefixes` is a mapping with "
                        f"{sorted(required)} — `package_of`/`package_name` being the pair that "
                        f"tells a package predicate from any other match — got {installed!r}"
                    )
                # The two LISTS are validated as lists, not merely as present: a string
                # where a list belongs iterates into its characters, and `protocols: http`
                # would then match no protocol and silence the whole reader rather than
                # failing. Loudly here is the only place it can be caught (§13.6).
                for named in ("measured", "protocols"):
                    if not isinstance(installed[named], list) or not installed[named]:
                        raise CatalogError(
                            f"loading server model {path}: `class_path_prefixes.{named}` is a "
                            f"non-empty list, got {installed[named]!r}"
                        )
                model.append(
                    {
                        "installed": True,
                        "framework": str(installed["framework"]),
                        "measured": [str(one) for one in installed["measured"]],
                        "protocols": [str(one) for one in installed["protocols"]],
                    }
                    | {
                        named: _declared_method(installed[named], f"{path}: `{named}`")
                        for named in (
                            "installer",
                            "entry",
                            "matcher",
                            "package_of",
                            "package_name",
                            "annotation_test",
                        )
                    }
                )
        return model

    def type_model(self) -> list[dict[str, Any]]:
        """Which types may stand where another is declared (`type-models/*.yml`).

        A `single_call` row's own `descriptor` says what type it accepts at its
        destination position, and a producing call says what it returns. The LANGUAGE
        separates two overloads by exactly that — name and parameter types in order — so a
        producer
        whose return type cannot be the declared type did not produce that value, and a
        destination read through it is a wrong row at `resolved`.

        **It is declared rather than scanned, and that is measured rather than
        preferred.** `type_hierarchy` records what a class in the module under analysis
        extends; the types here are in the JDK and in dependency jars, so it carries no
        row for any of them — zero across every corpus, with two fixtures holding an
        empty table. A dependency becomes readable only under `extract_libraries` and the
        JDK never does, so reading conformance from the scan would make a destination
        resolve or not depending on a scan option: one source tree, two answers. §8.2
        refuses that shape, and a declared table answers the same either way.

        Entries are `{subtype, supertype, by}` and the relation is CONFORMANCE, not
        `extends`: one shipped collection interface reaches its supertype through an
        intermediate interface on the platform version this repo builds with, and directly
        on an older one, so an edge is version-scoped where the relation is not. `by` carries the `javap` that measured it (§8.1, §7b).
        """
        model: list[dict[str, Any]] = []
        for path in sorted((self._directory / "type-models").glob("*.yml")):
            raw = _load(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise CatalogError(f"loading type model {path}: not a YAML mapping")
            entries = raw.get("conformance")
            if not isinstance(entries, list):
                raise CatalogError(f"loading type model {path}: `conformance` must be a list")
            for entry in entries:
                if not isinstance(entry, dict) or not {"subtype", "supertype", "by"} <= set(entry):
                    raise CatalogError(
                        f"loading type model {path}: each entry is a mapping with "
                        f"`subtype`, `supertype` and `by` — the measurement behind it, "
                        f"never a recollection (§8.1) — got {entry!r}"
                    )
                model.append(
                    {
                        "subtype": str(entry["subtype"]),
                        "supertype": str(entry["supertype"]),
                        "by": str(entry["by"]),
                    }
                )
        return model

    def value_model(self) -> list[dict[str, Any]]:
        """The identity of every PRODUCING call this source knows (spec 2026-09-22 §2,
        D02 §1f): which argument of a call carries the value its result stands for.

        Two declaration sites, one table. The entries `value-models/*.yml` declares come
        first, then every hop declaration already written on a catalog (`_HOP_KEYS`, four
        of them), HOISTED — the same three fields saying the same thing, so no catalog
        edit is forced and nothing changes behaviour (§2a step 1).

        **Declared first, and that ordering is a reading convenience rather than a safety
        property.** It decides which entry a reader meets first and which `by` travels
        beside it. It excludes nothing: `_matching_keys` includes `arity` and `descriptor`,
        so a discriminated entry and a bare one COEXIST, and a site the discriminated one
        turns away still matches the bare one. The estate HAD one such disagreement — an
        overload discriminator two consuming catalogs declared and three did not, where the
        bare entry also matched overloads whose argument 0 is something else entirely — and
        what closed it was editing those three catalogs so the bare spelling no longer
        exists, not the order of this list. `value-models/jdk.yml` records the measurement
        that settled it.

        Deduplicated by what an entry MATCHES on (`_matching_keys`, so a declared entry and
        the hoisted catalog spelling of the same producer are one entry, the declared one),
        and otherwise in declaration order — `value-models/` by
        filename, then the catalogs by filename and document order — so two runs over one
        directory build one table (NFR-1). Twelve rows of one shipped catalog carry the
        same pair of entries between them, and twelve copies of one identity is the
        once-per-consumer shape this table exists to end.

        **`load` calls this and hands the result to every catalog it builds** (Task 7,
        spec §3c's first migration): the walk resolves through it, so it has to reach the
        engines, and `Catalog.value_model` is where they read it. It still re-reads the
        directory rather than sharing `load`'s parse, so that the hoist stays one
        self-contained read Task 10 can narrow without touching the catalog loop; `load`'s
        own call is where what that costs is measured.
        """
        model: list[dict[str, Any]] = []
        # Which file declared each entry, kept so two files claiming one producer are
        # refused by name below rather than resolved by `sorted(glob)`: the loser would
        # vanish silently, and with it the `by` that was its whole justification (§7b).
        declared_in: dict[tuple[tuple[str, Any], ...], tuple[str, Path]] = {}
        for path in sorted((self._directory / "value-models").glob("*.yml")):
            raw = _load(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise CatalogError(f"loading value model {path}: not a YAML mapping")
            model_id = str(_required(raw, "id", path))
            for entry in _identities(raw, path):
                seen_in = declared_in.get(_matching_keys(entry))
                if seen_in is not None:
                    raise CatalogError(
                        f"loading value model {path}: `{model_id}` declares the identity "
                        f"{_matching_keys(entry)} that `{seen_in[0]}` ({seen_in[1].name}) "
                        f"already declares — one producer is declared once, and two entries "
                        f"citing two probes would leave whichever file sorts first (D02 §1f)"
                    )
                declared_in[_matching_keys(entry)] = (model_id, path)
                model.append(entry)
        for path in sorted(self._directory.glob("*.yml")):
            raw = _load(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                _hoisted(raw, path, model)
        deduplicated: list[dict[str, Any]] = []
        seen: set[tuple[tuple[str, Any], ...]] = set()
        for entry in model:
            if (identity := _matching_keys(entry)) not in seen:
                seen.add(identity)
                deduplicated.append(entry)
        return deduplicated

    def load(self) -> list[Catalog]:
        """Reads every catalog in the directory, sorted by filename.

        Raises `CatalogError` naming the file and the offending value when a
        catalog omits a required field or declares a `protocol` or `direction`
        outside D00's closed sets.
        """
        shape_models = self._models("shape-models")
        bean_models = self._models("bean-models")
        step_models = self._models("step-models")
        # Once, here, and handed to every catalog: an identity is declared once per
        # PRODUCER (spec §2), so it belongs to the source rather than to any one file.
        # It re-reads the directory this loop is about to read — measured at 26 ms for the
        # 101 shipped catalogs against 29 ms for `load` itself, on a resolve that takes
        # 0.8 s — and that buys the two readings staying independent, which is what lets
        # Task 10 delete the hop keys from the catalogs without touching this loop.
        identities = self.value_model()
        # The conformance table, read once per source for the same reason: it is
        # knowledge about TYPES rather than about any one catalog, and the engines need
        # it to refuse a producer whose return type cannot be the declared parameter
        # type (GUIDELINES §8.1 — the language tells two overloads apart by their parameter
        # types, and mirroring a language's own rule is not optional).
        conformance = self.type_model()
        servers = self.server_model()
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
                    format_any=bool(raw.get("format_any", False)),
                    # The reactor-linking spec, 2026-10-19 — optional, and checked
                    # where the system tier reads it rather than here, like every
                    # other block above. A plain string: it is one key name, and a
                    # catalog declaring several would be claiming a module registers
                    # under more than one name, which no framework here does.
                    participant_name_key=raw.get("participant_name_key"),
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
                    # D02 §1f — the source's own identity table, built above.
                    value_model=identities,
                    # The source's own type-conformance table, built above.
                    type_model=conformance,
                    # The server's own prefix keys, built above.
                    server_model=servers,
                )
            )
        return catalogs


# Spec 2026-09-22 §2a step 1. The keys a catalog already spells a producer's identity
# with, each hoisted into the shared table. `channel_via` and `url_via` name the producing
# call outright; the two WRAPPER keys name a TYPE and an argument of its constructor, so
# the method is `<init>` — the same three fields, one spelling along. Named here rather
# than inline because Task 10 deletes these keys and refuses them, and the deletion has to
# be able to find every one of them from the list that read them.
#
# **`record_wrappers` is the fourth, and the spec's §2a enumeration omitted it** (ruled
# 2026-09-23; the spec's own §0 row is amended). It is `{type, <name>_ctor_arg}`, the same
# shape as `call_wrappers`, and its three shipped occurrences are byte-identical entries
# for one producer — which is the duplication "declared once per producer" exists to end,
# so leaving it out would have skipped the hoist's clearest case. The undercount was
# already visible elsewhere in the spec: the migration table's "13 catalogs" for
# `single_call` only reaches 13 because it counts the three that declare this key.
_HOP_KEYS = ("channel_via", "url_via", "call_wrappers", "record_wrappers")

# The two of them whose entry names a type rather than a call.
_WRAPPER_KEYS = ("call_wrappers", "record_wrappers")

# A wrapper entry's position: `payload_ctor_arg: 0`, `channel_ctor_arg: 0` — the suffix is
# what distinguishes a constructor slot from an index into a type reference's own type
# arguments, which is what a bare `payload_arg` beside a `type` is everywhere else in the
# catalogs (`resolve/shadow.py` measures both populations and says which is which).
_CTOR_ARG = "_ctor_arg"


def _declared_method(declared: object, where: str) -> dict[str, Any]:
    """A `{type, method}` pair as a projected call site's own two columns: `{"owners": (…),
    "name": …}`.

    `type` may name one type, several, or none at all, and the three mean different things:

    * ONE — the ordinary case, and an exact match on the site's owner.
    * SEVERAL — one API reachable under two names. The servlet and reactive
      `RequestMappingHandlerMapping` are two unrelated classes carrying the same
      `setPathPrefixes`, and a reader that named one would silently skip the other stack
      (`catalog_symbols` takes scalar-or-list for the same reason, in the catalogs proper).
    * NONE — the owner is deliberately unconstrained, because the author's choice of static
      type is not what identifies the call. `Map#put` against `LinkedHashMap#put` is the
      case: javac emits whichever the variable was declared as, and what identifies a prefix
      entry is the MAP it writes into, not how the variable was spelled.

    The catalog writes types DOTTED, as every catalog does, and the conversion happens here:
    `type_descriptor` is the seam, and a `#` written into a catalog by hand is that seam
    skipped rather than applied
    (`tests/architecture/test_source_rules.py::test_catalogs_use_one_fqn_notation`).
    """
    if not isinstance(declared, dict) or not isinstance(declared.get("method"), str):
        raise CatalogError(
            f"loading server model {where} names a method as `{{type, method}}` with the type "
            f"dotted, got {declared!r}"
        )

    types = declared.get("type")
    named = [types] if isinstance(types, str) else types if isinstance(types, list) else []
    if types is not None and not (named and all(isinstance(one, str) for one in named)):
        raise CatalogError(
            f"loading server model {where} names `type` as one dotted type or a list of "
            f"them, got {types!r}"
        )
    return {
        "owners": tuple(type_descriptor(str(one)) for one in named),
        "name": str(declared["method"]),
    }


def _identities(raw: dict[str, Any], path: Path) -> list[dict[str, Any]]:
    """One `value-models/` file's `identified_by` entries, shape-checked here (D02 §1f).

    `owner` is OPTIONAL (spec §5a): Go's `nats.Connect(url)` and Python's
    `boto3.client("sqs")` are free functions, and `domain/symbols.owner_of` already
    documents that an ownerless symbol is an answer here, never an exception. Requiring one
    would bake OO into a model the fact grammar does not have.

    `by` is REQUIRED, and it is the rule §7b names: `value-models/` becomes a dumping
    ground otherwise — entries accumulate because adding one is easy, and nobody measures
    whether the framework really identifies that value that way. Refused at the edge, as a
    SHAPE, the way every other value in this file is; that the path names a committed probe
    which states what it measured against is checked where it can be — over the SHIPPED
    files, in `tests/architecture/test_value_model_probe_rows.py`, exactly as a `measured:`
    row's `by` is. A repository's own catalog set (D02 §6) cites its own probes, which are
    not in this tree, so this layer checks that one is cited and never where it lives.
    """
    declared = raw.get("identified_by")
    if declared is None:
        return []
    if not isinstance(declared, list) or not declared:
        raise CatalogError(
            f"loading value model {path}: `identified_by` must be a non-empty list — a "
            f"value model that identifies nothing is not a model (D02 §1f)"
        )
    entries: list[dict[str, Any]] = []
    for entry in declared:
        if not isinstance(entry, dict):
            raise CatalogError(
                f"loading value model {path}: each `identified_by` entry is a mapping"
            )
        # `arg` OR `from_receiver`, never neither and never both. The second form says the
        # result stands for whatever the RECEIVER stands for, which is what a chain like
        # `getInstances(name).get(0).getUri()` needs and what a model built only out of
        # positions cannot say (`OI-142`). Refusing BOTH is not pedantry: an entry carrying
        # each would be two different claims about one call, and nothing downstream could
        # say which the author meant.
        has_arg, from_receiver = "arg" in entry, entry.get("from_receiver")
        if has_arg and from_receiver is not None:
            raise CatalogError(
                f"loading value model {path}: `identified_by` entry {entry!r} declares BOTH "
                f"`arg` and `from_receiver` — one says which of this call's own positions "
                f"carries the value, the other says it carries whatever its receiver does, "
                f"and an entry claiming each is two claims about one call"
            )
        if from_receiver is not None and from_receiver is not True:
            raise CatalogError(
                f"loading value model {path}: `identified_by` entry {entry!r} declares "
                f"`from_receiver: {from_receiver!r}` — the only value is `true`, because the "
                f"key is a claim and not a setting"
            )
        required = ("method", "by") if from_receiver else ("method", "arg", "by")
        missing = [key for key in required if key not in entry]
        if missing:
            raise CatalogError(
                f"loading value model {path}: `identified_by` entry {entry!r} declares no "
                f"{', '.join(missing)} — `owner` is optional (spec §5a: a free function is an "
                f"answer, not an error), `method` with either `arg` or `from_receiver` says "
                f"where the value comes from, and `by` is the probe row behind the claim (§7b)"
            )
        # WHAT KIND of thing the identity yields — a closed pair, so a typo is a refusal
        # rather than a silent `address`. Almost every entry yields a whole address and
        # says nothing; a service-discovery lookup yields only the AUTHORITY (who is being
        # called, with no scheme and no path), and nothing about the resolved STRING could
        # tell the two apart: `customers-service` and `/api/v1` both lack a scheme, and
        # reading either as the other publishes a wrong column at `resolved` (`OI-142`).
        yields = entry.get("yields")
        if yields is not None and yields not in ("address", "authority"):
            raise CatalogError(
                f"loading value model {path}: `identified_by` entry {entry!r} declares "
                f"`yields: {yields!r}` — the only values are `address` (the default, a whole "
                f"URL) and `authority` (who is being called, with no scheme and no path)"
            )
        if not isinstance(entry["by"], str) or not entry["by"]:
            raise CatalogError(
                f"loading value model {path}: `identified_by` entry {entry!r} declares a `by` "
                f"that is not a probe document's path"
            )
        entries.append(_identity(entry, entry.get("owner")))
    return entries


def _matching_keys(entry: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    """What makes one identity entry the same claim as another: everything it matches on.

    `by` is left out, and that is the whole point of the helper. It is PROVENANCE — where
    the claim was measured — not part of the claim, so a declared entry and the hoisted
    catalog spelling of the same producer are one entry and not two. Deduplicated the other
    way round, the shipped table would list that producer twice — once with its probe and
    once without — and a reader counting producers would count it twice.
    """
    return tuple(sorted((key, value) for key, value in entry.items() if key != "by"))


def _identity(entry: dict[str, Any], owner: Any) -> dict[str, Any]:
    """One entry with its `owner` converted to the SCIP symbol form the facts carry
    (`domain/symbols.type_descriptor`), and every other key verbatim.

    Converted HERE rather than where the walk reads it for the reason the engines already
    convert a catalog's owners once at run start: the catalogs stay readable in their own
    dotted notation, the facts stay one grammar, and the comparison happens against a
    string that was built once. An entry with no `owner` keeps none.
    """
    if owner is None:
        return dict(entry)
    return {**entry, "owner": type_descriptor(owner)}


def _hoisted(node: Any, path: Path, into: list[dict[str, Any]]) -> None:
    """Every hop declaration anywhere in one catalog document, as identity entries.

    Anywhere, because the three keys are not at one depth: `url_via` sits on a `fluent`
    root, a step and a terminal; `channel_via` on a `single_call` method row and on an
    `interface_implementation` entry; `call_wrappers` is a block of `matches`. A walk of the
    whole document reads all of them without this layer learning any style's shape — which
    is also what keeps it reading them after Task 10 has deleted the ones it can.
    """
    if isinstance(node, list):
        for entry in node:
            _hoisted(entry, path, into)
        return
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        if key not in _HOP_KEYS:
            _hoisted(value, path, into)
            continue
        if not isinstance(value, list):
            raise CatalogError(f"loading catalog {path}: `{key}` must be a list of entries")
        for entry in value:
            if not isinstance(entry, dict):
                raise CatalogError(f"loading catalog {path}: each `{key}` entry is a mapping")
            if key in _WRAPPER_KEYS:
                into.extend(_constructor_identities(entry, key, path))
            else:
                into.append(_identity(entry, entry.get("owner")))


def _constructor_identities(entry: dict[str, Any], key: str, path: Path) -> list[dict[str, Any]]:
    """A wrapper entry as identity entries — one per `<name>_ctor_arg` it declares.

    The producer is the wrapper type's constructor, so the owner is that type and the
    method is `<init>`: `{type: HttpEntity, payload_ctor_arg: 0}` says `new HttpEntity(x)`
    stands for `x`, which is what `{owner, method, arg}` says in the other two keys.

    ONE ENTRY PER POSITION, not one per wrapper, and the shipped `record_wrappers` blocks
    are why: each declares `channel_ctor_arg` and `payload_ctor_arg` on one constructor,
    which is two claims about two arguments of the same producer. `last` is carried
    verbatim, as `all_strings` is — a rule resolved per site, never an index this layer
    could evaluate. Sorted by key name so an entry declaring two positions hoists in one
    order on every run.

    **EACH CARRIES ITS ROLE, and the role is read off the key's own prefix.** Two
    positions of one constructor are not interchangeable — one is the destination and one
    is the payload — and a pair of role-free entries cannot say which is which. The
    prefix before `_ctor_arg` already IS the role in every shipped spelling, so no
    vocabulary is invented here, no framework is named, and a wrapper that one day
    declares a third role works without touching this function. It matters because Task 10
    deletes these blocks: after that, the table is the only record of the pairing, and a
    table with no field for it would lose the distinction at exactly the moment the
    declaration that carried it goes.

    **The `_via` keys deliberately get NO role**, and the difference is not an omission.
    A `channel_via`/`url_via` entry names ONE position, and the consuming row already
    declares what that position means — the loader refuses a `channel_via` without a
    `channel_arg`/`url_arg` beside it, and Task 10 deletes the `_via` entry while leaving
    that meaning where it is. Stamping a role on those entries would also put the
    CONSUMER's meaning on the PRODUCER, which §1e forbids in as many words: one shipped
    producer's argument 0 is read as an address by two catalogs and as a destination by
    three, so a role there would split one producer into two entries and make the
    once-per-producer declaration impossible to write.

    `descriptor` is carried through where the entry declares one (CP-34): it is the only
    thing that tells two constructors of one type apart, so dropping it would merge
    measured overloads that disagree about where the payload is.
    """
    wrapper = entry.get("type")
    positions = sorted(name for name in entry if str(name).endswith(_CTOR_ARG))
    if not isinstance(wrapper, str) or not positions:
        raise CatalogError(
            f"loading catalog {path}: a `{key}` entry names a `type` and at least one "
            f"`<name>{_CTOR_ARG}` — got {entry!r}"
        )
    declared = (
        {"descriptor": entry["descriptor"]} if isinstance(entry.get("descriptor"), str) else {}
    )
    return [
        {
            "owner": type_descriptor(wrapper),
            "method": "<init>",
            **declared,
            "role": str(position)[: -len(_CTOR_ARG)],
            "arg": entry[position],
        }
        for position in positions
    ]


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


def _step_identity(step: Any) -> tuple[frozenset[str], str, str | None]:
    """What makes one step entry the same overload as another, as the engine
    matches it: its owners as a SET (`[A, B]` and `[B, A]` are one owner set),
    its method, and its descriptor's PARAMETER portion (a return type is not
    method identity — `fluent._same_overload`'s rule). A descriptor not spelled
    as one is compared as written; the engine refuses it by file."""
    if not isinstance(step, dict):
        return (frozenset({repr(step)}), "", None)
    owner = step.get("owner")
    owners = (
        frozenset(str(name) for name in owner)
        if isinstance(owner, list)
        else frozenset({str(owner)})
    )
    descriptor = step.get("descriptor")
    parameters = (
        parameter_types(descriptor)
        if isinstance(descriptor, str) and ")" in descriptor
        else (None if descriptor is None else str(descriptor))
    )
    return (owners, str(step.get("method")), parameters)


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


_CONDITION_KINDS = ("profile", "property", "other")


def _check_bean_model(raw: dict[str, Any], path: Path) -> None:
    """Refuses a malformed `conditions` or `presence` block of a bean model — or a malformed
    `stereotypes` / `configuration_annotation` / `stereotype_name_attrs` — naming the file
    (spec 2026-10-22 conditional-beans §2a). What the resolve pass reads from them is a
    framework rule, so every entry carries the probe that measured it (`by:`): a rule nobody
    measured is a guess, and a typo here would silently strip every bean of its condition."""
    where = f"loading model {path}"
    if "conditions" in raw:
        declared = raw["conditions"]
        if not isinstance(declared, dict):
            raise CatalogError(
                f"{where}: `conditions` must be a mapping of kind to entry, got {declared!r}"
            )
        for kind, entry in declared.items():
            if kind not in _CONDITION_KINDS or not isinstance(entry, dict):
                raise CatalogError(
                    f"{where}: `conditions.{kind}`: the kinds are `profile`, `property` and "
                    "`other`, each a mapping"
                )
            if kind == "other":
                names = entry.get("annotations")
                if not isinstance(names, list) or not names or not entry.get("by"):
                    raise CatalogError(
                        f"{where}: `conditions.other` needs `annotations` (a list) and a `by:` probe"
                    )
            elif not isinstance(entry.get("annotation"), str) or not entry.get("by"):
                raise CatalogError(
                    f"{where}: `conditions.{kind}` needs `annotation` and a `by:` probe"
                )
    if "presence" in raw:
        presence = raw["presence"]
        strings = ("missing", "present", "order_reason")
        lists = ("type_attrs", "name_attrs", "annotation_attrs")
        if (
            not isinstance(presence, dict)
            or not all(isinstance(presence.get(key), str) for key in strings)
            or not all(isinstance(presence.get(key), list) for key in lists)
            or not presence.get("by")
        ):
            raise CatalogError(
                f"{where}: `presence` needs `missing` and `present` (annotation names), "
                "`type_attrs`, `name_attrs` and `annotation_attrs` (lists), `order_reason` "
                "and a `by:` probe"
            )
    # Which classes are beans at all (CP-44 row 5): an empty or malformed list would make
    # every scanned class unconditional without a word, the failure the blocks above refuse.
    if "stereotypes" in raw:
        stereotypes = raw["stereotypes"]
        if (
            not isinstance(stereotypes, list)
            or not stereotypes
            or not all(isinstance(name, str) and name for name in stereotypes)
        ):
            raise CatalogError(
                f"{where}: `stereotypes` must be a non-empty list of annotation names, "
                f"got {stereotypes!r}"
            )
    if "configuration_annotation" in raw:
        configuration = raw["configuration_annotation"]
        if not isinstance(configuration, str) or not configuration:
            raise CatalogError(
                f"{where}: `configuration_annotation` must be one annotation name, "
                f"got {configuration!r}"
            )
    # The attribute naming a scanned bean, per stereotype (CP-44 row 6): a malformed entry
    # would give every scanned class its default name, read as decided.
    if "stereotype_name_attrs" in raw:
        naming = raw["stereotype_name_attrs"]
        if not isinstance(naming, dict) or not all(
            isinstance(name, str) and name and isinstance(attr, str) and attr
            for name, attr in naming.items()
        ):
            raise CatalogError(
                f"{where}: `stereotype_name_attrs` must map each annotation name to one "
                f"attribute, got {naming!r}"
            )


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
