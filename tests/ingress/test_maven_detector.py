from pathlib import Path

import pytest

from sextant.ingress.detect.maven import MavenDetector

FIXTURE = Path(__file__).parents[2] / "fixtures" / "orders-service"


def test_accepts_true_when_directory_holds_a_pom():
    assert MavenDetector().accepts(FIXTURE)


def test_accepts_false_when_directory_has_no_pom(tmp_path: Path):
    assert not MavenDetector().accepts(tmp_path)


def test_detect_reports_module_coordinates_and_output_dir_when_run_on_the_fixture():
    model = MavenDetector().detect(FIXTURE)
    module = model.modules[0]
    assert module.module_id == "com.acme:orders-service"
    assert module.coordinates == "com.acme/orders-service"
    assert module.version == "1.0.0"
    assert module.output_dirs == (FIXTURE / "target" / "classes",)
    assert module.languages == {"java", "kotlin"}
    assert module.source_roots == (
        FIXTURE / "src" / "main" / "java",
        FIXTURE / "src" / "main" / "kotlin",
    )


_BARE_POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <groupId>com.acme</groupId>
  <artifactId>thing</artifactId>
  <version>1.0.0</version>
</project>
"""


def _module(root: Path, pom: str = _BARE_POM) -> Path:
    (root / "pom.xml").write_text(pom, encoding="utf-8")
    return root


_CHILD_POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <parent>
    <groupId>com.acme</groupId>
    <artifactId>acme-parent</artifactId>
    <version>2.3.0</version>
  </parent>
  <artifactId>thing</artifactId>
</project>
"""


def test_a_reactor_child_takes_the_coordinates_its_parent_states(tmp_path: Path):
    """Maven's inheritance rule: a child inherits `groupId` and `version` from
    `<parent>` and may omit both elements entirely — `artifactId` alone is
    never inherited. Reading only the child's own elements raised
    `pom.xml has no <version>` and failed the whole analyze on the first
    reactor module it met, which is most real multi-module repositories:
    `spring-petclinic-microservices`' own children omit `<version>` exactly
    like this. The parent's value is Maven convention data, not a guess."""
    module = MavenDetector().detect(_module(tmp_path, _CHILD_POM)).modules[0]

    assert module.module_id == "com.acme:thing"
    assert module.coordinates == "com.acme/thing"
    assert module.version == "2.3.0"


def test_a_childs_own_coordinates_win_over_the_ones_its_parent_states(tmp_path: Path):
    """The parent is a FALLBACK, never an override: a child that states its own
    `groupId` is that groupId, whatever the parent says. The half-and-half form
    is the common one and the one `spring-petclinic-api-gateway` writes — its
    own `groupId`, its parent's `version` — so a fallback that fired
    unconditionally would rename every module in a reactor to its parent's
    group and merge modules that are not the same module."""
    pom = _CHILD_POM.replace(
        "  <artifactId>thing</artifactId>",
        "  <groupId>com.acme.sub</groupId>\n  <artifactId>thing</artifactId>",
    )
    module = MavenDetector().detect(_module(tmp_path, pom)).modules[0]

    assert module.module_id == "com.acme.sub:thing"
    # Still the parent's: only the stated half stopped being inherited.
    assert module.version == "2.3.0"


def test_a_pom_stating_no_coordinates_at_either_level_is_still_refused(tmp_path: Path):
    """The fallback widens where a value may be READ from; it does not invent
    one. A pom with no version anywhere still fails loudly rather than
    detecting a module with an empty or guessed version (M02)."""
    pom = _BARE_POM.replace("  <version>1.0.0</version>\n", "")

    with pytest.raises(ValueError, match="version"):
        MavenDetector().detect(_module(tmp_path, pom))


def test_kind_is_undetermined_when_no_evidence_decides_it(tmp_path: Path):
    """M02: "Where the evidence does not decide, the answer is `undetermined`,
    never a guess", and `undetermined` is a value. A fixed `service` is
    published into metadata.json as though it had been observed, which is the
    guess the spec's prohibitions name outright."""
    assert MavenDetector().detect(_module(tmp_path)).modules[0].kind == "undetermined"
    assert MavenDetector().detect(FIXTURE).modules[0].kind == "undetermined"


def test_kind_is_service_when_the_module_declares_a_main_class(tmp_path: Path):
    pom = _BARE_POM.replace(
        "</project>",
        "  <build><plugins><plugin><configuration>"
        "<mainClass>com.acme.Boot</mainClass>"
        "</configuration></plugin></plugins></build>\n</project>",
    )
    assert MavenDetector().detect(_module(tmp_path, pom)).modules[0].kind == "service"


