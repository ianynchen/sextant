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
@pytest.mark.pins("single_call.call-site-owner")
def test_a_get_on_anything_but_requests_or_httpx_derives_nothing(tmp_path, libraries):
    """`get`, `post` and `request` are common names: a dict's `get` and a module class with
    the libraries' own method names are calls on no `requests` or `httpx` owner."""
    assert (
        _outbound(
            tmp_path,
            libraries,
            "class Client:\n"
            "    def get(self, url: str) -> None: ...\n"
            "    def request(self, method: str, url: str) -> None: ...\n"
            "def send(cache: dict[str, str]) -> None:\n"
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
