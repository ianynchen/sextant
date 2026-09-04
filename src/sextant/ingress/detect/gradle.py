"""`GradleDetector` (2M design §1): sibling of `MavenDetector`, but where Maven
reads its build file directly, Gradle has no such file to read — the model a
`build.gradle(.kts)` describes exists only once Gradle itself has evaluated
it. So this detector LEARNS the build by running the target repository's own
`./gradlew`, driven by a read-only init script packaged beside this module
(`sextant-model.init.gradle`), which walks `allprojects` at task-execution
time and writes one JSON document to a `-P`-named file — never stdout, which
Gradle itself, the target build's own scripts, and JVM warnings all pollute.

**Honesty (2M design §1a).** Invoking `./gradlew` executes the target
repository's own build code — the same trust already extended when the
fixture suite compiles Maven fixtures with `mvn` (build plugins are code).
Sextant adds no sandbox around that. Nor is this detector filesystem-read-only
for the target the way `MavenDetector` is: Gradle writes `.gradle/` state
into the repository it runs against and may start a background daemon. And
the probe is not cheap or narrowly scoped (2M Task 3 fix round 1, I4): the
init script's `sextantModel` task depends on EVERY source-set-owning
project's own `classes` task, so one invocation compiles the ENTIRE target
build — every
project, including ones the CLI will go on to skip-list — takes however long
that full compile takes, and one project's compile failure refuses detection
for the whole repository, not only that project.

**Boundaries, stated where they arise (2M design §1c, widened by fix round
1).** A composite build (`includeBuild`) is invisible to `allprojects` —
`gradle.includedBuilds` names what was excluded, and a non-empty list
becomes a detect note (I1) rather than a silent absence. A root project that
carries its own source alongside subprojects loses that source the same way
an aggregation-only POM's own element does (2M design §2) — also a detect
note now (I2), never silent. Android variants are not modelled: this
detector reads the plain JVM-language source-set shape Gradle's own `main`
source set already exposes, nothing richer. `buildSrc` convention-plugin
SOURCES are never read — the init script reads the EVALUATED model, so a
convention plugin's effects on a project (its extra source sets, its applied
plugins) are visible, but `buildSrc/src` itself is not. A Gradle version too
old to run this init script fails with Gradle's own error — the same generic
build-configuration refusal every other build failure gets, needing no
special case here.
"""

import json
import os
import shutil
import subprocess
import tempfile
from importlib import resources
from pathlib import Path
from typing import Any

from sextant.application.ports.detector import LibraryRoot, ModuleModel, RepositoryModel
from sextant.ingress.detect.conventions import (
    CONTAINER_FILES,
    RESOURCE_SCHEMA_SUFFIXES,
    SOURCE_SCHEMA_NAMES,
)
from sextant.ingress.detect.sextant_config import read_extract_libraries

_SETTINGS_FILES = ("settings.gradle.kts", "settings.gradle")
_SINGLE_MODULE_BUILD_FILES = ("build.gradle.kts", "build.gradle")

_INIT_SCRIPT_RESOURCE = ("ingress", "detect", "sextant-model.init.gradle")

_WRAPPER_FALLBACK_NOTE = "no ./gradlew wrapper at the repository root; used `gradle` on PATH"

_COMPOSITE_BUILD_NOTE_PREFIX = "composite build: included builds not analyzed: "

# A stable SUBSTRING of Gradle's own wording for an offline dependency
# refusal (2M design §4), verified live against Gradle 9.7.1: "No cached
# version of <coordinate> available for offline mode." Gradle's own words
# carry the reason (DR-6); this is only the substring this detector
# recognises to decide whether an online retry is worth offering.
_OFFLINE_REFUSAL_SUBSTRING = "available for offline mode"

