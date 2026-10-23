"""The redactor (2K design §1). What these tests protect is one claim: a value
Sextant was trusted with locally does not leave in the clear, and everything
else leaves byte-identical. Both halves matter — a redactor that masked too
much would be turned off, and a redactor that reformats what it does not mask
would rewrite every document it touched."""

import json

import pytest

from sextant.domain.redaction import (
    BUILTIN_KEY_PATTERNS,
    REDACTED,
    RedactionError,
    RedactionRules,
    Redactor,
    _literal_prefix,
    peer_without_userinfo,
)


def _plain() -> Redactor:
    return Redactor.from_rules()


@pytest.mark.parametrize(
    "key",
    [
        "orders.db.password",
        "orders.client.secret",
        "orders.auth.token",
        "orders.aws.credential",
        "orders.api-key",
        "orders.api_key",
        "orders.apiKey",
        "orders.private-key",
        "http.authorization",
        "keystore.passphrase",
    ],
)
def test_a_key_naming_a_secret_masks_its_value_whole(key: str):
    """The key is the evidence, so nothing of the value survives: a partial
    mask of a credential is still a credential's shape, and the built-in set is
    what a module with no `.sextant.yml` at all is protected by."""
    assert _plain().redact_value(key, "hunter2") == REDACTED


def test_key_matching_ignores_case_and_separator_spelling():
    """Spring's own relaxed binding (`normalize_key`, shared with resolution):
    one written rule must cover every spelling of one key, or a repo escapes
    redaction by renaming `api-key` to `API_KEY`."""
    redactor = _plain()
    for spelling in ("orders.API_KEY", "orders.Api-Key", "ORDERS.apikey"):
        assert redactor.redact_value(spelling, "sk-live-1") == REDACTED


def test_a_key_naming_no_secret_leaves_its_value_untouched():
    """The negative half. `soap.billing.uri` is the fixture's own pin for this:
    an address masked by accident is an architecture document that lies about
    where a service points."""
    redactor = _plain()
    assert redactor.redact_value("soap.billing.uri", "http://billing.internal/ws") == (
        "http://billing.internal/ws"
    )
    assert redactor.redact_value("orders.audit.topic", "audit-events") == "audit-events"


def test_url_userinfo_is_stripped_wherever_a_value_is_an_address():
    """`scheme://user:pass@host` → `scheme://host`. The address is the answer a
    reader needs and the credential in front of it is not, so this strips
    rather than masking the value whole — unlike a key-pattern match, where the
    key already said the whole value is a secret."""
    redactor = _plain()
    assert redactor.redact_text("https://u:p@h/x") == "https://h/x"
    assert redactor.redact_value("billing.url", "https://svc:s3cret@billing.internal/v1") == (
        "https://billing.internal/v1"
    )


def test_userinfo_stripping_leaves_an_at_sign_that_is_not_userinfo():
    """An `@` in a path or a query string is part of the address, and a
    hostname with no scheme has no userinfo to find. Stripping either would
    corrupt a real endpoint."""
    redactor = _plain()
    assert redactor.redact_text("https://h/users/@me") == "https://h/users/@me"
    assert redactor.redact_text("https://h/x?to=a@b.com") == "https://h/x?to=a@b.com"
    assert redactor.redact_text("sqs.us-east-1.amazonaws.com") == "sqs.us-east-1.amazonaws.com"


@pytest.mark.parametrize(
    ("peer", "expected"),
    [
        # The shape `split_url` wrote before 2026-10-23: the scheme gone, the credential
        # kept, and nothing `redact_text`'s `scheme://` rule could see.
        ("svc:s3cret@billing.internal", "billing.internal"),
        ("svc:@billing.internal:8443", "billing.internal:8443"),
        # A token alone is a credential in an authority too — a peer is never a mailbox.
        ("ghp_tok@github.com", "github.com"),
        # A password carrying a raw `@`: the host follows the LAST one (RFC 3986 forbids
        # a raw `@` in a host).
        ("u:p@ss@billing", "billing"),
        ("svc:s3cret@[::1]:8080", "[::1]:8080"),
        ("u:p@billing?x=1", "billing?x=1"),
        # The whole address `peer_of` keeps: the scheme stays, the userinfo goes.
        ("https://svc:s3cret@billing/ws", "https://billing/ws"),
        ("//svc:s3cret@billing/ws", "//billing/ws"),
        ("https://u:p@ss@billing:9/x", "https://billing:9/x"),
    ],
)
def test_a_peer_loses_its_userinfo_in_every_shape_a_peer_takes(peer: str, expected: str):
    """The peer is the service a call reaches, and a credential is never part of WHICH
    service that is (`peer_without_userinfo`). `redact_peer` is the same rule at the exits,
    for a workspace analysed before the writers applied it."""
    assert peer_without_userinfo(peer) == expected
    assert _plain().redact_peer(peer) == expected


