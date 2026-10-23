"""The gateway prefix join on synthetic configuration rows — the cases a reactor fixture
cannot state one at a time without a fixture per case.

The two-route fixture (`tests/e2e/test_gateway_prefix.py`) proves the join end to end; this
file pins the rules the join applies, each against the shape that produced a false fact or a
wrong refusal when it was found (review of PR #56, 2026-10-20).
"""

import pytest

from sextant.application.stitch import gateway_links, route_model
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir

PREFIX = "spring.cloud.gateway.server.webflux.routes"


@pytest.fixture(scope="module")
def model():
    catalog = next(
        c
        for c in YamlCatalogSource(catalogs_dir()).load()
        if c.id == "spring-cloud-gateway-properties"
    )
    found = route_model(catalog.matches)
    assert found is not None
    return found


def _route(index: int, **fields: str) -> list[dict[str, object]]:
    return [
        {
            "participant": "edge",
            "key": f"{PREFIX}[{index}].{key}",
            "value": value,
            "environment": "default",
        }
        for key, value in fields.items()
    ]


def _served(method: str, path: str) -> dict[str, object]:
    return {
        "participant": "orders",
        "protocol": "http",
        "direction": "inbound",
        "method": method,
        "path": path,
        "peer": None,
        "handler": "h",
        "caller": None,
        "resolution": "resolved",
    }


NAMES = {"edge": "edge", "orders": "orders"}
BOTH_VERBS = [_served("GET", "/orders"), _served("POST", "/orders")]


@pytest.mark.pins("stitch.a-route-restricted-to-some-VERBS-composes-only-those")
def test_a_route_restricted_to_get_composes_no_post_link(model):
    """**Measured as a false fact in review:**

        - id: reads
          uri: lb://orders
          predicates: [ Path=/o/**, Method=GET ]
          filters:    [ StripPrefix=1 ]

    `orders` serves `GET` and `POST /orders`. The route forwards only `GET`, so a composed
    `POST /o/orders -> POST /orders` is an address the gateway rejects before it forwards —
    and the first version published it. The catalog declares the `Method` predicate for
    exactly this and the join now reads it; a route declaring none forwards every verb.
    """
    links, refusals = gateway_links(
        _route(
            0,
            **{
                "predicates[0]": "Path=/o/**",
                "predicates[1]": "Method=GET",
                "filters[0]": "StripPrefix=1",
                "uri": "lb://orders",
            },
        ),
        BOTH_VERBS,
        model,
        NAMES,
    )
    assert refusals == ()
    assert [(link.from_method, link.from_path) for link in links] == [("GET", "/o/orders")]


def test_a_route_declaring_no_method_forwards_every_verb(model):
    """The other half of the rule above, so a reader cannot take the restriction as "only GET
    composes": with no `Method` predicate the gateway forwards every verb and both links
    stand. No `pins` marker — this is the pre-existing behaviour the restriction narrows,
    and the guard above already proves the narrowing is live."""
    links, _ = gateway_links(
        _route(
            0,
            **{"predicates[0]": "Path=/o/**", "filters[0]": "StripPrefix=1", "uri": "lb://orders"},
        ),
        BOTH_VERBS,
        model,
        NAMES,
    )
    assert sorted(link.from_method or "" for link in links) == ["GET", "POST"]


def test_a_destination_carrying_a_credential_composes_as_the_bare_name(model):
    """`uri: lb://svc:s3cret@orders` names the service `orders`: Spring Cloud Gateway reads
    the host, and the userinfo is no part of the name (the rule `links.py` applies to the
    same target). Kept, the route composed nothing and nothing said why."""
    links, refusals = gateway_links(
        _route(
            0,
            **{
                "predicates[0]": "Path=/o/**",
                "filters[0]": "StripPrefix=1",
                "uri": "lb://svc:s3cret@orders",
            },
        ),
        BOTH_VERBS,
        model,
        NAMES,
    )
    assert refusals == ()
    assert sorted((link.from_method, link.from_path) for link in links) == [
        ("GET", "/o/orders"),
        ("POST", "/o/orders"),
    ]
