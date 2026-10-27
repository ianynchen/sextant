"""A client's base address (spec 2026-10-26 §3c, §3g items 1-3): Ktor's `defaultRequest`
join, and the `client_base` catalog key that declares where a client's base is set.

Two halves, each measured by CP-54 (`scripts/probes/cp54_ktor_client_ws_sse.md`):

- **The join** (row group (g), rows 51-60): what Ktor's own `DefaultRequest` sent for a base
  and a relative address, run over a mock engine. `join_url` must give the same string for
  every row, one assertion each (DR-6: mirror the framework, never our own rule).
- **The ladder** (row groups (e), rows 46-49, and (i), rows 79-80): the calls a base is set
  through, declared as catalog data and refused at load where malformed. Reading a client's
  construction through it waits on the value walk, which answers what a value is and not which
  call built it, and on a write fact for a field set from a call (D00 §5, CP-33 rows 6-7);
  until then a relative call keeps its path, peer NULL, at `unresolved`.
"""

from pathlib import Path

import pytest
from test_call_engines import (
    _EXTENSION_MATCHES,
    CATALOGS_DIR,
    FLUENT_CAPABILITIES,
    _document,
    _fluent_catalog,
    _resolve_fluent,
)
from test_ktor_client import _inlined_call

from sextant.application.ports.catalogs import CatalogError
from sextant.application.resolve.call_edges import record_call_edges
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.application.resolve.return_flow import record_return_flows
from sextant.application.resolve.shapes.client_base import (
    REPLACE_LAST_SEGMENT,
    client_base,
    client_base_of,
    join_url,
)
from sextant.application.resolve.values import cached_value_index
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    CallArgument,
    CallSiteFact,
    CallTarget,
    FieldWriteFact,
    MethodReturnFact,
    SymbolFact,
)
from sextant.domain.symbols import method_descriptor
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb.workspace import DuckDbWorkspace


@pytest.mark.pins("ktor.the-join-follows-KTORS-rule-not-concatenation")
def test_join_url_follows_ktors_rule():
    """One assertion per CP-54 row 51-60, each the URL Ktor's `DefaultRequest` sent."""
    rule = REPLACE_LAST_SEGMENT
    # Row 51: a base ending in `/` takes the relative path under its last directory.
    assert join_url("https://api.example.com/v1/", "orders", rule) == (
        "https://api.example.com/v1/orders"
    )
    # Row 52: a path starting with `/` replaces the base's whole path.
    assert join_url("https://api.example.com/v1/", "/orders", rule) == (
        "https://api.example.com/orders"
    )
    # Row 53: a base WITHOUT a trailing `/` has its last segment replaced — concatenation
    # would give `/v1orders` or `/v1/orders`, and Ktor sends neither.
    assert join_url("https://api.example.com/v1", "orders", rule) == (
        "https://api.example.com/orders"
    )
    # Row 54.
    assert join_url("https://api.example.com/v1", "/orders", rule) == (
        "https://api.example.com/orders"
    )
    # Row 55: an absolute address ignores the base.
    assert join_url("https://api.example.com/v1/", "https://other.example.com/x/y", rule) == (
        "https://other.example.com/x/y"
    )
    # Row 56: the call's own query is kept.
    assert join_url("https://api.example.com/v1/", "orders?limit=5&sort=asc", rule) == (
        "https://api.example.com/v1/orders?limit=5&sort=asc"
    )
    # Row 57: with no `defaultRequest` at all Ktor sends to its builder's origin,
    # `http://localhost` (row 50) — the same join with that origin as the base.
    assert join_url("http://localhost", "orders", rule) == "http://localhost/orders"
    # Row 58: a bare host is the root.
    assert join_url("https://api.example.com", "orders", rule) == ("https://api.example.com/orders")
    # Row 59: the base's query is appended AFTER the call's own (`mergeUrls`' order).
    assert join_url("https://api.example.com/v1/?key=1", "orders?limit=5", rule) == (
        "https://api.example.com/v1/orders?limit=5&key=1"
    )
    # Row 60: a deeper directory takes the whole relative path.
    assert join_url("https://api.example.com/v1/a/b/", "c/d", rule) == (
        "https://api.example.com/v1/a/b/c/d"
    )
    # Spec §3g item 1's own example, row 52's pattern.
    assert join_url("https://api.openai.com/v1/", "/chat", rule) == "https://api.openai.com/chat"
    # Row 83: a protocol-relative address is sent with the base's scheme.
    assert join_url("https://api.example.com/v1/", "//other.example.com/x/y", rule) == (
        "https://other.example.com/x/y"
    )
    # Row 84: two or more leading slashes start an authority whatever their number, so
    # `///x/y` is host `x` — not a path under the base's host.
    assert join_url("https://api.example.com/v1/", "///x/y", rule) == "https://x/y"
    # Rows 89-91: a query and no path is sent to the ROOT, the base's path dropped whether
    # or not it ends in `/`, and the base's own parameters follow the request's.
    assert join_url("https://api.example.com/v1/items", "?q=1", rule) == (
        "https://api.example.com/?q=1"
    )
    assert join_url("https://api.example.com/v1/", "?q=1", rule) == "https://api.example.com/?q=1"
    assert join_url("https://api.example.com/v1/items?key=1", "?q=1", rule) == (
        "https://api.example.com/?q=1&key=1"
    )


@pytest.mark.pins("ktor.a-SCHEME-without-a-host-is-not-joined")
def test_join_url_declines_what_it_does_not_model():
    """Where Ktor's result is not reproduced, `join_url` answers None and the caller keeps the
    address unresolved — never the string a scheme-based rule would invent."""
    rule = REPLACE_LAST_SEGMENT
    models = "https://generativelanguage.googleapis.com/v1beta/models/"
    # Row 81: Ktor keeps the request's scheme over the base's host and writes the base's port
    # explicitly — `gemini-pro://generativelanguage.googleapis.com:443/v1beta/models/
    # generateContent` — a URL no engine serves, built from `URLProtocol`'s port table.
    assert join_url(models, "gemini-pro:generateContent", rule) is None
    # Row 82: the same under a base without a trailing `/` (Ktor sent `…:443/v1beta/
    # generateContent`).
    assert join_url(models.removesuffix("/"), "gemini-pro:generateContent", rule) is None
    # `findScheme` throws on an illegal character before the `:`, so Ktor sends nothing.
    assert join_url(models, "a b:c", rule) is None
    # An authority with no host.
    assert join_url(models, "//", rule) is None


