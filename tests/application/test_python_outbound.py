"""Outbound HTTP calls of `requests` and `httpx` are `single_call` rows (plan 3 Task 2; rulings
R8-R12; Review Focus 2 and 3).

Each test writes a small program, scans it with the real Python scanner against the requests
2.34.2 and httpx 0.28.1 that `fixtures/orders-fastapi` locks, and runs the real pipeline with
the shipped catalogs (`test_fastapi_routes._resolved`). The rules are the libraries' own,
measured in `scripts/probes/requests_httpx_rules.md`.
"""

import json
from pathlib import Path

import pytest
from test_fastapi_routes import _LOCKED, _bare, _resolved

from fixture_python import FIXTURES
from sextant.application.ports.catalogs import CatalogError
from sextant.application.ports.detector import LibraryRoot
from sextant.application.resolve import values
from sextant.application.resolve.engines import single_call
from sextant.application.resolve.shapes.client_base import APPEND_TO_BASE, join_url
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_CLIENTS = {
    **_LOCKED,
    "requests": "2.34.2",
    "httpx": "0.28.1",
    "httpcore": "1.0.9",
    "anyio": "4.16.0",
    "certifi": "2026.10.23",
    "idna": "3.20",
    "urllib3": "2.8.0",
    "charset-normalizer": "3.5.2",
    "aiohttp": "3.14.5",
    "yarl": "1.25.1",
    "multidict": "7.2.1",
    "aiohappyeyeballs": "2.7.1",
    "aiosignal": "1.4.0",
    "attrs": "26.1.0",
    "frozenlist": "1.8.0",
    "propcache": "0.5.4",
}

_MODELS = (
    "from pydantic import BaseModel, ConfigDict\n"
    "from pydantic.alias_generators import to_camel\n"
    "class Order(BaseModel):\n"
    "    model_config = ConfigDict(alias_generator=to_camel)\n"
    "    order_id: int\n"
)


@pytest.fixture(scope="module")
def libraries(orders_fastapi_env: Path) -> tuple[LibraryRoot, ...]:
    (site,) = (FIXTURES / "orders-fastapi" / ".venv" / "lib").glob("python*/site-packages")
    return tuple(LibraryRoot(name, version, site) for name, version in _CLIENTS.items())


def _outbound(tmp_path: Path, libraries, main: str) -> list[tuple[object, ...]]:
    """Each outbound row of a program whose `app/main.py` is `main`: (method, peer, path,
    caller, resolution, the shape its body names or its wire type)."""
    workspace = _resolved(
        tmp_path, libraries, {"main.py": main, "models.py": _MODELS}, locked=_CLIENTS
    )
    rows = []
    for row in workspace.query("endpoints"):
        if row["direction"] != "outbound":
            continue
        body = None if row["request_shape"] is None else json.loads(row["request_shape"])
        rows.append(
            (
                row["method"],
                row["peer"],
                row["path"],
                str(_bare(row["caller"])).split("(")[0],
                row["resolution"],
                None if body is None else body.get("shape_id") or body["wire_type"],
            )
        )
    workspace.close()
    return sorted(rows, key=repr)


# --- The owner ------------------------------------------------------------------------------


@pytest.mark.declines("requests")
@pytest.mark.declines("httpx")
@pytest.mark.declines("aiohttp")
@pytest.mark.declines("urllib3")
@pytest.mark.pins("single_call.call-site-owner")
def test_a_get_on_anything_but_requests_or_httpx_derives_nothing(tmp_path, libraries):
    """`get`, `post` and `request` are common names: a dict's `get` and a module class with
    the libraries' own method names (`ClientSession` among them) are calls on no `requests` or `httpx` owner."""
    assert (
        _outbound(
            tmp_path,
            libraries,
            "class ClientSession:\n"
            "    def get(self, url: str) -> None: ...\n"
            "class Client:\n"
            "    def get(self, url: str) -> None: ...\n"
            "    def request(self, method: str, url: str) -> None: ...\n"
            "def send(cache: dict[str, str]) -> None:\n"
            "    ClientSession().get('https://a.example/w')\n"
            "    Client().get('https://a.example/x')\n"
            "    Client().request('GET', 'https://a.example/y')\n"
            "    cache.get('https://a.example/z')\n",
        )
        == []
    )


