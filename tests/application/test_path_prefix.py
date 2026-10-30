"""The configured path prefix's REFUSALS (spec 2026-10-18 §3, `OI-148`).

The happy path is pinned end to end by
`tests/e2e/test_rest_inbound_delivered.py::test_a_configured_context_path_and_servlet_path_reach_the_published_rows`,
which asserts on rows derived from real bytecode. What that test cannot reach is the cases
where a prefix must NOT be applied, and those are where this pass could publish an address
no environment serves — so they are unit-tested here against the rules themselves.
"""

import json
from pathlib import Path

import pytest

from sextant.application.ports.catalogs import Catalog
from sextant.application.resolve.path_prefix import (
    _agreed,
    _ant_matches,
    _composed,
    _for_handler,
    _in_range,
    _Installed,
    _matches_a_package,
    _version_admits,
    apply_path_prefixes,
)
from sextant.application.resolve.values import ValueIndex
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import Document, ModuleFact
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace


def test_a_key_every_environment_agrees_on_is_the_prefix():
    """The ordinary case, and the one `spring-petclinic-rest` has: five environments, all
    `/petclinic/`."""
    config = {
        "server.servlet.context-path": {env: "/petclinic/" for env in ("default", "h2", "mysql")}
    }
    assert _agreed(config, "server.servlet.context-path") == "/petclinic/"


def test_a_key_the_environments_DISAGREE_about_is_refused():
    """**The fabrication this pass could commit.** `prod` serving `/shop` while `dev` serves
    `/` is two addresses, and picking either publishes one environment's path for the
    other's rows — at `resolved`, where nothing says to doubt it.

    Refused rather than resolved by preference, which leaves the row exactly as it was
    before this pass existed. `derived_resource._base_path` carries the richer treatment for
    `spring.data.rest.base-path` (the expression plus a divergence question) and no corpus
    has produced a divergent PREFIX to measure it against — so the conservative half ships
    and the ledger stays where it already works.
    """
    config = {"server.servlet.context-path": {"dev": "/", "prod": "/shop"}}
    assert _agreed(config, "server.servlet.context-path") is None
    assert _composed(["server.servlet.context-path"], config) == ""


def test_a_key_no_environment_declares_contributes_nothing():
    """The framework's own default is empty, so a module configuring none derives its paths
    at `/` — which is why no catalog may `require` these keys."""
    assert _composed(["server.servlet.context-path"], {}) == ""


def test_the_keys_compose_in_declaration_order_and_the_separators_normalise():
    """`/petclinic/` + `/api` is `/petclinic/api`, never `/petclinic//api`. The measured
    value in a pinned corpus ends in a separator, so this is the real input rather than a
    defensive case."""
    config = {
        "server.servlet.context-path": {"default": "/petclinic/"},
        "spring.mvc.servlet.path": {"default": "/api"},
    }
    assert (
        _composed(["server.servlet.context-path", "spring.mvc.servlet.path"], config)
        == "/petclinic/api"
    )
    # Reversed declaration order reverses the composition: the order is the model's, not
    # alphabetical and not the config file's.
    assert (
        _composed(["spring.mvc.servlet.path", "server.servlet.context-path"], config)
        == "/api/petclinic"
    )


def test_a_value_that_is_only_separators_contributes_nothing():
    """`server.servlet.context-path=/` is the default spelled out, and prefixing with it
    would turn every path into `//orders`."""
    assert (
        _composed(["server.servlet.context-path"], {"server.servlet.context-path": {"d": "/"}})
        == ""
    )


@pytest.mark.pins("path_prefix.a-version-outside-the-measured-range-takes-no-prefix")
def test_a_module_whose_version_is_outside_the_range_takes_no_prefix():
    """Boot 1 spells the key `server.context-path`, and the shipped model declares only the
    Boot 2+ spellings (CP-38 measured 2.7.18, 3.5.14, 4.1.1; no Boot 1 jar was opened). A
    range read as "everything" would apply a key measured on Boot 2 to a module that reads a
    different one — the version is in the table precisely so that cannot happen."""
    entry = {
        "framework": "org.springframework.boot",
        "versions": ">=2.0",
        "keys": [],
        "protocols": [],
    }
    assert not _version_admits(
        entry, {"org.springframework.boot:spring-boot-starter-web": "1.5.22"}
    )
    assert _version_admits(entry, {"org.springframework.boot:spring-boot-starter-webmvc": "4.1.1"})

    reactive = {
        "framework": "org.springframework.boot",
        "versions": ">=2.0 <4.0",
        "keys": [],
        "protocols": [],
    }
    assert _version_admits(
        reactive, {"org.springframework.boot:spring-boot-starter-webflux": "3.5.14"}
    )
    # 4.x reactive is outside what CP-38 could measure — `spring-boot-webflux` is in no
    # local repository — so the row declines rather than claiming it.
    assert not _version_admits(
        reactive, {"org.springframework.boot:spring-boot-starter-webflux": "4.1.1"}
    )


