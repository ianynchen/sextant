"""`parameter_markers` (plan 2026-11-08-python-fastapi-inbound Task 4, N1, N2; ruling R14).

For each parameter, the producing call of its `default` and of each `Annotated` metadata
element, in written order, read through `values.producer_paths` (aliases in module fields and
in other files are followed), one marker per path. Built once per `ValueIndex`. It names no
framework: the calls below are whatever the code wrote."""

from pathlib import Path

from test_receiver_binding import _PREFIX, _resolved

from sextant.application.resolve.parameter_markers import parameter_markers
from sextant.application.resolve.values import value_index

_SIG = "(sig_dd69782a)."


def _markers(tmp_path: Path, files: dict[str, str], method: str, index: int) -> list[tuple]:
    """`(where, order, owner, name, caller)` of each marker of one parameter."""
    workspace = _resolved(tmp_path, files)
    found = parameter_markers(value_index(workspace)).get((_PREFIX + method + _SIG, index), ())
    workspace.close()
    return [
        (
            marker.where,
            marker.order,
            marker.site["owner"],
            marker.site["name"],
            str(marker.site["caller"]).removeprefix(_PREFIX),
        )
        for marker in found
    ]


def test_a_default_marker_is_found(tmp_path: Path):
    """`q=Query(None)`: the `Query` call the module body makes when it runs the `def`."""
    found = _markers(
        tmp_path,
        {"run.py": "from fastapi import Query\ndef h(q=Query(None)):\n    return q\n"},
        "app/run#h",
        0,
    )
    assert found == [("default", 0, "fastapi#", "Query", "app/run#<clinit>" + _SIG)]


def test_a_literal_default_has_no_marker(tmp_path: Path):
    """The near-miss: `limit=10` is produced by no call, so the parameter has no marker."""
    workspace = _resolved(tmp_path, {"run.py": "def h(limit=10):\n    return limit\n"})
    markers = parameter_markers(value_index(workspace))
    workspace.close()
    assert (_PREFIX + "app/run#h" + _SIG, 0) not in markers


def test_an_annotated_marker_is_found_in_written_order(tmp_path: Path):
    """`Annotated[str, Query(max_length=3), Header()]`: two markers, `Query` then `Header`;
    the type itself (`str`) is no marker."""
    found = _markers(
        tmp_path,
        {
            "run.py": "from typing import Annotated\n"
            "from fastapi import Header, Query\n"
            "def h(q: Annotated[str, Query(max_length=3), Header()]):\n    return q\n"
        },
        "app/run#h",
        0,
    )
    clinit = "app/run#<clinit>" + _SIG
    assert found == [
        ("annotation", 0, "fastapi#", "Query", clinit),
        ("annotation", 1, "fastapi#", "Header", clinit),
    ]


def test_an_alias_marker_in_another_file_is_found(tmp_path: Path):
    """`d: DbSession`, with `DbSession = Annotated[Session, Depends(get_db)]` in `deps.py`: the
    marker is the `Depends` call `deps.py`'s body makes."""
    found = _markers(
        tmp_path,
        {
            "db.py": "class Session:\n    pass\n",
            "deps.py": "from typing import Annotated\n"
            "from fastapi import Depends\n"
            "from app.db import Session\n"
            "def get_db():\n    return Session()\n"
            "DbSession = Annotated[Session, Depends(get_db)]\n",
            "run.py": "from app.deps import DbSession\ndef f(d: DbSession):\n    return d\n",
        },
        "app/run#f",
        0,
    )
    assert found == [("annotation", 0, "fastapi#", "Depends", "app/deps#<clinit>" + _SIG)]


def test_a_marker_two_paths_give_is_two_markers(tmp_path: Path):
    """`q=MARK`, where the module writes `MARK` on two branches: two paths, one marker each,
    never merged. (A conditional expression of two calls is one `non_enumerable` path, the
    walk's rule for a merge with no root, so it gives none.)"""
    found = _markers(
        tmp_path,
        {
            "run.py": "import os\n"
            "from fastapi import Header, Query\n"
            "if os.environ.get('STRICT'):\n    MARK = Query()\n"
            "else:\n    MARK = Header()\n"
            "def h(q=MARK):\n    return q\n"
        },
        "app/run#h",
        0,
    )
    clinit = "app/run#<clinit>" + _SIG
    assert sorted(found) == [
        ("default", 0, "fastapi#", "Header", clinit),
        ("default", 0, "fastapi#", "Query", clinit),
    ]


def test_a_jvm_module_has_no_markers(resolved_fixture):
    """No JVM parameter has a `default` or an `annotation_value`, so there is nothing to read."""
    workspace, _ = resolved_fixture
    assert parameter_markers(value_index(workspace)) == {}
