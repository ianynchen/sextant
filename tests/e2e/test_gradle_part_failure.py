"""One broken part does not stop the others (Android design M5), through the real wrapper.

Two plain `java` parts, `:good` and `:bad`, where `bad` has a syntax error. Gradle runs with
`--continue`, so `good` builds and is analyzed, and `bad` is skipped with javac's own error
text as its reason. Before M5, the one compile failure refused the whole repository.

The build is written into `tmp_path` with a copy of `fixtures/gradle-orders`'s wrapper, so
nothing is left in the repository. The parts have no dependencies, so the only thing a machine
must have is the wrapper's Gradle distribution. This test skips when that is not there, the
same way `test_gradle_fixture_builds.py` does.
"""

import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from sextant.cli.app import cli
from sextant.ingress.detect.gradle import _OFFLINE_REFUSAL_SUBSTRING

WRAPPER_SOURCE = Path(__file__).parents[2] / "fixtures" / "gradle-orders"


def _write_build(root: Path) -> None:
    shutil.copy2(WRAPPER_SOURCE / "gradlew", root / "gradlew")
    shutil.copy2(WRAPPER_SOURCE / "gradlew.bat", root / "gradlew.bat")
    shutil.copytree(WRAPPER_SOURCE / "gradle", root / "gradle")
    (root / "settings.gradle.kts").write_text(
        'rootProject.name = "parts"\ninclude("good", "bad")\n', encoding="utf-8"
    )
    sources = {
        "good": 'public class Good { public String hello() { return "hi"; } }\n',
        "bad": 'public class Bad { public String hello() { return "hi" } }\n',
    }
    for part, body in sources.items():
        package = root / part / "src" / "main" / "java" / "com" / "acme"
        package.mkdir(parents=True)
        (root / part / "build.gradle.kts").write_text(
            'plugins { java }\ngroup = "com.acme"\nversion = "1.0"\n', encoding="utf-8"
        )
        (package / f"{part.capitalize()}.java").write_text(
            f"package com.acme;\n{body}", encoding="utf-8"
        )


def test_one_broken_part_does_not_stop_the_others(tmp_path: Path):
    _write_build(tmp_path)
    result = CliRunner().invoke(cli, ["module", "analyze", str(tmp_path)])

    if result.exit_code != 0:
        message = str(result.exception)
        if "Gradle distribution not present" in message or _OFFLINE_REFUSAL_SUBSTRING in message:
            pytest.skip(
                "the Gradle wrapper distribution is not primed on this machine — run "
                "`./gradlew build` once inside fixtures/gradle-orders with network access "
                f"(or see the CI prime step in .github/workflows/pr.yml). Gradle said: {message}"
            )
        raise AssertionError(f"module analyze failed: {result.output}\n{message}")

    assert "analyzed good (com.acme:good):" in result.output
    assert "skipped bad (com.acme:bad): Compilation failed" in result.output
    # javac's own words, carried through Gradle's failure text.
    assert "error: ';' expected" in result.output
    assert (tmp_path / "good" / ".sextant" / "metadata.json").is_file()
    assert not (tmp_path / "bad" / ".sextant").exists()
