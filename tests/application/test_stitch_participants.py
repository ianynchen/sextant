"""The participant set of one reactor, and the federated views over it (Task 1).

`M06` reaches every participant's graph "only through the `Workspace` port's federated
views", and `D01`'s system scope says the system workspace owns two native tables and copies
nothing. These tests pin both halves: what `participants_of` makes of a reactor's own record
of its modules, and that `federate` reads those graphs without importing them.
"""

from pathlib import Path

import pytest

from sextant.application.stitch import participants_of
from sextant.storage.duckdb.workspace import DuckDbWorkspace


def _workspace_with_one_endpoint(path: Path, route: str) -> DuckDbWorkspace:
    """A workspace holding one inbound endpoint and NO Java anywhere.

    Deliberately synthetic, and the reason is the guard harness rather than speed: it copies
    the stub jar and six named fixtures only, and reports a pinned test needing any other
    fixture as *unmeasurable* rather than counting it as discriminating. The first draft of
    these two tests leaned on `analyzed_orders_service`, which is not in that list, so both
    came back unmeasurable — the harness working exactly as its own comment says it should.
    Nothing here is about a real module: the claim under test is that the view READS a
    participant's graph, and one row is enough to see whether it was read or copied.
    """
    workspace = DuckDbWorkspace(path)
    workspace.derive(
        "call_endpoints",
        rows=[
            {
                "protocol": "http",
                "direction": "inbound",
                "method": "GET",
                "path": route,
                "handler": "com/acme/Controller#get(sig_1).",
                "caller": None,
                "peer": None,
                "handler_signature": None,
                "resolution": "resolved",
                "evidence": "compiler",
                "catalog_id": "test",
                "request_shape": None,
                "response_shape": None,
                "consumes": None,
                "produces": None,
            }
        ],
    )
    return workspace


def _module(
    module_id: str,
    *,
    location: Path | None = None,
    analyzed: bool = True,
    skip_reason: str | None = None,
    commit_id: str | None = "abc1234",
) -> dict[str, object]:
    """One `modules.json` entry as the adapter hands it over, with `location` resolved."""
    return {
        "module_id": module_id,
        "location": location,
        "analyzed": analyzed,
        "skip_reason": skip_reason,
        "commit_id": commit_id,
    }


@pytest.mark.pins("stitch.a-participant-is-MATCHED-by-its-artifact-id")
def test_a_participants_name_is_the_artifact_id_a_client_would_state(tmp_path):
    """The name a link is matched BY, and why it is the artifactId.

        uri: lb://customers-service          # what the gateway states
        <artifactId>spring-petclinic-customers-service</artifactId>

    A client names a service the way service discovery does, and on a Spring module that is
    `spring.application.name`, which defaults to the artifactId. So the artifactId is the
    name, and the full coordinate travels beside it — two groups may ship one artifactId, and
    `module_id` is what keeps those two participants apart when they do.
    """
    found = participants_of(
        [
            _module(
                "org.springframework.samples.petclinic.customers:customers-service",
                location=tmp_path / "a",
            ),
            _module("com.acme:customers-service", location=tmp_path / "b"),
        ]
    )
    assert [p.name for p in found] == ["customers-service", "customers-service"]
    assert [p.module_id for p in found] == [
        "com.acme:customers-service",
        "org.springframework.samples.petclinic.customers:customers-service",
    ]


@pytest.mark.pins("stitch.an-ABSENT-participant-is-a-row-not-an-omission")
def test_a_module_whose_graph_cannot_be_read_is_a_row_with_a_reason(tmp_path):
    """**An absent participant is a ROW, and that is the point of it.**

    `M06`'s rule is that an unmatched call into a participant nobody could read is
    attributed to the GAP rather than reported as an architectural finding. A missing row
    cannot carry that: *nothing calls this service* and *we could not read this service* are
    different statements about a system, and a reader acting on the first when the second is
    true deletes a dependency that exists.

    Three causes, kept apart because a reader does something different about each: a module
    the detector skip-listed on purpose is correct behaviour; one never analyzed is a command
    to run; one analyzed whose workspace has gone is a stale system run.
    """
    found = {
        p.name: p
        for p in participants_of(
            [
                _module("com.acme:read", location=tmp_path / "ok"),
                _module("com.acme:skipped", skip_reason="packaging is `pom`"),
                _module("com.acme:never", analyzed=False),
                _module("com.acme:gone", analyzed=True),
            ]
        )
    }

    assert found["read"].present is True
    assert found["read"].absent_reason is None

    assert found["skipped"].present is False
    assert "skip-listed" in str(found["skipped"].absent_reason)
    assert "packaging is `pom`" in str(found["skipped"].absent_reason)

    assert found["never"].present is False
    assert "module analyze" in str(found["never"].absent_reason)

    assert found["gone"].present is False
    assert "no longer there" in str(found["gone"].absent_reason)


