"""What each root reaches, materialised (F8 §9.4, W37).

The walk itself is `query/trace.py`'s and is tested there. What these pin is the SHAPE of
what is kept: which symbols become rows, at what depth, and which of them the walk stopped
at. The pass calls the very function the renderer calls, so a second traversal with its own
rules about cycles and revisits — the thing that would put a table and a document at odds
about what is reachable — cannot arise.
"""

from pathlib import Path

from test_shapes import _MODULE, _document, _write

from sextant.application.resolve.reachability import record_reachability
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_API = _MODULE + "com/acme/Api#list()."
_SERVICE = _MODULE + "com/acme/Service#run()."


def _workspace(
    tmp_path: Path,
    roots: list[tuple[str, str]],
    edges: list[tuple[str, int, str, str | None]],
) -> DuckDbWorkspace:
    """`roots` as `(handler, path)` and `edges` as `(caller, ordinal, target, callee)` —
    inserted rather than derived, because what is under test is the projection of a walk
    and not the derivation of the graph it walks."""
    _write(tmp_path / "facts" / "doc.jsonl", _document("doc", "Api.java"), [])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    for handler, path in roots:
        workspace._connection.execute(
            "INSERT INTO roots (handler, root_kind, protocol, method, path) "
            "VALUES (?, 'inbound_endpoint', 'http', 'GET', ?)",
            [handler, path],
        )
    for caller, ordinal, target, callee in edges:
        workspace._connection.execute(
            "INSERT INTO call_edges (caller, ordinal, invoke_kind, target, callee, "
            "result, resolution, evidence) "
            "VALUES (?, ?, 'virtual', ?, ?, NULL, 'resolved', 'compiler')",
            [caller, ordinal, target, callee],
        )
    return workspace


def _rows(workspace: DuckDbWorkspace) -> list[tuple]:
    return workspace._connection.execute(
        "SELECT root, symbol, depth, terminal FROM reachability ORDER BY depth, symbol"
    ).fetchall()


def test_a_root_reaches_itself_at_depth_zero(tmp_path: Path):
    """ "Everything this root touches" is one lookup rather than a lookup plus a union with
    the key, which is the shape every consumer of this table wants."""
    workspace = _workspace(tmp_path, [(_API, "/orders")], [])

    record_reachability(workspace)
    rows = _rows(workspace)
    workspace.close()

    assert rows == [(_API, _API, 0, False)]


def test_a_terminal_is_recorded_by_the_target_the_compiler_wrote(tmp_path: Path):
    """A terminal is a thing the root REACHES. Recording only callees would make a root
    that calls nothing but a library look like a root that calls nothing at all — which is
    the difference between "this handler does no work" and "the work leaves the module"."""
    workspace = _workspace(
        tmp_path,
        [(_API, "/orders")],
        [(_API, 0, "java/lang/String#length().", None)],
    )

    record_reachability(workspace)
    rows = _rows(workspace)
    workspace.close()

    assert (_API, "java/lang/String#length().", 1, True) in rows


def test_depth_counts_edges_from_the_root(tmp_path: Path):
    """The root's own body is depth 0 and what it calls is depth 1, which is the same
    counting `## Traces` renders — two answers to "how far" would be one too many."""
    workspace = _workspace(
        tmp_path,
        [(_API, "/orders")],
        [
            (_API, 0, "com/acme/Service#run().", _SERVICE),
            (_SERVICE, 0, "java/lang/String#length().", None),
        ],
    )

    record_reachability(workspace)
    rows = _rows(workspace)
    workspace.close()

    assert {(row[1].split()[-1], row[2]) for row in rows} == {
        ("com/acme/Api#list().", 0),
        ("com/acme/Service#run().", 1),
        ("java/lang/String#length().", 2),
    }


def test_a_symbol_reached_twice_is_one_row(tmp_path: Path):
    """One row per (root, symbol). The walk expands a method once per trace, so a method
    reached again by another route is a `revisited` step carrying no subtree — recording
    every ROUTE instead is the exponential tree D01 gives as its reason for not storing
    traces at all."""
    workspace = _workspace(
        tmp_path,
        [(_API, "/orders")],
        [
            (_API, 0, "com/acme/Service#run().", _SERVICE),
            (_API, 1, "com/acme/Service#run().", _SERVICE),
        ],
    )

    record_reachability(workspace)
    rows = _rows(workspace)
    workspace.close()

    assert len(rows) == 2, rows
    assert sorted(row[1] for row in rows) == sorted([_API, _SERVICE])


def test_two_roots_reaching_one_symbol_are_two_rows(tmp_path: Path):
    """Keyed on (root, symbol), because the question is "what does THIS root reach" and a
    symbol shared by two roots is reached by both. Deduping across roots would answer a
    different question than the one the table exists for."""
    other = _MODULE + "com/acme/Other#go()."
    workspace = _workspace(
        tmp_path,
        [(_API, "/orders"), (other, "/other")],
        [
            (_API, 0, "com/acme/Service#run().", _SERVICE),
            (other, 0, "com/acme/Service#run().", _SERVICE),
        ],
    )

    record_reachability(workspace)
    rows = _rows(workspace)
    workspace.close()

    assert sorted(row[0] for row in rows if row[1] == _SERVICE) == sorted([_API, other])


def test_depth_is_the_shortest_route_not_the_first_one_the_walk_saw(tmp_path: Path):
    """The walk is depth-first, so a symbol reached down one branch BEFORE a shorter route
    to it is read comes up deep — and `depth` is meant to be distance from the root.

    Measured on `mall-admin` before this: 51 rows deeper than the true distance, and 26 of
    them symbols the ROOT ITSELF calls, recorded at depth 2 or more. A consumer filtering
    `depth = 1` for "what does this handler call directly" missed every one. The fixture
    has none of them, which is why the first tests here passed.

    This is that shape exactly: ordinal 0 expands into a service that calls `Helper`, and
    ordinal 1 calls `Helper` DIRECTLY. Depth-first sees the deep one first.
    """
    helper = _MODULE + "com/acme/Helper#help()."
    workspace = _workspace(
        tmp_path,
        [(_API, "/orders")],
        [
            (_API, 0, "com/acme/Service#run().", _SERVICE),
            (_SERVICE, 0, "com/acme/Helper#help().", helper),
            # The root's OWN direct call, at a later ordinal so the walk reaches it second.
            (_API, 1, "com/acme/Helper#help().", helper),
        ],
    )

    record_reachability(workspace)
    depths = {row[1]: row[2] for row in _rows(workspace)}
    workspace.close()

    assert depths[helper] == 1, "the root calls it directly, whatever the walk saw first"
    assert depths[_SERVICE] == 1


def test_a_second_analyze_over_one_workspace_does_not_double_the_table(tmp_path: Path):
    """The pass clears before it writes, which every other derived table's writer does and
    this one did not.

    `load_facts` clears `raw_facts` and every other derivation resets itself, so
    `reachability` alone survived a re-run: 190 rows became 380 with 190 duplicated
    `(root, symbol)` pairs, and they shipped in the exported parquet. Re-running `analyze`
    is the ordinary act — it is what the CLI tells a reader to do when the build stamps go
    stale — and every consumer asking what a handler reaches would have got twice the
    answer, then three times.
    """
    workspace = _workspace(
        tmp_path,
        [(_API, "/orders")],
        [(_API, 0, "com/acme/Service#run().", _SERVICE)],
    )

    record_reachability(workspace)
    record_reachability(workspace)
    rows = _rows(workspace)
    workspace.close()

    assert len(rows) == 2, rows
    assert len({(row[0], row[1]) for row in rows}) == 2
