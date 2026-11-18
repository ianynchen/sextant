"""Pin the `requests` and `httpx` call rules the Python outbound catalog copies (plan 3, Task 0).

Run it inside the orders-fastapi fixture's own environment, never Sextant's:

    fixtures/orders-fastapi/.venv/bin/python -I scripts/probes/requests_httpx_rules.py

Every rule is asserted, then printed. Requests go to a local HTTP server so the path, method and
body that reach the wire are what the library actually sends. The probe runs the libraries on
purpose; Sextant itself never does (spec 7). Rules and quotes are in `requests_httpx_rules.md`.
"""

from __future__ import annotations

import asyncio
import http.server
import importlib.metadata
import inspect
import json
import threading

import httpx
import requests
import requests.api
import requests.sessions

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


print("versions:", {d: importlib.metadata.version(d) for d in ("requests", "httpx", "httpcore")})

# 1. Defining symbols (the owner module a call resolves to).
assert requests.get.__module__ == "requests.api" and requests.request.__module__ == "requests.api"
assert requests.Session.get.__module__ == "requests.sessions"
assert requests.Session.request.__module__ == "requests.sessions"
assert requests.Session is requests.sessions.Session


def sourcefile(obj: object) -> str:
    return inspect.getsourcefile(inspect.unwrap(obj)).rsplit("/", 1)[-1]  # type: ignore[arg-type]


# httpx rewrites __module__ of its public names to "httpx"; the defining file is the truth.
assert httpx.get.__module__ == "httpx" and sourcefile(httpx.get) == "_api.py"
assert sourcefile(httpx.request) == "_api.py" and sourcefile(httpx.stream) == "_api.py"
assert (
    sourcefile(httpx.Client.get) == "_client.py"
    and sourcefile(httpx.AsyncClient.get) == "_client.py"
)
assert (
    sourcefile(httpx.Client.__init__) == "_client.py"
    and sourcefile(httpx.AsyncClient.__init__) == "_client.py"
)
rule(
    "owners: requests.api.{request,get,...}; requests.sessions.Session.{request,get,...}; "
    "httpx._api.{request,get,...,stream} and httpx._client.{Client,AsyncClient}.{request,get,...,stream} "
    "by defining FILE (their __module__ reads 'httpx')"
)

# 2. Verb set.
for mod, name in ((requests.api, "requests.api"), (httpx._api, "httpx._api")):
    for v in VERBS | {"request"}:
        assert callable(getattr(mod, v)), (name, v)
for cls in (requests.Session, httpx.Client, httpx.AsyncClient):
    for v in VERBS | {"request"}:
        assert callable(getattr(cls, v)), (cls, v)
assert not hasattr(requests.api, "stream") and not hasattr(requests.Session, "stream")
assert hasattr(httpx._api, "stream") and hasattr(httpx.Client, "stream")
rule(
    f"verb methods on every surface: {sorted(VERBS)} plus request; httpx alone adds stream(method, url)"
)

# 3. url_arg positions.
for v in VERBS:
    assert positional(getattr(requests.api, v))[0] == "url", v
    assert positional(getattr(requests.Session, v))[0] == "url", v
    assert positional(getattr(httpx._api, v))[0] == "url", v
    assert positional(getattr(httpx.Client, v))[0] == "url", v
    assert positional(getattr(httpx.AsyncClient, v))[0] == "url", v
for fn in (
    requests.api.request,
    requests.Session.request,
    httpx._api.request,
    httpx.Client.request,
    httpx.AsyncClient.request,
    httpx._api.stream,
    httpx.Client.stream,
):
    assert positional(fn)[:2] == ["method", "url"], fn
rule("verb helpers: url is positional 0; request()/stream(): method positional 0, url positional 1")
# requests.get's second positional is params; requests.post's is data; httpx verbs take only url positionally.
assert positional(requests.api.get)[:2] == ["url", "params"]
assert positional(requests.api.post)[:2] == ["url", "data"] and positional(requests.api.put)[
    :2
] == ["url", "data"]
assert positional(requests.api.patch)[:2] == ["url", "data"]
assert positional(requests.api.delete) == ["url"] and positional(requests.api.head) == ["url"]
assert positional(httpx._api.get) == ["url"] and positional(httpx._api.post) == ["url"]
assert positional(httpx.Client.post) == ["url"]
rule(
    "requests.api: get(url, params), post(url, data, json), put/patch(url, data), others (url) only; httpx verbs: url only"
)

