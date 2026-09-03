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
into the repository it runs against and may start a background daemon.

**Boundaries, stated rather than introspected (2M design §1c).** A composite
build (`includeBuild`) is invisible to this detector — `allprojects` walks
the ROOT build's own project tree only, so an included build's projects are
silently absent from the model, never partially read. Android variants are
not modelled: this detector reads the plain JVM-language source-set shape
Gradle's own `main` source set already exposes, nothing richer.
`buildSrc` convention-plugin SOURCES are never read —
the init script reads the EVALUATED model, so a convention plugin's effects
on a project (its extra source sets, its applied plugins) are visible, but
`buildSrc/src` itself is not. A Gradle version too old to run this init
script fails with Gradle's own error — the same generic build-configuration
refusal every other build failure gets, needing no special case here.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from sextant.application.ports.detector import LibraryRoot, ModuleModel, RepositoryModel
from sextant.ingress.detect.sextant_config import read_extract_libraries

_SETTINGS_FILES = ("settings.gradle.kts", "settings.gradle")
_SINGLE_MODULE_BUILD_FILES = ("build.gradle.kts", "build.gradle")

# Sextant's own read-only probe, packaged beside this module — one location,
# checkout and wheel alike (hatchling's default wheel layout carries every
# file under `src/sextant`, the same way it already carries the catalogs and
# the enrichment instructions), so a version mismatch between this detector
# and the script it runs cannot happen. Resolved relative to `__file__`
# rather than through `sextant.cli.resources` (2M Task 3): the import-linter
# layering contract (`cli -> ingress|... -> application -> domain`) puts
# `cli` OUTSIDE `ingress`, so a detector may not import it.
_INIT_SCRIPT = Path(__file__).with_name("sextant-model.init.gradle")

# Files that declare how the module is packaged to run — the same
# framework-neutral evidence `MavenDetector._CONTAINER_FILES` reads, and
# never a framework name (M02).
_CONTAINER_FILES = (
    "Dockerfile",
    "Containerfile",
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
)

# The same schema-root conventions `MavenDetector` reads (2M design §1's own
# words: "the schema-root conventions ... the Maven detector already reads")
# — duplicated rather than imported, because the init script's own JSON
# carries no such field (Interfaces' pinned schema has none): these are pure
# directory-existence facts about `dir`, checked the same way regardless of
# which build system named that directory.
_SCHEMA_ROOT_NAMES = ("proto", "avro")
_SCHEMA_ROOT_PATHS = (
    *((name,) for name in _SCHEMA_ROOT_NAMES),
    ("resources", "graphql"),
    ("resources", "wsdl"),
    ("resources", "xsd"),
    ("resources", "META-INF", "wsdl"),
)

_WRAPPER_FALLBACK_NOTE = "no ./gradlew wrapper at the repository root; used `gradle` on PATH"

# Gradle's own top-of-output banner, printed for EVERY build failure once
# Gradle itself has actually started (a dependency refusal, a task failure, a
# configuration error alike). Its absence is the cold-start signal (2M design
# §1): the wrapper never got as far as starting Gradle at all, which is what
# distinguishes "the distribution is not present" from every other failure —
# having it is treated like having `mvn` installed, not like a dependency.
_BUILD_FAILURE_BANNER = "FAILURE: Build failed with an exception."

# A stable SUBSTRING of Gradle's own wording for an offline dependency
# refusal (2M design §4), verified live against Gradle 9.7.1: "No cached
# version of <coordinate> available for offline mode." Gradle's own words
# carry the reason (DR-6); this is only the substring this detector
# recognises to decide whether an online retry is worth offering.
_OFFLINE_REFUSAL_SUBSTRING = "available for offline mode"


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


