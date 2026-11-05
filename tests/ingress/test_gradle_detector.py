import json
import subprocess
from pathlib import Path

import pytest

from sextant.ingress.detect import gradle as gradle_module
from sextant.ingress.detect.gradle import (
    GradleDetector,
    _compose_argv,
    _distribution_absent_message,
)

FIXTURE = Path(__file__).parents[2] / "fixtures" / "gradle-orders"


def _load_capture() -> dict:
    """The committed capture (2M Task 3 fix round 1, C1): every absolute path
    the real wrapper reported on the machine that recorded it is stored as a
    portable placeholder — `{root}` for fixtures/gradle-orders's own root,
    `{home}` for the Gradle user home the classpath entries sit under —
    substituted back at LOAD TIME against whatever THIS checkout's own paths
    actually are. Fixes 3 unit tests that read a hardcoded `/Users/...` path
    baked into the committed JSON, red from any other checkout root (CI's
    `/home/runner` among them) — and stops a real machine's home directory
    leaking into the repository (M6)."""
    raw = (Path(__file__).parent / "gradle-captures" / "gradle-orders.json").read_text(
        encoding="utf-8"
    )
    normalized = raw.replace("{root}", str(FIXTURE)).replace("{home}", str(Path.home()))
    return json.loads(normalized)


CAPTURE = _load_capture()


def _repository_model(data: dict, wrapper_note: str | None = None):
    return GradleDetector._repository_model(FIXTURE, data, wrapper_note)


def _minimal_project(
    *,
    path: str = ":thing",
    group: str = "com.acme",
    name: str = "thing",
    version: str = "1.0.0",
    dir_: str = "/repo/thing",
    source_roots: list[str] | None = None,
    classes_dirs: list[str] | None = None,
) -> dict:
    """A bare, filesystem-independent project record — for tests that only
    exercise `_repository_model`'s own translation (notes, module selection)
    and never reach `_module_of`'s `is_dir()` checks (M1) because the
    project in question is never turned into a `ModuleModel` (the root
    aggregator) or the test does not care about source/resource roots."""
    return {
        "path": path,
        "group": group,
        "name": name,
        "version": version,
        "dir": dir_,
        "sourceRoots": source_roots or [],
        "sourceLanguages": {root: ["java"] for root in source_roots or []},
        "resourceRoots": [],
        "classesDirs": classes_dirs or [],
        "publishing": False,
        "classpath": [],
    }


# --- accepts() -------------------------------------------------------------


@pytest.mark.parametrize("settings_file", ["settings.gradle", "settings.gradle.kts"])
def test_accepts_true_when_a_settings_file_sits_at_the_root(tmp_path: Path, settings_file: str):
    (tmp_path / settings_file).write_text("", encoding="utf-8")
    assert GradleDetector().accepts(tmp_path)


@pytest.mark.parametrize("build_file", ["build.gradle", "build.gradle.kts"])
def test_accepts_true_for_a_single_module_build_with_no_settings_file(
    tmp_path: Path, build_file: str
):
    (tmp_path / build_file).write_text("", encoding="utf-8")
    assert GradleDetector().accepts(tmp_path)


def test_accepts_false_when_the_directory_has_no_gradle_files(tmp_path: Path):
    assert not GradleDetector().accepts(tmp_path)


def test_accepts_true_for_the_real_fixture():
    assert GradleDetector().accepts(FIXTURE)


# --- the composed argv (2M design §1, pinned as data) ----------------------


def test_the_offline_argv_carries_offline_before_the_shared_flags():
    argv = _compose_argv(["./gradlew"], Path("/init.gradle"), Path("/out"), offline=True)
    assert argv == [
        "./gradlew",
        "--offline",
        "--init-script",
        "/init.gradle",
        "--no-configuration-cache",
        "--continue",
        "-q",
        "sextantBuild",
        "sextantModel",
        "-Psextant.outDir=/out",
    ]


def test_the_online_retry_argv_drops_offline_but_keeps_the_rest():
    argv = _compose_argv(["./gradlew"], Path("/init.gradle"), Path("/out"), offline=False)
    assert argv == [
        "./gradlew",
        "--init-script",
        "/init.gradle",
        "--no-configuration-cache",
        "--continue",
        "-q",
        "sextantBuild",
        "sextantModel",
        "-Psextant.outDir=/out",
    ]


def _project_record(path: str, name: str) -> dict:
    return {
        "path": path,
        "group": "com.acme",
        "name": name,
        "version": "1.0",
        "dir": f"/repo/{name}",
        "sourceRoots": [f"/repo/{name}/src/main/java"],
        "sourceLanguages": {f"/repo/{name}/src/main/java": ["java"]},
        "resourceRoots": [],
        "classesDirs": [f"/repo/{name}/build/classes/java/main"],
        "declaredRelease": 21,
        "publishing": False,
        "classpath": [],
        "target": None,
        "platform": None,
    }


def test_assemble_reads_one_file_per_project(tmp_path: Path):
    """Each project's own `sextantModel` task writes its own file (Android design M4), and
    the root's `sextantBuild` names every project; the detector joins them, in path order."""
    lib = _project_record(":pricing-lib", "pricing-lib")
    app = _project_record(":service-app", "service-app")
    build = {
        "projects": [
            {key: record[key] for key in ("path", "group", "name", "version", "dir")}
            for record in (app, lib)
        ],
        "includedBuilds": ["tools"],
    }
    (tmp_path / "build.json").write_text(json.dumps(build), encoding="utf-8")
    (tmp_path / "projects").mkdir()
    (tmp_path / "projects" / "_service-app.json").write_text(json.dumps([app]), encoding="utf-8")
    (tmp_path / "projects" / "_pricing-lib.json").write_text(json.dumps([lib]), encoding="utf-8")

    assembled = gradle_module._assemble(tmp_path)

    assert assembled["projects"] == [lib, app]
    assert assembled["includedBuilds"] == ["tools"]


def test_assemble_gives_a_project_with_no_file_one_record_with_empty_lists(tmp_path: Path):
    identity = {
        "path": ":docs",
        "group": "",
        "name": "docs",
        "version": "unspecified",
        "dir": "/repo/docs",
    }
    (tmp_path / "build.json").write_text(
        json.dumps({"projects": [identity], "includedBuilds": []}), encoding="utf-8"
    )

    [record] = gradle_module._assemble(tmp_path)["projects"]

    assert record["path"] == ":docs"
    assert record["classesDirs"] == [] and record["sourceRoots"] == []
    assert record["classpath"] == [] and record["target"] is None
    assert "buildFailure" not in record


# --- the translation from captured JSON to RepositoryModel/ModuleModel -----


def test_the_real_fixtures_capture_is_multi_module_with_both_subprojects_in_path_order():
    model = _repository_model(CAPTURE)
    assert model.multi_module is True
    assert [module.module_id for module in model.modules] == [
        "com.acme:pricing-lib",
        "com.acme:service-app",
    ]


