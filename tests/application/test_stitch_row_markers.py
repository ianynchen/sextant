"""The two row markers the linker reads: a path that is a pattern, and a row that serves any
verb (spec 2026-10-30-vertx-web §3a, §3c, §3g items 3 and 8).

Synthetic rows, because the markers are general machinery and no catalog writes one yet: what
is measured is that the linker reads them, not that some framework sets them.
"""

import pytest

from sextant.application.stitch import Participant, match
from sextant.application.stitch.links import uncalled
from sextant.domain.closed_sets import ANY_METHOD, PATH_KIND_PATTERN
from sextant.domain.paths import canonical_http_path


def _people(*names: str) -> "tuple[Participant, ...]":
    return tuple(Participant(n, n, None, None, True, None) for n in names)


def _inbound(participant: str, method: str | None, path: str, **markers: object) -> dict:
    return {
        "participant": participant,
        "protocol": "http",
        "direction": "inbound",
        "method": method,
        "path": path,
        "handler": "H#h",
        "caller": None,
        "peer": None,
        **markers,
    }


def _outbound(participant: str, method: str | None, path: str) -> dict:
    return {
        "participant": participant,
        "protocol": "http",
        "direction": "outbound",
        "method": method,
        "path": path,
        "handler": None,
        "caller": "C#c",
        "peer": None,
    }


@pytest.mark.pins("paths.a-PATTERN-path-is-never-canonicalised")
def test_a_pattern_path_is_never_canonicalised():
    regex = "\\/telemetry\\/.+"
    assert canonical_http_path(regex, path_kind=PATH_KIND_PATTERN) == regex
    # The same text as a template IS repaired: the marker is what decides, not the text.
    assert canonical_http_path(regex) == "/" + regex


@pytest.mark.pins("stitch.a-PATTERN-path-is-never-linked-by-path")
def test_a_pattern_path_is_never_linked_by_path():
    regex = "/files/.+"
    links, unmatched = match(
        _people("a", "b"),
        [
            _inbound("b", "GET", regex, path_kind=PATH_KIND_PATTERN),
            _outbound("a", "GET", regex),
        ],
    )
    assert links == ()
    assert [u.reason for u in unmatched] == ["no participant in this system serves this address"]


@pytest.mark.pins("stitch.an-ANY-METHOD-row-links-an-outbound-call-of-any-verb")
def test_an_any_method_row_links_an_outbound_call_of_any_verb():
    links, unmatched = match(
        _people("a", "b"),
        [
            _inbound("b", None, "/any", method_kind=ANY_METHOD),
            _outbound("a", "DELETE", "/any"),
            _outbound("a", "PATCH", "/any"),
        ],
    )
    assert unmatched == ()
    assert [(l.to_participant, l.to_method, l.to_path) for l in links] == [("b", None, "/any")] * 2
    assert [l.from_method for l in links] == ["DELETE", "PATCH"]
    # The row is reached, so it is not reported uncalled.
    endpoints = [_inbound("b", None, "/any", method_kind=ANY_METHOD)]
    assert uncalled(endpoints, links) == ()


def test_a_plain_null_method_row_still_links_no_verb():
    links, unmatched = match(
        _people("a", "b"),
        [_inbound("b", None, "/any"), _outbound("a", "GET", "/any")],
    )
    assert links == ()
    assert len(unmatched) == 1


def test_an_exact_verb_beats_nothing_and_keeps_its_own_method():
    """A participant serving the verb by name links at that verb, any-method row beside it
    or not."""
    inbound = [_inbound("b", "GET", "/x"), _inbound("b", None, "/x", method_kind=ANY_METHOD)]
    links, _ = match(_people("a", "b"), [*inbound, _outbound("a", "GET", "/x")])
    assert [(l.to_participant, l.to_method) for l in links] == [("b", "GET")]
    assert uncalled(inbound, links) == ()


