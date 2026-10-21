import os
import subprocess
from pathlib import Path

import pytest

from sextant.application.ports.detector import LibraryRoot
from sextant.ingress.detect import maven as maven_module
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


@pytest.mark.pins("detect.mavens-OWN-classpath-answers-for-the-dependency-set")
def test_dependency_coordinates_are_what_maven_resolved_transitives_included():
    """2O design §2a, ruling R9: the gate a `derived_resource` catalog reads
    needs the module's dependencies in the workspace. Since F1 that was what
    the pom declares PLUS what it inherits; since spec 2026-10-21 §3b it is what
    MAVEN resolved — the file `dependency:build-classpath` wrote beside the
    classes, which the fixture build primes — so a TRANSITIVE is in the set
    with the version Maven chose, exactly as Gradle has always reported.
    Sorted, because everything a detector reports is (NFR-1)."""
    module = MavenDetector().detect(FIXTURE).modules[0]

    assert module.dependency_source == "maven"
    assert module.dependency_source_reason is None
    assert "org.springframework:spring-web" in module.dependency_coordinates
    # The one the Data REST gate reads, declared by this fixture on purpose
    # (2O Task 6's conformance fixture).
    assert "org.springframework.data:spring-data-rest-core" in module.dependency_coordinates
    assert list(module.dependency_coordinates) == sorted(module.dependency_coordinates)
    # Data REST pulls `evo-inflector` in transitively and no pom here names it.
    # This line used to assert the OPPOSITE, as the shape the POM parse could
    # not see without implementing Maven's mediation; Maven's own answer sees
    # it, which is the whole of `OI-167`, and the declared-only reading is the
    # labelled fallback `dependency_source == "declared"` now names.
    assert "org.atteo:evo-inflector" in module.dependency_coordinates
    assert module.dependency_versions["org.atteo:evo-inflector"]


def test_a_module_declaring_no_dependencies_reports_none(tmp_path: Path):
    """Empty and unrecorded are different answers (`resolve/dependencies.py`):
    this is the empty one — a build that declares nothing — and it is an
    answer, not an absence."""
    module = MavenDetector().detect(_module(tmp_path)).modules[0]

    assert module.dependency_coordinates == ()


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


# --- Detect notes (2M Task 1) --------------------------------------------


@pytest.mark.parametrize(
    "gradle_file", ["build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"]
)
def test_gradle_files_beside_a_pom_are_a_note_maven_still_wins(tmp_path: Path, gradle_file: str):
    """One build system per run, stated, never merged (2M design §1): a `pom.xml`
    still wins outright over any Gradle file sitting beside it, and the
    coexistence is recorded rather than silently dropped — the exact string is
    pinned because it is what `metadata.json`'s `detect_notes` carries out to a
    reader deciding which build actually ran."""
    _module(tmp_path)
    (tmp_path / gradle_file).write_text("", encoding="utf-8")

    model = MavenDetector().detect(tmp_path)

    assert model.notes == ("gradle build files present; maven selected",)
    # Maven still won: the module it reports is the POM's, untouched by the
    # Gradle files sitting beside it.
    assert model.modules[0].module_id == "com.acme:thing"


def test_no_gradle_files_means_no_notes(tmp_path: Path):
    model = MavenDetector().detect(_module(tmp_path))
    assert model.notes == ()


def test_the_real_fixture_has_no_gradle_files_and_no_notes():
    assert MavenDetector().detect(FIXTURE).notes == ()


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


def test_a_sibling_inside_a_NESTED_aggregator_is_read(tmp_path: Path):
    """`OI-149`: a shared type in `framework/common` was invisible, so every endpoint's
    response contract was open.

    The layout is `YunaiV/ruoyi-vue-pro`'s, which is the common shape for a large build:
    the root aggregates `framework` and `app`, and `framework` is ITSELF an aggregator
    holding the module that declares the envelope every controller returns. Measured
    there: 85 open shapes in one module, 45 in another, and the response of all 323 of
    their endpoints undescribed.

    `_sibling_roots` was never the problem — it walks declared dependencies transitively
    and reads their compiled output, with no `.sextant.yml` opt-in, which is why
    `macrozheng/mall-swarm` (a FLAT reactor) resolves the same envelope correctly. The
    gap was `_reactor_modules`, which resolved the parent's `<modules>` entries and
    stopped: the root names `framework`, an aggregator with no `target/classes`, so the
    module holding the type was in no map and nothing could reach it.
    """
    root = tmp_path / "build"
    (root / "framework" / "common").mkdir(parents=True)
    (root / "app").mkdir()
    (root / "pom.xml").write_text(
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <groupId>com.acme</groupId><artifactId>build</artifactId><version>4.1.0</version>
  <packaging>pom</packaging>
  <modules><module>framework</module><module>app</module></modules>
</project>
""",
        encoding="utf-8",
    )
    # The nested aggregator: no compiled output of its own, which is exactly why
    # stopping at it read nothing.
    (root / "framework" / "pom.xml").write_text(
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <parent><groupId>com.acme</groupId><artifactId>build</artifactId><version>4.1.0</version></parent>
  <artifactId>framework</artifactId>
  <packaging>pom</packaging>
  <modules><module>common</module></modules>
</project>
""",
        encoding="utf-8",
    )
    (root / "framework" / "common" / "pom.xml").write_text(
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <parent><groupId>com.acme</groupId><artifactId>framework</artifactId><version>4.1.0</version></parent>
  <artifactId>common</artifactId>
</project>
""",
        encoding="utf-8",
    )
    (root / "app" / "pom.xml").write_text(
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <parent><groupId>com.acme</groupId><artifactId>build</artifactId><version>4.1.0</version></parent>
  <artifactId>app</artifactId>
  <dependencies>
    <dependency><groupId>com.acme</groupId><artifactId>common</artifactId><version>4.1.0</version></dependency>
  </dependencies>
</project>
""",
        encoding="utf-8",
    )
    classes = root / "framework" / "common" / "target" / "classes"
    classes.mkdir(parents=True)
    # A sibling root is taken only where compiled output EXISTS (`_sibling_roots`), so the
    # file has to be there; its contents are the scanner's business, not the detector's.
    (classes / "Envelope.class").write_bytes(b"\xca\xfe\xba\xbe")

    module = MavenDetector().detect(root / "app").modules[0]

    assert [root_.coordinate for root_ in module.library_roots] == ["com.acme:common"]
    assert module.library_roots[0].archive == classes
    # The version is the one THIS module declared for it, as for any sibling.
    assert module.library_roots[0].version == "4.1.0"
    assert module.sibling_coordinates == ("com.acme:common",)


