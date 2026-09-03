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
CAPTURE = json.loads(
    (Path(__file__).parent / "gradle-captures" / "gradle-orders.json").read_text(encoding="utf-8")
)


def _repository_model(data: dict, wrapper_note: str | None = None):
    return GradleDetector._repository_model(FIXTURE, data, wrapper_note)


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
    argv = _compose_argv(["./gradlew"], Path("/init.gradle"), Path("/out.json"), offline=True)
    assert argv == [
        "./gradlew",
        "--offline",
        "--init-script",
        "/init.gradle",
        "--no-configuration-cache",
        "-q",
        "sextantModel",
        "-Psextant.out=/out.json",
    ]


def test_the_online_retry_argv_drops_offline_but_keeps_the_rest():
    argv = _compose_argv(["./gradlew"], Path("/init.gradle"), Path("/out.json"), offline=False)
    assert argv == [
        "./gradlew",
        "--init-script",
        "/init.gradle",
        "--no-configuration-cache",
        "-q",
        "sextantModel",
        "-Psextant.out=/out.json",
    ]


# --- the translation from captured JSON to RepositoryModel/ModuleModel -----


def test_the_real_fixtures_capture_is_multi_module_with_both_subprojects_in_path_order():
    model = _repository_model(CAPTURE)
    assert model.multi_module is True
    assert [module.module_id for module in model.modules] == [
        "com.acme:pricing-lib",
        "com.acme:service-app",
    ]


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


def test_publishing_evidence_makes_the_kind_library_the_gradle_only_deviation():
    """2M design §2: `library` is unreadable from a POM alone, so Maven never
    returns it — Gradle CAN read publishing evidence from the evaluated
    model, and this fixture pins that deviation."""
    model = _repository_model(CAPTURE)
    pricing_lib = next(m for m in model.modules if m.module_id == "com.acme:pricing-lib")
    assert pricing_lib.kind == "library"
    assert pricing_lib.packaging == "jar"


def test_no_publishing_and_no_container_file_is_undetermined():
    model = _repository_model(CAPTURE)
    service_app = next(m for m in model.modules if m.module_id == "com.acme:service-app")
    assert service_app.kind == "undetermined"


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


# --- coordinates leaving loose: loud refusals (2M design §1) ---------------


def _project(
    tmp_path: Path,
    *,
    group: str = "com.acme",
    name: str = "thing",
    version: str = "1.0.0",
    publishing: bool = False,
    classpath: list | None = None,
    classes_dirs: list[str] | None = None,
    source_roots: list[str] | None = None,
) -> dict:
    return {
        "path": ":thing",
        "group": group,
        "name": name,
        "version": version,
        "dir": str(tmp_path),
        "sourceRoots": [str(tmp_path / "src" / "main" / "java")]
        if source_roots is None
        else source_roots,
        "resourceRoots": [],
        "classesDirs": [str(tmp_path / "build" / "classes" / "java" / "main")]
        if classes_dirs is None
        else classes_dirs,
        "publishing": publishing,
        "classpath": classpath or [],
    }


def test_a_project_with_no_group_is_refused_by_name(tmp_path: Path):
    project = _project(tmp_path, group="")
    with pytest.raises(ValueError, match="gradle project thing declares no group"):
        GradleDetector._module_of(tmp_path, project)


def test_a_project_with_version_unspecified_is_refused_by_name(tmp_path: Path):
    project = _project(tmp_path, version="unspecified")
    with pytest.raises(ValueError, match="gradle project thing declares no version"):
        GradleDetector._module_of(tmp_path, project)


# --- LibraryRoots from the classpath report (2M design §1) ------------------


_SPRING_WEB_ENTRY = {
    "path": "/gradle/caches/modules-2/files-2.1/org.springframework/spring-web/6.1.6/x/spring-web-6.1.6.jar",
    "group": "org.springframework",
    "name": "spring-web",
    "version": "6.1.6",
}
_PATH_ONLY_ENTRY = {"path": "/gradle/caches/transforms/whatever/local-thing.jar"}


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
    """A path Gradle reports with no component id can never be named by any
    `extract_libraries` coordinate — opt-in cannot gate what has nothing to
    be named BY, so it is reported regardless of `.sextant.yml` (2M design
    §1)."""
    project = _project(tmp_path, classpath=[_SPRING_WEB_ENTRY, _PATH_ONLY_ENTRY])
    module = GradleDetector._module_of(tmp_path, project)
    assert module.library_roots == ()
    [reason] = module.libraries_not_resolved
    assert reason.startswith(f"{_PATH_ONLY_ENTRY['path']}: ")
    assert "no component id" in reason


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


# --- cold-start taxonomy (2M design §1) -------------------------------------


