"""Canonical HTTP path identity (2O design §8).

**Why this exists.** `@RequestMapping("users")` and `@RequestMapping("/users")`
are the same URL to Spring (CP-1), and until this seam they were two endpoint
identities to us — which splits dedup, splits every path-keyed anchor, and
would split L's cross-service joins. Identity therefore becomes THE URL THE
FRAMEWORK SERVES, canonicalized in exactly one place so no engine can drift.

**What this deliberately does not touch.** A `path` holding a whole address or
a placeholder-bearing composition is not a path half — D02 keeps those whole
until the peer join splits them, and prefixing one fabricates a URL nobody
serves. `is_path_shaped` is the guard, and it is conservative: anything
carrying a scheme or a placeholder is left exactly as written.

**Scope.** HTTP only (SSE rows inherit it — `protocol_hint` reclassifies after
identity is minted). GraphQL paths are FIELD NAMES, not URLs; websocket is
deferred until a path-kind marker exists (2O §8).

**The one mirror.** `derive_endpoints.sql` composes its own path in SQL, from
columns this layer never sees, so it applies the same two rules there under
its `$canonical_path` gate rather than calling in. That mirror is pinned
against this module by `tests/application/test_endpoints.py::
test_the_sql_path_seam_answers_exactly_what_the_domain_seam_answers`, which
runs both over the SAME case table — the `derive_endpoints.sql`/
`annotation_driven.py` precedent for a rule that has to be stated on both
sides of the SQL boundary (`_destinations_of`'s own note), and the reason
storage may not simply import this module: ARCHITECTURE §10 forbids a
protocol name in `storage/`, and this seam's name is one.
"""

_SCHEME = "://"
_PLACEHOLDER_OPEN = "${"


def is_path_shaped(raw: str) -> bool:
    """False for anything that is a whole address rather than a path half."""
    return _SCHEME not in raw and _PLACEHOLDER_OPEN not in raw


def canonical_http_path(raw: str) -> str:
    """`raw` as the URL the framework serves, or `raw` untouched when it is
    not a path half. Trailing slashes are PRESERVED: Framework 6 removed
    trailing-slash matching, so `/users/` is a different URL from `/users`."""
    if not is_path_shaped(raw):
        return raw
    if raw == "":
        return "/"
    collapsed = raw
    while "//" in collapsed:
        collapsed = collapsed.replace("//", "/")
    return collapsed if collapsed.startswith("/") else "/" + collapsed
