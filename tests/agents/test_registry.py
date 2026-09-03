"""`AGENT_REGISTRY` (2K design §3, fix round 1 Important 5 ruling): moved
from `application/ports/enrichment.py` to `sextant.agents` itself — the
port layer cannot import an adapter, but `agents/__init__.py` importing its
own sibling `agents/tradewind.py` is ordinary intra-package wiring.

2N design §1: the registry's one entry is now a LAZY factory — `sys.modules`
must never carry `sextant.agents.tradewind` (or `tradewind` itself) merely
from `import sextant.agents`, only once the factory is actually CALLED."""

import subprocess
import sys

from sextant.agents import AGENT_REGISTRY


def test_the_registry_names_exactly_tradewind():
    assert set(AGENT_REGISTRY) == {"tradewind"}


def test_the_registered_constructor_builds_a_working_agent():
    from sextant.agents.tradewind import TradewindAgent

    agent = AGENT_REGISTRY["tradewind"](auth="subscription", model="claude-test")
    assert isinstance(agent, TradewindAgent)


def test_importing_the_agents_package_alone_never_imports_tradewind():
    """The lazy-factory pin (2N design §1): `import sextant.agents` is what
    every CLI invocation does to validate `--agent` against the known list,
    and no non-enrich invocation — nor an enrich run that never actually
    calls the agent (`--dry-run`, `--ingest`) — should pay for importing
    `tradewind` and its four vendor SDK adapters just for that.

    Run in a FRESH interpreter, not this process's own `sys.modules`: other
    tests in this suite (`tests/agents/test_tradewind_loop.py`) legitimately
    import `sextant.agents.tradewind` directly, and this process's own
    import of `sextant.agents` above (to reach `AGENT_REGISTRY`) already
    happened before this test runs — checking `sys.modules` here would pass
    or fail depending on test ORDER rather than on what `import sextant.
    agents` alone actually does (GUIDELINES §10: no ordering dependencies).
    """
    check = (
        "import sys, sextant.agents; "
        "assert 'sextant.agents.tradewind' not in sys.modules; "
        "assert 'tradewind' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-c", check],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
