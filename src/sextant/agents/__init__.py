"""The `agents` outer group (2K design §8): a new sibling of `ingress`,
`storage`, and `egress` in the layering `cli -> ingress | storage | egress |
agents -> application -> domain`. It imports `application`/`domain` inward
like any outer group, and nothing else outward — never `ingress`,
`storage`, or `egress`.

`tradewind.py` is the one place in Sextant permitted to import the
`tradewind` package (import-confined, enforced by `tests/architecture/
test_agents_confinement.py`) — DR-2's amendment names it the one sanctioned
model call in the codebase; the deterministic pipeline never reaches this
package. `claude-api`/`anthropic` are gone entirely (2N design §1, a user
ruling: removed, not deprecated) — `anthropic` is importable NOWHERE in
Sextant now, even transitively through this module's own imports.

`AGENT_REGISTRY` lives here, not in `application/ports/enrichment.py`
(fix round 1, Important 5 — the port cannot import an adapter; see that
module's own docstring for why). This is the intra-package import layering
forbids `application` from making: `agents/__init__.py` importing its own
sibling `agents/tradewind.py` is ordinary same-package wiring, so the
name -> constructor mapping can live where it is actually usable.

**The registry's own value is a LAZY factory (2N design §1), unlike
`claude-api`'s eager one.** `import tradewind` (the vendor package) pulls in
all four of its own vendor SDK adapters (`langchain-anthropic`,
`claude-agent-sdk`, `openai-codex`, `cursor-sdk`) at import time — real cost
no non-enrich `sextant` invocation, and no enrich run that never actually
calls the agent (`--dry-run`, `--ingest`), should pay. `_tradewind_agent`
below defers `from sextant.agents.tradewind import TradewindAgent` to
inside the function body, so `import sextant.agents` alone (what every CLI
invocation does, to validate `--agent` against the known list) imports
neither `sextant.agents.tradewind` nor `tradewind` itself — only the first
actual CALL through the registry does."""

from collections.abc import Callable
from pathlib import Path
from typing import Literal

from sextant.application.ports.enrichment import EnrichmentAgent

# The CLI's own `--max-turns` default (2N design §1 fix round 1, M6):
# single-sited here rather than repeated as a literal at each of its three
# consumers — `_tradewind_agent`'s own keyword default below,
# `TradewindAgent.__init__`'s (imported lazily, but importing a constant
# from THIS module costs nothing extra, since `cli/app.py` already imports
# `sextant.agents` eagerly to reach `AGENT_REGISTRY`), and `cli/app.py`'s
# own fallback when neither `--max-turns` nor `.sextant.yml enrich:
# max_turns:` is given.
DEFAULT_MAX_TURNS = 20


def _tradewind_agent(
    *,
    auth: Literal["subscription", "api-key"],
    model: str,
    max_turns: int = DEFAULT_MAX_TURNS,
    session_store: Path | None = None,
) -> EnrichmentAgent:
    from sextant.agents.tradewind import TradewindAgent

    return TradewindAgent(auth=auth, model=model, max_turns=max_turns, session_store=session_store)


# The known `--agent` names, mapped to their constructor (spec §3: "unknown
# name refused with the known list"). `cli/app.py` (2K Task 7, the
# composition root) is the one caller expected to use this — it validates
# the requested name against these keys and calls the constructor with
# whatever `--model`/`--max-turns`/`--auth` flags it collected, plus the
# `session_store` its own `.sextant.yml enrich:` reading resolved (2N design
# §1 fix round 1, M3) — every value `TradewindAgent.__init__` accepts, since
# this registry has exactly one entry and `cli/app.py`'s one call site always
# passes all four kwargs by name.
#
# `Callable[..., EnrichmentAgent]`, not `type[EnrichmentAgent]` (fix round
# 1 micro-round 2, Important 1): under mypy strict, `type[Protocol]` only
# exposes `object.__init__` on the value — a real constructor call like
# `AGENT_REGISTRY["tradewind"](auth=..., model=..., max_turns=...,
# session_store=...)` (2K Task 7's own dispatch) fails to type-check against
# it, even though `_tradewind_agent` itself is a perfectly ordinary callable
# that returns one.
AGENT_REGISTRY: dict[str, Callable[..., EnrichmentAgent]] = {"tradewind": _tradewind_agent}
