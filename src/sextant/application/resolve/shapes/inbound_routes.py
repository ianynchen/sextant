"""What an inbound route row takes from its declaration, for every engine that derives one:
the media columns (`consumes`/`produces`), the join of a prefix and a path, and the
record of a declaration the framework refuses to register.

These were `combinator`'s own. `fluent` derives inbound rows too (Vert.x spec §3g item 2),
and two copies of "how a media list becomes a column" or "how a framework joins `api` and
`orders`" are two places to disagree about one piece of evidence — so both engines call
this module and neither keeps a version of its own.
"""

import json
from collections.abc import Mapping
from typing import Any

# The one `path_join` a catalog may declare, beside "absent" (verbatim). Named once so the
# engine that validates the catalog and the engine that applies it read the same word.
LEADING_SLASH = "leading_slash"

MEDIA_FIELDS = ("consumes", "produces")


def media_json(values: list[str]) -> str | None:
    """A media column: a JSON array of the declared wire values, or NULL where
    nothing was derivable (spec §4) — the same text
    `derive_endpoints.sql`'s own `to_json` writes for annotation rows."""
    return json.dumps(values, separators=(",", ":")) if values else None


def media_columns(captures: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """The `(consumes, produces)` columns of one chain's captures.

    A capture is the raw argument the step read: a string literal, or a varargs position
    (`produces("a", "b")`), which arrives as one `array` argument whose elements are the
    values. Each column is the sorted, distinct set of the string literals it holds. An
    element nobody can read as a string contributes nothing and is that column's only
    loss: the column goes NULL while the row's own resolution is untouched, since the
    route's identity is its verb and path, not its media."""
    columns = [
        media_json(sorted(set(_media_strings(captures.get(field))))) for field in MEDIA_FIELDS
    ]
    return columns[0], columns[1]


def _media_strings(argument: Any) -> list[str]:
    if isinstance(argument, tuple):
        # An accumulated capture (`repeats`): one argument per call, oldest first.
        return [value for element in argument for value in _media_strings(element)]
    if not isinstance(argument, dict):
        return []
    if argument.get("kind") == "array":
        return [
            value for element in argument.get("elements") or [] for value in _media_strings(element)
        ]
    if argument.get("kind") == "string" and isinstance(argument.get("value"), str):
        return [str(argument["value"])]
    return []


def join_prefix(prefix: str | None, path: str, rule: str | None) -> str:
    """One literal path segment as the framework will join it behind `prefix` — the
    catalog's `path_join` applied, or the literal untouched when none is declared. Every
    literal the fold reads for a path position passes through here, so a join
    declared once holds for prefixes, verbs and (when they are read) array
    elements alike; a rule's own `path: ""` does not, since the empty segment is
    exactly one the join leaves alone. `leading_slash` is the framework's own
    three exceptions, verbatim: a segment that already starts with `/`, the
    empty segment, and the bare `*` stay as written; every other segment gains
    a leading `/`. Two spellings of one registration must be one row, and the
    join is what makes `path("api", …)` and `path("/api", …)` the same address
    here as they are in the framework. The prefix is already an address and is
    written as it is."""
    segment = path
    if rule == LEADING_SLASH and path not in ("", "*") and not path.startswith("/"):
        segment = "/" + path
    return (prefix or "") + segment


# The `open_questions` kind a refused declaration is filed under (`resolve/open_questions.py`
# owns the closed set; this is the one name it holds for the purpose).
REFUSED_REGISTRATION = "refused_registration"

# Why a registration was refused, the candidate's `reason`. One word per rule so a later
# refusal (a sub-router mounted on an unrooted path) adds a word here and no new kind.
UNROOTED_PATH = "unrooted_path"


# What an unread piece of a partly read path starts with: `<host>` (the address reader's
# marker for an unread authority), `{}` / `{name}` (a hole the walk printed) and `${…}` (a
# configuration placeholder). A path starting with one of these has an unknown first
# character.
_UNKNOWN_START = ("<", "{", "$")


def is_unrooted(path: str, read_whole: bool) -> bool:
    """Whether a path is one a framework that refuses (`refuses_unrooted_path`) throws on:
    empty, or not starting with `/`. Vert.x's `RouteImpl.checkPath` looks at the first
    character alone, so a PARTLY read path is refused too wherever that character was read.

    A path whose FIRST piece is unread (`_UNKNOWN_START`) is undecided and not refused: the
    unread piece may well be the `/`. `read_whole` says the path is the whole address, in
    which case a leading `<`, `{` or `$` is a literal character like any other."""
    if not path:
        return read_whole
    if path.startswith("/"):
        return False
    return read_whole or not path.startswith(_UNKNOWN_START)


def file_refusal(
    refusals: dict[tuple[str, str | None, str], dict[str, Any]],
    *,
    protocol: str,
    method: str | None,
    path: str,
    reason: str,
    caller: str,
    handler: str | None,
) -> None:
    """Notes one declaration the framework would raise on (DR-6: record it, never repair it).

    `refusals` is the run's accumulator, written to `open_questions` once at the end. An
    `open_questions` row is identified by `(protocol, method, path, question)`, so every
    registration of one refused address shares one row and each is a candidate of it,
    sorted (NFR-1) when the rows are built by `refusal_rows`."""
    row = refusals.setdefault(
        (protocol, method, path),
        {"protocol": protocol, "method": method, "path": path, "candidates": []},
    )
    candidate = {"caller": caller, "handler": handler, "reason": reason}
    if candidate not in row["candidates"]:
        row["candidates"].append(candidate)


def refusal_rows(
    refusals: Mapping[tuple[str, str | None, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    """The `open_questions` rows of a run's refusals, in a stable order."""
    rows = []
    for key in sorted(refusals, key=lambda k: (k[0], k[1] or "", k[2])):
        candidates = sorted(
            refusals[key]["candidates"], key=lambda c: json.dumps(c, sort_keys=True)
        )
        rows.append(
            {
                "protocol": key[0],
                "method": key[1],
                "path": key[2],
                "question": REFUSED_REGISTRATION,
                "candidates": json.dumps(candidates, sort_keys=True, separators=(",", ":")),
                "evidence": "; and ".join(sorted({str(c["caller"]) for c in candidates})),
            }
        )
    return rows
