"""The `EnrichmentAgent` port (2K design §3): the one seam a model call is
allowed to cross into Sextant. DR-2's amendment names `enrich` the one
sanctioned caller — the deterministic pipeline (analyze/resolve/render/
export) never reaches this port — and NFR-1's amendment carves out exactly
one exception to byte-determinism: the model's own response. Everything
else here — `EnrichmentBrief`'s composition, `EnrichmentAnswers`' shape,
answer validation and overlay assembly downstream — stays deterministic.

`application` never imports an adapter. Layering runs `cli -> ingress |
storage | egress | agents -> application -> domain`: an outer group
(`agents` included) depends on `application`, never the reverse, so this
module cannot import `sextant.agents.claude_api` to build a name ->
implementation mapping — only the composition root (`cli/app.py`, wired in
2K Task 7) may import an adapter and construct it. The name -> constructor
registry therefore lives one layer out, at `sextant.agents.AGENT_REGISTRY`
(an intra-package import inside `agents`, legal the way any package's
`__init__` importing its own sibling module is) — this port stays a pure
contract, holding no registry of its own.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sextant.application.enrich.tools import ToolDefinition, ToolExecutor


@dataclass(frozen=True)
class EnrichmentBrief:
    """What an agent is handed for one run (2K design §3): the composed
    prompt (2K Task 7's `compose_brief`), the instructions document text
    (`enrich/INSTRUCTIONS.md`), the tool definitions an agent's runtime
    maps into its own protocol, and the jailed roots — carried here rather
    than looked up, since the "universal door" (`--dry-run`, an external
    agent) never touches a `ToolExecutor` at all."""

    prompt: str
    instructions: str
    tool_definitions: tuple[ToolDefinition, ...]
    jailed_roots: tuple[Path, ...]


@dataclass(frozen=True)
class EnrichmentAnswers:
    """A run's outcome: the model's final in-band text (raw JSON, 2K design
    §6 — validated by the caller, never parsed here) and the transcript of
    every tool call and result (`ToolExecutor.transcript`, persisted by the
    caller to `enrich-transcript.jsonl`). `partial` states whether `text`
    is a clean final answer or whatever existed when a turn cap or the
    no-progress guard ended the run early — never silent about which, and
    `partial_reason` says WHY: `"max_turns"`, `"no_progress"`, a truncated
    or otherwise non-`end_turn` finish as `"stop:<reason>"` (the model's own
    `stop_reason`, verbatim), or `None` for a clean answer — so a caller
    (2K Task 7) can persist an honest account of how a run ended rather
    than just the fact that it did."""

    text: str
    transcript: list[dict[str, object]]
    partial: bool = False
    partial_reason: str | None = None


class EnrichmentAgentError(RuntimeError):
    """A run that could not be completed — the loud, typed failure an API
    error surfaces as (2K design §3's loop steps: "API errors surface as a
    loud, typed failure — enrich reports, nothing written"). A caller (2K
    Task 7's stage) catches this specifically, reports it, and writes no
    overlay — it never wants to catch whatever exception an adapter's own
    SDK happens to raise, which would couple it to a provider `application`
    is not allowed to import."""


class EnrichmentAgent(Protocol):
    """Implementations are keyed by name in `sextant.agents.AGENT_REGISTRY`
    (this module cannot hold that registry itself — see the module
    docstring). `run` is the one method: drive the brief through whatever
    loop the adapter's runtime uses, but every tool call executes through
    `executor` — the foreign runtime maps our tools into its own protocol;
    our code serves the bytes (2K design §3)."""

    def run(self, brief: EnrichmentBrief, executor: ToolExecutor) -> EnrichmentAnswers: ...
