"""Belt-and-braces network guard (2K design §9, fix round 1 Important 4):
every test in this directory patches `ClaudeApiAgent._send`, the one seam
that reaches `anthropic`, so the suite never touches the network — but a
patch is only as good as the seam it targets staying named `_send`. If a
future rename ever left a test's patch a silent no-op, `_send`'s real body
would run and reach for `ANTHROPIC_API_KEY`; stripping it from every
test's environment, autouse, turns that failure mode into a loud
`EnrichmentAgentError` (missing key) instead of a real, billed API call."""

import pytest


@pytest.fixture(autouse=True)
def _no_real_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