def test_distribution_absent_is_recognised_by_the_missing_build_failure_banner():
    """Gradle prints `FAILURE: Build failed with an exception.` for EVERY
    build failure once it has actually started — a wrapper bootstrap failure
    (the distribution itself could not be obtained) never reaches that
    point, verified live against Gradle 9.7.1 (a bogus wrapper distribution
    version): `Exception in thread "main"` from `org.gradle.wrapper.*`, no
    banner at all."""
    real_wrapper_failure = (
        'Exception in thread "main" java.io.IOException: Server returned HTTP response code: '
        "404 for URL: https://services.gradle.org/distributions/gradle-99.99.99-bin.zip\n"
        "\tat org.gradle.wrapper.Download.download(SourceFile:1)\n"
    )
    assert gradle_module._is_distribution_absent(real_wrapper_failure) is True


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
    message = _distribution_absent_message(FIXTURE)
    assert "Gradle distribution not present" in message
    assert str(FIXTURE / "gradle" / "wrapper" / "gradle-wrapper.properties") in message


def test_distribution_absent_message_has_no_file_to_name_without_a_wrapper(tmp_path: Path):
    message = _distribution_absent_message(tmp_path)
    assert (
        message
        == "Gradle distribution not present — Gradle could not start before running any task"
    )


# --- `_invoke`'s retry ladder, driven by a faked subprocess -----------------


def _completed(returncode: int, output: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=output, stderr="")


def test_a_clean_offline_run_reads_the_output_file_and_asks_for_no_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list[bool] = []

    def fake_run_once(gradle_command, path, out_file, offline):
        calls.append(offline)
        out_file.write_text(json.dumps({"projects": []}), encoding="utf-8")
        return _completed(0, "")

    monkeypatch.setattr(GradleDetector, "_run_once", staticmethod(fake_run_once))
    data = GradleDetector()._invoke(["./gradlew"], tmp_path, tmp_path / "out.json", False)
    assert data == {"projects": []}
    assert calls == [True]


def test_an_offline_refusal_without_allow_resolve_is_refused_with_no_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list[bool] = []

    def fake_run_once(gradle_command, path, out_file, offline):
        calls.append(offline)
        return _completed(
            1,
            "FAILURE: Build failed with an exception.\n"
            "> No cached version of org.springframework:spring-web:6.1.6 available for "
            "offline mode.\n",
        )

    monkeypatch.setattr(GradleDetector, "_run_once", staticmethod(fake_run_once))
    with pytest.raises(ValueError, match="available for offline mode"):
        GradleDetector()._invoke(["./gradlew"], tmp_path, tmp_path / "out.json", False)
    assert calls == [True]


def test_an_offline_refusal_with_allow_resolve_retries_online_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list[bool] = []

    def fake_run_once(gradle_command, path, out_file, offline):
        calls.append(offline)
        if offline:
            return _completed(
                1,
                "FAILURE: Build failed with an exception.\n"
                "> No cached version of org.springframework:spring-web:6.1.6 available for "
                "offline mode.\n",
            )
        out_file.write_text(json.dumps({"projects": []}), encoding="utf-8")
        return _completed(0, "")

    monkeypatch.setattr(GradleDetector, "_run_once", staticmethod(fake_run_once))
    data = GradleDetector()._invoke(["./gradlew"], tmp_path, tmp_path / "out.json", True)
    assert data == {"projects": []}
    assert calls == [True, False]


def test_a_build_configuration_failure_is_refused_with_gradles_own_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    verbatim = (
        "FAILURE: Build failed with an exception.\n"
        "* What went wrong:\nA problem occurred evaluating root project 'x'.\n"
        "> Could not find method sextantModel() for arguments...\n"
    )

    def fake_run_once(gradle_command, path, out_file, offline):
        return _completed(1, verbatim)

    monkeypatch.setattr(GradleDetector, "_run_once", staticmethod(fake_run_once))
    with pytest.raises(ValueError) as failure:
        GradleDetector()._invoke(["./gradlew"], tmp_path, tmp_path / "out.json", False)
    assert "Could not find method sextantModel" in str(failure.value)


def test_distribution_absent_is_recognised_even_on_the_second_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list[bool] = []

    def fake_run_once(gradle_command, path, out_file, offline):
        calls.append(offline)
        if offline:
            return _completed(
                1,
                "FAILURE: Build failed with an exception.\n"
                "> No cached version of org.springframework:spring-web:6.1.6 available for "
                "offline mode.\n",
            )
        return _completed(1, 'Exception in thread "main" java.io.IOException: 404\n')

    monkeypatch.setattr(GradleDetector, "_run_once", staticmethod(fake_run_once))
    with pytest.raises(ValueError, match="Gradle distribution not present"):
        GradleDetector()._invoke(["./gradlew"], tmp_path, tmp_path / "out.json", True)
    assert calls == [True, False]