@pytest.mark.parametrize(
    "peer",
    [
        "billing.internal",
        "billing.internal:8443",
        "[::1]:80",
        "${billing.url}",
        "lb://customers-service",
        # An `@` after the authority is not userinfo.
        "https://billing/a@b",
        # Not an authority at all: `:XE` is no port, so nothing here is a password.
        "jdbc:oracle:thin:@localhost:1521:XE",
    ],
)
def test_a_peer_with_no_userinfo_is_returned_unchanged(peer: str):
    assert peer_without_userinfo(peer) == peer
    assert _plain().redact_peer(peer) == peer


@pytest.mark.parametrize(
    "text",
    [
        "jdbc:oracle:thin:@localhost:1521:XE",
        "mailto:support@acme.com",
        "sip:alice@atlanta.com",
        "svc:s3cret@billing.internal",
    ],
)
def test_text_that_is_not_known_to_be_a_peer_keeps_its_at_sign(text: str):
    """The peer rule is for a value KNOWN to be an authority, and nothing else takes it. A
    first version applied it to every string `redact_text` sees — config values, call
    arguments, constants, every fact payload — and read the Oracle SID form as a password
    and a `mailto:` as a user (found by review on 2026-10-23, before it shipped). Even the
    credential shape is left alone outside a peer: there, nothing says it is an authority."""
    assert _plain().redact_text(text) == text
    assert _plain().redact_value("spring.datasource.url", text) == text


@pytest.mark.pins("redaction.open-question-CANDIDATES-are-masked-at-every-exit")
def test_an_open_questions_candidates_mask_their_peer_and_their_config_values():
    """`self_exchange` names the called side's peer and `environment_divergence` each
    environment's value of one key — and the document, the enrichment brief and the bundle
    all printed both verbatim until 2026-10-23. Names read out of code pass unchanged."""
    redactor = Redactor.from_rules(RedactionRules(value_patterns=("tok-[a-z]+",)))
    masked = redactor.redact_candidates(
        [
            {"side": "called", "symbol": "BillingClient#charge", "peer": "svc:s3cret@billing"},
            {"side": "served", "symbol": "ChargeController#charge", "peer": None},
            {"key": "spring.data.rest.base-path", "values": {"default": "/api", "prod": "tok-x"}},
            {"key": "spring.datasource.password", "values": {"default": "hunter2"}},
        ]
    )
    assert masked == [
        {"side": "called", "symbol": "BillingClient#charge", "peer": "billing"},
        {"side": "served", "symbol": "ChargeController#charge", "peer": None},
        {"key": "spring.data.rest.base-path", "values": {"default": "/api", "prod": REDACTED}},
        {"key": "spring.datasource.password", "values": {"default": REDACTED}},
    ]


def test_a_placeholder_expression_passes_through_whole():
    """2I's ruling, restated as a rule: an endpoint column may carry a whole
    `${...}` expression, and an expression is a REFERENCE to a value, never the
    value. Masking it would delete the only thing the row says about where it
    points, and there is no secret inside it to protect."""
    assert _plain().redact_text("${soap.billing.uri}") == "${soap.billing.uri}"


def test_repo_rules_widen_the_key_set():
    """`.sextant.yml`'s own addition — the fixture's `dsn`. A key no built-in
    pattern reaches is what proves the section is read at all."""
    redactor = Redactor.from_rules(RedactionRules(key_patterns=("dsn",)))
    assert redactor.redact_value("orders.internal.dsn", "postgres://u:p@h/db") == REDACTED
    # Still nothing but a widening: the built-ins are unchanged beside it.
    assert redactor.redact_value("orders.db.password", "hunter2") == REDACTED
    assert redactor.redact_value("orders.audit.topic", "audit-events") == "audit-events"


def test_repo_rules_widen_the_value_set_and_mask_only_what_they_match():
    """A value regex masks the SPAN it matched, not the line: these run over
    free text too (a rendered line, a tool result), and replacing the whole
    text would delete the context the match was found in."""
    redactor = Redactor.from_rules(RedactionRules(value_patterns=(r"ACME_[A-Z0-9]{4}",)))
    assert redactor.redact_value("notes", "see ACME_A1B2 and ACME_C3D4") == (
        f"see {REDACTED} and {REDACTED}"
    )
    assert redactor.redact_value("notes", "see nothing") == "see nothing"


