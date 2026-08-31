from pathlib import Path

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
