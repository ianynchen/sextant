"""The six in-process questions (spec 2026-10-22-boundary-vocabulary-and-diff §5, FR-24).

Every test writes the rows it is about by hand — symbol facts for what a question places,
`call_edges` and `type_hierarchy` rows for what it walks — because each question is a read
of those tables and a row written here says exactly which edge the answer came from. The
fixture-level questions (a real controller, a real payload class) are in
`tests/api/test_facade.py`.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from sextant.application.query.questions import QUESTIONS, QuestionRefused, answer
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import Document, Parameter, Signature, SymbolFact, TypeRef
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "
_DOCUMENT = "com/acme/q/Walk#"


def _method(name: str) -> str:
    return f"{_MODULE}com/acme/q/Walk#{name}(sig_00000001)."


def _document() -> Document:
    return Document(
        document_id=_DOCUMENT,
        relative_path="com/acme/q/Walk.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="sextant-jvm-extractor",
        content_hash="sha256:c",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:none",
    )


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[DuckDbWorkspace]:
    opened = DuckDbWorkspace(tmp_path / "workspace.duckdb")
    yield opened
    opened.close()


def _symbols(workspace: DuckDbWorkspace, root: Path, *facts: SymbolFact) -> None:
    write_fact_file(root / "facts" / "walk.jsonl", _document(), list(facts))
    workspace.load_facts(root / "facts")


def _methods(workspace: DuckDbWorkspace, root: Path, *names: str) -> None:
    _symbols(
        workspace,
        root,
        SymbolFact(
            document_id=_DOCUMENT, symbol=_MODULE + _DOCUMENT, construct_kind=ConstructKind.CLASS
        ),
        *(
            SymbolFact(
                document_id=_DOCUMENT,
                symbol=_method(name),
                construct_kind=ConstructKind.METHOD,
                enclosing=_MODULE + _DOCUMENT,
                line_start=10 + index,
                line_end=12 + index,
            )
            for index, name in enumerate(names)
        ),
    )


def _call(
    workspace: DuckDbWorkspace,
    caller: str,
    callee: str | None,
    resolution: str = "resolved",
    *,
    target: str | None = None,
) -> None:
    workspace._connection.execute(
        "INSERT INTO call_edges (caller, ordinal, invoke_kind, target, callee, resolution) "
        "VALUES (?, 0, 'virtual', ?, ?, ?)",
        [caller, target if target is not None else callee, callee, resolution],
    )


def _extends(workspace: DuckDbWorkspace, child: str, ancestor: str, *, scanned: bool) -> None:
    workspace._connection.execute(
        "INSERT INTO type_hierarchy (child, ancestor, kind, position, scanned) "
        "VALUES (?, ?, 'extends', 0, ?)",
        [child, ancestor, scanned],
    )


def _names(rows: object) -> list[str]:
    assert isinstance(rows, list)
    return [str(row["symbol"]) for row in rows]


# --- the one-hop questions ---------------------------------------------------------------


def test_source_places_a_symbol_at_its_document_and_lines(
    workspace: DuckDbWorkspace, tmp_path: Path
):
    _methods(workspace, tmp_path, "a")
    assert answer(workspace, "source", symbol=_method("a")) == [
        {
            "symbol": _method("a"),
            "file": "com/acme/q/Walk.java",
            "line_start": 10,
            "line_end": 12,
        }
    ]


def test_a_type_states_no_lines_rather_than_line_zero(workspace: DuckDbWorkspace, tmp_path: Path):
    """A class file gives a type no line table, and the fact writes 0. "The class file does
    not say" is not "line zero" — the export index's own rule (`located_symbols`)."""
    _methods(workspace, tmp_path)
    [row] = answer(workspace, "source", symbol=_MODULE + _DOCUMENT)
    assert (row["line_start"], row["line_end"]) == (None, None)


