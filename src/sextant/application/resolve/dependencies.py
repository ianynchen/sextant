"""The dependency gate (D02 §1's `detect.coordinates`, 2O design §2a, ruling
R9) — split out from `endpoints` for the reason `capabilities` is: it is a
gate, not a derivation, and both gates answer before any engine runs.

**Why a gate at all, stated precisely, because the framing was challenged and
the challenge was right.** This is NOT a deployment check. Sextant never
observes a deployment — an `@GetMapping` row does not prove the controller was
scanned, the profile active or the application running — and every row it emits
is a claim about DECLARED CODE. The distinction that survives is whether the
module's own artifacts GROUND the claim. A framework rule of the form *if this
library is present, these routes exist* is CONDITIONAL, and deriving the
consequent without the antecedent applies a rule whose PRECONDITION is unmet.
DR-6 makes the precondition part of the rule. A dependency declared in a build
file is intention at exactly the tier an annotation is — just in a different
file, which this analysis already parses.

**Why only some styles.** Most catalogs derive from evidence that NAMES the
framework: an annotation only that framework defines, a call to a type only it
ships. There the dependency is implied by the match itself, and gating on the
coordinate as well would only ever subtract rows the evidence already earned.
A style like `derived_resource` is the opposite case — its evidence (an
interface extending a generic repository contract) mentions no HTTP anywhere,
so the framework's presence is the only thing that turns it into an API.

**Why "unanswerable" degrades visibly rather than either way.** The two build
systems answer with different reach: Gradle reports the resolved compile
classpath, Maven the POM's direct declarations only (the standing parent/BOM
resolution gap). So a starter arriving transitively through a company parent is
invisible on Maven. Deriving anyway would fabricate an API for every plain
Spring Data JPA module; omitting silently would leave a reader unable to tell
"the framework is absent" from "we could not tell". The catalog is therefore
SKIPPED, through the same channel and into the same manifest section an unmet
capability already uses (M04, FR-17).
"""

import json

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace

# The styles whose framework rule is conditional on the dependency being
# declared (module docstring). Membership is a property of the STYLE, never a
# request a catalog file makes — the same rule `endpoints._RUNS_LAST` follows,
# and for the same reason: a catalog that could opt out of its own gate is not
# gated.
#
# **The test for membership**, applied to all eleven styles and stated here
# because the answer decides real output (`A-C5`, principles sweep §3.2): can
# this style's match be satisfied by code that names the framework NOWHERE?
#
#   * `annotation_driven`, `single_call`, `fluent`, `injected_client`,
#     `interface_implementation`, `supertype_dispatch`, `supertype_derived`
#     and `combinator` all key on a framework-owned fully-qualified name — an
#     annotation only that framework defines, a call on a type only it ships,
#     a supertype or an interface only it declares. The dependency is implied
#     by the match itself, and gating on the coordinate as well would only
#     subtract rows the evidence already earned. Worse, under Maven — where
#     only DIRECT declarations are recorded — it would subtract them from every
#     module inheriting the framework through a parent or a starter.
#   * `schema_operations` reads a `.proto`, `.graphql` or WSDL file in the
#     repository. The schema is the evidence, and it is first-party; a build
#     coordinate is not what makes its operations real.
#   * `derived_resource` is the original case: an interface extending a generic
#     repository contract mentions no HTTP anywhere, so the framework's
#     presence is the only thing that turns it into an API.
#   * `config_join` is the second, and is why this set grew. Its candidate scan
#     (`engines/config_join.py::_candidates`) reads EVERY declared method and
#     filters on the return TYPE — and the types `spring-cloud-stream.yml`
#     filters on are the three standard function interfaces the PLATFORM ships,
#     not the framework, so ordinary code satisfies them constantly. With no
#     configuration present `_selected_entries` binds every candidate, so the
#     whole match reduced to "this method returns a function", and three
#     utility methods on a plain class asserted four Kafka boundaries on a
#     module with no Spring Cloud Stream at all.
#
# `spring-kafka-media`, the other shipped `config_join` catalog, matches on a
# `spring.kafka.*` configuration key and so does name its framework — but
# membership is a property of the STYLE (above), so it is gated too. The cost
# is bounded and stated: it stamps carried media onto rows other engines
# derived and can mint nothing, so a Maven module inheriting spring-kafka
# transitively loses a media DECORATION and keeps every row, visibly, through
# the same SKIPPED channel.
DEPENDENCY_GATED = frozenset({"derived_resource", "config_join"})