def test_join_url_refuses_a_rule_it_does_not_know():
    """A join is named per framework behaviour; an unknown name is a broken catalog, never
    a fallback to concatenation."""
    with pytest.raises(ValueError, match="concatenate"):
        join_url("https://api.example.com/", "orders", "concatenate")


def test_the_ktor_client_catalog_declares_its_base_ladder():
    """`ktor-client.yml` declares `client_base` (and no longer the interim
    `relative_to_client_base`): the client at `HttpStatement`'s argument 1, the ladder
    CP-54 rows 46-49, 79-80 and 87-88 measure, the member `url(String)` setter, Ktor's join,
    and the origin a client with no base sends to (rows 50, 57)."""
    catalog = next(c for c in YamlCatalogSource(CATALOGS_DIR).load() if c.id == "ktor-client")
    declared = catalog.matches["client_base"]
    assert "relative_to_client_base" not in catalog.matches
    assert declared["client_arg"] == 1
    assert [(rung["owner"], rung["method"], rung["block_arg"]) for rung in declared["ladder"]] == [
        ("io.ktor.client.HttpClientKt", "HttpClient", 1),
        ("io.ktor.client.HttpClientJvmKt", "HttpClient", 0),
        ("io.ktor.client.HttpClient", "config", 0),
        ("io.ktor.client.plugins.DefaultRequestKt", "defaultRequest", 1),
    ]
    assert (
        declared["setter"]["owner"] == "io.ktor.client.plugins.DefaultRequest$DefaultRequestBuilder"
    )
    assert declared["setter"]["method"] == "url"
    assert declared["setter"]["value_arg"] == 0
    assert declared["join"] == REPLACE_LAST_SEGMENT
    assert {entry["owner"] for entry in declared["may_set_base"]} == {
        "io.ktor.client.HttpClientConfig",
        "io.ktor.client.plugins.DefaultRequestKt",
        "io.ktor.http.URLBuilder",
    }


_LADDER = {
    "client_arg": 1,
    "ladder": [{"owner": "com.acme.http.ClientKt", "method": "Client", "block_arg": 1}],
    "setter": {"owner": "com.acme.http.Defaults", "method": "url", "value_arg": 0},
    "join": REPLACE_LAST_SEGMENT,
    "may_set_base": [],
}


@pytest.mark.parametrize(
    ("broken", "named"),
    [
        ("yes", "client_base"),
        ({**_LADDER, "client_arg": -1}, "client_arg"),
        ({**_LADDER, "client_arg": True}, "client_arg"),
        ({**_LADDER, "ladder": []}, "ladder"),
        ({**_LADDER, "ladder": [{"owner": "com.acme.Kt", "method": "Client"}]}, "block_arg"),
        ({**_LADDER, "ladder": [{"method": "Client", "block_arg": 1}]}, "owner"),
        (
            {**_LADDER, "ladder": [{**_LADDER["ladder"][0], "parent": "argument"}]},
            "parent",
        ),
        ({**_LADDER, "setter": {"owner": "com.acme.Defaults", "method": "url"}}, "value_arg"),
        ({**_LADDER, "join": "concatenate"}, "join"),
        ({key: value for key, value in _LADDER.items() if key != "may_set_base"}, "may_set_base"),
        ({**_LADDER, "may_set_base": {"owner": "com.acme.Kt"}}, "may_set_base"),
        ({**_LADDER, "may_set_base": [{"method": "install"}]}, "owner"),
        ({**_LADDER, "may_set_base": [{"owner": "com.acme.Kt", "arg": 0}]}, "field"),
        ({**_LADDER, "may_set_base": [{"owner": "com.acme.Kt", "arg": 0, "field": "x"}]}, "field"),
        (
            {
                **_LADDER,
                "may_set_base": [{"owner": "com.acme.Kt", "arg": 0, "field": {"owner": "a"}}],
            },
            "field",
        ),
        ({**_LADDER, "may_set_base": [{"owner": "com.acme.Kt", "when": 1}]}, "when"),
        ({**_LADDER, "base": "x"}, "base"),
    ],
)
def test_a_malformed_client_base_is_refused_at_load(tmp_path: Path, broken, named):
    """Every part of the key is checked when the catalog loads: a ladder that cannot be
    read would otherwise load and silently never find a base."""
    catalog = _fluent_catalog({**_EXTENSION_MATCHES, "client_base": broken})
    with pytest.raises(CatalogError, match=named):
        _resolve_fluent(tmp_path, [], catalog)


def test_a_well_formed_client_base_loads(tmp_path: Path):
    """The positive half of the refusals above: the same key, well formed, loads."""
    catalog = _fluent_catalog({**_EXTENSION_MATCHES, "client_base": _LADDER})
    _resolve_fluent(tmp_path, [], catalog)


def test_the_shared_reader_refuses_the_retired_word_for_every_style():
    """`client_base_of` is what `fluent` and `single_call` both call, so the retired
    `relative_to_client_base` is refused once, for every style declaring the key."""
    with pytest.raises(CatalogError, match="relative_to_client_base"):
        client_base_of({"relative_to_client_base": True}, "tests/any.yml")
    assert client_base_of({}, "tests/any.yml") is None
    assert client_base_of({"client_base": _LADDER}, "tests/any.yml")["join"] == (
        REPLACE_LAST_SEGMENT
    )


# --- The base read through the ladder (Task 10) -----------------------------------------
# Facts spelled as the CP-54 probe module's own scan spells them: a file-level client is a
# `putstatic` in `<clinit>` of the factory call's result (D00 §5's `field_write`), the
# configuration block is a lambda argument naming its synthetic body, `defaultRequest`'s
# block is a second body, and `url(String)` is called on that body's own parameter.

_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "
_FILE = "com/acme/kt/ClientsKt#"
_CLINIT = _MODULE + method_descriptor(_FILE, "<clinit>", "()V")
_FACTORY = (
    "io/ktor/client/HttpClientKt#",
    "HttpClient",
    (
        "(Lio/ktor/client/engine/HttpClientEngineFactory;Lkotlin/jvm/functions/Function1;)"
        "Lio/ktor/client/HttpClient;"
    ),
)
# `HttpClient { … }`, the engine-less factory: its own JVM function, the block at argument
# 0 (CP-54 row 87).
_ENGINELESS = (
    "io/ktor/client/HttpClientJvmKt#",
    "HttpClient",
    "(Lkotlin/jvm/functions/Function1;)Lio/ktor/client/HttpClient;",
)
# `HttpClient(engine) { … }` over an engine INSTANCE: the same owner and name as `_FACTORY`
# and another overload, which no ladder rung declares.
_ENGINE_INSTANCE = (
    "io/ktor/client/HttpClientKt#",
    "HttpClient",
    (
        "(Lio/ktor/client/engine/HttpClientEngine;Lkotlin/jvm/functions/Function1;)"
        "Lio/ktor/client/HttpClient;"
    ),
)
_CONFIG = (
    "io/ktor/client/HttpClient#",
    "config",
    "(Lkotlin/jvm/functions/Function1;)Lio/ktor/client/HttpClient;",
)
_DEFAULT_REQUEST = (
    "io/ktor/client/plugins/DefaultRequestKt#",
    "defaultRequest",
    "(Lio/ktor/client/HttpClientConfig;Lkotlin/jvm/functions/Function1;)V",
)
_SETTER = (
    "io/ktor/client/plugins/DefaultRequest$DefaultRequestBuilder#",
    "url",
    "(Ljava/lang/String;)V",
)
_CIO = CallArgument(kind="enum", symbol="io/ktor/client/engine/cio/CIO#INSTANCE.")