def test_a_repo_cannot_narrow_the_built_in_set():
    """The one guarantee D04 §1 makes about this file: configuration widens
    redaction, never narrows it. There is no argument to `from_rules` that
    removes a built-in, which is what makes the promise structural rather than
    merely unwritten."""
    redactor = Redactor.from_rules(RedactionRules(key_patterns=("dsn",)))
    assert redactor.redact_value("orders.db.password", "hunter2") == REDACTED


@pytest.mark.parametrize(
    "rules",
    [
        RedactionRules(key_patterns=("",)),
        RedactionRules(key_patterns=("-_",)),
        RedactionRules(value_patterns=("",)),
        RedactionRules(value_patterns=("(unclosed",)),
    ],
)
def test_an_unusable_rule_is_refused_loudly(rules: RedactionRules):
    """Sextant's own input written wrong, not evidence to skip (D04 §2a). An
    empty pattern would mask everything and an uncompilable one would mask
    nothing — and a rule silently dropped reads exactly like a module that
    never asked for it."""
    with pytest.raises(RedactionError):
        Redactor.from_rules(rules)


def test_the_rule_set_hash_ignores_the_order_and_the_spelling_of_the_rules():
    """The hash names a SET. Two repositories that asked for the same rules
    must produce the same `redaction_set_hash` in their manifests, however
    their files listed them — otherwise the field says which file was written,
    not which rules ran."""
    one = Redactor.from_rules(RedactionRules(key_patterns=("dsn", "internal-token")))
    other = Redactor.from_rules(RedactionRules(key_patterns=("INTERNAL_TOKEN", "dsn", "dsn")))
    assert one.rule_set_hash == other.rule_set_hash
    assert one.rule_set_hash.startswith("sha256:")


def test_the_rule_set_hash_changes_when_a_rule_changes():
    """The whole point of recording it: a bundle masked under one set is not a
    bundle masked under another, and the manifest has to be able to say so."""
    plain = _plain().rule_set_hash
    widened = Redactor.from_rules(RedactionRules(key_patterns=("dsn",))).rule_set_hash
    by_value = Redactor.from_rules(RedactionRules(value_patterns=("ACME_",))).rule_set_hash
    assert len({plain, widened, by_value}) == 3


def test_a_benign_key_containing_a_pattern_substring_masks_anyway():
    """Over-masking is the ACCEPTED side (2K Task 1 review, ruled).
    `aws.secretsmanager.endpoint` names a hostname and carries `secret`, so it
    masks. The two directions are not symmetric: under-masking leaks a
    credential and cannot be undone once a bundle has left, while over-masking
    hides a hostname from a document that still says the key is present — a
    masked value counts as present, so NFR-7 survives it.

    Pinned so the trade is a decision rather than an accident. The day it costs
    a real workflow something, the fix is a MORE PRECISE built-in pattern —
    never a reveal, exclude or unmask mechanism, of which this codebase has
    none by construction."""
    redactor = _plain()
    assert redactor.redact_value("aws.secretsmanager.endpoint", "vpce-1.eu-west-1.vpc") == REDACTED
    assert redactor.redact_value("orders.tokenizer.class", "com.acme.Tokenizer") == REDACTED


def test_redact_json_strips_userinfo_from_every_string_leaf():
    """The bundle's carried JSON columns (`call_sites.arguments`,
    `annotations.args`): a hardcoded `https://user:pass@host` literal lands in
    one whole, and stripping its userinfo removes the secret while leaving the
    host — which is the wire identity the linking tier matches services on."""
    redacted = _plain().redact_json(
        '[{"kind":"string","value":"https://svc:s3cret@billing.internal/v1","symbol":null}]'
    )
    assert json.loads(redacted) == [
        {"kind": "string", "value": "https://billing.internal/v1", "symbol": None}
    ]


def test_redact_json_never_applies_the_key_based_rule():
    """Ruled: an argument is not a configuration key. A JSON object key
    reading `password` is a field name in a fact schema, not a claim that the
    string beside it is a credential — masking on it would gut the bundle of
    the path and URL literals the linking tier needs."""
    text = '{"password":"/billing/invoices","token":"order-events"}'
    assert _plain().redact_json(text) == text