def test_the_real_fixture_has_no_composite_build_or_root_source_notes():
    """Neither boundary arises for this fixture — an empty `notes` proves the
    new checks (I1, I2) do not fire on an ordinary multi-module build."""
    assert _repository_model(CAPTURE).notes == ()


def test_the_root_aggregator_project_never_becomes_a_module():
    """Gradle's own `:` path is the aggregator, exactly as an aggregation-only
    POM's own element is never a `ModuleModel` (2M design §2) — only the
    named children are."""
    model = _repository_model(CAPTURE)
    assert all(module.root != FIXTURE for module in model.modules)


def test_coordinates_and_version_come_from_the_projects_own_group_name_version():
    model = _repository_model(CAPTURE)
    pricing_lib = next(m for m in model.modules if m.module_id == "com.acme:pricing-lib")
    assert pricing_lib.coordinates == "com.acme/pricing-lib"
    assert pricing_lib.version == "1.0.0"
    assert pricing_lib.root == FIXTURE / "pricing-lib"


def test_source_and_resource_roots_and_languages_come_from_the_capture():
    model = _repository_model(CAPTURE)
    service_app = next(m for m in model.modules if m.module_id == "com.acme:service-app")
    assert service_app.source_roots == (FIXTURE / "service-app" / "src" / "main" / "java",)
    assert service_app.resource_roots == (FIXTURE / "service-app" / "src" / "main" / "resources",)
    assert service_app.languages == {"java"}


def test_classes_dirs_come_from_the_capture_as_output_dirs():
    model = _repository_model(CAPTURE)
    pricing_lib = next(m for m in model.modules if m.module_id == "com.acme:pricing-lib")
    assert pricing_lib.output_dirs == (
        FIXTURE / "pricing-lib" / "build" / "classes" / "java" / "main",
    )


def test_dependency_coordinates_come_from_the_resolved_compile_classpath():
    """2O design §2a, ruling R9. Unlike the Maven side — which reads the poms
    a module declares and inherits, and no transitives — the init script
    already walks the RESOLVED compile classpath, transitives included, so
    this is the reach a dependency gate gets on Gradle. Entries
    Gradle gave no component id (an inter-project dependency, a `files()`
    entry) carry no coordinate and contribute none: inventing one would name
    an artifact nobody published."""
    model = _repository_model(CAPTURE)
    module = next(m for m in model.modules if m.module_id.endswith("service-app"))

    assert "org.springframework:spring-core" in module.dependency_coordinates
    assert list(module.dependency_coordinates) == sorted(set(module.dependency_coordinates))
    assert all(":" in coordinate for coordinate in module.dependency_coordinates)


def test_a_project_whose_classpath_resolves_nothing_reports_no_coordinates():
    model = _repository_model(
        {
            "projects": [_minimal_project(classes_dirs=["/repo/thing/build/classes"])],
            "includedBuilds": [],
        }
    )

    assert model.modules[0].dependency_coordinates == ()


def test_a_publishing_project_is_not_classified_library():
    """The near-miss for the inference removed by the 2026-09-04 user ruling:
    publishing says where artifacts GO, not what a module CONTAINS, so it is
    never read. `pricing-lib` applies `maven-publish` and has no container
    file — the exact shape that used to return `library` and be SKIPPED
    outright. It must now read `undetermined` and be analyzed like anything
    else, which is what the same repo already did under Maven, whose own
    `_classify` refuses the identical guess ("every POM declares coordinates
    whether anything is published or not"). Before the ruling this asserted
    `library`; the divergence meant one repo analyzed differently under the
    two build systems."""
    model = _repository_model(CAPTURE)
    pricing_lib = next(m for m in model.modules if m.module_id == "com.acme:pricing-lib")
    assert pricing_lib.kind == "undetermined"
    assert pricing_lib.packaging == "jar"


def test_no_publishing_and_no_container_file_is_undetermined():
    model = _repository_model(CAPTURE)
    service_app = next(m for m in model.modules if m.module_id == "com.acme:service-app")
    assert service_app.kind == "undetermined"


def test_the_real_fixtures_inter_project_dependency_is_excluded_from_the_gap_list():
    """`service-app` declares `implementation(project(":pricing-lib"))` (2M
    Task 3 fix round 1, I3) — internal wiring Gradle resolved just fine, so
    it must not appear in `libraries_not_resolved` alongside a genuinely
    unresolved coordinate, even though nothing in this fixture names it via
    `extract_libraries`.

    **The `library_roots` half of this changed in W55** and the gap-list half did
    not. Until then an inter-project dependency was excluded outright and a Gradle
    module got no sibling scanning at all, where Maven had had it since W24; now
    the sibling IS a library root, so this asserts the root rather than its
    absence. What the test is about — that internal wiring is not a GAP — is
    unchanged, and is the first assertion."""
    model = _repository_model(CAPTURE)
    service_app = next(m for m in model.modules if m.module_id == "com.acme:service-app")
    assert service_app.libraries_not_resolved == ()
    assert [(r.coordinate, r.version) for r in service_app.library_roots] == [
        ("com.acme:pricing-lib", "1.0.0")
    ]


def test_a_gradle_sibling_is_named_by_its_group_and_artifact_never_by_its_project_path():
    """W55, and the design question it had to settle first.

    Gradle reports an inter-project dependency as a `ProjectComponentIdentifier`,
    which carries a project PATH (`:pricing-lib`) and no group, name or version at
    all. The path cannot be the coordinate: D00 §2 requires `origin` to survive
    being read on another machine, and a project path means something only inside
    the build that declares it. So the path is used to JOIN to that project's own
    record, and the coordinate comes from its `group` and `name`.

    That matters beyond tidiness: `sibling_coordinates` is what
    `drop_borrowed_endpoints.sql` matches against `documents.origin`, so a
    coordinate in a second spelling would silently match nothing and a sibling's
    controllers would publish as this module's."""
    model = _repository_model(CAPTURE)
    service_app = next(m for m in model.modules if m.module_id == "com.acme:service-app")
    pricing = next(m for m in model.modules if m.module_id == "com.acme:pricing-lib")

    assert service_app.sibling_coordinates == ("com.acme:pricing-lib",)
    # The same string the sibling module reports as its OWN id, which is what makes
    # the two joinable at all.
    assert service_app.sibling_coordinates == (pricing.module_id,)
    assert not any(":" == c[0] for c in service_app.sibling_coordinates), (
        "a project PATH reached `sibling_coordinates`"
    )
    # And a module depending on nothing internal names none.
    assert pricing.sibling_coordinates == ()


