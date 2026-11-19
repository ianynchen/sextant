"""Pin the Flask route-registration and request-read rules the Python inbound catalog copies (plan 5, Task 1).

Run it inside the orders-flask fixture's own environment, never Sextant's:

    fixtures/orders-flask/.venv/bin/python -I scripts/probes/flask_rules.py

Every rule is asserted, then printed. Rules are read from `app.url_map` after real registration;
requests go through Flask's own test client. The probe runs Flask on purpose; Sextant itself never
does (spec 7). Rules and quotes are in `flask_rules.md`.
"""

from __future__ import annotations

import importlib.metadata
import inspect

import flask
import flask.globals
from flask import Blueprint, Flask, request
from werkzeug.exceptions import BadRequestKeyError
from werkzeug.sansio.request import Request as SansioRequest
from werkzeug.wrappers.request import Request as WrapperRequest


def rule(text: str) -> None:
    print(f"RULE: {text}")


def rules(app: Flask) -> dict[str, set[str]]:
    """url_map as {rule string: methods}, static route excluded."""
    return {
        r.rule: set(r.methods or ()) for r in app.url_map.iter_rules() if r.endpoint != "static"
    }


def view() -> str:
    return "ok"


def definer(cls: type, name: str) -> str:
    """The class in the MRO whose own __dict__ defines `name`, as module.Class."""
    for k in cls.__mro__:
        if name in k.__dict__:
            return f"{k.__module__}.{k.__name__}"
    raise AssertionError(name)


print("versions:", {d: importlib.metadata.version(d) for d in ("flask", "werkzeug")})

# 0. Flask 2.x (CTFd locks 2.1.3) predates the `sansio` split: `route` and the verb shortcuts are
# on `flask.scaffold.Scaffold`. The 3.x ownership assertions below do not hold there, so a 2.x run reports the
# defining classes it measured, then runs the version-independent rules. Run it in that project's own environment, same flags.
V2 = int(importlib.metadata.version("flask").split(".")[0]) < 3
if V2:
    for cls, names in (
        (
            Flask,
            (
                "route",
                "get",
                "post",
                "put",
                "patch",
                "delete",
                "add_url_rule",
                "register_blueprint",
            ),
        ),
        (Blueprint, ("route", "get", "add_url_rule", "register_blueprint", "__init__")),
        (flask.Request, ("args", "cookies", "values")),
    ):
        for name in names:
            print(f"OWNER: {cls.__name__}.{name} -> {definer(cls, name)}")
    assert "self.headers =" in inspect.getsource(SansioRequest.__init__)
    print(
        "OWNER: headers is assigned by werkzeug.sansio.request.Request.__init__ (instance attribute)"
    )
    print(f"OWNER: Blueprint is {Blueprint.__module__}.{Blueprint.__qualname__}")
    print(f"OWNER: Flask is {Flask.__module__}.{Flask.__qualname__}")
    ann = inspect.get_annotations(flask.globals, eval_str=False)
    print(f"OWNER: flask.globals request annotation -> {ann.get('request')!r}")

# 1. Defining classes of the registration surface.
if not V2:
    for name in ("route", "get", "post", "put", "patch", "delete"):
        assert (
            definer(Flask, name) == definer(Blueprint, name) == "flask.sansio.scaffold.Scaffold"
        ), name
    assert definer(Flask, "add_url_rule") == "flask.sansio.app.App"
    assert definer(Blueprint, "add_url_rule") == "flask.sansio.blueprints.Blueprint"
    assert definer(Flask, "register_blueprint") == "flask.sansio.app.App"
    assert definer(Blueprint, "register_blueprint") == "flask.sansio.blueprints.Blueprint"
    assert "route" not in Flask.__dict__ and "get" not in Flask.__dict__
    rule(
        "route/get/post/put/patch/delete are defined on flask.sansio.scaffold.Scaffold (Flask and Blueprint inherit)"
    )
    rule(
        "add_url_rule is defined on flask.sansio.app.App (app) and flask.sansio.blueprints.Blueprint"
    )
    rule(
        "register_blueprint is defined on flask.sansio.app.App (app) and flask.sansio.blueprints.Blueprint"
    )