def _call(
    caller: str,
    ordinal: int,
    target: tuple[str, str, str],
    arguments: list[CallArgument],
    *,
    invoke_kind: str = "static",
    receiver: int | None = None,
    receiver_parameter: int | None = None,
    receiver_field: str | None = None,
    result: int | None = None,
) -> CallSiteFact:
    owner, name, descriptor = target
    return CallSiteFact(
        document_id="doc_1",
        caller=caller,
        target=CallTarget(owner=owner, name=name, descriptor=descriptor),
        invoke_kind=invoke_kind,
        ordinal=ordinal,
        receiver=receiver,
        receiver_parameter=receiver_parameter,
        receiver_field=receiver_field,
        result=result,
        arguments=arguments,
    )


def _body(name: str) -> str:
    """A configuration lambda's synthetic body, as its `lambda` argument names it: bare."""
    return method_descriptor(_FILE, name, "(Lio/ktor/client/HttpClientConfig;)Lkotlin/Unit;")


def _block(
    name: str, addresses: list[CallArgument], captures: int = 0
) -> tuple[CallArgument, list[CallSiteFact]]:
    """`{ defaultRequest { url(a); url(b) … } }`, or `{ }` where `addresses` is empty: the
    lambda argument the factory or `config` is handed, and the facts of its two bodies. A
    body capturing `captures` values has them as its leading parameters, so its own
    receiver parameter — the one the next block is called on — is the next one."""
    outer, inner = _body(name), _body(name + "$0")
    facts: list[CallSiteFact] = []
    if addresses:
        # The inner block is built by an `invokedynamic` handed the captured values.
        facts.append(
            _call(
                _MODULE + outer,
                0,
                _LAMBDA_FACTORY,
                [CallArgument(kind="parameter", value=index) for index in range(captures)],
                result=7,
            )
        )
        facts.append(
            _call(
                _MODULE + outer,
                1,
                _DEFAULT_REQUEST,
                [
                    CallArgument(kind="parameter", value=captures),
                    CallArgument(kind="lambda", symbol=inner, source=7, captures=captures),
                ],
            )
        )
        facts.extend(
            _call(
                _MODULE + inner,
                ordinal,
                _SETTER,
                [address],
                invoke_kind="virtual",
                receiver_parameter=captures,
            )
            for ordinal, address in enumerate(addresses)
        )
    return CallArgument(kind="lambda", symbol=outer, source=4, captures=captures), facts


def _base(url: str) -> CallArgument:
    return CallArgument(kind="string", value=url)


def _top_level(
    field: str,
    ordinal: int,
    addresses: list[CallArgument],
    factory: tuple[str, str, str] = _FACTORY,
) -> list:
    """`val <field> = HttpClient(CIO) { defaultRequest { url(…) } }` at file level: the
    factory call in `<clinit>` at `ordinal`, its result stored with `putstatic`."""
    block, facts = _block(f"{field}$lambda$0", addresses)
    arguments = [block] if factory == _ENGINELESS else [_CIO, block]
    result = 100 + ordinal
    return [
        _call(_CLINIT, ordinal, factory, arguments, result=result),
        FieldWriteFact(
            document_id="doc_1",
            field=_FILE + field + ".",
            value=CallArgument(kind="unresolved", source=result),
            written_by=_CLINIT,
        ),
        *facts,
    ]


def _derived(
    field: str, parent: str, ordinal: int, addresses: list[CallArgument], named: bool = True
) -> list:
    """`val <field> = <parent>.config { … }` at file level: `config`'s receiver is a
    `getstatic` of the parent, named by `receiver_field` unless `named` is False — what
    every scan wrote before that key."""
    block, facts = _block(f"{field}$lambda$0", addresses)
    result = 100 + ordinal
    return [
        _call(
            _CLINIT,
            ordinal,
            _CONFIG,
            [block],
            invoke_kind="virtual",
            receiver=90 + ordinal,
            receiver_field=_FILE + parent + "." if named else None,
            result=result,
        ),
        FieldWriteFact(
            document_id="doc_1",
            field=_FILE + field + ".",
            value=CallArgument(kind="unresolved", source=result),
            written_by=_CLINIT,
        ),
        *facts,
    ]


def _on(field: str, caller: str, address: str) -> list[CallSiteFact]:
    """`<field>.get("<address>")` in `caller`, the inlined sequence of CP-54 row (b)."""
    return _inlined_call(
        caller,
        address,
        verbs=(None, "Get"),
        client=CallArgument(kind="field", symbol=_FILE + field + "."),
    )


def _ktor_client():
    return next(c for c in YamlCatalogSource(CATALOGS_DIR).load() if c.id == "ktor-client")


def _resolved(tmp_path: Path, facts: list, catalog=None):
    """The facts, with the two derived tables the walk reads built by the passes that own
    them, then the catalog run (`ktor-client` unless another is given)."""
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    record_return_flows(workspace)
    record_call_edges(workspace)
    catalogs = [catalog or _ktor_client()]
    assert derive_endpoints(workspace, catalogs, capabilities=FLUENT_CAPABILITIES) == []
    return workspace


def _client_rows(tmp_path: Path, facts: list, catalog=None) -> list[tuple]:
    workspace = _resolved(tmp_path, facts, catalog)
    rows = sorted(
        (r["caller"], r["peer"], r["path"], r["resolution"]) for r in workspace.query("endpoints")
    )
    workspace.close()
    return rows


def _fn(name: str) -> str:
    return f"com/acme/kt/ClientsKt#{name}()."