def test_an_unrecorded_version_admits_the_entry_and_the_configuration_decides():
    """The ruling of 2026-10-18: a module records no framework version surprisingly often —
    `ruoyi-vue-pro` records none, its versions coming from an imported BOM and a
    `${revision}` property — so an absent version must not mean "no prefix". A module
    configures one framework generation, so at most one spelling of a key can be present and
    the configuration decides. Following the chain to the real version is the direction
    (`OI-139`, `OI-8`); this is what keeps such a module working meanwhile."""
    entry = {
        "framework": "org.springframework.boot",
        "versions": ">=2.0",
        "keys": [],
        "protocols": [],
    }
    assert _version_admits(entry, {})
    assert _version_admits(entry, {"com.example:unrelated": "1.0.0"})


def test_a_qualifier_compares_as_the_release_it_qualifies():
    assert _in_range("2.7.18-RC1", ">=2.0")
    assert _in_range("4.1.1", ">=2.0")
    assert not _in_range("1.5.22", ">=2.0")


def test_an_unreadable_version_clause_raises_rather_than_admitting_everything():
    """A clause this cannot parse is a mistake in a file written FOR Sextant, and "admit
    everything" is the one way it must not degrade — that would apply a prefix measured on
    one framework version to every other."""
    with pytest.raises(ValueError, match="unreadable version clause"):
        _in_range("2.7.18", "~>2.0")


# ---------------------------------------------------------------------------
# §4: the prefix a module INSTALLS, per controller package
# ---------------------------------------------------------------------------
#
# The happy path is pinned end to end by
# `tests/e2e/test_rest_inbound_delivered.py::test_a_prefix_installed_by_package_reaches_the_rows_it_moves`,
# on four controllers in four packages and two declaration shapes. What that fixture cannot
# reach is the two cases where a wrong row would be published rather than a right one
# missed — a pattern read as a prefix test, and a `match` call that is about something other
# than a package.


@pytest.mark.pins("path_prefix.a-pattern-segment-matches-a-WHOLE-segment")
def test_a_pattern_segment_matches_a_whole_package_component_and_not_a_prefix_of_one():
    """**The wrong row this refuses.** `ruoyi`'s own pattern is `**.controller.admin.**`, and
    a module with an `…controller.administration` package is one rename away. A prefix test
    matches it and publishes every one of its endpoints under `/admin-api` — an address the
    server does not serve them at, at `resolved`.

    Spring reads these with `new AntPathMatcher(".")`, so a segment is a package component:
    `*` spans characters inside one, `**` spans whole components.
    """
    assert _ant_matches("**.controller.admin.**", "com.acme.pp.controller.admin")
    assert _ant_matches("**.controller.admin.**", "com.acme.pp.controller.admin.orders")
    assert not _ant_matches("**.controller.admin.**", "com.acme.controller.administration.user")
    assert not _ant_matches("**.controller.admin.**", "com.acme.controller.app")
    # `*` is characters within one component, never the separator.
    assert _ant_matches("com.acme.*.admin", "com.acme.pp.admin")
    assert not _ant_matches("com.acme.*.admin", "com.acme.pp.inner.admin")
    assert _ant_matches("com.acme.pp?.admin", "com.acme.pp1.admin")
    # A pattern with no wildcard is the package itself, children excluded.
    assert _ant_matches("com.acme.admin", "com.acme.admin")
    assert not _ant_matches("com.acme.admin", "com.acme.admin.orders")


