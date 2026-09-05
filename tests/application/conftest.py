import subprocess
from pathlib import Path

import pytest

from sextant.application.ports.artifacts import ReadRequest, group_files_by_reader
from sextant.application.ports.scanner import ScanRequest
from sextant.application.resolve.pipeline import ResolveReport, resolve
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import config_fact_target, write_fact_file
from sextant.domain.facts import Document, ModuleFact
from sextant.domain.ignorefile import IgnoreRules
from sextant.domain.resource_files import list_files
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.ingress.extract.jvm.scanner import AsmScanner
from sextant.ingress.read.properties import PropertiesReader
from sextant.ingress.read.yaml_config import YamlConfigReader
from sextant.resources import catalogs_dir, extractor_jar
from sextant.storage.duckdb.workspace import DuckDbWorkspace

REPO = Path(__file__).parents[2]
JAR = extractor_jar()
FIXTURE = REPO / "fixtures" / "orders-service"
CATALOGS = catalogs_dir()


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
)


def write_fixture_module_fact(facts: Path) -> None:
    """The module fact `resolve/dependencies.py` reads, written beside the
    scanner's own fact files."""
    write_fact_file(
        facts / "module.jsonl",
        Document(
            document_id="doc_module",
            relative_path="pom.xml",
            module_id="com.acme:orders-service",
            language="java",
            sextant_version="0.1.0",
            fact_schema_version="1.0.0",
            scanner_id="asm",
            scanner_version="9.8",
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
                dependency_coordinates=list(FIXTURE_GATED_COORDINATES),
            )
        ],
    )


@pytest.fixture(scope="session")
def resolved_fixture(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[DuckDbWorkspace, ResolveReport]:
    """Compile, scan and resolve the fixture once per test session, against
    the shipped catalogs — the same real-bytecode path `test_pipeline.py`'s
    own `_resolved_fixture` runs per test, shared read-only across every test
    that does not need its own catalogs or its own tmp workspace (a test that
    does keeps calling `_resolved_fixture` directly). The workspace is handed
    back open: the rows the report points at are read from it, and closing it
    here would take them with it — session teardown closes it once, after
    every consumer is done."""
    tmp_path = tmp_path_factory.mktemp("resolved_fixture")
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    facts = tmp_path / "facts"
    AsmScanner(JAR).scan(
        ScanRequest(
            module_id="com.acme:orders-service",
            coordinates="com.acme/orders-service",
            version="1.0.0",
            classes_dir=FIXTURE / "target" / "classes",
            out_dir=facts,
        )
    )
    write_fixture_module_fact(facts)
    # 2F Task 7: the read half, mirroring `stages/analyze.py` — see
    # `test_pipeline._resolved_fixture`'s own copy for why a fixture resolved
    # without its configuration answers a different question entirely once a
    # `config_join` catalog is shipped. Duplicated rather than shared, like
    # the compile/scan/resolve above it.
    root = FIXTURE / "src" / "main" / "resources"
    for reader, owned in group_files_by_reader(
        list_files(root, FIXTURE, IgnoreRules.load(FIXTURE)),
        [PropertiesReader(), YamlConfigReader()],
    ):
        request = ReadRequest(
            module_id="com.acme:orders-service", version="1.0.0", files=owned, root=root
        )
        for document, config_facts in reader.read(request):
            target = config_fact_target(facts, document.relative_path)
            write_fact_file(target, document, config_facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    report = resolve(
        workspace,
        facts,
        YamlCatalogSource(CATALOGS),
        # Phase 2C: `call_site` and `string_constants` gate the RestTemplate
        # catalog (D02 §1's `single_call`); `chain_reconstruction` gates the
        # `fluent` catalogs (WebClient/RestClient/OkHttp/aws-sqs-sdk/
        # google-pubsub-publisher/spring-kafka-message) AND, as of Phase 2E
        # Task 9, `spring-webflux-router.yml`'s own `combinator` style — the
        # SAME three capabilities (`call_site`, `string_constants`,
        # `chain_reconstruction`), no new one added; `implemented_interfaces`
        # (2E-prep Task 12) gates `google-pubsub-subscriber.yml`'s own
        # `interface_implementation` style; `superclass` (capability 9.13, 2O
        # design §1b, Task 5) gates `grpc-java.yml`'s own `supertype_derived`
        # style; `generic_interfaces` (capability 9.14, 2O design §2a, Task 6)
        # gates `spring-data-rest.yml`'s own `derived_resource` style — a real
        # subset of what `AsmScanner.capabilities()` actually declares, the
        # same way the other capabilities here already are.
        #
        # Granting 9.14 rather than withholding it is deliberate: with the
        # capability met, this fixture exercises the DEPENDENCY gate instead —
        # the module fact written above deliberately omits Spring Data REST's
        # coordinate (`FIXTURE_GATED_COORDINATES` says why), so the gate answers
        # "not declared" and the skip is the check this live fixture is behind.
        {
            "annotation_args",
            "typed_signatures",
            "type_annotations",
            "call_site",
            "string_constants",
            "chain_reconstruction",
            "implemented_interfaces",
            "superclass",
            "generic_interfaces",
        },
    )
    yield workspace, report
    workspace.close()
