"""The module fact the dependency gate reads, for the two partial-pipeline
harnesses that build a workspace without running the detector.

Its own module rather than either conftest: `tests/application/conftest.py` and
`tests/architecture/conftest.py` both import as the module name `conftest`, so
an explicit `import conftest` from a test file resolves to whichever directory
pytest happened to put on `sys.path` first — a collision that only shows up
when the two directories are collected in one run. `shape_helpers.py` is the
precedent for a uniquely-named shared helper here.
"""

from pathlib import Path

# The capabilities the fixture harnesses grant, in one place for the same reason
# this module exists: `tests/application/conftest.py` defines the set that
# `resolved_fixture` uses, and a test importing it as `from conftest import ...`
# resolves to whichever `conftest` pytest put on `sys.path` first — which is
# `tests/architecture/conftest.py` whenever the two directories are collected in
# one run, and an `ImportError` only then.
#
# A real subset of what `AsmScanner.capabilities()` declares; `conftest` explains
# at length which gate each one opens and why two are granted rather than withheld.
FIXTURE_CAPABILITIES = {
    "annotation_args",
    "typed_signatures",
    "type_annotations",
    "call_site",
    "string_constants",
    "chain_reconstruction",
    "implemented_interfaces",
    "superclass",
    "generic_interfaces",
    "nested_annotation_args",
}

from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import Document, ModuleFact

# The dependency coordinates the fixture's POM declares that a
# dependency-gated style reads (`A-C5`). Neither this fixture nor
# `test_pipeline._resolved_fixture` runs the DETECTOR, so no module fact
# reaches the workspace unless one is written here — and without one every
# dependency-gated catalog is skipped as unanswerable, which since
# `config_join` joined `DEPENDENCY_GATED` would silently delete this fixture's
# whole Spring Cloud Stream surface.
#
# Deliberately a SUBSET of what the POM declares, and the omission is the
# point: `spring-data-rest-core` is in that POM too, and listing it here would
# un-skip `spring-data-rest` and change what every endpoint count in
# `test_pipeline.py` measures. The e2e suite runs the real detector and does
# derive those rows; making the two agree is a separate change, named here
# rather than smuggled into this one.
FIXTURE_GATED_COORDINATES = (
    "org.springframework.cloud:spring-cloud-stream",
    "org.springframework.kafka:spring-kafka",
    # F2 §3.6. `spring-stomp.yml` gates on this now, because `@MessageMapping`
    # alone cannot say whether a `@Controller` serves STOMP or RSocket — Spring's
    # own handlers do not distinguish them either. Omitting it here would leave
    # this harness deriving no STOMP rows while the e2e suite (which runs the real
    # detector over a POM that DOES declare it) derives five, and the difference
    # would read as a resolver bug rather than as a missing line in this tuple.
    "org.springframework:spring-websocket",
)


def write_fixture_module_fact_with(facts: Path, coordinates: tuple[str, ...]) -> None:
    """The module fact, with the coordinates the caller names.

    Separate from `write_fixture_module_fact` because a test about a DEPENDENCY
    GATE has to vary the one thing that function fixes. F2 §3.6's pair is the
    first such test: `spring-stomp` and `spring-rsocket` are told apart by the
    build and by nothing else, so a harness that always writes the same
    coordinates cannot express either side of the question."""
    _write_module_fact(facts, coordinates)


def write_fixture_module_fact(facts: Path) -> None:
    """The module fact `resolve/dependencies.py` reads, written beside the
    scanner's own fact files."""
    _write_module_fact(facts, FIXTURE_GATED_COORDINATES)


def _write_module_fact(facts: Path, coordinates: tuple[str, ...]) -> None:
    write_fact_file(
        facts / "module.jsonl",
        Document(
            document_id="doc_module",
            relative_path="pom.xml",
            module_id="com.acme:orders-service",
            language="java",
            sextant_version="0.1.0",
            fact_schema_version=2,
            scanner_id="asm",
            content_hash="sha256:module",
            origin_entry="target/classes",
            origin_tier=OriginTier.MODULE_OUTPUT,
            redaction_set_hash="sha256:none",
        ),
        [
            ModuleFact(
                document_id="doc_module",
                module_id="com.acme:orders-service",
                module_kind="service",
                languages=["java"],
                source_roots=["src/main/java"],
                output_dirs=["target/classes"],
                dependency_coordinates=list(coordinates),
            )
        ],
    )