@pytest.mark.pins("maven.a-climb-stops-at-the-aggregator-that-contains-this-module")
def test_an_ancestor_that_does_not_contain_this_module_does_not_replace_the_reactor_root(
    tmp_path: Path,
):
    """The climb above must not walk out of the project, and this is the case that taught
    it: a reactor root commonly inherits from a parent that is not its aggregator at all.

    `macrozheng/mall`'s root pom declares
    `<parent>org.springframework.boot:spring-boot-starter-parent</parent>` with an empty
    `<relativePath/>`, so `_parent_pom` resolves it out of the local repository. An
    unconditional climb replaced the real root with a pom inside `~/.m2` and found no
    siblings at all — `mall-admin` fell from **629 shape fields to 73**, and its field pin
    is what caught it.

    Here the outside parent is on disk and declares `<modules>` of its own, which is the
    harder version of the same thing: a plausible ancestor that aggregates something else.
    The rule is containment — an aggregator reaches its modules by relative paths, so one
    that does not contain this module cannot be the tree this module belongs to.
    """
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "pom.xml").write_text(
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <groupId>com.vendor</groupId><artifactId>vendor-parent</artifactId><version>9.0.0</version>
  <packaging>pom</packaging>
  <modules><module>something-else</module></modules>
</project>
""",
        encoding="utf-8",
    )
    root = tmp_path / "build"
    (root / "common").mkdir(parents=True)
    (root / "app").mkdir()
    (root / "pom.xml").write_text(
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <parent>
    <groupId>com.vendor</groupId><artifactId>vendor-parent</artifactId><version>9.0.0</version>
    <relativePath>../outside/pom.xml</relativePath>
  </parent>
  <artifactId>build</artifactId><packaging>pom</packaging>
  <modules><module>common</module><module>app</module></modules>
</project>
""",
        encoding="utf-8",
    )
    (root / "common" / "pom.xml").write_text(
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <parent><groupId>com.vendor</groupId><artifactId>build</artifactId><version>9.0.0</version></parent>
  <artifactId>common</artifactId>
</project>
""",
        encoding="utf-8",
    )
    (root / "app" / "pom.xml").write_text(
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <parent><groupId>com.vendor</groupId><artifactId>build</artifactId><version>9.0.0</version></parent>
  <artifactId>app</artifactId>
  <dependencies>
    <dependency><groupId>com.vendor</groupId><artifactId>common</artifactId><version>9.0.0</version></dependency>
  </dependencies>
</project>
""",
        encoding="utf-8",
    )
    classes = root / "common" / "target" / "classes"
    classes.mkdir(parents=True)
    (classes / "Shared.class").write_bytes(b"\xca\xfe\xba\xbe")

    module = MavenDetector().detect(root / "app").modules[0]

    assert module.sibling_coordinates == ("com.vendor:common",)


