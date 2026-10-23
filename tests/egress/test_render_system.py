"""`render_system_document` on hand-built rows: what the reactor fixture cannot reach."""

import pytest

from sextant.application.stitch import Link, Refusal, Unmatched
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


FIVE = ("default", "h2", "hsqldb", "mysql", "postgres")


def _link_row(link: Link) -> str:
    document = render_system_document(
        participants=(),
        links=(link,),
        unmatched=(),
        uncalled_endpoints=(),
        route_refusals=(),
        environment="default",
        redactor=Redactor.from_rules(RedactionRules()),
    )
    return next(line for line in document.splitlines() if line.startswith("| `web`"))


def _link(**sides: tuple[tuple[str, str], ...]) -> Link:
    return Link(
        from_participant="web",
        from_protocol="http",
        from_method="GET",
        from_path="/owners",
        from_caller="C#c().",
        to_participant="owners",
        to_protocol="http",
        to_method="GET",
        to_path="/owners",
        **sides,
    )


def test_a_link_whose_endpoint_is_open_in_every_environment_says_so_in_each():
    """Spec 2026-10-23-deployment-set-conditions §3c: the system document reads the same
    verdicts as the module's. A deployment-set condition is `unresolved` in every environment,
    so the endpoint exists in none that is decided and the row names each one open."""
    row = _link_row(_link(to_conditions=tuple((e, "unresolved") for e in FIVE)))
    assert row.count("not evaluated in `default`, `h2`, `hsqldb`, `mysql`, `postgres`") == 1, row
    assert "exists in" not in row, row


def test_a_link_whose_endpoint_is_decided_only_in_its_own_environment_reads_decided_there():
    row = _link_row(
        _link(to_conditions=tuple((e, "true" if e == "h2" else "unresolved") for e in FIVE))
    )
    assert "exists in `h2`; not evaluated in `default`, `hsqldb`, `mysql`, `postgres`" in row, row


def test_a_call_from_a_bean_open_in_every_environment_is_not_called_anywhere_decided():
    row = _link_row(_link(from_conditions=tuple((e, "unresolved") for e in FIVE)))
    calling_side = row.split("`owners`")[0]
    assert "called" not in calling_side, row
    assert "— not evaluated in `default`, `h2`, `hsqldb`, `mysql`, `postgres`" in calling_side, row
