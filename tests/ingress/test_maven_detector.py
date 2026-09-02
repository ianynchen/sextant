from pathlib import Path

import pytest

from sextant.ingress.detect.maven import MavenDetector
from sextant.ingress.detect.sextant_config import SextantConfigError

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


# --- Opt-in library extraction (2I Task 6) -------------------------------

_LIBRARY_POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <groupId>com.acme</groupId>
  <artifactId>thing</artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>stub</artifactId>
      <version>2.1.0</version>
    </dependency>
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>managed</artifactId>
    </dependency>
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>interpolated</artifactId>
      <version>${stub.version}</version>
    </dependency>
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>classified</artifactId>
      <version>2.1.0</version>
      <classifier>jdk17</classifier>
    </dependency>
  </dependencies>
</project>
"""


def _local_repository(home: Path, coordinate: str, version: str) -> Path:
    group, _, artifact = coordinate.partition(":")
    archive = (
        home / ".m2" / "repository" / Path(*group.split(".")) / artifact / version
    ) / f"{artifact}-{version}.jar"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"")
    return archive


def test_a_module_with_no_config_names_no_library_roots(tmp_path: Path):
    """The isolation guarantee at its source: opt-in means the file, so a
    module without one reaches the scan loop with nothing extra to scan and
    nothing unresolved to report."""
    _module(tmp_path, _LIBRARY_POM)
    module = MavenDetector().detect(tmp_path).modules[0]
    assert module.library_roots == ()
    assert module.libraries_not_resolved == ()


def test_a_declared_library_resolves_to_the_archive_the_build_would_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Two pieces of Maven convention and no invention: the VERSION is the one
    this module's own POM declares for that dependency — the only place the
    build states which release it compiles against — and the ARCHIVE is the
    local repository's own layout, where a successful build (M02's stated
    prerequisite) has already left it."""
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    archive = _local_repository(home, "com.example:stub", "2.1.0")
    root = tmp_path / "module"
    root.mkdir()
    _module(root, _LIBRARY_POM)
    (root / ".sextant.yml").write_text("extract_libraries: [com.example:stub]\n", encoding="utf-8")

    module = MavenDetector().detect(root).modules[0]

    assert module.libraries_not_resolved == ()
    [library] = module.library_roots
    assert (library.coordinate, library.version, library.archive) == (
        "com.example:stub",
        "2.1.0",
        archive,
    )