def test_a_nested_module_reaches_a_sibling_in_ANOTHER_subtree(tmp_path: Path):
    """The other half of `OI-149`, and live in the same project: the walk has to start at
    the TOP of the reactor, not at this module's own parent.

    `ruoyi-vue-pro` again — `yudao-module-mall/yudao-module-promotion` depends on
    `yudao-module-system`, which is a ROOT-level module, and
    `yudao-module-mall/yudao-module-product` depends on
    `yudao-framework/yudao-spring-boot-starter-web`, which is in a different subtree
    entirely. Descending from `yudao-module-mall` reaches neither: the dependency is up
    and across, and a reactor is the whole tree from its root by Maven's own definition.

    Climbing is per-step validated by `_parent_pom`, which accepts a `<relativePath>` pom
    only when it declares the coordinates the `<parent>` names — so this follows genuine
    Maven inheritance and cannot wander into an unrelated aggregator that happens to sit
    one directory up.
    """
    root = tmp_path / "build"
    (root / "framework" / "starter-web").mkdir(parents=True)
    (root / "mall" / "promotion").mkdir(parents=True)
    (root / "pom.xml").write_text(
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <groupId>com.acme</groupId><artifactId>build</artifactId><version>4.1.0</version>
  <packaging>pom</packaging>
  <modules><module>framework</module><module>mall</module></modules>
</project>
""",
        encoding="utf-8",
    )
    for aggregator, child in (("framework", "starter-web"), ("mall", "promotion")):
        (root / aggregator / "pom.xml").write_text(
            f"""<project xmlns="http://maven.apache.org/POM/4.0.0">
  <parent><groupId>com.acme</groupId><artifactId>build</artifactId><version>4.1.0</version></parent>
  <artifactId>{aggregator}</artifactId><packaging>pom</packaging>
  <modules><module>{child}</module></modules>
</project>
""",
            encoding="utf-8",
        )
    (root / "framework" / "starter-web" / "pom.xml").write_text(
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <parent><groupId>com.acme</groupId><artifactId>framework</artifactId><version>4.1.0</version></parent>
  <artifactId>starter-web</artifactId>
</project>
""",
        encoding="utf-8",
    )
    (root / "mall" / "promotion" / "pom.xml").write_text(
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <parent><groupId>com.acme</groupId><artifactId>mall</artifactId><version>4.1.0</version></parent>
  <artifactId>promotion</artifactId>
  <dependencies>
    <dependency><groupId>com.acme</groupId><artifactId>starter-web</artifactId><version>4.1.0</version></dependency>
  </dependencies>
</project>
""",
        encoding="utf-8",
    )
    classes = root / "framework" / "starter-web" / "target" / "classes"
    classes.mkdir(parents=True)
    (classes / "WebAutoConfiguration.class").write_bytes(b"\xca\xfe\xba\xbe")

    module = MavenDetector().detect(root / "mall" / "promotion").modules[0]

    assert module.sibling_coordinates == ("com.acme:starter-web",)
    assert module.library_roots[0].archive == classes


def test_a_nested_aggregators_sibling_this_module_does_not_depend_on_is_still_refused(
    tmp_path: Path,
):
    """The widening above must not become "every module in the reactor", which was tried
    and was wrong on its face: `mall-portal`'s `@Scheduled` cron task rendered inside
    `mall-admin`'s document because its classes entered a workspace that never compiles
    against them (`_sibling_roots`' own docstring). Descending into an aggregator adds
    CANDIDATES; the dependency list still decides.
    """
    root = tmp_path / "build"
    (root / "framework" / "common").mkdir(parents=True)
    (root / "framework" / "unrelated").mkdir(parents=True)
    (root / "app").mkdir()
    (root / "pom.xml").write_text(
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <groupId>com.acme</groupId><artifactId>build</artifactId><version>4.1.0</version>
  <packaging>pom</packaging>
  <modules><module>framework</module><module>app</module></modules>
</project>
""",
        encoding="utf-8",
    )
    (root / "framework" / "pom.xml").write_text(
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <parent><groupId>com.acme</groupId><artifactId>build</artifactId><version>4.1.0</version></parent>
  <artifactId>framework</artifactId><packaging>pom</packaging>
  <modules><module>common</module><module>unrelated</module></modules>
</project>
""",
        encoding="utf-8",
    )
    for name in ("common", "unrelated"):
        (root / "framework" / name / "pom.xml").write_text(
            f"""<project xmlns="http://maven.apache.org/POM/4.0.0">
  <parent><groupId>com.acme</groupId><artifactId>framework</artifactId><version>4.1.0</version></parent>
  <artifactId>{name}</artifactId>
</project>
""",
            encoding="utf-8",
        )
        compiled = root / "framework" / name / "target" / "classes"
        compiled.mkdir(parents=True)
        (compiled / "Thing.class").write_bytes(b"\xca\xfe\xba\xbe")
    (root / "app" / "pom.xml").write_text(
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <parent><groupId>com.acme</groupId><artifactId>build</artifactId><version>4.1.0</version></parent>
  <artifactId>app</artifactId>
  <dependencies>
    <dependency><groupId>com.acme</groupId><artifactId>common</artifactId><version>4.1.0</version></dependency>
  </dependencies>
</project>
""",
        encoding="utf-8",
    )

    module = MavenDetector().detect(root / "app").modules[0]

    assert module.sibling_coordinates == ("com.acme:common",)


# --- Reactor discovery (2M Task 2) ---------------------------------------

REACTOR = FIXTURE.parent / "orders-reactor"


def test_the_reactor_walk_yields_every_leaf_module_in_declaration_order():
    """`fixtures/orders-reactor/pom.xml` is aggregation-only (2M design §2):
    it is never a module in its own right, only the two `<modules>` entries
    it names — `orders-service`, adopted completely unchanged by a relative
    `<module>` path, and `billing-lib`, a real reactor child declaring
    `<parent>`. `library` is never returned from coordinates alone
    (`_classify`), so the sibling with no service evidence is
    `undetermined`, never guessed at."""
    model = MavenDetector().detect(REACTOR)

    assert [module.module_id for module in model.modules] == [
        "com.acme:orders-service",
        "com.acme:billing-lib",
    ]
    orders_service, billing_lib = model.modules
    assert orders_service.root == FIXTURE
    # No Dockerfile, no `<mainClass>`: same as `test_kind_is_undetermined_
    # when_no_evidence_decides_it` already pins for this fixture detected
    # alone — the reactor walk must not change what evidence `_classify`
    # reads for a module it adopts unchanged.
    assert orders_service.kind == "undetermined"
    assert billing_lib.root == REACTOR / "billing-lib"
    assert billing_lib.version == "1.0.0"
    assert billing_lib.kind == "undetermined"


def test_the_reactor_walk_reads_orders_service_exactly_as_detecting_it_alone_would():
    """The whole point of adopting it by relative path rather than copying it:
    detecting it through the reactor and detecting it directly read the SAME
    `pom.xml`, so the two must agree on every field, not merely on the parts
    this test happens to check."""
    through_reactor = MavenDetector().detect(REACTOR).modules[0]
    alone = MavenDetector().detect(FIXTURE).modules[0]
    assert through_reactor == alone


_AGGREGATOR_POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <groupId>com.acme</groupId>
  <artifactId>agg</artifactId>
  <version>1.0.0</version>
  <packaging>pom</packaging>
  <modules>
    <module>MODULE</module>
  </modules>
</project>
"""


def test_a_modules_cycle_is_refused_with_the_cycle_named(tmp_path: Path):
    """Every other unreadable input in this codebase degrades to an honest
    absence (DR-6); a cycle is not a shape a directory can honestly have, so
    it is refused loudly, with the cycle itself in the message, rather than
    walked forever."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "pom.xml").write_text(_AGGREGATOR_POM.replace("MODULE", "../b"), encoding="utf-8")
    (b / "pom.xml").write_text(_AGGREGATOR_POM.replace("MODULE", "../a"), encoding="utf-8")

    with pytest.raises(ValueError, match="cycle") as failure:
        MavenDetector().detect(a)
    assert str(a.resolve()) in str(failure.value)
    assert str(b.resolve()) in str(failure.value)


def test_multi_module_is_true_for_the_real_reactor_and_false_for_a_plain_module():
    """2M Task 2 fix round 1, F1: the CLI's multi-module gate reads whether
    the TARGETED root itself declared `<modules>`, never `len(modules) >
    1` — a reactor naming exactly one child is still a reactor."""
    assert MavenDetector().detect(REACTOR).multi_module is True
    assert MavenDetector().detect(FIXTURE).multi_module is False


def test_multi_module_is_true_even_when_the_reactor_names_exactly_one_child(tmp_path: Path):
    """The real-world shape this pins: `fixtures/pom.xml` itself names only
    `orders-soap-client`, and a reactor with one child still analyzes that
    child into ITS OWN workspace, not the aggregator's — `len(modules) > 1`
    would have routed it into the single-module branch instead."""
    reactor = tmp_path / "reactor"
    reactor.mkdir()
    (reactor / "pom.xml").write_text(_AGGREGATOR_POM.replace("MODULE", "child"), encoding="utf-8")
    (reactor / "child").mkdir()
    _module(reactor / "child")

    model = MavenDetector().detect(reactor)

    assert model.multi_module is True
    assert len(model.modules) == 1


def test_a_module_naming_a_directory_with_no_pom_is_refused_by_name(tmp_path: Path):
    """2M Task 2 fix round 1, F2: a `<module>` naming a directory that holds
    no `pom.xml` is a mistake in the analysed repository, refused by name —
    never a bare `FileNotFoundError` from the recursive parse underneath."""
    reactor = tmp_path / "reactor"
    reactor.mkdir()
    (reactor / "pom.xml").write_text(_AGGREGATOR_POM.replace("MODULE", "ghost"), encoding="utf-8")
    (reactor / "ghost").mkdir()

    with pytest.raises(ValueError, match="ghost") as failure:
        MavenDetector().detect(reactor)
    assert "no pom.xml" in str(failure.value)


def test_an_empty_module_entry_is_refused_by_name(tmp_path: Path):
    """2M Task 2 fix round 1, F6: a `<module/>` with no path at all names
    nothing — refused loudly rather than silently skipped, the DR-6
    exemption every other malformed `<modules>` shape here already gets."""
    reactor = tmp_path / "reactor"
    reactor.mkdir()
    (reactor / "pom.xml").write_text(_AGGREGATOR_POM.replace("MODULE", ""), encoding="utf-8")

    with pytest.raises(ValueError, match="empty <module/>"):
        MavenDetector().detect(reactor)


def test_a_child_named_twice_in_one_modules_list_is_analyzed_once(tmp_path: Path):
    """2M Task 2 fix round 1, F6: a parent listing the same child by two
    spellings (`child` and `./child`) analyzes it once, not once per
    spelling — the duplicate is a naming accident, not two modules."""
    reactor = tmp_path / "reactor"
    reactor.mkdir()
    pom = _AGGREGATOR_POM.replace(
        "<module>MODULE</module>", "<module>child</module>\n    <module>./child</module>"
    )
    (reactor / "pom.xml").write_text(pom, encoding="utf-8")
    (reactor / "child").mkdir()
    _module(reactor / "child")

    model = MavenDetector().detect(reactor)

    assert len(model.modules) == 1


def test_packaging_defaults_to_jar_when_the_pom_declares_none(tmp_path: Path):
    """Maven's own default (2M design §2, ruled amendment) — not a guess
    this detector invents: `<packaging>` absent means `jar`, the same value
    a real Maven build would use."""
    assert MavenDetector().detect(_module(tmp_path)).modules[0].packaging == "jar"


def test_packaging_is_read_from_the_pom_when_declared(tmp_path: Path):
    pom = _BARE_POM.replace("</project>", "  <packaging>pom</packaging>\n</project>")
    assert MavenDetector().detect(_module(tmp_path, pom)).modules[0].packaging == "pom"


def test_a_missing_coordinate_refusal_names_the_pom_it_came_from(tmp_path: Path):
    """2M final review wave, MINOR 3: `_text`'s refusal used to read
    "pom.xml has no <groupId>" — unactionable the moment more than one pom
    exists, as every reactor child does. It now names the exact pom.xml this
    reading failed against."""
    pom = _BARE_POM.replace("  <groupId>com.acme</groupId>\n", "")

    with pytest.raises(ValueError, match="groupId") as failure:
        MavenDetector().detect(_module(tmp_path, pom))
    assert str(tmp_path / "pom.xml") in str(failure.value)


def test_a_malformed_pom_is_refused_by_name_not_a_bare_parse_error(tmp_path: Path):
    """2M final review wave, I2: `ElementTree.ParseError` subclasses
    `SyntaxError`, not `ValueError`, and names no file on its own — a
    traceback rather than a message once it reaches the CLI. `_parse_pom`
    catches it here and re-raises with the pom.xml that failed to parse."""
    (tmp_path / "pom.xml").write_text("<project><groupId>oops</project>", encoding="utf-8")

    with pytest.raises(ValueError) as failure:
        MavenDetector().detect(tmp_path)
    assert str(tmp_path / "pom.xml") in str(failure.value)


def test_an_empty_modules_list_is_refused_by_name(tmp_path: Path):
    """2M final review wave, MINOR 4: `<modules/>` naming zero children used
    to walk to nothing and analyze successfully with no output — a
    `render`/`enrich`/`export` later pointed at that empty reactor root then
    hit `_refuse_if_unanalyzed`'s own bare "one of: " listing with nothing
    after it. Refused here instead, by the pom that declares the empty
    `<modules>`."""
    reactor = tmp_path / "reactor"
    reactor.mkdir()
    empty = _AGGREGATOR_POM.replace("    <module>MODULE</module>\n", "")
    (reactor / "pom.xml").write_text(empty, encoding="utf-8")

    with pytest.raises(ValueError, match="declares <modules> but names none") as failure:
        MavenDetector().detect(reactor)
    assert str(reactor / "pom.xml") in str(failure.value)


# --- F1: the RESOLVED dependency set, with versions --------------------------
#
# The measurement that motivated it: `mall-admin`, a real Spring MVC module
# with 160 endpoints, declares five coordinates and not one of them is Spring,
# because its starters arrive through the reactor parent. Reading the module's
# own `<dependencies>` alone had `resolve/dependencies.py` skipping every such
# module. Everything below is built from pom files in `tmp_path` and a local
# repository under a monkeypatched `HOME` — no `mvn`, no network, no build.

_PARENT_POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.acme</groupId>
  <artifactId>acme-parent</artifactId>
  <version>2.3.0</version>
  <packaging>pom</packaging>
  <properties>
    <stream.version>4.1.0</stream.version>
  </properties>
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-web</artifactId>
        <version>6.1.6</version>
      </dependency>
    </dependencies>
  </dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.springframework.cloud</groupId>
      <artifactId>spring-cloud-stream</artifactId>
      <version>${stream.version}</version>
    </dependency>
  </dependencies>
</project>
"""

_INHERITING_POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>com.acme</groupId>
    <artifactId>acme-parent</artifactId>
    <version>2.3.0</version>
    <relativePath>../pom.xml</relativePath>
  </parent>
  <artifactId>orders</artifactId>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-web</artifactId>
    </dependency>
  </dependencies>
</project>
"""


def _reactor(tmp_path: Path, child_pom: str = _INHERITING_POM) -> Path:
    """A parent pom and one child beside it, the ordinary shape of every
    multi-module Maven repository."""
    (tmp_path / "pom.xml").write_text(_PARENT_POM, encoding="utf-8")
    child = tmp_path / "orders"
    child.mkdir()
    (child / "pom.xml").write_text(child_pom, encoding="utf-8")
    return child


def _published_pom(home: Path, coordinate: str, version: str, body: str) -> Path:
    """One pom in the local Maven repository, at the layout a build leaves it
    in — which is the only place a parent or a BOM from OUTSIDE the repository
    can be read from without running Maven or reaching the network."""
    group, _, artifact = coordinate.partition(":")
    directory = home / ".m2" / "repository" / Path(*group.split(".")) / artifact / version
    directory.mkdir(parents=True, exist_ok=True)
    published = directory / f"{artifact}-{version}.pom"
    published.write_text(body, encoding="utf-8")
    return published


def test_a_dependency_declared_only_by_the_parent_is_in_the_modules_set(tmp_path: Path):
    """F1's whole point, and the live defect it closes: Maven puts a parent's
    own `<dependencies>` on the child's classpath, so a module inheriting a
    Spring Cloud Stream starter DEPENDS on it. Recorded as direct declarations
    alone, that module's `config_join` catalogs were skipped — visibly, but
    skipped — on a build that genuinely has the framework."""
    module = MavenDetector().detect(_reactor(tmp_path)).modules[0]

    assert "org.springframework.cloud:spring-cloud-stream" in module.dependency_coordinates
    assert list(module.dependency_coordinates) == sorted(module.dependency_coordinates)


def test_an_inherited_version_and_a_managed_one_both_resolve(tmp_path: Path):
    """Two ladders in one module: the parent's own dependency carries a
    `${...}` property the parent defines, and the child's own dependency
    carries no version at all and takes the parent's
    `<dependencyManagement>`. Neither was readable before F1."""
    module = MavenDetector().detect(_reactor(tmp_path)).modules[0]

    assert module.dependency_versions == {
        "org.springframework:spring-web": "6.1.6",
        "org.springframework.cloud:spring-cloud-stream": "4.1.0",
    }
    assert module.dependencies_not_resolved == ()


def test_the_childs_own_declaration_beats_the_version_its_parent_manages(tmp_path: Path):
    """Maven's precedence, kept: a version written on the declaration wins over
    a managed one. Reading them the other way round would report a release the
    build does not use — a wrong version is worse than none, because a
    version-scoped rule would then apply confidently and wrongly."""
    child = _INHERITING_POM.replace(
        "<artifactId>spring-web</artifactId>",
        "<artifactId>spring-web</artifactId>\n      <version>6.2.1</version>",
    )
    module = MavenDetector().detect(_reactor(tmp_path, child)).modules[0]

    assert module.dependency_versions["org.springframework:spring-web"] == "6.2.1"


def test_a_property_the_module_redefines_wins_over_the_parents(tmp_path: Path):
    """Interpolation happens in the CHILD's merged property context, nearest
    wins — the same inheritance rule the dependency maps follow, applied to the
    values they are written in terms of."""
    child = _INHERITING_POM.replace(
        "<artifactId>orders</artifactId>",
        "<artifactId>orders</artifactId>\n  <properties>"
        "<stream.version>4.2.0</stream.version></properties>",
    )
    module = MavenDetector().detect(_reactor(tmp_path, child)).modules[0]

    assert module.dependency_versions["org.springframework.cloud:spring-cloud-stream"] == "4.2.0"


def test_a_parent_outside_the_repository_is_read_from_the_local_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """`spring-boot-starter-parent` is not in anybody's repository, and it is
    where most of a Boot application's versions live. A successful build —
    M02's stated prerequisite — has already left its pom in the local
    repository, and reading a file that is already there is neither a build
    nor a network call."""
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    _published_pom(
        home,
        "com.vendor:vendor-parent",
        "9.9.9",
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <groupId>com.vendor</groupId><artifactId>vendor-parent</artifactId><version>9.9.9</version>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.1.6</version>
    </dependency>
  </dependencies>
</project>
""",
    )
    root = tmp_path / "module"
    root.mkdir()
    _module(
        root,
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <parent>
    <groupId>com.vendor</groupId><artifactId>vendor-parent</artifactId><version>9.9.9</version>
  </parent>
  <artifactId>orders</artifactId>
</project>
""",
    )

    module = MavenDetector().detect(root).modules[0]

    assert module.dependency_versions == {"org.springframework:spring-context": "6.1.6"}
    assert module.dependencies_not_resolved == ()


def test_an_imported_bom_answers_for_the_versions_it_manages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """`<type>pom</type><scope>import</scope>` is how a Boot or a Spring Cloud
    application gets almost every version it has. The BOM's own entries are
    resolved in the BOM's property context, not the importing module's: they
    are different namespaces, and answering one from the other would settle a
    version on a value that never applied to it."""
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    _published_pom(
        home,
        "com.vendor:vendor-bom",
        "1.2.3",
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <groupId>com.vendor</groupId><artifactId>vendor-bom</artifactId><version>1.2.3</version>
  <properties><jackson.version>2.17.2</jackson.version></properties>
  <dependencyManagement><dependencies>
    <dependency>
      <groupId>com.fasterxml.jackson.core</groupId>
      <artifactId>jackson-databind</artifactId>
      <version>${jackson.version}</version>
    </dependency>
  </dependencies></dependencyManagement>
</project>
""",
    )
    root = tmp_path / "module"
    root.mkdir()
    _module(
        root,
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <groupId>com.acme</groupId><artifactId>orders</artifactId><version>1.0.0</version>
  <dependencyManagement><dependencies>
    <dependency>
      <groupId>com.vendor</groupId><artifactId>vendor-bom</artifactId><version>1.2.3</version>
      <type>pom</type><scope>import</scope>
    </dependency>
  </dependencies></dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.fasterxml.jackson.core</groupId>
      <artifactId>jackson-databind</artifactId>
    </dependency>
  </dependencies>
</project>
""",
    )

    module = MavenDetector().detect(root).modules[0]

    assert module.dependency_versions == {"com.fasterxml.jackson.core:jackson-databind": "2.17.2"}


def test_a_bom_managing_its_own_artifacts_by_project_version_resolves_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """`${project.version}` is a Maven BUILT-IN — the version of the pom the element is
    written in — and it is NOT an entry in any `<properties>` block. It is how a Spring
    Cloud component BOM versions its own artifacts: measured at
    `scripts/probes/cp35_bom_chain.md`, 6 of 8 managed entries in
    `spring-cloud-gateway-dependencies:5.0.0` are spelled exactly this way, and so is every
    one of the four starters `spring-petclinic-api-gateway` declares.

    Interpolating only from `<properties>` resolved nothing for it and `_managed_versions`
    dropped the entry with no message, so a whole route table derived nothing while the
    symptom read as a BOM that had never been opened (`OI-139`)."""
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    _published_pom(
        home,
        "com.vendor:vendor-bom",
        "5.0.0",
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <groupId>com.vendor</groupId><artifactId>vendor-bom</artifactId><version>5.0.0</version>
  <dependencyManagement><dependencies>
    <dependency>
      <groupId>com.vendor</groupId><artifactId>vendor-starter</artifactId>
      <version>${project.version}</version>
    </dependency>
  </dependencies></dependencyManagement>
</project>
""",
    )
    root = tmp_path / "module"
    root.mkdir()
    _module(
        root,
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <groupId>com.acme</groupId><artifactId>orders</artifactId><version>1.0.0</version>
  <dependencyManagement><dependencies>
    <dependency>
      <groupId>com.vendor</groupId><artifactId>vendor-bom</artifactId><version>5.0.0</version>
      <type>pom</type><scope>import</scope>
    </dependency>
  </dependencies></dependencyManagement>
  <dependencies>
    <dependency><groupId>com.vendor</groupId><artifactId>vendor-starter</artifactId></dependency>
  </dependencies>
</project>
""",
    )

    module = MavenDetector().detect(root).modules[0]

    assert module.dependency_versions == {"com.vendor:vendor-starter": "5.0.0"}
    assert module.dependencies_not_resolved == ()


def test_project_version_in_a_bom_is_the_boms_own_version_never_the_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The scope rule, asserted where getting it wrong is INVISIBLE rather than loud. If
    `${project.version}` were answered from the importing module's model, this module's
    `9.9.9` would be written into the version map and the coordinate
    `com.vendor:vendor-starter:9.9.9` would simply not exist — a silent wrong answer where
    today there is an honest `dependencies_not_resolved` entry. The two versions are
    deliberately far apart so a passing test cannot be a coincidence."""
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    _published_pom(
        home,
        "com.vendor:vendor-bom",
        "1.2.3",
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <groupId>com.vendor</groupId><artifactId>vendor-bom</artifactId><version>1.2.3</version>
  <dependencyManagement><dependencies>
    <dependency>
      <groupId>com.vendor</groupId><artifactId>vendor-starter</artifactId>
      <version>${project.version}</version>
    </dependency>
  </dependencies></dependencyManagement>
</project>
""",
    )
    root = tmp_path / "module"
    root.mkdir()
    _module(
        root,
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <groupId>com.acme</groupId><artifactId>orders</artifactId><version>9.9.9</version>
  <dependencyManagement><dependencies>
    <dependency>
      <groupId>com.vendor</groupId><artifactId>vendor-bom</artifactId><version>1.2.3</version>
      <type>pom</type><scope>import</scope>
    </dependency>
  </dependencies></dependencyManagement>
  <dependencies>
    <dependency><groupId>com.vendor</groupId><artifactId>vendor-starter</artifactId></dependency>
  </dependencies>
</project>
""",
    )

    module = MavenDetector().detect(root).modules[0]

    assert module.dependency_versions == {"com.vendor:vendor-starter": "1.2.3"}


def test_a_managed_version_an_imported_bom_cannot_settle_is_named_not_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The defect worth fixing beyond the one property. `_managed_versions` had no `else`
    on its `if settled is not None:`, so an entry whose version named nothing readable
    vanished from the map AND from the reasons — and a module then reported a dependency
    unresolved for a cause nothing on the page could explain.

    A module's OWN unresolvable version has always been named
    (`test_a_version_nobody_could_resolve_is_named_rather_than_guessed`); one an imported
    BOM manages was not. Same discipline, one level further out."""
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    _published_pom(
        home,
        "com.vendor:vendor-bom",
        "1.2.3",
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <groupId>com.vendor</groupId><artifactId>vendor-bom</artifactId><version>1.2.3</version>
  <dependencyManagement><dependencies>
    <dependency>
      <groupId>com.vendor</groupId><artifactId>vendor-starter</artifactId>
      <version>${nobody.defines.this}</version>
    </dependency>
  </dependencies></dependencyManagement>
</project>
""",
    )
    root = tmp_path / "module"
    root.mkdir()
    _module(
        root,
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <groupId>com.acme</groupId><artifactId>orders</artifactId><version>1.0.0</version>
  <dependencyManagement><dependencies>
    <dependency>
      <groupId>com.vendor</groupId><artifactId>vendor-bom</artifactId><version>1.2.3</version>
      <type>pom</type><scope>import</scope>
    </dependency>
  </dependencies></dependencyManagement>
  <dependencies>
    <dependency><groupId>com.vendor</groupId><artifactId>vendor-starter</artifactId></dependency>
  </dependencies>
</project>
""",
    )

    module = MavenDetector().detect(root).modules[0]

    assert module.dependency_versions == {}
    assert any(
        "vendor-starter" in reason and "nobody.defines.this" in reason
        for reason in module.dependencies_not_resolved
    ), module.dependencies_not_resolved


def test_a_version_nobody_could_resolve_is_named_rather_than_guessed(tmp_path: Path):
    """FR-17, the same discipline `libraries_not_resolved` keeps. The
    coordinate is still in the SET — the module does depend on it, and the
    dependency gate must see it — but it is absent from the version map, and
    the reason says which of the two failures it was. An unexpanded
    `${jackson.version}` written into the map would be a release nobody cut."""
    root = tmp_path / "module"
    root.mkdir()
    _module(
        root,
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <groupId>com.acme</groupId><artifactId>orders</artifactId><version>1.0.0</version>
  <dependencies>
    <dependency><groupId>com.acme</groupId><artifactId>unmanaged</artifactId></dependency>
    <dependency>
      <groupId>com.acme</groupId><artifactId>propertied</artifactId>
      <version>${nobody.defines.this}</version>
    </dependency>
  </dependencies>
</project>
""",
    )

    module = MavenDetector().detect(root).modules[0]

    assert module.dependency_coordinates == ("com.acme:propertied", "com.acme:unmanaged")
    assert module.dependency_versions == {}
    assert module.dependencies_not_resolved == (
        (
            "com.acme:propertied: version `${nobody.defines.this}` names a property no pom "
            "this analysis could read defines"
        ),
        (
            "com.acme:unmanaged: no version on the declaration and none managed by any pom "
            "this analysis could read"
        ),
    )


def test_a_parent_nobody_can_open_is_named_and_the_module_still_detects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A machine that never built this module has no parent pom to read, and
    the analysis must degrade visibly rather than refuse: the module detects,
    its own declarations are recorded, and the ancestor it could not open is
    named — with a repository-RELATIVE location, since a path under someone's
    home identifies nothing off the machine that wrote it (D00 §2).

    `HOME` is moved to an empty directory so the assertion is about this
    resolution and not about whatever the developer's own local repository
    happens to hold."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkey = tmp_path / "module"
    monkey.mkdir()
    _module(
        monkey,
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <parent>
    <groupId>com.vendor</groupId><artifactId>absent-parent</artifactId><version>9.9.9</version>
  </parent>
  <groupId>com.acme</groupId><artifactId>orders</artifactId><version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-web</artifactId>
      <version>6.1.6</version>
    </dependency>
  </dependencies>
</project>
""",
    )

    module = MavenDetector().detect(monkey).modules[0]

    assert module.dependency_versions == {"org.springframework:spring-web": "6.1.6"}
    [reason] = module.dependencies_not_resolved
    assert reason.startswith("com.vendor:absent-parent:9.9.9: no parent pom on disk")
    assert "com/vendor/absent-parent/9.9.9/absent-parent-9.9.9.pom" in reason
    assert str(Path.home()) not in reason


def test_a_relative_path_pointing_at_someone_elses_pom_is_not_read_as_the_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Maven checks that the pom at `<relativePath>` declares the coordinates
    the `<parent>` element names, and so does this. An aggregator that is NOT
    this module's parent sits at `../pom.xml` in plenty of real layouts, and
    inheriting its properties and dependencies would be a fabrication — the
    module would be reported as depending on something no build puts on its
    classpath."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    child = _reactor(tmp_path, _INHERITING_POM.replace("acme-parent", "other-parent"))

    module = MavenDetector().detect(child).modules[0]

    # `spring-cloud-stream` is the neighbouring pom's own dependency and must
    # not appear; the child's own declaration stays, versionless and named.
    assert module.dependency_coordinates == ("org.springframework:spring-web",)
    assert module.dependency_versions == {}
    assert module.dependencies_not_resolved[0].startswith("com.acme:other-parent:2.3.0")


def test_the_fixture_resolves_a_version_for_every_coordinate_it_declares():
    """The committed fixture pins every version on the declaration, so the two
    maps describe the same set — which is what makes it the control for every
    case above: a shortfall there is the resolution's, not the fixture's."""
    module = MavenDetector().detect(FIXTURE).modules[0]

    assert set(module.dependency_versions) == set(module.dependency_coordinates)
    assert module.dependencies_not_resolved == ()
    assert module.dependency_versions["org.springframework:spring-web"] == "6.1.6"


def _pom(tmp_path: Path, body: str) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "pom.xml").write_text(
        '<project xmlns="http://maven.apache.org/POM/4.0.0">'
        "<groupId>com.acme</groupId><artifactId>m</artifactId><version>1.0.0</version>"
        f"{body}</project>",
        encoding="utf-8",
    )
    return tmp_path


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        # The modern spelling, and the one a reader should reach for.
        ("<properties><maven.compiler.release>21</maven.compiler.release></properties>", 21),
        # The legacy `1.x` spelling is still what older builds carry on
        # `<target>`/`<source>`, and reading only the bare form would miss half
        # the estate.
        ("<properties><maven.compiler.target>1.8</maven.compiler.target></properties>", 8),
        ("<properties><maven.compiler.source>11</maven.compiler.source></properties>", 11),
        # Spring Boot's parent sets this one and nothing else.
        ("<properties><java.version>17</java.version></properties>", 17),
        # Plugin configuration WINS over the property, because
        # `maven.compiler.release` is only the default expression for that
        # parameter — an explicit `<release>` overrides it, and reading the
        # property first would report a release the build does not use.
        (
            (
                "<properties><maven.compiler.release>11</maven.compiler.release></properties>"
                "<build><plugins><plugin>"
                "<artifactId>maven-compiler-plugin</artifactId>"
                "<configuration><release>21</release></configuration>"
                "</plugin></plugins></build>"
            ),
            21,
        ),
        # A property nothing defines is not a release. Refusing to guess is the
        # point: `None` sends multi-release selection to its next source
        # (the module's own class-file major) rather than to a wrong answer.
        ("<properties><maven.compiler.release>${jdk}</maven.compiler.release></properties>", None),
        # A build declaring none reports absence, never a default.
        ("", None),
    ],
)
def test_the_declared_release_is_read_where_the_build_states_it(
    tmp_path: Path, body: str, expected: int | None
):
    """W3b. §8.2 admits this value: it is written in the pom, so it is code
    rather than a deployment possibility. Its consumer is multi-release
    selection — which overlay of a dependency's class actually loads is a
    property of the module doing the depending, and this is where that module
    says so. Nothing read any of these keys before."""
    [module] = MavenDetector().detect(_pom(tmp_path / "m", body)).modules
    assert module.declared_release == expected


