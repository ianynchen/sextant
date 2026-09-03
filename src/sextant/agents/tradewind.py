"""`tradewind`: the Tradewind-backed `EnrichmentAgent` (2N design §1) — the
ONE adapter behind the port, replacing `claude-api` outright (the user
ruling: removed, not deprecated). Import-confined to this file, mirroring
`claude-api`'s own precedent (enforced by `tests/architecture/
test_agents_confinement.py`): the ONE module in Sextant permitted to import
`tradewind`. Every byte a model reads or writes still passes through
`ToolExecutor` (2K Task 5's jail) — this file maps OUR tool definitions and
results into Tradewind's `Tool`/`SessionOptions` shapes and back; it decides
nothing about what is visible, jailed, or redacted.

Pinned by commit sha via `[tool.uv.sources]` (`pyproject.toml`) — post-0.6.0,
no version tags exist. `examples/tradewind` is a read-only clone of the same
commit, kept for reading the library's own source when a behavior question
arises; it is not imported by anything here.

**One `Tradewind(config)`/session/run per call.** `run` builds a fresh
config and client, mints a caller-side session id (`uuid.uuid4()`), and
drives exactly one `session.run(...)` turn — Tradewind's tool handlers are
async (`handler(**arguments)`, invoked by `ToolHost._call_local`) while
`EnrichmentAgent.run` is sync, so `run` bridges the two with exactly ONE
`asyncio.run` wrapping the whole client/session/turn lifecycle.

**Auth selects the backend, never guessed.** `"subscription"` maps to
Tradewind's `claude` backend — the machine's own logged-in Claude Code
engine, which disables its built-in dev tools (`ClaudeAgentOptions.tools=[]`,
confirmed in `claude_backend.py`) so only the registered jailed tools exist
and the jail guarantee holds. `"api-key"` maps to the `langchain` backend,
reading `ANTHROPIC_API_KEY` from the environment HERE — Tradewind itself
never reads env — and refusing its absence before any client is built (the
2K precedent this adapter keeps: name the variable, fail before the network).

**The system prompt diverges by backend, honestly.** `SessionOptions.
system_prompt` carries `brief.instructions` on both, but the claude backend
APPENDS it to the Claude Code preset persona (`claude_backend.py`'s own
`_build_options`: `{"type": "preset", "preset": "claude_code", "append":
ctx.system_prompt}`) rather than replacing it — so the two auth modes run
materially different system prompts. This adapter does nothing to paper over
that; it is Tradewind's own behavior, stated here because it is the one
divergence a caller comparing the two modes needs to know about.

**The no-progress guard, without `session.stop()`.** Tradewind owns the tool
loop itself; the only seam this adapter controls is what a tool HANDLER
returns. `session.stop()` is never used — an interrupted turn synthesizes a
terminal event with no final text, which can never be the honest partial the
port promises, and a stop issued mid-handler would cancel before the model
ever read anything appended to that handler's own result. Instead, every
handler EXECUTES normally (so `ToolExecutor.transcript` records every call,
same as always) and `_NudgeGuard` tracks each `(name, canonical-json args)`
key across the whole run; the THIRD time one repeats, the nudge sentence is
appended to that call's real result, once, and the run simply continues.
Termination stays Tradewind's own `max_tool_rounds` — a model that keeps
repeating after the nudge burns rounds to the cap, same as one that never
repeats at all, and `_partial_reason` reports `"no_progress"` for that
specific ending rather than the less-specific `"max_turns"`.

**`end_reason` mapping, the whole of Tradewind's reachable vocabulary
through this adapter:**

* `"end_turn"` -> `partial=False`, `partial_reason=None` — a clean answer.
* `"max_tokens"` -> `partial=True`, `partial_reason="stop:max_tokens"` — the
  provider truncated the response; Tradewind's own backends distinguish no
  other abnormal-stop reason, unlike `claude-api`'s open `stop:<reason>`
  family talking to the Messages API directly.
* `"max_tool_rounds"` -> `partial=True`, `partial_reason` is `"no_progress"`
  when this run's guard ever fired, else the less-specific `"max_turns"`.
* `"interrupted"` is unreachable through this adapter's own usage (`stop()`
  is never called) — if Tradewind ever produces it anyway, that is a bug
  outside this adapter's contract, reported loudly as `EnrichmentAgentError`
  rather than silently folded into one of the three reasons above.

**The round cap is validated against the api-key backend's own ceiling.**
Tradewind's langchain backend hard-fails at 25 model iterations (`_MAX_
ITERATIONS` in `langchain_backend.py`) — a `max_tool_rounds` of N there
costs N+1 iterations (N tool-round calls, one final answer), so 25 is the
first value that can exhaust the ceiling instead of ending with an honest
`max_tool_rounds` completion. `__init__` refuses `max_turns > 24` for
`auth="api-key"` up front, naming the ceiling — never a silent late failure
through the general exception net below.

**The session store.** `auth="api-key"` persists Tradewind's session mirror
to `<module>/.tradewind/sessions.sqlite` (the module root — always
`brief.jailed_roots[0]`, the one layout `cli/app.py`'s composition root
ever builds this adapter against) — mkdir'd first, since `TradewindConfig`'s
own sqlite store does not create parent directories.  `auth="subscription"`
keeps Tradewind's ephemeral default (`store=None`): the Claude Code engine
already keeps its own native record, and a second copy adds nothing.
`session_store`, when given, overrides either default outright —
`Path(":memory:")` is the opt-out spelling (an in-memory sqlite store,
Tradewind's own precedent for "no persistence" when a concrete path is
still required somewhere in the call chain). `.tradewind/` joins the jail's
own exclusions (`application/enrich/tools.py`'s `DERIVED_OUTPUT_DIRS`) so a
model can never read its own prior conversation back — the identical
feedback loop the enrichment overlay's own exclusion (2K Task 3) closes.

**`history_scope` is never passed.** Sextant's own usage never spawns
subagents or forks, so Tradewind's `"tree"` scope has nothing to fold; an
enrichment session is single-turn, so even `"flat"` would read nothing back;
and Tradewind's per-backend default is already the honest answer for each
backend (`"flat"` on the mirror-rebuilding langchain backend, `"none"` on
the natively-resuming claude backend) — passing anything explicit here would
only risk `Unsupported` on the claude backend for no benefit on either.

**Testing seam.** `backend_factories`, forwarded verbatim to `Tradewind()`'s
own keyword-only constructor argument, is Tradewind's OWN public injection
seam (`client.py`'s docstring: "the front-door injection seam for an
embedder's no-network tests") — production code never passes it; the
suite uses it to swap in a `FakeMessagesListChatModel` behind the langchain
backend, never touching the network (2N design §1's testing note).
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import SecretStr
from tradewind import Tradewind, TradewindConfig
from tradewind.application.client import BackendFactory
from tradewind.domain.models import (
    ApiKeyAuth,
    BackendName,
    ModelSpec,
    Profile,
    SessionOptions,
    SubscriptionAuth,
    Tool,
    TurnResult,
)

from sextant.application.enrich.tools import ToolDefinition, ToolExecutor
from sextant.application.ports.enrichment import (
    EnrichmentAgentError,
    EnrichmentAnswers,
    EnrichmentBrief,
)

# `ANTHROPIC_API_KEY` only — never a constructor argument, a CLI flag, or a
# config value (2K design §3's precedent, kept here): read at the moment
# `run` needs it, so it never ends up copied into a transcript entry or an
# error message.
_API_KEY_ENV = "ANTHROPIC_API_KEY"

# The api-key (langchain) backend's own hard ceiling (`_MAX_ITERATIONS` in
# `tradewind/adapters/langchain_backend.py`) is 25 model iterations; a
# `max_tool_rounds` of N there costs N+1 iterations, so 24 is the highest
# value that can never reach it.
_API_KEY_MAX_TURNS_CEILING = 24

_TIER = "standard"
_STORE_DIRNAME = ".tradewind"
_STORE_FILENAME = "sessions.sqlite"

_AUTH_BACKEND: dict[str, BackendName] = {"subscription": "claude", "api-key": "langchain"}

# The no-progress guard's one message, appended to the THIRD identical
# call's own real result (2N design §1) — never a separate turn, since
# Tradewind owns the tool loop and this adapter's only seam is a handler's
# return value.
_NUDGE = (
    "\n\n[sextant] You have made this exact call three times. The result "
    "will not change; write your answers with what you have, or try a "
    "different call."
)


class _NudgeGuard:
    """Tracks every `(name, canonical-json args)` key this run's handlers
    have seen. `nudged` becomes `True` the moment any key is seen a third
    time — read by `_partial_reason` to tell `"no_progress"` apart from the
    less-specific `"max_turns"` once the run ends at the cap."""

    def __init__(self) -> None:
        self._counts: dict[tuple[str, str], int] = {}
        self.nudged = False

    def result_for(self, name: str, args: dict[str, object], result: str) -> str:
        # `default=repr` (claude-api's own precedent): this bookkeeping must
        # never be able to raise ahead of `ToolExecutor.execute`'s own
        # never-raises guarantee over an argument shape `json.dumps` cannot
        # serialize on its own.
        key = (name, json.dumps(args, sort_keys=True, default=repr))
        count = self._counts.get(key, 0) + 1
        self._counts[key] = count
        if count == 3:
            self.nudged = True
            return result + _NUDGE
        return result


class TradewindAgent:
    """`auth` selects the backend (module docstring); `model` is passed to
    Tradewind's `ModelSpec` verbatim — a bad name is the provider's own
    error, surfaced as `EnrichmentAgentError`. `max_turns` is Tradewind's
    `max_tool_rounds` (default 20, matching the CLI's own default); refused
    above 24 for `auth="api-key"` at construction (module docstring).
    `session_store` overrides the per-auth default store path outright.

    `backend_factories` (keyword-only) is a TEST-ONLY seam — Tradewind's own
    public injection point, forwarded verbatim (module docstring's "Testing
    seam"). Production code never passes it.
    """

    def __init__(
        self,
        auth: Literal["subscription", "api-key"],
        model: str,
        max_turns: int = 20,
        session_store: Path | None = None,
        *,
        backend_factories: dict[BackendName, BackendFactory] | None = None,
    ) -> None:
        if auth == "api-key" and max_turns > _API_KEY_MAX_TURNS_CEILING:
            raise ValueError(
                f"--max-turns {max_turns} exceeds the api-key backend's own ceiling of "
                f"{_API_KEY_MAX_TURNS_CEILING} model iterations"
            )
        self._auth = auth
        self._model = model
        self._max_turns = max_turns
        self._session_store = session_store
        self._backend_factories = backend_factories

    def run(self, brief: EnrichmentBrief, executor: ToolExecutor) -> EnrichmentAnswers:
        try:
            return asyncio.run(self._run_async(brief, executor))
        except EnrichmentAgentError:
            raise
        except Exception as failure:  # every Tradewind/SDK failure, wrapped
            raise EnrichmentAgentError(f"tradewind run failed: {failure}") from failure

    async def _run_async(self, brief: EnrichmentBrief, executor: ToolExecutor) -> EnrichmentAnswers:
        config = self._config(brief.jailed_roots)
        guard = _NudgeGuard()
        tools = [_tool(definition, executor, guard) for definition in brief.tool_definitions]
        client = Tradewind(config, backend_factories=self._backend_factories)
        try:
            session = await client.ensure(
                str(uuid.uuid4()),
                SessionOptions(system_prompt=brief.instructions, tools=tools),
            )
            result = await session.run(brief.prompt, max_tool_rounds=self._max_turns)
        finally:
            await client.aclose()
        return _answers(result, executor, guard)

    def _config(self, jailed_roots: tuple[Path, ...]) -> TradewindConfig:
        backend = _AUTH_BACKEND[self._auth]
        auth = (
            ApiKeyAuth(api_key=SecretStr(_require_api_key()))
            if self._auth == "api-key"
            else SubscriptionAuth()
        )
        profile = Profile(backend=backend, auth=auth, models={_TIER: ModelSpec(model=self._model)})
        return TradewindConfig(
            profiles={"default": profile},
            default_profile="default",
            store=self._store_path(jailed_roots),
        )

    def _store_path(self, jailed_roots: tuple[Path, ...]) -> Path | None:
        if self._session_store is not None:
            path = self._session_store
        elif self._auth == "api-key":
            module_root = jailed_roots[0]
            path = module_root / _STORE_DIRNAME / _STORE_FILENAME
        else:
            return None
        # `TradewindConfig.store`'s sqlite engine does not create parent
        # directories (module docstring) — a no-op for `Path(":memory:")`,
        # whose parent (`.`) already exists.
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


def _require_api_key() -> str:
    key = os.environ.get(_API_KEY_ENV)
    if not key:
        raise EnrichmentAgentError(
            f"{_API_KEY_ENV} is not set — tradewind's api-key auth needs it to authenticate"
        )
    return key


def _tool(definition: ToolDefinition, executor: ToolExecutor, guard: _NudgeGuard) -> Tool:
    """One `ToolDefinition` as a Tradewind `Tool`: the handler wraps
    `executor.execute` (the jail, unchanged) and the no-progress guard
    (module docstring). Tradewind's `ToolHost._call_local` invokes this as
    `handler(**arguments)` — `**arguments` collects the call's own JSON
    object back into a plain `dict`, exactly the shape `ToolExecutor.execute`
    expects."""

    async def handler(**arguments: object) -> str:
        result = executor.execute(definition.name, arguments)
        nudged = guard.result_for(definition.name, arguments, result)
        if nudged != result:
            # `executor.execute` already appended this call's own entry to
            # `executor.transcript` (the record Sextant persists) using the
            # UN-nudged result — rewritten here so the persisted transcript
            # shows exactly what the model was handed, not a stale copy
            # (module docstring: "the nudge sentence, appended to that
            # call's real result"). Safe without a lock: Tradewind's own
            # tool loop awaits one call at a time, so `transcript[-1]` is
            # still this call's entry when this line runs.
            executor.transcript[-1]["result"] = nudged
        return nudged

    return Tool(
        name=definition.name,
        description=definition.description,
        input_schema=definition.schema,
        handler=handler,
    )


def _partial_reason(result: TurnResult, guard: _NudgeGuard) -> tuple[bool, str | None]:
    if result.end_reason == "end_turn":
        return False, None
    if result.end_reason == "max_tokens":
        return True, "stop:max_tokens"
    if result.end_reason == "max_tool_rounds":
        return True, ("no_progress" if guard.nudged else "max_turns")
    # "interrupted" — unreachable through this adapter's own usage, since
    # `session.stop()` is never called (module docstring). Fails loud rather
    # than silently mapping an end_reason this adapter's contract does not
    # cover into one of the three above.
    raise EnrichmentAgentError(
        f"tradewind ended the run with an unexpected end_reason {result.end_reason!r} "
        "(this adapter never calls session.stop())"
    )


def _answers(result: TurnResult, executor: ToolExecutor, guard: _NudgeGuard) -> EnrichmentAnswers:
    partial, reason = _partial_reason(result, guard)
    return EnrichmentAnswers(
        text=result.final_text or "",
        transcript=list(executor.transcript),
        partial=partial,
        partial_reason=reason,
    )


if TYPE_CHECKING:
    # A typed-assignment pin (claude-api's own precedent), checked by
    # `mypy src` and erased at runtime: proves `TradewindAgent` structurally
    # satisfies `EnrichmentAgent` so a future signature drift on either side
    # is a type error here, not a surprise at whatever call site first
    # assigns one to the other.
    from sextant.application.ports.enrichment import EnrichmentAgent

    _typed_pin: EnrichmentAgent = TradewindAgent(auth="subscription", model="pin")
