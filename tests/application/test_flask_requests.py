"""Flask request reads: what a handler's body reads off `flask.request` (plan
2026-11-19-python-flask-inbound, Task 4).

Each read is a property of the library class `request` is typed as (`flask.globals.request:
Request`), then `.get` or a subscript on the result. `.get` is optional, a subscript required, but
for `request.headers[k]`, which raises a plain `KeyError` (a 500, not a 400): it is a bare read. The
rules are measured in `scripts/probes/flask_rules.md`.
"""

import test_flask_routes

libraries = test_flask_routes.libraries
orders_flask_env = test_flask_routes.orders_flask_env

_HEAD = "from flask import Flask, request\napp = Flask(__name__)\n"


def _reads(tmp_path, libraries, body: str, head: str = _HEAD) -> list[tuple]:
    workspace = test_flask_routes._resolved(tmp_path, libraries, {"main.py": head + body})
    return sorted(
        (row["kind"], row["name"], row["requirement"], row["resolution"])
        for row in workspace.query("endpoint_metadata")
        if row["direction"] == "inbound" and row["kind"] in ("query", "header", "cookie", "param")
    )


def _handler(body: str) -> str:
    return (
        "@app.get('/x')\ndef x():\n"
        + "".join(f"    {line}\n" for line in body.split("\n"))
        + "    return ''\n"
    )


def test_get_is_optional_on_each_of_the_four_sources(tmp_path, libraries):
    body = _handler(
        "request.args.get('q')\nrequest.headers.get('X-Token')\n"
        "request.cookies.get('sid')\nrequest.values.get('v')"
    )

    assert _reads(tmp_path, libraries, body) == [
        ("cookie", "sid", "optional", "resolved"),
        ("header", "X-Token", "optional", "resolved"),
        ("param", "v", "optional", "resolved"),
        ("query", "q", "optional", "resolved"),
    ]


def test_a_subscript_is_required_but_a_header_subscript_is_a_bare_read(tmp_path, libraries):
    body = _handler(
        "request.args['q']\nrequest.cookies['sid']\nrequest.values['v']\nrequest.headers['X-Token']"
    )

    assert _reads(tmp_path, libraries, body) == [
        ("cookie", "sid", "required", "resolved"),
        ("header", "X-Token", None, "resolved"),
        ("param", "v", "required", "resolved"),
        ("query", "q", "required", "resolved"),
    ]


def test_get_with_a_default_or_a_type_is_the_same_read(tmp_path, libraries):
    body = _handler(
        "request.args.get('a', 1)\nrequest.args.get('b', type=int)\nrequest.args.get('c', 1, int)"
    )

    assert _reads(tmp_path, libraries, body) == [
        ("query", name, "optional", "resolved") for name in "abc"
    ]


def test_a_name_that_is_not_a_literal_is_an_unresolved_read(tmp_path, libraries):
    body = _handler("request.args.get(compute())")

    assert _reads(tmp_path, libraries, body, _HEAD + "def compute():\n    return 'q'\n") == [
        ("query", None, "optional", "unresolved")
    ]


def test_the_same_calls_on_another_receiver_read_nothing(tmp_path, libraries):
    body = _handler(
        "other = {}\nother.get('q')\nother['q']\nother.args.get('q')\nother.headers['h']"
    )

    assert _reads(tmp_path, libraries, body) == []


def test_a_read_in_a_helper_the_handler_calls_is_not_read(tmp_path, libraries):
    body = "def helper():\n    return request.args.get('q')\n" + _handler("helper()")

    assert _reads(tmp_path, libraries, body) == []