def _distribution_absent_message(path: Path) -> str:
    """Cold-start taxonomy class 1 (2M design §1): the wrapper distribution
    itself is absent and must be downloaded before ANY task can run —
    `--offline` never governs this, so it is reported distinctly from a
    dependency refusal. Names the wrapper properties file where one exists;
    the `gradle`-on-PATH fallback has none to name."""
    properties = path / "gradle" / "wrapper" / "gradle-wrapper.properties"
    if properties.is_file():
        return (
            f"Gradle distribution not present — {properties} names a distribution "
            "Gradle could not obtain before running any task"
        )
    return "Gradle distribution not present — Gradle could not start before running any task"


def _is_distribution_absent(output: str) -> bool:
    return _BUILD_FAILURE_BANNER not in output


def _read_json(out_file: Path) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(out_file.read_text(encoding="utf-8"))
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
        subprocess half.

        The root project (Gradle's own `:` path) is never itself a
        `ModuleModel`, the same way an aggregation-only POM's own element
        never becomes one (2M design §2) — only when it names no OTHER
        project is it the sole module, exactly as a single-module Gradle
        build (no settings file) has none to name."""
        projects = data["projects"]
        subprojects = [project for project in projects if project["path"] != ":"]
        multi_module = len(subprojects) > 0
        selected = subprojects if multi_module else [p for p in projects if p["path"] == ":"]
        modules = tuple(
            GradleDetector._module_of(Path(project["dir"]), project) for project in selected
        )
        notes = tuple(sorted(note for note in (wrapper_note,) if note))
        return RepositoryModel(root=path, modules=modules, notes=notes, multi_module=multi_module)

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
            raise ValueError(_distribution_absent_message(path))
        if not (allow_resolve and _OFFLINE_REFUSAL_SUBSTRING in combined):
            raise ValueError(combined.strip())

        second = self._run_once(gradle_command, path, out_file, offline=False)
        if second.returncode != 0:
            combined_retry = second.stdout + second.stderr
            if _is_distribution_absent(combined_retry):
                raise ValueError(_distribution_absent_message(path))
            raise ValueError(combined_retry.strip())
        return _read_json(out_file)

    @staticmethod
    def _run_once(
        gradle_command: list[str], path: Path, out_file: Path, offline: bool
    ) -> subprocess.CompletedProcess[str]:
        argv = _compose_argv(gradle_command, _INIT_SCRIPT, out_file, offline)
        return subprocess.run(argv, cwd=path, capture_output=True, text=True, check=False)

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
        source_roots = tuple(Path(root) for root in project["sourceRoots"])
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
            output_dirs=tuple(Path(root) for root in project["classesDirs"]),
            resource_roots=tuple(Path(root) for root in project["resourceRoots"]),
            schema_roots=tuple(
                root
                for parts in _SCHEMA_ROOT_PATHS
                if (root := path.joinpath("src", "main", *parts)).is_dir()
            ),
            library_roots=library_roots,
            libraries_not_resolved=libraries_not_resolved,
        )

    @staticmethod
    def _classify(path: Path, project: dict[str, Any]) -> str:
        """Service, library, or undetermined (M02, widened by 2M design §2):
        a container file beside the project is the same framework-neutral
        service evidence `MavenDetector` reads. `library` is the
        Gradle-only deviation — a publishing plugin applied is evidence a
        POM alone can never carry, so `MavenDetector` never returns it."""
        if any((path / name).is_file() for name in _CONTAINER_FILES):
            return "service"
        if project["publishing"]:
            return "library"
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

        A classpath entry Gradle reports with NO component id (a local
        `files()` dependency, a flat-dir repository entry — 2M design §1) can
        never be named by any coordinate `extract_libraries` declares, so
        opt-in cannot gate it either way; it joins `libraries_not_resolved`
        unconditionally, by its path, with its own distinct reason.
        """
        unresolved: list[str] = [
            f"{entry['path']}: gradle resolved this classpath entry to no component id "
            "(a local file() or flatDir dependency, most likely) — cannot form a library "
            "coordinate"
            for entry in classpath
            if not entry.get("group") or not entry.get("name")
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