def test_a_handler_no_pattern_names_takes_no_prefix_and_one_two_patterns_claim_takes_none():
    """Three refusals, all of them "publish the address the row already had".

    The first is the ordinary case: a module prefixes its controller packages and leaves
    everything else — Actuator's own handlers, a framework's error controller — alone.

    The second is the predicate's own annotation conjunct: a class in a matching package that
    does not carry the annotation is a class the framework never asks the predicate about.

    The third is a contradiction the facts cannot settle. The framework applies the FIRST
    matching entry of a `LinkedHashMap`, and nothing in the facts records that order, so two
    prefixes claiming one package are refused rather than resolved by a coin toss — the rule
    `_agreed` applies to a divergent configuration key, one source over.
    """
    marker = "org/springframework/web/bind/annotation/RestController#"
    installed = (
        _Installed(prefix="/admin-api", pattern="**.controller.admin.**", annotation=marker),
        _Installed(prefix="/app-api", pattern="**.controller.app.**", annotation=marker),
    )
    handler = "sextant-jvm maven acme/orders 1 com/acme/pp/controller/admin/C#get(sig_1)."
    annotated = {"com/acme/pp/controller/admin/C#": frozenset({marker})}
    assert _for_handler(handler, installed, annotated) == "/admin-api"
    other = "sextant-jvm maven acme/orders 1 org/springframework/boot/actuate/W#links(sig_1)."
    assert _for_handler(other, installed, annotated) == ""
    # The same handler, in the same matching package, carrying no such annotation: a config
    # class, an entity, a functional-routing bean — none of them rows this mapping serves.
    assert _for_handler(handler, installed, {}) == ""
    both = (
        _Installed(prefix="/one", pattern="**.controller.admin.**", annotation=marker),
        _Installed(prefix="/two", pattern="**.controller.**", annotation=marker),
    )
    assert _for_handler(handler, both, annotated) == ""
    # One prefix reached by two patterns is NOT a contradiction: the answer is the same.
    agreeing = (
        _Installed(prefix="/admin-api", pattern="**.controller.admin.**", annotation=marker),
        _Installed(prefix="/admin-api", pattern="**.controller.**", annotation=marker),
    )
    assert _for_handler(handler, agreeing, annotated) == "/admin-api"


@pytest.mark.pins("path_prefix.a-package-predicate-is-what-identifies-a-declaration")
def test_a_match_call_that_is_not_about_a_package_is_not_a_prefix_declaration():
    """**The discriminator, and the only thing standing between this reader and a guess.**

    What identifies a prefix declaration is a lambda matching a pattern against *a class's
    package name* — `Package#getName` on `Class#getPackage`, measured at ordinals 1, 2 and 3
    of the fixture's lambda. A module has other `match` calls; one of them matching a
    REQUEST PATH, inside a lambda handed to some other map, is not a declaration that
    `/v1/**` prefixes anything.

    Both indexes below are synthetic and minimal: the two `match` sites differ in nothing but
    what produced their second argument.
    """
    entry = {
        "matcher": {"owners": ("org/springframework/util/AntPathMatcher#",), "name": "match"},
        "package_of": {"owners": ("java/lang/Class#",), "name": "getPackage"},
        "package_name": {"owners": ("java/lang/Package#",), "name": "getName"},
    }
    caller = "sextant-jvm maven acme/orders 1 com/acme/C#lambda$0(sig_1)."

    def site(ordinal, owner, name, arguments, receiver=None):
        return {
            "caller": caller,
            "ordinal": ordinal,
            "owner": owner,
            "name": name,
            "arguments": arguments,
            "receiver": receiver,
        }

    matching = site(
        3,
        "org/springframework/util/AntPathMatcher#",
        "match",
        [
            {"kind": "string", "value": "**.controller.admin.**"},
            {"kind": "unresolved", "source": 9},
        ],
    )
    package_of = {
        **site(1, "java/lang/Class#", "getPackage", []),
        # The lambda's own class parameter, which is what the predicate is ABOUT.
        "receiver_parameter": 1,
    }
    package_name = site(2, "java/lang/Package#", "getName", [], receiver=7)
    index = _index(
        sites={(caller, 1): package_of, (caller, 2): package_name, (caller, 3): matching},
        producers={(caller, 7): (1,), (caller, 9): (2,)},
    )
    # The answer is WHICH PARAMETER the predicate is about — parameter 1 here — because the
    # annotation conjunct must be about the same class to count.
    assert _matches_a_package(index, matching, entry) == 1

    # The same call, its second argument produced by something that is not a package name.
    lowercased = site(2, "java/lang/String#", "toLowerCase", [], receiver=7)
    assert None is _matches_a_package(
        _index(
            sites={(caller, 1): package_of, (caller, 2): lowercased, (caller, 3): matching},
            producers={(caller, 7): (1,), (caller, 9): (2,)},
        ),
        matching,
        entry,
    )
    # A package name whose receiver came from somewhere other than `Class#getPackage` —
    # a `Package` handed in rather than taken off the class the predicate is asked about.
    assert None is _matches_a_package(
        _index(
            sites={(caller, 2): package_name, (caller, 3): matching},
            producers={(caller, 9): (2,)},
        ),
        matching,
        entry,
    )


