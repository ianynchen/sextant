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
#
# A substring rule OVER-MASKS, and that is the accepted side (2K Task 1 review,
# ruled): `aws.secretsmanager.endpoint` masks a hostname. Under-masking leaks a
# credential and cannot be undone once a bundle has left; over-masking hides a
# value from a document that still says the key is present. The day it costs a
# real workflow something, the fix is a MORE PRECISE pattern here — never a
# reveal mechanism, which this module has no way to express.
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
# the URL cannot be mistaken for userinfo. Up to the authority's LAST `@`: RFC
# 3986 forbids a raw `@` in a host, and a password may itself carry an
# unencoded one — stopping at the first left `https://ss@host` of
# `https://u:p@ss@host` (found 2026-10-23). Any character but a delimiter or
# whitespace may precede that `@`: a password carries what it carries, and the
# NTLM proxy form `http://CORP\\jdoe:pass@proxy` has a backslash in its user.
# The cost is text, never a secret: in compact raw text with no delimiter
# between a bare-host URL and a later `@` (`url='https://svc',owner='a@x.com'`)
# the strip runs on into the next value (OI-178). A `${...}` expression carries no
# `://`, so it passes through whole — which is the 2I ruling: an expression is
# a REFERENCE to a value, never the value, and there is no secret inside it.
#
# There is deliberately no rule for userinfo WITHOUT a scheme. In text,
# `svc:s3cret@billing.internal` cannot be told from `mailto:ops@billing.internal`
# or `jdbc:oracle:thin:@localhost:1521:XE`, so such a rule rewrites real
# addresses (both found by review on 2026-10-23). The one place that shape
# arose — a URL's authority once `split_url` removed its scheme — now drops
# the userinfo where the shape is KNOWN (`authority_without_userinfo`).
_USERINFO = re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]*://)[^/?#\s]*@")


def authority_without_userinfo(authority: str) -> str:
    """An AUTHORITY with its userinfo dropped: RFC 3986 §3.2's `[userinfo "@"] host [":"
    port]` reduced to host and port, which is the service a call reaches — a credential
    written into the URL is never part of WHICH service that is.

    For a value the caller KNOWS is an authority (`split_url`'s, or an `lb://` target), so
    there is nothing to guess: everything up to the last `@` goes, whatever the host and
    port look like — `billing:{port}`, `${billing.host:localhost}` and `[::1]:8080` all keep
    their own spelling (a host that is a template is the case a shape test missed, found by
    review on 2026-10-23). An `@` inside a `{...}` placeholder is the placeholder's own text
    and is skipped.

    The authority ends at the first `/`, `?` or `#` outside a placeholder, and nothing after
    it is userinfo: `localhost:8080?user=admin@corp.com` keeps its host. Where the braces
    never balance (`svc:p{ss@billing`), they are not a placeholder, and the last `@` before
    the end of the authority is taken regardless — stripping too much rather than keeping a
    password no exit can see."""

    def cut(skip_braces: bool) -> tuple[int, int]:
        depth = 0
        last_at = -1
        for index, character in enumerate(authority):
            if skip_braces and character == "{":
                depth += 1
            elif skip_braces and character == "}":
                depth = max(0, depth - 1)
            elif depth == 0 and character in "/?#":
                break
            elif depth == 0 and character == "@":
                last_at = index
        return last_at, depth

    last_at, depth = cut(skip_braces=True)
    if depth:
        last_at, _ = cut(skip_braces=False)
    return authority[last_at + 1 :]


# What a NAME looks like, for the paired rule `Redactor._masked` applies. A header
# name, a query-parameter name or a form-field name is one token — letters,
# digits and the three separators a name may carry — and never prose.
#
# The constraint is the whole reason the paired rule is safe. `redact_value`'s
# substring match is right for a configuration key, where every key is already
# a name; against arbitrary strings read out of bytecode it also matches log
# formats ("Changed password for User: {}") and SQL ("UPDATE users SET
# password=:password ..."), and the argument after either of those is not a
# credential. Requiring the token shape separates them: measured over the
# 6,185 call sites of `orders-service`, `jhipster-sample-app` and
# `spring-petclinic-rest`, it pairs on exactly one string — an `Authorization`
# header — and on none of the five prose and SQL strings a bare substring
# match pairs on.
_KEY_TOKEN = re.compile(r"[A-Za-z0-9._-]{1,64}\Z")