def test_kind_is_service_when_a_container_file_sits_beside_the_pom(tmp_path: Path):
    _module(tmp_path)
    (tmp_path / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    assert MavenDetector().detect(tmp_path).modules[0].kind == "service"


def test_languages_and_source_roots_follow_the_source_tree_when_the_module_is_not_java(
    tmp_path: Path,
):
    """The detector is keyed by build system, not language (M02), and only
    `ingress/extract/jvm` may name a language (ARCHITECTURE §10). A hardcoded
    `java` is both: it makes a Kotlin module report a language it does not
    hold and a source root that does not exist — a path everything downstream
    treats as somewhere it already looked."""
    _module(tmp_path)
    kotlin = tmp_path / "src" / "main" / "kotlin"
    kotlin.mkdir(parents=True)
    (kotlin / "Order.kt").write_text("class Order\n", encoding="utf-8")
    (tmp_path / "src" / "main" / "resources").mkdir()

    module = MavenDetector().detect(tmp_path).modules[0]

    assert module.languages == {"kotlin"}
    assert module.source_roots == (kotlin,)
    assert all(root.is_dir() for root in module.source_roots)


def test_source_roots_are_empty_when_the_module_has_no_source_directory(tmp_path: Path):
    module = MavenDetector().detect(_module(tmp_path)).modules[0]
    assert module.source_roots == ()
    assert module.languages == frozenset()


def test_resource_roots_contains_the_conventional_resources_directory_when_it_exists(
    tmp_path: Path,
):
    _module(tmp_path)
    resources = tmp_path / "src" / "main" / "resources"
    resources.mkdir(parents=True)

    module = MavenDetector().detect(tmp_path).modules[0]

    assert module.resource_roots == (resources,)


def test_resource_roots_is_empty_when_the_module_has_no_resources_directory(tmp_path: Path):
    module = MavenDetector().detect(_module(tmp_path)).modules[0]
    assert module.resource_roots == ()


def test_schema_roots_reports_proto_then_avro_when_both_exist(tmp_path: Path):
    _module(tmp_path)
    proto = tmp_path / "src" / "main" / "proto"
    avro = tmp_path / "src" / "main" / "avro"
    # Reverse mkdir order, so a passing test cannot be an accident of
    # directory-listing order rather than the detector's own fixed sequence.
    avro.mkdir(parents=True)
    proto.mkdir(parents=True)

    module = MavenDetector().detect(tmp_path).modules[0]

    assert module.schema_roots == (proto, avro)


def test_schema_roots_names_only_the_directories_that_exist(tmp_path: Path):
    _module(tmp_path)
    avro = tmp_path / "src" / "main" / "avro"
    avro.mkdir(parents=True)

    module = MavenDetector().detect(tmp_path).modules[0]

    assert module.schema_roots == (avro,)


def test_schema_roots_is_empty_when_the_module_has_no_schema_directory(tmp_path: Path):
    module = MavenDetector().detect(_module(tmp_path)).modules[0]
    assert module.schema_roots == ()


def test_schema_roots_reports_the_sdl_directory_under_resources(tmp_path: Path):
    """Spring GraphQL's own convention puts SDL on the classpath, so this one
    schema root sits UNDER `src/main/resources` rather than beside the source
    roots — the detector reads a build layout, and this is the layout the
    build actually has."""
    _module(tmp_path)
    graphql = tmp_path / "src" / "main" / "resources" / "graphql"
    graphql.mkdir(parents=True)

    module = MavenDetector().detect(tmp_path).modules[0]

    assert module.schema_roots == (graphql,)
    # `resources` is a non-source directory, so nothing under it was ever
    # going to be reported as a language.
    assert module.languages == frozenset()


def test_schema_roots_reports_the_three_contract_directories_under_resources(tmp_path: Path):
    """A SOAP contract is served at runtime, so all three sit on the classpath
    — `META-INF/wsdl` being where the JAX-WS packaging convention puts it.
    Reported in the detector's own fixed order, never a directory listing's."""
    _module(tmp_path)
    resources = tmp_path / "src" / "main" / "resources"
    # Reverse mkdir order, so a passing test cannot be an accident of
    # directory-listing order rather than the detector's own fixed sequence.
    packaged = resources / "META-INF" / "wsdl"
    packaged.mkdir(parents=True)
    xsd = resources / "xsd"
    xsd.mkdir()
    wsdl = resources / "wsdl"
    wsdl.mkdir()

    module = MavenDetector().detect(tmp_path).modules[0]

    assert module.schema_roots == (wsdl, xsd, packaged)
    assert module.languages == frozenset()


def test_schema_roots_reports_every_one_of_the_real_fixtures_schema_directories():
    module = MavenDetector().detect(FIXTURE).modules[0]

    assert module.schema_roots == (
        FIXTURE / "src" / "main" / "proto",
        FIXTURE / "src" / "main" / "avro",
        FIXTURE / "src" / "main" / "resources" / "graphql",
        FIXTURE / "src" / "main" / "resources" / "wsdl",
    )


def test_a_declared_source_directory_wins_over_the_conventional_layout(tmp_path: Path):
    """M02: the detector reads the build, never a convention."""
    pom = _BARE_POM.replace(
        "</project>",
        "  <build><sourceDirectory>sources/scala</sourceDirectory></build>\n</project>",
    )
    _module(tmp_path, pom)
    (tmp_path / "sources" / "scala").mkdir(parents=True)
    (tmp_path / "src" / "main" / "java").mkdir(parents=True)

    module = MavenDetector().detect(tmp_path).modules[0]

    assert module.source_roots == (tmp_path / "sources" / "scala",)
    assert module.languages == {"scala"}
