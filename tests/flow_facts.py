"""Hand-built call sites, given the control-flow position the extractor writes for code with
no branch in it (D00 §5's `dominator`, `on_every_exit`, `post_dominator` and `reaches_return`,
spec 2026-11-02-per-path-truth rule 9).

A reader takes a site with no `on_every_exit` as "position not computed", which is undecided
— the walk then splits at every call between a value's producer and its use. A test that
builds `o = create(); o.setHost("a"); use(o);` by hand means the straight line, so it states
the straight line: each site's `dominator` is the site before it in the same method, its
`post_dominator` the site after it, and every site runs on every exit and reaches a return. A site the test already
gave a position keeps it.

Its own module beside `fixture_build`, for the reason that file gives: several directories
under `tests/` have their own `conftest.py`.
"""

from collections.abc import Sequence
from typing import Any

from sextant.domain.facts import CallSiteFact


def straight_line(facts: Sequence[Any]) -> list[Any]:
    """`facts`, every call site without a position given the straight line's."""
    ordinals: dict[str, list[int]] = {}
    for fact in facts:
        if isinstance(fact, CallSiteFact):
            ordinals.setdefault(fact.caller, []).append(fact.ordinal)
    before: dict[tuple[str, int], int | None] = {}
    after: dict[tuple[str, int], int | None] = {}
    for caller, seen in ordinals.items():
        ordered = sorted(set(seen))
        for at, ordinal in enumerate(ordered):
            before[(caller, ordinal)] = ordered[at - 1] if at else None
            after[(caller, ordinal)] = ordered[at + 1] if at + 1 < len(ordered) else None
    return [
        fact.model_copy(
            update={
                "dominator": before[(fact.caller, fact.ordinal)],
                "on_every_exit": True,
                "post_dominator": after[(fact.caller, fact.ordinal)],
                "reaches_return": True,
            }
        )
        if isinstance(fact, CallSiteFact) and fact.on_every_exit is None
        else fact
        for fact in facts
    ]
