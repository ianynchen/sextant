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
2K Task 7) may import an adapter and construct it. `AGENT_REGISTRY` below
is the one piece of that knowledge `application` is allowed to hold: the
closed set of valid `--agent` names (spec §3: "unknown name refused with
the known list"), so the CLI's validation and any test pin against one
constant rather than a hand-copied literal.
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
    no-progress guard ended the run early — never silent about which."""

    text: str
    transcript: list[dict[str, object]]
    partial: bool = False


class EnrichmentAgentError(RuntimeError):
    """A run that could not be completed — the loud, typed failure an API
    error surfaces as (2K design §3's loop steps: "API errors surface as a
    loud, typed failure — enrich reports, nothing written"). A caller (2K
    Task 7's stage) catches this specifically, reports it, and writes no
    overlay — it never wants to catch whatever exception an adapter's own
    SDK happens to raise, which would couple it to a provider `application`
    is not allowed to import."""


class EnrichmentAgent(Protocol):
    """Implementations are keyed by name in `AGENT_REGISTRY`, never
    imported here. `run` is the one method: drive the brief through
    whatever loop the adapter's runtime uses, but every tool call executes
    through `executor` — the foreign runtime maps our tools into its own
    protocol; our code serves the bytes (2K design §3)."""

    def run(self, brief: EnrichmentBrief, executor: ToolExecutor) -> EnrichmentAnswers: ...


# The known `--agent` names (2K design §3). Extending this to a second
# adapter (`claude-sdk`, `tradewind`) is a one-line addition here plus the
# adapter's own file — no other change, which is the point of a registry
# keyed by name rather than a chain of CLI conditionals.
AGENT_REGISTRY: tuple[str, ...] = ("claude-api",)
