"""The one reason-list check, shared by the guard test and the suites that hold the data.

`tests/application/test_one_reason_list.py` reads each table on a fixture the e2e suite
already analyses, and `tests/e2e/test_sextant_reads_itself.py` reads the same tables on
Sextant's own analysis. The Vert.x e2e run and the shadow run hold the pass-through and
`values` answers, so they call the same functions from here: one check, no second copy. It lives beside
`fixture_build.py` so every test directory can import it when run alone.
"""

import json
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from sextant.application.resolve.resolved_peers import resolved_peers
from sextant.application.resolve.values import _REASONS
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace

# The words the three lists used before the one list. Planted by the tests below to prove the
# guard fails on them; no code writes any of them.
OLD_WORDS = (
    "missing_key",
    "environment",
    "remote_source",
    "placeholder_cycle",
    "multi_placeholder",
    "declared_here",
    "inherited",
    "ancestor_not_scanned",
    "owner_not_scanned",
    "no_declaration_found",
    "handed_to",
    "stored_in",
    "produced_by",
    "of_type",
    "from_field",
    "no_body",
)


def outside_the_list(
    rows: Iterable[Mapping[str, Any]],
    where: str,
    reason: str,
    *,
    found: Callable[[Mapping[str, Any]], bool],
    detail: str | None = None,
) -> list[str]:
    """What is wrong with the `reason` column of `rows`: a word outside the list, a reason on
    an answer that was found, or no reason on one that was not. `detail`, where the table has
    one, is set exactly when the reason is."""
    wrong = []
    for row in rows:
        word = row[reason]
        if word is not None and word not in _REASONS:
            wrong.append(f"{where}: {word!r} is not a general reason ({row})")
        elif (word is None) != found(row):
            wrong.append(f"{where}: reason {word!r} beside found={found(row)} ({row})")
        elif detail is not None and (row[detail] is None) != (word is None):
            wrong.append(f"{where}: detail {row[detail]!r} beside reason {word!r} ({row})")
    return wrong


def stored_reason_tables(workspace: DuckDbWorkspace) -> dict[str, list[dict[str, Any]]]:
    """The four tables that store a reason word, read off one analysed workspace."""
    return {
        **{
            name: [dict(row) for row in workspace.query(name)]
            for name in ("resolved_config", "resolved_schedules", "method_resolution")
        },
        "resolved_peers": resolved_peers(workspace, YamlCatalogSource(catalogs_dir()).load()),
    }


def _peer_found(row: Mapping[str, Any]) -> bool:
    """An address that was written (`path`, `peer`) and came out empty was not resolved."""
    return (row["path"] is None or row["resolved_path"] is not None) and (
        row["peer"] is None or row["resolved_peer"] is not None
    )


def stored_reasons_outside_the_list(tables: Mapping[str, list[dict[str, Any]]]) -> list[str]:
    """`outside_the_list` over each table of `stored_reason_tables`, each with its own rule
    for an answer that was found."""
    return [
        *outside_the_list(
            tables["resolved_config"],
            "resolved_config",
            "unresolved_reason",
            found=lambda row: row["value"] is not None,
            detail="unresolved_detail",
        ),
        *outside_the_list(
            tables["resolved_schedules"],
            "resolved_schedules",
            "unresolved_reason",
            found=lambda row: row["value"] is not None,
            detail="unresolved_detail",
        ),
        *outside_the_list(
            tables["resolved_peers"],
            "resolved_peers",
            "unresolved_reason",
            found=_peer_found,
            detail="unresolved_detail",
        ),
        *outside_the_list(
            tables["method_resolution"],
            "method_resolution",
            "reason",
            found=lambda row: row["declaring_class"] is not None,
            detail="detail",
        ),
    ]


def value_answers_outside_the_list(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    """The same check over `value_resolutions` (the `values` answers, filled by `--shadow`):
    a reason exactly on an `unresolved` answer."""
    return outside_the_list(
        rows,
        "value_resolutions",
        "reason",
        found=lambda row: row["answer_kind"] != "unresolved",
    )


def unread_outside_the_list(questions: Iterable[Mapping[str, Any]]) -> list[str]:
    """The same check over every pass-through `unread[]` entry: `{reason, detail}`, the reason
    one word of the list and the detail text."""
    wrong = []
    for question in questions:
        if question["question"] != "handler_pass_through":
            continue
        for candidate in json.loads(str(question["candidates"])):
            for entry in candidate["unread"]:
                if set(entry) != {"reason", "detail"}:
                    wrong.append(f"unread entry keys {sorted(entry)}")
                elif entry["reason"] not in _REASONS or not entry["detail"]:
                    wrong.append(f"unread entry {entry}")
    return wrong