def _why(tmp_path: Path, facts: list, caller: str) -> tuple[str | None, str | None]:
    """What the shared reader answers for the client of `caller`'s one request — the base,
    or the reason there is none — asked exactly as an engine asks it."""
    workspace = _resolved(tmp_path, facts)
    statement = next(
        dict(row)
        for row in workspace.query("call_sites")
        if row["caller"] == caller
        and row["name"] == "<init>"
        and row["owner"] == "io/ktor/client/statement/HttpStatement#"
    )
    client = {**statement["arguments"][1], "captured_at": (caller, statement["ordinal"], 1)}
    declared = _ktor_client().matches["client_base"]
    answer = client_base(workspace, cached_value_index(workspace), client, declared)
    workspace.close()
    return answer


@pytest.mark.pins("ktor.a-RELATIVE-call-joins-its-clients-default-request-base")
def test_a_top_level_client_base_joins_a_relative_call(tmp_path: Path):
    """`val client = HttpClient(CIO) { defaultRequest { url("https://pricing.example.com/") } }`
    and `client.get("quotes")`: Ktor sends `https://pricing.example.com/quotes` (CP-54 rows
    51, 88). The client is reached through its `<clinit>` write, the base read through the
    ladder, and the relative address joined by Ktor's rule."""
    facts = [
        *_top_level("client", 1, [_base("https://pricing.example.com/")]),
        *_on("client", _fn("quotes"), "quotes"),
    ]
    assert _client_rows(tmp_path, facts) == [
        (_fn("quotes"), "pricing.example.com", "/quotes", "resolved")
    ]


def test_an_absolute_call_ignores_the_base(tmp_path: Path):
    """An absolute address is the whole address, whatever the client's base (row 55)."""
    facts = [
        *_top_level("client", 1, [_base("https://pricing.example.com/")]),
        *_on("client", _fn("orders"), "https://orders.example.com/orders"),
    ]
    assert _client_rows(tmp_path, facts) == [
        (_fn("orders"), "orders.example.com", "/orders", "resolved")
    ]


@pytest.mark.pins("ktor.a-RELATIVE-call-joins-its-clients-default-request-base")
def test_two_clients_join_their_own_bases(tmp_path: Path):
    """Two file-level clients with two bases, a relative call on each: each call joins the
    base of the client it is made on, never the other's."""
    facts = [
        *_top_level("pricing", 1, [_base("https://pricing.example.com/v1/")]),
        *_top_level("billing", 3, [_base("https://billing.example.com/")]),
        *_on("pricing", _fn("quotes"), "quotes"),
        *_on("billing", _fn("invoices"), "invoices"),
    ]
    assert _client_rows(tmp_path, facts) == [
        (_fn("invoices"), "billing.example.com", "/invoices", "resolved"),
        (_fn("quotes"), "pricing.example.com", "/v1/quotes", "resolved"),
    ]


@pytest.mark.pins("ktor.each-client-joins-its-OWN-base")
def test_a_derived_config_client_reads_its_own_base(tmp_path: Path):
    """`val derived = client.config { defaultRequest { url(…/c/) } }`: the derived client's
    own base wins over its parent's (CP-54 row 79)."""
    facts = [
        *_top_level("client", 1, [_base("https://parent.example.com/p/")]),
        *_derived("derived", "client", 3, [_base("https://child.example.com/c/")]),
        *_on("derived", _fn("child"), "orders"),
        *_on("client", _fn("parent"), "orders"),
    ]
    assert _client_rows(tmp_path, facts) == [
        (_fn("child"), "child.example.com", "/c/orders", "resolved"),
        (_fn("parent"), "parent.example.com", "/p/orders", "resolved"),
    ]


@pytest.mark.pins("values.a-STATIC-FIELD-receiver-is-followed-to-its-writer")
def test_a_derived_client_with_no_base_of_its_own_inherits_its_parents(tmp_path: Path):
    """`val derived = client.config { }`: with no `defaultRequest` of its own the derived
    client sends to its parent's base (CP-54 row 80). The parent is `config`'s receiver, a
    `getstatic` of `client` that `receiver_field` names; where the facts name only the
    read's own value id, the parent cannot be reached and the call stays relative."""
    facts = [
        *_top_level("client", 1, [_base("https://parent.example.com/p/")]),
        *_derived("derived", "client", 3, []),
        *_on("derived", _fn("child"), "orders"),
    ]
    assert _client_rows(tmp_path / "named", facts) == [
        (_fn("child"), "parent.example.com", "/p/orders", "resolved")
    ]
    unnamed = [
        *_top_level("client", 1, [_base("https://parent.example.com/p/")]),
        *_derived("derived", "client", 3, [], named=False),
        *_on("derived", _fn("child"), "orders"),
    ]
    assert _client_rows(tmp_path / "unnamed", unnamed) == [
        (_fn("child"), None, "orders", "unresolved")
    ]
    assert _why(tmp_path / "why", unnamed, _fn("child")) == (None, "not_readable")


@pytest.mark.declines("ktor-client")
@pytest.mark.pins("ktor.a-client-with-no-DECLARED-base-is-not-assumed-localhost")
def test_a_client_with_no_declared_base_stays_relative(tmp_path: Path):
    """A client whose construction is reached and whose blocks reach no declared setter.
    Ktor sends such a client's relative call to its builder's origin, `http://localhost`
    (CP-54 rows 50, 57), but that the client HAS no base cannot be proven from the
    bytecode: `install(DefaultRequest)`, a caller-supplied `block()`, a helper the block
    calls all set one, and the set is open. So the call stays relative and unresolved, as
    for a construction not reached at all (ruling reversed, Task 10 fix round 2)."""
    facts = [*_top_level("client", 1, []), *_on("client", _fn("local"), "orders")]
    assert _client_rows(tmp_path, facts) == [(_fn("local"), None, "orders", "unresolved")]
    assert _why(tmp_path / "why", facts, _fn("local")) == (
        None,
        "computed_base_addresses_not_traced",
    )


@pytest.mark.pins("ktor.the-ENGINE-LESS-factory-is-a-ladder-rung")
def test_the_engine_less_factory_is_a_rung(tmp_path: Path):
    """`HttpClient { defaultRequest { url(…) } }` — koog's shape — is
    `HttpClientJvmKt.HttpClient(Function1)`, the block at argument 0 (CP-54 rows 87-88)."""
    facts = [
        *_top_level("client", 1, [_base("https://engineless.example.com/e/")], factory=_ENGINELESS),
        *_on("client", _fn("orders"), "orders"),
    ]
    assert _client_rows(tmp_path, facts) == [
        (_fn("orders"), "engineless.example.com", "/e/orders", "resolved")
    ]


