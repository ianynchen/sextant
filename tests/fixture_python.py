"""Create a Python fixture's own virtual environment from its committed `uv.lock`.

A Python fixture is to `uv` what a JVM fixture is to Maven: its dependencies are pinned in the
fixture, installed once, and the suite then runs offline. The environment is the fixture's own
(`<fixture>/.venv`, gitignored), never Sextant's: the oracle runs FastAPI there, in a
subprocess, so nothing of the fixture's is imported into Sextant's process.

CI primes the environment online (`python tests/fixture_python.py`, a step in `pr.yml`), so the
suite's own `synced(..., offline=True)` finds every package in the uv cache, so the suite never
reaches the network. `--frozen` refuses to re-resolve: a `pyproject.toml` edited without `uv lock`
fails here instead of installing something the lock never saw.

Every Python fixture with its own `pyproject.toml` must also be named in the repository's root
`.sextantignore`, or Sextant reading itself finds it as a second module.

Its own module rather than `conftest.py` for the reason `fixture_build.py` gives: several test
directories have their own `conftest.py`, so a bare `from conftest import ...` fails elsewhere.
"""

import subprocess
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

# The Python fixtures the suite runs code in. CI syncs these online first.
PRIMED_PYTHON_FIXTURES = ("orders-fastapi",)


def interpreter(root: Path) -> Path:
    """The fixture's own Python, which exists once `synced` has run."""
    return root / ".venv" / "bin" / "python"


def synced(root: Path, *, offline: bool) -> Path:
    """Install `root`'s locked dependencies into `root/.venv` and return the environment.

    Offline for the suite; online only for the priming step. Raises `CalledProcessError` when
    `uv` fails, which offline means a package missing from the cache.
    """
    command = ["uv", "sync", "--frozen", "--project", str(root)]
    if offline:
        command.append("--offline")
    subprocess.run(command, check=True, cwd=root)
    return root / ".venv"


if __name__ == "__main__":
    for name in PRIMED_PYTHON_FIXTURES:
        synced(FIXTURES / name, offline=False)
