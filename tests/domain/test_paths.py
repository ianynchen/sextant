import pytest

from sextant.domain.paths import canonical_http_path, is_path_shaped


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
