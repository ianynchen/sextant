"""A gateway route's prefix joined to the paths the service it names serves (Task 4).

`fixtures/reactor-gateway` is two routes to one service differing only in `StripPrefix`, so
the composition and the refusal that gates it are measured side by side in one run:

    /good/**  StripPrefix=1   prefix is ONE segment  -> composed
    /a/b/**   StripPrefix=1   prefix is TWO segments -> refused

**This is a path prefix, not a rewrite engine** — the user's own correction, and the reason
`M06`'s "no runtime prediction" rule is kept. The rule `StripPrefix` applies is measured in
`scripts/probes/cp40_strip_prefix.md` against two releases either side of Spring Cloud's
module rename, and all this code does is refuse wherever the configuration does not license
the composition.
"""

import shutil

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli

REACTOR = FIXTURES / "reactor-gateway"


@pytest.fixture(scope="module")
def gateway_document(tmp_path_factory: pytest.TempPathFactory) -> str:
    """`system.md` for the gateway reactor, through the CLI both times.

    A private copy: both commands write into the root they are given, so pointing them at
    `fixtures/` would race another test under xdist.
    """
    compile_fixture(REACTOR / "orders")
    reactor = tmp_path_factory.mktemp("gateway") / "reactor-gateway"
    shutil.copytree(REACTOR, reactor)
    runner = CliRunner()
    analyzed = runner.invoke(cli, ["module", "analyze", str(reactor)])
    assert analyzed.exit_code == 0, analyzed.output
    linked = runner.invoke(cli, ["system", "analyze", str(reactor)])
    assert linked.exit_code == 0, linked.output
    return (reactor / ".sextant" / "render" / "system.md").read_text(encoding="utf-8")


@pytest.mark.pins("stitch.a-gateway-ROUTE-PREFIX-joins-the-paths-the-service-serves")
def test_a_route_prefix_composes_with_the_served_path(gateway_document):
    """The composition, and it is the same join a class-level prefix already makes:

        Path=/good/**  ->  lb://orders        # the gateway declares
        @GetMapping("/orders")                 # `orders` serves
        GET /good/orders                       # the gateway's own address

    A class-level `@RequestMapping("/owners")` in front of a method's `@GetMapping` makes
    `/owners/{ownerId}`, and `setPathPrefixes` does it per package; this is that shape with
    the two halves in two MODULES. Nothing is rewritten and no router is simulated — the
    prefix is read off the predicate and the path off the other module's own row.

    **`resolved`, not `narrowed`**, and on the user's ruling: every endpoint the route reaches
    genuinely is reachable, so each pair is its own certain link. `narrowed` would tell a
    reader there is doubt about which one, and there is none.
    """
    assert "| `edge` GET `/good/orders` | `orders` | GET `/orders` | resolved · declared |" in (
        gateway_document
    )


@pytest.mark.pins("stitch.a-STRIP-that-disagrees-with-the-prefix-REFUSES-the-composition")
def test_a_route_whose_strip_disagrees_with_its_prefix_is_refused(gateway_document):
    """The gate, with both numbers in the reason.

        Path=/a/b/**   filters: [StripPrefix=1]

    The prefix is two segments and the filter removes one, so a request to `/a/b/orders`
    arrives at the service as `/b/orders` — which `orders` does not serve. Composing anyway
    would publish `/a/b/orders` as an address reaching `GET /orders`, and no request takes
    that path. Measured off the jar (CP-40): the filter keeps every segment whose index is
    `>= parts`, so the two numbers must agree or the composition is not prefix-plus-path.

    **The dependency is NOT lost**, which is what makes refusing cheap: the `lb://orders`
    row still links `edge` to `orders` at participant level, and only the claim about which
    endpoints the route reaches is withheld.
    """
    assert "## Gateway routes whose prefix was not composed" in gateway_document
    assert "`/a/b/**`" in gateway_document
    assert "strips 1 path segment and its prefix has 2" in gateway_document
    # The composed route is NOT in the refusal section, which is what makes it a finding
    # rather than a list of every route.
    refused = gateway_document.split("whose prefix was not composed")[1]
    assert "/good/" not in refused
    # And the participant-level link survives the refusal.
    assert "`lb://orders`" in gateway_document


@pytest.mark.pins("stitch.a-refused-route-composes-NO-endpoint-link")
def test_a_refused_route_publishes_no_endpoint_link_for_that_service(gateway_document):
    """The refusal has to be a refusal. `orders` serves exactly one route, so if the
    mismatched prefix had composed anyway there would be a second endpoint link — `/a/b/orders`
    — beside the good one. There is not.

    One service, one served route, two gateway routes: the fixture is built so this count is
    unambiguous."""
    composed = [
        line
        for line in gateway_document.splitlines()
        if line.startswith("| `edge` ") and "`orders`" in line and "no route" not in line
    ]
    assert len(composed) == 1, composed
    assert "/good/orders" in composed[0]
