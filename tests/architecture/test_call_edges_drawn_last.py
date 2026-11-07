"""Ruling R31 (task 9a fix round 3): the function bodies a `__call__` runs (ruling R29) reach
`call_edges` in memory, from receiver binding, and are stored in no other table. That is
true only while nothing redraws `call_edges` after binding: `enrich`, `diff`, reopening a
workspace and the bundle all read the stored table. So `record_call_edges` has exactly two
callers, the pipeline's first draw and the binder, and the binder's is the last draw. A new
caller fails here, not in the data."""

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src" / "sextant"
_NAME = "record_call_edges"


def _calls(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == _NAME)
            or (isinstance(node.func, ast.Attribute) and node.func.attr == _NAME)
        )
    ]


def test_call_edges_are_drawn_only_by_the_pipeline_and_the_binder():
    callers = {
        path.relative_to(_SRC).as_posix(): len(lines)
        for path in sorted(_SRC.rglob("*.py"))
        if (lines := _calls(path))
    }
    assert callers == {
        "application/resolve/pipeline.py": 1,
        "application/resolve/receiver_binding.py": 2,
    }


def test_the_pipeline_draws_the_edges_before_it_binds_and_never_after():
    pipeline = _SRC / "application" / "resolve" / "pipeline.py"
    tree = ast.parse(pipeline.read_text(encoding="utf-8"))
    lines = {
        name: [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == name
        ]
        for name in (_NAME, "bind_until_settled")
    }
    (draw,) = lines[_NAME]
    (bind,) = lines["bind_until_settled"]
    assert draw < bind
