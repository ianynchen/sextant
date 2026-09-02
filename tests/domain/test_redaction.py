"""The redactor (2K design §1). What these tests protect is one claim: a value
Sextant was trusted with locally does not leave in the clear, and everything
else leaves byte-identical. Both halves matter — a redactor that masked too
much would be turned off, and a redactor that reformats what it does not mask
would rewrite every document it touched."""

import pytest

from sextant.domain.redaction import REDACTED, RedactionError, RedactionRules, Redactor


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
