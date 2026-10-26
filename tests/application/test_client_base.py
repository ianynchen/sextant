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
from test_call_engines import _EXTENSION_MATCHES, CATALOGS_DIR, _fluent_catalog, _resolve_fluent

from sextant.application.ports.catalogs import CatalogError
from sextant.application.resolve.shapes.client_base import (
    REPLACE_LAST_SEGMENT,
    client_base_of,
    join_url,
)
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource


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
    CP-54 rows 46-49 and 79-80 measure, the member `url(String)` setter, Ktor's join."""
    catalog = next(c for c in YamlCatalogSource(CATALOGS_DIR).load() if c.id == "ktor-client")
    declared = catalog.matches["client_base"]
    assert "relative_to_client_base" not in catalog.matches
    assert declared["client_arg"] == 1
    assert [(rung["owner"], rung["method"], rung["block_arg"]) for rung in declared["ladder"]] == [
        ("io.ktor.client.HttpClientKt", "HttpClient", 1),
        ("io.ktor.client.HttpClient", "config", 0),
        ("io.ktor.client.plugins.DefaultRequestKt", "defaultRequest", 1),
    ]
    assert (
        declared["setter"]["owner"] == "io.ktor.client.plugins.DefaultRequest$DefaultRequestBuilder"
    )
    assert declared["setter"]["method"] == "url"
    assert declared["setter"]["value_arg"] == 0
    assert declared["join"] == REPLACE_LAST_SEGMENT


_LADDER = {
    "client_arg": 1,
    "ladder": [{"owner": "com.acme.http.ClientKt", "method": "Client", "block_arg": 1}],
    "setter": {"owner": "com.acme.http.Defaults", "method": "url", "value_arg": 0},
    "join": REPLACE_LAST_SEGMENT,
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
