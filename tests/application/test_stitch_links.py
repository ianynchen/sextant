"""The filter chain (M06 steps 1, 2 and 4) on a two-module reactor.

`fixtures/reactor-twoservice` is the smallest system the stitcher can be measured on: one
module calls three addresses, and the three are the three outcomes the chain has to keep
apart — a link, a destination outside the system, and an address whose authority went unread.

The module directories are deliberately not the service names (`orders-api` registers as
`orders`), which is `spring-petclinic`'s own shape and the reason a participant answers to
both its artifactId and the name it registers under.
"""

import json
import shutil

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.application.stitch import match, participants_of, with_registered_names
from sextant.cli.app import cli
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace

REACTOR = FIXTURES / "reactor-twoservice"


@pytest.fixture(scope="module")
def linked(tmp_path_factory: pytest.TempPathFactory):
    """`(links, unmatched)` for the two-module reactor, through the whole real path.

    Analysed at the reactor ROOT, which is what writes `modules.json` — the participant set
    this reads rather than re-walks.
    """
    workspace_root = tmp_path_factory.mktemp("reactor")
    # The REACTOR root, not its modules one by one: `mvn compile` there builds
    # every module, which is also how CI primes it (`fixture_build`'s own list).
    compile_fixture(REACTOR)
    # **A private COPY, because analysing a reactor writes into the reactor.** `modules.json`
    # and every module workspace land under the root being analysed, so two tests pointing at
    # `fixtures/` would race under xdist — the shared-tree failure GUIDELINES §13.9 records
    # three occurrences of. `copytree` keeps `target/` and the stamp's mtime, so no `mvn` runs.
    reactor = workspace_root / "reactor-twoservice"
    shutil.copytree(REACTOR, reactor)
    result = CliRunner().invoke(cli, ["module", "analyze", str(reactor)])
    assert result.exit_code == 0, result.output

    entries = json.loads((reactor / ".sextant" / "modules.json").read_text())["modules"]
    for entry in entries:
        candidate = reactor / str(entry.get("dir") or "") / ".sextant" / "workspace.duckdb"
        entry["location"] = candidate if candidate.exists() else None
        entry["commit_id"] = None
    people = participants_of(entries)
    live = {p.name: p.location for p in people if p.present and p.location is not None}

    key = next(
        (
            c.participant_name_key
            for c in YamlCatalogSource(catalogs_dir()).load()
            if c.participant_name_key
        ),
        None,
    )
    system = DuckDbWorkspace(workspace_root / "system.duckdb")
    try:
        system.federate(live)
        endpoints = system.query("system_endpoints")
        config = system.query("system_config", environment="default")
    finally:
        system.close()
    people = with_registered_names(people, config, key)
    return (*match(people, endpoints), people)


@pytest.mark.pins("stitch.a-PEER-the-client-states-settles-who-before-the-path-picks-the-route")
def test_a_call_to_a_registered_name_links_to_that_participants_route(linked):
    """The link, end to end:

        restTemplate.getForObject("http://billing/balances", …)   // orders-api
        @GetMapping("/balances")                                  // billing-api

    `billing` is not a module directory and not an artifactId — it is what `billing-api`
    registers as, in its own `application.yml`. So the client's `billing` resolves through
    the ALIAS index, and the path then only has to pick the route inside that one
    participant.

    `declared` rather than `name_match`, because the client STATED who it calls: `M06`'s key
    table calls that the strong HTTP case, and the destination is read rather than inferred
    from the shape of the system.
    """
    links, _unmatched, _people = linked
    balances = [link for link in links if link.to_path == "/balances"]
    assert len(balances) == 1, links
    link = balances[0]
    assert link.from_participant == "orders-api"
    assert link.to_participant == "billing-api"
    assert (link.to_method, link.to_path) == ("GET", "/balances")
    assert (link.resolution, link.evidence) == ("resolved", "declared")
    # The participant's OWN name on both ends, never the alias the client happened to write:
    # the row has to join `participants`, and a reader comparing two links must see one
    # spelling per participant.
    assert "billing" not in {link.from_participant, link.to_participant}