# --- Review Focus 2: the verb ------------------------------------------------------------------


def test_a_verb_held_in_a_variable_is_null_and_the_row_unresolved(tmp_path, libraries):
    assert _outbound(
        tmp_path,
        libraries,
        "import httpx\n"
        "import requests\n"
        "def send(method: str) -> None:\n"
        "    requests.request(method, 'https://a.example/x')\n"
        "    httpx.request(method, 'https://b.example/y')\n",
    ) == [
        (None, "a.example", "/x", "app/main#send", "unresolved", None),
        (None, "b.example", "/y", "app/main#send", "unresolved", None),
    ]


def test_a_verb_written_as_text_is_sent_upper_cased(tmp_path, libraries):
    """Probe "Verb case": both libraries upper-case the method string (ruling R10)."""
    assert _outbound(
        tmp_path,
        libraries,
        "import httpx\n"
        "import requests\n"
        "def send() -> None:\n"
        "    requests.request('get', 'https://a.example/x')\n"
        "    requests.Session().request(method='patch', url='https://a.example/y')\n"
        "    httpx.Client().request('DELETE', 'https://b.example/z')\n",
    ) == [
        ("DELETE", "b.example", "/z", "app/main#send", "resolved", None),
        ("GET", "a.example", "/x", "app/main#send", "resolved", None),
        ("PATCH", "a.example", "/y", "app/main#send", "resolved", None),
    ]


# --- Review Focus 3: a relative address and the client's base ----------------------------------


def test_a_relative_address_with_no_base_keeps_its_path_and_names_no_peer(tmp_path, libraries):
    """A client handed in by a caller nothing reads, a client built without `base_url`, and a
    module function: httpx refuses each relative address (`UnsupportedProtocol`), so no host is
    invented and none is `resolved`."""
    assert _outbound(
        tmp_path,
        libraries,
        "import httpx\n"
        "def given(client: httpx.Client) -> None:\n"
        "    client.get('/status')\n"
        "def bare() -> None:\n"
        "    httpx.Client().get('/health')\n"
        "def module() -> None:\n"
        "    httpx.get('/ping')\n",
    ) == [
        ("GET", None, "/health", "app/main#bare", "unresolved", None),
        ("GET", None, "/ping", "app/main#module", "unresolved", None),
        ("GET", None, "/status", "app/main#given", "unresolved", None),
    ]


def test_a_relative_address_joins_the_base_the_client_was_built_with(tmp_path, libraries):
    """`base_url` read off the construction (an argument rung), the client found through a
    module variable, an instance field the scanner gave no type (its owner from the settled
    binding, ruling R9) and an `async` client; an absolute address ignores the base."""
    assert _outbound(
        tmp_path,
        libraries,
        "import httpx\n"
        "api = httpx.Client(base_url='https://api.example/v1')\n"
        "def listed() -> None:\n"
        "    api.get('/orders')\n"
        "    api.get('https://other.example/x')\n"
        "class Slack:\n"
        "    def __init__(self) -> None:\n"
        "        self.client = httpx.AsyncClient(base_url='https://slack.example/api/')\n"
        "    async def post(self) -> None:\n"
        "        await self.client.post('chat.postMessage')\n",
    ) == [
        ("GET", "api.example", "/v1/orders", "app/main#listed", "resolved", None),
        ("GET", "other.example", "/x", "app/main#listed", "resolved", None),
        ("POST", "slack.example", "/api/chat.postMessage", "app/main/Slack#post", "resolved", None),
    ]


