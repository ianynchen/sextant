"""Which of a module's files are test code, by pytest's own collection rules (plan 2, final
review M1; the user's ruling of 2026-11-09: "We only care about code that eventually goes to
prod"). Python has no source sets, so the scanner does not read these files, as the JVM
scanner does not read `src/test` (it is not in the compiled output).

A file is test code when any of these holds (`scripts/probes/pytest_collection.md`, pytest
9.2.0):
- it is at or below a path the settings' `testpaths` names. Each entry is a glob, read from
  the folder the settings file is in, as pytest reads it when it runs from there;
- its name matches a `python_files` pattern: the settings' list, else pytest's default
  `test_*.py` and `*_test.py`. A pattern with no `/` is matched against the file's name, and
  one with a `/` against its whole path, as pytest's `fnmatch_ex` matches;
- it is a `conftest.py`;
- it is in a folder named `tests` or `test` below the scanned root.

**The settings file** is the one pytest itself chooses: from the scanned root up to the
analysed root, the first folder with one of `pytest.toml`, `.pytest.toml`, `pytest.ini`,
`.pytest.ini`, `pyproject.toml`, `tox.ini` and `setup.cfg`, in that order, that holds
pytest's settings. A `pytest.toml` or `pytest.ini` holds them even with no pytest table or
section; a `pyproject.toml` only with `[tool.pytest]` or `[tool.pytest.ini_options]`, a
`tox.ini` only with `[pytest]`, a `setup.cfg` only with `[tool:pytest]`. pytest goes on up to
the file system's root; Sextant stops at the analysed root, which is also where
`.sextantignore` is read. A settings file that cannot be read is passed over: pytest itself
would not run with it.
"""

import configparser
import fnmatch
import glob
import os
import shlex
import tomllib
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_FILES = ("test_*.py", "*_test.py")
_CONFTEST = "conftest.py"
_TEST_FOLDERS = frozenset({"tests", "test"})
# The settings files pytest looks for in each folder, in its order of precedence.
_TOML_FILES = ("pytest.toml", ".pytest.toml")
_INI_FILES = ("pytest.ini", ".pytest.ini")
_PYPROJECT = "pyproject.toml"
_TOX = "tox.ini"
_SETUP_CFG = "setup.cfg"
_ORDER = (*_TOML_FILES, *_INI_FILES, _PYPROJECT, _TOX, _SETUP_CFG)


@dataclass(frozen=True)
class PytestCollection:
    """The test code of one scanned root: `root` is that folder, `testpaths` the paths the
    settings name (each found path, absolute), `patterns` the `python_files` patterns."""

    root: Path
    testpaths: tuple[Path, ...] = ()
    patterns: tuple[str, ...] = _DEFAULT_FILES

    @classmethod
    def of(cls, root: Path, top: Path) -> "PytestCollection":
        """The rules for the files under `root`, from the settings file pytest would choose
        between `root` and `top`."""
        for folder in _upward(root, top):
            for name in _ORDER:
                path = folder / name
                if not path.is_file():
                    continue
                settings = _settings(path)
                if settings is None:
                    continue
                return cls(
                    root,
                    tuple(
                        folder / found
                        for entry in _args(settings.get("testpaths"))
                        for found in sorted(glob.glob(entry, root_dir=folder, recursive=True))
                    ),
                    tuple(_args(settings.get("python_files"))) or _DEFAULT_FILES,
                )
        return cls(root)

    def holds_folder(self, folder: Path) -> bool:
        """Whether every file at or below `folder`, a folder below `root`, is test code."""
        return folder.name in _TEST_FOLDERS or any(
            folder.is_relative_to(path) for path in self.testpaths
        )

    def holds(self, path: Path) -> bool:
        """Whether the file at `path`, below `root`, is test code."""
        folders = path.parent.relative_to(self.root).parts
        return (
            path.name == _CONFTEST
            or any(folder in _TEST_FOLDERS for folder in folders)
            or any(path.is_relative_to(found) for found in self.testpaths)
            or any(_matches(pattern, path) for pattern in self.patterns)
        )


def _upward(root: Path, top: Path) -> list[Path]:
    """`root` and each folder above it up to `top`; `root` alone where it is not below
    `top`."""
    if not root.is_relative_to(top):
        return [root]
    folders = [root]
    while folders[-1] != top:
        folders.append(folders[-1].parent)
    return folders


def _settings(path: Path) -> dict[str, object] | None:
    """The pytest settings `path` holds, or None where pytest would pass the file over."""
    try:
        if path.name in _TOML_FILES:
            document = tomllib.loads(path.read_text(encoding="utf-8"))
            table = document.get("pytest", {})
            return table if isinstance(table, dict) else {}
        if path.name == _PYPROJECT:
            tool = tomllib.loads(path.read_text(encoding="utf-8")).get("tool", {})
            pytest = tool.get("pytest") if isinstance(tool, dict) else None
            if not isinstance(pytest, dict):
                return None
            table = pytest.get("ini_options")
            native = {key: value for key, value in pytest.items() if key != "ini_options"}
            return native or (table if isinstance(table, dict) else None)
        parser = configparser.RawConfigParser(strict=False)
        parser.read(path, encoding="utf-8")
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, configparser.Error):
        return None
    section = "tool:pytest" if path.name == _SETUP_CFG else "pytest"
    if parser.has_section(section):
        return dict(parser.items(section))
    return {} if path.name in _INI_FILES else None


def _args(value: object) -> list[str]:
    """A setting of pytest's `args` kind: a list as written, or a string split as a shell
    splits it."""
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            return shlex.split(value)
        except ValueError:
            return []
    return []


def _matches(pattern: str, path: Path) -> bool:
    """pytest's `fnmatch_ex`: a pattern with no path separator matches the file's name, and
    one with a separator matches the whole path, preceded by `*/` where it is relative."""
    if os.sep not in pattern:
        return fnmatch.fnmatch(path.name, pattern)
    if not os.path.isabs(pattern):
        pattern = f"*{os.sep}{pattern}"
    return fnmatch.fnmatch(str(path), pattern)
