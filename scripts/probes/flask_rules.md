# Flask route-registration and request-read rules (plan 5, Task 1)

Measured by `flask_rules.py`, run as
`fixtures/orders-flask/.venv/bin/python -I scripts/probes/flask_rules.py`.
Every rule below is an `assert` in the script. Rules are read from `app.url_map` after real
registration; requests go through Flask's own test client.

**Version scope.** Flask 3.1.3 and werkzeug 3.1.9, pinned in the fixture's `pyproject.toml` and
`uv.lock`. The running process prints both versions on its first line. Every verdict holds for these
versions and no other.

## Defining symbols

Quoted symbols are the file's own names; no line numbers.

| Surface | Defined on | File |
|---|---|---|
| `route`, `get`, `post`, `put`, `patch`, `delete` | `Scaffold` (neither `Flask` nor `Blueprint` defines them) | `flask/sansio/scaffold.py` |
| `add_url_rule` on an app | `App.add_url_rule` | `flask/sansio/app.py` |
| `add_url_rule` on a blueprint | `Blueprint.add_url_rule` | `flask/sansio/blueprints.py` |
| `register_blueprint` on an app | `App.register_blueprint` | `flask/sansio/app.py` |
| `register_blueprint` on a blueprint | `Blueprint.register_blueprint` | `flask/sansio/blueprints.py` |
| the prefix join | `BlueprintSetupState.add_url_rule` | `flask/sansio/blueprints.py` |
| the prefix choice | `BlueprintSetupState.__init__` | `flask/sansio/blueprints.py` |
| nested prefix composition | `Blueprint.register` (loop over `self._blueprints`) | `flask/sansio/blueprints.py` |
| `request` | module variable `request: Request` in `flask/globals.py` | `flask/globals.py` |
| `Request.args`, `Request.cookies` | `Request` | `werkzeug/sansio/request.py` |
| `Request.values` | `Request` | `werkzeug/wrappers/request.py` |
| `Request.headers` | instance attribute set in `Request.__init__` (not a property) | `werkzeug/sansio/request.py` |

`flask.request` is `LocalProxy(_cv_request, "request", ...)` annotated `request: Request`, where
`Request` is `flask.wrappers.Request`.

## Registration

- `Scaffold.route(rule, **options)` returns `decorator(f)`, which calls
  `self.add_url_rule(rule, endpoint, f, **options)` and returns `f`. So the rule is index 0 and the
  decorated function is the handler.
- `add_url_rule(self, rule, endpoint=None, view_func=None, ...)` on both app and blueprint:
  `rule` index 0, `endpoint` index 1, `view_func` index 2 (keyword name `view_func`).
- `Scaffold._method_route` backs `get/post/put/patch/delete`: `if "methods" in options: raise
  TypeError(...)`, then `self.route(rule, methods=[method], **options)`. One method each;
  `methods=` on them is refused.

## `methods=`

| Registration | `url_map` methods |
|---|---|
| no `methods` | `GET, HEAD, OPTIONS` |
| `methods=["post", "Put"]` | `POST, PUT, OPTIONS` (upper-cased; no HEAD without GET) |
| `methods=["GET", "HEAD"]` or `["GET", "OPTIONS"]` | `GET, HEAD, OPTIONS` (same set as the automatic one) |
| `methods=["GET"], provide_automatic_options=False` | `GET, HEAD` (OPTIONS dropped, HEAD kept) |
| `methods=["POST"]` | `POST, OPTIONS` (OPTIONS is added to every rule, not only GET ones) |
| `methods="GET"` (bare string) | `TypeError` at registration |

`App.add_url_rule` does `methods = {item.upper() for item in methods}` and, when `OPTIONS` is
not in it and `PROVIDE_AUTOMATIC_OPTIONS` is set, adds `OPTIONS`. werkzeug's `Rule` adds `HEAD`
when `GET` is present. The test client confirms an `OPTIONS` answer lists `OPTIONS, POST` and a
`GET` on a POST-only rule answers 405.

## Paths and converters

- A rule without a leading `/` raises `ValueError("URL rule 'nolead' must start with a slash.")`
  from werkzeug's `Rule.__init__`, at registration (import time for decorators).
- Converters stay exactly as written in `url_map`: `/u/<id>`, `/u/<int:id>`, `/u/<path:rest>`,
  `/u/<string:s>/x/<float:f>`.
- `<id>` and `<int:id>` on one path both register; werkzeug matches the `int` one first. This is a
  matching boundary, not modeled.

## Blueprint prefix joins

The join, quoted from `BlueprintSetupState.add_url_rule`:

```python
if self.url_prefix is not None:
    if rule:
        rule = "/".join((self.url_prefix.rstrip("/"), rule.lstrip("/")))
    else:
        rule = self.url_prefix
```

The prefix choice, from `BlueprintSetupState.__init__`: `url_prefix = self.options.get("url_prefix")`;
`if url_prefix is None: url_prefix = self.blueprint.url_prefix`.

Catalog words these ground:

- **`path_join: single_slash`.** `prefix.rstrip("/") + "/" + rule.lstrip("/")`. Measured: `/p/` + `x`,
  `/p` + `x`, and `/p//` + `//x` all give `/p/x`. An empty rule serves the prefix itself, verbatim
  (`/p` -> `/p`, `/p/` -> `/p/`). Rule `/` under `/p` gives `/p/`, so `""` and `"/"` differ.
  A slash-less rule under a prefix is accepted (`/p` + `nolead` -> `/p/nolead`); with no prefix it
  is the leading-slash `ValueError` above.
- **`prefix_replaces_own`.** `register_blueprint(bp, url_prefix=...)` REPLACES the blueprint's own
  `url_prefix`: own `/own`, given `/given` -> `/given/x`. Only `None` keeps the own prefix.
  An empty string `''` is not `None`, so it replaces too: own `/own`, given `''` -> `/x`; and an
  empty rule under it is an empty URL rule, `ValueError` at registration.
- No own prefix and a given one: `/given` + `/x` -> `/given/x`. No prefix at all: the rule as written.

### Nesting

`Blueprint.register` walks `self._blueprints`: `bp_url_prefix = bp_options.get("url_prefix")`, falling
back to `blueprint.url_prefix`; then, when the parent state has a prefix too,
`bp_options["url_prefix"] = state.url_prefix.rstrip("/") + "/" + bp_url_prefix.lstrip("/")`.

- `parent.register_blueprint(child)` with prefixes `/parent`, `/child`, rule `/x`: `/parent/child/x`,
  endpoint `parent.child.v`.
- Given prefixes: `parent.register_blueprint(child, url_prefix="/given")` and
  `app.register_blueprint(parent, url_prefix="/top")`: `/top/given/x`. Each level's given prefix
  replaces that level's own, then they compose parent first.
- A trailing-slash parent prefix (`/top/`) joins with exactly one `/`: `/top/child/x`.

### One blueprint registered twice

The second `app.register_blueprint(bp, ...)` under the same name raises
`ValueError("The name 'bp' is already registered for this blueprint. Use 'name=' to provide a unique name.")`.
With `name="bp2"` both register: `/a/x` and `/b/x`, endpoints `bp.v` and `bp2.v`.

### Slash handling: stated boundary, not modeled

- `strict_slashes` (default True): a rule `/slash/` also answers `/slash` with a 308 redirect; a rule
  `/noslash` does not answer `/noslash/` (404). `url_map` keeps one rule, as written.
- `merge_slashes` (default True): `url_map` keeps `/a//b` as written. It changes request matching only.

## Request reads

| Read | Absent key | Meaning |
|---|---|---|
| `request.args["q"]` | `BadRequestKeyError` (400) | required |
| `request.args.get("q")` | `None` / the default | optional |
| `request.args.get("q", type=int)` | converts; default when conversion fails | typed optional |
| `request.headers["H"]` | plain `KeyError` (not `BadRequestKeyError`) | required |
| `request.headers.get("H")` | `None` | optional |
| `request.cookies["c"]` | `BadRequestKeyError` | required |
| `request.values["x"]` | `BadRequestKeyError` | required |

`request.values` merges query and form into one mapping: with `?q=1&both=fromquery` and form
`f=2&both=fromform`, `values["q"]` is `1`, `values["f"]` is `2`, `values["both"]` is `fromquery`
(args come first) and `values.getlist("both")` is `["fromquery", "fromform"]`. `request.args` does not
see the form field `f`. So the `param` kind means exactly: a read by name from the query string or the
form body, not one of the two alone.

## Observations

Generated by `scripts/probes/flask_rules.py`, run in `fixtures/orders-flask`'s own environment.
The 3.1.3 column is Flask. The column header is the version the running process reported (it
prints `importlib.metadata.version` for flask and werkzeug on its first line), not the version the
lock asked for. Every row is an `assert` in the script, so a cell that failed would have stopped
the run.

| Rule | 3.1.3 |
|---|---|
| defining class of `route/get/post/put/patch/delete` | `Scaffold` (`flask/sansio/scaffold.py`) |
| defining class of `add_url_rule`, `register_blueprint` | `App` (app), `Blueprint` (blueprint) |
| `add_url_rule` handler position | `view_func`, index 2 |
| `methods` absent | `GET, HEAD, OPTIONS` |
| `methods=["post"]` | `POST, OPTIONS` (upper-cased) |
| `provide_automatic_options=False` on GET | `GET, HEAD` |
| rule without leading `/` | `ValueError` at registration |
| `path_join` | `prefix.rstrip("/") + "/" + rule.lstrip("/")`; empty rule = the prefix |
| `register_blueprint(url_prefix=...)` | replaces the blueprint's own prefix (`prefix_replaces_own`) |
| nested blueprints | parent prefix, then child prefix, then rule |
| same blueprint twice, same name | `ValueError` ("Use 'name=' to provide a unique name.") |
| `request.args["q"]` absent | `BadRequestKeyError` (required); `.get` optional |
| `request.values` | query and form merged, args first |