# --- Maven's own classpath (spec 2026-10-21) -------------------------------------------


def _no_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every `detect` below that must not start Maven is run under this: a start is a
    test failure with the argv in it, not a slow pass."""

    def refuse(argv, **_kwargs):
        raise AssertionError(f"mvn was started: {argv}")

    monkeypatch.setattr(maven_module.subprocess, "run", refuse)


_DEPENDS = "<dependencies><dependency><groupId>org.example</groupId><artifactId>lib</artifactId><version>1.2</version></dependency></dependencies>"
# A module that DECLARES a dependency: the other precondition `_ask_maven` checks — a POM
# compiling against nothing but the platform has no classpath worth asking for.
_DEPENDENT_POM = _BARE_POM.replace("</project>", f"{_DEPENDS}</project>")


def _built(module_dir: Path, pom: str = _DEPENDENT_POM) -> Path:
    """A module with something BUILT: the POM, and a class under `target/classes` — the
    precondition `_ask_maven` checks before it starts a process."""
    module_dir.mkdir(parents=True, exist_ok=True)
    _module(module_dir, pom)
    classes = module_dir / "target" / "classes"
    classes.mkdir(parents=True, exist_ok=True)
    (classes / "Thing.class").write_bytes(b"\xca\xfe\xba\xbe")
    return module_dir


def _classpath_file(module_dir: Path, entries: list[Path]) -> Path:
    file = module_dir / "target" / "sextant-classpath.txt"
    file.write_text(os.pathsep.join(str(entry) for entry in entries), encoding="utf-8")
    return file


@pytest.mark.pins("detect.a-POM-with-nothing-built-starts-no-process")
def test_a_temporary_pom_detect_starts_no_process_and_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Spec §4: the unit suite writes temporary POMs by the dozen, and none of them has
    compiled output — so there is nothing a classpath could be read FOR, and the
    detector must refuse the question before any process starts. The declared set is the
    answer, LABELLED (ruling b), with the precondition as the reason."""
    _no_process(monkeypatch)
    monkeypatch.setattr(maven_module.shutil, "which", lambda _name: "/usr/bin/mvn")
    module = MavenDetector().detect(_module(tmp_path)).modules[0]
    assert module.dependency_source == "declared"
    assert module.dependency_source_reason is not None
    assert "target/classes" in module.dependency_source_reason


