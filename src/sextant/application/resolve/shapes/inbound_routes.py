"""What an inbound route row takes from its declaration, for every engine that derives one:
the media columns (`consumes`/`produces`) and the join of a prefix and a path.

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
