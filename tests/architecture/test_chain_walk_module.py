"""The chain walk knows nothing about endpoints (Quartz spec 2026-10-28 §3d).

`shapes/chains.py` walks a builder chain — roots, steps, captures, folding, joins, bean
hops, lambda bodies, continuations — and yields each chain's end. What an end BECOMES is
its consumer's business: `fluent` turns one into endpoint rows, and a scheduling engine
turns one into `scheduled_work` rows. A walk that learned an endpoint concept would put
both derivations back in one module, which is the thing the move exists to undo.

So the module imports nothing from `engines/`, and its source never names the endpoint
vocabulary. `direction` is not on the list (plan ruling R1): a fluent root may carry its
own `direction:`, and the walk carries the root's declaration with the chain it starts
without reading it.
"""

import ast
from pathlib import Path

CHAINS = (
    Path(__file__).parents[2]
    / "src"
    / "sextant"
    / "application"
    / "resolve"
    / "shapes"
    / "chains.py"
)

ENDPOINT_WORDS = ("call_endpoints", "protocol", "client_base", "channel_bindings")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_chain_walk_names_no_endpoint_concept():
    assert CHAINS.exists(), f"{CHAINS} does not exist"
    engines = sorted(
        name for name in _imported_modules(CHAINS) if "sextant.application.resolve.engines" in name
    )
    assert engines == [], f"shapes/chains.py imports from engines/: {engines}"
    source = CHAINS.read_text(encoding="utf-8")
    named = [word for word in ENDPOINT_WORDS if word in source]
    assert named == [], f"shapes/chains.py names endpoint concepts: {named}"
