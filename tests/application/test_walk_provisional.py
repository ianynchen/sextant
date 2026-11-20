"""An answer worked out while a back edge was open is reused only where a fresh compute would
work out the same answer (`values.Kept`): every back edge it rested on still pending, and none
of the positions it entered pending now.

Each test drives a real `_Walk` over a hand-built graph of positions: the walk's own `_compute`
is replaced by one that asks the walk for each child of a position (`_resolve`), so the memo
layers and the cycle guard under test are the walk's own. Each runs on both memo layers: a slot
is kept per (position, path) (`_memo`), a parameter once per position on the empty path
(`_suffixes`, R39).

Written before the keep rule they constrain. The first two PASS on the code that keeps no
answer resting on an open back edge (nothing is reused, so nothing is wrongly reused) and must
stay green after it; the third is meaningful only once such answers are kept.
"""

from typing import Any

import pytest

from sextant.application.resolve import values
from sextant.application.resolve.values import CYCLE, Answer, ValueIndex

_LAYERS = [values._SLOT, values._PARAMETER]


def _index() -> ValueIndex:
    """No reads at all: the graph below is the only thing the walk is asked about."""
    return ValueIndex(
        sites={},
        receivers={},
        producers={},
        returns={},
        callers={},
        parameters={},
        constants={},
        produced={},
        writers={},
        returned_values={},
        reached=frozenset(),
    )


class _Graph:
    """A walk whose positions are the names of `edges`: a position's answer is every child's
    answer in order, then its own literal where `leaf` holds it."""

    def __init__(self, kind: str, edges: dict[str, list[str]], leaf: set[str]) -> None:
        self.kind = kind
        self.edges = edges
        self.leaf = leaf
        self.computed: list[str] = []
        self.walk = values._Walk(_index(), deps=[])
        self.walk._compute = self._compute  # type: ignore[method-assign]

    def at(self, name: str) -> tuple[Any, ...]:
        if self.kind == values._SLOT:
            return (values._SLOT, name, 0, 0)
        return (values._PARAMETER, name, 0)

    def ask(self, name: str) -> list[Any]:
        """`name`'s answer on the empty path, each path as its literal or its reason."""
        return [answer.value or answer.reason for _, answer in self._ask(name)]

    def _ask(self, name: str) -> tuple[Any, ...]:
        return self.walk._resolve(self.at(name), (), ())

    def _compute(self, position: Any, trail: Any, frames: Any) -> tuple[Any, ...]:
        name = position[1]
        self.computed.append(name)
        found: list[Any] = []
        for child in self.edges.get(name, []):
            found.extend(self._ask(child))
        if name in self.leaf:
            found.append(((), Answer(kind="literal", value=name)))
        return tuple(found)


# Passes before the keep rule changes, and must stay green after.
@pytest.mark.parametrize("kind", _LAYERS)
def test_provisional_answer_not_reused_after_region_completes(kind):
    # H -> P -> H: P is worked out while H is pending, so its answer holds `cycle` at H.
    graph = _Graph(kind, {"H": ["P", "M"], "P": ["H", "L"]}, {"M", "L"})
    assert graph.ask("H") == [CYCLE, "L", "M"]
    # H is done. Asked again with nothing pending, P reads H's finished answer, M and all:
    # never the answer that held `cycle` at H.
    assert graph.ask("P") == [CYCLE, "L", "M", "L"]
    assert graph.computed.count("P") == 2


# Passes before the keep rule changes, and must stay green after.
@pytest.mark.parametrize("kind", _LAYERS)
def test_provisional_answer_not_reused_when_new_position_is_pending(kind):
    # P is first worked out under H, entering R (R -> P is P's own cycle). H then asks R
    # itself: with R pending, a fresh P answers `cycle` at R instead of entering it, so P's
    # first answer, which entered R, is not P's answer here although H is still pending.
    graph = _Graph(kind, {"H": ["P", "R"], "P": ["H", "R"], "R": ["P", "L"]}, {"L"})
    first = [CYCLE, CYCLE, "L"]
    again = [CYCLE, CYCLE]
    assert graph.ask("H") == first + again + ["L"]
    assert graph.computed.count("P") == 2


# Meaningful only once answers resting on an open back edge are kept.
@pytest.mark.parametrize("kind", _LAYERS)
def test_provisional_entries_die_with_their_back_edges(kind):
    graph = _Graph(kind, {"H": ["P", "M"], "P": ["H", "L"]}, {"M", "L"})
    graph.ask("H")
    for memo in (graph.walk._memo, graph.walk._suffixes):
        held = getattr(memo, "provisional", {})
        assert not [
            entry for entries in held.values() for entry in entries if graph.at("H") in entry[2]
        ]