def test_callees_leaves_out_a_call_that_left_the_workspace(
    workspace: DuckDbWorkspace, tmp_path: Path
):
    """A boundary call has no callee — no body was read — so it is not a symbol anyone can
    be told the file of. One hop: the callee's own callees are not listed."""
    _methods(workspace, tmp_path, "a", "b", "c")
    _call(workspace, _method("a"), _method("b"))
    _call(workspace, _method("a"), None, target="org/lib/Client#send(sig_00000002).")
    _call(workspace, _method("b"), _method("c"))
    assert _names(answer(workspace, "callees", symbol=_method("a"))) == [_method("b")]
    assert _names(answer(workspace, "callers", symbol=_method("c"))) == [_method("b")]


def test_implementations_and_uses_compare_the_bare_type_the_tables_spell(
    workspace: DuckDbWorkspace, tmp_path: Path
):
    """`type_hierarchy` and a signature name a type BARE (D00 §5a) while the question names
    it in full, so the answer exists only if the comparison is on the bare descriptor. A
    type is used by what returns it, takes it, holds it, and extends it."""
    payload, child = "com/acme/q/Payload#", "com/acme/q/Detailed#"
    reference = TypeRef(symbol=payload)
    _symbols(
        workspace,
        tmp_path,
        SymbolFact(
            document_id=_DOCUMENT, symbol=_MODULE + payload, construct_kind=ConstructKind.CLASS
        ),
        SymbolFact(
            document_id=_DOCUMENT, symbol=_MODULE + child, construct_kind=ConstructKind.CLASS
        ),
        SymbolFact(
            document_id=_DOCUMENT,
            symbol=_method("returns"),
            construct_kind=ConstructKind.METHOD,
            signature=Signature(returns=reference),
        ),
        SymbolFact(
            document_id=_DOCUMENT,
            symbol=_method("takes"),
            construct_kind=ConstructKind.METHOD,
            signature=Signature(
                parameters=[Parameter(name="p", type=reference)],
                returns=TypeRef(symbol="void#"),
            ),
        ),
        SymbolFact(
            document_id=_DOCUMENT,
            symbol=f"{_MODULE}com/acme/q/Walk#held.",
            construct_kind=ConstructKind.FIELD,
            signature=Signature(returns=reference),
        ),
        SymbolFact(
            document_id=_DOCUMENT,
            symbol=_method("unrelated"),
            construct_kind=ConstructKind.METHOD,
            signature=Signature(returns=TypeRef(symbol="com/acme/q/Other#")),
        ),
    )
    _extends(workspace, child, payload, scanned=True)

    assert _names(answer(workspace, "implementations", symbol=_MODULE + payload)) == [
        _MODULE + child
    ]
    assert _names(answer(workspace, "uses", symbol=_MODULE + payload)) == sorted(
        [
            _MODULE + child,
            f"{_MODULE}com/acme/q/Walk#held.",
            _method("returns"),
            _method("takes"),
        ]
    )


# --- impact ------------------------------------------------------------------------------


def test_impact_terminates_on_recursion(workspace: DuckDbWorkspace, tmp_path: Path):
    """`a` calls `b` and `b` calls `a`. The walk upstream from `a` reaches `b`, then `a`
    again, and stops there: the subject is never its own impact."""
    _methods(workspace, tmp_path, "a", "b")
    _call(workspace, _method("a"), _method("b"))
    _call(workspace, _method("b"), _method("a"))
    result = answer(workspace, "impact", symbol=_method("a"))
    assert result == {
        "definite": [
            {
                "symbol": _method("b"),
                "file": "com/acme/q/Walk.java",
                "line_start": 11,
                "line_end": 13,
            }
        ],
        "possible": [],
        "unknown_regions": [],
    }


