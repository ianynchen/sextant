"""Which files pytest takes as test code, and where it reads its settings from (plan 2, final
review M1: test code is not scanned).

Run it with an interpreter that has pytest installed, never inside the repository's `.venv`:

    <corpus>/.venv/bin/python scripts/probes/pytest_collection.py

It writes small projects into a fresh temporary folder, runs pytest's own collection on each
(`pytest.main(["--collect-only"])` from the project's folder, as `pytest` with no arguments
runs), and prints one JSON document headed by the version the process itself reports: for each
project, the settings file pytest chose, its `testpaths` and `python_files`, the files it
collected tests from, and the `conftest.py` files it loaded. What the results mean is in
`pytest_collection.md`. The probe runs pytest on purpose. Sextant itself never does that.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# A test function, so a collected file gives an item.
_TEST = "def test_one():\n    pass\n"
# Every project holds these files; each case adds its settings and runs from `run_from`.
_FILES = {
    "app/main.py": _TEST,
    "app/test_inline.py": _TEST,
    "app/inline_test.py": _TEST,
    "app/check_names.py": _TEST,
    "app/sub/conftest.py": "",
    "tests/helpers.py": _TEST,
    "tests/test_api.py": _TEST,
    "tests/conftest.py": "",
    "test/test_old.py": _TEST,
    "spec/test_spec.py": _TEST,
    "spec/deep/check_deep.py": _TEST,
}

# (name, extra files, folder pytest runs from)
_CASES: list[tuple[str, dict[str, str], str]] = [
    ("no settings", {}, "."),
    (
        "pyproject ini_options: testpaths, python_files",
        {
            "pyproject.toml": '[project]\nname = "p"\n\n[tool.pytest.ini_options]\n'
            'testpaths = ["spec"]\npython_files = "check_*.py"\n'
        },
        ".",
    ),
    (
        "pyproject [tool.pytest] (TOML mode)",
        {"pyproject.toml": '[project]\nname = "p"\n\n[tool.pytest]\ntestpaths = ["tests"]\n'},
        ".",
    ),
    (
        "pyproject without a pytest table, pytest.ini above",
        {
            "pyproject.toml": '[project]\nname = "p"\n',
            "../pytest.ini": "[pytest]\ntestpaths = spec\n",
        },
        ".",
    ),
    (
        "pytest.ini beside pyproject (pytest.ini first)",
        {
            "pytest.ini": "[pytest]\ntestpaths = spec\n",
            "pyproject.toml": '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n',
        },
        ".",
    ),
    (
        "pytest.ini with no [pytest] section",
        {"pytest.ini": "[other]\nx = 1\n", "setup.cfg": "[tool:pytest]\ntestpaths = spec\n"},
        ".",
    ),
    ("tox.ini [pytest]", {"tox.ini": "[tox]\n\n[pytest]\ntestpaths = tests spec\n"}, "."),
    ("setup.cfg [tool:pytest]", {"setup.cfg": "[tool:pytest]\npython_files = *_test.py\n"}, "."),
    (
        "testpaths glob",
        {"pytest.ini": "[pytest]\ntestpaths = sp*\n"},
        ".",
    ),
    (
        "python_files with a path separator",
        {"pytest.ini": "[pytest]\npython_files = spec/*/check_*.py test_*.py\n"},
        ".",
    ),
    (
        "run from a folder below the settings file",
        {"pytest.ini": "[pytest]\ntestpaths = spec\n"},
        "app",
    ),
]


class _Recorder:
    """A pytest plugin that keeps what the run's own config and session report."""

    def __init__(self) -> None:
        self.found: dict[str, object] = {}

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        config = session.config
        root = config.rootpath
        self.found = {
            "configfile": config.inipath.relative_to(root.parent).as_posix()
            if config.inipath
            else None,
            "rootdir": root.name,
            "testpaths": list(config.getini("testpaths")),
            "python_files": list(config.getini("python_files")),
            "collected": sorted(
                {Path(item.path).relative_to(root).as_posix() for item in session.items}
            ),
            "conftests": sorted(
                Path(plugin.__file__).relative_to(root).as_posix()
                for plugin in config.pluginmanager.get_plugins()
                if getattr(plugin, "__file__", "").endswith("conftest.py")
                and Path(plugin.__file__).is_relative_to(root)
            ),
        }


def _run(base: Path, extra: dict[str, str], run_from: str) -> dict[str, object]:
    project = base / "project"
    for relative, text in {**_FILES, **extra}.items():
        path = (project / relative).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    recorder = _Recorder()
    here = os.getcwd()
    os.chdir(project / run_from)
    try:
        pytest.main(["--collect-only", "-q", "-p", "no:cacheprovider"], plugins=[recorder])
    finally:
        os.chdir(here)
    return recorder.found


def main() -> None:
    """Each case runs in a process of its own: pytest imports the test files it collects,
    and one process would find a second project's `test_api` already imported."""
    results: dict[str, object] = {"pytest": pytest.__version__, "python": sys.version.split()[0]}
    cases: dict[str, object] = {}
    with tempfile.TemporaryDirectory() as folder:
        for index, (name, _, _) in enumerate(_CASES):
            base = Path(folder) / f"case{index}"
            base.mkdir()
            output = subprocess.run(
                [sys.executable, "-I", __file__, str(index), str(base)],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            cases[name] = json.loads(output.rsplit("\n@@\n", 1)[1])
    results["cases"] = cases
    print(json.dumps(results, indent=1))


def _one(index: int, base: Path) -> None:
    _, extra, run_from = _CASES[index]
    found = _run(base, extra, run_from)
    print("\n@@\n" + json.dumps(found))


if __name__ == "__main__":
    if len(sys.argv) == 3:
        _one(int(sys.argv[1]), Path(sys.argv[2]))
    else:
        main()
