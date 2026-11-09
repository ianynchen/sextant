"""`registration_conditions` on its own (OI-368, task 10b re-review ruling of 2026-11-09, part
2): where a row cannot be tied to one call of a helper whose calls register different rows, the
fallback never says "served" because some call of the helper is under no test."""

from sextant.application.resolve.registration_conditions import (
    UNCONDITIONAL,
    Conditions,
    Existence,
    existence_rows,
)

GUARD = ("main#<clinit>", "settings.DEBUG", True, ("settings.DEBUG",))
# `helper` is called at <clinit>@1 under no test and at <clinit>@2 under `settings.DEBUG`; the
# route is registered at helper@0.
CONDITIONS = Conditions(
    guards={("main#<clinit>", 2): (GUARD,)},
    callers={"helper": (("main#<clinit>", 1), ("main#<clinit>", 2))},
)
SITES = [("helper", 0)]


def _row(path: str) -> dict[str, object]:
    return {
        "protocol": "http",
        "direction": "inbound",
        "method": "GET",
        "path": path,
        "handler": "h",
        "caller": "helper",
    }


def test_a_call_chosen_by_the_row_decides_it():
    assert CONDITIONS.of_sites(SITES, {"helper": ("main#<clinit>", 1)}) == UNCONDITIONAL
    assert CONDITIONS.of_sites(SITES, {"helper": ("main#<clinit>", 2)}) == frozenset({(GUARD,)})


def test_untied_drops_the_unguarded_call_where_another_is_guarded():
    assert CONDITIONS.of_sites(SITES) == UNCONDITIONAL
    assert CONDITIONS.of_sites(SITES, untied=True) == frozenset({(GUARD,)})


def test_one_registration_giving_several_rows_reads_them_untied():
    existence = Existence(
        tied=CONDITIONS.of_sites(SITES),
        untied=CONDITIONS.of_sites(SITES, untied=True),
        key=tuple(SITES),
    )
    a, b = _row("/a"), _row("/b")
    written = existence_rows([(a, existence), (b, existence)], ["default"])
    assert sorted({str(row["path"]) for row in written}) == ["/a", "/b"]
    assert {row["holds"] for row in written} == {"unresolved"}


def test_one_registration_giving_one_row_reads_it_tied():
    """A helper called with nothing that differs gives one row: served."""
    existence = Existence(
        tied=CONDITIONS.of_sites(SITES),
        untied=CONDITIONS.of_sites(SITES, untied=True),
        key=tuple(SITES),
    )
    row = _row("/same")
    assert existence_rows([(row, existence), (row, existence)], ["default"]) == []
