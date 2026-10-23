"""Where a link's two ends exist (spec 2026-10-22-conditional-beans §3): `_with_conditions`
picks each end's bean from the federated `endpoint_conditions` rows by direction and states
the verdict `bean_presence` gives — never the per-condition rows, which read two exclusive
factories as a bean that exists nowhere."""

from sextant.api import _with_conditions
from sextant.application.stitch.links import Link

CALLER = "s maven c 1 com/acme/Client#call()."
LINK = Link(
    from_participant="orders",
    from_protocol="http",
    from_method="GET",
    from_path="/balances",
    from_caller=CALLER,
    to_participant="billing",
    to_protocol="http",
    to_method="GET",
    to_path="/balances",
)


def _row(participant: str, direction: str, bean: str, environment: str, holds: str, **extra):
    return {
        "participant": participant,
        "direction": direction,
        "method": "GET",
        "path": "/balances",
        "caller": extra.get("caller"),
        "bean": bean,
        "environment": environment,
        "holds": holds,
    }


def _presence(participant: str, bean: str, **verdicts: str):
    return [
        {"participant": participant, "bean": bean, "environment": e, "holds": h}
        for e, h in verdicts.items()
    ]


def test_each_end_states_its_own_beans_presence_by_direction():
    """The same participant could appear at both ends of a path; the inbound row never
    stands in for the outbound one."""
    conditions = [
        _row("billing", "inbound", "Ctl#", "prod", "true"),
        _row("orders", "outbound", "Client#", "prod", "true", caller=CALLER),
        _row("orders", "inbound", "Other#", "prod", "true"),
    ]
    presence = [
        *_presence("billing", "Ctl#", default="false", prod="true"),
        *_presence("orders", "Client#", default="true", prod="false"),
        *_presence("orders", "Other#", default="false", prod="false"),
    ]
    [link] = _with_conditions((LINK,), conditions, presence)
    assert link.to_conditions == (("default", "false"), ("prod", "true"))
    assert link.from_conditions == (("default", "true"), ("prod", "false"))


def test_a_beans_exclusive_factories_are_read_from_its_presence_not_its_conditions():
    """Two factories each hold in one environment; the per-condition rows hold AND fail in
    each. The presence verdict says the bean exists in both."""
    conditions = [
        _row("orders", "outbound", "Client#", "prod", "true", caller=CALLER),
        _row("orders", "outbound", "Client#", "prod", "false", caller=CALLER),
        _row("orders", "outbound", "Client#", "staging", "true", caller=CALLER),
        _row("orders", "outbound", "Client#", "staging", "false", caller=CALLER),
    ]
    presence = _presence("orders", "Client#", default="false", prod="true", staging="true")
    [link] = _with_conditions((LINK,), conditions, presence)
    assert link.from_conditions == (("default", "false"), ("prod", "true"), ("staging", "true"))


def test_a_link_between_unconditional_ends_carries_nothing():
    [link] = _with_conditions((LINK,), [], [])
    assert link.to_conditions == () and link.from_conditions == ()