# 2. Positions: the rule is index 0; the handler is `view_func`, index 2, on both add_url_rule's.
for cls in (Flask, Blueprint):
    pos = list(inspect.signature(cls.add_url_rule).parameters)
    assert pos[:4] == ["self", "rule", "endpoint", "view_func"], pos
rule(
    "add_url_rule(rule, endpoint=None, view_func=None, ...): rule index 0, view_func index 2 (app and blueprint)"
)
assert list(inspect.signature(Flask.route).parameters)[:2] == ["self", "rule"]
assert Flask("d").route("/d")(view) is view
rule("route(rule, **options) is a decorator; the decorated function is the handler")

# Verb decorators: one method each; `methods=` on them is refused.
app = Flask("v")
for verb in ("get", "post", "put", "patch", "delete"):
    getattr(app, verb)(f"/{verb}")(view)
    assert rules(app)[f"/{verb}"] - {"HEAD", "OPTIONS"} == {verb.upper()}, verb
    try:
        getattr(app, verb)("/bad", methods=["GET"])
    except TypeError:
        pass
    else:
        raise AssertionError(verb)
rule(
    "app.get/post/put/patch/delete(rule) register exactly that method (plus the automatic ones); methods= on them raises TypeError"
)

# The verb shortcuts are `route`: `_method_route` hands off to `self.route`.
for verb in ("get", "post", "put", "patch", "delete"):
    assert "self._method_route(" in inspect.getsource(getattr(Flask, verb)), verb
assert "self.route(rule, methods=[method]" in inspect.getsource(Flask._method_route)
rule(
    "get/post/put/patch/delete delegate to Scaffold._method_route, which calls self.route(rule, methods=[method])"
)

# A returned Response object is passed through, not built into a body.
from flask import Response as FlaskResponse
from werkzeug.wrappers import Response as WerkzeugResponse

assert issubclass(FlaskResponse, WerkzeugResponse)
_resp = Flask("r")
_sent = FlaskResponse("raw", status=202)
_resp.add_url_rule("/r", view_func=lambda: _sent, endpoint="r")
_resp.add_url_rule("/s", view_func=lambda: WerkzeugResponse("w", status=203), endpoint="s")
assert _resp.make_response(_sent) is _sent
with _resp.test_client() as _c:
    assert (_c.get("/r").status_code, _c.get("/r").get_data()) == (202, b"raw")
    assert (_c.get("/s").status_code, _c.get("/s").get_data()) == (203, b"w")
rule(
    "a handler returning flask.Response (a subclass of werkzeug Response) or a werkzeug Response is the finished response: make_response returns it unchanged, so no body shape comes from its annotation"
)

# 3. methods=.
app = Flask("m")
app.add_url_rule("/default", view_func=view, endpoint="d")
app.add_url_rule("/lower", view_func=view, endpoint="l", methods=["post", "Put"])
app.add_url_rule("/explicit_head", view_func=view, endpoint="eh", methods=["GET", "HEAD"])
app.add_url_rule("/explicit_options", view_func=view, endpoint="eo", methods=["GET", "OPTIONS"])
app.add_url_rule(
    "/no_auto", view_func=view, endpoint="na", methods=["GET"], provide_automatic_options=False
)
app.add_url_rule("/post_only", view_func=view, endpoint="po", methods=["POST"])
got = rules(app)
assert got["/default"] == {"GET", "HEAD", "OPTIONS"}
rule("methods absent -> GET, and url_map also lists HEAD and OPTIONS: {GET, HEAD, OPTIONS}")
assert got["/lower"] == {"POST", "PUT", "OPTIONS"}
rule(
    "methods are upper-cased on the wire (`post` -> POST); no HEAD is added without GET: {POST, PUT, OPTIONS}"
)
assert got["/explicit_head"] == {"GET", "HEAD", "OPTIONS"}
assert got["/explicit_options"] == {"GET", "HEAD", "OPTIONS"}
rule("declared HEAD / OPTIONS collapse into the same set as the automatic ones")
assert got["/no_auto"] == {"GET", "HEAD"}
rule("provide_automatic_options=False drops OPTIONS but keeps the automatic HEAD: {GET, HEAD}")
assert got["/post_only"] == {"POST", "OPTIONS"}
rule("automatic OPTIONS row is added to every rule, not only GET ones: {POST, OPTIONS}")
try:
    app.add_url_rule("/str", view_func=view, endpoint="s", methods="GET")  # type: ignore[arg-type]