@pytest.mark.declines("ktor-client")
@pytest.mark.pins("ktor.only-a-DECLARED-factory-overload-is-read")
def test_an_undeclared_factory_overload_leaves_the_call_relative(tmp_path: Path):
    """`HttpClient(engine) { … }` over an engine INSTANCE shares the factory's owner and name
    and is not a declared rung: its block is not read, and the call keeps its path."""
    facts = [
        *_top_level("client", 1, [_base("https://pricing.example.com/")], factory=_ENGINE_INSTANCE),
        *_on("client", _fn("quotes"), "quotes"),
    ]
    assert _client_rows(tmp_path, facts) == [(_fn("quotes"), None, "quotes", "unresolved")]
    assert _why(tmp_path / "why", facts, _fn("quotes")) == (
        None,
        "computed_base_addresses_not_traced",
    )


@pytest.mark.pins("ktor.a-RELATIVE-setter-after-an-absolute-one-declines")
def test_the_last_absolute_setter_is_the_base_and_a_relative_one_after_it_declines(
    tmp_path: Path,
):
    """A block calling `url(…)` twice applies both, in order (CP-54 rows 85-86): two
    absolute addresses leave the second; a relative one after an absolute one MOVES the
    base, which is not modelled, so the call keeps its path rather than a base Ktor never
    used."""
    twice = [
        *_top_level(
            "client",
            1,
            [_base("https://first.example.com/a/"), _base("https://second.example.com/b/")],
        ),
        *_on("client", _fn("orders"), "orders"),
    ]
    assert _client_rows(tmp_path / "twice", twice) == [
        (_fn("orders"), "second.example.com", "/b/orders", "resolved")
    ]
    moved = [
        *_top_level("client", 1, [_base("https://first.example.com/a/"), _base("b/")]),
        *_on("client", _fn("orders"), "orders"),
    ]
    assert _client_rows(tmp_path / "moved", moved) == [
        (_fn("orders"), None, "orders", "unresolved")
    ]
    assert _why(tmp_path / "why", moved, _fn("orders")) == (
        None,
        "computed_base_addresses_not_traced",
    )


_MADE = _MODULE + method_descriptor(
    _FILE, "madeClient", "(Ljava/lang/String;)Lio/ktor/client/HttpClient;"
)


def _made(callers: list[tuple[str, int, str]]) -> list:
    """`fun madeClient(base: String) = HttpClient(CIO) { defaultRequest { url(base) } }` and
    one file-level `val <field> = madeClient("<base>")` per caller. Both lambdas capture
    `base`, so it is each body's parameter 0 and the block's own receiver is parameter 1."""
    block, facts = _block("madeClient$lambda$0", [CallArgument(kind="parameter", value=0)], 1)
    made = [
        SymbolFact(
            document_id="doc_1",
            symbol=_MADE,
            construct_kind="method",
            enclosing=_MODULE + _FILE,
        ),
        _call(_MADE, 0, _LAMBDA_FACTORY, [CallArgument(kind="parameter", value=0)], result=4),
        _call(_MADE, 1, _FACTORY, [_CIO, block], result=11),
        MethodReturnFact(
            document_id="doc_1",
            method=_MADE,
            ordinal=0,
            value=CallArgument(kind="unresolved", source=11),
        ),
        *facts,
    ]
    for field, ordinal, base in callers:
        made += [
            _call(
                _CLINIT,
                ordinal,
                (_FILE, "madeClient", "(Ljava/lang/String;)Lio/ktor/client/HttpClient;"),
                [_base(base)],
                result=100 + ordinal,
            ),
            FieldWriteFact(
                document_id="doc_1",
                field=_FILE + field + ".",
                value=CallArgument(kind="unresolved", source=100 + ordinal),
                written_by=_CLINIT,
            ),
        ]
    return made


# The `invokedynamic` that builds a capturing lambda: its arguments are the captured values,
# which is how the walk binds a body's leading parameters (`values.value_index`, OI-150).
_LAMBDA_FACTORY = (
    "java/lang/invoke/LambdaMetafactory#",
    "invoke",
    "(Ljava/lang/String;)Lkotlin/jvm/functions/Function1;",
)


def test_a_block_capturing_the_factorys_parameter_resolves_it_through_the_walk(tmp_path: Path):
    """`val made = madeClient("https://made.example.com/")`: the base is `madeClient`'s
    parameter, captured into both blocks, and the walk resolves it at the one call that
    hands it in."""
    facts = [
        *_made([("made", 1, "https://made.example.com/")]),
        *_on("made", _fn("orders"), "made/path"),
    ]
    assert _client_rows(tmp_path, facts) == [
        (_fn("orders"), "made.example.com", "/made/path", "resolved")
    ]


@pytest.mark.declines("ktor-client")
@pytest.mark.pins("ktor.a-base-from-ANOTHER-path-is-never-paired")
def test_two_callers_of_the_factory_function_decline_rather_than_pick(tmp_path: Path):
    """Two `madeClient(…)` calls with two bases: the producer the client walk names is the
    factory call INSIDE `madeClient`, which carries no path, so nothing says which of the
    two bases the client `a` was built with. Publishing either — or both — would pair a
    client with a base from another path (ruling M-1), so the call keeps its path."""
    facts = [
        *_made([("a", 1, "https://a.example.com/"), ("b", 3, "https://b.example.com/")]),
        *_on("a", _fn("orders"), "orders"),
    ]
    assert _client_rows(tmp_path, facts) == [(_fn("orders"), None, "orders", "unresolved")]
    assert _why(tmp_path / "why", facts, _fn("orders")) == (None, "non_enumerable")


def test_an_unreachable_client_leaves_the_call_relative_with_a_reason(tmp_path: Path):
    """`fun use(client: HttpClient) = client.get("orders")` and nothing in the module calls
    `use`: the client comes from outside what was scanned. The row keeps its path at
    `unresolved`, and the reader says why — the walk's own reason, `external`."""
    use = _MODULE + method_descriptor(_FILE, "use", "(Lio/ktor/client/HttpClient;)V")
    facts = _inlined_call(
        use, "orders", verbs=(None, "Get"), client=CallArgument(kind="parameter", value=0)
    )
    assert _client_rows(tmp_path, facts) == [(use, None, "orders", "unresolved")]
    assert _why(tmp_path / "why", facts, use) == (None, "external")