def test_a_client_subclass_joins_the_base_its_construction_was_handed(tmp_path, libraries):
    """OI-525: `Api(httpx.Client)` defines no `__init__`, so `Api(base_url=...)` runs
    `Client.__init__`: the construction is the declared rung's (`Dispatch.heirs`), and a
    relative address joins its base. (Through `with … as`, the call on the name is not bound
    to the class yet: OI-525 stays open for it.)"""
    assert _outbound(
        tmp_path,
        libraries,
        "import httpx\n"
        "class Api(httpx.Client):\n"
        "    pass\n"
        "def listed() -> None:\n"
        "    Api(base_url='https://a.example/v1').get('/w')\n",
    ) == [("GET", "a.example", "/v1/w", "app/main#listed", "resolved", None)]


def test_a_client_a_with_statement_opens_is_the_client_it_built(tmp_path, libraries):
    """Plan 3 R13: `Client.__enter__`, `AsyncClient.__aenter__` and `Session.__enter__` return
    the client itself (`value-models/python-clients.yml`), so the name `with … as` binds is
    that client: its owner, and its base, are the construction's."""
    assert _outbound(
        tmp_path,
        libraries,
        "import httpx\n"
        "import requests\n"
        "def sync() -> None:\n"
        "    with httpx.Client(base_url='https://a.example/v1') as client:\n"
        "        client.get('/x')\n"
        "async def run() -> None:\n"
        "    async with httpx.AsyncClient(base_url='https://b.example') as client:\n"
        "        await client.post('/y')\n"
        "def session() -> None:\n"
        "    with requests.Session() as http:\n"
        "        http.delete('https://c.example/z')\n",
    ) == [
        ("DELETE", "c.example", "/z", "app/main#session", "resolved", None),
        ("GET", "a.example", "/v1/x", "app/main#sync", "resolved", None),
        ("POST", "b.example", "/y", "app/main#run", "resolved", None),
    ]


def test_a_with_statement_on_a_client_subclass_is_the_client_it_built(tmp_path, libraries):
    """The `__enter__` entry is on `httpx.Client`; a subclass that does not define its own
    `__enter__` inherits it, so the name `with … as` binds is the subclass instance (plan
    2026-11-23-python-django-redesign, Task 5: a stated call matches on ancestors). A
    subclass that defines its own `__enter__` runs that body, which is followed."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": "import httpx\n"
            "class Api(httpx.Client):\n"
            "    pass\n"
            "class Own(httpx.Client):\n"
            "    def __enter__(self) -> str:\n"
            "        return 'own'\n"
            "def sink(x: object) -> None: ...\n"
            "def run(client: Api, own: Own) -> None:\n"
            "    with client as c:\n"
            "        sink(c)\n"
            "    with own as o:\n"
            "        sink(o)\n"
            "def main() -> None:\n"
            "    run(Api(), Own())\n",
            "models.py": _MODELS,
        },
        locked=_CLIENTS,
    )
    index = values.value_index(
        workspace, returns_arguments=YamlCatalogSource(catalogs_dir()).returns_arguments()
    )
    sites = sorted(
        (row for row in workspace.query("call_sites") if row["name"] == "sink"),
        key=lambda row: row["ordinal"],
    )
    sunk = [
        [b.slots[0].value for b in values.resolve_site(workspace, dict(row), index)]
        for row in sites
    ]
    workspace.close()
    assert sunk == [["app/main/Api#"], ["own"]]


def test_an_unbound_call_through_a_client_subclass_is_its_first_argument(tmp_path, libraries):
    """OI-522: `Api.__enter__(client)` calls `httpx.Client.__enter__`, a method that takes
    `self`, through the class: its receiver is the first argument, the instance, never the
    class `Api`."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": "import httpx\n"
            "class Api(httpx.Client):\n"
            "    pass\n"
            "def sink(x: object) -> None: ...\n"
            "def run(client: Api) -> None:\n"
            "    sink(Api.__enter__(client))\n"
            "def main() -> None:\n"
            "    run(Api())\n",
            "models.py": _MODELS,
        },
        locked=_CLIENTS,
    )
    index = values.value_index(
        workspace, returns_arguments=YamlCatalogSource(catalogs_dir()).returns_arguments()
    )
    (site,) = (row for row in workspace.query("call_sites") if row["name"] == "sink")
    sunk = [
        (b.slots[0].value, b.slots[0].class_object)
        for b in values.resolve_site(workspace, dict(site), index)
    ]
    workspace.close()
    assert sunk == [("app/main/Api#", False)]