except TypeError:
    rule("methods as a bare string raises TypeError at registration")
else:
    raise AssertionError("bare-string methods accepted")
c = app.test_client()
assert set(c.open("/post_only", method="OPTIONS").headers["Allow"].split(", ")) == {
    "OPTIONS",
    "POST",
}
assert c.get("/post_only").status_code == 405

# 4. Path refusals and converters.
app = Flask("p")
try:
    app.add_url_rule("nolead", view_func=view, endpoint="n")
except ValueError as e:
    assert str(e) == (
        "urls must start with a leading slash"
        if V2
        else "URL rule 'nolead' must start with a slash."
    )
    rule(f"a rule without a leading slash raises ValueError({str(e)!r}) at registration")
else:
    raise AssertionError("rule without slash accepted")
for i, path in enumerate(("/u/<id>", "/u/<int:id>", "/u/<path:rest>", "/u/<string:s>/x/<float:f>")):
    app.add_url_rule(path, view_func=view, endpoint=f"c{i}")
assert set(rules(app)) == {"/u/<id>", "/u/<int:id>", "/u/<path:rest>", "/u/<string:s>/x/<float:f>"}
rule("converters stay as written in url_map: <id>, <int:id>, <path:rest> (url_map rule strings)")
# <id> and <int:id> overlap: werkzeug sorts int first, so /u/5 matches <int:id>.
assert app.url_map.bind("x").match("/u/5")[0] == "c1"
rule(
    "overlapping <id> and <int:id> both register; the more specific converter wins a match (boundary, not modeled)"
)


# 5. Blueprint joins.
def build(own: str | None, given: str | None, rule_: str, *, use_given: bool = True) -> list[str]:
    app = Flask("b")
    bp = Blueprint("bp", __name__, url_prefix=own)
    bp.add_url_rule(rule_, view_func=view, endpoint="v")
    app.register_blueprint(bp, **({"url_prefix": given} if use_given else {}))
    return sorted(rules(app))


assert build("/own", None, "/x", use_given=False) == ["/own/x"]
rule("own url_prefix joins the rule: /own + /x -> /own/x")
assert build("/own", "/given", "/x") == ["/given/x"]
rule(
    "register_blueprint(url_prefix=...) REPLACES the blueprint's own prefix: own /own, given /given -> /given/x"
)
assert build("/own", None, "/x") == ["/own/x"]
rule("register_blueprint(url_prefix=None) keeps the own prefix")
assert build("/own", "", "/x") == ["/x"]
rule(
    "register_blueprint(url_prefix='') also REPLACES the own prefix (only None keeps it): own /own, given '' -> /x"
)
try:
    build("/own", "", "")
except ValueError:
    rule(
        "an empty rule under the replaced-to-empty prefix '' is an empty URL rule: ValueError at registration"
    )
else:
    raise AssertionError("empty rule under empty prefix accepted")
assert build(None, "/given", "/x") == ["/given/x"]
rule("no own prefix, given prefix: /given + /x -> /given/x")
assert build(None, None, "/x", use_given=False) == ["/x"]
rule("no prefix at all: the rule is registered as written")
assert build("/p/", None, "/x", use_given=False) == ["/p/x"]
assert build("/p", None, "x", use_given=False) == ["/p/x"]
assert build("/p//", None, "//x", use_given=False) == ["/p/x"]
rule(
    "prefix.rstrip('/') + '/' + rule.lstrip('/'): trailing-slash prefix and slash-less rule both join with exactly one '/'"
)
assert build("/p", None, "", use_given=False) == ["/p"]
assert build("/p/", None, "", use_given=False) == ["/p/"]
rule("empty rule under a prefix serves the prefix itself, verbatim (/p -> /p, /p/ -> /p/)")
assert build("/p", None, "/", use_given=False) == ["/p/"]
rule("rule '/' under /p -> /p/ (the trailing slash is kept; '' and '/' differ)")
try:
    build(None, None, "nolead", use_given=False)