# 4. Keyword bodies.
for v in ("post", "put", "patch"):
    assert params(getattr(requests.api, v))[:2] == ["url", "data"], v
    assert params(getattr(requests.Session, v))[:2] == ["url", "data"], v
    assert ("json" in params(getattr(requests.api, v))[:3]) == (v == "post"), (
        v
    )  # put/patch: json= in **kwargs
    assert {"json", "data", "content", "files"} <= set(params(getattr(httpx._api, v))), v
    assert {"json", "data", "content", "files"} <= set(params(getattr(httpx.Client, v))), v
assert "content" not in params(requests.Session.request)
assert {"json", "data", "files"} <= set(params(requests.Session.request))
assert {"json", "data", "content", "files"} <= set(params(httpx._api.request))
assert {"json", "data", "content", "files"} <= set(params(httpx.Client.request))
for v in ("get", "head", "options", "delete"):  # httpx: no body keyword on the bodiless verbs
    for fn in (getattr(httpx._api, v), getattr(httpx.Client, v), getattr(httpx.AsyncClient, v)):
        assert not ({"json", "data", "content", "files"} & set(params(fn))), (v, fn)
assert "kwargs" in params(requests.api.get) and "kwargs" in params(requests.api.delete)
rule(
    "body keywords: requests post(url, data, json, **kwargs), put/patch(url, data, **kwargs) and request(method, url, **kwargs): "
    "json=/data=/files= and never content=; httpx: content=/data=/json=/files= (module, Client and "
    "AsyncClient post/put/patch/request; httpx get/head/options/delete take none)"
)
try:
    requests.post(BASE, content=b"x")
    raise AssertionError("requests accepted content=")
except TypeError as err:
    print("requests.post(content=) ->", err)

# 5. Wire behaviour of the same shapes.
requests.post(BASE + "/a", json={"k": 1})
assert (
    seen[-1][:2] == ("POST", "/a") and json.loads(seen[-1][2]) == {"k": 1} and "json" in seen[-1][3]
)
requests.post(BASE + "/b", data={"k": "v"})
assert seen[-1][2] == b"k=v" and "x-www-form-urlencoded" in seen[-1][3]
requests.request("PUT", BASE + "/c")
assert seen[-1][:2] == ("PUT", "/c")
requests.request(method="DELETE", url=BASE + "/d")
assert seen[-1][:2] == ("DELETE", "/d")
httpx.post(BASE + "/e", json={"k": 1})
assert seen[-1][:2] == ("POST", "/e") and json.loads(seen[-1][2]) == {"k": 1}
httpx.post(BASE + "/f", content=b"raw")
assert seen[-1][2] == b"raw"
httpx.request("PATCH", BASE + "/g")
assert seen[-1][:2] == ("PATCH", "/g")
with httpx.stream("GET", BASE + "/h"):
    pass
assert seen[-1][:2] == ("GET", "/h")
rule(
    "wire: requests json=/data=, httpx json=/content=, request(method, url) all reach the server as written"
)

# 5b. A verb written in lower case (plan 3 ruling R10): both libraries upper-case it.
requests.request("get", BASE + "/lower-r")
assert seen[-1][:2] == ("GET", "/lower-r")
requests.Session().request("patch", BASE + "/lower-s")
assert seen[-1][:2] == ("PATCH", "/lower-s")
httpx.request("get", BASE + "/lower-x")
assert seen[-1][:2] == ("GET", "/lower-x")
httpx.Client().request("delete", BASE + "/lower-c")
assert seen[-1][:2] == ("DELETE", "/lower-c")
rule(
    "request(method, url): the method string is upper-cased by both libraries ('get' is sent as GET)"
)

