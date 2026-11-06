"""Every production build of the value walk's index names the container's models.

`values.cached_value_index` is built ONCE per resolve, by whichever engine asks first, and
every later caller gets that index. A caller that leaves out `bean_models` and
`value_annotations` would build an index with no container-filled parameter at all, and the
recipe hop (spec 2026-11-05 di-recipe-hop §2) would silently not run for the whole resolve,
whichever engine came first. So every call under `src/` passes all five arguments.
"""

import ast
from pathlib import Path

SOURCE = Path(__file__).parents[2] / "src" / "sextant"


def test_every_index_build_in_the_resolve_passes_the_bean_models():
    short: list[str] = []
    for path in sorted(SOURCE.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name != "cached_value_index" and not (
                name == "value_index" and path.name == "shadow.py"
            ):
                continue
            if len(node.args) + len(node.keywords) < 5:
                short.append(f"{path.relative_to(SOURCE)}:{node.lineno}")
    assert short == [], f"index built without the container's models: {short}"