def _index(sites, producers) -> ValueIndex:
    """A `ValueIndex` holding only the two reads `_matches_a_package` makes. Every other
    field is empty rather than plausible: a fold this test did not measure has no business
    answering anything."""
    return ValueIndex(
        sites=sites,
        receivers={},
        producers=producers,
        returns={},
        callers={},
        parameters={},
        constants={},
        produced={},
        writers={},
        returned_values={},
        reached=frozenset(),
    )


@pytest.mark.pins("endpoints.an-attached-entry-follows-its-row-by-ROW-ID")
def test_a_header_written_at_mint_time_follows_its_row_through_the_prefix(tmp_path):
    """Review Focus 4 of the 2026-10-30 plan (ruling 7). `fluent` and `single_call` write an
    `endpoint_metadata` row in the same pass that mints its endpoint, so the entry is written
    against `GET /x` before the configured prefix has run. The prefix then moves the row to
    `/shop/x`, and the entry moves with it: it is bound to the row's `row_id` when written, and
    the prefix rewrites both by that id. Left at `/x`, it would name an address nothing serves,
    and a reader joining the two tables on the address would lose it."""
    workspace = _module_workspace(tmp_path, ["org.springframework:spring-webmvc"])
    workspace.derive("endpoint_metadata_reset")
    handler = "sextant-jvm maven com.acme/shop 1.0.0 com/acme/Shop#x(sig_00000001)."
    workspace._connection.execute(
        "INSERT INTO endpoints (row_id, protocol, direction, method, path, handler, catalog_id) "
        "VALUES (1, 'http', 'inbound', 'GET', '/x', ?, 'invented')",
        [handler],
    )
    workspace.derive(
        "endpoint_metadata_insert",
        rows=[
            {
                "protocol": "http",
                "direction": "inbound",
                "method": "GET",
                "path": "/x",
                "caller": handler,
                "kind": "header",
                "name": "X-Ver",
                "value": "2",
                "resolution": "resolved",
                "evidence": "compiler",
                "requirement": None,
            }
        ],
    )
    workspace._connection.execute(
        "INSERT INTO resolved_config (key, value, source, environment) "
        "VALUES ('server.servlet.context-path', '/shop', 'application.properties', 'default')"
    )
    catalog = Catalog(
        id="invented",
        style="annotation",
        protocol="http",
        direction="inbound",
        requires=(),
        matches={},
        source=Path("tests/invented.yml"),
        wrappers=[],
        nullability={},
        serialization={},
        known_types=[],
        dispatcher="spring",
        server_model=YamlCatalogSource(catalogs_dir()).server_model(),
    )
    apply_path_prefixes(workspace, [catalog])
    (endpoint_id,) = workspace._connection.execute(
        "SELECT row_id FROM endpoints WHERE path = '/shop/x'"
    ).fetchone()
    metadata = workspace._connection.execute(
        "SELECT path, row_id FROM endpoint_metadata"
    ).fetchall()
    workspace.close()

    assert metadata == [("/shop/x", endpoint_id)]


