"""Pin the `aiohttp` and `urllib3` call rules the Python outbound catalogs copy (plan 3 follow-up, Task 2).

Run it inside the orders-fastapi fixture's own environment, never Sextant's:

    fixtures/orders-fastapi/.venv/bin/python -I scripts/probes/aiohttp_urllib3_rules.py

Every rule is asserted, then printed. Requests go to a local HTTP server so the path, method and
body that reach the wire are what the library actually sends. The probe runs the libraries on
purpose; Sextant itself never does (spec 7). Rules and quotes are in `aiohttp_urllib3_rules.md`.
"""

from __future__ import annotations

import asyncio
import http.server
import importlib.metadata
import inspect
import json
import threading

import aiohttp
import aiohttp.client
import urllib3
import urllib3._request_methods
import urllib3.poolmanager

VERBS = {"get", "options", "head", "post", "put", "patch", "delete"}
seen: list[tuple[str, str, bytes, str]] = []


class Handler(http.server.BaseHTTPRequestHandler):
    def _any(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        seen.append((self.command, self.path, body, self.headers.get("Content-Type", "")))
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _any

    def log_message(self, *args: object) -> None:
        pass


server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{server.server_port}"


def rule(text: str) -> None:
    print(f"RULE: {text}")


def params(fn: object) -> list[str]:
    return [p for p in inspect.signature(fn).parameters if p != "self"]  # type: ignore[arg-type]


def positional(fn: object) -> list[str]:
    return [
        n
        for n, p in inspect.signature(fn).parameters.items()  # type: ignore[arg-type]
        if n != "self" and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]


def keyword_only(fn: object) -> list[str]:
    return [
        n
        for n, p in inspect.signature(fn).parameters.items()  # type: ignore[arg-type]
        if p.kind == p.KEYWORD_ONLY
    ]


def sourcefile(obj: object) -> str:
    return inspect.getsourcefile(inspect.unwrap(obj)).rsplit("/", 1)[-1]  # type: ignore[arg-type]


print(
    "versions:",
    {d: importlib.metadata.version(d) for d in ("aiohttp", "urllib3", "yarl", "multidict")},
)

# ---------------------------------------------------------------- aiohttp
# 1. Defining symbols.
assert aiohttp.ClientSession is aiohttp.client.ClientSession
assert aiohttp.ClientSession.__module__ == "aiohttp.client"
assert aiohttp.request is aiohttp.client.request and aiohttp.request.__module__ == "aiohttp.client"
for v in VERBS | {"request"}:
    assert getattr(aiohttp.ClientSession, v).__qualname__ == f"ClientSession.{v}", v
    assert sourcefile(getattr(aiohttp.ClientSession, v)) == "client.py", v
assert sourcefile(aiohttp.request) == "client.py"
rule(
    "owners: aiohttp.client.ClientSession.{get,...,request} and aiohttp.client.request (file "
    "aiohttp/client.py); aiohttp.ClientSession / aiohttp.request are re-exports of those"
)

# 2. Verb set.
for v in VERBS | {"request"}:
    assert callable(getattr(aiohttp.ClientSession, v)), v
assert not hasattr(aiohttp.ClientSession, "stream") and not hasattr(aiohttp, "get")
assert not hasattr(aiohttp, "post") and not hasattr(aiohttp, "head")
rule(
    f"verb methods on ClientSession: {sorted(VERBS)} plus request; the module has request() only "
    "(no aiohttp.get/post/...) and no stream()"
)

# 3. url / method positions, body keywords.
for v in VERBS:
    assert positional(getattr(aiohttp.ClientSession, v)) == ["url"], v
assert positional(aiohttp.ClientSession.request) == ["method", "url"]
assert positional(aiohttp.request) == ["method", "url"]
for v in ("post", "put", "patch"):
    assert keyword_only(getattr(aiohttp.ClientSession, v))[0] == "data", v
    assert "kwargs" in params(getattr(aiohttp.ClientSession, v)), v
for v in ("get", "head", "options", "delete"):
    assert "data" not in params(getattr(aiohttp.ClientSession, v)), v
assert "data" not in params(aiohttp.ClientSession.request)
assert "kwargs" in params(aiohttp.ClientSession.request) and "kwargs" in params(aiohttp.request)
assert {"data", "json"} <= set(params(aiohttp.ClientSession._request))
rule(
    "url is positional 0 on every verb method; request(method, url): method 0, url 1 (ClientSession "
    "and module level); no body is positional. post/put/patch name `data` keyword-only; "
    "json= (and data= on request/get/...) travel in **kwargs to ClientSession._request"
)
assert positional(aiohttp.ClientSession.__init__)[0] == "base_url"
rule("ClientSession(base_url, ...): base_url is positional 0 and also a keyword")

# 4. Wire behaviour (async).
printed_sources: dict[str, str] = {}


async def wire() -> None:
    async with aiohttp.ClientSession() as s:
        async with s.post(BASE + "/a", json={"k": 1}) as r:
            assert r.status == 200
        assert seen[-1][:2] == ("POST", "/a") and json.loads(seen[-1][2]) == {"k": 1}
        assert "application/json" in seen[-1][3]
        async with s.post(BASE + "/b", data={"k": "v"}):
            pass
        assert seen[-1][2] == b"k=v" and "x-www-form-urlencoded" in seen[-1][3]
        async with s.post(BASE + "/c", data=b"raw"):
            pass
        assert seen[-1][2] == b"raw" and "octet-stream" in seen[-1][3]
        async with s.post(BASE + "/d", data="text"):
            pass
        assert seen[-1][2] == b"text" and "text/plain" in seen[-1][3]
        fd = aiohttp.FormData()
        fd.add_field("f", b"x", filename="f.txt")
        async with s.post(BASE + "/e", data=fd):
            pass
        assert "multipart/form-data" in seen[-1][3] and b'name="f"' in seen[-1][2]
        async with s.post(BASE + "/n"):
            pass
        assert seen[-1][2] == b"" and seen[-1][3] == "application/octet-stream"
        async with s.get(BASE + "/n"):
            pass
        assert seen[-1][2] == b"" and seen[-1][3] == ""
    rule(
        "wire: json= sends compact JSON as application/json; data=dict form-urlencoded; data=bytes "
        "octet-stream; data=str text/plain; data=FormData with a file multipart; no body keyword "
        "sends an EMPTY body (POST also labels it application/octet-stream)"
    )

    # verb casing: ClientRequest upper-cases, request(method, url) at both levels.
    async with aiohttp.ClientSession() as s:
        async with s.request("get", BASE + "/lower-s"):
            pass
        assert seen[-1][:2] == ("GET", "/lower-s")
        async with s.request("patch", BASE + "/lower-p"):
            pass
        assert seen[-1][:2] == ("PATCH", "/lower-p")
        async with s.request("PUT", BASE + "/upper"):
            pass
        assert seen[-1][:2] == ("PUT", "/upper")
        async with s.request(method="DELETE", url=BASE + "/kw"):
            pass
        assert seen[-1][:2] == ("DELETE", "/kw")
    async with aiohttp.request("delete", BASE + "/lower-m"):
        pass
    assert seen[-1][:2] == ("DELETE", "/lower-m")
    async with aiohttp.request("post", BASE + "/m", json={"k": 2}):
        pass
    assert seen[-1][:2] == ("POST", "/m") and json.loads(seen[-1][2]) == {"k": 2}
    rule(
        "request(method, url): a lower-case method string is upper-cased on the wire ('get' -> GET), "
        "on ClientSession.request and on aiohttp.request; method=/url= keywords behave the same"
    )

    # body keywords together.
    async with aiohttp.ClientSession() as s:
        for kw in (
            {"data": {"d": "v"}, "json": {"j": 1}},
            {"data": b"x", "json": {"j": 1}},
            {"data": "", "json": {"j": 1}},
            {"data": {}, "json": {"j": 1}},
        ):
            before = len(seen)
            try:
                async with s.post(BASE + "/both", **kw):  # type: ignore[arg-type]
                    pass
                raise AssertionError(f"accepted {kw}")
            except ValueError as err:
                assert "data and json parameters can not be used at the same time" in str(err)
            assert len(seen) == before, "nothing may reach the wire"
        # An explicit None is the same as absent, so it does not clash.
        async with s.post(BASE + "/jn", data=None, json={"j": 1}):
            pass
        assert json.loads(seen[-1][2]) == {"j": 1}
        async with s.post(BASE + "/dn", data={"d": "v"}, json=None):
            pass
        assert seen[-1][2] == b"d=v"
        # Same on a bodiless verb and on request().
        try:
            async with s.request("GET", BASE + "/gb", data=b"x", json={"j": 1}):
                pass
            raise AssertionError
        except ValueError:
            pass
        async with s.get(BASE + "/gj", json={"j": 1}):
            pass
        assert seen[-1][:2] == ("GET", "/gj") and json.loads(seen[-1][2]) == {"j": 1}
        async with s.get(BASE + "/gd", data=b"raw"):
            pass
        assert seen[-1][2] == b"raw"
    rule(
        "data= together with json= (any non-None data, even '' or {}) raises ValueError "
        "('data and json parameters can not be used at the same time') before any request is "
        "sent: there is no precedence. None means absent. get()/request() take data=/json= the "
        "same way through **kwargs and send the body"
    )

    # async with changes nothing.
    opened = aiohttp.ClientSession()
    async with opened as entered:
        assert entered is opened
    assert aiohttp.ClientSession.__aenter__.__qualname__ == "ClientSession.__aenter__"
    s2 = aiohttp.ClientSession()
    try:
        async with s2.get(BASE + "/plain"):
            pass
    finally:
        await s2.close()
    plain = seen[-1]
    async with aiohttp.ClientSession() as s3, s3.get(BASE + "/plain") as resp:
        assert resp.status == 200
    assert seen[-1] == plain
    async with aiohttp.ClientSession() as s4:
        resp = await s4.get(BASE + "/awaited")  # a call may be awaited instead of entered
        assert resp.status == 200
        resp.release()
    assert seen[-1][:2] == ("GET", "/awaited")
    rule(
        "async with: `async with ClientSession() as s` binds the session itself (ClientSession."
        "__aenter__ returns self); `async with s.get(...) as r` and `await s.get(...)` send the same "
        "request; neither changes anything on the wire"
    )


asyncio.run(wire())

# 5. base_url join.
print("ClientSession._build_url source:\n" + inspect.getsource(aiohttp.ClientSession._build_url))
init_src = inspect.getsource(aiohttp.ClientSession.__init__)
start = init_src.index("if base_url is None or isinstance(base_url, URL)")
print(
    "ClientSession.__init__ base_url check:\n"
    + init_src[start : init_src.index("if timeout is sentinel", start)]
)

JOIN = [
    ("https://h.example/api/", "users", "https://h.example/api/users"),
    ("https://h.example/api/", "/users", "https://h.example/users"),
    ("https://h.example", "users", "https://h.example/users"),
    ("https://h.example", "/users", "https://h.example/users"),
    ("https://h.example/", "users", "https://h.example/users"),
    ("https://h.example/api/", "", "https://h.example/api/"),
    ("https://h.example/api/", "./x", "https://h.example/api/x"),
    ("https://h.example/api/", "../x", "https://h.example/x"),
    ("https://h.example/api/", "x?q=1", "https://h.example/api/x?q=1"),
    ("https://h.example/api/", "https://other.example/x", "https://other.example/x"),
]
rejected: list[tuple[str, str]] = []


async def joins() -> None:
    for base, path, want in JOIN:
        async with aiohttp.ClientSession(base_url=base) as s:
            got = str(s._build_url(path))
            assert got == want, (base, path, got, want)
        print(f"base_url={base!r} + {path!r} -> {want}")
    # '//host/x' has a host, so yarl calls it absolute: _build_url returns it unjoined, and with no
    # scheme the request itself cannot be made.
    async with aiohttp.ClientSession(base_url="https://h.example/api/") as s:
        got = str(s._build_url("//other.example/x"))
        assert got == "//other.example/x", got
        try:
            async with s.get("//other.example/x"):
                pass
        except AssertionError as err:
            # The library's own bare `assert port is not None` in aiohttp/connector.py.
            assert err.__traceback__ is not None
            assert inspect.getinnerframes(err.__traceback__)[-1].filename.endswith(
                "aiohttp/connector.py"
            ), "rejected somewhere other than the connector"
            print(f"get('//other.example/x') -> {type(err).__name__} from aiohttp/connector.py")
        else:
            raise SystemExit("probe failure: scheme-less host accepted")
    # What construction refuses.
    for bad, exc in (
        ("https://h.example/api", ValueError),  # path without a trailing '/'
        ("https://h.example/api?x=1", ValueError),
        ("/relative/", ValueError),  # not absolute: yarl "URL should be absolute"
        ("h.example/", ValueError),
    ):
        try:
            aiohttp.ClientSession(base_url=bad)
            raise AssertionError(f"accepted base_url {bad!r}")
        except exc as err:
            print(f"ClientSession(base_url={bad!r}) -> {type(err).__name__}: {err}")
    # A query on a slash-ended base is accepted at construction, and join drops it.
    async with aiohttp.ClientSession(base_url="https://h.example/api/?x=1") as s:
        got = str(s._build_url("users"))
        assert got == "https://h.example/api/users", got
        print(f"base_url='https://h.example/api/?x=1' + 'users' -> {got}")
    # base_url with a request that hits the wire.
    async with aiohttp.ClientSession(base_url=BASE) as s:
        async with s.get("/wire?q=1"):
            pass
        assert seen[-1][:2] == ("GET", "/wire?q=1")
    async with aiohttp.ClientSession(base_url=BASE + "/svc/") as s:
        async with s.post("items", json={}):
            pass
        assert seen[-1][:2] == ("POST", "/svc/items")
        async with s.post("/items", json={}):
            pass
        assert seen[-1][:2] == ("POST", "/items")
    # base_url as a keyword and as a yarl URL both work.
    async with aiohttp.ClientSession(BASE) as s:
        async with s.get("/pos"):
            pass
        assert seen[-1][:2] == ("GET", "/pos")


asyncio.run(joins())
rule(
    "aiohttp base_url join is RFC 3986 reference resolution (yarl URL.join), unlike httpx's append: "
    "a leading '/' RESETS to the host root (base 'https://h.example/api/' + '/users' -> "
    "'https://h.example/users'); a path without a leading '/' is appended to the base path "
    "('https://h.example/api/' + 'users' -> '.../api/users'); '//host/x' is NOT joined (it has a host) and the "
    "request then fails with a bare AssertionError raised by the connector's `assert port is not None` in aiohttp/connector.py (asserted by origin file); an absolute URL wins; '.'/'..' segments are normalised; an empty path gives the base itself"
)
rule(
    "ClientSession(base_url=...) raises at construction: ValueError('base_url must have a trailing "
    "'/'') when the URL path does not end in '/' ('https://h.example/api' is refused, "
    "'https://h.example' and 'https://h.example/api/' are fine); ValueError ('URL should be "
    "absolute', from yarl) when it is not an absolute URL. So a working base_url has the join "
    "semantics above with its path always ending in '/'"
)


async def no_base() -> None:
    async with aiohttp.ClientSession() as s:
        for rel in ("/relative", "relative"):
            try:
                async with s.get(rel):
                    pass
                raise AssertionError("relative url accepted")
            except aiohttp.InvalidURL as err:
                print(f"ClientSession().get({rel!r}) -> {type(err).__name__}: {err}")
    try:
        async with aiohttp.request("GET", "/relative"):
            pass
        raise AssertionError
    except aiohttp.InvalidURL as err:
        print(f"aiohttp.request('GET', '/relative') -> {type(err).__name__}")
    # host-only without scheme is also unusable.
    async with aiohttp.ClientSession() as s:
        try:
            async with s.get("h.example/x"):
                pass
            raise AssertionError
        except aiohttp.InvalidURL:
            pass


asyncio.run(no_base())
rule(
    "without base_url a relative URL ('/relative', 'relative', 'host/x') raises aiohttp.InvalidURL "
    "before any request is sent; aiohttp.request() has no base_url at all"
)
assert "base_url" not in params(aiohttp.request)

# ---------------------------------------------------------------- urllib3
# 6. Defining symbols.
assert urllib3.PoolManager is urllib3.poolmanager.PoolManager
assert urllib3.PoolManager.request.__qualname__ == "RequestMethods.request"
assert urllib3.PoolManager.request.__module__ == "urllib3._request_methods"
assert "request" not in vars(urllib3.PoolManager)
assert urllib3.PoolManager.__mro__[1] is urllib3._request_methods.RequestMethods
assert urllib3.request.__module__ == "urllib3"
assert sourcefile(urllib3.request) == "__init__.py"
assert callable(urllib3.PoolManager.request_encode_body)
assert callable(urllib3.PoolManager.request_encode_url) and callable(urllib3.PoolManager.urlopen)
assert urllib3.PoolManager.urlopen.__qualname__ == "PoolManager.urlopen"
rule(
    "owners: urllib3.PoolManager inherits request / request_encode_body / request_encode_url from "
    "urllib3._request_methods.RequestMethods (file urllib3/_request_methods.py; PoolManager does "
    "not define request itself); PoolManager.urlopen is its own; the module-level urllib3.request "
    "is defined in urllib3/__init__.py"
)
for v in VERBS:
    assert not hasattr(urllib3.PoolManager, v), v
    assert not hasattr(urllib3, v), v
rule("verb set: none: PoolManager and the module have request() only (no get/post/... helpers)")

assert positional(urllib3.PoolManager.request) == [
    "method",
    "url",
    "body",
    "fields",
    "headers",
    "json",
]
assert positional(urllib3.request) == ["method", "url"]
assert keyword_only(urllib3.request)[:3] == ["body", "fields", "headers"]
assert "json" in keyword_only(urllib3.request)
assert positional(urllib3.PoolManager.urlopen)[:2] == ["method", "url"]
assert positional(urllib3.PoolManager.request_encode_body)[:3] == ["method", "url", "fields"]
rule(
    "PoolManager.request(method, url, body, fields, headers, json, **urlopen_kw): method 0, url 1, "
    "body 2, fields 3, headers 4, json 5; urllib3.request(method, url, *, body, fields, headers, "
    "..., json): method 0, url 1, every other parameter keyword-only"
)
assert urllib3.PoolManager.__init__.__qualname__ == "PoolManager.__init__"
pm_opened = urllib3.PoolManager()
with pm_opened as entered:
    assert entered is pm_opened
assert urllib3.PoolManager.__enter__.__qualname__ == "PoolManager.__enter__"
rule("with PoolManager() as p: PoolManager.__enter__ returns the manager itself")

# 7. Wire.
http_ = urllib3.PoolManager()


def last() -> tuple[str, str, bytes, str]:
    return seen[-1]


http_.request("GET", BASE + "/g")
assert last()[:2] == ("GET", "/g")
http_.request("get", BASE + "/lower-g")
assert last()[:2] == ("GET", "/lower-g")
http_.request("post", BASE + "/lower-p", body=b"x")
assert last()[:2] == ("POST", "/lower-p")
http_.request(method="PATCH", url=BASE + "/kw")
assert last()[:2] == ("PATCH", "/kw")
urllib3.request("delete", BASE + "/lower-m")
assert last()[:2] == ("DELETE", "/lower-m")
urllib3.request("put", BASE + "/m", json={"k": 1})
assert last()[:2] == ("PUT", "/m") and json.loads(last()[2]) == {"k": 1}
rule(
    "request(method, url): `method = method.upper()` (quoted in the .md): a lower-case string is "
    "sent upper-cased on PoolManager.request and urllib3.request; method=/url= keywords the same"
)

http_.request("POST", BASE + "/j", json={"k": 1})
assert json.loads(last()[2]) == {"k": 1} and last()[3] == "application/json"
assert last()[2] == b'{"k":1}'
http_.request("POST", BASE + "/b", body=b"raw")
assert last()[2] == b"raw" and last()[3] == ""
http_.request("POST", BASE + "/bs", body="text")
assert last()[2] == b"text"
http_.request("POST", BASE + "/f", fields={"k": "v"})
assert "multipart/form-data" in last()[3] and b'name="k"' in last()[2]
http_.request("POST", BASE + "/n")
assert last()[2] == b"" and last()[3] == ""
rule(
    'wire (POST): json= sends compact JSON ({"k":1}) as application/json; body= sends exactly the '
    "bytes/str with NO Content-Type; fields= sends multipart/form-data; nothing sends no body"
)

# fields on the bodiless methods go to the URL; on others to a multipart body.
for verb in ("GET", "HEAD", "DELETE", "OPTIONS"):
    http_.request(verb, BASE + "/q", fields={"a": "1", "b": "2"})
    assert last()[:2] == (verb, "/q?a=1&b=2") and last()[2] == b"", verb
for verb in ("POST", "PUT", "PATCH"):
    http_.request(verb, BASE + "/q", fields={"a": "1"})
    assert last()[1] == "/q" and "multipart/form-data" in last()[3], verb
assert urllib3.PoolManager._encode_url_methods == {"DELETE", "GET", "HEAD", "OPTIONS"}
rule(
    "fields=: for DELETE/GET/HEAD/OPTIONS they are appended to the URL as a query string "
    "(RequestMethods._encode_url_methods), for every other method (POST/PUT/PATCH and unknown) "
    "they become a multipart/form-data body"
)
http_.request("GET", BASE + "/gj", json={"j": 1})
assert last()[:2] == ("GET", "/gj") and json.loads(last()[2]) == {"j": 1}
http_.request("DELETE", BASE + "/db", body=b"raw")
assert last()[2] == b"raw"
rule("json=/body= are sent on every method, GET and DELETE included")


# Combinations.
def rejects(msg: str, **kw: object) -> None:
    before = len(seen)
    try:
        http_.request("POST", BASE + "/x", **kw)  # type: ignore[arg-type]
    except TypeError as err:
        assert msg in str(err), str(err)
        assert len(seen) == before
        print(f"rejected {sorted(kw)} -> TypeError: {err}")
        return
    raise AssertionError(f"accepted {kw}")


rejects("both 'body' and 'json'", body=b"x", json={"j": 1})
rejects("both 'fields' and 'body'", body=b"x", fields={"a": "1"})
rejects("both 'fields' and 'body'", json={"j": 1}, fields={"a": "1"})
rejects("both 'body' and 'json'", body=b"x", json={"j": 1}, fields={"a": "1"})
# Falsy values behave as absent where the check tests truthiness / None.
http_.request("POST", BASE + "/ef", body=b"x", fields={})
assert last()[2] == b"x"
http_.request("POST", BASE + "/jf0", json={"j": 1}, fields={})
assert json.loads(last()[2]) == {"j": 1}
http_.request("POST", BASE + "/jn", json={"j": 1}, body=None)
assert json.loads(last()[2]) == {"j": 1}
try:
    http_.request("POST", BASE + "/je", json={}, body=b"x")
    raise AssertionError("json={} with body= accepted")
except TypeError:
    pass
# On GET the same body/json/fields rules apply: fields go to the URL so they do not clash.
http_.request("GET", BASE + "/gfb", body=b"x", fields={"a": "1"})
assert last()[:2] == ("GET", "/gfb?a=1") and last()[2] == b"x"
http_.request("GET", BASE + "/gfj", json={"j": 1}, fields={"a": "1"})
assert last()[:2] == ("GET", "/gfj?a=1") and json.loads(last()[2]) == {"j": 1}
rule(
    "combinations: body+json raises TypeError on every method; fields+body and fields+json raise "
    "TypeError on POST/PUT/PATCH (fields becomes the body) but are accepted on GET/HEAD/DELETE/"
    "OPTIONS (fields goes to the URL); body=None / json=None / an empty fields={} count as absent; "
    "json={} (not None) still clashes with body="
)
# Header interaction.
http_.request("POST", BASE + "/hj", json={"j": 1}, headers={"Content-Type": "text/x-custom"})
assert last()[3] == "text/x-custom"
http_.request("POST", BASE + "/hj2", json={"j": 1}, headers={"X-A": "1"})
assert last()[3] == "application/json"
http_.request("POST", BASE + "/hf", fields={"k": "v"}, headers={"Content-Type": "text/x-custom"})
assert last()[3] == "text/x-custom"
rule(
    "Content-Type: json= sets application/json unless the caller's headers name content-type "
    "(any case); fields= multipart also keeps a caller's Content-Type (setdefault); body= never sets one"
)

# 8. Module-level urllib3.request goes through one shared PoolManager.
assert type(urllib3._DEFAULT_POOL) is urllib3.PoolManager
urllib3.request("POST", BASE + "/mj", json={"k": 3})
assert json.loads(last()[2]) == {"k": 3}
urllib3.request("GET", BASE + "/mq", fields={"a": "1"})
assert last()[:2] == ("GET", "/mq?a=1")
try:
    urllib3.request("POST", BASE + "/mb", body=b"x", json={"j": 1})
    raise AssertionError
except TypeError:
    pass
try:
    urllib3.request("GET", "/relative")
    raise AssertionError
except urllib3.exceptions.LocationValueError as err:
    print("urllib3.request('GET', '/relative') ->", type(err).__name__, err)
rule(
    "urllib3.request delegates to a module-level PoolManager (urllib3._DEFAULT_POOL.request): the same "
    "body/json/fields rules; urllib3 has no base URL: a relative URL raises LocationValueError"
)
try:
    http_.request("GET", "/relative")
    raise AssertionError
except urllib3.exceptions.LocationValueError:
    pass
print("urllib3.request source (tail):\n" + inspect.getsource(urllib3.request)[-420:])
print("RequestMethods.request source (head):")
print(inspect.getsource(urllib3._request_methods.RequestMethods.request).split('"""')[2][:700])
print("OK")