def test_a_pinned_version_resolves_without_asking_the_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The three-segment escape hatch. `com.example:managed` is declared with
    NO version — the BOM case this detector cannot read, and the case most real
    Spring Boot dependencies are in — so the two-segment form can never reach
    it. Pinning the version in `.sextant.yml` is the author asserting which
    release to read, and it asks the POM nothing at all.

    The coordinate the library is then KNOWN by stays `groupId:artifactId`, so
    the fact subtree and the rendered attribution do not change shape depending
    on whether a version was pinned."""
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    archive = _local_repository(home, "com.example:managed", "4.5.6")
    root = tmp_path / "module"
    root.mkdir()
    _module(root, _LIBRARY_POM)
    (root / ".sextant.yml").write_text(
        "extract_libraries: ['com.example:managed:4.5.6']\n", encoding="utf-8"
    )

    module = MavenDetector().detect(root).modules[0]

    assert module.libraries_not_resolved == ()
    [library] = module.library_roots
    assert (library.coordinate, library.version, library.archive) == (
        "com.example:managed",
        "4.5.6",
        archive,
    )


@pytest.mark.parametrize(
    ("coordinate", "expected_reason"),
    [
        # Three forms this detector cannot read a release out of, one answer —
        # and the answer names the remedy rather than the form.
        ("com.example:managed", "does not read a version from"),
        ("com.example:interpolated", "does not read a version from"),
        ("com.example:classified", "does not read a version from"),
        ("com.example:absent", "declares no such dependency"),
        ("com.example:stub", "no 2.1.0 archive in the local repository"),
    ],
)
def test_a_library_that_resolves_to_no_archive_is_named_with_its_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, coordinate: str, expected_reason: str
):
    """Five ways a coordinate can fail, one answer: it is REPORTED, **with the
    reason**. No version scanned for in the repository, no nearest match, no
    second location — a wrong jar is indistinguishable downstream from a right
    one, while a named coordinate is a gap a reader can close (FR-17).

    The reason is what makes the gap actionable: "declare the dependency",
    "pin the version" and "install the artifact" are three different things to
    go and do, and a bare coordinate leaves a reader to guess which. Nothing
    raises: a library nobody could find is not a reason to refuse the module's
    own analysis.

    **And no reason may carry an absolute path.** These strings travel — into
    metadata.json, into the rendered gaps list, into a published bundle — and
    D00 §2's rule holds for every one: a path under someone's home directory
    identifies nothing off the machine that wrote it. The check is on the whole
    reason rather than on a known offender, because the first version of the
    "why" wording leaked the local repository directory back in through a
    parenthetical that a substring assertion for the message never saw."""
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    root = tmp_path / "module"
    root.mkdir()
    _module(root, _LIBRARY_POM)
    (root / ".sextant.yml").write_text(f"extract_libraries: [{coordinate}]\n", encoding="utf-8")

    module = MavenDetector().detect(root).modules[0]

    assert module.library_roots == ()
    [reported] = module.libraries_not_resolved
    assert reported.startswith(f"{coordinate}: ")
    assert expected_reason in reported
    assert str(home) not in reported
    assert ".m2" not in reported
    assert not any(word.startswith("/") for word in reported.replace("(", " ").split())


def test_a_missing_archive_names_where_to_look_without_naming_anyones_machine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The layout, relative to a repository root and anchored to none: it is the
    half of the location that is true on every machine, so the reader supplies
    the root they actually have. Naming the absolute directory instead told a
    bundle's reader where the jar was not, on a computer they do not own."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    root = tmp_path / "module"
    root.mkdir()
    _module(root, _LIBRARY_POM)
    (root / ".sextant.yml").write_text("extract_libraries: [com.example:stub]\n", encoding="utf-8")

    [reported] = MavenDetector().detect(root).modules[0].libraries_not_resolved

    assert "com/example/stub/2.1.0/stub-2.1.0.jar" in reported


def test_the_sibling_library_fixture_detects_through_its_parents_coordinates():
    """`fixtures/orders-soap-client` declares only an `artifactId`: its groupId
    and version are its parent's. The reactor-inheritance rule has been
    implemented since the reactor fix with no fixture to prove it on — this is
    it, and it is the same POM that opt-in library extraction resolves this
    coordinate against."""
    module = MavenDetector().detect(FIXTURE.parent / "orders-soap-client").modules[0]
    assert module.module_id == "com.example:orders-soap-client"
    assert module.version == "1.0.0"
    assert module.languages == {"java"}
    # No main class, no container file: nothing here is evidence of a service,
    # and `library` is never returned from coordinates alone (`_classify`).
    assert module.kind == "undetermined"
    # And it opts into nothing itself — the opt-in belongs to the module doing
    # the analysing, never to the library being analysed.
    assert module.library_roots == ()


def test_a_malformed_config_stops_detection_rather_than_extracting_nothing(tmp_path: Path):
    """The DR-6 exemption. Every other unreadable input in this codebase
    degrades to an honest absence, because it is evidence Sextant does not
    own. `.sextant.yml` is an instruction written FOR Sextant, and "extract
    nothing" is what a typo would otherwise mean — silently, and forever."""
    root = _module(tmp_path, _LIBRARY_POM)
    (root / ".sextant.yml").write_text("extract_libaries: [com.example:stub]\n", encoding="utf-8")
    with pytest.raises(SextantConfigError):
        MavenDetector().detect(root)