def test_a_container_file_beside_the_project_makes_it_a_service(tmp_path: Path):
    project = _project(tmp_path, publishing=False)
    (tmp_path / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    module = GradleDetector._module_of(tmp_path, project)
    assert module.kind == "service"


def test_a_project_without_the_java_plugin_reports_packaging_pom_and_no_source(tmp_path: Path):
    """The Gradle equivalent of a leaf `<packaging>pom</packaging>` (2M
    design §2): nothing here for the CLI's skip gate to scan, reported the
    same way so `_skip_reason` recognises it without a Gradle-specific case."""
    project = _project(tmp_path, publishing=False, classes_dirs=[], source_roots=[])
    module = GradleDetector._module_of(tmp_path, project)
    assert module.packaging == "pom"
    assert module.source_roots == ()
    assert module.output_dirs == ()


# --- composite builds and a root that carries its own source (fix round 1,
# I1/I2) -----------------------------------------------------------------


def test_a_non_empty_included_builds_list_becomes_one_note_naming_all_of_them():
    data = {"projects": [_minimal_project(path=":")], "includedBuilds": ["shared-lib", "other"]}
    model = _repository_model(data)
    assert model.notes == ("composite build: included builds not analyzed: other, shared-lib",)


def test_an_empty_included_builds_list_is_no_note():
    data = {"projects": [_minimal_project(path=":")], "includedBuilds": []}
    assert _repository_model(data).notes == ()


def test_a_root_project_with_its_own_source_gets_a_note_when_dropped():
    root = _minimal_project(
        path=":", name="root-thing", dir_="/repo", source_roots=["/repo/src/main/java"]
    )
    child = _minimal_project(path=":child", name="child", dir_="/repo/child")
    data = {"projects": [root, child], "includedBuilds": []}
    model = _repository_model(data)
    [note] = model.notes
    assert "gradle root project at /repo declares its own source but is not analyzed" in note


def test_a_root_project_with_its_own_classes_dirs_also_gets_the_note():
    root = _minimal_project(path=":", dir_="/repo", classes_dirs=["/repo/build/classes/java/main"])
    child = _minimal_project(path=":child", dir_="/repo/child")
    model = _repository_model({"projects": [root, child], "includedBuilds": []})
    assert len(model.notes) == 1


def test_a_root_project_with_no_source_of_its_own_gets_no_note():
    root = _minimal_project(path=":", dir_="/repo")
    child = _minimal_project(path=":child", dir_="/repo/child")
    model = _repository_model({"projects": [root, child], "includedBuilds": []})
    assert model.notes == ()


def test_a_single_module_build_never_gets_the_root_source_note():
    """The note is about a root that carries source ALONGSIDE subprojects and
    is dropped for it — a genuinely single-module build (no subprojects at
    all) keeps its root as the one module, so the note would misdescribe it
    as dropped when it was analyzed."""
    root = _minimal_project(path=":", dir_="/repo", source_roots=["/repo/src/main/java"])
    # No real source directory backs this synthetic path, so the module
    # itself ends up with an empty source_roots tuple (M1) — irrelevant
    # here, since the point is the note never fires for a single module.
    model = _repository_model({"projects": [root], "includedBuilds": []})
    assert model.notes == ()


# --- a project's identity, formed the way Gradle itself forms it (OI-273) ---


def _project(
    tmp_path: Path,
    *,
    path: str = ":thing",
    group: str = "com.acme",
    name: str = "thing",
    version: str = "1.0.0",
    publishing: bool = False,
    classpath: list | None = None,
    classes_dirs: list[str] | None = None,
    source_roots: list[str] | None = None,
    source_languages: dict[str, list[str]] | None = None,
    resource_roots: list[str] | None = None,
) -> dict:
    """A project record backed by REAL directories on disk for its default
    source/resource roots — `_module_of` now filters both by `is_dir()` (2M
    Task 3 fix round 1, M1), so a synthetic project that wants them to
    survive translation has to actually have them, the same discipline
    `MavenDetector`'s own fixtures already follow."""
    default_source = tmp_path / "src" / "main" / "java"
    default_resource = tmp_path / "src" / "main" / "resources"
    if source_roots is None:
        default_source.mkdir(parents=True, exist_ok=True)
    if resource_roots is None:
        default_resource.mkdir(parents=True, exist_ok=True)
    reported_sources = [str(default_source)] if source_roots is None else source_roots
    return {
        "path": path,
        "group": group,
        "name": name,
        "version": version,
        "dir": str(tmp_path),
        "sourceRoots": reported_sources,
        "sourceLanguages": {root: ["java"] for root in reported_sources}
        if source_languages is None
        else source_languages,
        "resourceRoots": [str(default_resource)] if resource_roots is None else resource_roots,
        "classesDirs": [str(tmp_path / "build" / "classes" / "java" / "main")]
        if classes_dirs is None
        else classes_dirs,
        "publishing": publishing,
        "classpath": classpath or [],
    }


def test_a_root_project_with_no_group_is_named_by_its_root_project_name_alone(tmp_path: Path):
    """No group means no Maven coordinates at all — measured on Gradle 9.8.2,
    `publishToMavenLocal` refuses with "groupId cannot be empty" — so nothing outside
    the build can reference this project by coordinates, and the only identity it has
    is its place in its build. A root project's place is its name: what Gradle
    reports as `rootProject.name` (the folder name by default). Refusing it instead
    left `kotlin-ktor-exposed-starter` and 21 of 36 ktor-samples unanalysable."""
    project = _project(tmp_path, path=":", group="", name="kotlin-ktor-exposed-starter")
    module = GradleDetector._module_of(tmp_path, project, [project])
    assert module.module_id == "kotlin-ktor-exposed-starter"


@pytest.mark.pins("detect.a-NESTED-no-group-gradle-project-is-root-name-plus-path")
def test_a_nested_project_with_no_group_is_its_root_name_and_full_project_path(tmp_path: Path):
    """The root project name comes from Gradle's own record of the root (path `:`),
    never from parsing `settings.gradle`, and every segment of the project path is
    kept: `:libs:core` and `:core` are different projects of one build, and dropping
    the middle would give them one identity."""
    root = _project(tmp_path, path=":", group="", name="Acme", classes_dirs=[])
    core = _project(tmp_path, path=":libs:core", group="", name="core")
    app = _project(tmp_path, path=":app", group="", name="app")
    reactor = [root, core, app]
    assert GradleDetector._module_of(tmp_path, core, reactor).module_id == "Acme:libs:core"
    assert GradleDetector._module_of(tmp_path, app, reactor).module_id == "Acme:app"


def test_a_project_with_no_group_writes_dot_for_manager_package_and_version(tmp_path: Path):
    """D00 §1: "an unpublished service has no package manager, package or version".
    The extractor writes `sextant-jvm . . . <descriptor>` for a module whose
    coordinates and version are `.` — so a no-group project hands it exactly that,
    whatever version it declares: a version names a release of a package, and
    there is no package."""
    project = _project(tmp_path, path=":", group="", name="app", version="1.4.0")
    module = GradleDetector._module_of(tmp_path, project, [project])
    assert (module.coordinates, module.version) == (".", ".")


@pytest.mark.pins("detect.a-GROUPED-gradle-project-keeps-its-maven-coordinates")
def test_a_project_with_a_group_and_no_version_is_published_as_unspecified(tmp_path: Path):
    """Gradle publishes a grouped project with no version as
    `com/acme/nogroup-app/unspecified/nogroup-app-unspecified.jar` (measured, Gradle
    9.8.2): the version is literally `unspecified`, so that is the version its symbols
    carry — not a refusal, and not an invented one."""
    project = _project(tmp_path, version="unspecified")
    module = GradleDetector._module_of(tmp_path, project)
    assert module.module_id == "com.acme:thing"
    assert (module.coordinates, module.version) == ("com.acme/thing", "unspecified")


# --- source/resource roots Gradle names but does not promise exist (fix
# round 1, M1) -------------------------------------------------------------


def test_a_reported_source_root_that_does_not_exist_is_dropped(tmp_path: Path):
    """Gradle NAMES a source-set directory as a build convention; it does not
    promise the directory exists on disk (2M Task 3 fix round 1, M1) — the
    same 'no guess' discipline `MavenDetector`'s own `resource_roots` already
    keeps, applied here to a report this detector did not derive itself."""
    ghost = tmp_path / "src" / "main" / "java"
    project = _project(tmp_path, source_roots=[str(ghost)])
    module = GradleDetector._module_of(tmp_path, project)
    assert module.source_roots == ()
    assert module.languages == frozenset()


def test_a_reported_resource_root_that_does_not_exist_is_dropped(tmp_path: Path):
    ghost = tmp_path / "src" / "main" / "resources"
    project = _project(tmp_path, resource_roots=[str(ghost)])
    module = GradleDetector._module_of(tmp_path, project)
    assert module.resource_roots == ()


def test_a_reported_source_root_that_does_exist_is_kept(tmp_path: Path):
    real = tmp_path / "src" / "main" / "java"
    real.mkdir(parents=True)
    project = _project(tmp_path, source_roots=[str(real)])
    module = GradleDetector._module_of(tmp_path, project)
    assert module.source_roots == (real,)


@pytest.mark.pins("detect.a-gradle-source-roots-LANGUAGE-is-the-plugin-that-registered-it")
def test_a_source_roots_language_is_the_plugin_that_registered_it_not_its_name(
    tmp_path: Path,
):
    """ktor-samples' `client-tools` declares `kotlin.srcDirs("src")`: the directory's
    NAME is `src`, and reading the language off the name left a module no scanner
    accepts. Gradle knows which source-directory set registered the root — the Kotlin
    plugin's `kotlin` set here — and the init script reports it, so that is the answer."""
    src = tmp_path / "src"
    src.mkdir()
    project = _project(tmp_path, source_roots=[str(src)], source_languages={str(src): ["kotlin"]})
    module = GradleDetector._module_of(tmp_path, project)
    assert module.languages == {"kotlin"}


def test_a_root_two_plugins_registered_carries_both_languages(tmp_path: Path):
    """The Kotlin plugin adds `src/main/java` to its own set as well — kotlinc compiles
    `.kt` files found there — so Gradle reports both sets for that one directory, and
    both are languages of the module."""
    java = tmp_path / "src" / "main" / "java"
    java.mkdir(parents=True)
    project = _project(
        tmp_path, source_roots=[str(java)], source_languages={str(java): ["java", "kotlin"]}
    )
    assert GradleDetector._module_of(tmp_path, project).languages == {"java", "kotlin"}


def test_a_root_that_does_not_exist_contributes_no_language(tmp_path: Path):
    """Every Kotlin JVM project REGISTERS `src/main/kotlin` and `src/main/java`; a
    directory that is not on disk holds no source, so its language is not present."""
    kotlin = tmp_path / "src" / "main" / "kotlin"
    kotlin.mkdir(parents=True)
    ghost = tmp_path / "src" / "main" / "java"
    project = _project(
        tmp_path,
        source_roots=[str(ghost), str(kotlin)],
        source_languages={str(ghost): ["java", "kotlin"], str(kotlin): ["kotlin"]},
    )
    assert GradleDetector._module_of(tmp_path, project).languages == {"kotlin"}


@pytest.mark.pins("detect.a-GENERATED-source-directory-names-a-language")
def test_a_module_whose_only_source_is_generated_takes_its_language_from_it(tmp_path: Path):
    """An OpenAPI-generator API module, a jOOQ module, a protobuf contracts module: every
    class is compiled from a directory a task writes under the build directory. That
    directory is not a source ROOT — nobody edits it — but Gradle reports it in the
    source set, registered by the plugin that compiles it, so it names the module's
    language. Without that the module had classes and no language, and "no scanner accepts
    a module with no language" stopped the whole reactor (OI-273 fix round 2, review N1)."""
    generated = tmp_path / "build" / "generated" / "src" / "main" / "java"
    (generated / "api").mkdir(parents=True)
    (generated / "api" / "PricingApi.java").write_text("package api; class PricingApi {}\n")
    project = _project(tmp_path, source_roots=[], source_languages={str(generated): ["java"]})
    module = GradleDetector._module_of(tmp_path, project)
    assert module.languages == {"java"}
    assert module.source_roots == ()


def test_an_empty_generated_directory_names_no_language(tmp_path: Path):
    """Gradle's java plugin creates the annotation-processor output directory on every
    compile, empty when no processor ran: a compiler's scratch space, not source. A Kotlin
    module must not read as `java` because of it."""
    kotlin = tmp_path / "src" / "main" / "kotlin"
    kotlin.mkdir(parents=True)
    processor = tmp_path / "build" / "generated" / "sources" / "annotationProcessor" / "java"
    processor.mkdir(parents=True)
    project = _project(
        tmp_path,
        source_roots=[str(kotlin)],
        source_languages={str(kotlin): ["kotlin"], str(processor): ["java"]},
    )
    assert GradleDetector._module_of(tmp_path, project).languages == {"kotlin"}


# --- schema roots: proto/avro stay sibling-to-source; the resource-nested
# trio now follows the REPORTED resource root (fix round 1, I5) ------------


def test_proto_and_avro_schema_roots_stay_a_sibling_to_source_convention(tmp_path: Path):
    proto = tmp_path / "src" / "main" / "proto"
    proto.mkdir(parents=True)
    project = _project(tmp_path)
    module = GradleDetector._module_of(tmp_path, project)
    assert module.schema_roots == (proto,)


def test_schema_roots_are_probed_under_a_non_conventional_reported_resource_root(
    tmp_path: Path,
):
    """A resources directory that is NOT `src/main/resources` — legal Gradle
    (`sourceSets.main.resources.srcDir(...)`) — still gets its GraphQL/WSDL/
    XSD schema roots found (2M Task 3 fix round 1, I5), closing the gap
    `MavenDetector`'s own hardcoded `src/main/resources` guess cannot: this
    detector probes whichever resource root(s) the BUILD actually reports."""
    custom_resources = tmp_path / "config" / "resources"
    graphql = custom_resources / "graphql"
    graphql.mkdir(parents=True)
    project = _project(tmp_path, resource_roots=[str(custom_resources)])
    module = GradleDetector._module_of(tmp_path, project)
    assert module.schema_roots == (graphql,)


def test_no_schema_directories_means_no_schema_roots(tmp_path: Path):
    project = _project(tmp_path)
    module = GradleDetector._module_of(tmp_path, project)
    assert module.schema_roots == ()


# --- LibraryRoots from the classpath report (2M design §1) ------------------


_SPRING_WEB_ENTRY = {
    "path": "/gradle/caches/modules-2/files-2.1/org.springframework/spring-web/6.1.6/x/spring-web-6.1.6.jar",
    "group": "org.springframework",
    "name": "spring-web",
    "version": "6.1.6",
}
_PATH_ONLY_ENTRY = {"path": "/gradle/caches/transforms/whatever/local-thing.jar"}
_INTERNAL_PROJECT_ENTRY = {
    "path": "/repo/pricing-lib/build/classes/java/main",
    "internal": True,
}


def test_a_module_with_no_config_names_no_library_roots(tmp_path: Path):
    project = _project(tmp_path, classpath=[_SPRING_WEB_ENTRY])
    module = GradleDetector._module_of(tmp_path, project)
    assert module.library_roots == ()
    assert module.libraries_not_resolved == ()


def test_a_declared_coordinate_resolves_to_the_archive_gradle_already_reported(tmp_path: Path):
    (tmp_path / ".sextant.yml").write_text(
        "extract_libraries: [org.springframework:spring-web]\n", encoding="utf-8"
    )
    project = _project(tmp_path, classpath=[_SPRING_WEB_ENTRY])
    module = GradleDetector._module_of(tmp_path, project)
    assert module.libraries_not_resolved == ()
    [library] = module.library_roots
    assert library.coordinate == "org.springframework:spring-web"
    assert library.version == "6.1.6"
    assert library.archive == Path(_SPRING_WEB_ENTRY["path"])


def test_a_pinned_version_is_matched_against_the_reported_component(tmp_path: Path):
    (tmp_path / ".sextant.yml").write_text(
        "extract_libraries: ['org.springframework:spring-web:6.1.6']\n", encoding="utf-8"
    )
    project = _project(tmp_path, classpath=[_SPRING_WEB_ENTRY])
    module = GradleDetector._module_of(tmp_path, project)
    [library] = module.library_roots
    assert library.version == "6.1.6"


def test_a_declared_coordinate_absent_from_the_classpath_is_named_with_its_reason(
    tmp_path: Path,
):
    (tmp_path / ".sextant.yml").write_text(
        "extract_libraries: [com.example:absent]\n", encoding="utf-8"
    )
    project = _project(tmp_path, classpath=[_SPRING_WEB_ENTRY])
    module = GradleDetector._module_of(tmp_path, project)
    assert module.library_roots == ()
    [reason] = module.libraries_not_resolved
    assert reason.startswith("com.example:absent: ")


def test_a_path_only_classpath_entry_joins_libraries_not_resolved_unconditionally(
    tmp_path: Path,
):
    """A path Gradle reports with no component id, and no `internal` marker
    either, can never be named by any `extract_libraries` coordinate — opt-in
    cannot gate what has nothing to be named BY, so it is reported
    regardless of `.sextant.yml` (2M design §1)."""
    project = _project(tmp_path, classpath=[_SPRING_WEB_ENTRY, _PATH_ONLY_ENTRY])
    module = GradleDetector._module_of(tmp_path, project)
    assert module.library_roots == ()
    [reason] = module.libraries_not_resolved
    assert reason.startswith(f"{_PATH_ONLY_ENTRY['path']}: ")
    assert "no component id" in reason


def test_an_internal_project_dependency_is_excluded_from_the_gap_list(tmp_path: Path):
    """A `project(":other")` dependency has no component id EITHER, but the
    init script marks it `internal` — internal wiring Gradle resolved just
    fine, never a gap (2M Task 3 fix round 1, I3): it must not join
    `libraries_not_resolved` the way a genuine path-only entry does."""
    project = _project(tmp_path, classpath=[_SPRING_WEB_ENTRY, _INTERNAL_PROJECT_ENTRY])
    module = GradleDetector._module_of(tmp_path, project)
    assert module.library_roots == ()
    assert module.libraries_not_resolved == ()


def test_an_internal_project_dependency_stays_excluded_even_when_declared(tmp_path: Path):
    """Opt-in cannot select it either: it carries no group/name for
    `extract_libraries` to match against, so declaring the project's own
    coordinates changes nothing about this entry."""
    (tmp_path / ".sextant.yml").write_text(
        "extract_libraries: [com.acme:pricing-lib]\n", encoding="utf-8"
    )
    project = _project(tmp_path, classpath=[_INTERNAL_PROJECT_ENTRY])
    module = GradleDetector._module_of(tmp_path, project)
    assert module.library_roots == ()
    [reason] = module.libraries_not_resolved
    assert reason.startswith("com.acme:pricing-lib: ")


# --- wrapper fallback (2M design §1c) ---------------------------------------


def test_the_wrapper_is_preferred_when_it_exists(tmp_path: Path):
    wrapper = tmp_path / "gradlew"
    wrapper.write_text("#!/bin/sh\n", encoding="utf-8")
    command, note = GradleDetector._gradle_command(tmp_path)
    assert command == [str(wrapper)]
    assert note is None


def test_falling_back_to_gradle_on_path_is_recorded_as_a_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(gradle_module.shutil, "which", lambda name: "/usr/bin/gradle")
    command, note = GradleDetector._gradle_command(tmp_path)
    assert command == ["/usr/bin/gradle"]
    assert note == "no ./gradlew wrapper at the repository root; used `gradle` on PATH"


def test_no_wrapper_and_no_gradle_on_path_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(gradle_module.shutil, "which", lambda name: None)
    with pytest.raises(ValueError, match="no ./gradlew wrapper"):
        GradleDetector._gradle_command(tmp_path)


def test_the_wrapper_fallback_note_reaches_repositorymodel_notes():
    """The parameter `_repository_model` takes for exactly this must
    actually be exercised non-`None` somewhere (2M Task 3 fix round 1, M4) —
    the fallback note flows all the way to `RepositoryModel.notes`, not only
    to `_gradle_command`'s own return value."""
    data = {"projects": [_minimal_project(path=":")], "includedBuilds": []}
    note = "no ./gradlew wrapper at the repository root; used `gradle` on PATH"
    model = _repository_model(data, wrapper_note=note)
    assert model.notes == (note,)


# --- cold-start taxonomy (2M design §1, tightened by fix round 1, C2) ------


_REAL_WRAPPER_BOOTSTRAP_FAILURE = (
    'Exception in thread "main" java.io.IOException: Server returned HTTP response code: '
    "404 for URL: https://services.gradle.org/distributions/gradle-99.99.99-bin.zip\n"
    "\tat org.gradle.wrapper.Download.download(SourceFile:1)\n"
)

# Verified live against Gradle 9.7.1 (`JAVA_HOME=/nonexistent/bad/java/home
# ./gradlew ...`): neither the build-failure banner nor any wrapper-bootstrap
# evidence — the exact case C2 exists to stop being misread as "the
# distribution is absent".
_REAL_BAD_JAVA_HOME_FAILURE = (
    "ERROR: JAVA_HOME is set to an invalid directory: /nonexistent/bad/java/home\n\n"
    "Please set the JAVA_HOME variable in your environment to match the\n"
    "location of your Java installation.\n"
)


def test_a_real_wrapper_bootstrap_failure_is_recognised_by_positive_evidence():
    assert gradle_module._is_distribution_absent(_REAL_WRAPPER_BOOTSTRAP_FAILURE) is True


def test_a_bad_java_home_is_not_misclassified_as_distribution_absent():
    """2M Task 3 fix round 1, C2: `_is_distribution_absent` used to be
    "banner absent", which misread ANY non-startup failure (a bad
    `JAVA_HOME` proved this live) as "distribution absent" and dropped
    Gradle's own words. It now requires POSITIVE wrapper-bootstrap evidence,
    so this falls through to the verbatim class-3 refusal instead."""
    assert gradle_module._is_distribution_absent(_REAL_BAD_JAVA_HOME_FAILURE) is False


def test_an_ordinary_build_failure_carries_the_banner_and_is_not_distribution_absent():
    real_offline_failure = (
        "\nFAILURE: Build failed with an exception.\n\n* What went wrong:\n"
        "> Could not resolve org.springframework:spring-web:6.1.6.\n"
        "   > No cached version of org.springframework:spring-web:6.1.6 available for "
        "offline mode.\n"
    )
    assert gradle_module._is_distribution_absent(real_offline_failure) is False
    assert gradle_module._OFFLINE_REFUSAL_SUBSTRING in real_offline_failure


def test_distribution_absent_message_names_the_wrapper_properties_file():
    message = _distribution_absent_message(FIXTURE, _REAL_WRAPPER_BOOTSTRAP_FAILURE)
    assert "Gradle distribution not present" in message
    assert str(FIXTURE / "gradle" / "wrapper" / "gradle-wrapper.properties") in message
    # DR-6 applies to this class too (2M Task 3 fix round 1, C2): naming the
    # properties file is not enough on its own — Gradle's own words ride
    # along.
    assert "org.gradle.wrapper.Download" in message


def test_distribution_absent_message_has_no_file_to_name_without_a_wrapper(tmp_path: Path):
    message = _distribution_absent_message(tmp_path, _REAL_WRAPPER_BOOTSTRAP_FAILURE)
    assert message.startswith(
        "Gradle distribution not present — Gradle could not start before running any task"
    )
    assert "org.gradle.wrapper.Download" in message


# Captured from the real wrapper (Gradle 9.5.0's, examples/playport, a fresh Gradle user
# home, `--offline`): the wrapper DOWNLOADED its distribution successfully, and then the
# build itself failed resolving a plugin offline. Path shortened; otherwise verbatim.
_REAL_DOWNLOAD_THEN_OFFLINE_PLUGIN_FAILURE = (
    "Downloading https://services.gradle.org/distributions/gradle-9.5.0-bin.zip\n"
    ".............10%.............20%..............30%.............40%.............50%"
    "..............60%.............70%..............80%.............90%.............100%\n"
    "\nFAILURE: Build failed with an exception.\n\n* Where:\n"
    "Build file '/repo/playport/build.gradle.kts' line: 1\n\n* What went wrong:\n"
    "Plugin [id: 'org.jetbrains.kotlin.jvm', version: '2.4.20', apply: false] was not found "
    "in any of the following sources:\n\n"
    "- Gradle Core Plugins (plugin is not in 'org.gradle' namespace)\n"
    "- Included Builds (No included builds contain this plugin)\n"
    "- Plugin Repositories (could not resolve plugin artifact "
    "'org.jetbrains.kotlin.jvm:org.jetbrains.kotlin.jvm.gradle.plugin:2.4.20')\n"
    "  Searched in the following repositories:\n    MavenRepo\n"
    "    Gradle Central Plugin Repository\n\nBUILD FAILED in 17s\n"
)


# Captured from a real Gradle 9.7.1 run (Task 1 fix round 1): two projects, each with a
# dependency the cache lacks, run offline with `--continue` and this detector's own argv. With
# two or more failed tasks Gradle prints "Build completed with N failures", not the single
# failure's "Build failed with an exception". The first two lines are the wrapper's download
# lines, the shape `_REAL_DOWNLOAD_THEN_OFFLINE_PLUGIN_FAILURE` captured: a fresh machine
# downloads the distribution first and then fails the same way.
_REAL_DOWNLOAD_THEN_TWO_OFFLINE_FAILURES = (
    "Downloading https://services.gradle.org/distributions/gradle-9.7.1-bin.zip\n"
    ".............10%.............20%..............30%.............40%.............50%"
    "..............60%.............70%..............80%.............90%.............100%\n"
    "\n"
    "FAILURE: Build completed with 2 failures.\n"
    "\n"
    "1: Task failed with an exception.\n"
    "-----------\n"
    "* What went wrong:\n"
    "Execution failed for task ':a:compileJava' (registered by plugin class 'org.gradle.api.plugins.JavaBasePlugin').\n"
    "> Could not resolve all files for configuration ':a:compileClasspath'.\n"
    "   > Could not resolve org.example.sextant:not-cached-a:1.0.0.\n"
    "     Required by:\n"
    "         project ':a'\n"
    "      > No cached version of org.example.sextant:not-cached-a:1.0.0 available for offline mode.\n"
    "\n"
    "* Try:\n"
    "> Run with --stacktrace option to get the stack trace.\n"
    "> Run with --info or --debug option to get more log output.\n"
    "> Run with --scan to get full insights from a Build Scan (powered by Develocity).\n"
    "> Get more help at https://help.gradle.org.\n"
    "==============================================================================\n"
    "\n"
    "2: Task failed with an exception.\n"
    "-----------\n"
    "* What went wrong:\n"
    "Execution failed for task ':b:compileJava' (registered by plugin class 'org.gradle.api.plugins.JavaBasePlugin').\n"
    "> Could not resolve all files for configuration ':b:compileClasspath'.\n"
    "   > Could not resolve org.example.sextant:not-cached-b:1.0.0.\n"
    "     Required by:\n"
    "         project ':b'\n"
    "      > No cached version of org.example.sextant:not-cached-b:1.0.0 available for offline mode.\n"
    "\n"
    "* Try:\n"
    "> Run with --stacktrace option to get the stack trace.\n"
    "> Run with --info or --debug option to get more log output.\n"
    "> Run with --scan to get full insights from a Build Scan (powered by Develocity).\n"
    "> Get more help at https://help.gradle.org.\n"
    "==============================================================================\n"
    "\n"
    "BUILD FAILED in 321ms\n"
)


@pytest.mark.pins("detect.SEVERAL-failed-parts-after-a-download-are-retried-online-under-the-flag")
def test_several_offline_failures_after_a_download_retry_online_under_the_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """`--continue` lets every part fail on its own, and Gradle then reports "Build completed
    with N failures". That banner proves the build engine ran, the same as the single-failure
    one: the download succeeded, so this is an offline refusal and `--allow-resolve` retries it
    online — never "Gradle distribution not present"."""
    calls: list[bool] = []

    def fake_run_once(gradle_command, path, out_dir, offline):
        calls.append(offline)
        if offline:
            return _completed(1, _REAL_DOWNLOAD_THEN_TWO_OFFLINE_FAILURES)
        _write_empty_build(out_dir)
        return _completed(0, "")

    monkeypatch.setattr(GradleDetector, "_run_once", staticmethod(fake_run_once))
    data = GradleDetector()._invoke(["./gradlew"], tmp_path, tmp_path, True)
    assert data == {"projects": [], "includedBuilds": []}
    assert calls == [True, False]


def test_the_project_file_name_is_distinct_for_every_project_path():
    """`:a_b` and `:a:b` are two projects; `_` is escaped first, so their files differ."""
    assert gradle_module._project_file_name(":") == "_.json"
    assert gradle_module._project_file_name(":a:b") == "_a_b.json"
    assert gradle_module._project_file_name(":a_b") == "_a__b.json"


@pytest.mark.pins("detect.a-download-that-SUCCEEDED-is-not-a-missing-distribution")
def test_a_download_that_succeeded_before_a_build_failure_is_not_distribution_absent():
    """The wrapper prints `Downloading https://...` and its progress, succeeds, and then
    the BUILD fails — Gradle's own banner says so. Reading the download line alone reported
    "Gradle distribution not present" and hid Gradle's real reason (OI-273 fix round 1)."""
    assert (
        gradle_module._is_distribution_absent(_REAL_DOWNLOAD_THEN_OFFLINE_PLUGIN_FAILURE) is False
    )


@pytest.mark.pins("detect.an-OFFLINE-PLUGIN-refusal-is-retried-online-under-the-flag")
def test_an_offline_plugin_refusal_with_allow_resolve_retries_online_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Offline, a plugin Gradle has never cached fails as "could not resolve plugin artifact"
    (measured on Gradle 8.14.1 and 9.5.0) — never as "available for offline mode", the
    wording a missing DEPENDENCY gets. It is the same refusal: the cache lacks it and the
    network might not, so `--allow-resolve` retries it online, as it does a dependency."""
    calls: list[bool] = []

    def fake_run_once(gradle_command, path, out_dir, offline):
        calls.append(offline)
        if offline:
            return _completed(1, _REAL_DOWNLOAD_THEN_OFFLINE_PLUGIN_FAILURE)
        _write_empty_build(out_dir)
        return _completed(0, "")

    monkeypatch.setattr(GradleDetector, "_run_once", staticmethod(fake_run_once))
    data = GradleDetector()._invoke(["./gradlew"], tmp_path, tmp_path, True)
    assert data == {"projects": [], "includedBuilds": []}
    assert calls == [True, False]


def test_an_offline_plugin_refusal_without_the_flag_reports_gradles_own_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    def fake_run_once(gradle_command, path, out_dir, offline):
        return _completed(1, _REAL_DOWNLOAD_THEN_OFFLINE_PLUGIN_FAILURE)

    monkeypatch.setattr(GradleDetector, "_run_once", staticmethod(fake_run_once))
    with pytest.raises(ValueError, match="could not resolve plugin artifact") as failure:
        GradleDetector()._invoke(["./gradlew"], tmp_path, tmp_path, False)
    assert "distribution not present" not in str(failure.value)


# --- `_invoke`'s retry ladder, driven by a faked subprocess -----------------


def _completed(returncode: int, output: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=output, stderr="")


def _write_empty_build(out_dir: Path) -> None:
    """What `sextantBuild` writes for a build with no projects to read."""
    (out_dir / "build.json").write_text(
        json.dumps({"projects": [], "includedBuilds": []}), encoding="utf-8"
    )


def test_a_clean_offline_run_reads_the_output_file_and_asks_for_no_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list[bool] = []

    def fake_run_once(gradle_command, path, out_dir, offline):
        calls.append(offline)
        _write_empty_build(out_dir)
        return _completed(0, "")

    monkeypatch.setattr(GradleDetector, "_run_once", staticmethod(fake_run_once))
    data = GradleDetector()._invoke(["./gradlew"], tmp_path, tmp_path, False)
    assert data == {"projects": [], "includedBuilds": []}
    assert calls == [True]


def test_an_offline_refusal_without_allow_resolve_is_refused_with_no_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list[bool] = []

    def fake_run_once(gradle_command, path, out_dir, offline):
        calls.append(offline)
        return _completed(
            1,
            "FAILURE: Build failed with an exception.\n"
            "> No cached version of org.springframework:spring-web:6.1.6 available for "
            "offline mode.\n",
        )

    monkeypatch.setattr(GradleDetector, "_run_once", staticmethod(fake_run_once))
    with pytest.raises(ValueError, match="available for offline mode"):
        GradleDetector()._invoke(["./gradlew"], tmp_path, tmp_path, False)
    assert calls == [True]


def test_an_offline_refusal_with_allow_resolve_retries_online_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list[bool] = []

    def fake_run_once(gradle_command, path, out_dir, offline):
        calls.append(offline)
        if offline:
            return _completed(
                1,
                "FAILURE: Build failed with an exception.\n"
                "> No cached version of org.springframework:spring-web:6.1.6 available for "
                "offline mode.\n",
            )
        _write_empty_build(out_dir)
        return _completed(0, "")

    monkeypatch.setattr(GradleDetector, "_run_once", staticmethod(fake_run_once))
    data = GradleDetector()._invoke(["./gradlew"], tmp_path, tmp_path, True)
    assert data == {"projects": [], "includedBuilds": []}
    assert calls == [True, False]


def test_a_build_configuration_failure_is_refused_with_gradles_own_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    verbatim = (
        "FAILURE: Build failed with an exception.\n"
        "* What went wrong:\nA problem occurred evaluating root project 'x'.\n"
        "> Could not find method sextantModel() for arguments...\n"
    )

    def fake_run_once(gradle_command, path, out_dir, offline):
        return _completed(1, verbatim)

    monkeypatch.setattr(GradleDetector, "_run_once", staticmethod(fake_run_once))
    with pytest.raises(ValueError) as failure:
        GradleDetector()._invoke(["./gradlew"], tmp_path, tmp_path, False)
    assert "Could not find method sextantModel" in str(failure.value)


def test_a_bad_java_home_failure_is_refused_verbatim_not_as_distribution_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """2M Task 3 fix round 1, C2, exercised through the real retry ladder:
    a failure carrying neither the banner nor wrapper-bootstrap evidence
    must reach the caller as Gradle's own verbatim words, never relabelled
    "Gradle distribution not present"."""

    def fake_run_once(gradle_command, path, out_dir, offline):
        return _completed(1, _REAL_BAD_JAVA_HOME_FAILURE)

    monkeypatch.setattr(GradleDetector, "_run_once", staticmethod(fake_run_once))
    with pytest.raises(ValueError) as failure:
        GradleDetector()._invoke(["./gradlew"], tmp_path, tmp_path, False)
    assert "JAVA_HOME is set to an invalid directory" in str(failure.value)
    assert "distribution not present" not in str(failure.value)


def test_distribution_absent_is_recognised_even_on_the_second_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list[bool] = []

    def fake_run_once(gradle_command, path, out_dir, offline):
        calls.append(offline)
        if offline:
            return _completed(
                1,
                "FAILURE: Build failed with an exception.\n"
                "> No cached version of org.springframework:spring-web:6.1.6 available for "
                "offline mode.\n",
            )
        return _completed(1, _REAL_WRAPPER_BOOTSTRAP_FAILURE)

    monkeypatch.setattr(GradleDetector, "_run_once", staticmethod(fake_run_once))
    with pytest.raises(ValueError, match="Gradle distribution not present"):
        GradleDetector()._invoke(["./gradlew"], tmp_path, tmp_path, True)
    assert calls == [True, False]


# --- escape hatches wrapped into named refusals (2M Task 3 fix round 1, I6)


def test_a_successful_exit_with_no_output_file_is_a_named_refusal(tmp_path: Path):
    missing = tmp_path / "does-not-exist.json"
    with pytest.raises(ValueError, match="wrote no model"):
        gradle_module._read_json(missing)


def test_malformed_json_output_is_a_named_refusal(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        gradle_module._read_json(bad)


def test_a_json_document_missing_an_expected_key_is_a_named_refusal():
    with pytest.raises(ValueError, match="missing the"):
        GradleDetector._repository_model(FIXTURE, {"projects": [{"path": ":"}]}, None)


def test_a_non_executable_wrapper_is_a_named_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Routine for a zip-delivered checkout (2M Task 3 fix round 1, I6):
    `./gradlew`'s executable bit does not always survive a zip/tarball round
    trip."""

    def fake_run(argv, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(gradle_module.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="not executable"):
        GradleDetector._run_once(["./gradlew"], tmp_path, tmp_path, True)


def test_a_timeout_becomes_a_named_refusal_not_a_hang(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """2M Task 3 fix round 1, M3: a build that never finishes must become a
    refusal a caller can see, never a hang nothing ever reports."""

    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout", 0))

    monkeypatch.setattr(gradle_module.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="did not finish within"):
        GradleDetector._run_once(["./gradlew"], tmp_path, tmp_path, True)


# --- the init script itself, loaded through the installed package (2M Task
# 3 fix round 1, I7) ---------------------------------------------------------


def test_the_init_script_resource_is_packaged():
    script = gradle_module._init_script()
    assert script.is_file()
    assert script.name == "sextant-model.init.gradle"
    assert "sextantModel" in script.read_text(encoding="utf-8")


def test_a_missing_init_script_is_a_named_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(gradle_module.resources, "files", lambda package: tmp_path)
    with pytest.raises(gradle_module.MissingInitScriptError):
        gradle_module._init_script()


# --- F1: the resolved versions beside the coordinates ------------------------


def test_dependency_versions_come_from_the_same_resolved_report(tmp_path: Path):
    """F1. Gradle already resolved every conflict before it reported, so the
    version here is the one that would actually be on the classpath — a
    stronger answer than the Maven side's, which reads versions off the poms
    that declare them and reaches no transitive at all."""
    project = _project(tmp_path, classpath=[_SPRING_WEB_ENTRY])
    module = GradleDetector._module_of(tmp_path, project)

    assert module.dependency_versions == {"org.springframework:spring-web": "6.1.6"}
    # Nothing to report: Gradle carries a version for every component it
    # named, so this list is a Maven-side answer only.
    assert module.dependencies_not_resolved == ()


def test_an_entry_with_no_coordinate_contributes_no_version(tmp_path: Path):
    """The same rule the coordinates keep, one column over: a `files()` entry
    and an inter-project dependency have no coordinate to key a version on, and
    inventing one would name a release nobody cut."""
    project = _project(
        tmp_path, classpath=[_SPRING_WEB_ENTRY, _PATH_ONLY_ENTRY, _INTERNAL_PROJECT_ENTRY]
    )
    module = GradleDetector._module_of(tmp_path, project)

    assert module.dependency_versions == {"org.springframework:spring-web": "6.1.6"}


def test_every_recorded_coordinate_carries_a_version_on_the_capture():
    """Against the captured report of a real Gradle build rather than a
    hand-built project: the two maps must describe the same set, or a
    version-scoped rule would read "unanswerable" for a dependency the report
    answered for."""
    model = _repository_model(CAPTURE)
    module = next(m for m in model.modules if m.module_id.endswith("service-app"))

    assert set(module.dependency_versions) == set(module.dependency_coordinates)
    assert list(module.dependency_versions) == sorted(module.dependency_versions)


def test_the_declared_release_comes_from_gradles_own_evaluated_model():
    """W3b, Gradle half. Asked of GRADLE rather than parsed out of a build
    script, because the value can come from a convention plugin, a toolchain or
    a property, and only the evaluated model knows which one won.

    The capture's values were recorded from a live run of the init script
    against `fixtures/gradle-orders`, whose two Java projects set
    `options.release.set(21)`. The root project applies no Java plugin and
    reports absence — not a default, and not the 21 its children declare.
    """
    model = _repository_model(_load_capture())
    assert {module.declared_release for module in model.modules} == {21}


def test_a_project_record_predating_the_release_field_reads_as_absence(tmp_path: Path):
    """A capture taken by an OLDER init script has no such key at all, and a
    missing key is the same absence as a project declaring nothing — never a
    crash, and never a default standing in for a value the build never
    stated."""
    project = _minimal_project(dir_=str(tmp_path))
    project.pop("declaredRelease", None)
    assert GradleDetector._module_of(tmp_path, project).declared_release is None


@pytest.mark.pins("detect.a-NO-GROUP-sibling-is-read-as-an-unpublished-library-root")
def test_a_no_group_sibling_is_read_as_a_library_root_under_its_module_id(tmp_path: Path):
    """The no-group sibling Gradle actually produces: the ROOT project. Gradle gives every
    subproject a default group (the root's name), so only the root has none, and
    `:app` with `implementation project(':')` has it on its compile classpath — a
    dependency in every sense, read the way a grouped sibling is. It has no coordinates
    (Gradle will not publish it), so it is marked unpublished exactly as a module is:
    named by its module id, the bare root name `Acme`, with `.` for package and version
    (OI-273 round 2; fix round 1, review M2: this is the shape that must be tested)."""
    root_classes = tmp_path / "build" / "classes" / "java" / "main"
    root_classes.mkdir(parents=True)
    root = _project(tmp_path, path=":", group="", name="Acme", classes_dirs=[str(root_classes)])
    app = _project(
        tmp_path / "app",
        path=":app",
        group="Acme",
        name="app",
        version="unspecified",
        classpath=[{"path": str(root_classes), "internal": True, "projectPath": ":"}],
    )
    module = GradleDetector._module_of(tmp_path / "app", app, [root, app])

    assert module.module_id == "Acme:app"
    assert module.sibling_coordinates == ("Acme",)
    assert [(r.coordinate, r.version, r.package, r.archive) for r in module.library_roots] == [
        ("Acme", ".", ".", root_classes)
    ]
    # The same string the root reports as its OWN id, which is what joins the two.
    assert module.sibling_coordinates == (
        GradleDetector._module_of(tmp_path, root, [root, app]).module_id,
    )
