import subprocess


def test_import_contracts_hold_when_the_suite_runs():
    result = subprocess.run(["lint-imports"], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
