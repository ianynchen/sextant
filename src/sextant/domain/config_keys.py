"""How a configuration key is compared, wherever it is compared.

The rule lived in `application/resolve/config.py` while resolution was its only
caller. 2K's redactor is a second one, and it sits in `domain` — below
`application`, so it cannot import the resolver — which leaves exactly two
options: one rule here, or a second copy of Spring's binding grammar drifting
beside the first. `resolve/config.py` re-exports this function, so every
existing caller reads unchanged.
"""


def normalize_key(key: str) -> str:
    """Spring's own RELAXED binding rule (D02 §2i's `key_matching: relaxed`):
    case-insensitive, with `-` and `_` stripped, so kebab-case, camelCase and
    `ENV_VAR` spellings of one key compare equal. A pure function so Task 8's
    field ladder (2F design §4's `@ConfigurationProperties(prefix)` rung)
    can reuse the exact same rule this pass uses for `${...}` references,
    rather than a second, drifting copy of Spring's binding grammar."""
    return key.lower().replace("-", "").replace("_", "")