except ValueError:
    rule(
        "a blueprint rule without a leading slash and no prefix refuses at registration (ValueError)"
    )
else:
    raise AssertionError("blueprint rule without slash and prefix accepted")
for own, given, label in (("api", None, "own"), (None, "api", "registration")):
    try:
        build(own, given, "/x", use_given=given is not None)
    except ValueError:
        rule(
            f"a slash-less {label} url_prefix ('api' + '/x' -> 'api/x') refuses at registration (ValueError)"
        )
    else:
        raise AssertionError(f"slash-less {label} prefix accepted")
assert build("/p", None, "nolead", use_given=False) == ["/p/nolead"]
rule(
    "a slash-less blueprint rule under a prefix is accepted: the join supplies the slash (/p + nolead -> /p/nolead)"
)

# nesting
app = Flask("n")
parent = Blueprint("parent", __name__, url_prefix="/parent")
child = Blueprint("child", __name__, url_prefix="/child")
child.add_url_rule("/x", view_func=view, endpoint="v")
parent.register_blueprint(child)
app.register_blueprint(parent)
assert sorted(rules(app)) == ["/parent/child/x"]
assert [r.endpoint for r in app.url_map.iter_rules() if r.rule == "/parent/child/x"] == [
    "parent.child.v"
]
rule(
    "nested bp.register_blueprint(child): parent prefix, then child prefix, then rule -> /parent/child/x (endpoint parent.child.v)"
)
app = Flask("n2")
parent = Blueprint("parent", __name__, url_prefix="/parent")
child = Blueprint("child", __name__, url_prefix="/child")
child.add_url_rule("/x", view_func=view, endpoint="v")
parent.register_blueprint(child, url_prefix="/given")
app.register_blueprint(parent, url_prefix="/top")
assert sorted(rules(app)) == ["/top/given/x"]
rule(
    "nesting with given prefixes: each level's given prefix replaces that level's own; then they compose: /top + /given + /x"
)
app = Flask("n3")
parent = Blueprint("parent", __name__)
child = Blueprint("child", __name__, url_prefix="/child")
child.add_url_rule("/x", view_func=view, endpoint="v")
parent.register_blueprint(child)
app.register_blueprint(parent, url_prefix="/top/")
assert sorted(rules(app)) == ["/top/child/x"]
rule(
    "nesting joins a trailing-slash parent prefix with exactly one '/': /top/ + /child + /x -> /top/child/x"
)

# one blueprint, twice
app = Flask("t")
bp = Blueprint("bp", __name__)
bp.add_url_rule("/x", view_func=view, endpoint="v")
app.register_blueprint(bp, url_prefix="/a")
try:
    app.register_blueprint(bp, url_prefix="/b")
except ValueError as e:
    assert "already registered" in str(e) and "name=" in str(e)
    rule(f"registering one blueprint twice under the same name raises ValueError: {str(e)!r}")
else:
    raise AssertionError("same blueprint twice accepted")
app.register_blueprint(bp, url_prefix="/b", name="bp2")
assert sorted(rules(app)) == ["/a/x", "/b/x"]
assert sorted(app.view_functions) == ["bp.v", "bp2.v", "static"]
rule(
    "registering it again with name='bp2' gives both prefixes: /a/x and /b/x (endpoints bp.v, bp2.v)"
)

