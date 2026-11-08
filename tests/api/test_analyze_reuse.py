"""A re-run reuses what did not change (OI-325; D00 §2: "the source file is the unit of
incremental reuse"; D01 §7). Every case analyses one project twice into one workspace, the
second time after a change, and compares that workspace with a fresh analysis of the changed
project: the fact files byte for byte, every table, and `metadata.json`. A reused fact must be
what a fresh scan writes, or the reuse is a wrong value (user ruling 2026-11-02).

Which files were reused is read off the fact files' modification times: a file the second run
kept is the first run's file, untouched. Whether the resolve ran is counted at the stage.

The project is built in `tmp_path`: a `pyproject.toml`, four module files, and a `.venv`
holding the one library it declares, `greet`. `shop/api.py` imports `shop.util`, which does
not exist at first: `from shop import util` is then the member `util` of `shop`, and once
`shop/util.py` exists it is the module, so adding that file changes `shop/api.py`'s facts
without touching its bytes.
"""

import json
import shutil
from pathlib import Path

import duckdb
import pytest

from sextant import api, resources
from sextant.application.stages import analyze as stage

_FILES = {
    "shop/__init__.py": "",
    "shop/models.py": "class Order:\n    def total(self) -> int:\n        return 1\n",
    "shop/api.py": (
        "from greet import hello\n"
        "from shop import util\n"
        "from shop.models import Order\n"
        "\n"
        "\n"
        "def handle():\n"
        "    hello()\n"
        "    util.ping()\n"
        "    return Order().total()\n"
    ),
    "shop/service.py": "from shop.api import handle\n\n\ndef run():\n    return handle()\n",
}
# The workspace tables that say how the workspace was built, not what the module is: the
# second run's and a fresh run's may differ there and nowhere else.
_HOW_IT_WAS_BUILT = {"scan_reuse", "resolve_stamp"}


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _install(site: Path, version: str) -> None:
    """`greet` as an installer leaves it: its file, and a `.dist-info` whose `RECORD`
    lists it."""
    for old in site.glob("greet-*.dist-info"):
        for file in old.iterdir():
            file.unlink()
        old.rmdir()
    info = site / f"greet-{version}.dist-info"
    _write(info / "METADATA", f"Metadata-Version: 2.1\nName: greet\nVersion: {version}\n\n")
    _write(site / "greet" / "__init__.py", "def hello() -> str:\n    return 'hi'\n")
    _write(site / "greet" / "py.typed", "")
    record = ["greet/__init__.py,sha256=x,1", "greet/py.typed,,"]
    record += [f"{info.name}/METADATA,,", f"{info.name}/RECORD,,"]
    _write(info / "RECORD", "\n".join(record) + "\n")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    _write(
        root / "pyproject.toml",
        '[project]\nname = "shop"\nversion = "1.0.0"\ndependencies = ["greet"]\n',
    )
    for relative, text in _FILES.items():
        _write(root / relative, text)
    _write(root / ".venv" / "pyvenv.cfg", "home = /usr/bin\nversion_info = 3.12.4\n")
    _install(root / ".venv" / "lib" / "python3.12" / "site-packages", "1.0")
    return root