def test_redact_json_returns_an_untouched_document_character_for_character():
    """The same promise `redact_text` makes. Re-serializing a document nothing
    matched would rewrite whitespace and escaping the caller never asked to
    change — and at the export exit every one of those bytes would move for
    nothing (NFR-1)."""
    text = '[ {"kind": "string",  "value": "/billing/invoices"} ]'
    assert _plain().redact_json(text) == text


# `json_text_prefilter` and the literal-prefix reader under it. The claim that
# matters — the predicate admits every document the walk changes — is pinned
# where RE2 runs (`tests/storage/test_workspace.py`, over adversarial texts, and
# `tests/e2e/test_vertical_slice.py`, over a whole analysed fact set). What is
# pinned HERE is the reading of a pattern: which characters are taken as its
# literal prefix and which shape gives up, because a prefix read one character
# too long is a document excluded that the walk would have masked.


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("sk-live-[a-z0-9]+", ("sk-live-", False)),
        (r"AKIA[0-9A-Z]{16}", ("AKIA", False)),
        (r"(?i)bearer\s+\S+", ("bearer", True)),
        # `=` is one of the five an HTML-safe writer escapes, so it ends the prefix.
        (r"\.env=.*", (".env", False)),
        ("my_secret_[0-9]+", ("my_secret_", False)),
        # A quantifier makes the character before it optional: `c` is not required.
        ("abc?", ("ab", False)),
        ("abc*d", ("ab", False)),
        ("abc{0,3}", ("ab", False)),
        # A group after the prefix does not disturb it, even one with alternation.
        ("x(a|b)", ("x", False)),
        # Characters JSON may not spell as themselves end the prefix.
        ("ab/c", ("ab", False)),
        ('q"r', ("q", False)),
        ("ab\\\\c", ("ab", False)),
        ("abé", ("ab", False)),
    ],
)
def test_the_literal_prefix_of_a_value_pattern(pattern: str, expected: tuple[str, bool]):
    assert _literal_prefix(pattern) == expected


@pytest.mark.parametrize(
    "pattern",
    [
        # Nothing literal before the first thing that is not.
        "[0-9]{16}",
        "^xyz",
        r"\d+",
        "(abc)",
        ".*secret",
        # Alternation at the top: a match may begin with either branch.
        "a|b",
        r"a\|b|c",
        # Verbose mode: whitespace and `#` are not literals, so nothing is read.
        "(?x) a b",
        # A quantifier on the only character.
        "a?",
    ],
)
def test_a_value_pattern_with_no_literal_prefix_gives_up(pattern: str):
    assert _literal_prefix(pattern) is None


def test_the_prefilter_names_every_built_in_rule_and_nothing_a_repo_did_not_add():
    """One alternative per rule: the userinfo strip, and each built-in key
    pattern with `-` and `_` allowed between its characters — `normalize_key`
    run backwards, so `api_key`, `api-key` and `apiKey` all fall inside it."""
    prefilter = _plain().json_text_prefilter()
    assert prefilter is not None
    # Splitting on `|` reads the built-in set only: a value pattern's
    # case-insensitive prefix carries `(?:…|…)` groups of its own, which this
    # split would cut through. The built-ins have no value patterns.
    alternatives = prefilter.split("|")
    assert alternatives[0] == r":\\?/\\?/[^/?#\s@]*@"
    assert alternatives[1:] == [
        "(?i:" + "[-_]*".join(pattern) + ")" for pattern in BUILTIN_KEY_PATTERNS
    ]


def test_the_prefilter_gives_up_when_a_value_pattern_has_no_prefix():
    """A value pattern nothing short of running it can rule out means no
    document can be ruled out — the caller walks every one, as it did before
    the prefilter existed. Refusing is the safe answer; a predicate that
    ignored such a pattern would exclude documents that pattern masks."""
    redactor = Redactor.from_rules(RedactionRules(value_patterns=("[0-9]{16}", "sk-live-.*")))
    assert redactor.json_text_prefilter() is None


def test_a_key_pattern_no_argument_literal_could_carry_adds_nothing():
    """The paired rule reads only `_KEY_TOKEN`-shaped literals, so a key
    pattern with a character outside that shape can never fire there; it is
    still applied to configuration keys, which this predicate does not cover."""
    widened = Redactor.from_rules(RedactionRules(key_patterns=("dsn", "clé", "a/b")))
    prefilter = widened.json_text_prefilter()
    assert prefilter is not None
    assert "(?i:d[-_]*s[-_]*n)" in prefilter
    assert "clé" not in prefilter and "a[-_]*/" not in prefilter
