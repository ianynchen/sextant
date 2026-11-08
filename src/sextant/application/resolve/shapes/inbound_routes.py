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

from sextant.application.ports.catalogs import CatalogError
from sextant.application.resolve.shapes.arguments import HOLE, UNREADABLE_HOST
from sextant.domain.closed_sets import ANY_METHOD
from sextant.domain.paths import EXPRESSION_OPENS

# The one `path_join` a catalog may declare, beside "absent" (verbatim). Named once so the
# engine that validates the catalog and the engine that applies it read the same word.
LEADING_SLASH = "leading_slash"
# How a `root_kind: entry_point` catalog joins its words: one space, as a command is typed
# (design 2026-11-06-reading-decorators §4, ruled: a rule, not a catalog value).
WORDS = "words"

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


def validated_path_join(matches: Mapping[str, Any], source: object, style: str) -> str | None:
    """`matches.path_join`, checked at load so a typo is refused rather than read as
    verbatim, which would publish the glued address the word exists to prevent: absent, or
    `leading_slash`, the one rule. `style` names the D02 style the refusal cites."""
    if matches.get("path_join", LEADING_SLASH) != LEADING_SLASH:
        raise CatalogError(
            f"loading catalog {source}: `path_join: "
            f"{matches.get('path_join')!r}` — the only value is `{LEADING_SLASH}`; "
            f"leave it out for verbatim concatenation (D02 §2's `{style}` style)"
        )
    return matches.get("path_join")


def validated_verbless_serves(matches: Mapping[str, Any], source: object, style: str) -> str | None:
    """`verbless_serves` (Vert.x spec §3a), the word `fluent` and `annotation_driven` catalogs
    share: `any` for a framework whose route with no verb serves every verb of an open set,
    absent for one that says nothing. Any other value is a broken file — the one answer the
    row can carry is `method_kind = any`. `style` names the D02 style the refusal cites."""
    declared = matches.get("verbless_serves")
    if declared is not None and declared != ANY_METHOD:
        raise CatalogError(
            f"loading catalog {source}: `verbless_serves` is `{ANY_METHOD}`, got "
            f"{declared!r} (D02 §2's `{style}` style)"
        )
    return None if declared is None else ANY_METHOD


def join_prefix(prefix: str | None, path: str, rule: str | None) -> str:
    """One literal path segment as the framework will join it behind `prefix` — the
    catalog's `path_join` applied, or the literal untouched when none is declared. Every
    literal an engine reads for a path position passes through here, so a join declared once
    holds for prefixes, verbs and (when they are read) array elements alike; a rule's own
    `path: ""` does not, since the empty segment is exactly one the join leaves alone.
    `leading_slash` is the framework's own three exceptions, verbatim: a segment that
    already starts with `/`, the empty segment, and the bare `*` stay as written; every
    other segment gains a leading `/`. Two spellings of one registration must be one row,
    and the join is what makes `path("api", …)` and `path("/api", …)` the same address here
    as they are in the framework. The prefix is already an address and is written as it
    is."""
    if rule == WORDS:
        return " ".join(word for word in (prefix, path) if word)
    segment = path
    if rule == LEADING_SLASH and path not in ("", "*") and not path.startswith("/"):
        segment = "/" + path
    return (prefix or "") + segment


# The one name a `path_fallback` names on a chain (design 2026-11-06-reading-decorators §3c):
# the construct the registration receives, its handler.
CONSTRUCT_NAME = "construct_name"
_WORD_FALLBACK_KEYS = frozenset({"name", "lower", "replace", "drop_suffixes"})