The full run output, verbatim:

```
versions: {'flask': '3.1.3', 'werkzeug': '3.1.9'}
RULE: route/get/post/put/patch/delete are defined on flask.sansio.scaffold.Scaffold (Flask and Blueprint inherit)
RULE: add_url_rule is defined on flask.sansio.app.App (app) and flask.sansio.blueprints.Blueprint
RULE: register_blueprint is defined on flask.sansio.app.App (app) and flask.sansio.blueprints.Blueprint
RULE: add_url_rule(rule, endpoint=None, view_func=None, ...): rule index 0, view_func index 2 (app and blueprint)
RULE: route(rule, **options) is a decorator; the decorated function is the handler
RULE: app.get/post/put/patch/delete(rule) register exactly that method (plus the automatic ones); methods= on them raises TypeError
RULE: methods absent -> GET, and url_map also lists HEAD and OPTIONS: {GET, HEAD, OPTIONS}
RULE: methods are upper-cased on the wire (`post` -> POST); no HEAD is added without GET: {POST, PUT, OPTIONS}
RULE: declared HEAD / OPTIONS collapse into the same set as the automatic ones
RULE: provide_automatic_options=False drops OPTIONS but keeps the automatic HEAD: {GET, HEAD}
RULE: automatic OPTIONS row is added to every rule, not only GET ones: {POST, OPTIONS}
RULE: methods as a bare string raises TypeError at registration
RULE: a rule without a leading slash raises ValueError("URL rule 'nolead' must start with a slash.") at registration
RULE: converters stay as written in url_map: <id>, <int:id>, <path:rest> (url_map rule strings)
RULE: overlapping <id> and <int:id> both register; the more specific converter wins a match (boundary, not modeled)
RULE: own url_prefix joins the rule: /own + /x -> /own/x
RULE: register_blueprint(url_prefix=...) REPLACES the blueprint's own prefix: own /own, given /given -> /given/x
RULE: register_blueprint(url_prefix=None) keeps the own prefix
RULE: register_blueprint(url_prefix='') also REPLACES the own prefix (only None keeps it): own /own, given '' -> /x
RULE: an empty rule under the replaced-to-empty prefix '' is an empty URL rule: ValueError at registration
RULE: no own prefix, given prefix: /given + /x -> /given/x
RULE: no prefix at all: the rule is registered as written
RULE: prefix.rstrip('/') + '/' + rule.lstrip('/'): trailing-slash prefix and slash-less rule both join with exactly one '/'
RULE: empty rule under a prefix serves the prefix itself, verbatim (/p -> /p, /p/ -> /p/)
RULE: rule '/' under /p -> /p/ (the trailing slash is kept; '' and '/' differ)
RULE: a blueprint rule without a leading slash and no prefix refuses at registration (ValueError)
RULE: a slash-less blueprint rule under a prefix is accepted: the join supplies the slash (/p + nolead -> /p/nolead)
RULE: nested bp.register_blueprint(child): parent prefix, then child prefix, then rule -> /parent/child/x (endpoint parent.child.v)
RULE: nesting with given prefixes: each level's given prefix replaces that level's own; then they compose: /top + /given + /x
RULE: nesting joins a trailing-slash parent prefix with exactly one '/': /top/ + /child + /x -> /top/child/x
RULE: registering one blueprint twice under the same name raises ValueError: "The name 'bp' is already registered for this blueprint. Use 'name=' to provide a unique name."
RULE: registering it again with name='bp2' gives both prefixes: /a/x and /b/x (endpoints bp.v, bp2.v)
RULE: strict_slashes (default True): '/slash/' also answers '/slash' with a 308 redirect; '/noslash' does not answer '/noslash/' (404). url_map keeps one rule as written. Boundary, not modeled
RULE: merge_slashes (default True) rewrites no rule: url_map keeps '/a//b' as written; it only affects matching a request. Boundary, not modeled
RULE: flask.request is a werkzeug LocalProxy annotated `request: Request` in flask/globals.py (flask.wrappers.Request)
RULE: args and cookies are properties of werkzeug.sansio.request.Request; values is a property of werkzeug.wrappers.request.Request
RULE: headers is not a property: werkzeug.sansio.request.Request.__init__ assigns self.headers (instance attribute)
RULE: request.args['q'] on a missing key raises BadRequestKeyError (400): subscript = required
RULE: request.args.get('q') on a missing key returns None / the default: optional
RULE: request.headers['H'] raises a plain KeyError (not BadRequestKeyError) when absent; .get is optional
RULE: request.cookies['c'] raises BadRequestKeyError when absent; .get is optional
RULE: request.values merges query (args) and form: both are readable by one name, and on a clash args come first. A `param` row therefore means 'query or form field'
RULE: request.values['x'] on a missing key raises BadRequestKeyError: subscript = required
RULE: args.get('q', type=int) converts, returns the default when conversion fails (typed optional read)
```