@pytest.mark.parametrize(
    ("base", "path", "sent"),
    [
        # Every row of the probe's table ("base_url").
        ("https://h.example/api", "/users", "https://h.example/api/users"),
        ("https://h.example/api", "users", "https://h.example/api/users"),
        ("https://h.example/api/", "/users", "https://h.example/api/users"),
        ("https://h.example", "/users", "https://h.example/users"),
        ("https://h.example/api", "", "https://h.example/api/"),
        ("https://h.example/api", "//other.example/x", "https://h.example/api/x"),
        ("https://h.example/api", "./x", "https://h.example/api/x"),
        ("https://h.example/api", "x?q=1", "https://h.example/api/x?q=1"),
        ("https://h.example/api", "../x", "https://h.example/x"),
        # Not measured: declined.
        ("https://h.example/api", "x#frag", None),
        ("https://h.example/api", "///x", None),
        ("https://h.example/api?k=1", "x", None),
        ("https://h.example/api", "mailto:x", None),
    ],
)
def test_append_to_base_is_httpx_merge_url(base, path, sent):
    assert join_url(base, path, APPEND_TO_BASE) == sent


# --- The body ---------------------------------------------------------------------------------


def test_a_serialised_model_is_the_body_only_with_its_wire_names(tmp_path, libraries):
    """`model_dump(by_alias=True)` writes the shape's wire names; `model_dump()` writes the
    fields' own names (`order_id`, not `orderId`), so that body is not described (N4). The
    `json=` of `requests.put` reaches it through `**kwargs` (ruling R2)."""
    assert _outbound(
        tmp_path,
        libraries,
        "import requests\n"
        "from app.models import Order\n"
        "def wire(order: Order) -> None:\n"
        "    requests.put('https://a.example/w', json=order.model_dump(by_alias=True))\n"
        "def own(order: Order) -> None:\n"
        "    requests.put('https://a.example/o', json=order.model_dump())\n",
    ) == [
        ("PUT", "a.example", "/o", "app/main#own", "unresolved", None),
        ("PUT", "a.example", "/w", "app/main#wire", "resolved", "app/models/Order#"),
    ]


def test_the_body_is_the_first_keyword_in_the_library_precedence(tmp_path, libraries):
    """Probe "Several body keywords": requests sends `data=` over `json=`; httpx `content=` over
    both. A call writing no body keyword has no body, and its row is not marked down for it."""
    assert _outbound(
        tmp_path,
        libraries,
        "import httpx\n"
        "import requests\n"
        "from app.models import Order\n"
        "def form(order: Order, raw: str) -> None:\n"
        "    requests.post('https://a.example/f', json=order.model_dump(by_alias=True), data=raw)\n"
        "    httpx.post('https://b.example/c', json=order.model_dump(by_alias=True), content='x')\n"
        "def empty() -> None:\n"
        "    requests.post('https://a.example/e')\n"
        "    httpx.post('https://b.example/e')\n",
    ) == [
        ("POST", "a.example", "/e", "app/main#empty", "resolved", None),
        ("POST", "a.example", "/f", "app/main#form", "resolved", "string"),
        ("POST", "b.example", "/c", "app/main#form", "resolved", "string"),
        ("POST", "b.example", "/e", "app/main#empty", "resolved", None),
    ]