def validated_word_fallback(declared: Any, where: str) -> dict[str, Any] | None:
    """A `fluent` catalog's `path_fallback` (design 2026-11-06-reading-decorators §3c,
    approved): what a chain's own word is where its root's `url` capture reads no argument —
    `construct_name`, the handler's own name, or the mapping `{name: construct_name, lower,
    replace, drop_suffixes}` stating the framework's respelling of it. None where nothing is
    declared. Anything else is refused, `where` naming the catalog."""
    if declared is None:
        return None
    if declared == CONSTRUCT_NAME:
        return {"lower": False, "replace": {}, "drop_suffixes": ()}
    replace = declared.get("replace", {}) if isinstance(declared, dict) else None
    suffixes = declared.get("drop_suffixes", []) if isinstance(declared, dict) else None
    if (
        not isinstance(declared, dict)
        or not set(declared) <= _WORD_FALLBACK_KEYS
        or declared.get("name") != CONSTRUCT_NAME
        or not isinstance(declared.get("lower", False), bool)
        or not isinstance(replace, dict)
        or not all(isinstance(k, str) and k and isinstance(v, str) for k, v in replace.items())
        or not isinstance(suffixes, list)
        or not all(isinstance(suffix, str) and suffix for suffix in suffixes)
    ):
        raise CatalogError(
            f"{where}: `path_fallback` is `{CONSTRUCT_NAME}` or `{{name: {CONSTRUCT_NAME}, "
            f"lower: bool, replace: {{from: to}}, drop_suffixes: [word]}}`, got {declared!r}"
        )
    return {
        "lower": bool(declared.get("lower", False)),
        "replace": dict(replace),
        "drop_suffixes": tuple(suffixes),
    }


def fallback_word(rule: Mapping[str, Any], name: str) -> str:
    """`name` respelled as a `path_fallback` states, each part in order: lower case, each
    `replace` pair, then a last part in `drop_suffixes` removed with the `-` before it, where
    the name has a `-` (click 8.5.0's `command`: `init_data_command` is `init-data`)."""
    word = name.lower() if rule["lower"] else name
    for old, new in rule["replace"].items():
        word = word.replace(old, new)
    left, separator, last = word.rpartition("-")
    if separator and last in rule["drop_suffixes"]:
        word = left
    return word


# The `open_questions` kind a refused declaration is filed under (`resolve/open_questions.py`
# owns the closed set; this is the one name it holds for the purpose).
REFUSED_REGISTRATION = "refused_registration"

# Why a registration was refused, the candidate's `reason`. One word per rule so a later
# refusal adds a word here and no new kind.
UNROOTED_PATH = "unrooted_path"
# A mount the framework refuses (`mount[].refuses`, Vert.x spec §3c): a mount path with no
# trailing wildcard where the framework needs one (an exact path), a pattern path, and a mount
# point given the wildcard the framework adds itself.
EXACT_MOUNT_PATH = "exact_mount_path"
PATTERN_MOUNT_PATH = "pattern_mount_path"
WILDCARD_MOUNT_POINT = "wildcard_mount_point"
# A route given an empty list of verbs (`http_method`'s list form, D02 §2's `fluent` style): the
# framework refuses a route that serves no verb at all.
NO_METHODS = "no_methods"
# A route whose response type the framework cannot build a response from: a union naming a
# type the catalog says is no response model (`response_fallback.none_types`) beside others.
INVALID_RESPONSE_TYPE = "invalid_response_type"


# What an unread piece of a partly read path starts with, each spelled by the layer that
# owns it: the address reader's `<host>`, the walk's `{}` hole, and the `${…}` / `#{…}`
# notations `canonical_http_path` already refuses to treat as a path half. A path starting
# with one of these has an unknown first character.
_UNKNOWN_START = (UNREADABLE_HOST, HOLE, *EXPRESSION_OPENS)


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
    method_kind: str | None,
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
        {
            "protocol": protocol,
            "method": method,
            "method_kind": method_kind,
            "path": path,
            "candidates": [],
        },
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
                "method_kind": refusals[key]["method_kind"],
                "question": REFUSED_REGISTRATION,
                "candidates": json.dumps(candidates, sort_keys=True, separators=(",", ":")),
                "evidence": "; and ".join(sorted({str(c["caller"]) for c in candidates})),
            }
        )
    return rows