@pytest.fixture
def resolves(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """One entry per resolve the stage ran."""
    ran: list[int] = []
    real = stage.resolve

    def counted(*args, **kwargs):
        ran.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(stage, "resolve", counted)
    return ran


def _analyze(project: Path, workspace: Path) -> None:
    api.analyze(project, options=api.AnalyzeOptions(workspace_dir=workspace))


def _fact_files(workspace: Path) -> dict[str, bytes]:
    facts = workspace / "facts"
    return {
        path.relative_to(facts).as_posix(): path.read_bytes()
        for path in sorted(facts.rglob("*"))
        if path.is_file()
    }


def _modified(workspace: Path) -> dict[str, int]:
    facts = workspace / "facts"
    return {
        path.relative_to(facts).as_posix(): path.stat().st_mtime_ns
        for path in sorted(facts.rglob("*.jsonl"))
    }


def _tables(workspace: Path) -> dict[str, list[tuple[object, ...]]]:
    connection = duckdb.connect(str(workspace / "workspace.duckdb"), read_only=True)
    try:
        names = [
            str(name)
            for (name,) in connection.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main' ORDER BY table_name"
            ).fetchall()
        ]
        tables: dict[str, list[tuple[object, ...]]] = {}
        for name in names:
            if name in _HOW_IT_WAS_BUILT:
                continue
            columns = {
                str(column)
                for (column,) in connection.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                    [name],
                ).fetchall()
            }
            if "seq" in columns:
                # `seq` is the rowid a load gave a fact (`schema.sql`'s `symbols`), and a
                # workspace loaded twice numbers on from its first load: its ORDER is the
                # contract, so the rows are compared in that order without the number.
                rows = connection.execute(f"SELECT * EXCLUDE (seq) FROM {name} ORDER BY seq")
                tables[name] = rows.fetchall()
            else:
                rows = connection.execute(f"SELECT * FROM {name}")
                tables[name] = sorted(rows.fetchall(), key=repr)
        return tables
    finally:
        connection.close()


def _assert_same_as_fresh(project: Path, warm: Path, tmp_path: Path) -> None:
    fresh = tmp_path / "fresh"
    _analyze(project, fresh)
    assert _fact_files(warm) == _fact_files(fresh)
    assert _tables(warm) == _tables(fresh)
    assert json.loads((warm / "metadata.json").read_text()) == json.loads(
        (fresh / "metadata.json").read_text()
    )


def _rewritten(before: dict[str, int], after: dict[str, int]) -> set[str]:
    """The fact files the second run wrote: new ones, and old ones whose time moved."""
    return {name for name, when in after.items() if before.get(name) != when}


_MODULE_DOCUMENTS = {"module.jsonl", "__type_headers__.jsonl"}


def test_no_change_reuses_every_file_and_keeps_the_resolve(
    project: Path, tmp_path: Path, resolves: list[int]
):
    warm = tmp_path / "warm"
    _analyze(project, warm)
    before = _modified(warm)

    _analyze(project, warm)

    assert _rewritten(before, _modified(warm)) <= _MODULE_DOCUMENTS
    assert len(resolves) == 1
    _assert_same_as_fresh(project, warm, tmp_path)


def test_one_file_edited_rereads_that_file_alone(
    project: Path, tmp_path: Path, resolves: list[int]
):
    warm = tmp_path / "warm"
    _analyze(project, warm)
    before = _modified(warm)

    _write(project / "shop" / "service.py", "def run():\n    return 2\n")
    _analyze(project, warm)

    assert _rewritten(before, _modified(warm)) - _MODULE_DOCUMENTS == {"shop/service.py.jsonl"}
    assert len(resolves) == 2
    _assert_same_as_fresh(project, warm, tmp_path)


def test_a_file_another_imports_edited_in_a_body_rereads_that_file_alone(
    project: Path, tmp_path: Path
):
    """`shop/api.py` imports `Order` from `shop/models.py` and reads that file's HEADER
    (round 1, user choice A) and nothing of its bodies, so changing a body leaves
    `shop/api.py`'s facts as they were — which the comparison with a fresh run proves rather
    than assumes."""
    warm = tmp_path / "warm"
    _analyze(project, warm)
    before = _modified(warm)

    _write(
        project / "shop" / "models.py",
        "class Order:\n    def total(self) -> int:\n        return 2\n",
    )
    _analyze(project, warm)

    assert _rewritten(before, _modified(warm)) - _MODULE_DOCUMENTS == {"shop/models.py.jsonl"}
    _assert_same_as_fresh(project, warm, tmp_path)


def test_a_file_another_imports_edited_in_its_header_rereads_its_importers(
    project: Path, tmp_path: Path
):
    """A signature `shop/api.py` read changes (`total`'s declared return): every file that
    read that header is read again, and the result is a fresh run's."""
    warm = tmp_path / "warm"
    _analyze(project, warm)
    before = _modified(warm)

    _write(
        project / "shop" / "models.py",
        "class Order:\n    def total(self) -> str:\n        return 'a'\n",
    )
    _analyze(project, warm)

    assert _rewritten(before, _modified(warm)) - _MODULE_DOCUMENTS == {
        "shop/models.py.jsonl",
        "shop/api.py.jsonl",
    }
    _assert_same_as_fresh(project, warm, tmp_path)


