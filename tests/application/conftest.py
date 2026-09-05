import subprocess
from pathlib import Path

import pytest
from fixture_module import write_fixture_module_fact

from sextant.application.ports.artifacts import ReadRequest, group_files_by_reader
from sextant.application.ports.scanner import ScanRequest
from sextant.application.resolve.pipeline import ResolveReport, resolve
from sextant.domain.factfile import config_fact_target, write_fact_file
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
            # `nested_annotation_args` (capability 9.16, 2O design §4a, Task 8)
            # gates `spring-scheduling.yml`'s own `scheduled_work` style.
            # GRANTED rather than withheld, for the reason 9.14 is above: with
            # it withheld the catalog joins the skip list and this fixture stops
            # answering the question it exists for, while with it met the
            # catalog RUNS against a module that schedules nothing — which is
            # the honest zero the `scheduled_work` table should hold here.
            "nested_annotation_args",
        },
    )
    yield workspace, report
    workspace.close()