@pytest.mark.pins("stitch.a-peer-OUTSIDE-the-system-is-a-finding-not-a-fallback")
def test_a_call_to_a_service_this_system_does_not_contain_links_to_nothing(linked):
    """`http://payments/charges` — and no participant is called `payments`.

    **The dangerous failure here is not refusing; it is falling through.** Had the matcher
    answered "the peer is unknown, so try the path instead", a module serving `/charges`
    would have been linked to a call that does not reach it — `M06`'s fabrication rather
    than imprecision, "and an agent will then reason from it". So an unrecognised peer
    refuses the whole question and the row is `M06`'s own finding: a service outside the
    system, a participant nobody added, or a dependency nobody documented.
    """
    _links, unmatched, _people = linked
    charges = [row for row in unmatched if row.path == "/charges"]
    assert len(charges) == 1, unmatched
    assert "payments" in charges[0].reason
    assert "not a participant" in charges[0].reason


@pytest.mark.pins("stitch.an-UNREAD-authority-is-never-matched-by-path-alone")
def test_an_address_whose_host_went_unread_refuses_even_a_unique_path(linked):
    """The user's decision 6, refused on 2026-10-19, with the hardest case for it:

        restTemplate.getForObject(base + "/balances", …)   // base comes from the caller

    The row is `<host>/balances`, and `billing-api` serves `/balances` **uniquely in this
    reactor**. So uniqueness would answer — and the answer could still be wrong, because
    uniqueness inside the reactor cannot rule out a target outside it. The only key that
    would link this rests on the half of the address nobody read.

    Measured cost of the refusal where it was decided: 5 of `apollo-portal`'s 10 outbound
    rows, and 0 elsewhere. For Apollo the link would have been correct, which is evidence for
    the rule rather than proof of it.
    """
    links, unmatched, _people = linked
    unread = [row for row in unmatched if str(row.path).startswith("<host>")]
    assert len(unread) == 1, unmatched
    assert "authority went unread" in unread[0].reason
    # And the uniqueness that would have answered is genuinely there: exactly one link to
    # `/balances` exists, from the call that named its peer.
    assert len([link for link in links if link.to_path == "/balances"]) == 1


def test_an_inbound_endpoint_nobody_calls_produces_no_link(linked):
    """`/ledgers` is served and never called from inside the reactor.

    `M06`'s second finding that is not an error: an inbound endpoint nobody calls is either
    dead or called from outside. Either way it is NOT a link, and nothing here invents one —
    the test is that the absence is clean, not that something was published about it.

    **Deliberately carries no `pins` marker, and that is a statement rather than an
    oversight.** A guard is one conjunct a test must notice the removal of, and this absence
    is not produced by any single one: the matcher only ever walks outbound rows, and
    disabling that filter still mints nothing here, because an inbound row names no peer and
    no participant other than itself serves `/ledgers`. A guard invented to make this
    markable would be a mutation nothing real produces — which the registry's own note calls
    more dangerous than no test at all, because the coverage file would count it.
    """
    links, _unmatched, _people = linked
    assert [link for link in links if link.to_path == "/ledgers"] == []


def test_a_module_registering_a_different_name_carries_it_as_an_alias(linked):
    """What the alias index holds, end to end: `billing-api` registers as `billing`, so it
    answers to both.

    **No `pins` marker, and it carried one until the sweep said otherwise.** Both of this
    fixture's modules register names unlike their artifactIds, so the rule that an EQUAL name
    adds no alias never fires here and disabling it changes nothing this test can see — the
    harness reported exactly that. The rule is pinned where it can be exercised, by
    `test_stitch_participants.test_a_registered_name_equal_to_the_artifact_id_adds_no_alias`
    on synthetic rows; this test is the end-to-end evidence that the alias index is read
    from a real module's configuration.
    """
    _links, _unmatched, people = linked
    by_name = {p.name: p for p in people}
    assert by_name["billing-api"].aliases == ("billing",)
    assert by_name["orders-api"].aliases == ("orders",)
    assert set(by_name["billing-api"].answers_to()) == {"billing-api", "billing"}