# Positive evidence that Gradle's OWN wrapper bootstrap — never Gradle's real
# build engine — produced this output (2M Task 3 fix round 1, C2). Verified
# live against Gradle 9.7.1: a wrapper pointed at a distribution version that
# 404s prints `Exception in thread "main" ... at org.gradle.wrapper.Download
# ...`, never the build-failure banner. Checking for the banner's ABSENCE
# alone (this detector's first cut) misclassified every OTHER pre-Gradle
# failure the same way — verified live with a bad `JAVA_HOME`, which prints
# neither the banner nor any of these substrings, and correctly falls
# through to the verbatim class-3 refusal instead of being read as "the
# distribution is absent".
_WRAPPER_BOOTSTRAP_SUBSTRINGS = (
    "org.gradle.wrapper.",
    "Downloading https",
    "Could not create local gradle distribution",
)


class MissingInitScriptError(FileNotFoundError):
    """Sextant's own Gradle probe is not where the install put it."""


def _init_script() -> Path:
    """The packaged init script, resolved through the installed package (2M
    Task 3 fix round 1, I7) — the same reasoning `sextant.resources`
    already states for the catalogs/extractor/instructions (a version
    mismatch cannot happen when a resource travels with the code that reads
    it), without importing that module: the import-linter layering contract
    (`cli -> ingress|... -> application -> domain`) puts `cli` OUTSIDE
    `ingress`, so a detector may not import it."""
    path = Path(str(resources.files("sextant"))).joinpath(*_INIT_SCRIPT_RESOURCE)
    if not path.is_file():
        raise MissingInitScriptError(f"the Gradle init script is not at {path}")
    return path


def _compose_argv(
    gradle_command: list[str], init_script: Path, out_file: Path, offline: bool
) -> list[str]:
    """The composed argv (2M design §1, pinned): `<gradle> --init-script
    <ours> --no-configuration-cache -q sextantModel -Psextant.out=<tmpfile>`,
    with `--offline` prepended for the first attempt only — network posture
    is the ONE thing that differs between the two attempts `detect` may
    make."""
    argv = [*gradle_command]
    if offline:
        argv.append("--offline")
    argv += [
        "--init-script",
        str(init_script),
        "--no-configuration-cache",
        "-q",
        "sextantModel",
        f"-Psextant.out={out_file}",
    ]
    return argv


def _distribution_absent_message(path: Path, output: str) -> str:
    """Cold-start taxonomy class 1 (2M design §1): the wrapper distribution
    itself is absent and must be downloaded before ANY task can run —
    `--offline` never governs this, so it is reported distinctly from a
    dependency refusal. Names the wrapper properties file where one exists
    (the `gradle`-on-PATH fallback has none to name), and carries Gradle's
    own output too (2M Task 3 fix round 1, C2) — DR-6 applies to this class
    exactly as it does to the other two; naming the file alone dropped
    Gradle's own words on the floor."""
    properties = path / "gradle" / "wrapper" / "gradle-wrapper.properties"
    named = (
        f"Gradle distribution not present — {properties} names a distribution "
        "Gradle could not obtain before running any task"
        if properties.is_file()
        else "Gradle distribution not present — Gradle could not start before running any task"
    )
    return f"{named}:\n{output.strip()}"


def _is_distribution_absent(output: str) -> bool:
    return any(substring in output for substring in _WRAPPER_BOOTSTRAP_SUBSTRINGS)


def _read_json(out_file: Path) -> dict[str, Any]:
    """The init script's own JSON, read back — wrapped into a named refusal
    for two escape hatches a zero exit code does not rule out (2M Task 3 fix
    round 1, I6): a `sextantModel` name collision or an overriding build
    script could exit 0 without ever running OUR task's `doLast`, leaving no
    file to read at all; and the file that IS there might not parse."""
    try:
        text = out_file.read_text(encoding="utf-8")
    except FileNotFoundError as missing:
        raise ValueError(
            f"gradle exited successfully but wrote no model to {out_file} — the target "
            "build may have overridden the sextantModel task"
        ) from missing
    try:
        document: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError as malformed:
        raise ValueError(f"gradle wrote invalid JSON to {out_file}: {malformed}") from malformed
    return document


