"""The inbound-route helpers `combinator` and `fluent` share (Vert.x spec §3g item 2): the
media columns an inbound row carries and the `leading_slash` join of a prefix and a path.
They were `combinator`'s own; moving them is what lets a second engine call the same code."""

import pytest

from sextant.application.resolve.shapes.inbound_routes import join_prefix, media_columns


def _string(value: str) -> dict:
    return {"kind": "string", "value": value}


def test_no_media_capture_is_both_columns_null():
    assert media_columns({}) == (None, None)


def test_a_string_capture_is_a_one_element_json_array():
    assert media_columns({"produces": _string("application/json")}) == (
        None,
        '["application/json"]',
    )


def test_a_vararg_capture_is_sorted_and_distinct():
    captures = {
        "consumes": {
            "kind": "array",
            "elements": [_string("text/xml"), _string("application/json"), _string("text/xml")],
        }
    }
    assert media_columns(captures) == ('["application/json","text/xml"]', None)


def test_a_value_nobody_can_read_contributes_nothing():
    captures = {"produces": {"kind": "array", "elements": [{"kind": "unknown"}, _string("a/b")]}}
    assert media_columns(captures) == (None, '["a/b"]')
    assert media_columns({"produces": {"kind": "unknown"}}) == (None, None)


def test_the_leading_slash_rule_adds_one_slash_and_leaves_three_cases_alone():
    assert join_prefix(None, "orders", "leading_slash") == "/orders"
    assert join_prefix(None, "/orders", "leading_slash") == "/orders"
    assert join_prefix(None, "", "leading_slash") == ""
    assert join_prefix(None, "*", "leading_slash") == "*"


def test_a_prefix_is_written_verbatim_before_the_joined_path():
    assert join_prefix("/api", "orders", "leading_slash") == "/api/orders"
    assert join_prefix("/api", "", "leading_slash") == "/api"


@pytest.mark.parametrize("rule", ["", None])
def test_no_rule_is_verbatim_concatenation(rule):
    assert join_prefix("/api", "orders", rule) == "/apiorders"
