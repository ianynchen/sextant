"""`claude-api`: the Messages-API tool-use loop (2K design §3) — the one
adapter behind `EnrichmentAgent` shipping in v1, and the ONE module in
Sextant with permission to import `anthropic` (import-confined, mirroring
the `google.protobuf` pattern of `tests/architecture/
test_protobuf_confinement.py`; enforced here by `tests/architecture/
test_agents_confinement.py`). Every byte a model reads or writes still
passes through `ToolExecutor` (2K Task 5's jail): this file maps OUR tool
definitions and results into the SDK's request/response shapes and back —
it decides nothing about what is visible, jailed, or redacted.

DR-2's amendment (2K design §8) names this the one sanctioned model call in
Sextant — analyze/resolve/render/export never reach it. It is also NFR-1's
one stated exception: the model's own response is not byte-reproducible run
to run, but everything this loop hands back — the transcript
(`ToolExecutor.transcript`, untouched by this file) and the answer text
(the FINAL response's text block, verbatim, never an earlier turn's stale
commentary — see `run`) — is exactly what downstream validation and
assembly (2K Task 3/7) already treat deterministically.

`_send` is the ONLY method that touches the `anthropic` SDK — the single
seam `tests/agents/test_claude_api_loop.py` overrides with a scripted fake
transport, so the suite never makes a network call (2K design §9); the
suite's `tests/agents/conftest.py` also strips `ANTHROPIC_API_KEY` from
every test's environment, belt-and-braces, so a `_send` patch that silently
stopped taking effect (a rename, say) fails loudly instead of placing a
real, billed call."""

import json
import os
from typing import TYPE_CHECKING, Any, cast

import anthropic
from anthropic.types import Message, MessageParam, ToolParam, ToolUseBlock

from sextant.application.enrich.tools import ToolDefinition, ToolExecutor
from sextant.application.ports.enrichment import (
    EnrichmentAgentError,
    EnrichmentAnswers,
    EnrichmentBrief,
)

# `ANTHROPIC_API_KEY` only — never a constructor argument, a CLI flag, or a
# config value (2K design §3). A value threaded through `__init__` or a
# call argument is a value that could end up copied into a transcript entry
# or an error message; reading it here, at the moment of the call, is the
# only shape that rules that out.
_API_KEY_ENV = "ANTHROPIC_API_KEY"

# The no-progress guard's one message (2K design §3: "identical (name,
# args) three times → one nudge message, then end run with what exists").
_NUDGE = (
    "You have called the same tool with the same arguments three times in "
    "a row without new information. Give your final answer now (the JSON "
    "the instructions describe), or say what you were unable to determine "
    "and why."
)


