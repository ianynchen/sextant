"""The configured path prefix's REFUSALS (spec 2026-10-18 §3, `OI-148`).

The happy path is pinned end to end by
`tests/e2e/test_rest_inbound_delivered.py::test_a_configured_context_path_and_servlet_path_reach_the_published_rows`,
which asserts on rows derived from real bytecode. What that test cannot reach is the cases
where a prefix must NOT be applied, and those are where this pass could publish an address
no environment serves — so they are unit-tested here against the rules themselves.
"""

import pytest

from sextant.application.resolve.path_prefix import (
    _agreed,
    _composed,
    _in_range,
    _version_admits,
)


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