# --- aiohttp ---------------------------------------------------------------------------------
# Every rule is aiohttp's own, measured in `scripts/probes/aiohttp_urllib3_rules.md`.


def test_aiohttp_relative_address_joins_the_session_base_by_rfc_3986(tmp_path, libraries):
    """Probe "aiohttp `base_url`": a relative path appends to a base ending in `/`, a leading `/`
    resets to the host root, and an absolute address ignores the base; `async with` binds the
    session itself."""
    assert _outbound(
        tmp_path,
        libraries,
        "import aiohttp\n"
        "async def run() -> None:\n"
        "    async with aiohttp.ClientSession(base_url='https://api.example/v1/') as s:\n"
        "        await s.get('orders')\n"
        "        await s.get('/health')\n"
        "        await s.get('https://other.example/x')\n",
    ) == [
        ("GET", "api.example", "/health", "app/main#run", "resolved", None),
        ("GET", "api.example", "/v1/orders", "app/main#run", "resolved", None),
        ("GET", "other.example", "/x", "app/main#run", "resolved", None),
    ]


def test_aiohttp_relative_address_without_a_base_names_no_peer(tmp_path, libraries):
    """Probe "Without `base_url`": aiohttp raises `InvalidURL` on a relative address, from a
    session with no base and from `aiohttp.request` (which has no base). The row keeps its path,
    names no peer and stays unresolved."""
    assert _outbound(
        tmp_path,
        libraries,
        "import aiohttp\n"
        "async def run() -> None:\n"
        "    async with aiohttp.ClientSession() as s:\n"
        "        await s.get('/health')\n"
        "    await aiohttp.request('GET', '/ping')\n",
    ) == [
        ("GET", None, "/health", "app/main#run", "unresolved", None),
        ("GET", None, "/ping", "app/main#run", "unresolved", None),
    ]


def test_aiohttp_verb_in_a_variable_is_null_and_text_is_upper_cased(tmp_path, libraries):
    """Probe "Verb case": `request(method, url)` upper-cases the string; a variable claims no
    verb."""
    assert _outbound(
        tmp_path,
        libraries,
        "import aiohttp\n"
        "async def send(method: str) -> None:\n"
        "    async with aiohttp.ClientSession() as s:\n"
        "        await s.request(method, 'https://a.example/x')\n"
        "        await s.request('patch', 'https://a.example/y')\n"
        "    await aiohttp.request('delete', 'https://a.example/z')\n",
    ) == [
        ("DELETE", "a.example", "/z", "app/main#send", "resolved", None),
        ("PATCH", "a.example", "/y", "app/main#send", "resolved", None),
        (None, "a.example", "/x", "app/main#send", "unresolved", None),
    ]


def test_aiohttp_json_body_takes_its_fields_from_the_serialiser(tmp_path, libraries):
    """The body is the pydantic serialiser's wire names (`by_alias=True`); `model_dump()` writes
    the fields' own names, so that body is not described (N4)."""
    assert _outbound(
        tmp_path,
        libraries,
        "import aiohttp\n"
        "from app.models import Order\n"
        "async def send(order: Order) -> None:\n"
        "    async with aiohttp.ClientSession() as s:\n"
        "        await s.post('https://a.example/w', json=order.model_dump(by_alias=True))\n"
        "        await s.post('https://a.example/o', json=order.model_dump())\n",
    ) == [
        ("POST", "a.example", "/o", "app/main#send", "unresolved", None),
        ("POST", "a.example", "/w", "app/main#send", "resolved", "app/models/Order#"),
    ]


