"""No catalog seeds an identity value the matched call does not evidence
(GUIDELINES §8, §8.3; `docs/principles-sweep-2026-09-05.md` §4).

## The rule

**No derivation may publish a defaulted value at `resolved`/`compiler`. A
value that comes from a catalog default rather than from evidence is
`unresolved`, or the row does not ship.**

That is §8's *"absent evidence, produce nothing"* said about one particular way
of breaking it, and it was broken four times before it was written down
(sweep §4.1). This file is the half of the mechanism §8.3 demands beside the
prose: the retroactive audit list of every shipped site the rule now governs,
as an allowlist that only shrinks.

## What this file can enforce, and what it deliberately cannot

A defaulted value is one the MATCHED evidence says nothing about. Whether that
is possible is a property of the engine style, and only one style can do it:

* `single_call` and `annotation_driven` publish from a single matched
  construct. A verb declared beside `getForObject` or beside
  `@DeleteExchange` is read off the thing that was matched — the framework's
  own rule for that construct — and nothing later in the derivation can
  contradict it. `spring-actuator`'s `@ReadOperation → GET` is the same shape:
  a measured framework rule (CP-5), attached to the annotation that carries it.
* `fluent` is different in kind. A chain's captures fold across several calls,
  last wins, and **an unmatched step passes through uncaptured** (D02 §4). A
  literal seeded where the matched call does not name it therefore survives
  every call the catalog failed to model — silently, at `resolved`/`compiler`.
  That is exactly `A-C2`: `Request.Builder.<init>` seeded `http_method: GET`,
  `.method("DELETE", body)` was not a declared step, and the module's DELETE
  shipped as a GET.

So the enforceable form is: **a `fluent` root or step may declare a literal
identity value only where its own method name IS that value.** `webClient.get()`
names GET; `Request.Builder.<init>` names nothing.

What it cannot check is the other half — that every framework method which
OVERRIDES the seeded value is a declared step. That is a framework-completeness
question, answerable only by measurement (§8.1, "measure; do not reason"), and
each allowlist entry below states it as the condition that would make the entry
wrong (§9).

It is OFFLINE and deterministic (NFR-1): it reads the shipped catalogs and runs
nothing.
"""

import re
from pathlib import Path

import yaml

REPO = Path(__file__).parents[2]
CATALOGS = REPO / "src" / "sextant" / "catalogs"

# The capture fields that reach an identity column of `endpoints`
# (`derive_call_endpoints.sql`'s own `method`/`path`/`peer`). `url`, `base` and
# `channel` are already refused as literals by the engine itself
# (`fluent._validate_captures` demands `argN` for every `_ARGUMENT_FIELDS`
# member), so `http_method` is the one field a catalog can spell as a literal
# at all — and it is the one that shipped wrong.
_IDENTITY_CAPTURES = ("http_method",)

# A capture spelled `argN` addresses the matched call's own argument, so it IS
# the evidence and can never be a seeded default: where the argument cannot be
# read the engine answers NULL at `unresolved` rather than falling back to a
# literal (`fluent._derive`). Excluded from the scan for that reason and not as
# a convenience — an `argN` value on an identity field is the shape this rule
# wants catalogs to move TOWARD.
_READS_THE_CALL_SITE = re.compile(r"^arg\d+$")

# Sites where a `fluent` entry seeds an identity value its own method name does
# not name. An ALLOWLIST, not a backlog: each entry records a framework DEFAULT
# that is genuinely true of the matched call, together with the condition that
# would make it wrong (§9). It does not travel in the direction of getting
# longer.
_FRAMEWORK_DEFAULT_AT_THE_ROOT = {
    ("okhttp", "roots", "<init>", "http_method", "GET"): (
        "a bare `okhttp3.Request$Builder` really does issue GET — OkHttp's own "
        "documented default, and the reason the seed must NOT simply be deleted "
        "(deleting it under-reports every plain `.url().build()` chain). This is "
        "admissible only while every `Request.Builder` method that SETS the verb "
        "is a declared step, because an unmatched step passes through uncaptured "
        "and leaves this literal standing. That condition is met at okhttp "
        "4.12.0: `javap -p -s` gives eight verb-setting methods and `okhttp.yml` "
        "declares a step for every one, pinned by "
        "`test_sweep_round1_framework_rules.py` against CP-11 "
        "(`scripts/probes/cp11_sweep_round1.md`). It stops being right the day "
        "OkHttp adds a ninth this catalog does not declare."
    ),
}


