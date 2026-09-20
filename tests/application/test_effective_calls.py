"""Tests for `effective_call_sites` (spec 2026-09-19 §3, Task 3) — proof step 1 that the
projection point is a PURE RENAME before either Kotlin projection lands on it: with nothing
to project yet, the function returns exactly `call_sites`'s own rows, and `Workspace.once`
hands back the same list on a second call rather than rebuilding it.
"""

from pathlib import Path

from sextant.application.resolve.effective_calls import effective_call_sites
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import CallArgument, CallSiteFact, CallTarget, Document, SymbolFact
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "
CALLER = "com/acme/orders/Caller#handle(sig_a1)."


def _document() -> Document:
    return Document(
        document_id="doc_1",
        relative_path="com/acme/orders/Caller.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _site(
    caller: str,
    ordinal: int,
    owner: str,
    name: str,
    *,
    arguments: list[CallArgument] | None = None,
    result: int | None = None,
    invoke_kind: str = "static",
) -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_1",
        caller=caller,
        target=CallTarget(owner=owner, name=name, descriptor="(...)V"),
        invoke_kind=invoke_kind,
        ordinal=ordinal,
        result=result,
        arguments=list(arguments or []),
    )


def _method_symbol(bare: str) -> SymbolFact:
    return SymbolFact(
        document_id="doc_1", symbol=_MODULE + bare, construct_kind=ConstructKind.METHOD
    )


def _workspace(tmp_path: Path, facts: list) -> DuckDbWorkspace:
    write_fact_file(tmp_path / "facts" / "Caller.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    return workspace


def test_effective_call_sites_is_the_raw_list_when_nothing_projects(tmp_path: Path):
    workspace = _workspace(
        tmp_path,
        [_method_symbol(CALLER), _site(CALLER, 0, "com/x/Y#", "m", result=1, arguments=[])],
    )

    assert effective_call_sites(workspace) == workspace.query("call_sites")
    assert effective_call_sites(workspace) is effective_call_sites(workspace)  # once per load
