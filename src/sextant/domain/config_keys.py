"""How a configuration key is compared, wherever it is compared.

The rule lived in `application/resolve/config.py` while resolution was its only
caller. 2K's redactor is a second one, and it sits in `domain` — below
`application`, so it cannot import the resolver — which leaves exactly two
options: one rule here, or a second copy of Spring's binding grammar drifting
beside the first. Every former caller imports it from here now — no module
re-exports it, because an implicit re-export is a second name for one rule and
the point of the move was to have one.
"""


def normalize_key(key: str) -> str:
    """Spring's own RELAXED binding rule (D02 §2i's `key_matching: relaxed`):
    case-insensitive, with `-` and `_` stripped, so kebab-case, camelCase and
    `ENV_VAR` spellings of one key compare equal. A pure function so Task 8's
    field ladder (2F design §4's `@ConfigurationProperties(prefix)` rung)
    can reuse the exact same rule this pass uses for `${...}` references,
    rather than a second, drifting copy of Spring's binding grammar."""
    return key.lower().replace("-", "").replace("_", "")


# D01's own placeholder form — the expression an endpoint row carries until
# the per-environment join resolves it (`resolved_peers`, whose SQL matches on
# exactly this delimiter pair). Rungs 1 and 2 return an expression the facts
# already spell; rung 3 SYNTHESISES one from a prefix and a property name, so
# it is the one rung that has to write the delimiters itself.
#
# Written here rather than read from a `config_model` for the same reason the
# relaxed-binding rule below is applied unconditionally: `placeholders` and
# `key_matching` are declared on the framework FAMILY's base catalog, and a
# client catalog — the only thing this ladder is handed — cannot see them.
# `resolved_peers`' own SQL already hard-codes this same pair, so one form is
# assumed in exactly two places rather than one; a non-`${}` ecosystem has to
# thread the pair onto `field_sources` and into that query together.
_PLACEHOLDER = ("${", "}")


def carries_expression(text: str) -> bool:
    """Whether an address carries a D01 placeholder — an OPEN delimiter with
    a matching CLOSE after it, `resolve/config.py`'s own reading (an
    unterminated `${` is literal text there too).

    What it decides: an address containing one is unsplittable, whatever else
    it looks like (2F design §4). `https://${billing.host}/orders` matches
    CP-2's absolute-URL shape perfectly and splitting it would write
    `${billing.host}` into the `peer` column as if it were an authority —
    a peer no environment ever named, and one the per-environment join reads
    only from `path`/`peer` as WHOLE expressions. So the check runs BEFORE the
    split, never after."""
    open_, close = _PLACEHOLDER
    start = text.find(open_)
    return start != -1 and close in text[start + len(open_) :]