# What `Redactor.json_text_prefilter` is built from: each rule restated as the
# LOOSER test "the JSON text contains something this rule could act on", in
# the RE2 dialect. RE2 is what the export's own query engine runs, and it is
# not Python's `re`: no lookaround, no backreferences, ASCII-only `\s`, `\w`
# and `\d`, and a narrower case fold. Every pattern here is written so that
# each of those differences can only widen the match, never narrow it — the
# whole value of the prefilter is that it never excludes a document the walk
# would change, and the pin for that is `tests/storage/test_workspace.py`'s
# comparison of the walk over every payload against the walk over the
# prefiltered ones.
#
# The one assumption every alternative shares: a JSON writer spells a printable
# ASCII character other than `"`, `\` and `/` as itself. JSON permits `\u003a`
# for a colon, but no serializer whose output is read here writes one, so a
# rule's ASCII characters appear in the text exactly as they appear in the
# decoded string. This holds as long as fact files come from a JSON serializer
# rather than from a hand that chose to escape ASCII.
#
# `_USERINFO` in JSON text: the scheme is dropped (it only narrows), `/` may be
# spelled `\/`, and the class also refuses `@` — it stops at the FIRST one, so
# it matches wherever the last-`@` rule would change the text — a `\t` or `\n` escape
# in the text is two printable characters, which the class admits though the
# decoded whitespace would not, and that is the widening direction.
_USERINFO_IN_JSON_TEXT = r":\\?/\\?/[^/?#\s@]*@"
# The characters a NORMALIZED key token is made of — `_KEY_TOKEN`'s set with
# the two separators `normalize_key` strips taken out and lowercased. A key
# pattern using any other character cannot be a substring of a normalized
# token, so the paired rule can never fire on it and it contributes nothing.
_NORMALIZED_TOKEN_CHARACTERS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789.")
# Under Python's case-insensitive matching three ASCII letters also match a
# non-ASCII letter that folds to them (Unicode simple case folding: the dotted
# and dotless `I`, the long `s`, the Kelvin sign). RE2 folds only two of the
# four, and a JSON writer may spell any of them as a `\u` escape, so a
# case-insensitive literal lists every spelling itself. The raw letters are
# written as Python escapes so the code points are checkable by eye: the
# Kelvin sign once shipped here as the ASCII letter `K` it looks like, and a
# `(?i)kelvin-…` pattern then excluded `Kelvin-42`, which the walk masks.
_FOLDS_TO_ASCII = {
    "i": ("\u0130\u0131", r"\\u013[01]"),
    "k": ("\u212a", r"\\u212[aA]"),
    "s": ("\u017f", r"\\u017[fF]"),
}
# Characters a literal prefix stops at: JSON spells them with an escape (`"`,
# `\`, control characters), may spell them with one (`/`, and any non-ASCII
# character as `\uXXXX`; `<>&='` as `\u003c` and so on by an HTML-safe writer,
# which a third-party scanner named in `scanner_id` may be), so the decoded
# and the encoded text differ there and a literal that needs one is not a
# substring of the text. Every other printable ASCII character is assumed
# spelled as itself — the residual stated above.
_NOT_SPELLED_AS_ITSELF = frozenset("\"\\/<>&='")


def _re2_literal(text: str) -> str:
    """`text` as an RE2 pattern matching exactly itself. Word characters
    stand for themselves; every other ASCII character is escaped, which RE2
    reads as that character whether or not it needed escaping."""
    return "".join(ch if ch.isalnum() or ch == "_" else "\\" + ch for ch in text)


def _re2_case_insensitive_literal(text: str) -> str:
    """`text` as an RE2 pattern matching it under Python's case-insensitive
    rule — both cases of each letter and, for the three letters a non-ASCII
    letter folds onto, that letter in both of its JSON spellings."""
    parts = []
    for ch in text:
        if not ch.isalpha():
            parts.append(_re2_literal(ch))
            continue
        folded, escaped = _FOLDS_TO_ASCII.get(ch.lower(), ("", ""))
        letters = f"[{ch.lower()}{ch.upper()}{folded}]"
        parts.append(f"(?:{letters}|{escaped})" if escaped else letters)
    return "".join(parts)


