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

**Scope.** INBOUND HTTP only (SSE rows inherit it — `protocol_hint` reclassifies
after identity is minted). GraphQL paths are FIELD NAMES, not URLs; websocket is
deferred until a path-kind marker exists (2O §8).

**Why OUTBOUND http is excluded (ruling R8).** CP-1 is evidence about what a
server SERVES, and a client's declaration is not the same kind of value. A
client mapping written without a leading separator is resolved against its
configured base address's PATH, while one written with a leading separator is
root-relative: against a base of `https://host/v1/`, `invoices` and
`/invoices` are two different URLs, so prefixing the first REWRITES an address
rather than normalizing a spelling — the approximation DR-6 forbids, and the
reason divergent frameworks get separate units here rather than one averaged
rule. §8's whole purpose — one identity per route the module SERVES, so dedup,
the path-keyed anchors and L's cross-service joins agree — is served by the
inbound half alone. An outbound row's identity is a composed address that the
peer join governs, and it keeps whatever half the declaration actually wrote.

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

from sextant.domain.closed_sets import Direction, Protocol

_SCHEME = "://"
# The two notations an unresolved address arrives in: a property placeholder
# and an expression-language reference. BOTH, not one, because the guard's
# claim is "this is not a path half yet" and neither notation is — a rule that
# knew only `${` would rewrite `#{…}` into a URL nobody serves, which is the
# fabrication this guard exists to refuse. They are listed here together, and
# mirrored together in `derive_endpoints.sql`'s own `$canonical_path` gate;
# a third notation belongs in both places or in neither. This stays right for
# as long as no framework spells a SERVED path with either sequence — a
# framework that did would have its literal address left uncanonicalized here.
_EXPRESSION_OPENS = ("${", "#{")


def serves_urls(protocol: str, direction: str) -> bool:
    """Whether a catalog's addresses are URLs THIS MODULE SERVES — the one
    gate every caller of `canonical_http_path` asks (ruling R8).

    Spelled once, here, rather than four times in four engines plus a fifth
    time as the `$canonical_path` bind `derive_endpoints.sql` reads: the two
    halves of that pair are pinned against each other by a test, and a gate
    restated per engine is the drift that test could not see.
    """
    return protocol == Protocol.HTTP and direction == Direction.INBOUND


def is_path_shaped(raw: str) -> bool:
    """False for anything that is a whole address rather than a path half."""
    return _SCHEME not in raw and not any(open_ in raw for open_ in _EXPRESSION_OPENS)


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
