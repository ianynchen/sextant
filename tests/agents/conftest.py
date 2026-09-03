"""Belt-and-braces network guard (2K design §9, fix round 1 Important 4):
every api-key-auth test in this directory injects a scripted fake transport
(`tests/agents/test_tradewind_loop.py`'s `backend_factories` seam) rather
than touching the network — but a fake is only as good as it actually being
the one Tradewind resolves. Stripping `ANTHROPIC_API_KEY` from every test's
environment, autouse, turns a fake that silently stopped taking effect into
a loud `EnrichmentAgentError` (missing key, `TradewindAgent.run`'s own
pre-client check) instead of a real, billed API call."""

import pytest


@pytest.fixture(autouse=True)
def _no_real_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
