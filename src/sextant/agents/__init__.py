"""The `agents` outer group (2K design §8): a new sibling of `ingress`,
`storage`, and `egress` in the layering `cli -> ingress | storage | egress |
agents -> application -> domain`. It imports `application`/`domain` inward
like any outer group, and nothing else outward — never `ingress`,
`storage`, or `egress`.

`claude_api.py` is the one place in Sextant permitted to import the
`anthropic` SDK (import-confined, enforced by `tests/architecture/
test_agents_confinement.py`) — DR-2's amendment names it the one sanctioned
model call in the codebase; the deterministic pipeline never reaches this
package.

`AGENT_REGISTRY` lives here, not in `application/ports/enrichment.py`
(fix round 1, Important 5 — the port cannot import an adapter; see that
module's own docstring for why). This is the intra-package import layering
forbids `application` from making: `agents/__init__.py` importing its own
sibling `agents/claude_api.py` is ordinary same-package wiring, so the
name -> constructor mapping can live where it is actually usable. Adding a
second adapter (`claude-sdk`, `tradewind`) is genuinely a one-line addition
here plus the adapter's own file — the claim the previous shape made but
could not keep, now true: importing `sextant.agents` eagerly imports
`claude_api`, and so `anthropic`, which is accepted (2K Task 7's CLI needs
this registry built before it can validate `--agent` at all)."""

from sextant.agents.claude_api import ClaudeApiAgent
from sextant.application.ports.enrichment import EnrichmentAgent

# The known `--agent` names, mapped to their constructor (spec §3: "unknown
# name refused with the known list"). `cli/app.py` (2K Task 7, the
# composition root) is the one caller expected to use this — it validates
# the requested name against these keys and calls the constructor with
# whatever `--model`/`--max-turns` flags it collected.
AGENT_REGISTRY: dict[str, type[EnrichmentAgent]] = {"claude-api": ClaudeApiAgent}
