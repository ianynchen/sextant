"""`tests/fixture_build.py`'s stamp: a compiled fixture is compiled again only when its
inputs change.

The suite is what these protect. MEASURED 2026-09-12 (`fixture_build.py`'s docstring): 19
of the 25 Maven runs in one full suite run verified a tree that had not changed since the
last run, ~130s of CPU. The stamp is what removes them, so what needs pinning is exactly
the two ways it could go wrong — skipping a compile that was needed (a changed source, a
changed parent POM, a rebuilt stub jar, a `target/` that is gone) and running one that was
not (a stamped root, or a `copytree` of one, which is how two module-scoped fixtures reach
their own copy of `orders-service`).

Maven itself never runs here: `subprocess.run` is replaced by a fake that records the call
and lays down `target/classes`, the one thing the stamp check looks for beside the stamp.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

import fixture_build
import fixture_stub

_POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.acme</groupId>
  <artifactId>{name}</artifactId>
  <version>1.0.0</version>
</project>
"""

_CHILD_POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>com.acme</groupId>
    <artifactId>reactor</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
  </parent>
  <artifactId>child</artifactId>
</project>
"""


@pytest.fixture
def stub_jar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A stand-in for the stub library's jar in `~/.m2`, so a test can rebuild it."""
    jar = tmp_path / "m2" / "orders-soap-client-1.0.0.jar"
    jar.parent.mkdir()
    jar.write_bytes(b"PK")
    monkeypatch.setattr(fixture_stub, "local_repository_jar", lambda: jar)
    return jar


@pytest.fixture
def maven(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Records every root Maven is asked to compile, and compiles it the cheap way."""
    roots: list[Path] = []

    def fake_run(args: list[str], *, cwd: Path, check: bool) -> None:
        assert args == ["mvn", "-q", "-o", "compile"]
        roots.append(cwd)
        (cwd / "target" / "classes").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return roots


def _module(root: Path, *, pom: str = _POM) -> Path:
    source = root / "src" / "main" / "java" / "com" / "acme"
    source.mkdir(parents=True)
    (source / "Hello.java").write_text("package com.acme;\npublic class Hello {}\n")
    (root / "pom.xml").write_text(pom.format(name=root.name), encoding="utf-8")
    return root


def _stamped(root: Path) -> Path:
    """As `compile_and_stamp` leaves a root, without running anything."""
    (root / "target" / "classes").mkdir(parents=True, exist_ok=True)
    (root / fixture_build.STAMP).write_text(fixture_build.fingerprint(root), encoding="utf-8")
    return root


def test_a_stamped_compiled_root_does_not_invoke_maven(
    tmp_path: Path, stub_jar: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _stamped(_module(tmp_path / "module"))

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"Maven was invoked: {args} {kwargs}")

    monkeypatch.setattr(subprocess, "run", refuse)
    assert fixture_build.compile_fixture(root) == root


def test_a_copy_of_a_stamped_root_is_stamped_too(
    tmp_path: Path, stub_jar: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The two module-scoped `compiled_fixture`s copy `orders-service` with `copytree`,
    which keeps `target/` — and the stamp inside it must hold for the copy, which is why
    the fingerprint reads content and relative paths, never mtimes or absolute paths."""
    root = _stamped(_module(tmp_path / "module"))
    copy = tmp_path / "elsewhere" / "module"
    shutil.copytree(root, copy)
    monkeypatch.setattr(subprocess, "run", pytest.fail)
    assert fixture_build.is_current(copy)
    fixture_build.compile_fixture(copy)


def test_changing_one_source_byte_reinvokes_maven_and_rewrites_the_stamp(
    tmp_path: Path, stub_jar: Path, maven: list[Path]
) -> None:
    root = _stamped(_module(tmp_path / "module"))
    before = (root / fixture_build.STAMP).read_text(encoding="utf-8")
    source = root / "src" / "main" / "java" / "com" / "acme" / "Hello.java"
    source.write_text(source.read_text().replace("Hello {}", "Hello { }"))

    fixture_build.compile_fixture(root)

    assert maven == [root]
    after = (root / fixture_build.STAMP).read_text(encoding="utf-8")
    assert after != before
    assert after == fixture_build.fingerprint(root)


def test_a_missing_target_classes_reinvokes_maven_even_with_a_matching_stamp(
    tmp_path: Path, stub_jar: Path, maven: list[Path]
) -> None:
    root = _stamped(_module(tmp_path / "module"))
    shutil.rmtree(root / "target" / "classes")

    fixture_build.compile_fixture(root)

    assert maven == [root]
    assert (root / "target" / "classes").is_dir()


def test_the_parent_pom_is_part_of_the_fingerprint_when_the_root_declares_a_parent(
    tmp_path: Path, stub_jar: Path
) -> None:
    """`orders-reactor/billing-lib` reaches the reactor's `pom.xml` by `<relativePath>`;
    a change there changes what Maven compiles against."""
    reactor = tmp_path / "reactor"
    reactor.mkdir()
    (reactor / "pom.xml").write_text(_POM.format(name="reactor"), encoding="utf-8")
    child = _module(reactor / "child", pom=_CHILD_POM)
    before = fixture_build.fingerprint(child)

    (reactor / "pom.xml").write_text(_POM.format(name="reactor") + "\n", encoding="utf-8")

    assert fixture_build.fingerprint(child) != before


def test_the_stub_jar_is_part_of_the_fingerprint(tmp_path: Path, stub_jar: Path) -> None:
    """`orders-service` compiles against the stub library, which the session fixture
    rebuilds whenever its sources are newer than the jar — a rebuilt jar is a new input."""
    root = _module(tmp_path / "module")
    before = fixture_build.fingerprint(root)

    os.utime(stub_jar, (stub_jar.stat().st_atime, stub_jar.stat().st_mtime + 60))

    assert fixture_build.fingerprint(root) != before


def test_touching_a_source_changes_nothing(tmp_path: Path, stub_jar: Path) -> None:
    """Content, not mtimes: a checkout or a `copytree` may set any mtime it likes."""
    root = _module(tmp_path / "module")
    before = fixture_build.fingerprint(root)
    source = root / "src" / "main" / "java" / "com" / "acme" / "Hello.java"

    os.utime(source, (source.stat().st_atime, source.stat().st_mtime + 60))

    assert fixture_build.fingerprint(root) == before


def test_what_a_compile_writes_and_the_suite_scribbles_are_not_inputs(
    tmp_path: Path, stub_jar: Path
) -> None:
    root = _module(tmp_path / "module")
    before = fixture_build.fingerprint(root)

    (root / "target" / "classes").mkdir(parents=True)
    (root / "target" / "classes" / "Hello.class").write_bytes(b"\xca\xfe\xba\xbe")
    (root / ".sextant").mkdir()
    (root / ".sextant" / "workspace.duckdb").write_bytes(b"")
    (root / ".sextant-enrichment.json").write_text("{}")
    (root / ".tradewind").mkdir()
    (root / ".tradewind" / "sessions.sqlite").write_bytes(b"")

    assert fixture_build.fingerprint(root) == before
