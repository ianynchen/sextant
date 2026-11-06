"""`PythonDetector` (Python design §3e): sibling of `MavenDetector` and `GradleDetector`
for Python build files. It finds the modules a repository holds, their identity, their
import roots and the environment their libraries are installed in.

**What it reads.** Build files only (M02): `pyproject.toml` and `Pipfile` with
`tomllib`, `setup.cfg` with `configparser`, `requirements*.txt` as lines, and the
`METADATA` file of each installed distribution. It never imports, runs or parses
scanned code. A `setup.py` is a program, so only its NAME is evidence. The one read of
a `.py` file is a plain text search for a `sys.path` change, in the files beside a
build file, and the result is a note.

**Where it looks.** Python build files can be at any depth, so the whole tree is
walked once. Dependency folders (`node_modules`), version control (`.git`), Sextant's
own results (`.sextant`) and every virtual environment (any folder that holds
`pyvenv.cfg`) are not entered.

**What is a module (§3e).**
- A `pyproject.toml` with `[project]`, `[tool.poetry]` or `[build-system]`, or a
  `setup.cfg` with `[metadata]`, marks a module wherever it is. A file that holds only
  tool settings (CTFd's `[nosetests]`) marks nothing.
- A uv workspace root (`[tool.uv.workspace]`) is a module only when it also marks one
  and has Python files of its own, outside its members.
- A `requirements*.txt` or a `Pipfile` marks a module only when its folder holds Python
  code of its own: code that is not inside a module below it. A list with no code of its
  own (a lint or test list at the root) marks nothing and is a note. A module above it
  does not matter: each service under a project is its own module.
- A `setup.py` marks a module only when no folder above it is already a module and it
  is not inside a package (no `__init__.py` beside it or above it).
- A folder of Python files that is in no module is a note, not a module.
- A build file that cannot be read (not TOML, not UTF-8, a template with `{{ }}` in it)
  is a note, and its folder is not a module. Only the build file of the folder that was
  asked for is a refusal.

**Identity (§3e).** `[project]`, then `[tool.poetry]`, then `setup.cfg [metadata]`, with
the name normalized by PEP 503. A dynamic version is the installed project's own
version, else `.`. A module with no name is unpublished: its coordinates and version
are `.`, and its id is its folder relative to the repository root (D00 §1).

**Environment (§3e).** `.venv`, `venv` or `env` beside the build file; for a uv workspace
member, the same names at the workspace root; for a Poetry project, the folder Poetry
itself names under `virtualenvs.path` from `poetry.toml`, or under Poetry's default cache.
A Poetry project with no environment, or with more than one, gets a note.
"""

import base64
import configparser
import hashlib
import os
import re
import sys
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NamedTuple

import pathspec

from sextant.application.ports.detector import (
    LibraryRoot,
    ModuleModel,
    NoModulesFound,
    RepositoryModel,
)
from sextant.domain.ignorefile import IgnoreRules
from sextant.domain.symbols import NOT_APPLICABLE

_PYPROJECT = "pyproject.toml"
_SETUP_CFG = "setup.cfg"
_SETUP_PY = "setup.py"
_PIPFILE = "Pipfile"
_PACKAGE_MARKER = "__init__.py"
_ENVIRONMENT_MARKER = "pyvenv.cfg"
_GITIGNORE = ".gitignore"

# The folder names `python -m venv`, uv and Poetry give an environment beside the
# build file, in the order they are tried. A folder is an environment only when it
# holds `pyvenv.cfg`; `.python-version` names an interpreter and is never one.
_ENVIRONMENT_NAMES = (".venv", "venv", "env")

# Folders the walk does not enter. Every folder that holds `pyvenv.cfg` is skipped
# too, whatever its name.
_SKIPPED_FOLDERS = frozenset(
    {".git", "node_modules", ".sextant", "__pycache__", ".venv", ".tox", ".nox"}
)