# A module-level type alias in `shop/models.py` and a parameter annotated with it in
# `shop/service.py` (plan 2026-11-08 N2): the parameter's type and annotation value are read
# through `shop/models.py`'s header.
_ALIASED_MODELS = (
    "from typing import Annotated\n"
    "class Order:\n    def total(self) -> int:\n        return 1\n"
    "class Invoice:\n    pass\n"
    "OrderRef = Annotated[Order, 'ref']\n"
)
_ALIASED_SERVICE = "from shop.models import OrderRef\n\n\ndef run(o: OrderRef):\n    return 1\n"


def test_editing_an_alias_rereads_the_files_that_import_it(project: Path, tmp_path: Path):
    """`OrderRef` changes what it is an alias of: `shop/service.py`, whose parameter is typed
    by it, is read again, and its facts are a fresh run's."""
    _write(project / "shop" / "models.py", _ALIASED_MODELS)
    _write(project / "shop" / "service.py", _ALIASED_SERVICE)
    warm = tmp_path / "warm"
    _analyze(project, warm)
    before = _modified(warm)

    _write(
        project / "shop" / "models.py",
        _ALIASED_MODELS.replace("Annotated[Order, ", "Annotated[Invoice, "),
    )
    _analyze(project, warm)

    rewritten = _rewritten(before, _modified(warm)) - _MODULE_DOCUMENTS
    assert {"shop/models.py.jsonl", "shop/service.py.jsonl"} <= rewritten
    assert "Invoice#" in (warm / "facts" / "shop" / "service.py.jsonl").read_text()
    _assert_same_as_fresh(project, warm, tmp_path)


def test_editing_a_body_beside_an_alias_rereads_only_that_file(project: Path, tmp_path: Path):
    """A body of `shop/models.py` changes and its alias does not: only that file is read
    again."""
    _write(project / "shop" / "models.py", _ALIASED_MODELS)
    _write(project / "shop" / "service.py", _ALIASED_SERVICE)
    warm = tmp_path / "warm"
    _analyze(project, warm)
    before = _modified(warm)

    _write(project / "shop" / "models.py", _ALIASED_MODELS.replace("return 1", "return 2"))
    _analyze(project, warm)

    assert _rewritten(before, _modified(warm)) - _MODULE_DOCUMENTS == {"shop/models.py.jsonl"}
    _assert_same_as_fresh(project, warm, tmp_path)


def test_one_file_added_rereads_it_and_every_file_whose_import_it_changes(
    project: Path, tmp_path: Path
):
    warm = tmp_path / "warm"
    _analyze(project, warm)
    before = _modified(warm)

    _write(project / "shop" / "util.py", "def ping():\n    pass\n")
    _analyze(project, warm)

    assert _rewritten(before, _modified(warm)) - _MODULE_DOCUMENTS == {
        "shop/util.py.jsonl",
        "shop/api.py.jsonl",
    }
    _assert_same_as_fresh(project, warm, tmp_path)


def test_one_file_deleted_takes_its_facts_with_it(project: Path, tmp_path: Path):
    warm = tmp_path / "warm"
    _write(project / "shop" / "util.py", "def ping():\n    pass\n")
    _analyze(project, warm)

    (project / "shop" / "util.py").unlink()
    _analyze(project, warm)

    assert "shop/util.py.jsonl" not in _fact_files(warm)
    _assert_same_as_fresh(project, warm, tmp_path)


def test_a_library_version_changed_in_the_environment_rereads_every_file(
    project: Path, tmp_path: Path
):
    warm = tmp_path / "warm"
    _analyze(project, warm)
    before = _modified(warm)

    _install(project / ".venv" / "lib" / "python3.12" / "site-packages", "2.0")
    _analyze(project, warm)

    assert set(_rewritten(before, _modified(warm))) >= {f"{name}.jsonl" for name in _FILES}
    _assert_same_as_fresh(project, warm, tmp_path)