class GradleDetector:
    """Learns the build by running it (2M design §1): `accepts()` reads only
    file NAMES (a settings file, or a build file where no settings file
    exists — a single-module build), and `detect()` invokes the project's own
    `./gradlew`, falling back to a `gradle` on PATH with the fallback
    recorded as a detect note. One invocation per attempt, at most two
    attempts — offline, then a flagged online retry — and never twice per
    `analyze` (the CLI's own `_KnownModuleDetector` is what keeps a second
    real detection from ever happening; this class only ever runs once per
    `detect()` call).
    """

    def accepts(self, path: Path) -> bool:
        if any((path / name).is_file() for name in _SETTINGS_FILES):
            return True
        return any((path / name).is_file() for name in _SINGLE_MODULE_BUILD_FILES)

    def detect(self, path: Path, allow_resolve: bool = False) -> RepositoryModel:
        gradle_command, wrapper_note = self._gradle_command(path)
        with tempfile.TemporaryDirectory() as workdir:
            out_file = Path(workdir) / "sextant-model.json"
            data = self._invoke(gradle_command, path, out_file, allow_resolve)
        return self._repository_model(path, data, wrapper_note)

    @staticmethod
    def _repository_model(
        path: Path, data: dict[str, Any], wrapper_note: str | None
    ) -> RepositoryModel:
        """The init script's own JSON, translated into a `RepositoryModel` —
        pulled out of `detect()` so the unit suite drives it straight from a
        CAPTURED document (2M design §4: "no Gradle invocation in unit
        tests"), the same separation `detect()`'s own `_invoke` keeps for the
        subprocess half. A key the init script's own schema promises but this
        JSON does not carry (2M Task 3 fix round 1, I6) is a named refusal,
        not a bare `KeyError` reading as a crash in the tool.

        The root project (Gradle's own `:` path) is never itself a
        `ModuleModel`, the same way an aggregation-only POM's own element
        never becomes one (2M design §2) — only when it names no OTHER
        project is it the sole module, exactly as a single-module Gradle
        build (no settings file) has none to name."""
        try:
            projects = data["projects"]
            subprojects = [project for project in projects if project["path"] != ":"]
            multi_module = len(subprojects) > 0
            selected = subprojects if multi_module else [p for p in projects if p["path"] == ":"]
            modules = tuple(
                GradleDetector._module_of(Path(project["dir"]), project) for project in selected
            )
            notes: list[str] = [note for note in (wrapper_note,) if note]
            notes.extend(GradleDetector._composite_build_notes(data))
            if multi_module:
                notes.extend(GradleDetector._root_sources_notes(projects))
        except KeyError as missing:
            raise ValueError(
                f"gradle's own model JSON is missing the {missing} key — the init script "
                "and this detector may be out of step"
            ) from missing
        return RepositoryModel(
            root=path, modules=modules, notes=tuple(sorted(notes)), multi_module=multi_module
        )

    @staticmethod
    def _composite_build_notes(data: dict[str, Any]) -> tuple[str, ...]:
        """`includeBuild` composite builds are invisible to `allprojects`
        (2M design §1c) — stated, not silent (2M Task 3 fix round 1, I1):
        the init script names every included build, and a non-empty list
        becomes one note naming all of them."""
        included = data.get("includedBuilds", [])
        if not included:
            return ()
        return (f"{_COMPOSITE_BUILD_NOTE_PREFIX}{', '.join(sorted(included))}",)

    @staticmethod
    def _root_sources_notes(projects: list[dict[str, Any]]) -> tuple[str, ...]:
        """A root project that carries its own source alongside subprojects
        loses that source the same way an aggregation-only POM's own
        element does (2M design §2) — stated, not silent (2M Task 3 fix
        round 1, I2)."""
        root = next((project for project in projects if project["path"] == ":"), None)
        if root is None or (not root["sourceRoots"] and not root["classesDirs"]):
            return ()
        message = (
            f"gradle root project at {root['dir']} declares its own source but is not "
            "analyzed — it aggregates subprojects (2M design §2's aggregation-only convention)"
        )
        return (message,)

    @staticmethod
    def _gradle_command(path: Path) -> tuple[list[str], str | None]:
        """The project's own wrapper, always preferred — falling back to a
        `gradle` on PATH with the fallback recorded as a detect note (2M
        design §1)."""
        wrapper = path / ("gradlew.bat" if os.name == "nt" else "gradlew")
        if wrapper.is_file():
            return [str(wrapper)], None
        on_path = shutil.which("gradle")
        if on_path is None:
            raise ValueError(
                f"{path} has no ./gradlew wrapper and no `gradle` is on PATH — commit the "
                "project's own wrapper, or install Gradle"
            )
        return [on_path], _WRAPPER_FALLBACK_NOTE

    def _invoke(
        self, gradle_command: list[str], path: Path, out_file: Path, allow_resolve: bool
    ) -> dict[str, Any]:
        """Runs `sextantModel`, offline first, applying the cold-start
        taxonomy (2M design §1) to a failure: distribution-absent is checked
        BEFORE anything else, on either attempt, because it is not a build
        failure at all — Gradle itself never started. An offline dependency
        refusal is retried online exactly once when `allow_resolve` permits
        it; any other failure, and a failed retry, surfaces as Gradle's own
        error verbatim (DR-6)."""
        first = self._run_once(gradle_command, path, out_file, offline=True)
        if first.returncode == 0:
            return _read_json(out_file)

        combined = first.stdout + first.stderr
        if _is_distribution_absent(combined):
            raise ValueError(_distribution_absent_message(path, combined))
        if not (allow_resolve and _OFFLINE_REFUSAL_SUBSTRING in combined):
            raise ValueError(combined.strip())

        second = self._run_once(gradle_command, path, out_file, offline=False)
        if second.returncode != 0:
            combined_retry = second.stdout + second.stderr
            if _is_distribution_absent(combined_retry):
                raise ValueError(_distribution_absent_message(path, combined_retry))
            raise ValueError(combined_retry.strip())
        return _read_json(out_file)

    # A cap, not a guess at how long a real build takes (2M Task 3 fix round
    # 1, M3): the init script's own `sextantModel` task compiles the whole
    # target build (I4), so this has to be generous — but a build that never
    # finishes must become a named refusal, never a hang nothing ever
    # reports.
    _SUBPROCESS_TIMEOUT_SECONDS = 900

    @staticmethod
    def _run_once(
        gradle_command: list[str], path: Path, out_file: Path, offline: bool
    ) -> subprocess.CompletedProcess[str]:
        argv = _compose_argv(gradle_command, _init_script(), out_file, offline)
        try:
            return subprocess.run(
                argv,
                cwd=path,
                capture_output=True,
                text=True,
                check=False,
                timeout=GradleDetector._SUBPROCESS_TIMEOUT_SECONDS,
            )
        except PermissionError as refused:
            # Routine for a zip-delivered checkout (2M Task 3 fix round 1,
            # I6): `./gradlew`'s executable bit does not always survive a
            # zip/tarball round trip, and the OS's refusal to exec it is not
            # a build failure to report as one.
            raise ValueError(f"{gradle_command[0]} is not executable: {refused}") from refused
        except subprocess.TimeoutExpired as expired:
            raise ValueError(
                f"gradle did not finish within {GradleDetector._SUBPROCESS_TIMEOUT_SECONDS}s: "
                f"{' '.join(argv)}"
            ) from expired

    @staticmethod
    def _module_of(path: Path, project: dict[str, Any]) -> ModuleModel:
        name = project["name"]
        group = project["group"]
        version = project["version"]
        # Coordinates Gradle leaves loose are a loud refusal naming the
        # missing one (2M design §1) — the same discipline `MavenDetector`
        # applies to a POM missing `<groupId>`/`<version>`, never a
        # `:name`-shaped module id.
        if not group:
            raise ValueError(f"gradle project {name} declares no group — cannot form a module id")
        if version == "unspecified":
            raise ValueError(
                f"gradle project {name} declares no version (Gradle's own `unspecified` "
                "default) — cannot form a module id"
            )
        # Gradle NAMES a source/resource root as a build convention; it does
        # not promise the directory exists on disk (2M Task 3 fix round 1,
        # M1) — the same "no guess" discipline `MavenDetector`'s own
        # `resource_roots` already keeps, applied here to a report this
        # detector did not derive itself.
        source_roots = tuple(
            root for root in (Path(entry) for entry in project["sourceRoots"]) if root.is_dir()
        )
        resource_roots = tuple(
            root for root in (Path(entry) for entry in project["resourceRoots"]) if root.is_dir()
        )
        library_roots, libraries_not_resolved = GradleDetector._library_roots(
            path, project["classpath"]
        )
        return ModuleModel(
            module_id=f"{group}:{name}",
            coordinates=f"{group}/{name}",
            version=version,
            root=path,
            kind=GradleDetector._classify(path, project),
            # Gradle's own default is `jar` in every sense that matters here:
            # a project without a source-set-owning plugin applied has
            # nothing this detector can scan (empty `classesDirs`), the exact
            # shape a Maven leaf packaged `pom` has — reusing `"pom"` lets
            # the CLI's existing skip gate (`_skip_reason`, 2M design §2)
            # recognise it without any Gradle-specific case there.
            packaging="jar" if project["classesDirs"] else "pom",
            languages=frozenset(root.name for root in source_roots),
            source_roots=source_roots,
            output_dirs=tuple(Path(entry) for entry in project["classesDirs"]),
            resource_roots=resource_roots,
            schema_roots=GradleDetector._schema_roots(project),
            # The RESOLVED compile classpath's own coordinates, transitives
            # included — sorted and deduplicated (NFR-1). Only entries Gradle
            # gave a component id: an inter-project dependency and a
            # `files()` entry carry no coordinate at all (the init script's
            # own rule), and inventing one for them would name an artifact
            # nobody published.
            dependency_coordinates=tuple(
                sorted(
                    {
                        f"{entry['group']}:{entry['name']}"
                        for entry in project["classpath"]
                        if entry.get("group") and entry.get("name")
                    }
                )
            ),
            library_roots=library_roots,
            libraries_not_resolved=libraries_not_resolved,
        )

    @staticmethod
    def _schema_roots(project: dict[str, Any]) -> tuple[Path, ...]:
        """The same schema-root conventions `MavenDetector` reads (2M design
        §1), with one gap closed (2M Task 3 fix round 1, I5): the three
        classpath-resource conventions (SDL/WSDL/XSD) are probed under
        whichever resource root(s) the build ACTUALLY reports, not a
        hardcoded `src/main/resources` guess — a non-conventional resources
        directory (`sourceSets.main.resources.srcDir(...)`) is exactly what
        Maven's own hardcoded equivalent cannot see. `proto`/`avro` stay a
        sibling-to-source convention, the same as Maven's own: no per-build
        override exists for either to read instead."""
        dir_path = Path(project["dir"])
        found = [
            root
            for name in SOURCE_SCHEMA_NAMES
            if (root := dir_path.joinpath("src", "main", name)).is_dir()
        ]
        for resource_root in (Path(entry) for entry in project["resourceRoots"]):
            for suffix in RESOURCE_SCHEMA_SUFFIXES:
                candidate = resource_root.joinpath(*suffix)
                if candidate.is_dir():
                    found.append(candidate)
        return tuple(found)

    @staticmethod
    def _classify(path: Path, project: dict[str, Any]) -> str:
        """Service or undetermined, from evidence — the same two answers
        `MavenDetector._classify` gives, from the same framework-neutral
        container-file evidence.

        **`library` is never returned, and publishing is never read** (user
        ruling, 2026-09-04). A publishing plugin says where artifacts GO, not
        what the module CONTAINS: a user has many ways to publish, may publish
        by a mechanism invisible to us, or may build locally and never publish
        at all. Whether a module is worth reading is decided by code
        reference, not by distribution. `MavenDetector` already refuses the
        same guess in almost these words — "every POM declares coordinates
        whether anything is published or not — reading that as evidence would
        be the guess this method exists to refuse" — and this method used to
        make exactly that guess for Gradle, which made the SAME repo analyze
        differently under the two build systems.

        This holds as long as skipping is decided from module kind at all; a
        future skip rule must rest on there being provably nothing to scan
        (`packaging=pom`), never on an inference about a module's purpose."""
        if any((path / name).is_file() for name in CONTAINER_FILES):
            return "service"
        return "undetermined"

    @staticmethod
    def _library_roots(
        path: Path, classpath: list[dict[str, Any]]
    ) -> tuple[tuple[LibraryRoot, ...], tuple[str, ...]]:
        """`extract_libraries` (2I design §5) works for Gradle through its
        OWN route (2M design §1): the archive is the path Gradle already
        resolved, never a guessed `~/.gradle/caches` layout, and the version
        is the one Gradle's own component id reports (or the one pinned in
        `.sextant.yml`, for the same escape-hatch reason `MavenDetector`
        keeps one).

        A classpath entry Gradle reports with NO component id splits two
        ways (2M Task 3 fix round 1, I3). An INTER-PROJECT dependency
        (`project(":other")`) is internal wiring Gradle resolved just fine —
        the init script marks it `internal` (its component id is a
        `ProjectComponentIdentifier`, never a `ModuleComponentIdentifier`),
        and this detector excludes it from the gap list outright: the
        project it names is already its own entry in `projects[]`, not a
        library nobody could find. Anything else with no component id (a
        local `files()` dependency, a flat-dir repository entry) genuinely
        has no coordinate `extract_libraries` could ever have named, so
        opt-in cannot gate it either way; it joins `libraries_not_resolved`
        unconditionally, by its path, with its own distinct reason.
        """
        unresolved: list[str] = [
            f"{entry['path']}: gradle resolved this classpath entry to no component id "
            "(a local file() or flatDir dependency, most likely) — cannot form a library "
            "coordinate"
            for entry in classpath
            if not entry.get("internal") and (not entry.get("group") or not entry.get("name"))
        ]
        declared = read_extract_libraries(path)
        if not declared:
            return (), tuple(unresolved)

        by_coordinate: dict[str, list[dict[str, Any]]] = {}
        for entry in classpath:
            group, name = entry.get("group"), entry.get("name")
            if group and name:
                by_coordinate.setdefault(f"{group}:{name}", []).append(entry)

        roots: list[LibraryRoot] = []
        for item in declared:
            group, artifact, *pinned = item.split(":")
            coordinate = f"{group}:{artifact}"
            candidates = by_coordinate.get(coordinate, [])
            version: str | None
            if pinned:
                version = pinned[0]
                match = next((c for c in candidates if c.get("version") == version), None)
            else:
                match = candidates[0] if candidates else None
                version = match.get("version") if match else None
            if match is None or not version:
                unresolved.append(
                    f"{coordinate}: this module's compile classpath does not resolve this "
                    "dependency — declare it, or pin the version in .sextant.yml"
                )
                continue
            roots.append(
                LibraryRoot(coordinate=coordinate, version=version, archive=Path(match["path"]))
            )
        return tuple(roots), tuple(unresolved)