_REQUIREMENTS = re.compile(r"requirements.*\.txt")

# A requirement's distribution name (PEP 508): the name, then extras, a version, a
# marker, a URL (`name @ url`) or nothing. A line that starts with an option (`-r`,
# `-e`) or a bare URL (`git+https://...`) names no distribution here.
_REQUIREMENT_NAME = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?=$|[\[<>=!~;@ ,(])")

_SYS_PATH_CHANGE = re.compile(r"\bsys\.path\.(?:insert|append)\(")

_POETRY_SETTINGS = "poetry.toml"

_LOOSE_FOLDER_NOTE = "python files in a folder with no project file, not analysed: "
_LIST_ONLY_NOTE = "requirements with no python code of its own, not a module: "
_UNREADABLE_NOTE = "build file not read, so its folder is not a module: "


class _Identity(NamedTuple):
    """A module's normalized name and version, as its build file states them. `name`
    is None for an unpublished module; `version` is None where it is dynamic."""

    name: str | None
    version: str | None


def normalize_name(name: str) -> str:
    """PEP 503: lower case, and every run of `-`, `_` and `.` made one `-`."""
    return re.sub(r"[-_.]+", "-", name).lower()


def poetry_environment_name(name: str, folder: Path) -> str:
    """The name Poetry gives a project's environment in its central folder, without
    the `-py<major>.<minor>` that follows it: Poetry's own `EnvManager.generate_env_name`.
    `name` is the PEP 503 name (Poetry's `package.name`); `folder` holds `pyproject.toml`."""
    sanitized = re.sub(r'[ $`!*@"\\\r\n\t]', "_", name.lower())[:42]
    real_folder = os.path.normcase(os.path.realpath(folder))
    digest = hashlib.sha256(real_folder.encode("utf-8")).digest()
    return f"{sanitized}-{base64.urlsafe_b64encode(digest).decode()[:8]}"


def _is_build_file(name: str) -> bool:
    return (
        name in (_PYPROJECT, _SETUP_CFG, _SETUP_PY, _PIPFILE)
        or _REQUIREMENTS.fullmatch(name) is not None
    )


def is_skipped_folder(parent: str, name: str) -> bool:
    """Whether the folder `name` under `parent` holds no code of a module: a tool cache,
    version control, installed packages, or an environment (it holds `pyvenv.cfg`). The
    detector and the scanner share this rule."""
    return name in _SKIPPED_FOLDERS or os.path.isfile(
        os.path.join(parent, name, _ENVIRONMENT_MARKER)
    )


def _walk(root: Path) -> Iterator[tuple[Path, list[str]]]:
    """Every folder under `root` that the detector may read, with its file names, in
    sorted order. Skipped folders and environments are not entered, and neither is a
    path `.sextantignore` excludes (D04 §3) or a `.gitignore` file at or below `root`
    names: a git-ignored clone or worktree is not part of the project. `root` itself is
    always read."""
    ignore = IgnoreRules.load(root)
    git: list[tuple[Path, pathspec.GitIgnoreSpec]] = []
    for current, folders, files in os.walk(root):
        here = Path(current)
        if _GITIGNORE in files:
            lines = (here / _GITIGNORE).read_text(encoding="utf-8", errors="replace")
            git.append((here, pathspec.GitIgnoreSpec.from_lines(lines.splitlines())))
        folders[:] = sorted(
            folder
            for folder in folders
            if not is_skipped_folder(current, folder)
            and not _excluded(here / folder, root, ignore, git, folder=True)
        )
        yield here, sorted(name for name in files if not _excluded(here / name, root, ignore, git))


def _excluded(
    path: Path,
    root: Path,
    ignore: IgnoreRules,
    git: list[tuple[Path, "pathspec.GitIgnoreSpec"]],
    *,
    folder: bool = False,
) -> bool:
    suffix = "/" if folder else ""
    if ignore.matches(path.relative_to(root)):
        return True
    return any(
        spec.match_file(path.relative_to(base).as_posix() + suffix)
        for base, spec in git
        if path.is_relative_to(base)
    )


class _UnreadableBuildFile(ValueError):
    """A build file that is not valid TOML or `setup.cfg`, or not UTF-8."""

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"{path} is not a readable build file: {reason}")
        self.path = path
        self.reason = reason


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as malformed:
        raise _UnreadableBuildFile(path, str(malformed)) from malformed