# slash behavior: a stated boundary
app = Flask("s")
app.add_url_rule("/slash/", view_func=view, endpoint="a")
app.add_url_rule("/noslash", view_func=view, endpoint="b")
c = app.test_client()
assert c.get("/slash").status_code == 308 and c.get("/slash/").status_code == 200
assert c.get("/noslash").status_code == 200 and c.get("/noslash/").status_code == 404
assert set(rules(app)) == {"/slash/", "/noslash"}
rule(
    "strict_slashes (default True): '/slash/' also answers '/slash' with a 308 redirect; '/noslash' does not answer '/noslash/' (404). url_map keeps one rule as written. Boundary, not modeled"
)
app = Flask("s2")
app.add_url_rule("/a//b", view_func=view, endpoint="a")
assert set(rules(app)) == {"/a//b"}
assert app.url_map.merge_slashes is True
rule(
    "merge_slashes (default True) rewrites no rule: url_map keeps '/a//b' as written; it only affects matching a request. Boundary, not modeled"
)

# 6. Request reads.
ann = inspect.get_annotations(flask.globals, eval_str=False)
assert ann["request"] == "Request"
assert request.__class__.__name__ == "LocalProxy"
rule(
    "flask.request is a werkzeug LocalProxy annotated `request: Request` in flask/globals.py (flask.wrappers.Request)"
)
assert flask.Request is flask.wrappers.Request
for attr, owner in (
    ("args", "werkzeug.sansio.request.Request"),
    ("cookies", "werkzeug.sansio.request.Request"),
    ("values", "werkzeug.wrappers.request.Request"),
):
    assert definer(flask.Request, attr) == owner, attr
    owner_class = {"werkzeug.sansio.request.Request": SansioRequest}.get(owner, WrapperRequest)
    assert isinstance(owner_class.__dict__[attr], property), attr
assert "headers" not in SansioRequest.__dict__ and "headers" not in WrapperRequest.__dict__
assert "self.headers = headers" in inspect.getsource(SansioRequest.__init__)
rule(
    "args and cookies are properties of werkzeug.sansio.request.Request; values is a property of werkzeug.wrappers.request.Request"
)
rule(
    "headers is not a property: werkzeug.sansio.request.Request.__init__ assigns self.headers (instance attribute)"
)

app = Flask("r")
with app.test_request_context(
    "/?q=1&both=fromquery",
    method="POST",
    data={"f": "2", "both": "fromform"},
    headers={"X-Token": "t"},
    environ_overrides={"HTTP_COOKIE": "sid=abc"},
):
    try:
        request.args["missing"]
    except BadRequestKeyError:
        rule(
            "request.args['q'] on a missing key raises BadRequestKeyError (400): subscript = required"
        )
    else:
        raise AssertionError("missing arg did not raise")
    assert request.args.get("missing") is None and request.args.get("missing", "d") == "d"
    rule("request.args.get('q') on a missing key returns None / the default: optional")
    assert request.args["q"] == "1"
    assert request.headers["X-Token"] == "t" and request.headers.get("X-None") is None
    try:
        request.headers["X-None"]
    except KeyError as e:
        assert not isinstance(e, BadRequestKeyError)
        rule(
            "request.headers['H'] raises a plain KeyError (not BadRequestKeyError) when absent; .get is optional"
        )
    else:
        raise AssertionError("absent header did not raise")
    assert request.cookies["sid"] == "abc"
    try:
        request.cookies["nope"]
    except BadRequestKeyError:
        rule("request.cookies['c'] raises BadRequestKeyError when absent; .get is optional")
    else:
        raise AssertionError("absent cookie did not raise")
    assert "f" not in request.args and request.form["f"] == "2"
    assert request.values["q"] == "1" and request.values["f"] == "2"
    assert request.values["both"] == "fromquery"
    assert request.values.getlist("both") == ["fromquery", "fromform"]
    rule(
        "request.values merges query (args) and form: both are readable by one name, and on a clash args come first. "
        "A `param` row therefore means 'query or form field'"
    )
    try:
        request.values["missing"]
    except BadRequestKeyError:
        rule("request.values['x'] on a missing key raises BadRequestKeyError: subscript = required")
    else:
        raise AssertionError("absent values key did not raise")
    assert request.args.get("q", type=int) == 1
    assert request.args.get("both", type=int) is None
    assert request.args.get("both", type=int, default=-1) == -1
    rule(
        "args.get('q', type=int) converts; a non-numeric value ('fromquery') returns None, or the default when one is given (typed optional read)"
    )
