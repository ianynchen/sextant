"""`paths_of`: the three structural reads of a route expression (design 2026-11-22 §5c,
rulings R15 and R16), each case measured in `scripts/probes/django_rules.md`, "`re_path`"."""

import pytest

from sextant.application.resolve.shapes.route_expression import paths_of


@pytest.mark.parametrize(
    ("expression", "prefix", "paths", "exact"),
    [
        ("^graphql/$", False, ("graphql/",), True),
        # A prefix with no `$` is a prefix match: exact as a mount prefix.
        ("^api/v1/", True, ("api/v1/",), True),
        ("^download/(?P<id>[^/]+)/$", False, ("download/<id>/",), True),
        ("^opensearch\\.xml$", False, ("opensearch.xml",), True),
        # As a mount prefix two exact prefixes; as an endpoint it also serves longer paths.
        ("^directory/?", True, ("directory", "directory/"), True),
        ("^directory/?", False, ("^directory/?",), False),
        (
            "^r/(?P<id>\\d+)(\\.json)?/?$",
            False,
            ("r/<id>", "r/<id>/", "r/<id>.json", "r/<id>.json/"),
            True,
        ),
        ("^u/(?P<a>\\d+)/(?P<b>\\d+)?$", False, ("u/<a>/", "u/<a>/<b>"), True),
        ("^deactivate?$", False, ("deactivat", "deactivate"), True),
        ("^a?/b?/c?$", False, ("^a?/b?/c?$",), False),
        ("^(shelf|books)/x/$", False, ("^(shelf|books)/x/$",), False),
        ("^x/[a-z]+/$", False, ("^x/[a-z]+/$",), False),
        ("^s/(?P<status>(local|federated))/$", False, ("s/<status>/",), True),
        # An optional group in the middle drops only the group.
        ("^m/(?P<x>\\d+)?/end/$", False, ("m//end/", "m/<x>/end/"), True),
        # A final `$` is a full match without `^`; neither anchor is a search.
        ("mid/x$", False, ("mid/x",), True),
        ("loose/", False, ("loose/",), False),
        ("loose/", True, ("loose/",), False),
        ("^noend", False, ("^noend",), False),
        # An unnamed group that is not optional, beside a named one, still matches text.
        ("^mixed/(\\d+)/(?P<n>[a-z]+)/$", False, ("^mixed/(\\d+)/(?P<n>[a-z]+)/$",), False),
        # A `^` that is not at the start, a backslash other than `\.`, `\-`, `\/`.
        ("^user/^user/(?P<u>\\w+)/?$", False, ("^user/^user/(?P<u>\\w+)/?$",), False),
        ("^a\\-b\\/c$", False, ("a-b/c",), True),
        ("^a\\d$", False, ("^a\\d$",), False),
        # Not a named group, a group not closed, a quantifier on a group.
        ("^(?:a)/$", False, ("^(?:a)/$",), False),
        ("^(?P<a>x/$", False, ("^(?P<a>x/$",), False),
        ("^(?P<a>x)+/$", False, ("^(?P<a>x)+/$",), False),
        ("^a??$", False, ("^a??$",), False),
        ("^.$", False, ("^.$",), False),
        # A real route's unescaped dot is any character: not exact.
        ("^robots.txt$", False, ("^robots.txt$",), False),
        # Fix round 1 (probe: a mount prefix is not backtracked across the include boundary):
        # a named group that can end the prefix takes all it can, so not exact; one followed by
        # a required literal stays exact. An endpoint is matched whole and is not affected.
        ("^(?P<lang>[a-z]{2})?/?", True, ("^(?P<lang>[a-z]{2})?/?",), False),
        ("^(?P<slug>[\\w-]+)", True, ("^(?P<slug>[\\w-]+)",), False),
        ("^(?P<lang>[a-z]{2})/", True, ("<lang>/",), True),
        ("^x/(?P<a>\\d+)$", False, ("x/<a>",), True),
    ],
)
def test_paths_of(expression: str, prefix: bool, paths: tuple[str, ...], exact: bool) -> None:
    assert paths_of(expression, prefix=prefix) == (paths, exact)


def test_the_brief_interfaces() -> None:
    assert paths_of("^inbox/?$") == (("inbox", "inbox/"), True)
    assert paths_of("^old/(?P<item_id>\\d+)/$") == (("old/<item_id>/",), True)
    assert paths_of("^(shelf|books)/$") == (("^(shelf|books)/$",), False)
