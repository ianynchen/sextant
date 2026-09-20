"""Effective call sites (spec 2026-09-19 §3): the `call_sites` facts as every ENGINE reads
them, with two projections applied once per load — a compiler-emitted `$default` bridge call
re-targeted to the function it stands for (§3a, T4) and a class-compiled lambda argument
read as the `lambda` it is (§3b, T5). Both join on shared fields the extractor publishes on
the declaration it scanned (`bridge_of`, `lambda_body`); nothing here names a language.

`call_sites` itself is untouched: the exported bundle, the graph/trace readers
(`call_edges`, `return_flow`, `format`) and every raw-fact test keep the bytecode's own
statement. This module is the ONE projection point (F10) — a reader that wants what the
engines see calls `effective_call_sites`, never `query("call_sites")` plus its own rewrite.
"""

from typing import Any

from sextant.application.ports.workspace import Workspace


def effective_call_sites(workspace: Workspace) -> list[dict[str, Any]]:
    """`call_sites`, projected. Ordinal-ordered as the named query is (NFR-1); built once
    per load through `Workspace.once`, which also guards that only fact queries are read."""
    return workspace.once(_effective)


def _effective(workspace: Workspace) -> list[dict[str, Any]]:
    return list(workspace.query("call_sites"))