@pytest.mark.pins("stitch.a-reactor-entry-with-no-coordinate-names-no-participant")
def test_an_entry_with_no_coordinate_is_refused_rather_than_named_empty(tmp_path):
    """A participant whose name would be the empty string matches nothing meaningfully and
    would sit in the table claiming to be a service. Refused, which is the same choice every
    reader in this project makes about a value it cannot name."""
    assert participants_of([_module("", location=tmp_path)]) == ()


@pytest.mark.pins("stitch.a-federated-view-READS-a-participants-graph-and-copies-nothing")
def test_the_federated_view_reads_every_participants_endpoints_without_importing(
    tmp_path: Path,
):
    """`D01`'s system scope, measured rather than asserted: the system workspace owns its two
    native tables and reads each participant's `endpoints` through a view.

    The same module is attached under two names, which is what makes the claim testable
    without a second fixture: if the view were copying rows, the two participants could not
    share one file. The `participant` column is what tells them apart, and it is a VALUE in
    the view rather than part of an identifier — an artifactId carries hyphens, and quoting a
    caller's string into SQL is how a name becomes an injection.
    """
    alpha_ws = _workspace_with_one_endpoint(tmp_path / "alpha.duckdb", "/alpha")
    bravo_ws = _workspace_with_one_endpoint(tmp_path / "bravo.duckdb", "/bravo")
    alpha_ws.close()
    bravo_ws.close()
    system = DuckDbWorkspace(tmp_path / "system.duckdb")
    try:
        system.federate({"alpha": tmp_path / "alpha.duckdb", "bravo": tmp_path / "bravo.duckdb"})
        rows = system.query("system_endpoints")
        # Nothing was imported: the system workspace's own `endpoints` table is empty while
        # the view answers for both participants.
        assert system.query("endpoints") == []
        assert {(str(r["participant"]), str(r["path"])) for r in rows} == {
            ("alpha", "/alpha"),
            ("bravo", "/bravo"),
        }
    finally:
        system.close()


@pytest.mark.pins("stitch.NO-participant-leaves-an-EMPTY-view-never-a-missing-one")
def test_a_system_with_no_readable_participant_still_answers(tmp_path: Path):
    """A reactor every module of which was skip-listed has no graph to read. The view is
    created and EMPTY rather than absent, because a missing view makes the query raise a
    catalog error that says nothing about why — and the reason belongs per participant in
    `participants`, which is where a reader can act on it.
    """
    system = DuckDbWorkspace(tmp_path / "system.duckdb")
    try:
        system.federate({})
        assert system.query("system_endpoints") == []
    finally:
        system.close()


@pytest.mark.pins("stitch.FEDERATING-again-replaces-the-previous-set")
def test_federating_a_second_time_replaces_the_first_set(tmp_path: Path):
    """One process may analyze two reactors, so a second `federate` must not leave the first
    reactor's participants readable — a link minted against a participant that is not in this
    system is a dependency this system does not have.
    """
    _workspace_with_one_endpoint(tmp_path / "one.duckdb", "/one").close()
    system = DuckDbWorkspace(tmp_path / "system.duckdb")
    try:
        system.federate({"first": tmp_path / "one.duckdb"})
        assert {str(r["participant"]) for r in system.query("system_endpoints")} == {"first"}
        system.federate({"second": tmp_path / "one.duckdb"})
        assert {str(r["participant"]) for r in system.query("system_endpoints")} == {"second"}
    finally:
        system.close()
