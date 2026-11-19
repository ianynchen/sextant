"""Flask blueprint prefixes: a blueprint's own `url_prefix=`, the prefix `register_blueprint`
gives, and nesting (plan 2026-11-19-python-flask-inbound Task 3).

Flask joins a prefix and a rule with one slash (`prefix.rstrip("/") + "/" + rule.lstrip("/")`,
the empty rule serving the prefix itself), and a prefix written at registration REPLACES the
blueprint's own, even the empty one; only an absent one keeps it. The rules are quoted in
`scripts/probes/flask_rules.md`.

Each test writes a small Flask program and runs the real pipeline with the shipped catalogs
(`test_flask_routes._resolved`).
"""

import test_flask_routes
from test_flask_routes import _handler, _rows

# The Flask environment the route tests read, shared rather than restated.
libraries = test_flask_routes.libraries
orders_flask_env = test_flask_routes.orders_flask_env

_HEAD = "from flask import Blueprint, Flask\napp = Flask(__name__)\n"
_X = "@bp.get('/x')\ndef x():\n    return ''\n"


def _paths(tmp_path, libraries, body: str) -> list[tuple[object, object]]:
    workspace = test_flask_routes._resolved(tmp_path, libraries, {"main.py": _HEAD + body})
    return sorted((row[0], row[1]) for row in _rows(workspace))


def test_own_prefix_goes_before_every_route_on_it(tmp_path, libraries):
    rows = test_flask_routes._rows(
        test_flask_routes._resolved(
            tmp_path,
            libraries,
            {
                "main.py": _HEAD
                + "bp = Blueprint('bp', __name__, url_prefix='/own')\n"
                + _X
                + "app.register_blueprint(bp)\n"
            },
        )
    )

    assert rows == [("GET", "/own/x", _handler("x"), "resolved")]


def test_a_blueprint_never_registered_rows_at_its_own_held_prefix(tmp_path, libraries):
    body = "bp = Blueprint('bp', __name__, url_prefix='/own')\n" + _X

    assert _paths(tmp_path, libraries, body) == [("GET", "/own/x")]


def test_registration_prefix_replaces_the_own_one(tmp_path, libraries):
    body = (
        "bp = Blueprint('bp', __name__, url_prefix='/own')\n"
        + _X
        + "app.register_blueprint(bp, url_prefix='/given')\n"
    )

    assert _paths(tmp_path, libraries, body) == [("GET", "/given/x")]


def test_an_empty_registration_prefix_also_replaces_the_own_one(tmp_path, libraries):
    body = (
        "bp = Blueprint('bp', __name__, url_prefix='/own')\n"
        + _X
        + "app.register_blueprint(bp, url_prefix='')\n"
    )

    assert _paths(tmp_path, libraries, body) == [("GET", "/x")]


def test_a_registration_prefix_alone_serves_the_routes(tmp_path, libraries):
    body = "bp = Blueprint('bp', __name__)\n" + _X + "app.register_blueprint(bp, url_prefix='/g')\n"

    assert _paths(tmp_path, libraries, body) == [("GET", "/g/x")]


def test_a_trailing_slash_prefix_and_a_slashless_rule_join_with_one_slash(tmp_path, libraries):
    body = (
        "bp = Blueprint('bp', __name__, url_prefix='/p/')\n"
        "@bp.get('x')\ndef x():\n    return ''\n"
        "@bp.get('/y')\ndef y():\n    return ''\n"
        "@bp.get('')\ndef root():\n    return ''\n"
        "app.register_blueprint(bp)\n"
    )

    assert _paths(tmp_path, libraries, body) == [
        ("GET", "/p/"),
        ("GET", "/p/x"),
        ("GET", "/p/y"),
    ]


def test_a_nested_blueprint_serves_parent_prefix_then_child_prefix(tmp_path, libraries):
    body = (
        "parent = Blueprint('parent', __name__, url_prefix='/parent/')\n"
        "bp = Blueprint('bp', __name__, url_prefix='/child')\n"
        + _X
        + "parent.register_blueprint(bp)\n"
        + "app.register_blueprint(parent)\n"
    )

    assert _paths(tmp_path, libraries, body) == [("GET", "/parent/child/x")]


def test_a_blueprint_registered_twice_serves_under_both_prefixes(tmp_path, libraries):
    body = (
        "bp = Blueprint('bp', __name__, url_prefix='/own')\n"
        + _X
        + "app.register_blueprint(bp, url_prefix='/a')\n"
        + "app.register_blueprint(bp, name='bp2', url_prefix='/b')\n"
    )

    assert _paths(tmp_path, libraries, body) == [("GET", "/a/x"), ("GET", "/b/x")]


def test_a_slashless_prefix_is_refused_and_serves_nothing(tmp_path, libraries):
    """Probe: `url_prefix='api'` joins to `api/x`, which Flask refuses at registration, own
    prefix or given, so no row is published."""
    own = "bp = Blueprint('bp', __name__, url_prefix='api')\n" + _X + "app.register_blueprint(bp)\n"
    given = (
        "bp = Blueprint('bp', __name__)\n" + _X + "app.register_blueprint(bp, url_prefix='api')\n"
    )
    held = "bp = Blueprint('bp', __name__, url_prefix='api')\n" + _X

    assert _paths(tmp_path / "a", libraries, own) == []
    assert _paths(tmp_path / "b", libraries, given) == []
    assert _paths(tmp_path / "c", libraries, held) == []
