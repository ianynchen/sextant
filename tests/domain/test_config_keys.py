"""The relaxed configuration-key binding rule, which two layers now share.

It lived in `application/resolve/config.py` while resolution was its only
caller. 2K's redactor is the second, and `domain` cannot import `application`
— so the rule moved down rather than being copied, and its test moved with it.
What the test pins is unchanged: Spring's own RELAXED binding (D02 §2i), the
rule both `${...}` lookups and key-pattern redaction compare through.
"""

from sextant.domain.config_keys import normalize_key


def test_normalize_key_strips_case_dash_and_underscore():
    """A pure function, not a method on anything, so either layer can import
    it without pulling in the other's pass (2F design §4's field ladder was
    the first reuse; redaction's key patterns are the second)."""
    assert normalize_key("my-key") == normalize_key("MY_KEY") == normalize_key("myKey")


def test_normalize_key_keeps_the_dots_that_separate_segments():
    """The separators it strips are the ones Spring treats as spelling; a `.`
    is structure. Redaction depends on this: `orders.internal.dsn` must stay
    three segments, or a pattern naming one segment would match across two."""
    assert normalize_key("orders.internal.DSN") == "orders.internal.dsn"
