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
- A `setup.py`, a `requirements*.txt` or a `Pipfile` marks a module only when no folder
  above it is already a module. A `setup.py` must also not be inside a package (no
  `__init__.py` beside it or above it), and a requirements file needs Python files at
  or below its folder.
- A folder of Python files that is in no module is a note, not a module.

**Identity (§3e).** `[project]`, then `[tool.poetry]`, then `setup.cfg [metadata]`, with
the name normalized by PEP 503. A dynamic version is the installed project's own
version, else `.`. A module with no name is unpublished: its coordinates and version
are `.`, and its id is its folder relative to the repository root (D00 §1).
"""

import configparser
import os
import re
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NamedTuple

from sextant.application.ports.detector import LibraryRoot, ModuleModel, RepositoryModel
from sextant.domain.symbols import NOT_APPLICABLE

_PYPROJECT = "pyproject.toml"
_SETUP_CFG = "setup.cfg"
_SETUP_PY = "setup.py"
_PIPFILE = "Pipfile"
_PACKAGE_MARKER = "__init__.py"
_ENVIRONMENT_MARKER = "pyvenv.cfg"

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

_LOOSE_FOLDER_NOTE = "python files in a folder with no project file, not analysed: "


class _Identity(NamedTuple):
    """A module's normalized name and version, as its build file states them. `name`
    is None for an unpublished module; `version` is None where it is dynamic."""

    name: str | None
    version: str | None


def normalize_name(name: str) -> str:
    """PEP 503: lower case, and every run of `-`, `_` and `.` made one `-`."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _is_build_file(name: str) -> bool:
    return (
        name in (_PYPROJECT, _SETUP_CFG, _SETUP_PY, _PIPFILE)
        or _REQUIREMENTS.fullmatch(name) is not None
    )


def _walk(root: Path) -> Iterator[tuple[Path, list[str]]]:
    """Every folder under `root` that the detector may read, with its file names, in
    sorted order. Skipped folders and environments are not entered."""
    for current, folders, files in os.walk(root):
        folders[:] = sorted(
            folder
            for folder in folders
            if folder not in _SKIPPED_FOLDERS
            and not os.path.isfile(os.path.join(current, folder, _ENVIRONMENT_MARKER))
        )
        yield Path(current), sorted(files)


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as malformed:
        raise ValueError(f"{path} is not valid TOML: {malformed}") from malformed