def _read_cfg(path: Path) -> configparser.RawConfigParser:
    """`setup.cfg` with no interpolation: a `%` in a value is text, as setuptools
    reads it."""
    parser = configparser.RawConfigParser(strict=False)
    try:
        parser.read(path, encoding="utf-8")
    except (configparser.Error, UnicodeDecodeError) as malformed:
        raise _UnreadableBuildFile(path, str(malformed)) from malformed
    return parser


def _requirement_name(line: str) -> str | None:
    """The normalized distribution name a requirement line declares, or None. A comment
    line or an option line does not start with a letter or digit, so it names nothing."""
    found = _REQUIREMENT_NAME.match(line.strip())
    return normalize_name(found.group(1)) if found else None


def _cfg_lines(value: str) -> list[str]:
    return [line for line in value.splitlines() if line.strip()]


def _table(data: dict[str, Any], *keys: str) -> dict[str, Any]:
    """The nested table at `keys`, or an empty table where any part is absent."""
    for key in keys:
        value = data.get(key)
        if not isinstance(value, dict):
            return {}
        data = value
    return data


class _BuildFiles:
    """The build files of one folder, each read once."""

    def __init__(self, folder: Path, files: list[str]) -> None:
        self.folder = folder
        self.files = files
        self.pyproject = _read_toml(folder / _PYPROJECT) if _PYPROJECT in files else {}
        self.setup_cfg = _read_cfg(folder / _SETUP_CFG) if _SETUP_CFG in files else None
        self.pipfile = _read_toml(folder / _PIPFILE) if _PIPFILE in files else {}
        self.poetry_settings = (
            _read_toml(folder / _POETRY_SETTINGS) if _POETRY_SETTINGS in files else {}
        )

    @property
    def project(self) -> dict[str, Any]:
        return _table(self.pyproject, "project")

    @property
    def poetry(self) -> dict[str, Any]:
        return _table(self.pyproject, "tool", "poetry")

    @property
    def workspace_patterns(self) -> tuple[list[str], list[str]] | None:
        """The `members` and `exclude` patterns of a uv workspace root, or None for any
        other folder."""
        if "workspace" not in _table(self.pyproject, "tool", "uv"):
            return None
        workspace = _table(self.pyproject, "tool", "uv", "workspace")
        return (
            [str(member) for member in workspace.get("members", [])],
            [str(excluded) for excluded in workspace.get("exclude", [])],
        )

    @property
    def uses_poetry(self) -> bool:
        """`[tool.poetry]`, a `poetry.toml`, or Poetry's build backend."""
        backend = str(_table(self.pyproject, "build-system").get("build-backend", ""))
        return bool(self.poetry) or bool(self.poetry_settings) or backend.startswith("poetry")

    def kind(self) -> str | None:
        """The build file that marks this folder as a module, strongest first, or None
        where none does. `setup_py` and `requirements` are the weak kinds (§3e)."""
        if self.project or self.poetry or "build-system" in self.pyproject:
            return "pyproject"
        if self.setup_cfg is not None and self.setup_cfg.has_section("metadata"):
            return "setup_cfg"
        if _SETUP_PY in self.files:
            return "setup_py"
        if _PIPFILE in self.files or any(_REQUIREMENTS.fullmatch(f) for f in self.files):
            return "requirements"
        return None

    def identity(self) -> _Identity:
        """`[project]`, then `[tool.poetry]`, then `setup.cfg [metadata]` (§3e)."""
        for table in (self.project, self.poetry):
            if "name" in table:
                dynamic = "version" in table.get("dynamic", [])
                version = None if dynamic else table.get("version")
                return _Identity(normalize_name(str(table["name"])), _version_or_none(version))
        if self.setup_cfg is not None and self.setup_cfg.has_option("metadata", "name"):
            version = self.setup_cfg.get("metadata", "version", fallback=None)
            # `attr:` and `file:` read the version from code or a file at build time.
            if version is not None and version.strip().startswith(("attr:", "file:")):
                version = None
            return _Identity(
                normalize_name(self.setup_cfg.get("metadata", "name")), _version_or_none(version)
            )
        return _Identity(None, None)

    def dependencies(self) -> tuple[str, ...]:
        """Every distribution name this folder's build files declare, normalized and
        sorted: `[project] dependencies`, Poetry's dependency table (less `python`),
        `setup.cfg install_requires`, each `requirements*.txt`, and `Pipfile [packages]`."""
        names: set[str | None] = set()
        names.update(_requirement_name(str(line)) for line in self.project.get("dependencies", []))
        names.update(
            normalize_name(key)
            for key in _table(self.poetry, "dependencies")
            if key.lower() != "python"
        )
        if self.setup_cfg is not None:
            install_requires = self.setup_cfg.get("options", "install_requires", fallback="")
            names.update(_requirement_name(line) for line in _cfg_lines(install_requires))
        for name in self.files:
            if _REQUIREMENTS.fullmatch(name):
                text = (self.folder / name).read_text(encoding="utf-8", errors="replace")
                names.update(_requirement_name(line) for line in text.splitlines())
        names.update(normalize_name(key) for key in _table(self.pipfile, "packages"))
        return tuple(sorted(name for name in names if name))

    def import_roots(self, has_python: set[Path]) -> tuple[Path, ...]:
        """The folders a name like `app.api` is found from (§3e): the package settings
        of setuptools, hatch or Poetry, else a `src/` layout, else the module folder.
        `has_python` is every folder that holds a `.py` file."""
        folder = self.folder
        named: list[str] = []
        setuptools = _table(self.pyproject, "tool", "setuptools")
        package_dir = setuptools.get("package-dir", {})
        if isinstance(package_dir, dict) and "" in package_dir:
            named.append(str(package_dir[""]))
        named.extend(
            str(where) for where in _table(setuptools, "packages", "find").get("where", [])
        )
        wheel = _table(self.pyproject, "tool", "hatch", "build", "targets", "wheel")
        named.extend(str(Path(str(package)).parent) for package in wheel.get("packages", []))
        for package in self.poetry.get("packages", []):
            if isinstance(package, dict):
                named.append(str(package.get("from", ".")))
        if self.setup_cfg is not None:
            for line in _cfg_lines(self.setup_cfg.get("options", "package_dir", fallback="")):
                key, _, value = line.partition("=")
                if not key.strip() and value.strip():
                    named.append(value.strip())
            where = self.setup_cfg.get("options.packages.find", "where", fallback="")
            named.extend(line.strip() for line in _cfg_lines(where))
        roots = sorted({Path(os.path.normpath(folder / name)) for name in named})
        existing = tuple(root for root in roots if root.is_dir())
        if existing:
            return existing
        src = folder / "src"
        if any(src == path or src in path.parents for path in has_python):
            return (src,)
        return (folder,)