def literal_identity_captures() -> list[dict[str, str]]:
    """Every `fluent` root/step entry declaring a literal identity capture.

    Enumerated off the directory and walked over `matches.roots` /
    `matches.steps` by key name, never listed: the one thing this rule must not
    do is stop seeing an entry.
    """
    found: list[dict[str, str]] = []
    for path in sorted(CATALOGS.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if document.get("style") != "fluent":
            continue
        matches = document.get("matches") or {}
        for where in ("roots", "steps"):
            for entry in matches.get(where) or []:
                captures = entry.get("captures") or {}
                for field in _IDENTITY_CAPTURES:
                    if field not in captures or _READS_THE_CALL_SITE.match(str(captures[field])):
                        continue
                    found.append(
                        {
                            "catalog": str(path.stem),
                            "where": where,
                            "method": str(entry.get("method")),
                            "field": field,
                            "value": str(captures[field]),
                        }
                    )
    return found


def _identity(row: dict[str, str]) -> tuple[str, str, str, str, str]:
    return (row["catalog"], row["where"], row["method"], row["field"], row["value"])


def _names_its_own_value(row: dict[str, str]) -> bool:
    """Whether the matched call's own name IS the value being captured.

    `startswith`, not equality: `postForObject` and `getForEntity` are the
    `single_call` spelling of the same entailment, and a `fluent` library that
    named its verb setters `postJson`/`getJson` would be the same fact. What it
    refuses is a name that shares no prefix with the verb at all — `<init>`,
    `newBuilder`, `build`.
    """
    return row["method"].lower().startswith(row["value"].lower())


def test_no_fluent_entry_seeds_an_identity_value_its_own_call_does_not_name():
    """The rule. A seeded verb survives every call the catalog failed to model,
    and ships at `resolved`/`compiler` where nothing downstream can tell it from
    an observation — which is how `.method("DELETE", body)` published GET."""
    defaulted = sorted(
        _identity(row)
        for row in literal_identity_captures()
        if not _names_its_own_value(row) and _identity(row) not in _FRAMEWORK_DEFAULT_AT_THE_ROOT
    )
    assert defaulted == [], (
        "these shipped `fluent` entries seed an identity value their own matched call does "
        "not name, and are not on this file's allowlist:\n"
        + "\n".join(
            f"  - {catalog}: {where} `{method}` captures {field}: {value}"
            for catalog, where, method, field, value in defaulted
        )
        + "\n\nEither read the value off the call site (`http_method: argN`), or — where the "
        "literal really is the framework's own default for a call that names nothing — add it "
        "to _FRAMEWORK_DEFAULT_AT_THE_ROOT with the condition that would make it wrong."
    )


def test_the_allowlist_only_ever_shrinks():
    """An entry naming a site that no longer ships, or one whose own call now
    names its value, must go in the same commit.

    Without this the list is write-only: a tuple could sit here forever after
    the catalog stopped needing it, exempting a site that no longer exists and
    — worse — pre-exempting any future entry that happens to match it.
    """
    shipped = {_identity(row) for row in literal_identity_captures()}
    entailed = {_identity(row) for row in literal_identity_captures() if _names_its_own_value(row)}
    unknown = sorted(set(_FRAMEWORK_DEFAULT_AT_THE_ROOT) - shipped)
    stale = sorted(set(_FRAMEWORK_DEFAULT_AT_THE_ROOT) & entailed)
    assert (unknown, stale) == ([], []), (
        "_FRAMEWORK_DEFAULT_AT_THE_ROOT is out of date — "
        f"names no shipped `fluent` entry: {unknown or 'none'}; "
        f"names an entry whose own call now names its value: {stale or 'none'}"
    )


def test_every_allowlisted_default_records_why_it_is_not_an_invention():
    """§9: a comment justifying an omission states the condition that would make
    it wrong. An allowlist of bare tuples is a list of exemptions nobody can
    review — the reason IS the audit."""
    unexplained = sorted(
        site for site, reason in _FRAMEWORK_DEFAULT_AT_THE_ROOT.items() if len(reason) < 80
    )
    assert unexplained == [], (
        f"these allowlist entries carry no stated reason and revisit condition: {unexplained}"
    )


def test_the_scan_finds_the_seeded_verbs_that_ship():
    """A check that discovers nothing passes for the wrong reason — an empty
    scan has no defaulted values either, and the file would assert only that the
    allowlist is complete.

    Two pins, one per side of the entailment: `okhttp`'s own `get` step, which
    the rule ADMITS because the call names the verb, and `spring-webclient`'s
    `get` root, which is the same fact at the other grammar position. A walk
    that lost either would exempt everything it enforces.
    """
    shipped = {_identity(row) for row in literal_identity_captures()}
    assert ("okhttp", "steps", "get", "http_method", "GET") in shipped
    assert ("spring-webclient", "roots", "get", "http_method", "GET") in shipped
    # A floor, deliberately not the shipped total: a count would fail a second
    # time on every legitimate catalog edit and say nothing the rule has not.
    assert len(shipped) >= 15