def _read_cfg(path: Path) -> configparser.RawConfigParser:
    """`setup.cfg` with no interpolation: a `%` in a value is text, as setuptools
    reads it."""
    parser = configparser.RawConfigParser(strict=False)
    try:
        parser.read(path, encoding="utf-8")
    except configparser.Error as malformed:
        raise ValueError(f"{path} is not a valid setup.cfg: {malformed}") from malformed
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

    @property
    def project(self) -> dict[str, Any]:
        return _table(self.pyproject, "project")

    @property
    def poetry(self) -> dict[str, Any]:
        return _table(self.pyproject, "tool", "poetry")

    @property
    def workspace_members(self) -> list[str] | None:
        """The member patterns of a uv workspace root, or None for any other folder."""
        if "workspace" not in _table(self.pyproject, "tool", "uv"):
            return None
        workspace = _table(self.pyproject, "tool", "uv", "workspace")
        return [str(member) for member in workspace.get("members", [])]

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
        if _PIPFILE in self.files:
            names.update(
                normalize_name(key)
                for key in _table(_read_toml(self.folder / _PIPFILE), "packages")
            )
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
        build_files = {
            folder: _BuildFiles(folder, files)
            for folder, files in listing.items()
            if any(_is_build_file(name) for name in files)
        }
        kinds = {folder: kind for folder, files in build_files.items() if (kind := files.kind())}
        workspaces = self._workspaces(build_files)

        # The strong kinds first, wherever they are; a workspace root keeps its place
        # only with Python files of its own. Then the weak kinds, top down, each only
        # where no folder above it is a module.
        modules = {folder for folder, kind in kinds.items() if kind in ("pyproject", "setup_cfg")}
        for root in workspaces:
            if root in modules and not any(
                self._nearest(folder, modules) == root for folder in has_python
            ):
                modules.discard(root)
        for folder in sorted(kinds, key=lambda f: (len(f.parts), f)):
            if kinds[folder] in ("pyproject", "setup_cfg") or self._nearest(folder, modules):
                continue
            if kinds[folder] == "setup_py" and self._inside_a_package(path, folder, listing):
                continue
            if kinds[folder] == "requirements" and not any(
                folder == f or folder in f.parents for f in has_python
            ):
                continue
            modules.add(folder)
        if not modules:
            raise ValueError(f"no Python module found in {path}: no project file marks one")

        models = [
            self._module_of(
                path, build_files[folder], kinds[folder], modules, has_python, workspaces
            )
            for folder in sorted(modules)
        ]
        notes = self._loose_folder_notes(path, modules, has_python)
        for folder in sorted(modules):
            notes.extend(_sys_path_notes(path, folder, listing[folder]))
        notes.extend(self._shared_name_notes(path, models))
        return RepositoryModel(
            root=path,
            modules=tuple(models),
            notes=tuple(sorted(notes)),
            multi_module=len(models) > 1,
        )

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
        """Every uv workspace root, with the member folders its patterns name."""
        workspaces: dict[Path, set[Path]] = {}
        for folder, files in build_files.items():
            members = files.workspace_members
            if members is None:
                continue
            workspaces[folder] = {
                member for pattern in members for member in folder.glob(pattern) if member.is_dir()
            }
        return workspaces

    @staticmethod
    def _module_of(
        root: Path,
        files: _BuildFiles,
        kind: str,
        modules: set[Path],
        has_python: set[Path],
        workspaces: dict[Path, set[Path]],
    ) -> ModuleModel:
        folder = files.folder
        environment_folder = _environment_in(folder)
        if environment_folder is None:
            # A uv workspace has one environment, at its root, for every member.
            for workspace, members in sorted(workspaces.items()):
                if folder in members:
                    environment_folder = _environment_in(workspace)
                    break
        environment = (
            _read_environment(environment_folder) if environment_folder is not None else None
        )
        installed = environment.installed if environment is not None else {}

        identity = files.identity()
        if identity.name is None:
            module_id = (
                Path(os.path.relpath(folder, root)).as_posix() if folder != root else folder.name
            )
            coordinates = version = NOT_APPLICABLE
        else:
            module_id = coordinates = identity.name
            version = identity.version or installed.get(identity.name, NOT_APPLICABLE)

        own_python = any(PythonDetector._nearest(f, modules) == folder for f in has_python)
        dependencies = files.dependencies()
        versions = {name: installed[name] for name in dependencies if name in installed}
        archives = (
            tuple(
                LibraryRoot(coordinate=name, version=installed_version, archive=site_packages)
                for name, installed_version in versions.items()
            )
            if environment is not None and (site_packages := environment.site_packages)
            else ()
        )
        return ModuleModel(
            module_id=module_id,
            coordinates=coordinates,
            version=version,
            root=folder,
            kind=kind,
            languages=frozenset({"python"}) if own_python else frozenset(),
            source_roots=files.import_roots(has_python),
            output_dirs=(),
            packaging="wheel",
            dependency_coordinates=dependencies,
            dependency_versions=versions,
            dependency_archives=archives,
            environment=environment_folder,
        )

    @staticmethod
    def _loose_folder_notes(root: Path, modules: set[Path], has_python: set[Path]) -> list[str]:
        """The top folders of Python files that are in no module (§3e, ruled): listed,
        not analysed."""
        loose = {f for f in has_python if PythonDetector._nearest(f, modules) is None}
        top = [f for f in loose if not any(parent in loose for parent in f.parents)]
        return [
            f"{_LOOSE_FOLDER_NOTE}{Path(os.path.relpath(f, root)).as_posix()}" for f in sorted(top)
        ]

    @staticmethod
    def _shared_name_notes(root: Path, models: list[ModuleModel]) -> list[str]:
        """Two folders that publish one name (a project and a template copy of it) give
        two modules with one id. Both are kept, and the note names the folders."""
        by_id: dict[str, list[str]] = {}
        for model in models:
            by_id.setdefault(model.module_id, []).append(
                Path(os.path.relpath(model.root, root)).as_posix()
            )
        return [
            f"more than one module has the name {module_id}: {', '.join(sorted(folders))}"
            for module_id, folders in sorted(by_id.items())
            if len(folders) > 1
        ]