@pytest.mark.xfail(
    strict=True,
    reason="`body_arg` has no word for 'these keywords together are rejected'; the call, which "
    "never runs, publishes the `data=` body. Needs new vocabulary, so it is logged, not built.",
)
def test_aiohttp_data_with_json_publishes_no_body(tmp_path, libraries):
    """Probe "aiohttp bodies": `data=` with `json=` raises `ValueError` before anything is sent,
    so no body is claimed for it."""
    assert _outbound(
        tmp_path,
        libraries,
        "import aiohttp\n"
        "from app.models import Order\n"
        "async def send(order: Order, raw: str) -> None:\n"
        "    async with aiohttp.ClientSession() as s:\n"
        "        await s.post('https://a.example/b', data=raw, json=order.model_dump(by_alias=True))\n",
    ) == [("POST", "a.example", "/b", "app/main#send", "unresolved", None)]


# --- urllib3 ---------------------------------------------------------------------------------
# Every rule is urllib3's own, measured in `scripts/probes/aiohttp_urllib3_rules.md`. It has no
# verb helpers and no base URL: every address is absolute.


def test_urllib3_request_reads_the_verb_and_the_absolute_address(tmp_path, libraries):
    """Probe "Verbs and positions": `request(method, url)`, on the module and on a
    `PoolManager` (defined on `RequestMethods`); text is upper-cased, a variable claims no verb."""
    assert _outbound(
        tmp_path,
        libraries,
        "import urllib3\n"
        "def run(method: str) -> None:\n"
        "    urllib3.request('GET', 'https://a.example/x')\n"
        "    urllib3.request(method, 'https://a.example/v')\n"
        "    with urllib3.PoolManager() as pool:\n"
        "        pool.request('delete', 'https://b.example/y')\n"
        "    urllib3.PoolManager().request('POST', 'https://c.example/z')\n",
    ) == [
        ("DELETE", "b.example", "/y", "app/main#run", "resolved", None),
        ("GET", "a.example", "/x", "app/main#run", "resolved", None),
        ("POST", "c.example", "/z", "app/main#run", "resolved", None),
        (None, "a.example", "/v", "app/main#run", "unresolved", None),
    ]


def test_urllib3_body_is_body_or_json_by_keyword(tmp_path, libraries):
    """Probe "urllib3 bodies": `json=` and `body=` are sent on every verb; `fields=` is not a
    model and is not read."""
    assert _outbound(
        tmp_path,
        libraries,
        "import urllib3\n"
        "from app.models import Order\n"
        "def send(order: Order) -> None:\n"
        "    urllib3.request('POST', 'https://a.example/w', json=order.model_dump(by_alias=True))\n"
        "    urllib3.request('PUT', 'https://a.example/o', json=order.model_dump())\n"
        "    urllib3.request('GET', 'https://a.example/q', fields={'a': '1'})\n",
    ) == [
        ("GET", "a.example", "/q", "app/main#send", "resolved", None),
        ("POST", "a.example", "/w", "app/main#send", "resolved", "app/models/Order#"),
        ("PUT", "a.example", "/o", "app/main#send", "unresolved", None),
    ]


@pytest.mark.xfail(
    strict=True,
    reason="`body_arg` has no word for 'these keywords together are rejected'; the call, which "
    "never runs (`TypeError`), publishes the `body=` body. Needs new vocabulary, so it is "
    "logged, not built.",
)
def test_urllib3_body_with_json_publishes_no_body(tmp_path, libraries):
    """Probe "urllib3 bodies": `body=` with `json=` raises `TypeError` on every verb, so no
    body is claimed for it."""
    assert _outbound(
        tmp_path,
        libraries,
        "import urllib3\n"
        "from app.models import Order\n"
        "def send(order: Order, raw: dict[str, str]) -> None:\n"
        "    urllib3.request('POST', 'https://a.example/b', body=order.model_dump(by_alias=True), json=raw)\n",
    ) == [("POST", "a.example", "/b", "app/main#send", "unresolved", None)]


# --- The owner a binding gives ----------------------------------------------------------------


