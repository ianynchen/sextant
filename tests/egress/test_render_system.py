"""`render_system_document` on hand-built rows: what the reactor fixture cannot reach."""

import pytest

from sextant.application.stitch import Refusal, Unmatched
from sextant.domain.redaction import REDACTED, RedactionRules, Redactor
from sextant.egress.render.system import render_system_document


@pytest.mark.pins("stitch.the-system-document-masks-gateway-REFUSALS")
def test_every_address_and_reason_the_system_document_prints_is_masked():
    """The system document is an exit (2026-10-23): a gateway route and its refusal reason
    are configuration read verbatim, and an unmatched call's path and reason are an
    endpoint's. The two-service reactor has no gateway, so its end-to-end test never prints
    a refusal."""
    redactor = Redactor.from_rules(RedactionRules(value_patterns=("tok-[a-z]+",)))
    document = render_system_document(
        participants=(),
        links=(),
        unmatched=(
            Unmatched(
                participant="orders-api",
                protocol="http",
                method="GET",
                path="https://svc:s3cret@payments/charges",
                caller="C#c().",
                reason="no participant serves https://svc:s3cret@payments/charges",
            ),
        ),
        uncalled_endpoints=(),
        route_refusals=(
            Refusal(
                participant="gateway",
                route="Path=/hooks/tok-abc",
                reason="the prefix /hooks/tok-abc composes with no route",
            ),
        ),
        environment="default",
        redactor=redactor,
    )
    assert "s3cret" not in document
    assert "tok-abc" not in document
    assert "`https://payments/charges`" in document
    assert f"`Path=/hooks/{REDACTED}`" in document
