"""The CatalogSource port (ARCHITECTURE §7). Catalogs are Sextant's own
framework knowledge (D02) — not the analysed module's configuration, which is
read as facts by an ArtifactReader.

A port rather than a directory argument because D02 §6 loads two sets together
and privileges neither: the catalogs shipped with Sextant, and a repository's
own. Both arrive as one list, and the layer that interprets them never learns
where they came from."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class Catalog:
    id: str
    style: str
    protocol: str
    direction: str
    requires: tuple[str, ...]
    matches: dict[str, Any]
    # Where this came from. Carried so a defect found after loading — a style
    # no engine implements — can still name the file, which is the only place
    # it is cheap to fix.
    source: Path
    # D02 §1's `detect.coordinates`: the dependency coordinates that make this
    # catalog's framework rule applicable to a module. Declared by every
    # shipped catalog since day one and read by NOTHING until 2O Task 6
    # (ruling R9, `docs/documented-not-implemented.md` entry #1) — it is read
    # here now, and consumed by the one style whose framework rule is
    # CONDITIONAL on the dependency: `derived_resource` derives an HTTP API
    # from a repository interface that names no HTTP anywhere, so applying it
    # to a module that does not declare Spring Data REST would apply a rule
    # whose precondition is unmet (2O design §2a).
    #
    # **It is deliberately NOT yet a module-wide catalog-activation gate**,
    # which is what D02 §12 describes: that would deactivate ~40 catalogs on
    # every module whose recorded coordinates do not name their framework, and
    # under Maven — where only DIRECT declarations are recorded — a module
    # declaring `spring-boot-starter-web` would lose `spring-mvc.yml`
    # outright. Making the key real for one style is what this phase's scope
    # covers; the activation gate needs a resolved classpath first, and the
    # register entry stays open until it has one.
    detect_coordinates: tuple[str, ...] = ()
    # D02 §2a, §2e, §2f, §2g. Default to empty so a catalog that declares none
    # of them — every catalog before Task 8, and the invented catalogs tests
    # construct by hand — still loads; only Task 9's wrapper unwrapping reads
    # `wrappers` today, the rest wait on Tasks 10 and 11.
    wrappers: list[dict[str, Any]] = field(default_factory=list)
    nullability: dict[str, Any] = field(default_factory=dict)
    serialization: dict[str, Any] = field(default_factory=dict)
    known_types: list[dict[str, Any]] = field(default_factory=list)
    # D02 §2i: a new top-level, optional block, one per framework family —
    # the family's base catalog carries it (Spring's ships on spring-web.yml).
    # `resolve/config.py`'s pass 2 collects every catalog's own non-empty
    # block; every other catalog's default `{}` means it contributes none.
    config_model: dict[str, Any] = field(default_factory=dict)
    # 2G design §7's format vocabulary, three optional top-level blocks read
    # only by `resolve/format.py`'s ladder. Each is shipped by the catalog
    # that OWNS the knowledge — a protocol's constant format by the catalog
    # declaring that protocol, the MIME table and the default-converter
    # markers by the family's HTTP catalogs — so no format name is ever an
    # engine's to know. Every catalog that declares none contributes none.
    #
    # `format_fixed`  -- protocol -> format, for a protocol whose wire is
    #                    constant by definition (rung 1).
    # `media_formats` -- MIME string -> format (rung 2).
    # `json_default_markers` -- markers whose presence anywhere in a module is
    #                    evidence that a JSON default converter is on the
    #                    classpath (rung 5). One flat list, two forms: a bare
    #                    string is a PACKAGE FAMILY, matched against the fqns
    #                    the module names; a `{coordinate: "group:artifact"}`
    #                    mapping is a CLASSPATH COORDINATE (2O design §7,
    #                    CP-6), matched against the coordinates this analysis
    #                    recorded. The second form exists because the framework
    #                    itself acts on the jar's mere presence — a module can
    #                    carry the converter and name none of its packages —
    #                    and both forms are checked where the ladder reads
    #                    them (`resolve/format.py`), which is where every other
    #                    format value is checked too.
    # D02's framework-contract media default (D01 §4's evidence kind (b)),
    # specified since 2E and used by nothing until 2O Task 6 (register entry
    # #6): the media type the FRAMEWORK enforces where no mapping declares one.
    # Read as a TOP-LEVEL key rather than under `mapping:` where D02 first
    # sketched it, because the catalog that finally needs it declares no
    # `mapping` at all — its rows are a framework rule, not annotation
    # attributes — and the contract belongs to the framework rather than to any
    # one annotation (D02 amended in the same commit).
    #
    # `default_consumes` stays unread: Data REST negotiates the REQUEST side
    # the way Spring MVC does, so there is still no catalog that could declare
    # one honestly, and reserving the key without a consumer is what put the
    # pair in the register in the first place.
    default_produces: tuple[str, ...] = ()
    format_fixed: dict[str, str] = field(default_factory=dict)
    media_formats: dict[str, str] = field(default_factory=dict)
    json_default_markers: list[str | dict[str, str]] = field(default_factory=list)
    # 2G design §7's fourth format vocabulary, read only by
    # `resolve/shapes/parse_binding.py`: `{bytes_payloads: [...], calls:
    # [...]}` — which payload parameter types mean "this channel carries the
    # wire's bytes, not a decoded object", and which calls turn those bytes
    # into a typed payload. Carried through unread here, like every block
    # above; the pass that reads it refuses a malformed one.
    parse_calls: dict[str, Any] = field(default_factory=dict)
    # 2H design §6's `protocol_hint` vocabulary, read only by
    # `resolve/protocol_hint.py`: `{protocol: <target>, hint_media: [...],
    # hint_returns: [...]}` — what evidence turns a row of THIS catalog's own
    # protocol into a row of another one. Carried through unread here, like
    # every block above; the pass that reads it refuses a malformed one.
    protocol_hint: dict[str, Any] = field(default_factory=dict)


class CatalogError(ValueError):
    """A catalog that cannot be trusted. An unchecked value does not stay in
    the file: it is bound straight into the derivation and published as
    `protocol` in metadata.json, where a typo is indistinguishable from an
    observation."""


class CatalogSource(Protocol):
    def load(self) -> list[Catalog]:
        """Every catalog this source holds, in a deterministic order."""