def test_a_client_held_in_a_class_property_joins_its_base(tmp_path: Path):
    """`class Agent { private val client = HttpClient { defaultRequest { url(…) } } }` —
    koog's `WebSearchAgent` shape: the property is written in the constructor from the
    engine-less factory's result (`aload_0; invokestatic; putfield`), and a method reads it
    back with `getfield`."""
    agent = "com/acme/kt/Agent#"
    init = _MODULE + method_descriptor(agent, "<init>", "()V")
    search = _MODULE + method_descriptor(agent, "search", "()V")
    block, body = _block("client$lambda$0", [_base("https://search.example.com/api/")])
    facts = [
        _call(init, 0, _ENGINELESS, [block], result=12),
        FieldWriteFact(
            document_id="doc_1",
            field=agent + "client.",
            value=CallArgument(kind="unresolved", source=12),
            written_by=init,
        ),
        *body,
        *_inlined_call(
            search,
            "search",
            verbs=(None, "Get"),
            client=CallArgument(kind="field", symbol=agent + "client."),
        ),
    ]
    assert _client_rows(tmp_path, facts) == [
        (search, "search.example.com", "/api/search", "resolved")
    ]


def test_a_client_handed_in_as_a_parameter_joins_its_callers_base(tmp_path: Path):
    """`fun use(client: HttpClient) = client.get("orders")`, called once with a client the
    caller built: the walk crosses `bound_to_parameter` to that caller's factory call, and
    the call joins that client's base."""
    use_jvm = "(Lio/ktor/client/HttpClient;)V"
    use = _MODULE + method_descriptor(_FILE, "use", use_jvm)
    main = _MODULE + method_descriptor(_FILE, "main", "()V")
    block, body = _block("main$lambda$0", [_base("https://telemetry.example.com/")])
    facts = [
        SymbolFact(
            document_id="doc_1", symbol=use, construct_kind="method", enclosing=_MODULE + _FILE
        ),
        # A read body is what makes `main`'s call to `use` an edge the walk can cross.
        MethodReturnFact(document_id="doc_1", method=use, ordinal=0, value=None),
        _call(main, 0, _FACTORY, [_CIO, block], result=5),
        _call(
            main,
            1,
            (_FILE, "use", use_jvm),
            [CallArgument(kind="unresolved", source=5)],
        ),
        *body,
        *_inlined_call(
            use, "orders", verbs=(None, "Get"), client=CallArgument(kind="parameter", value=0)
        ),
    ]
    assert _client_rows(tmp_path, facts) == [(use, "telemetry.example.com", "/orders", "resolved")]


# --- Fix round 1: silence is "no base" only where it is silence ---------------------------


_DEFAULT_REQUEST_REPLACE = (
    "io/ktor/client/plugins/DefaultRequestKt#",
    "defaultRequest",
    "(Lio/ktor/client/HttpClientConfig;ZLkotlin/jvm/functions/Function1;)V",
)
_URL_BLOCK = (
    "io/ktor/client/plugins/DefaultRequest$DefaultRequestBuilder#",
    "url",
    "(Lkotlin/jvm/functions/Function1;)V",
)
_SET_HOST = (
    "io/ktor/client/plugins/DefaultRequest$DefaultRequestBuilder#",
    "setHost",
    "(Ljava/lang/String;)V",
)
_CONFIG_KT = "io/ktor/client/HttpClientConfig#"
_INSTALL = (
    _CONFIG_KT,
    "install",
    "(Lio/ktor/client/plugins/HttpClientPlugin;Lkotlin/jvm/functions/Function1;)V",
)
_INSTALL_DEFAULT = (
    _CONFIG_KT,
    "install$default",
    (
        "(Lio/ktor/client/HttpClientConfig;Lio/ktor/client/plugins/HttpClientPlugin;"
        "Lkotlin/jvm/functions/Function1;ILjava/lang/Object;)V"
    ),
)
_DEFAULT_REQUEST_PLUGIN = CallArgument(
    kind="field", symbol="io/ktor/client/plugins/DefaultRequest#Plugin."
)
_WEBSOCKETS_PLUGIN = CallArgument(
    kind="field", symbol="io/ktor/client/plugins/websocket/WebSockets#Plugin."
)


_PRICING = "https://pricing.example.com/"


def _plain_client(extra: list[CallSiteFact], inner: list[CallSiteFact] | None = None) -> list:
    """`val client = HttpClient(CIO) { <extra>; defaultRequest { url(_PRICING); <inner> } }`
    and `client.get("orders")`: a client whose base IS read, so each rule below is seen
    protecting that base from a call that may override it. `inner` sites take ordinals
    from 1, after the setter."""
    outer = _MODULE + _body("client$lambda$0")
    facts = [
        _call(
            _CLINIT,
            1,
            _FACTORY,
            [_CIO, CallArgument(kind="lambda", symbol=_body("client$lambda$0"), source=4)],
            result=101,
        ),
        FieldWriteFact(
            document_id="doc_1",
            field=_FILE + "client.",
            value=CallArgument(kind="unresolved", source=101),
            written_by=_CLINIT,
        ),
        *extra,
        *_on("client", _fn("orders"), "orders"),
        _call(
            outer,
            9,
            _DEFAULT_REQUEST,
            [
                CallArgument(kind="parameter", value=0),
                CallArgument(kind="lambda", symbol=_body("client$lambda$0$0"), source=7),
            ],
        ),
        _in_default_request(0, _SETTER, [_base(_PRICING)]),
        *(inner or []),
    ]
    return facts


def _in_client_block(ordinal: int, target, arguments: list[CallArgument]) -> CallSiteFact:
    return _call(_MODULE + _body("client$lambda$0"), ordinal, target, arguments)


def _in_default_request(ordinal: int, target, arguments: list[CallArgument]) -> CallSiteFact:
    return _call(
        _MODULE + _body("client$lambda$0$0"),
        ordinal,
        target,
        arguments,
        invoke_kind="virtual",
        receiver_parameter=0,
    )


_BASED_ROW = (_fn("orders"), "pricing.example.com", "/orders", "resolved")
_DECLINED_ROW = (_fn("orders"), None, "orders", "unresolved")


def test_a_call_that_sets_no_base_keeps_the_read_base(tmp_path: Path):
    """`install(WebSockets)` — a plugin that sets no base, installed through the
    `install$default` bridge (CP-54 row 92) — beside a declared base: the base stands, so
    only calls that MAY move the base decline."""
    facts = _plain_client(
        [
            _in_client_block(
                0,
                _INSTALL_DEFAULT,
                [
                    CallArgument(kind="parameter", value=0),
                    _WEBSOCKETS_PLUGIN,
                    CallArgument(kind="null"),
                    CallArgument(kind="int", value=2),
                    CallArgument(kind="null"),
                ],
            )
        ]
    )
    assert _client_rows(tmp_path, facts) == [_BASED_ROW]


