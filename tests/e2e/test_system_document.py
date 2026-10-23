"""`system analyze` end to end, and the document it writes.

**The document is the result, not the table** (user ruling, 2026-10-17). So these tests read
the markdown, not the `links` rows — a green table behind a blank document is the failure this
file exists to catch.
"""

import shutil

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli

REACTOR = FIXTURES / "reactor-twoservice"


@pytest.fixture(scope="module")
def system_document(tmp_path_factory: pytest.TempPathFactory) -> str:
    """`system.md` for the two-module reactor, through the CLI both times.

    Analysed in a private COPY: both commands write into the root they are given —
    `modules.json`, every module workspace, the system workspace and the document — so
    pointing them at `fixtures/` would have two tests racing in one tree under xdist.
    `copytree` keeps `target/` and the stamp's mtime, so neither command runs `mvn`.
    """
    # The REACTOR root, not its modules one by one: `mvn compile` there builds
    # every module, which is also how CI primes it (`fixture_build`'s own list).
    compile_fixture(REACTOR)
    reactor = tmp_path_factory.mktemp("system") / "reactor-twoservice"
    shutil.copytree(REACTOR, reactor)
    runner = CliRunner()
    analyzed = runner.invoke(cli, ["module", "analyze", str(reactor)])
    assert analyzed.exit_code == 0, analyzed.output
    linked = runner.invoke(cli, ["system", "analyze", str(reactor)])
    assert linked.exit_code == 0, linked.output
    return (reactor / ".sextant" / "render" / "system.md").read_text(encoding="utf-8")


@pytest.mark.pins("stitch.the-SYSTEM-DOCUMENT-carries-the-link-not-only-the-table")
def test_the_document_states_the_link_both_sides_of_the_call_support(system_document):
    """The whole point of the tier, in one row of one document:

        restTemplate.getForObject("http://billing/balances", …)   // orders-api
        @GetMapping("/balances")                                   // billing-api

    Before this, Sextant published both facts in two documents and joined neither. The row
    names the caller, the service, the route and how much the match is worth — and `billing`
    resolving to `billing-api` is the alias index doing its job, because the client states a
    registered name and the participant is its artifactId.
    """
    assert "## Links" in system_document
    assert "`orders-api` GET `/balances`" in system_document
    assert "`billing-api`" in system_document
    assert "resolved · declared" in system_document


@pytest.mark.pins("stitch.the-document-names-every-REFUSAL-with-its-reason")
def test_the_document_states_why_each_unmatched_call_matched_nothing(system_document):
    """`M06`'s honesty obligation, as a SECTION rather than a footnote.

    Two calls match nothing and they fail for different reasons, so the document gives each
    its own sentence rather than one count:

    * `http://payments/charges` — no participant is called `payments`. Falling through to the
      path here would link a module that merely serves `/charges`, which is fabrication.
    * `base + "/balances"` — the authority went unread, and `billing-api` serves `/balances`
      **uniquely**. The refusal costs a real link on purpose (decision 6).

    A reader who cannot tell these apart cannot act on either: the first is a dependency
    leaving the system, the second is an analysis limit.
    """
    assert "## Outbound endpoints that matched nothing" in system_document
    assert "which is not a participant" in system_document
    assert "authority went unread" in system_document
    # The three readings an unmatched outbound row can have, stated rather than left to the
    # reader to guess at.
    assert "a service outside this system" in system_document


@pytest.mark.pins("stitch.UNCALLED-inbound-endpoints-are-a-section-of-their-own")
def test_the_document_lists_uncalled_inbound_endpoints_separately(system_document):
    """`M06` requires unmatched outbound and uncalled inbound reported SEPARATELY, because
    they are different questions: one is a dependency this system may not have captured, the
    other is a route nothing here calls. `/ledgers` is the second kind, and the document
    declines to say whether it is dead or called from outside — it cannot know."""
    assert "## Inbound endpoints nothing in this system calls" in system_document
    assert "GET `/ledgers`" in system_document
    assert "Either dead, or called from outside" in system_document
    # And the called one is NOT in that list, which is what makes the section a finding
    # rather than an inventory.
    uncalled_section = system_document.split("nothing in this system calls")[1]
    assert "/balances" not in uncalled_section


@pytest.mark.pins("stitch.the-document-names-the-ENVIRONMENT-it-resolved-for")
def test_the_document_says_which_environment_it_resolved_values_for(system_document):
    """A module's registered name and a gateway's routes are both configuration, so a link
    is a statement about ONE environment. A document that did not say which would be
    unreadable the first time two environments disagree — and `M06` step 0's rule is that
    every comparison uses the values resolved for the one named."""
    assert "`default` environment" in system_document


@pytest.mark.pins("conditions.a-LINK-states-where-its-inbound-endpoint-exists")
def test_a_link_to_a_conditional_endpoint_states_where_the_endpoint_exists(system_document):
    """`BalanceController` is under `@Profile("prod")` and `billing-api` resolves two
    environments (`default`, `prod`). Ruling 2 (spec 2026-10-21-conditional-controllers): the
    link is matched and kept as any other — nothing about either side's implementation or
    environment enters the join — and the condition, a property of the INBOUND endpoint,
    travels with it as data: the row states where the endpoint exists, read from
    `billing-api`'s own `endpoint_conditions` through the federated view."""
    row = next(
        line for line in system_document.splitlines() if "`orders-api` GET `/balances`" in line
    )
    assert "`billing-api`" in row, row
    assert "exists in `prod`; not in `default`" in row, row


@pytest.mark.pins("conditions.a-LINK-states-where-its-outbound-caller-exists")
def test_a_link_from_a_conditional_caller_states_where_the_call_exists(system_document):
    """`BillingClient` is a `@Component` under `@Profile("prod")` and `orders-api` resolves two
    environments (`default`, `prod`), so the call exists in `prod` only (spec 2026-10-22-
    conditional-beans §3). The link is matched and kept as any other; the row states the
    OUTBOUND side's existence beside the calling side, as it states the inbound side's beside
    the endpoint — from `orders-api`'s own rows through the federated views, the answer being
    `bean_presence`'s."""
    row = next(
        line for line in system_document.splitlines() if "`orders-api` GET `/balances`" in line
    )
    assert "called only in `prod`; not in `default`" in row, row
    # Each side states its own: the endpoint's existence stays beside the endpoint.
    assert row.index("called only in") < row.index("`billing-api`"), row
    assert "exists in `prod`; not in `default`" in row.split("`billing-api`")[1], row


def test_a_reactor_nobody_analyzed_is_refused_naming_the_command_to_run(tmp_path):
    """The `no analysis` refusal (M00's own rule), and why it is a refusal rather than an
    empty document: "no links" would be a claim about the system, when the truth is that
    nothing has been read yet.

    No `pins` marker: the refusal is one `if` over a path's existence, and a guard that
    disabled it would make `system_analyze` raise further down on a missing file rather than
    return a wrong answer — a crash, not a false fact, so there is nothing for a guard to
    measure.
    """
    result = CliRunner().invoke(cli, ["system", "analyze", str(tmp_path)])
    assert result.exit_code != 0
    assert "no analysis found" in result.output
    assert "sextant module analyze" in result.output