def test_no_mvn_on_path_is_the_reason_not_a_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _no_process(monkeypatch)
    monkeypatch.setattr(maven_module.shutil, "which", lambda _name: None)
    module = MavenDetector().detect(_built(tmp_path)).modules[0]
    assert module.dependency_source == "declared"
    assert "`mvn` is not on PATH" in (module.dependency_source_reason or "")


@pytest.mark.pins("detect.mavens-FILE-feeds-archives-coordinates-and-siblings")
def test_mavens_file_feeds_archives_coordinates_and_siblings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Spec §3b, from a CAPTURED file, no Maven involved (2M design §4's rule): a jar
    under the local repository names its coordinate and version by the repository
    layout; a reactor sibling's `target/classes` directory is a library root named by its
    OWN POM; an entry that is neither is reported by its path with its reason. The file
    is newer than the POM, so the re-use rule (§3d) holds and no process starts."""
    _no_process(monkeypatch)
    monkeypatch.setattr(maven_module.shutil, "which", lambda _name: "/usr/bin/mvn")
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    jar = home / ".m2" / "repository" / "org" / "example" / "lib" / "1.2" / "lib-1.2.jar"
    jar.parent.mkdir(parents=True)
    jar.write_bytes(b"PK")
    sibling = _built(
        tmp_path / "sib",
        _DEPENDENT_POM.replace("<artifactId>thing</artifactId>", "<artifactId>sib</artifactId>"),
    )
    module = _built(tmp_path / "m")
    stray = tmp_path / "elsewhere" / "local.jar"
    _classpath_file(module, [jar, sibling / "target" / "classes", stray])

    detected = MavenDetector().detect(module).modules[0]

    assert detected.dependency_source == "maven"
    assert detected.dependency_source_reason is None
    assert detected.dependency_archives == (
        LibraryRoot(coordinate="org.example:lib", version="1.2", archive=jar),
    )
    assert detected.dependency_coordinates == ("org.example:lib",)
    assert detected.dependency_versions == {"org.example:lib": "1.2"}
    assert detected.dependencies_not_resolved == ()
    assert LibraryRoot("com.acme:sib", "1.0.0", sibling / "target" / "classes") in (
        detected.library_roots
    )
    assert any(str(stray) in reason for reason in detected.libraries_not_resolved)


@pytest.mark.pins("detect.a-STALE-file-asks-maven-offline-and-online-only-under-the-flag")
def test_a_stale_file_asks_maven_offline_and_online_only_under_the_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """M02's posture, ruling (a)/(b): offline first; the offline refusal is retried
    online exactly once and only under `allow_resolve`; a failure is the module's reason
    in Maven's own words, never an exception. A single module gets no `compile` phase and
    no `-pl` (spec §2, fact 2). The file is OLDER than the POM here, so §3d's re-use rule
    does not hold and Maven is asked."""
    monkeypatch.setattr(maven_module.shutil, "which", lambda _name: "/usr/bin/mvn")
    module = _built(tmp_path)
    file = _classpath_file(module, [])
    stale = (module / "pom.xml").stat().st_mtime - 60
    os.utime(file, (stale, stale))
    calls: list[tuple[list[str], Path]] = []

    def fake_run(argv, *, cwd, **_kwargs):
        calls.append((list(argv), Path(cwd)))
        return subprocess.CompletedProcess(
            argv, 1, stdout="", stderr="[ERROR] Cannot access central in offline mode\n"
        )

    monkeypatch.setattr(maven_module.subprocess, "run", fake_run)

    detected = MavenDetector().detect(module).modules[0]
    assert [argv[:4] for argv, _ in calls] == [["mvn", "-o", "-q", "-B"]]
    assert "compile" not in calls[0][0] and "-pl" not in calls[0][0]
    assert calls[0][1] == module
    assert detected.dependency_source == "declared"
    assert detected.dependency_source_reason == "Cannot access central in offline mode"

    calls.clear()
    MavenDetector().detect(module, allow_resolve=True)
    assert len(calls) == 2
    assert "-o" in calls[0][0] and "-o" not in calls[1][0]


@pytest.mark.pins("detect.a-reactor-CHILD-is-asked-from-the-root-with-compile-attached")
def test_a_reactor_child_is_asked_from_the_root_with_pl_and_compile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Spec §2, fact 2: inside a reactor the goal resolves a sibling only as a built
    artifact of the same session, and a module directory cannot even read its own
    import-POMs — so Maven is started from the ROOT, told `-pl <this module> -am`, with
    `compile` attached. Maven here returns success and writes nothing, and the module
    says so rather than reading a file that is not there."""
    monkeypatch.setattr(maven_module.shutil, "which", lambda _name: "/usr/bin/mvn")
    root = tmp_path / "reactor"
    root.mkdir()
    _module(
        root,
        _BARE_POM.replace(
            "<artifactId>thing</artifactId>", "<artifactId>reactor</artifactId>"
        ).replace(
            "</project>",
            "<packaging>pom</packaging><modules><module>a</module></modules></project>",
        ),
    )
    child = _built(
        root / "a",
        _CHILD_POM.replace("acme-parent", "reactor")
        .replace("2.3.0", "1.0.0")
        .replace("</project>", f"{_DEPENDS}</project>"),
    )
    calls: list[tuple[list[str], Path]] = []

    def fake_run(argv, *, cwd, **_kwargs):
        calls.append((list(argv), Path(cwd)))
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(maven_module.subprocess, "run", fake_run)
    detected = MavenDetector().detect(child).modules[0]

    [(argv, cwd)] = calls
    assert cwd == root
    assert "compile" in argv
    assert argv[argv.index("-pl") + 1] == "a" and "-am" in argv
    assert detected.dependency_source == "declared"
    assert "wrote no current target/sextant-classpath.txt" in (
        detected.dependency_source_reason or ""
    )


def test_mavens_reason_is_its_last_named_error_line():
    output = "[ERROR] Failed to execute goal\n[ERROR] dependency: x:y:jar:1 (test)\n[ERROR] \n[ERROR] -> [Help 1]\n"
    assert MavenDetector._maven_reason(output, 1) == "dependency: x:y:jar:1 (test)"
    assert MavenDetector._maven_reason("", 7) == "mvn exited 7 and printed nothing"
