"""`AGENT_REGISTRY` (2K design §3, fix round 1 Important 5 ruling): moved
from `application/ports/enrichment.py` to `sextant.agents` itself — the
port layer cannot import an adapter, but `agents/__init__.py` importing its
own sibling `agents/claude_api.py` is ordinary intra-package wiring."""

from sextant.agents import AGENT_REGISTRY
from sextant.agents.claude_api import ClaudeApiAgent


def test_the_registry_maps_claude_api_to_its_constructor():
    assert AGENT_REGISTRY == {"claude-api": ClaudeApiAgent}


def test_the_registered_constructor_builds_a_working_agent():
    agent = AGENT_REGISTRY["claude-api"](model="claude-test")
    assert isinstance(agent, ClaudeApiAgent)