def test_a_rung_or_setter_under_another_descriptor_declines_the_read_base(
    tmp_path: Path,
):
    """`defaultRequest(replace = true) { … }` (row 48's second overload) in the client's block,
    and `url { host = … }` (row 46's block setter) in a `defaultRequest` block: each may
    override the base that was read, so the call keeps its path rather than publish it.
    Either alone declines. (On Ktor's catalog two rules cover each; the rule alone is
    pinned on an invented ladder below.)"""
    replace = _plain_client(
        [
            _in_client_block(
                0,
                _DEFAULT_REQUEST_REPLACE,
                [
                    CallArgument(kind="parameter", value=0),
                    CallArgument(kind="boolean", value=True),
                    CallArgument(kind="lambda", symbol=_body("other$lambda"), source=3),
                ],
            )
        ]
    )
    assert _client_rows(tmp_path / "replace", replace) == [_DECLINED_ROW]
    block = _plain_client(
        [],
        inner=[
            _in_default_request(
                1, _URL_BLOCK, [CallArgument(kind="lambda", symbol=_body("u$lambda"), source=3)]
            )
        ],
    )
    assert _client_rows(tmp_path / "block", block) == [_DECLINED_ROW]


@pytest.mark.declines("ktor-client")
@pytest.mark.pins("ktor.any-other-call-on-the-SETTERS-owner-declines")
def test_any_other_call_on_the_setters_owner_declines(tmp_path: Path):
    """`defaultRequest { url(…); host = "other.example.com" }`: `setHost` on the setter's own
    type moves the base that was read and is not the declared setter, so the base is not
    published."""
    facts = _plain_client(
        [], inner=[_in_default_request(1, _SET_HOST, [_base("other.example.com")])]
    )
    assert _client_rows(tmp_path, facts) == [_DECLINED_ROW]


@pytest.mark.declines("ktor-client")
@pytest.mark.pins("ktor.a-LISTED-call-that-may-set-the-base-declines")
def test_install_default_request_declines_the_read_base(tmp_path: Path):
    """`install(DefaultRequest) { url("https://installed.example.com/") }` beside a declared
    base sets a base as `defaultRequest { }` does (CP-54 rows 92-93), through a generic
    installer the ladder does not read; `may_set_base` names it, so the base that was read
    is not published as the one Ktor uses."""
    facts = _plain_client(
        [
            _in_client_block(
                0,
                _INSTALL,
                [
                    _DEFAULT_REQUEST_PLUGIN,
                    CallArgument(kind="lambda", symbol=_body("installed$lambda"), source=3),
                ],
            )
        ]
    )
    assert _client_rows(tmp_path, facts) == [_DECLINED_ROW]


def test_a_configuration_key_base_is_carried_at_partial(tmp_path: Path):
    """`defaultRequest { url("${pricing.base-url}") }` (Kotlin's escaped `\\$`): the base is a configuration key.
    It is rendered as a configuration-fed `base` capture already is (`fluent.
    _composed_address`, pinned by `test_call_engines`' `${billing.url}/invoices`): base and
    path concatenated as written, peer NULL. It is `partial`, because Ktor's join depends on
    whether the deployed value ends in `/` — which is also why `quotes` reads as glued on."""
    facts = [
        *_top_level("client", 1, [_base("${pricing.base-url}")]),
        *_on("client", _fn("quotes"), "quotes"),
    ]
    assert _client_rows(tmp_path, facts) == [
        (_fn("quotes"), None, "${pricing.base-url}quotes", "partial")
    ]


def test_an_assembled_base_with_no_key_declines(tmp_path: Path):
    """`url("https://" + host + "/")` where `host` is not read: the walk answers the template
    `https://{}/`, which names no configuration key, so it is not a base."""
    facts = [
        *_top_level("client", 1, [CallArgument(kind="concat", source=55, value="https://{}/")]),
        *_on("client", _fn("quotes"), "quotes"),
    ]
    assert _client_rows(tmp_path, facts) == [(_fn("quotes"), None, "quotes", "unresolved")]


@pytest.mark.declines("ktor-client")
@pytest.mark.pins("fluent.a-request-executed-TWICE-holds-no-client")
def test_a_request_executed_on_two_clients_holds_neither(tmp_path: Path):
    """One builder handed to two `HttpStatement`s on two clients with two bases: which client
    the row means is not known, so it holds neither and keeps its path."""
    facts = [
        *_top_level("first", 1, [_base("https://first.example.com/")]),
        *_top_level("second", 3, [_base("https://second.example.com/")]),
        *_on("first", _fn("orders"), "orders"),
        _call(
            _fn("orders"),
            90,
            (
                "io/ktor/client/statement/HttpStatement#",
                "<init>",
                "(Lio/ktor/client/request/HttpRequestBuilder;Lio/ktor/client/HttpClient;)V",
            ),
            [
                CallArgument(
                    kind="instance", source=18, symbol="io/ktor/client/request/HttpRequestBuilder#"
                ),
                CallArgument(kind="field", symbol=_FILE + "second."),
            ],
            invoke_kind="special",
            receiver=300,
        ),
    ]
    assert _client_rows(tmp_path, facts) == [_DECLINED_ROW]


def test_n_calls_on_one_client_read_its_construction_once(tmp_path: Path, monkeypatch):
    """The construction-keyed memo: three relative calls on one client read the
    construction that built it once in the resolve."""
    from sextant.application.resolve.shapes import client_base as module

    reads: list[tuple[str, int]] = []
    original = module._Ladder._read_construction

    def counting(self, built, seen):
        reads.append(built)
        return original(self, built, seen)

    monkeypatch.setattr(module._Ladder, "_read_construction", counting)
    facts = [
        *_top_level("client", 1, [_base("https://pricing.example.com/")]),
        *_on("client", _fn("a"), "a"),
        *_on("client", _fn("b"), "b"),
        *_on("client", _fn("c"), "c"),
    ]
    assert [row[1] for row in _client_rows(tmp_path, facts)] == ["pricing.example.com"] * 3
    assert reads == [(_CLINIT, 1)]


# An invented ladder on which ONLY the same-name rule can see the call: its nested rung's
# owner is not the setter's, and it lists nothing in `may_set_base`.
_ACME_FACTORY = (
    "com/acme/http/ClientKt#",
    "Client",
    "(Lkotlin/jvm/functions/Function1;)Lcom/acme/http/Client;",
)
_ACME_DEFAULTS_OTHER = (
    "com/acme/http/DefaultsKt#",
    "defaults",
    "(Lcom/acme/http/Config;ZLkotlin/jvm/functions/Function1;)V",
)
_ACME_LADDER = {
    "client_arg": 1,
    "ladder": [
        {
            "owner": "com.acme.http.ClientKt",
            "method": "Client",
            "block_arg": 0,
            "descriptor": _ACME_FACTORY[2],
        },
        {
            "owner": "com.acme.http.DefaultsKt",
            "method": "defaults",
            "block_arg": 1,
            "descriptor": "(Lcom/acme/http/Config;Lkotlin/jvm/functions/Function1;)V",
        },
    ],
    "setter": {"owner": "com.acme.http.Defaults", "method": "url", "value_arg": 0},
    "join": REPLACE_LAST_SEGMENT,
    "may_set_base": [],
}


