"""`GradleDetector` (2M design §1): sibling of `MavenDetector`, but where Maven
reads its build file directly, Gradle has no such file to read — the model a
`build.gradle(.kts)` describes exists only once Gradle itself has evaluated
it. So this detector LEARNS the build by running the target repository's own
`./gradlew`, driven by a read-only init script packaged beside this module
(`sextant-model.init.gradle`). Each project's own task writes that project's
records, and the root project's task names every project, all into a
`-P`-named folder (Android design M4) — never stdout, which Gradle itself,
the target build's own scripts, and JVM warnings all pollute. `_assemble`
joins the files into one document.

**Honesty (2M design §1a).** Invoking `./gradlew` executes the target
repository's own build code — the same trust already extended when the
fixture suite compiles Maven fixtures with `mvn` (build plugins are code).
Sextant adds no sandbox around that. Nor is this detector filesystem-read-only
for the target the way `MavenDetector` is: Gradle writes `.gradle/` state
into the repository it runs against and may start a background daemon. And
the probe is not cheap or narrowly scoped (2M Task 3 fix round 1, I4): the
init script's `sextantModel` task in EVERY source-set-owning project depends
on that project's own `classes` task, so one invocation compiles the ENTIRE
target build — every
project, including ones the CLI will go on to skip-list — and takes however
long that full compile takes. Gradle runs with `--continue` (Android design
M5), so a project whose build fails does not stop the others: that project,
and each project that needs it, is skipped with Gradle's own reason, and the
other projects are read.

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
import re
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from importlib import resources
from pathlib import Path
from typing import Any, NamedTuple

from sextant.application.ports.detector import LibraryRoot, ModuleModel, RepositoryModel
from sextant.domain.symbols import NOT_APPLICABLE
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

# The same refusal for a PLUGIN (OI-273 fix round 1). Offline, a plugin Gradle has never
# cached reports "Plugin [id: ...] was not found in any of the following sources", its
# plugin-repository line reading "could not resolve plugin artifact '<id>:<id>.gradle.
# plugin:<version>'" — measured on Gradle 8.14.1 and 9.5.0 — and never the dependency
# wording above. The first attempt is always offline, so the cache is all it consulted.
_OFFLINE_PLUGIN_REFUSAL_SUBSTRING = "could not resolve plugin artifact"

# Gradle's own build-failure banners: printed only once the build ENGINE ran, so either
# one proves the distribution was there (OI-273 fix round 1). A wrapper that
# downloaded the distribution successfully prints `Downloading https://...` first, and the
# build may then fail for any reason of its own. One failed task gives the first banner;
# with `--continue`, two or more failed tasks give the second, "Build completed with 2
# failures." (Task 1 fix round 1, measured on Gradle 9.7.1).
_BUILD_FAILURE_BANNERS = (
    "FAILURE: Build failed with an exception.",
    "FAILURE: Build completed with ",
)

# The line that starts Gradle's own message for one failed task (Android design M5),
# measured on Gradle 9.7.1. Gradle 9 writes "(registered by plugin class '...')" after the
# task path, so only the start of the line is matched.
_FAILED_TASK = re.compile(r"^Execution failed for task '([^']+)'")

_OFFLINE_PARTS_NOTE = (
    "some parts need dependencies that are not in the local Gradle cache; "
    "--allow-resolve lets Gradle download them"
)

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


class _Identity(NamedTuple):
    """A project's module id, the `<package> <version>` its symbols carry, and whether
    it has Maven coordinates at all (`GradleDetector._identity`)."""

    module_id: str
    coordinates: str
    version: str
    published: bool


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
    gradle_command: list[str], init_script: Path, out_dir: Path, offline: bool
) -> list[str]:
    """The composed argv (2M design §1, pinned): `<gradle> --init-script
    <ours> --no-configuration-cache --continue -q sextantBuild sextantModel
    -Psextant.outDir=<tmpdir>`, with `--offline` prepended for the first
    attempt only — network posture is the ONE thing that differs between the
    two attempts `detect` may make. `sextantModel` runs in every project, each
    reading only its own configurations (Android design M4); `--continue` lets
    the other projects finish when one fails (M5)."""
    argv = [*gradle_command]
    if offline:
        argv.append("--offline")
    argv += [
        "--init-script",
        str(init_script),
        "--no-configuration-cache",
        "--continue",
        "-q",
        "sextantBuild",
        "sextantModel",
        f"-Psextant.outDir={out_dir}",
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
    """Wrapper-bootstrap evidence, and no sign the build engine ever ran: the banner
    alone was this detector's first cut and misread a bad `JAVA_HOME` (fix round 1, C2);
    the bootstrap substrings alone misread a SUCCESSFUL download followed by a build
    failure (OI-273 fix round 1). Both together."""
    if any(banner in output for banner in _BUILD_FAILURE_BANNERS):
        return False
    return any(substring in output for substring in _WRAPPER_BOOTSTRAP_SUBSTRINGS)


def _is_offline_refusal(output: str) -> bool:
    """Something the local cache lacked and the network might have — a dependency or a
    plugin — and so worth the one online retry `--allow-resolve` permits."""
    return _OFFLINE_REFUSAL_SUBSTRING in output or _OFFLINE_PLUGIN_REFUSAL_SUBSTRING in output


def _read_json(out_file: Path) -> Any:
    """The init script's own JSON, read back — wrapped into a named refusal
    for two escape hatches a zero exit code does not rule out (2M Task 3 fix
    round 1, I6): a `sextantBuild` name collision or an overriding build
    script could exit 0 without ever running OUR task's `doLast`, leaving no
    file to read at all; and the file that IS there might not parse."""
    try:
        text = out_file.read_text(encoding="utf-8")
    except FileNotFoundError as missing:
        raise ValueError(
            f"gradle exited successfully but wrote no model to {out_file} — the target "
            "build may have overridden the sextantBuild task"
        ) from missing
    try:
        return json.loads(text)
    except json.JSONDecodeError as malformed:
        raise ValueError(f"gradle wrote invalid JSON to {out_file}: {malformed}") from malformed


def _project_file_name(project_path: str) -> str:
    """The file a project's own `sextantModel` task writes: its path with every `_` made
    `__` first and then every `:` made `_`, so the root project `:` is `_`, `:libs:core` is
    `_libs_core` and `:libs_core` is `_libs__core` — two paths never share a file. The init
    script's own rule."""
    return f"{project_path.replace('_', '__').replace(':', '_')}.json"


