import subprocess
import sys
from pathlib import Path


def _lint_imports() -> Path:
    """Resolve the console script beside the interpreter running the tests.

    Not a bare name: PATH only carries it when the virtual environment has been
    activated, so a bare lookup makes the contracts appear broken whenever the
    suite is invoked as `.venv/bin/pytest` — a false failure about the one thing
    this test exists to be trusted on.
    """
    return Path(sys.executable).parent / "lint-imports"


def test_import_contracts_hold_when_the_suite_runs():
    script = _lint_imports()
    assert script.exists(), f"import-linter is not installed beside {sys.executable}"
    result = subprocess.run([str(script)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