def _acme_client(block_calls: list[CallSiteFact]) -> list:
    """`val client = Client { <block_calls> }` and `client` executing a relative request,
    in the shapes `_EXTENSION_MATCHES` reads."""
    caller = _fn("acme")
    builder = "com/acme/http/Request$Builder#"
    return [
        _call(
            _CLINIT,
            1,
            _ACME_FACTORY,
            [CallArgument(kind="lambda", symbol=_body("acme$lambda$0"), source=4)],
            result=101,
        ),
        FieldWriteFact(
            document_id="doc_1",
            field=_FILE + "client.",
            value=CallArgument(kind="unresolved", source=101),
            written_by=_CLINIT,
        ),
        *block_calls,
        # `defaults { url("https://acme.example.com/") }`, the declared nested rung.
        _call(
            _MODULE + _body("acme$lambda$0"),
            5,
            (
                "com/acme/http/DefaultsKt#",
                "defaults",
                "(Lcom/acme/http/Config;Lkotlin/jvm/functions/Function1;)V",
            ),
            [
                CallArgument(kind="parameter", value=0),
                CallArgument(kind="lambda", symbol=_body("acme$lambda$0$0"), source=7),
            ],
        ),
        _call(
            _MODULE + _body("acme$lambda$0$0"),
            0,
            ("com/acme/http/Defaults#", "url", "(Ljava/lang/String;)V"),
            [_base("https://acme.example.com/")],
            invoke_kind="virtual",
            receiver_parameter=0,
        ),
        _call(caller, 0, (builder, "<init>", "()V"), [], invoke_kind="special", receiver=2),
        _call(
            caller,
            1,
            (
                "com/acme/http/RequestKt#",
                "url",
                "(Lcom/acme/http/Request$Builder;Ljava/lang/String;)V",
            ),
            [CallArgument(kind="instance", source=2, symbol=builder), _base("orders")],
        ),
        _call(
            caller,
            2,
            (
                "com/acme/http/Statement#",
                "<init>",
                "(Lcom/acme/http/Request$Builder;Lcom/acme/http/Client;)V",
            ),
            [
                CallArgument(kind="instance", source=2, symbol=builder),
                CallArgument(kind="field", symbol=_FILE + "client."),
            ],
            invoke_kind="special",
            receiver=7,
        ),
    ]


@pytest.mark.declines("ktor-client")
@pytest.mark.pins("ktor.a-rung-or-setter-under-ANOTHER-descriptor-declines")
def test_a_rung_under_another_descriptor_declines_on_any_ladder(tmp_path: Path):
    """The rule itself, with nothing else to catch the call: `defaults` under an undeclared
    descriptor in the factory's block may set the base, so the client is not read as having
    none. Without that call the same client's declared base is read."""
    catalog = _fluent_catalog({**_EXTENSION_MATCHES, "client_base": _ACME_LADDER})
    plain = _acme_client([])
    assert _client_rows(tmp_path / "plain", plain, catalog) == [
        (_fn("acme"), "acme.example.com", "/orders", "resolved")
    ]
    other = _acme_client(
        [
            _call(
                _MODULE + _body("acme$lambda$0"),
                0,
                _ACME_DEFAULTS_OTHER,
                [
                    CallArgument(kind="parameter", value=0),
                    CallArgument(kind="boolean", value=True),
                    CallArgument(kind="lambda", symbol=_body("other$lambda"), source=3),
                ],
            )
        ]
    )
    assert _client_rows(tmp_path / "other", other, catalog) == [
        (_fn("acme"), None, "orders", "unresolved")
    ]


_CONFIGURE_JVM = "(Lio/ktor/client/HttpClientConfig;)V"
_CONFIGURE = _MODULE + method_descriptor(_FILE, "configure", _CONFIGURE_JVM)
_LOG = _MODULE + method_descriptor(_FILE, "log", "(Ljava/lang/String;)V")
_NULL_CHECK = (
    "kotlin/jvm/internal/Intrinsics#",
    "checkNotNullParameter",
    "(Ljava/lang/Object;Ljava/lang/String;)V",
)


def _in_module(symbol: str) -> list:
    """A method of this module with a scanned body: what makes a call to it a resolved
    `call_edges` row."""
    return [
        SymbolFact(
            document_id="doc_1", symbol=symbol, construct_kind="method", enclosing=_MODULE + _FILE
        ),
        MethodReturnFact(document_id="doc_1", method=symbol, ordinal=0, value=None),
    ]


@pytest.mark.declines("ktor-client")
@pytest.mark.pins("ktor.a-block-handing-its-receiver-to-MODULE-code-declines")
def test_a_block_handing_its_receiver_to_module_code_declines(tmp_path: Path):
    """`HttpClient(CIO) { configure(this) }`, `configure` a method of this module: its body
    is scanned and not followed, so it may set the base, and the client is not read as having
    none. The same module call handed something else (`log("x")`) is no such hand-off."""
    handed = [
        *_in_module(_CONFIGURE),
        *_plain_client(
            [
                _in_client_block(
                    0,
                    (_FILE, "configure", _CONFIGURE_JVM),
                    [CallArgument(kind="parameter", value=0)],
                )
            ]
        ),
    ]
    assert _client_rows(tmp_path / "handed", handed) == [_DECLINED_ROW]
    other = [
        *_in_module(_LOG),
        *_plain_client(
            [_in_client_block(0, (_FILE, "log", "(Ljava/lang/String;)V"), [_base("x")])]
        ),
    ]
    assert _client_rows(tmp_path / "other", other) == [_BASED_ROW]


def test_the_null_check_on_the_receiver_does_not_decline(tmp_path: Path):
    """Kotlin opens every block body with `Intrinsics.checkNotNullParameter(this, …)`: a
    library call handed the receiver, which `may_set_base` does not list, so a plain client
    keeps its declared base."""
    facts = _plain_client(
        [
            _in_client_block(
                0, _NULL_CHECK, [CallArgument(kind="parameter", value=0), _base("$this$HttpClient")]
            )
        ]
    )
    assert _client_rows(tmp_path, facts) == [_BASED_ROW]
