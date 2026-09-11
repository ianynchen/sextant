import pytest

from sextant.domain.paths import canonical_http_path, is_path_shaped, serves_urls


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("users", "/users"),  # CP-1: Spring serves this at /users
        ("/users", "/users"),
        ("/api//users", "/api/users"),  # one separator per boundary
        ("/users/", "/users/"),  # Framework 6: trailing slash is DISTINCT
        ("", "/"),
    ],
)
def test_canonicalization_matches_what_spring_serves(raw: str, expected: str) -> None:
    assert canonical_http_path(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "https://billing.example/orders",  # a whole address, not a path half
        "https://${billing.host}/orders",  # placeholder-bearing composition
        "${service.base}/orders",
    ],
)
def test_whole_addresses_are_not_path_shaped_and_are_never_prefixed(raw: str) -> None:
    # D02 keeps a composed address whole in `path` until the peer join resolves
    # it; prefixing one would publish a URL nobody serves.
    assert not is_path_shaped(raw)
    assert canonical_http_path(raw) == raw


@pytest.mark.parametrize(
    "protocol, direction, expected",
    [
        ("http", "inbound", True),
        # Ruling R8: a CLIENT's slashless path resolves against its base
        # address's own path while a leading separator is root-relative, so
        # canonicalizing one rewrites an address instead of normalizing a
        # spelling. CP-1 is evidence about a server.
        ("http", "outbound", False),
        # A topic is not a URL and has no separators to normalize.
        ("kafka", "inbound", False),
        ("kafka", "outbound", False),
        # GraphQL's address is a FIELD NAME; websocket shares one protocol
        # with STOMP destinations. Both are out for their own reasons, and
        # both fall out of the same protocol test.
        ("graphql", "inbound", False),
        ("websocket", "inbound", False),
        # `both` is minted by D02 §3's merge, long after identity — no
        # catalog declares it, and the gate never sees it.
        ("http", "both", False),
    ],
)
def test_only_an_inbound_http_catalog_addresses_urls_this_module_serves(
    protocol: str, direction: str, expected: bool
) -> None:
    assert serves_urls(protocol, direction) is expected