@pytest.mark.pins("stitch.a-NAMED-HOLE-in-a-served-path-is-never-linked-by-path")
def test_a_path_holding_a_named_hole_is_never_linked():
    hole = "<prefix>/status"
    links, unmatched = match(
        _people("a", "b"),
        [_inbound("b", "GET", hole), _outbound("a", "GET", hole)],
    )
    assert links == ()
    assert len(unmatched) == 1


def test_a_path_with_an_ordinary_template_variable_still_links():
    links, _ = match(
        _people("a", "b"),
        [_inbound("b", "GET", "/orders/{id}"), _outbound("a", "GET", "/orders/{id}")],
    )
    assert [l.to_path for l in links] == ["/orders/{id}"]


@pytest.mark.pins("stitch.an-UNCALLED-report-skips-pattern-and-named-hole-rows")
def test_a_pattern_or_named_hole_row_is_never_reported_uncalled():
    endpoints = [
        _inbound("b", "GET", "/files/.+", path_kind=PATH_KIND_PATTERN),
        _inbound("b", "GET", "<prefix>/status"),
        _inbound("b", "GET", "/plain"),
    ]
    assert [u.path for u in uncalled(endpoints, ())] == ["/plain"]


@pytest.mark.pins("stitch.an-ANY-METHOD-link-marks-only-the-any-method-row-reached")
def test_an_any_method_link_marks_only_the_any_method_row_reached():
    inbound = [_inbound("b", None, "/p"), _inbound("b", None, "/p", method_kind=ANY_METHOD)]
    links, _ = match(_people("a", "b"), [*inbound, _outbound("a", "GET", "/p")])
    # Only the any-method row serves GET; the plain NULL-method row was not reached.
    assert [(u.method, u.path) for u in uncalled(inbound, links)] == [(None, "/p")]
    assert links[0].to_any_method


@pytest.mark.pins("stitch.an-ANY-METHOD-link-states-no-method")
def test_a_link_to_an_any_method_row_states_no_method_and_one_by_name_states_it():
    links, _ = match(
        _people("a", "b"),
        [_inbound("b", None, "/p", method_kind=ANY_METHOD), _outbound("a", "PUT", "/p")],
    )
    assert (links[0].to_method, links[0].to_any_method) == (None, True)
    links, _ = match(_people("a", "b"), [_inbound("b", "PUT", "/p"), _outbound("a", "PUT", "/p")])
    assert (links[0].to_method, links[0].to_any_method) == ("PUT", False)


@pytest.mark.pins("stitch.an-ANY-METHOD-row-is-reached-through-a-by-name-link-on-its-path")
def test_an_any_method_row_beside_a_by_name_row_is_reached_by_the_by_name_link():
    # The first test above covers this through `uncalled`; here the any-method row is
    # asserted reached on its own, with the exact-verb row also present.
    inbound = [_inbound("b", "GET", "/x"), _inbound("b", None, "/x", method_kind=ANY_METHOD)]
    links, _ = match(_people("a", "b"), [*inbound, _outbound("a", "GET", "/x")])
    assert uncalled(inbound, links) == ()


@pytest.mark.pins("stitch.an-ANY-METHOD-row-links-an-outbound-call-of-any-verb")
def test_an_outbound_call_with_no_verb_links_an_any_method_row():
    links, unmatched = match(
        _people("a", "b"),
        [_inbound("b", None, "/p", method_kind=ANY_METHOD), _outbound("a", None, "/p")],
    )
    assert unmatched == ()
    assert [(l.from_method, l.to_participant, l.to_method) for l in links] == [(None, "b", None)]


@pytest.mark.pins("stitch.an-uncalled-ANY-METHOD-row-says-so")
def test_an_uncalled_any_method_row_carries_its_marker_and_a_plain_one_does_not():
    # The system document prints `any` off this flag (final review C1); the NULL method alone
    # cannot tell the two rows apart.
    inbound = [_inbound("b", None, "/p"), _inbound("b", None, "/q", method_kind=ANY_METHOD)]
    assert [(u.path, u.any_method) for u in uncalled(inbound, ())] == [
        ("/p", False),
        ("/q", True),
    ]
