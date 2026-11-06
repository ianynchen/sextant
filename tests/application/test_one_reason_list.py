"""One reason list everywhere (spec 2026-11-05-one-reason-list-design §4, §5).

Every "not resolved" answer carries one word of `values._REASONS` and a detail. This guard
reads each place that stores such a word, on a fixture the e2e suite already analyses, and
fails on any other word. A found answer has no reason (NULL), and a NULL reason is allowed
only there. The pass-through `unread[]` entries are read by the Vert.x e2e run
(`tests/e2e/test_rest_inbound_delivered.py`) and the `values` answers by the shadow run
(`tests/application/test_shadow_mode.py`), which hold that data already cached; all use the
functions of `tests/reason_guard.py`.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from reason_guard import (
    OLD_WORDS,
    outside_the_list,
    unread_outside_the_list,
    value_answers_outside_the_list,
)
from sextant.application.boundary.source import BoundarySource
from sextant.application.boundary.vocabulary import KINDS
from sextant.storage.duckdb.workspace import DuckDbWorkspace, open_read_only


@pytest.fixture(scope="module")
def tables(analyzed_orders_service: Path) -> dict[str, list[dict[str, Any]]]:
    workspace = DuckDbWorkspace(analyzed_orders_service / "workspace.duckdb")
    try:
        return {
            name: [dict(row) for row in workspace.query(name)]
            for name in (
                "resolved_config",
                "resolved_schedules",
                "resolved_peers",
                "method_resolution",
            )
        }
    finally:
        workspace.close()


def _all_wrong(tables: Mapping[str, list[dict[str, Any]]]) -> list[str]:
    return [
        *outside_the_list(
            tables["resolved_config"],
            "resolved_config",
            "unresolved_reason",
            found=lambda row: row["value"] is not None,
            detail="unresolved_detail",
        ),
        *outside_the_list(
            tables["resolved_schedules"],
            "resolved_schedules",
            "unresolved_reason",
            found=lambda row: row["unresolved_reason"] is None,
            detail="unresolved_detail",
        ),
        *outside_the_list(
            tables["resolved_peers"],
            "resolved_peers",
            "unresolved_reason",
            found=lambda row: row["unresolved_reason"] is None,
        ),
        *outside_the_list(
            tables["method_resolution"],
            "method_resolution",
            "reason",
            found=lambda row: row["declaring_class"] is not None,
            detail="detail",
        ),
    ]


def test_every_stored_reason_is_one_word_of_the_general_list(tables):
    assert _all_wrong(tables) == []


def test_the_fixture_exercises_each_table_so_the_guard_is_not_vacuous(tables):
    for name, rows in tables.items():
        assert rows, name
    assert any(r["reason"] for r in tables["method_resolution"])
    assert any(r["unresolved_reason"] for r in tables["resolved_config"])


@pytest.mark.parametrize("old", OLD_WORDS)
def test_the_guard_fails_when_an_old_word_is_planted(tables, old):
    """Each former word is written into each column in turn, on a copy, and the guard names it."""
    planted = {name: [dict(row) for row in rows] for name, rows in tables.items()}
    columns = {
        "resolved_config": "unresolved_reason",
        "resolved_schedules": "unresolved_reason",
        "resolved_peers": "unresolved_reason",
        "method_resolution": "reason",
    }
    for name, column in columns.items():
        if not planted[name]:
            continue
        before = dict(planted[name][0])
        planted[name][0][column] = old
        assert any(old in line for line in _all_wrong(planted)), (name, old)
        planted[name][0] = before


@pytest.mark.parametrize("old", OLD_WORDS)
def test_the_guard_fails_when_an_old_word_is_a_values_reason(old):
    answer = {"answer_kind": "unresolved", "reason": old}
    assert value_answers_outside_the_list([answer])
    assert (
        value_answers_outside_the_list([{"answer_kind": "unresolved", "reason": "escapes"}]) == []
    )
    assert value_answers_outside_the_list([{"answer_kind": "literal", "reason": "escapes"}])


@pytest.mark.parametrize("old", ("handed_to", "produced_by", "of_type", "no_body"))
def test_the_guard_fails_on_an_old_pass_through_entry(old):
    question = {
        "question": "handler_pass_through",
        "candidates": json.dumps([{"unread": [{"how": old, "name": "x"}]}]),
    }
    assert unread_outside_the_list([question])
    planted = {
        "question": "handler_pass_through",
        "candidates": json.dumps([{"unread": [{"reason": old, "detail": "x"}]}]),
    }
    assert unread_outside_the_list([planted])
    good = {
        "question": "handler_pass_through",
        "candidates": json.dumps([{"unread": [{"reason": "escapes", "detail": "x"}]}]),
    }
    assert unread_outside_the_list([good]) == []


def test_the_graph_property_attributes_carry_the_same_words(analyzed_orders_service: Path):
    """`boundary-property`'s `unresolved_reason` is read off `resolved_config`; the graph
    side is checked too, so a second copy of the words cannot appear there."""
    source = BoundarySource.open(analyzed_orders_service, open_read_only)
    try:
        rows = source.rows(KINDS["boundary-property"])
    finally:
        source.close()
    assert rows
    assert (
        outside_the_list(
            rows,
            "boundary-property",
            "unresolved_reason",
            found=lambda row: row["value"] is not None,
            detail="unresolved_detail",
        )
        == []
    )
