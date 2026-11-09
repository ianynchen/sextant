"""A walk started inside another walk passes what it reads to the position that started it.

A binding round keeps every shared upward path that read nothing its new edges change
(`values.suffixes_kept`). That holds only if a path's record holds every read made while it
was worked out, and a walk can start another one: the unseen-object check and the object
reader do (task 8 re-review C1, where a lost read left a kept path stale and a real owner
dropped). So `_Walk` takes the stack of the walk that started it as a required argument, and
every walk-starting call inside `_Walk` hands its own stack on. The two readers that cache what
they built (`parameter_markers`, `_recipe_values`) keep their reads beside the answer and are
asked through `_read`, which this file does not check; their tests are in
`tests/application/test_receiver_binding.py` and `test_fastapi_depends.py`.
"""

import ast
from pathlib import Path

from sextant.application.resolve import values

# The module functions that start a walk of their own.
_STARTS_A_WALK = frozenset(
    {
        "producer_paths",
        "producers_of",
        "resolve_positions",
        "resolve_positions_on_paths",
        "resolve_site",
        "_Walk",
    }
)


def _walk_class() -> ast.ClassDef:
    tree = ast.parse(Path(values.__file__).read_text(encoding="utf-8"))
    (found,) = [
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "_Walk"
    ]
    return found


def test_every_walk_started_inside_a_walk_is_handed_its_stack():
    missing = []
    for node in ast.walk(_walk_class()):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in _STARTS_A_WALK:
            continue
        handed = [
            keyword.value
            for keyword in node.keywords
            if keyword.arg == "deps"
            and isinstance(keyword.value, ast.Attribute)
            and keyword.value.attr == "_deps"
            and isinstance(keyword.value.value, ast.Name)
            and keyword.value.value.id == "self"
        ]
        if not handed:
            missing.append(f"{node.func.id} at line {node.lineno}")

    assert missing == []