class ClaudeApiAgent:
    """`model` is passed to the API verbatim (2K design §3: provider model
    catalogs are not re-implemented here — a bad name is the provider's own
    error, surfaced loudly through `EnrichmentAgentError`). `max_turns`
    caps how many requests one `run` sends before ending with whatever
    answer exists (default 50, per spec §3); `max_output_tokens` is the
    Messages API's required per-response cap (default 8192 — generous for
    one claim-schema JSON answer, 2K design §6, without being unbounded)."""

    def __init__(self, model: str, max_turns: int = 50, max_output_tokens: int = 8192) -> None:
        if max_turns < 1:
            raise ValueError(f"max_turns must be >= 1, got {max_turns}")
        self._model = model
        self._max_turns = max_turns
        self._max_output_tokens = max_output_tokens

    def run(self, brief: EnrichmentBrief, executor: ToolExecutor) -> EnrichmentAnswers:
        """`system(brief.instructions) + user(brief.prompt)`, with
        `executor.definitions()` mapped to the API's tool shape. While the
        response requests tools and turns remain: run them through
        `executor` — never anything else (2K design §3's "our code serves
        the bytes") — and feed the results back.

        The answer text is ALWAYS the text of whichever response ends the
        run — never an earlier turn's: a turn that mixes commentary with a
        tool request (`"Let me check the file... <tool_use>"`) has its text
        discarded the moment that turn is not the one that ends the run, so
        a later, textless ending can never surface it as though it were the
        final word. Three endings, each naming why in `partial_reason`:

        * no tool request at all — the model's true final answer.
          `partial` is `False` only when that response's own `stop_reason`
          is `"end_turn"`; a truncated or otherwise cut-off finish
          (`max_tokens`, `refusal`, ...) is `partial=True`,
          `partial_reason="stop:<reason>"` — a `stop_reason` this loop
          never trusted BEFORE (fix round 1, Important 1) let a
          `max_tokens`-truncated, plausibly mid-object answer through as
          if it were whole.
        * the no-progress guard (three identical (name, args) calls in a
          row) sends exactly one nudge and ends the run with whatever that
          one further turn produced — `partial_reason="no_progress"`.
        * `max_turns` exhausted before either of the above —
          `partial_reason="max_turns"`.
        """
        tools = [_tool_param(definition) for definition in brief.tool_definitions]
        messages: list[dict[str, Any]] = [{"role": "user", "content": brief.prompt}]
        recent_calls: list[tuple[str, str]] = []
        response: Message | None = None

        for _turn in range(self._max_turns):
            response = self._send(messages=messages, system=brief.instructions, tools=tools)
            tool_uses = _tool_uses_of(response)
            if not tool_uses:
                return _answer(response, executor, _stop_reason_partial(response))

            messages.append({"role": "assistant", "content": response.content})
            results = []
            for call in tool_uses:
                # `default=repr` (fix round 1, minor b): a call's `input`
                # is whatever JSON the model sent, but the no-progress key
                # is diagnostic bookkeeping, not a tool result — it must
                # never be able to raise ahead of `executor.execute`'s own
                # never-raises guarantee over an argument shape `json.dumps`
                # cannot serialize on its own.
                key = (call.name, json.dumps(call.input, sort_keys=True, default=repr))
                recent_calls.append(key)
                outcome = executor.execute(call.name, call.input)
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": outcome})
            messages.append({"role": "user", "content": results})

            if len(recent_calls) >= 3 and len(set(recent_calls[-3:])) == 1:
                messages.append({"role": "user", "content": _NUDGE})
                response = self._send(messages=messages, system=brief.instructions, tools=tools)
                return _answer(response, executor, "no_progress")

        assert response is not None  # max_turns >= 1, enforced at construction
        return _answer(response, executor, "max_turns")

    def _send(
        self, *, messages: list[dict[str, Any]], system: str, tools: list[dict[str, object]]
    ) -> Message:
        """The one seam that reaches the network. Reads the API key from
        `ANTHROPIC_API_KEY` at call time — never stored on `self`, never
        logged, never folded into the exception it raises — and wraps every
        SDK failure (auth, rate limit, connection, malformed response) in
        the one typed `EnrichmentAgentError` a caller can catch without
        importing `anthropic` itself.

        `messages`/`tools` are built by `run` as plain dicts (the loop's own
        conversation state, echoed straight back from whatever `anthropic`
        itself returned) rather than the SDK's own param TypedDicts — the
        `cast`s below are this one file's business, not a claim that the
        shape was checked twice."""
        api_key = os.environ.get(_API_KEY_ENV)
        if not api_key:
            raise EnrichmentAgentError(
                f"{_API_KEY_ENV} is not set — claude-api needs it to authenticate"
            )
        client = anthropic.Anthropic(api_key=api_key)
        try:
            return client.messages.create(
                model=self._model,
                max_tokens=self._max_output_tokens,
                system=system,
                messages=cast(list[MessageParam], messages),
                tools=cast(list[ToolParam], tools),
            )
        except anthropic.AnthropicError as api_error:
            raise EnrichmentAgentError(f"claude-api call failed: {api_error}") from api_error


def _answer(
    response: Message, executor: ToolExecutor, partial_reason: str | None
) -> EnrichmentAnswers:
    """The one place `EnrichmentAnswers` is built: `text` is always the
    text of THIS response (fix round 1, Important 2 — never an
    accumulated/stale earlier turn's), `partial` follows directly from
    whether a reason was given."""
    return EnrichmentAnswers(
        text=_text_of(response),
        transcript=list(executor.transcript),
        partial=partial_reason is not None,
        partial_reason=partial_reason,
    )


def _stop_reason_partial(response: Message) -> str | None:
    """`None` for a clean `"end_turn"` finish; `"stop:<reason>"` for
    anything else — a `max_tokens` truncation or a `refusal` both end a
    turn with no tool request, so `not tool_uses` alone cannot tell a
    genuine final answer from a cut-off one (fix round 1, Important 1)."""
    if response.stop_reason == "end_turn":
        return None
    return f"stop:{response.stop_reason}"


def _tool_param(definition: ToolDefinition) -> dict[str, object]:
    """A `ToolDefinition` (name/description/schema) in the shape the
    Messages API expects: `input_schema`, not `schema`."""
    return {
        "name": definition.name,
        "description": definition.description,
        "input_schema": definition.schema,
    }


def _text_of(response: Message) -> str:
    """Every text block in `response.content`, joined — the model's
    in-band final answer when there is no tool request alongside it. Reads
    the `type` DISCRIMINANT rather than `isinstance` — the same check a
    scripted test's own duck-typed stand-ins satisfy without needing to be
    the SDK's own pydantic classes."""
    return "\n".join(block.text for block in response.content if block.type == "text")


def _tool_uses_of(response: Message) -> list[ToolUseBlock]:
    """Every tool-request block in `response.content`, in the order the
    model asked for them."""
    return [block for block in response.content if block.type == "tool_use"]


if TYPE_CHECKING:
    # A typed-assignment pin (fix round 1, minor d), checked by `mypy src`
    # and erased at runtime (`TYPE_CHECKING` is `False` there): proves
    # `ClaudeApiAgent` structurally satisfies `EnrichmentAgent` so a future
    # signature drift on either side is a type error here, not a surprise
    # at whatever call site first assigns one to the other.
    from sextant.application.ports.enrichment import EnrichmentAgent

    _typed_pin: EnrichmentAgent = ClaudeApiAgent(model="pin")
