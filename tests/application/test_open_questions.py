"""Tests for the 2O amendment to `QUESTIONS` (2O design §0): three kinds
arrive ahead of the tasks that will write and read them (Tasks 2, 5, 7), and
the closed set keeps refusing anything outside it — the same discipline
`test_format_ladder.py`'s own `test_a_question_kind_outside_the_closed_set_is_refused`
pins for the two kinds 2G shipped."""

import pytest

from sextant.application.resolve.open_questions import QUESTIONS, record_open_questions
from sextant.storage.duckdb.workspace import DuckDbWorkspace


def test_the_three_new_kinds_are_accepted():
    for kind in ("channel_destination", "service_identity", "environment_divergence"):
        assert kind in QUESTIONS


def test_an_unknown_kind_is_still_refused_by_name(tmp_path):
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    with pytest.raises(ValueError, match="not one of"):
        record_open_questions(
            workspace,
            [
                {
                    "protocol": "http",
                    "method": "GET",
                    "path": "/x",
                    "question": "invented_kind",
                    "candidates": "[]",
                    "evidence": "syntax",
                }
            ],
        )
    workspace.close()