# 5c. Several body keywords on one call (plan 3 ruling R11): which one becomes the body.
requests.post(BASE + "/rj", json={"j": 1}, data={"d": "v"})
assert seen[-1][2] == b"d=v" and "x-www-form-urlencoded" in seen[-1][3]
requests.post(BASE + "/rf", json={"j": 1}, data={"d": "v"}, files={"f": b"x"})
assert "multipart/form-data" in seen[-1][3] and b'name="d"' in seen[-1][2]
assert b'name="f"' in seen[-1][2] and b'"j"' not in seen[-1][2]
requests.post(BASE + "/re", json={"j": 1}, data={})
assert json.loads(seen[-1][2]) == {"j": 1}
httpx.post(BASE + "/xj", json={"j": 1}, data={"d": "v"})
assert seen[-1][2] == b"d=v" and "x-www-form-urlencoded" in seen[-1][3]
httpx.post(BASE + "/xc", json={"j": 1}, data={"d": "v"}, content=b"raw")
assert seen[-1][2] == b"raw"
httpx.post(BASE + "/xf", json={"j": 1}, data={"d": "v"}, files={"f": b"x"})
assert "multipart/form-data" in seen[-1][3] and b'name="d"' in seen[-1][2]
assert b'name="f"' in seen[-1][2] and b'"j"' not in seen[-1][2]
httpx.post(BASE + "/xe", json={"j": 1}, data={})
assert json.loads(seen[-1][2]) == {"j": 1}
requests.post(BASE + "/rn")
assert seen[-1][2] == b""
httpx.post(BASE + "/xn")
assert seen[-1][2] == b""
rule(
    "several body keywords: requests files > data > json (data= and files= go together as multipart); "
    "httpx content > files > data > json (the same multipart rule); an empty data= gives way to json=; "
    "a call with no body keyword sends no body"
)
assert positional(requests.Session.request)[:7] == [
    "method",
    "url",
    "params",
    "data",
    "headers",
    "cookies",
    "files",
]
assert positional(requests.Session.request)[15] == "json"
assert positional(requests.api.request) == ["method", "url"]
assert positional(requests.api.post)[:3] == ["url", "data", "json"]
rule(
    "body positions: requests post(url, data, json): data 1, json 2; put/patch(url, data): data 1; "
    "Session.request: data 3, files 6, json 15; requests.request(method, url, **kwargs): none"
)

# 5d. A client opened by `with` / `async with` is the client itself (plan 3 ruling R13).
for cls, name in ((httpx.Client, "__enter__"), (requests.sessions.Session, "__enter__")):
    assert getattr(cls, name).__qualname__ == f"{cls.__name__}.{name}", (cls, name)
    opened = cls()
    with opened as entered:
        assert entered is opened, cls
assert httpx.AsyncClient.__aenter__.__qualname__ == "AsyncClient.__aenter__"
assert not hasattr(requests.sessions.Session, "__aenter__")


async def _entered() -> bool:
    opened = httpx.AsyncClient()
    async with opened as entered:
        return entered is opened


assert asyncio.run(_entered())
rule(
    "with/async with: httpx.Client.__enter__, httpx.AsyncClient.__aenter__ and "
    "requests.sessions.Session.__enter__ (each defined on that class) return the client itself; "
    "Session has no __aenter__"
)

# 6. requests.Session has no base URL.
s = requests.Session()
assert not hasattr(s, "base_url")
try:
    requests.Session(base_url=BASE)  # type: ignore[call-arg]
    raise AssertionError("Session took base_url")
except TypeError as err:
    print("requests.Session(base_url=) ->", err)
try:
    s.get("/relative")
    raise AssertionError("relative url accepted")
except requests.exceptions.MissingSchema as err:
    print("Session.get('/relative') ->", err)
s.get(BASE + "/s")
assert seen[-1][:2] == ("GET", "/s")
rule(
    "requests.Session has no base URL: a relative path raises MissingSchema; every url is absolute"
)

# 7. httpx base_url join.
print("httpx _merge_url source:\n" + inspect.getsource(httpx.Client._merge_url))
cases = [
    ("https://h.example/api", "/users", "https://h.example/api/users"),
    ("https://h.example/api", "users", "https://h.example/api/users"),
    ("https://h.example/api/", "/users", "https://h.example/api/users"),
    ("https://h.example", "/users", "https://h.example/users"),
    ("https://h.example/api", "", "https://h.example/api/"),
    ("https://h.example/api", "https://other.example/x", "https://other.example/x"),
    (
        "https://h.example/api",
        "//other.example/x",
        "https://h.example/api/x",
    ),  # scheme-less: host dropped
    ("https://h.example/api", "./x", "https://h.example/api/x"),
    ("https://h.example/api", "x?q=1", "https://h.example/api/x?q=1"),
    ("https://h.example/api", "../x", "https://h.example/x"),
]
for base, path, want in cases:
    for cls in (httpx.Client, httpx.AsyncClient):
        got = str(cls(base_url=base).build_request("GET", path).url)
        assert got == want, (cls.__name__, base, path, got, want)
    print(f"base_url={base!r} + {path!r} -> {want}")
assert str(httpx.Client(base_url="https://h.example/api").base_url) == "https://h.example/api/"
assert str(httpx.Client(base_url="https://h.example").base_url) == "https://h.example"
rule(
    "httpx base_url: trailing slash forced; a relative path has its leading '/' stripped and is APPENDED "
    "to base_url's path; an absolute URL ignores base_url; no base_url -> relative path unusable"
)
try:
    httpx.Client().get("/x")
    raise AssertionError
except httpx.UnsupportedProtocol as err:
    print("httpx.Client().get('/x') ->", err)
print("OK")
