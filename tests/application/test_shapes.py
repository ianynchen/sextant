from shape_helpers import (
    ORDER_VIEW,
    SPRING_WRAPPERS,
    mono_of,
    response_entity_of,
    unknown_box_of,
)

from sextant.application.resolve.shapes import root_type


def test_unwraps_recursively_to_the_payload_type():
    rooted = root_type(mono_of(response_entity_of(ORDER_VIEW)), SPRING_WRAPPERS)
    assert rooted.symbol == "com/acme/orders/contracts/OrderView#"
    assert rooted.chain == ("async", "http_envelope")
    assert rooted.unmatched_wrapper is False


def test_stops_at_an_unfamiliar_wrapper_and_says_so():
    """An incomplete catalog must degrade visibly. Rooting at the payload of a
    wrapper nobody declared would be a guess presented as an observation."""
    rooted = root_type(unknown_box_of(ORDER_VIEW), SPRING_WRAPPERS)
    assert rooted.symbol == "com/acme/UnknownBox#"
    assert rooted.unmatched_wrapper is True


def test_a_bare_payload_type_is_not_flagged_as_an_unmatched_wrapper():
    """`OrderView` carries no type arguments, so it never looked like an
    envelope in the first place — it is the root, not a gap in the catalog."""
    rooted = root_type(ORDER_VIEW, SPRING_WRAPPERS)
    assert rooted.symbol == "com/acme/orders/contracts/OrderView#"
    assert rooted.chain == ()
    assert rooted.unmatched_wrapper is False