def test_an_unowned_call_is_read_on_its_bound_owner_only_where_every_path_agrees(
    tmp_path, libraries
):
    """Ruling R9: `fetch`'s `client` has no annotation, so its call names no owner; the binding
    reads one per caller. Two callers handing two clients leave it unowned (no row); callers
    agreeing on one make it a call on that client."""
    fetch = "def fetch(client) -> None:\n    client.get('https://a.example/x')\n"
    assert (
        _outbound(
            tmp_path / "two",
            libraries,
            "import httpx\nimport requests\n"
            + fetch
            + "def a() -> None:\n    fetch(requests.Session())\n"
            + "def b() -> None:\n    fetch(httpx.Client())\n",
        )
        == []
    )
    assert _outbound(
        tmp_path / "one",
        libraries,
        "import httpx\n"
        + fetch
        + "def b() -> None:\n    fetch(httpx.Client())\n"
        + "def c() -> None:\n    fetch(httpx.Client(timeout=3))\n",
    ) == [("GET", "a.example", "/x", "app/main#fetch", "resolved", None)]


# --- The catalog words ------------------------------------------------------------------------


def _catalog(tmp_path: Path, name: str, text: str) -> Path:
    directory = tmp_path / "catalogs"
    directory.mkdir()
    for shipped in catalogs_dir().iterdir():
        if shipped.is_dir():
            (directory / shipped.name).symlink_to(shipped)
    (directory / name).write_text(text, encoding="utf-8")
    return directory


_HEAD = (
    "id: probe\nstyle: single_call\nprotocol: http\ndirection: outbound\n"
    "detect: { coordinates: [] }\nmatches:\n  owner: httpx._client.Client\n"
)


@pytest.mark.parametrize(
    ("text", "refusal"),
    [
        (
            _HEAD + "  client_base:\n    client_arg: receiver\n    ladder:\n"
            "      - { owner: httpx._client.Client, method: <init>, base_arg: { keyword: base_url } }\n"
            "      - { owner: x.Y, method: build, block_arg: 0 }\n"
            "    join: append_to_base\n"
            "  methods:\n    - { name: get, http_method: GET, url_arg: 0 }\n",
            "one ladder is one shape",
        ),
        (
            _HEAD + "  client_base:\n    client_arg: receiver\n    ladder:\n"
            "      - { owner: httpx._client.Client, method: <init>, base_arg: { keyword: base_url } }\n"
            "    join: fill_authority\n"
            "  methods:\n    - { name: get, http_method: GET, url_arg: 0 }\n",
            "`join` is one of",
        ),
        (
            _HEAD
            + "  methods:\n    - { name: get, http_method: GET, url_arg: 0, method_case: upper }\n",
            "`method_case",
        ),
        (
            _HEAD
            + "  methods:\n    - { name: post, http_method: POST, url_arg: 0, body_arg: [] }\n",
            "a list of argument references",
        ),
    ],
)
def test_a_broken_word_is_refused_naming_the_file(tmp_path, text, refusal):
    catalogs = _catalog(tmp_path, "probe.yml", text)
    """Refused at load, or by the engine before it reads a call site (`_validate_*`)."""
    with pytest.raises(CatalogError, match=refusal):
        (probe,) = [one for one in YamlCatalogSource(catalogs).load() if one.id == "probe"]
        single_call.run(DuckDbWorkspace(tmp_path / "ws.duckdb"), probe)


def test_a_session_subclass_publishes_only_the_modules_own_calls(tmp_path, libraries):
    """`class Outgoing(requests.Session)`: `Session`'s bodies are read (a module class extends
    it, fact schema 22), and its own `self.request("GET", url)` inside `Session.get` is the
    library's call, never this module's row (F4 §5.2, `drop_borrowed_endpoints.sql`). The
    module's call is its one row."""
    rows = _outbound(
        tmp_path,
        libraries,
        "import requests\n"
        "class Outgoing(requests.Session):\n    pass\n"
        "def send() -> None:\n"
        "    Outgoing().get('https://a.example/w')\n",
    )

    assert rows == [("GET", "a.example", "/w", "app/main#send", "resolved", None)]