def _has_top_level_alternation(body: str) -> bool:
    """Whether `body` (a Python regular expression with its leading flags
    removed) is `A|B` at its outermost level. Such a pattern has no single
    literal prefix: a match may start with B's first character."""
    depth = 0
    in_class = False
    index = 0
    while index < len(body):
        ch = body[index]
        if ch == "\\":
            index += 2
            continue
        if in_class:
            in_class = ch != "]"
        elif ch == "[":
            in_class = True
            # `[]...]` and `[^]...]`: a `]` first in the class is a member.
            following = index + 1
            if following < len(body) and body[following] == "^":
                following += 1
            if following < len(body) and body[following] == "]":
                index = following
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "|" and depth == 0:
            return True
        index += 1
    return False


def _literal_prefix(pattern: str) -> tuple[str, bool] | None:
    """The characters every match of `pattern` (a Python regular expression)
    begins with, and whether they match case-insensitively — or None when
    the pattern has no such prefix, in which case nothing short of running
    the pattern says whether a text matches it.

    Deliberately conservative: it reads a pattern's leading literal
    characters and stops at the first thing that is not one — a class, a
    group, an anchor, an alternation, a quantifier (which makes the character
    before it optional, so that character is dropped too) — and at the first
    character JSON may not spell as itself. Every stop shortens the prefix,
    and a shorter prefix matches more, which is the safe direction. Only the
    `x` (verbose) flag, under which whitespace and `#` are not literals, gives
    up entirely.
    """
    flags = ""
    body = pattern
    if body.startswith("(?"):
        close = body.find(")")
        candidate = body[2:close] if close > 0 else ""
        if not candidate or any(ch not in "aiLmsu" for ch in candidate):
            # `(?x)` at the front, or a group where a literal would have to be.
            return None
        flags, body = candidate, body[close + 1 :]
    if _has_top_level_alternation(body):
        return None
    prefix: list[str] = []
    index = 0
    while index < len(body):
        ch = body[index]
        if ch == "\\":
            following = body[index + 1] if index + 1 < len(body) else ""
            # `\d`, `\A`, `\1`, `\_`: a class, an anchor or a backreference —
            # not a literal. Anything else after a backslash is that character.
            if not following or following.isalnum() or following == "_" or not following.isascii():
                break
            literal = following
            index += 2
        elif ch in ".[(|^$)":
            break
        elif ch in "*?{":
            if prefix:
                prefix.pop()
            break
        elif ch == "+":
            break
        else:
            literal = ch
            index += 1
        if literal in _NOT_SPELLED_AS_ITSELF or not literal.isascii() or not literal.isprintable():
            break
        prefix.append(literal)
    if not prefix:
        return None
    return "".join(prefix), "i" in flags


class RedactionError(ValueError):
    """A redaction rule that cannot be honoured as written."""