def _module_workspace(tmp_path: Path, coordinates: list[str]) -> DuckDbWorkspace:
    """A workspace holding one module fact with these dependency coordinates — the facts
    `_web_stack` reads the module's stack off — and nothing else yet."""
    document = Document(
        document_id="doc_module",
        relative_path="module",
        module_id="com.acme:shop",
        language="module",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="detector",
        content_hash="sha256:a",
        origin_entry="com.acme/shop",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    write_fact_file(
        tmp_path / "facts" / "module.jsonl",
        document,
        [
            ModuleFact(
                document_id="doc_module",
                module_id="com.acme:shop",
                module_kind="service",
                languages=["java"],
                source_roots=["src/main/java"],
                output_dirs=["target/classes"],
                dependency_coordinates=coordinates,
                dependency_versions={},
            )
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    return workspace


def _served(
    workspace: DuckDbWorkspace,
    config: dict[str, str],
    dispatcher: str | None,
    *,
    keep_open: bool = False,
) -> str:
    """The path one inbound `GET /x` row is published at, after the shipped server model has
    been applied under `config`, the row derived by a catalog declaring `dispatcher`."""
    workspace._connection.execute(
        "INSERT INTO endpoints (row_id, protocol, direction, method, path, handler, catalog_id) "
        "VALUES (1, 'http', 'inbound', 'GET', '/x', 'h', 'invented')"
    )
    for key, value in config.items():
        workspace._connection.execute(
            "INSERT INTO resolved_config (key, value, source, environment) "
            "VALUES (?, ?, 'application.properties', 'default')",
            [key, value],
        )
    catalog = Catalog(
        id="invented",
        style="annotation",
        protocol="http",
        direction="inbound",
        requires=(),
        matches={},
        source=Path("tests/invented.yml"),
        wrappers=[],
        nullability={},
        serialization={},
        known_types=[],
        dispatcher=dispatcher,
        server_model=YamlCatalogSource(catalogs_dir()).server_model(),
    )
    apply_path_prefixes(workspace, [catalog])
    (path,) = workspace._connection.execute("SELECT path FROM endpoints").fetchone()
    if not keep_open:
        workspace.close()
    return str(path)


def test_a_reactive_module_ignores_a_leftover_servlet_context_path(tmp_path):
    """Ruling 3. A WebFlux module serves under `spring.webflux.base-path` and nothing else:
    CP-57 set `server.servlet.context-path=/c` beside `spring.webflux.base-path=/w` on a
    reactive app and every handler — controller, functional route, Gateway route, Actuator —
    answered at `/w/…`, never `/c/…`. The context path is a servlet container's, and a
    reactive app has none.

    The stack is read the way Spring Boot deduces it, off the module's dependencies:
    `spring-webflux` without `spring-webmvc` or Jersey's servlet container is reactive.
    Measured before the fix: published at `/c/x`, the servlet entry winning because it is
    declared first."""
    workspace = _module_workspace(tmp_path, ["org.springframework:spring-webflux"])
    config = {"server.servlet.context-path": "/c", "spring.webflux.base-path": "/w"}

    assert _served(workspace, config, "spring") == "/w/x"


def test_a_catalog_without_a_dispatcher_takes_no_configured_prefix(tmp_path):
    """Ruling 3. A configured prefix belongs to a dispatcher, and a catalog that names none —
    Quarkus, Micronaut, Javalin, Ktor — is served by something Spring Boot's keys do not
    configure. Measured before the fix: `/shop/x`, every inbound row taking the prefix its
    protocol had."""
    workspace = _module_workspace(tmp_path, ["org.springframework:spring-webmvc"])

    assert _served(workspace, {"server.servlet.context-path": "/shop"}, None) == "/x"


def test_a_module_listing_only_the_starter_takes_the_servlet_prefixes(tmp_path):
    """A dependency set read off the build file (`dependency_source: declared`) names the
    starter the module asked for and none of its transitives, so `spring-webmvc` is absent
    though the module runs on it. The server model's `stacks` list the starters beside the
    framework artifacts, so the stack is still found. Measured before: `/x`, the module read
    as running no web stack."""
    workspace = _module_workspace(tmp_path, ["org.springframework.boot:spring-boot-starter-web"])
    config = {"server.servlet.context-path": "/shop", "spring.mvc.servlet.path": "/api"}

    assert _served(workspace, config, "spring") == "/shop/api/x"


def test_a_module_whose_stack_is_unread_files_a_question_and_takes_no_prefix(tmp_path):
    """A module that configures a prefix, has rows a dispatcher serves, and carries none of
    the coordinates any stack is read off. Which keys reach its rows depends on the stack —
    a leftover context path does nothing on a reactive app (CP-57) — so no prefix is applied,
    and the keys that were not are named in one `web_stack` question rather than dropped
    silently."""
    workspace = _module_workspace(tmp_path, ["com.acme:unrelated"])
    path = _served(
        workspace,
        {"server.servlet.context-path": "/shop", "spring.mvc.servlet.path": "/api"},
        "spring",
        keep_open=True,
    )
    questions = [dict(row) for row in workspace.query("open_questions")]
    workspace.close()

    assert path == "/x"
    assert [(q["protocol"], q["method"], q["path"], q["question"]) for q in questions] == [
        ("http", None, None, "web_stack")
    ]
    candidates = json.loads(str(questions[0]["candidates"]))
    assert {c["stack"]: c["keys"] for c in candidates} == {
        "servlet": ["server.servlet.context-path", "spring.mvc.servlet.path"],
    }