def _version_or_none(version: object) -> str | None:
    return None if version is None else str(version).strip() or None


class _Environment(NamedTuple):
    folder: Path
    site_packages: Path | None
    # Normalized distribution name -> installed version.
    installed: dict[str, str]


def _read_environment(folder: Path) -> _Environment:
    """The distributions installed in one environment, from each `*.dist-info/METADATA`
    under `lib/python*/site-packages`. Only the `Name` and `Version` headers are read."""
    candidates = sorted((folder / "lib").glob("python*/site-packages"))
    site_packages = candidates[0] if candidates else None
    installed: dict[str, str] = {}
    if site_packages is not None:
        for metadata in sorted(site_packages.glob("*.dist-info/METADATA")):
            headers: dict[str, str] = {}
            for line in metadata.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.strip():
                    break
                key, _, value = line.partition(":")
                if key in ("Name", "Version") and key not in headers:
                    headers[key] = value.strip()
            if "Name" in headers and "Version" in headers:
                installed.setdefault(normalize_name(headers["Name"]), headers["Version"])
    return _Environment(folder, site_packages, installed)


def _environment_in(folder: Path) -> Path | None:
    for name in _ENVIRONMENT_NAMES:
        if (folder / name / _ENVIRONMENT_MARKER).is_file():
            return folder / name
    return None