@pytest.mark.parametrize("stamp", ["SEXTANT_VERSION", "FACT_SCHEMA_VERSION"])
def test_a_version_bump_rereads_every_file_and_resolves_again(
    project: Path, tmp_path: Path, resolves: list[int], monkeypatch: pytest.MonkeyPatch, stamp: str
):
    from sextant.egress.render import metadata
    from sextant.ingress.extract.python import scanner

    warm = tmp_path / "warm"
    _analyze(project, warm)
    before = _modified(warm)

    # Every module that stamps the version, as a release moves them all.
    bumped = "9.9.9" if stamp == "SEXTANT_VERSION" else 99
    for module in (scanner, stage, metadata):
        monkeypatch.setattr(module, stamp, bumped)
    _analyze(project, warm)

    assert set(_rewritten(before, _modified(warm))) >= {f"{name}.jsonl" for name in _FILES}
    assert len(resolves) == 2
    _assert_same_as_fresh(project, warm, tmp_path)


def test_a_file_newly_ignored_is_dropped_as_a_fresh_run_drops_it(project: Path, tmp_path: Path):
    warm = tmp_path / "warm"
    _analyze(project, warm)

    _write(project / ".sextantignore", "shop/service.py\n")
    _analyze(project, warm)

    assert "shop/service.py.jsonl" not in _fact_files(warm)
    _assert_same_as_fresh(project, warm, tmp_path)


def test_a_catalog_model_edited_resolves_again(
    project: Path, tmp_path: Path, resolves: list[int], monkeypatch: pytest.MonkeyPatch
):
    """Every file under the catalogs is knowledge the resolve reads: a model folder beside
    the catalogs (`server-models/`) edited must re-run it (OI-325 fix round 1)."""
    catalogs = tmp_path / "catalogs"
    shutil.copytree(resources.catalogs_dir(), catalogs)
    monkeypatch.setattr(api, "catalogs_dir", lambda root=None: catalogs)
    warm = tmp_path / "warm"
    _analyze(project, warm)

    model = catalogs / "server-models" / "spring-boot.yml"
    model.write_text(model.read_text() + "# edited\n")
    _analyze(project, warm)

    assert len(resolves) == 2
    _assert_same_as_fresh(project, warm, tmp_path)


def test_a_code_file_changed_rereads_every_file_and_resolves_again(
    project: Path, tmp_path: Path, resolves: list[int], monkeypatch: pytest.MonkeyPatch
):
    """The code digest is in both keys (`resources.code_identity`, which every file of the
    package moves: `tests/test_sextant_resources.py`), so a changed code file — a
    derivation's `.sql` as much as a `.py` — re-reads every file and resolves again."""
    from sextant.ingress.extract.python import scanner

    warm = tmp_path / "warm"
    _analyze(project, warm)
    before = _modified(warm)

    for module in (api, scanner):
        monkeypatch.setattr(module, "code_identity", lambda: "sha256:another build")
    _analyze(project, warm)

    assert set(_rewritten(before, _modified(warm))) >= {f"{name}.jsonl" for name in _FILES}
    assert len(resolves) == 2
    _assert_same_as_fresh(project, warm, tmp_path)


def test_a_record_that_cannot_be_read_rereads_its_file(project: Path, tmp_path: Path):
    """A record whose detail is not what this build writes — a damaged row, or an older
    format — is not a reason to stop: its file is read again (OI-325 fix round 1)."""
    warm = tmp_path / "warm"
    _analyze(project, warm)
    before = _modified(warm)
    connection = duckdb.connect(str(warm / "workspace.duckdb"))
    try:
        connection.execute("UPDATE scan_reuse SET detail = 'not json' WHERE target LIKE '%api%'")
        connection.execute("UPDATE scan_reuse SET detail = '{}' WHERE target LIKE '%models%'")
    finally:
        connection.close()

    _analyze(project, warm)

    assert _rewritten(before, _modified(warm)) - _MODULE_DOCUMENTS == {
        "shop/api.py.jsonl",
        "shop/models.py.jsonl",
    }
    _assert_same_as_fresh(project, warm, tmp_path)