def _string_literal(node: object) -> str | None:
    """One ARGUMENT-GRAMMAR entry's own string literal, or None for anything
    else. The grammar is `{"kind": "string", "value": "..."}` — the shape
    `call_sites.arguments`, `return_flows.value` and `method_returns.value`
    carry, and the shape a `call_site` fact's payload nests under
    `arguments`."""
    if (
        isinstance(node, dict)
        and node.get("kind") == "string"
        and isinstance(node.get("value"), str)
    ):
        return str(node["value"])
    return None


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

    def union(self, other: "Redactor") -> "Redactor":
        """Every rule either set holds: what masks anything either side wanted hidden, for
        an exit that prints rows masked under two rule sets (the diff, spec 2026-10-22
        §3d). Both are already validated, so nothing is refused here."""
        return Redactor(
            tuple(sorted({*self._key_patterns, *other._key_patterns})),
            tuple(sorted({*self._value_patterns, *other._value_patterns})),
        )

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
        patterns.

        **Substring matching over-masks, deliberately** (2K Task 1 review,
        ruled): `aws.secretsmanager.endpoint` carries `secret` and therefore
        masks, though the value is a hostname. The two failure directions are
        not symmetric — under-masking leaks a credential, over-masking hides a
        hostname from a document that still says the key is present (a masked
        value counts as present, so NFR-7 survives) — so the loose side is the
        safe side. The day it costs a real workflow something, the fix is a
        MORE PRECISE built-in pattern, never a reveal or exclude mechanism:
        this file has no mechanism that narrows, by construction.
        """
        if self.masks_key(key):
            return REDACTED
        return self.redact_text(value)

    def masks_key(self, key: str) -> bool:
        """Whether `key` names a secret — the test `redact_value` masks a value WHOLE by,
        here for an exit that holds a value and the keys it was read through rather than
        one key (`resolve/resolved_schedules.py::redact_schedule_value`)."""
        normalized = normalize_key(key)
        return any(pattern in normalized for pattern in self._key_patterns)

    def redact_json(self, text: str) -> str:
        """A JSON document with every STRING LEAF passed through
        `redact_text` — userinfo stripping and the value patterns — **plus the
        one paired case where a literal NAMES the literal beside it.**

        A call argument is not a configuration key, and applying the key rule
        to every string here would mask the path and URL literals that ARE the
        wire identities the linking tier matches services on (2K Task 1 review,
        ruled). That ruling stands and this does not disturb it: no string is
        masked for what it contains.

        What the ruling did not cover is a NAME/VALUE PAIR, which is how a
        credential actually reaches this grammar — `.header("Authorization",
        "Bearer …")`, `.queryParam("api_key", …)`. W29 established that such a
        header carries a credential and masks it into `endpoint_metadata` by
        exactly this rule; the same bytes then shipped verbatim in
        `call_sites.arguments` and in the `call_site` fact's payload, in the
        same bundle, so the mask accomplished nothing. Measured on the
        `orders-service` fixture before this existed: `Bearer
        sk-live-fixture-secret` in two `graph/*.parquet` files in the clear.

        So a string literal that IS a credential name — the token shape
        `_KEY_TOKEN` requires, matched against the effective key set — masks
        the literals of the argument that FOLLOWS it. Position is the only
        evidence available: the grammar records an argument list, not a map,
        and `.header(name, value)` is where the pairing lives.

        **The boundary is the grammar.** Only `{"kind": "string"}` entries pair
        and only within one list, so `annotations.args` — plain JSON with no
        such entries — is untouched, and two adjacent bare strings are not
        read as a pair. A credential passed as anything but a literal beside
        its literal name is not reached here.

        Walks the parsed document rather than the raw text so the result is
        always valid JSON. Object KEYS are left alone: they are a schema, not
        a value.

        A document no rule touches is returned **as given**, character for
        character — the same promise `redact_text` makes, and it has to be
        kept here too: re-serializing an untouched document would rewrite
        whitespace and escaping the caller never asked to change, and every
        exported byte would move for nothing.
        """
        parsed = json.loads(text)
        masked = self._masked(parsed)
        if masked == parsed:
            return text
        return json.dumps(masked, ensure_ascii=False)

    def _masked(self, node: object) -> object:
        """`redact_json`'s walk: `redact_text` over every string leaf, and the
        paired rule over every list."""
        if isinstance(node, list):
            masked: list[object] = []
            names_the_next = False
            for index, item in enumerate(node):
                if names_the_next:
                    names_the_next = False
                    masked.append(self._masked_whole(item))
                    continue
                literal = _string_literal(item)
                names_the_next = (
                    literal is not None and self._names_a_secret(literal) and index + 1 < len(node)
                )
                masked.append(self._masked(item))
            return masked
        if isinstance(node, dict):
            return {key: self._masked(value) for key, value in node.items()}
        if isinstance(node, str):
            return self.redact_text(node)
        return node

    def _masked_whole(self, node: object) -> object:
        """One argument with every string literal in it replaced by the
        marker, and its structure left exactly as it was.

        Only the `value` of a `{"kind": "string"}` entry is replaced, never the
        `kind` beside it — a walk that masked every string leaf would rewrite
        the grammar's own discriminators and produce an argument list nothing
        could read. The nesting is real: a varargs header value arrives as
        `{"kind": "array", "elements": [...]}`, which is where the fixture's
        `Bearer` token sits.
        """
        if isinstance(node, dict):
            if _string_literal(node) is not None:
                return {key: REDACTED if key == "value" else value for key, value in node.items()}
            return {key: self._masked_whole(value) for key, value in node.items()}
        if isinstance(node, list):
            return [self._masked_whole(item) for item in node]
        if isinstance(node, str):
            return self.redact_text(node)
        return node

    def _names_a_secret(self, text: str) -> bool:
        """Whether one string literal is a credential's NAME.

        Two tests, and the token shape is the load-bearing one. `redact_value`
        matches its key set as a substring, which is right where every input is
        already a key; these inputs are arbitrary strings read out of bytecode,
        where a substring match also fires on prose and SQL that merely mention
        a credential — and the argument after "Changed password for User: {}"
        is a username, not a secret. `_KEY_TOKEN` says the string is a name
        rather than a sentence.
        """
        if _KEY_TOKEN.match(text) is None:
            return False
        normalized = normalize_key(text)
        return any(pattern in normalized for pattern in self._key_patterns)

    def json_text_prefilter(self) -> str | None:
        """A regular expression, in the RE2 dialect, that matches the text of
        EVERY JSON document `redact_json` would change — and some it would
        not. Or None, when a value pattern has no literal prefix (see
        `_literal_prefix`) and so no text can be ruled out without running it.

        For a caller holding tens of thousands of documents in a store whose
        query engine runs RE2, this is the test to apply BEFORE handing each
        one to `redact_json`: a document this does not match has no string any
        rule can act on, so walking it would return it unchanged. Measured on
        the `mall-admin` example, 75,296 distinct fact payloads become the few
        hundred that contain something a rule could touch.

        Three rules, one alternative each — `_USERINFO_IN_JSON_TEXT` for the
        userinfo strip; for every key pattern that could name a secret, its
        characters in either case with `-` and `_` allowed between them, which
        is `normalize_key` run backwards over a `_KEY_TOKEN` literal; and for
        every value pattern its literal prefix, spelled case-insensitively
        when the pattern is. The paired rule's other conditions (the token
        shape, an argument following) and a value pattern's remainder are not
        restated: leaving a condition out widens the match, and this only has
        to be wide enough.

        It restates no rule's DECISION — the walk still decides, on every
        document this admits — which is what keeps this a filter rather than
        a second copy of the rules: a document that reaches the walk is
        masked exactly as it would have been without the filter. The pin is
        the equality of the two, walked over the whole fact set of a fixture.
        """
        alternatives = [_USERINFO_IN_JSON_TEXT]
        for pattern in self._key_patterns:
            if set(pattern) <= _NORMALIZED_TOKEN_CHARACTERS:
                spelled = "[-_]*".join(_re2_literal(ch) for ch in pattern)
                alternatives.append(f"(?i:{spelled})")
        for pattern in self._value_patterns:
            found = _literal_prefix(pattern)
            if found is None:
                return None
            prefix, case_insensitive = found
            alternatives.append(
                _re2_case_insensitive_literal(prefix) if case_insensitive else _re2_literal(prefix)
            )
        return "|".join(alternatives)

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

    def redact_candidates(self, candidates: list[dict[str, object]]) -> list[dict[str, object]]:
        """An open question's `candidates` on their way out, one rule per column that can
        carry a value from the module rather than a name from its code: a `peer` (the
        `self_exchange` question's called side) through `redact_text`, as the endpoint's own
        peer column is, and the per-environment
        `values` of a `key` (`environment_divergence`) through `redact_value` under that key.
        The document, the enrichment brief and the bundle all print these, and before
        2026-10-23 all three printed them verbatim. Every other field — a symbol, a class, a
        format, a binder — is a name read out of code and passes through unchanged."""
        masked: list[dict[str, object]] = []
        for candidate in candidates:
            out = dict(candidate)
            if isinstance(out.get("peer"), str):
                out["peer"] = self.redact_text(str(out["peer"]))
            values = out.get("values")
            if isinstance(out.get("key"), str) and isinstance(values, dict):
                key = str(out["key"])
                out["values"] = {
                    env: self.redact_value(key, value) if isinstance(value, str) else value
                    for env, value in values.items()
                }
            masked.append(out)
        return masked