def _poetry_cache() -> Path:
    """Poetry's default cache folder: `platformdirs.user_cache_path("pypoetry",
    appauthor=False)`, as Poetry's `locations.py` sets it, for this platform."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "pypoetry"
    if sys.platform == "win32":
        return Path.home() / "AppData" / "Local" / "pypoetry" / "Cache"
    return Path.home() / ".cache" / "pypoetry"


def _poetry_environments(files: _BuildFiles, name: str) -> tuple[Path, list[Path]]:
    """The folder Poetry keeps this project's environments in (`virtualenvs.path` from
    `poetry.toml`, else `<cache>/virtualenvs`), and each environment there that Poetry
    named for this project: its exact name, then `-py<major>.<minor>`."""
    configured = _table(files.poetry_settings, "virtualenvs").get("path")
    cache = _poetry_cache()
    if configured is None:
        location = cache / "virtualenvs"
    else:
        expanded = Path(str(configured).replace("{cache-dir}", str(cache))).expanduser()
        location = Path(os.path.normpath(files.folder / expanded))
    prefix = f"{poetry_environment_name(name, files.folder)}-py"
    found = (
        sorted(
            entry
            for entry in location.iterdir()
            if entry.name.startswith(prefix) and (entry / _ENVIRONMENT_MARKER).is_file()
        )
        if location.is_dir()
        else []
    )
    return location, found


def _sys_path_notes(root: Path, folder: Path, files: list[str]) -> list[str]:
    """Each `sys.path.insert`/`append` in the `.py` files beside a build file, as text.
    The change is not followed (§3e); the note says where it is."""
    notes = []
    for name in files:
        if not name.endswith(".py"):
            continue
        text = (folder / name).read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            if _SYS_PATH_CHANGE.search(line):
                relative = Path(os.path.relpath(folder / name, root)).as_posix()
                notes.append(f"{relative}:{number}: sys.path change, not followed: {line.strip()}")
    return notes


class PythonDetector:
    """Reads Python build files (Python design §3e). `accepts()` reads only file names,
    at any depth; `detect()` reads build files and installed `METADATA`, nothing else.
    `allow_resolve` does nothing: nothing is ever downloaded."""

    def accepts(self, path: Path) -> bool:
        return any(any(_is_build_file(name) for name in files) for _, files in _walk(path))

    def detect(self, path: Path, allow_resolve: bool = False) -> RepositoryModel:
        listing = dict(_walk(path))
        has_python = {
            folder for folder, files in listing.items() if any(f.endswith(".py") for f in files)
        }
        notes: list[str] = []
        build_files: dict[Path, _BuildFiles] = {}
        for folder, files in listing.items():
            if not any(_is_build_file(name) for name in files):
                continue
            try:
                build_files[folder] = _BuildFiles(folder, files)
            except _UnreadableBuildFile as unreadable:
                # The folder asked for must be read; a nested one is a note (a tool's
                # test data, a project template with `{{ }}` in it).
                if folder == path:
                    raise
                relative = Path(os.path.relpath(unreadable.path, path)).as_posix()
                notes.append(f"{_UNREADABLE_NOTE}{relative} ({unreadable.reason})")
        kinds = {folder: kind for folder, files in build_files.items() if (kind := files.kind())}
        workspaces = self._workspaces(build_files)

        # The strong kinds first, wherever they are; a workspace root keeps its place
        # only with Python files of its own.
        modules = {folder for folder, kind in kinds.items() if kind in ("pyproject", "setup_cfg")}
        for root in workspaces:
            if root in modules and not self._owns_code(root, modules, has_python):
                modules.discard(root)
        # Then each requirements list with code of its own. A list owns nothing that a
        # list below it owns, so all are added before any is tested.
        lists = {folder for folder, kind in kinds.items() if kind == "requirements"}
        modules |= lists
        for folder in sorted(lists):
            if not self._owns_code(folder, modules, has_python):
                modules.discard(folder)
                names = ", ".join(
                    Path(os.path.relpath(folder / name, path)).as_posix()
                    for name in listing[folder]
                    if name == _PIPFILE or _REQUIREMENTS.fullmatch(name)
                )
                notes.append(f"{_LIST_ONLY_NOTE}{names}")
        # Last, each `setup.py`, top down, only where no folder above it is a module.
        for folder in sorted(kinds, key=lambda f: (len(f.parts), f)):
            if kinds[folder] != "setup_py" or self._nearest(folder, modules):
                continue
            if self._inside_a_package(path, folder, listing):
                continue
            modules.add(folder)
        if not modules:
            raise NoModulesFound(
                f"no Python module found in {path}: no project file marks one", notes
            )

        models = []
        for folder in sorted(modules):
            model, module_notes = self._module_of(
                path, build_files[folder], kinds[folder], modules, has_python, workspaces
            )
            models.append(model)
            notes.extend(module_notes)
        notes.extend(self._loose_folder_notes(path, modules, has_python))
        for folder in sorted(modules):
            notes.extend(_sys_path_notes(path, folder, listing[folder]))
        return RepositoryModel(
            root=path,
            modules=tuple(models),
            notes=tuple(sorted(notes)),
            multi_module=len(models) > 1,
        )

    @staticmethod
    def _owns_code(folder: Path, modules: set[Path], has_python: set[Path]) -> bool:
        """Whether a folder of Python files belongs to `folder` and not to a module
        below it."""
        return any(PythonDetector._nearest(f, modules) == folder for f in has_python)

    @staticmethod
    def _nearest(folder: Path, modules: set[Path]) -> Path | None:
        """The module `folder` belongs to: itself or the closest folder above it."""
        for candidate in (folder, *folder.parents):
            if candidate in modules:
                return candidate
        return None

    @staticmethod
    def _inside_a_package(root: Path, folder: Path, listing: dict[Path, list[str]]) -> bool:
        """Whether `folder`, or a folder above it inside the repository, holds
        `__init__.py` — the measured shape of a `setup.py` that is code, not a build
        file (CTFd's `CTFd/forms/setup.py`)."""
        for candidate in (folder, *folder.parents):
            if _PACKAGE_MARKER in listing.get(candidate, ()):
                return True
            if candidate == root:
                return False
        return False

    @staticmethod
    def _workspaces(build_files: dict[Path, _BuildFiles]) -> dict[Path, set[Path]]:
        """Every uv workspace root, with the member folders its `members` patterns name
        and its `exclude` patterns do not."""
        workspaces: dict[Path, set[Path]] = {}
        for folder, files in build_files.items():
            patterns = files.workspace_patterns
            if patterns is None:
                continue
            members, excluded = patterns
            named = {path for pattern in members for path in folder.glob(pattern)}
            named -= {path for pattern in excluded for path in folder.glob(pattern)}
            workspaces[folder] = {path for path in named if path.is_dir()}
        return workspaces

    @staticmethod
    def _module_of(
        root: Path,
        files: _BuildFiles,
        kind: str,
        modules: set[Path],
        has_python: set[Path],
        workspaces: dict[Path, set[Path]],
    ) -> tuple[ModuleModel, list[str]]:
        """The module whose build files are `files`, and the notes about it."""
        folder = files.folder
        identity = files.identity()
        module_id = (
            identity.name
            if identity.name is not None
            else Path(os.path.relpath(folder, root)).as_posix()
            if folder != root
            else folder.name
        )
        environment_folder, notes = PythonDetector._environment_of(
            files, identity.name, module_id, workspaces
        )
        environment = (
            _read_environment(environment_folder) if environment_folder is not None else None
        )
        installed = environment.installed if environment is not None else {}

        if identity.name is None:
            coordinates = version = NOT_APPLICABLE
        else:
            module_id = coordinates = identity.name
            version = identity.version or installed.get(identity.name, NOT_APPLICABLE)

        # Observed over the module's whole tree, less the modules below it.
        own_python = PythonDetector._owns_code(folder, modules, has_python)
        dependencies = files.dependencies()
        versions = {name: installed[name] for name in dependencies if name in installed}
        if environment is not None:
            # A declared library missing from the environment has no symbols (§3e).
            notes.extend(
                f"{name} is not installed in the scanned environment"
                for name in dependencies
                if name not in installed
            )
        archives = (
            tuple(
                LibraryRoot(coordinate=name, version=installed_version, archive=site_packages)
                for name, installed_version in versions.items()
            )
            if environment is not None and (site_packages := environment.site_packages)
            else ()
        )
        import_roots = files.import_roots(has_python)
        model = ModuleModel(
            module_id=module_id,
            coordinates=coordinates,
            version=version,
            root=folder,
            kind=kind,
            languages=frozenset({"python"}) if own_python else frozenset(),
            source_roots=import_roots,
            # Python runs from source: the import roots are what the scanner reads.
            output_dirs=import_roots,
            packaging="wheel",
            dependency_coordinates=dependencies,
            dependency_versions=versions,
            dependency_archives=archives,
            environment=environment_folder,
            # Python finds a method by its method resolution order (spec §3b).
            lookup="c3",
        )
        return model, notes

    @staticmethod
    def _environment_of(
        files: _BuildFiles,
        name: str | None,
        module_id: str,
        workspaces: dict[Path, set[Path]],
    ) -> tuple[Path | None, list[str]]:
        """The environment a module's libraries are installed in (§3e), and the notes
        about it: `.venv`, `venv` or `env` beside the build file (Poetry's `in-project`
        folder is `.venv`); for a uv workspace member, the same names at the workspace
        root; for a Poetry project, the one environment Poetry named for it. Two or more
        are a closed list this detector cannot narrow, so none is read."""
        folder = files.folder
        found = _environment_in(folder)
        if found is not None:
            return found, []
        # A uv workspace has one environment, at its root, for every member.
        for workspace, members in sorted(workspaces.items()):
            if folder in members:
                return _environment_in(workspace), []
        if not files.uses_poetry:
            return None, []
        if name is None:
            return None, [f"{module_id}: no Poetry environment found: the project has no name"]
        location, environments = _poetry_environments(files, name)
        if len(environments) == 1:
            return environments[0], []
        if environments:
            listed = ", ".join(str(environment) for environment in environments)
            return None, [f"{module_id}: more than one Poetry environment, none read: {listed}"]
        return None, [
            f"{module_id}: no Poetry environment found (looked for .venv and in {location})"
        ]

    @staticmethod
    def _loose_folder_notes(root: Path, modules: set[Path], has_python: set[Path]) -> list[str]:
        """The top folders of Python files that are in no module (§3e, ruled): listed,
        not analysed."""
        loose = {f for f in has_python if PythonDetector._nearest(f, modules) is None}
        top = [f for f in loose if not any(parent in loose for parent in f.parents)]
        return [
            f"{_LOOSE_FOLDER_NOTE}{Path(os.path.relpath(f, root)).as_posix()}" for f in sorted(top)
        ]