# The caveat rides BOTH messages, and on this one it is the load-bearing half
# (fix round 3, I-2): on Maven the recorded coordinates are the POM's direct
# declarations, so a starter inherited through a company parent is genuinely
# absent from them and this message would otherwise read as a confident "the
# framework is not here". A reader who cannot tell that from real absence
# cannot act on the skip, which is the whole of what "SKIPPED with a reason"
# is for. Stated in the STRING rather than only in the three documents that
# already say it, because the string is the only one a manifest reader sees.
_NOT_DECLARED = (
    "a build declaration of one of {coordinates} — this module's build declares "
    "none of them (D02 `detect.coordinates`; Maven records DIRECT declarations "
    "only, so a starter inherited through a parent or a BOM is absent from them "
    "and cannot be told apart from real absence here)"
)

_NOT_RECORDED = (
    "a build declaration of one of {coordinates} — this analysis recorded no "
    "dependency coordinates for the module, so the question cannot be answered "
    "(Maven records DIRECT declarations only; a workspace whose facts predate the "
    "module fact records none)"
)


def unmet_dependency(workspace: Workspace, catalog: Catalog) -> str | None:
    """What a dependency-gated catalog required of the module's build and did
    not get, or `None` when the gate is satisfied or does not apply.

    Returns a REASON rather than a boolean because the two failing cases are
    not the same fact and a reader must be able to tell them apart: the
    framework is not declared here, versus nothing was recorded to check
    against.

    Raises `CatalogError` for a gated catalog that declares no coordinates at
    all — a `derived_resource` catalog with an empty `detect.coordinates` would
    derive every repository in every module unconditionally, which is the
    fabrication this gate exists to prevent, and silence about it is the worst
    way to find out.
    """
    if catalog.style not in DEPENDENCY_GATED:
        return None
    if not catalog.detect_coordinates:
        raise CatalogError(
            f"loading catalog {catalog.source}: `style: {catalog.style}` derives rows from "
            f"evidence that names no framework, so it must declare `detect.coordinates` — "
            f"without them every module would derive them (2O design §2a, ruling R9)"
        )
    wanted = ", ".join(catalog.detect_coordinates)
    declared = _declared_coordinates(workspace)
    if declared is None:
        return _NOT_RECORDED.format(coordinates=wanted)
    if declared.isdisjoint(catalog.detect_coordinates):
        return _NOT_DECLARED.format(coordinates=wanted)
    return None


def _declared_coordinates(workspace: Workspace) -> set[str] | None:
    """Every coordinate the module fact recorded, or `None` when there is no
    module fact to read at all.

    `None` and the empty set are different answers and both are real: a
    workspace with no module fact recorded nothing (older facts, or a test that
    built its own), while a module fact carrying an empty list is a build that
    declares no dependencies. Only the first is unanswerable; the second is an
    answer, and it is "no".

    A module fact whose payload carries no `dependency_coordinates` KEY at all
    reads as SQL NULL here and counts as the first case, not the second: it
    recorded nothing, so it answers nothing. Sextant's own emitter always
    writes the key (the field's `default_factory` on `ModuleFact`), so this
    degrades a hand-authored or third-party fact file at the same
    `fact_schema_version` rather than anything this codebase produces — and it
    degrades to the SKIPPED path this function exists to provide instead of
    aborting the whole resolve on a `JSONDecodeError` (fix round 3, M-1). That
    holds as long as the field stays required-with-a-default on the model; a
    schema in which the key is genuinely optional and MEANS "no dependencies"
    would need the two cases separated here rather than merged.

    More than one module fact in one workspace is not a case this collapses
    carefully — a workspace is one module (M00) — so the union is taken, which
    is the same answer for the one-module case and the only non-arbitrary one
    otherwise.
    """
    declared: set[str] = set()
    recorded_any = False
    for row in workspace.query("module_dependencies"):
        recorded = row["dependency_coordinates"]
        if recorded is None:
            continue
        recorded_any = True
        declared.update(str(entry) for entry in json.loads(str(recorded)))
    return declared if recorded_any else None
