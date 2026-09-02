"""Redaction (2K design §1, D04 §"The mark a redaction leaves").

**One redactor, applied at the exits.** The workspace stays verbatim — analysis
needs real values locally (peer resolution substitutes real addresses), and the
user's own disk is not the trust boundary. Masking happens where data crosses
that boundary: the rendered document, the exported bundle, and (2K Task 5) the
enrichment tools' read path. Nothing here writes to a table or a fact; a caller
projects a value through this module on its way out.

**Additive only, by construction.** `from_rules` takes *additions* and unions
the built-ins in itself, so there is no argument a caller could pass — and no
`.sextant.yml` anyone could write — that narrows the set. D04 §1 states the
rule ("a repository cannot switch redaction off"); making the built-ins
un-passable is what keeps it true rather than documented.

**The marker is `«redacted»`.** Guillemets, so it is not a value any config
file, URL or topic name could legitimately carry, and one stable literal so a
masked value still counts as present, compares equal across runs, and greps.
"""

import hashlib
import json
import re
from dataclasses import dataclass

from sextant.domain.config_keys import normalize_key

REDACTED = "«redacted»"

# The built-in key patterns, already normalized (`normalize_key`), matched as
# SUBSTRINGS of a normalized key. Normalization is what makes the set both
# case- and format-insensitive: `api-key`, `api_key` and `apiKey` all normalize
# to `apikey`, so one entry covers the spellings 2K design §1 writes as
# `api[-_]?key` — the regex there describes matching against a RAW key, and
# against a normalized one it is exactly this literal.
BUILTIN_KEY_PATTERNS = (
    "apikey",
    "authorization",
    "credential",
    "passphrase",
    "password",
    "privatekey",
    "secret",
    "token",
)

# There are no built-in VALUE patterns. 2K design §1 names key-pattern masking
# and URL userinfo stripping as the built-in rules and nothing else; a repo adds
# value regexes when it knows the shape of its own secrets. A built-in guess at
# that shape would mask real addresses and topic names in every document Sextant
# renders, which is the failure NFR-7 cares about most.

# `scheme://user:pass@host` → `scheme://host`. Anchored on the scheme so the
# `@` in a path, a query string or a bare hostname is untouched, and bounded by
# the delimiters that end an authority (`/`, `?`, `#`) so an `@` further along
# the URL cannot be mistaken for userinfo. A `${...}` expression carries no
# `://`, so it passes through whole — which is the 2I ruling: an expression is
# a REFERENCE to a value, never the value, and there is no secret inside it.
_USERINFO = re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]*://)[^/?#\s@]*@")


class RedactionError(ValueError):
    """A redaction rule that cannot be honoured as written."""


@dataclass(frozen=True)
class RedactionRules:
    """What a repository ADDS to the built-in set (`.sextant.yml`'s `redact:`).

    `key_patterns` are substrings matched against a normalized config key;
    `value_patterns` are regular expressions matched against a value's text.
    Both default to empty — the ordinary module, which redacts by the built-in
    set alone.
    """

    key_patterns: tuple[str, ...] = ()
    value_patterns: tuple[str, ...] = ()


NO_ADDITIONS = RedactionRules()


class Redactor:
    """The effective rule set, compiled once and applied at every exit.

    Construct through `from_rules`. Instances are immutable and hold no state
    between calls, so one redactor serves a whole run — which is the point:
    `rule_set_hash` names the rules a given run's outputs were masked with.
    """

    def __init__(self, key_patterns: tuple[str, ...], value_patterns: tuple[str, ...]) -> None:
        self._key_patterns = key_patterns
        self._value_patterns = value_patterns
        self._compiled = tuple(re.compile(pattern) for pattern in value_patterns)

    @classmethod
    def from_rules(cls, additions: RedactionRules = NO_ADDITIONS) -> "Redactor":
        """The built-ins WIDENED by `additions` — never replaced by them.

        Raises `RedactionError` for an addition that cannot be applied: an
        empty key pattern (which would match every key), an empty value
        pattern, or a value pattern that is not a regular expression. A repo
        that widens redaction into nonsense is Sextant's own input written
        wrong (D04 §2a's refusal), not evidence to skip.
        """
        keys = set(BUILTIN_KEY_PATTERNS)
        for pattern in additions.key_patterns:
            normalized = normalize_key(pattern)
            if not normalized:
                raise RedactionError(
                    f"redact key pattern {pattern!r} is empty — it matches every key"
                )
            keys.add(normalized)
        values = set()
        for pattern in additions.value_patterns:
            if not pattern:
                raise RedactionError("redact value pattern is empty — it matches every value")
            try:
                re.compile(pattern)
            except re.error as failure:
                raise RedactionError(
                    f"redact value pattern {pattern!r} is not a regular expression: {failure}"
                ) from failure
            values.add(pattern)
        # Sorted here, once: the effective set is a SET, and sorting it at
        # construction is what makes `rule_set_hash` independent of the order
        # a `.sextant.yml` happened to list its additions in.
        return cls(tuple(sorted(keys)), tuple(sorted(values)))

    @property
    def rule_set_hash(self) -> str:
        """The sha256 of the effective rule set, canonically serialized (D05
        §2's `redaction_set_hash`, D06 §3's reserved manifest field).

        Canonical means: the normalized, deduplicated, sorted sets, dumped as
        JSON with sorted keys and no incidental whitespace. So two runs of the
        same rules hash the same however the file listed them, and changing a
        rule — adding one, removing one, editing one — changes the hash.
        """
        canonical = json.dumps(
            {
                "key_patterns": list(self._key_patterns),
                "value_patterns": list(self._value_patterns),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def redact_value(self, key: str, value: str) -> str:
        """One configuration value, masked by the key that names it or by what
        it contains. A key matching the effective key set masks the value
        WHOLE — the key already says the value is a secret, so no amount of
        structure in it is safe to keep. Anything else falls through to
        `redact_text`, which still strips URL userinfo and applies the value
        patterns."""
        normalized = normalize_key(key)
        if any(pattern in normalized for pattern in self._key_patterns):
            return REDACTED
        return self.redact_text(value)

    def redact_text(self, text: str) -> str:
        """Free text — an address expression, a rendered line, a tool result —
        with URL userinfo stripped and every value-pattern match replaced by
        the marker. Text nothing matches is returned unchanged, byte for byte:
        a redactor that reformatted what it does not mask would change every
        document it touched."""
        redacted = _USERINFO.sub(r"\g<scheme>", text)
        for pattern in self._compiled:
            redacted = pattern.sub(REDACTED, redacted)
        return redacted