def test_a_path_through_narrowed_dispatch_is_possible_and_the_strongest_path_wins(
    workspace: DuckDbWorkspace, tmp_path: Path
):
    """D01 §5: three partitions, never one count. A caller reached only through a dispatch
    that narrowed to several bodies may not run the subject, so it is `possible`, and so is
    everything that reaches the subject only through it. A symbol with ANY all-resolved path
    is `definite`, even when the walk met it through the narrowed one first — `z` is one hop
    away through `narrowed` and three away through `resolved`, and the upgrade carries on
    upstream to `w`."""
    _methods(workspace, tmp_path, "t", "n", "r", "x", "y", "z", "r2", "w")
    _call(workspace, _method("n"), _method("t"), "narrowed")
    _call(workspace, _method("r"), _method("t"))
    _call(workspace, _method("x"), _method("n"))
    _call(workspace, _method("y"), _method("n"))
    _call(workspace, _method("y"), _method("r"))
    _call(workspace, _method("z"), _method("t"), "narrowed")
    _call(workspace, _method("r2"), _method("r"))
    _call(workspace, _method("z"), _method("r2"))
    _call(workspace, _method("w"), _method("z"))

    result = answer(workspace, "impact", symbol=_method("t"))
    assert isinstance(result, dict)
    assert _names(result["definite"]) == [_method(n) for n in ("r", "r2", "w", "y", "z")]
    assert _names(result["possible"]) == [_method(n) for n in ("n", "x")]


def test_the_unknown_regions_are_an_unresolved_call_and_an_ancestor_nobody_read(
    workspace: DuckDbWorkspace, tmp_path: Path
):
    """What the walk cannot see past is listed, never folded into either partition: a call
    whose dispatch was not resolved but whose target names the walked method may reach it,
    and a walked type whose ancestor was never scanned may be called through that ancestor
    by code this workspace holds no body for."""
    _methods(workspace, tmp_path, "t", "u")
    _call(workspace, _method("u"), None, "unresolved", target="com/acme/q/Walk#t(sig_00000001).")
    _extends(workspace, _DOCUMENT, "org/lib/Callback#", scanned=False)

    result = answer(workspace, "impact", symbol=_method("t"))
    assert result == {
        "definite": [],
        "possible": [],
        "unknown_regions": [
            {"symbol": "org/lib/Callback#", "reason": "ancestor not scanned"},
            {"symbol": _method("u"), "reason": "unresolved call"},
        ],
    }


def test_impact_reads_the_workspace_once_per_hop(
    workspace: DuckDbWorkspace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """GUIDELINES §8.7: the walk's cost is decided here, not profiled later. One read
    places the subject, then one read per hop of the frontier — never one per symbol the
    walk reaches. A chain three callers deep with two callers at every level is four hop
    reads (the last finds nothing), not one per caller."""
    _methods(workspace, tmp_path, "t", "a1", "a2", "b1", "b2", "c1", "c2")
    for level, below in (("a", "t"), ("b", "a1"), ("c", "b1")):
        for index in ("1", "2"):
            _call(workspace, _method(level + index), _method(below))
    _call(workspace, _method("b2"), _method("a2"))

    asked: list[str] = []
    real = workspace.query

    def counted(name: str, **params: object) -> list[dict[str, object]]:
        asked.append(name)
        return real(name, **params)

    monkeypatch.setattr(workspace, "query", counted)
    result = answer(workspace, "impact", symbol=_method("t"))
    assert isinstance(result, dict) and len(result["definite"]) == 6
    assert asked == ["question_source"] + ["question_impact_step"] * 4


# --- refusals ----------------------------------------------------------------------------


def test_an_unknown_question_is_refused_naming_the_six_in_order(workspace: DuckDbWorkspace):
    assert QUESTIONS == ("source", "callers", "callees", "implementations", "uses", "impact")
    with pytest.raises(
        QuestionRefused, match="source, callers, callees, implementations, uses, impact"
    ):
        answer(workspace, "path", symbol="x")


def test_an_unknown_symbol_is_refused_naming_it_rather_than_answering_empty(
    workspace: DuckDbWorkspace, tmp_path: Path
):
    """An empty list would read as "nothing calls it" when the truth is "no such symbol":
    a typo must not look like dead code."""
    _methods(workspace, tmp_path, "a")
    with pytest.raises(QuestionRefused, match="no symbol .*Walk#typo"):
        answer(workspace, "callers", symbol=f"{_MODULE}com/acme/q/Walk#typo.")