def _failures_by_project(output: str) -> dict[str, str]:
    """Gradle's own message for each failed task, by the path of the project that owns the
    task (Android design M5): `:app:compileJava` belongs to `:app`, and `:compileJava` to
    the root project `:`. The message is the lines after `Execution failed for task '...'`
    up to the next blank line. Gradle puts "> " in front of the first line of a message and
    two spaces in front of each line that continues it (javac's own error lines are such
    lines); those two characters are removed, and the rest of each line is kept as Gradle
    wrote it. Two failed tasks of one project give one message, in Gradle's order."""
    lines = output.splitlines()
    found: dict[str, list[str]] = {}
    for index, line in enumerate(lines):
        failed = _FAILED_TASK.match(line)
        if failed is None:
            continue
        project_path = failed.group(1).rsplit(":", 1)[0] or ":"
        message = found.setdefault(project_path, [])
        for following in lines[index + 1 :]:
            if not following.strip():
                break
            message.append(following[2:] if following.startswith(("> ", "  ")) else following)
    return {path: "\n".join(message) for path, message in sorted(found.items())}


def _clear(out_dir: Path) -> None:
    """Removes every file a Gradle run wrote into `out_dir`, so the next run's result is
    read alone: a project file left by the offline attempt must not stand in for a project
    that failed on the online retry."""
    for entry in out_dir.iterdir():
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def _assemble(out_dir: Path, output: str = "") -> dict[str, Any]:
    """The one document `_repository_model` reads, joined from the files the init script
    wrote (Android design M4): `build.json` from the root project's `sextantBuild` names
    every project and the included builds, and each project's own `sextantModel` wrote a
    list of records under `projects/`. A project with no file gets one record with empty
    lists — its build identity only, nothing to scan. Records are in `(path, target)`
    order, so the document is the same on every run (NFR-1).

    `output` is Gradle's output from a run that FAILED, and empty for a run that did not
    (Android design M5). After a failed run, every project's `sextantModel` that ran wrote a
    file, so a project with no file was not built, and its record gets `buildFailure`: its
    own failed task's message, or else a statement that a project it needs failed, naming
    the projects that did. Where Gradle's output names no failed task at all, the reason
    is that output itself, as Gradle wrote it."""
    build = _read_json(out_dir / "build.json")
    failures = _failures_by_project(output)
    failed_paths = ", ".join(failures)
    try:
        records: list[dict[str, Any]] = []
        for project in build["projects"]:
            project_file = out_dir / "projects" / _project_file_name(str(project["path"]))
            if project_file.is_file():
                records.extend(_read_json(project_file))
                continue
            records.append(
                {
                    **project,
                    "sourceRoots": [],
                    "sourceLanguages": {},
                    "resourceRoots": [],
                    "classesDirs": [],
                    "declaredRelease": None,
                    "publishing": False,
                    "classpath": [],
                    "target": None,
                    "platform": None,
                }
            )
            if output:
                records[-1]["buildFailure"] = failures.get(
                    str(project["path"]),
                    f"not built: a part it needs failed to build ({failed_paths})"
                    if failures
                    else output.strip(),
                )
        included_builds = build["includedBuilds"]
    except KeyError as missing:
        raise ValueError(
            f"gradle's own build JSON is missing the {missing} key — the init script "
            "and this detector may be out of step"
        ) from missing
    records.sort(key=lambda record: (str(record["path"]), str(record.get("target") or "")))
    return {"projects": records, "includedBuilds": included_builds}


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
            data = self._invoke(gradle_command, path, Path(workdir), allow_resolve)
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
                GradleDetector._module_of(Path(project["dir"]), project, projects)
                for project in selected
            )
            notes: list[str] = [note for note in (wrapper_note,) if note]
            notes.extend(GradleDetector._composite_build_notes(data))
            notes.extend(data.get("notes", []))
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
        self, gradle_command: list[str], path: Path, out_dir: Path, allow_resolve: bool
    ) -> dict[str, Any]:
        """Runs `sextantBuild` and `sextantModel`, offline first, applying the cold-start
        taxonomy (2M design §1) to a failure: distribution-absent is checked
        BEFORE anything else, on either attempt, because it is not a build
        failure at all — Gradle itself never started. An offline dependency
        refusal is retried online exactly once when `allow_resolve` permits
        it, into an empty output folder.

        A failed run that still wrote `build.json` is a PARTIAL result (Android design
        M5): `--continue` let every project that could build finish, and `_assemble`
        gives each project that did not its reason. Without `allow_resolve`, an offline
        refusal in it adds a note that names the flag. A failed run with no `build.json`
        never reached the projects at all, and surfaces as Gradle's own error verbatim
        (DR-6)."""
        first = self._run_once(gradle_command, path, out_dir, offline=True)
        if first.returncode == 0:
            return _assemble(out_dir)

        combined = first.stdout + first.stderr
        if _is_distribution_absent(combined):
            raise ValueError(_distribution_absent_message(path, combined))
        if not (allow_resolve and _is_offline_refusal(combined)):
            notes = [_OFFLINE_PARTS_NOTE] if _is_offline_refusal(combined) else []
            return self._partial(out_dir, combined, notes)

        _clear(out_dir)
        second = self._run_once(gradle_command, path, out_dir, offline=False)
        if second.returncode == 0:
            return _assemble(out_dir)
        combined_retry = second.stdout + second.stderr
        if _is_distribution_absent(combined_retry):
            raise ValueError(_distribution_absent_message(path, combined_retry))
        return self._partial(out_dir, combined_retry, [])

    @staticmethod
    def _partial(out_dir: Path, output: str, notes: list[str]) -> dict[str, Any]:
        """A failed run's result: the projects that built, and a reason for each that did
        not, when Gradle got as far as writing `build.json`; Gradle's own error verbatim
        when it did not."""
        if not (out_dir / "build.json").is_file():
            raise ValueError(output.strip())
        return {**_assemble(out_dir, output), "notes": notes}

    # A cap, not a guess at how long a real build takes (2M Task 3 fix round
    # 1, M3): the init script's own `sextantModel` task compiles the whole
    # target build (I4), so this has to be generous — but a build that never
    # finishes must become a named refusal, never a hang nothing ever
    # reports.
    _SUBPROCESS_TIMEOUT_SECONDS = 900

    @staticmethod
    def _run_once(
        gradle_command: list[str], path: Path, out_dir: Path, offline: bool
    ) -> subprocess.CompletedProcess[str]:
        argv = _compose_argv(gradle_command, _init_script(), out_dir, offline)
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
    def _module_of(
        path: Path, project: dict[str, Any], reactor: Sequence[dict[str, Any]] = ()
    ) -> ModuleModel:
        # `reactor` defaults to EMPTY, which yields no siblings — the honest answer
        # for a caller that does not know the rest of the build, and what every
        # single-project build gets anyway. The detector's own call site passes the
        # real list; tests that build one project pass nothing and get the
        # pre-W55 behaviour, which is what they are about.
        identity = GradleDetector._identity(project, reactor)
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
        # W55: reactor siblings as library roots, the way `MavenDetector` has done
        # since W24 — appended to whatever `.sextant.yml` opted into, because a
        # sibling is a dependency in every sense that matters: it is on the
        # classpath, its types appear in this module's signatures, and the only
        # difference from a resolved jar is that it was built next door.
        siblings = GradleDetector._sibling_roots(project, reactor)
        library_roots = library_roots + siblings
        return ModuleModel(
            module_id=identity.module_id,
            coordinates=identity.coordinates,
            version=identity.version,
            root=path,
            kind=GradleDetector._classify(path, project),
            # Gradle's own default is `jar` in every sense that matters here:
            # a project without a source-set-owning plugin applied has
            # nothing this detector can scan (empty `classesDirs`), the exact
            # shape a Maven leaf packaged `pom` has — reusing `"pom"` lets
            # the CLI's existing skip gate (`_skip_reason`, 2M design §2)
            # recognise it without any Gradle-specific case there.
            packaging="jar" if project["classesDirs"] else "pom",
            languages=GradleDetector._languages(project, source_roots),
            source_roots=source_roots,
            output_dirs=tuple(Path(entry) for entry in project["classesDirs"]),
            resource_roots=resource_roots,
            schema_roots=GradleDetector._schema_roots(project),
            # Asked of Gradle rather than parsed out of a build script (W3b):
            # the value can come from a convention plugin, a toolchain or a
            # property, and only the evaluated model knows which one won.
            # `.get(...)` rather than `[...]`: a workspace analysed by an
            # OLDER init script has no such key, and a missing key is the same
            # absence as a project that declares nothing.
            declared_release=project.get("declaredRelease"),
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
            # The version Gradle resolved for each of them (F1). No resolution
            # of our own is needed or wanted on this side: the report is the
            # output of Gradle's own conflict resolution, so the version here
            # is the one that would actually be on the classpath — which is a
            # STRONGER answer than the Maven side's, where a version is read
            # off the poms that declare it and transitives are out of reach.
            #
            # An entry with no `version` is skipped rather than defaulted: a
            # `files()` entry and an inter-project dependency carry no
            # coordinate at all (they are already excluded above), and a
            # coordinate Gradle reported without a version is a shape nothing
            # here has seen — inventing one would be a release nobody cut.
            dependency_versions=GradleDetector._dependency_versions(project["classpath"]),
            # Gradle has only ever answered from its own resolved compile classpath, which
            # is what this label means (spec 2026-10-21 §3c); the Maven detector earns it
            # per module and falls back to `declared`, Gradle never does.
            dependency_source="gradle",
            library_roots=library_roots,
            sibling_coordinates=tuple(root.coordinate for root in siblings),
            libraries_not_resolved=libraries_not_resolved,
            # Gradle resolved the compile classpath itself and the init script records
            # each artifact's `path` beside its coordinate, so the header read's classpath
            # is read straight off it. Entries with no coordinate (a flat `files()` jar, an
            # inter-project dependency) have nothing to name a fact's `origin` by and are
            # left out — the same rule `dependency_coordinates` above applies.
            dependency_archives=tuple(
                LibraryRoot(
                    coordinate=f"{entry['group']}:{entry['name']}",
                    version=str(entry["version"]),
                    archive=Path(str(entry["path"])),
                )
                for entry in sorted(
                    (
                        e
                        for e in project["classpath"]
                        if e.get("group") and e.get("name") and e.get("version") and e.get("path")
                    ),
                    key=lambda e: (str(e["group"]), str(e["name"]), str(e["version"])),
                )
                if Path(str(entry["path"])).is_file()
            ),
            # Gradle's own reason this project was not built (Android design M5). Read from
            # every record, not only from one `_assemble` made for a project with no file:
            # a record the init script writes may carry one too.
            build_failure=project.get("buildFailure"),
        )

    @staticmethod
    def _languages(project: dict[str, Any], source_roots: tuple[Path, ...]) -> frozenset[str]:
        """The source-directory sets Gradle says registered each source directory (OI-273
        round 2) — never a directory's name, which a plugin's `srcDirs("src")` makes `src`.

        Two kinds of directory count. An EXISTING source root counts as it stands. A
        directory Gradle reports that is not a root — generated, under the build directory —
        counts when it holds a file (fix round 2, review N1): a module whose only code is
        generated (OpenAPI generator, jOOQ, protobuf) is written in the language of the set
        that compiles it, and without this it had classes and no language and stopped the
        reactor. Holding a file, because the JDK's compiling plugin creates its
        annotation-processor output directory on every compile, empty when no processor ran
        — a compiler's scratch space, which must not name a language the module lacks."""
        roots = {str(root) for root in source_roots}
        found: set[str] = set()
        for directory, languages in project["sourceLanguages"].items():
            if directory in roots or (
                Path(directory).is_dir()
                and any(entry.is_file() for entry in Path(directory).rglob("*"))
            ):
                found.update(languages)
        return frozenset(found)

    @staticmethod
    def _identity(project: dict[str, Any], reactor: Sequence[dict[str, Any]]) -> "_Identity":
        """The identity Gradle itself gives the project (OI-273, ruled 2026-11-03 from
        Gradle 9.8.2's measured behaviour). A group with no version publishes as
        `<group>/<name>/unspecified`, so `unspecified` IS the version and is kept. No
        group publishes as nothing at all — `publishToMavenLocal` refuses with "groupId
        cannot be empty" — so the project has no coordinates, its symbols carry `. . .`
        (D00 §1), and its only identity is its place in its build: the root project's
        name, then the project path with every segment kept (`Acme:libs:core`); the
        root project itself is its name alone. Both come from Gradle's own records, the
        root's being the reactor entry at path `:`. One rule for a module and for a
        sibling read as its library root, so the two spell one project the same way."""
        name = project["name"]
        group = project["group"]
        if group:
            return _Identity(f"{group}:{name}", f"{group}/{name}", project["version"], True)
        path_in_build = project["path"]
        if path_in_build == ":":
            module_id = name
        else:
            root = {p["path"]: p for p in reactor}[":"]
            module_id = f"{root['name']}{path_in_build}"
        return _Identity(module_id, NOT_APPLICABLE, NOT_APPLICABLE, False)

    @staticmethod
    def _sibling_roots(
        project: dict[str, Any], reactor: Sequence[dict[str, Any]]
    ) -> tuple[LibraryRoot, ...]:
        """The compiled output of every reactor sibling on this project's compile
        classpath (W55), as library roots.

        **The design question this had to settle first, and its answer.** Gradle
        reports an inter-project dependency as a `ProjectComponentIdentifier`,
        which carries a project PATH — `:pricing-lib` — and no group, name or
        version at all. So the path is used to JOIN to that project's own record,
        and the identity is the one `_identity` forms from it, the same one the
        sibling has when it is analysed as a module — which is what
        `drop_borrowed_endpoints.sql` matches `documents.origin` against.

        For a grouped sibling that is its `group:artifact`, the spelling Maven's
        siblings carry. For a sibling with NO group (OI-273, ruled 2026-11-03) it is
        the root project's name plus the project path, because that is the only
        identity such a project has: Gradle will not publish it. The path does become
        part of the identity then, and D00 §2's portability holds anyway — the root
        name and the path are the build's own declarations, the same on every
        machine that checks the build out, never a filesystem location.

        **No transitive walk, because Gradle already did it.** `compileClasspath`
        is a RESOLVED configuration: an inter-project dependency's own api
        dependencies are on it as their own entries. `MavenDetector` walks the
        reactor itself because a POM's `<dependencies>` list is declarations, not
        a resolution — a difference in the two build systems, not in the rule.

        A project the reactor does not name, or one with no compiled output, is
        skipped rather than guessed at: `LibraryRoot` points at bytecode, and a
        root naming a directory that does not exist would be a scan target the
        scanner has to refuse later.
        """
        by_path = {str(entry["path"]): entry for entry in reactor}
        found: dict[tuple[str, str], LibraryRoot] = {}
        for entry in project["classpath"]:
            if not entry.get("internal"):
                continue
            sibling = by_path.get(str(entry.get("projectPath") or ""))
            if sibling is None:
                continue
            # A sibling with no group is read too (OI-273 round 2): it is on the
            # classpath like any other. It has no coordinates, so it is named by its module
            # id and marked unpublished — `.` for package and version — the identity its
            # symbols carry when it is analysed as a module itself.
            identity = GradleDetector._identity(sibling, reactor)
            coordinate = identity.module_id
            # ONE ROOT PER CLASSES DIRECTORY, because `LibraryRoot.archive` is one
            # path and Gradle's `classesDirs` is a SET: it carries one entry per
            # compiled source set, so a project built from more than one of them
            # has more than one, and taking only the first would silently drop
            # everything the others hold. Maven's sibling walk passes a single
            # directory because a POM has one `target/classes` — a difference
            # between the build systems, not between the rules. All of them share
            # a coordinate, which is what `origin` records and what
            # `sibling_coordinates` names.
            for directory in (Path(each) for each in sibling.get("classesDirs") or ()):
                if not directory.is_dir():
                    continue
                found.setdefault(
                    (coordinate, str(directory)),
                    LibraryRoot(
                        coordinate=coordinate,
                        version=str(identity.version or "unversioned"),
                        archive=directory,
                        package=None if identity.published else NOT_APPLICABLE,
                    ),
                )
        return tuple(found[key] for key in sorted(found))

    @staticmethod
    def _dependency_versions(classpath: list[dict[str, Any]]) -> dict[str, str]:
        """`groupId:artifactId` to resolved version, in sorted key order so the
        mapping serializes the same way twice (NFR-1).

        Two entries for one coordinate cannot disagree — Gradle already
        resolved the conflict before it reported — so the first wins and no
        tiebreak is invented for a case the report cannot produce."""
        versions: dict[str, str] = {}
        for entry in sorted(
            classpath, key=lambda item: (str(item.get("group")), str(item.get("name")))
        ):
            if not (entry.get("group") and entry.get("name") and entry.get("version")):
                continue
            versions.setdefault(f"{entry['group']}:{entry['name']}", str(entry["version"]))
        return versions

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
