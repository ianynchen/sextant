"""`TradewindAgent`'s loop (2N design §1, Task 4 brief). The suite never
touches the network: every test drives Tradewind through its own PUBLIC
`backend_factories` seam (`Tradewind.__init__`'s keyword-only argument),
injecting a `FakeMessagesListChatModel` behind the langchain (api-key)
backend — the shape proven against a live smoke script twice before this
file existed (`_ToolFake`'s no-op `bind_tools` is the one adjustment that
shape needs: `FakeMessagesListChatModel` has none, and Tradewind's own
`_bind_tools` raises `Unsupported` the moment tools are registered against a
model that lacks one). `tests/agents/conftest.py`'s autouse fixture strips
`ANTHROPIC_API_KEY` from the environment as a second, independent guard;
this file's own autouse fixture sets a dummy value back — never a real
key — so `TradewindAgent.run`'s pre-client check passes without ever
reaching a real `ChatAnthropic` (the fake `chat_model_factory` bypasses that
entirely).

`TradewindAgent` is exercised against a REAL `ToolExecutor` (2K Task 5's
jail) over a small `tmp_path` fixture, so a tool result the loop feeds back
is a genuine one, not a stand-in, and a tool-executor refusal is the
executor's own refusal string, not one invented for the test. Every test
that runs a full turn passes `session_store=Path(":memory:")` explicitly —
the store-path DEFAULTING logic (module-local for api-key, ephemeral for
subscription) is pinned separately, so the other tests stay hermetic and
never touch `tmp_path`'s filesystem for anything but the jail's own roots.

One test goes through the same seam a level up, with a whole fake `Backend`
rather than a fake chat model (`_FailingBackend`): the SUBSCRIPTION path's
real backend drives the machine's own Claude Code engine and has no
in-process model to script, so a fake backend is the only instrument that
reaches both auth paths — and the only one that can COUNT how many times
Sextant asks a backend to run.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

# `tradewind.adapters.langchain_backend` (and `tradewind` itself) is
# import-confined to `sextant.agents.tradewind` everywhere in Sextant's OWN
# source (`tests/architecture/test_agents_confinement.py`) — this test file
# is not source Sextant ships, so importing Tradewind's own public testing
# seam directly here is the intended shape (the brief's own Test bullet:
# "injected through LangchainBackend(profile, native,
# chat_model_factory=...)").
from tradewind.adapters.langchain_backend import LangchainBackend
from tradewind.application.ports import Backend, TurnContext
from tradewind.domain.errors import TurnExecutionFailed, Unsupported
from tradewind.domain.events import Event, TurnFailed, TurnStarted
from tradewind.domain.models import Capabilities, NormalizedMessage, SessionRow

from sextant.agents.tradewind import TradewindAgent, _NudgeGuard, _tool
from sextant.application.enrich.tools import MAX_RESULT_BYTES, ToolDefinition, ToolExecutor
from sextant.application.ports.enrichment import EnrichmentAgentError, EnrichmentBrief
from sextant.domain.ignorefile import IgnoreRules
from sextant.domain.redaction import Redactor


@pytest.fixture(autouse=True)
def _dummy_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """A present-but-fake value: every test here injects its own
    `chat_model_factory`, so nothing ever constructs the REAL `ChatAnthropic`
    this key would otherwise authenticate — it exists only to clear
    `TradewindAgent.run`'s own pre-client `ANTHROPIC_API_KEY` check."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-not-real")


class _ToolFake(FakeMessagesListChatModel):
    def bind_tools(self, tools: object, **kwargs: object) -> "_ToolFake":
        return self


# The exact text the failing backend reports, asserted verbatim in the message
# the caller finally sees: a loud failure that does not carry WHAT failed is
# a different promise from the one Task 11 pins.
_BACKEND_ERROR = "upstream refused the request (probe)"


class _FailingBackend(Backend):
    """A Tradewind `Backend` whose one turn ends in `TurnFailed`, recording
    every invocation it receives.

    The subscription (claude) path has no in-process fake MODEL to script —
    its real backend drives the machine's own Claude Code engine — so the
    seam that reaches both auth paths symmetrically is Tradewind's own
    `backend_factories`, one fake registered under whichever `BackendName`
    the auth selects (`tradewind._AUTH_BACKEND`). Registering it under
    `"langchain"` too is deliberate rather than redundant with
    `test_a_tradewind_failure_surfaces_as_a_loud_typed_failure_and_writes_nothing`
    above, which drives the REAL langchain backend: what is measured here is
    how many times SEXTANT asks a backend to run before it raises, and only a
    backend that counts its own invocations can answer that.
    """

    def __init__(self, profile: object, native_config: object, invocations: list[str]) -> None:
        super().__init__(profile, native_config)  # type: ignore[arg-type]
        # `Backend.name` is a `ClassVar` a concrete backend fixes; this one
        # stands in for two, so it takes the name from the profile it was
        # built for rather than claiming either at class scope.
        self.name = profile.backend  # type: ignore[attr-defined]
        self.invocations = invocations

    def capabilities(self) -> Capabilities:
        # Exactly what this adapter's own request asks for — a system prompt,
        # in-process tools and `max_tool_rounds` — and False everywhere else:
        # a native-resume or transcript-read claim would send the turn runner
        # looking for a native transcript this fake does not have.
        return Capabilities(
            supports_system_prompt=True,
            supports_structured_output=False,
            supports_interactive_permissions=True,
            supports_in_process_tools=True,
            supports_native_resume=False,
            supports_fork=False,
            supports_transcript_read=False,
            supports_tool_round_cap=True,
        )

    async def run(self, ctx: TurnContext) -> AsyncIterator[Event]:
        self.invocations.append(ctx.turn_id)
        yield TurnStarted(turn_id=ctx.turn_id)
        yield TurnFailed(turn_id=ctx.turn_id, error=_BACKEND_ERROR)

    async def probe_native(self, session: SessionRow) -> bool:
        return False

    async def read_native_transcript(
        self, session: SessionRow, after_native_id: str | None
    ) -> list[NormalizedMessage]:
        raise Unsupported("this fake keeps no native transcript")

    async def interrupt(self, session_id: str) -> None:
        return None


def _failing_backend_factories(backend_name: str, invocations: list[str]) -> dict[str, object]:
    return {backend_name: lambda profile, native: _FailingBackend(profile, native, invocations)}


def _executor(tmp_path: Path) -> ToolExecutor:
    root = tmp_path / "root"
    root.mkdir()
    (root / "notes.txt").write_text("first line\nsecond line\n", encoding="utf-8")
    return ToolExecutor(
        roots=(root,), redactor=Redactor.from_rules(), ignore=IgnoreRules.load(root)
    )


def _brief(executor: ToolExecutor, module_root: Path | None = None) -> EnrichmentBrief:
    return EnrichmentBrief(
        prompt="Describe the module.",
        instructions="You are Sextant's enrichment agent.",
        tool_definitions=tuple(executor.definitions()),
        jailed_roots=() if module_root is None else (module_root,),
    )


def _backend_factories(model: FakeMessagesListChatModel) -> dict[str, object]:
    return {
        "langchain": lambda profile, native: LangchainBackend(
            profile, native, chat_model_factory=lambda _spec: model
        )
    }


def _agent(model: FakeMessagesListChatModel, max_turns: int = 20) -> TradewindAgent:
    return TradewindAgent(
        auth="api-key",
        model="fake-model",
        max_turns=max_turns,
        session_store=Path(":memory:"),
        backend_factories=_backend_factories(model),
    )


def _tool_call(name: str, args: dict[str, object], call_id: str = "t1") -> dict[str, object]:
    return {"name": name, "args": args, "id": call_id}


def _capturing_fake(responses: list[AIMessage], calls: list[list[object]]) -> _ToolFake:
    """A `_ToolFake` that records the `messages` list every `.astream()`
    call receives into `calls`, then delegates to the real fake behavior —
    the seam request-content pins need, since the fake itself ignores its
    input entirely (fix round 1, I1b)."""

    class _Capturing(_ToolFake):
        async def astream(self, input, **kwargs):
            calls.append(list(input))
            async for chunk in super().astream(input, **kwargs):
                yield chunk

    return _Capturing(responses=responses)


def test_happy_path_runs_one_tool_round_then_returns_the_final_answer(tmp_path: Path):
    executor = _executor(tmp_path)
    scripted = _ToolFake(
        responses=[
            AIMessage(content="", tool_calls=[_tool_call("list_dir", {"path": "."})]),
            AIMessage(content='[{"kind": "component"}]'),
        ]
    )

    answers = _agent(scripted).run(_brief(executor), executor)

    assert answers.text == '[{"kind": "component"}]'
    assert answers.partial is False
    assert answers.partial_reason is None
    assert [entry["name"] for entry in answers.transcript] == ["list_dir"]
    assert answers.transcript[0]["result"] == "notes.txt"
    # The transcript IS `executor.transcript` — the caller (cli/app.py)
    # persists that one list, not a copy the loop assembled itself.
    assert answers.transcript is not executor.transcript
    assert answers.transcript == executor.transcript


def test_a_max_tokens_truncated_finish_is_marked_partial(tmp_path: Path):
    """Fix round 1, I1a: this scenario moved from claude-api's own suite,
    not died — a provider-truncated response (no tool request, `end_reason`
    `"max_tokens"`) is a mid-object JSON fragment, marked partial rather
    than accepted as a whole answer. Scriptable via `AIMessage.response_
    metadata["stop_reason"]`, which `langchain_backend.py`'s own
    `_stop_reason` reads off the gathered response."""
    executor = _executor(tmp_path)
    scripted = _ToolFake(
        responses=[
            AIMessage(
                content='{"claims": [{"kind": "component", "na',
                response_metadata={"stop_reason": "max_tokens"},
            )
        ]
    )

    answers = _agent(scripted).run(_brief(executor), executor)

    assert answers.partial is True
    assert answers.partial_reason == "stop:max_tokens"
    assert answers.text == '{"claims": [{"kind": "component", "na'


def test_the_system_prompt_and_user_message_reach_tradewind_as_the_brief_states(
    tmp_path: Path,
):
    """Fix round 1, I1b: `brief.instructions` becomes the SYSTEM message,
    `brief.prompt` the USER message — pinned by capturing the messages
    `.astream()` actually receives, since `_ToolFake` otherwise ignores its
    own input entirely and a scripted response alone cannot prove what was
    SENT."""
    executor = _executor(tmp_path)
    calls: list[list[object]] = []
    scripted = _capturing_fake([AIMessage(content="[]")], calls)
    brief = _brief(executor)

    _agent(scripted).run(brief, executor)

    assert len(calls) == 1
    messages = calls[0]
    assert isinstance(messages[0], SystemMessage)
    assert messages[0].content == brief.instructions
    assert isinstance(messages[-1], HumanMessage)
    assert messages[-1].content == brief.prompt


def test_a_tool_definition_maps_to_a_tradewind_tool_with_input_schema_not_schema(
    tmp_path: Path,
):
    """Fix round 1, I1c: `ToolDefinition(name, description, schema)` ->
    `Tool(name, description, input_schema, handler)` — the field RENAME is
    the one thing worth pinning directly (`_tool`'s only mapping decision);
    the handler's own behavior is covered by every other test in this file
    that actually runs a turn."""
    executor = _executor(tmp_path)
    definition = ToolDefinition(
        name="find",
        description="Search for files.",
        schema={"type": "object", "properties": {"pattern": {"type": "string"}}},
    )

    tool = _tool(definition, executor, _NudgeGuard())

    assert tool.name == "find"
    assert tool.description == "Search for files."
    assert tool.input_schema == {
        "type": "object",
        "properties": {"pattern": {"type": "string"}},
    }


def test_a_multi_call_turn_keeps_every_call_distinct_for_the_no_progress_guard(tmp_path: Path):
    """Two DIFFERENT calls in the same round must not look like a repeat of
    each other — the guard only fires on the SAME `(name, args)` seen a
    third time, however the calls are distributed across rounds."""
    executor = _executor(tmp_path)
    scripted = _ToolFake(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    _tool_call("find", {"pattern": "*.txt"}, call_id="a"),
                    _tool_call("find", {"pattern": "*.md"}, call_id="b"),
                ],
            ),
            AIMessage(content="[]"),
        ]
    )

    answers = _agent(scripted).run(_brief(executor), executor)

    assert answers.partial is False
    assert len(executor.transcript) == 2
    assert all("[sextant]" not in entry["result"] for entry in executor.transcript)


def test_the_cap_ends_the_run_with_max_turns_when_never_nudged(tmp_path: Path):
    """Every round asks something DIFFERENT, so the no-progress guard never
    fires — the cap alone ends the run, and `partial_reason` stays the
    less-specific `"max_turns"`."""
    executor = _executor(tmp_path)
    scripted = _ToolFake(
        responses=[
            AIMessage(content="", tool_calls=[_tool_call("find", {"pattern": f"*.{i}"})])
            for i in range(6)
        ]
    )

    answers = _agent(scripted, max_turns=2).run(_brief(executor), executor)

    assert answers.partial is True
    assert answers.partial_reason == "max_turns"
    assert answers.text == ""
    assert len(executor.transcript) == 2


def test_nudged_then_capped_ends_with_no_progress_and_the_nudge_sentence_recorded(
    tmp_path: Path,
):
    """The model repeats the identical call past the cap: the THIRD
    identical call's transcript entry gains the nudge sentence, once, and
    the run still ends only at `max_tool_rounds` — never a fourth identical
    call skipped, never `session.stop()`."""
    executor = _executor(tmp_path)
    identical = _tool_call("find", {"pattern": "*.txt"}, call_id="same")
    scripted = _ToolFake(
        responses=[AIMessage(content="", tool_calls=[identical]) for _ in range(10)]
    )

    answers = _agent(scripted, max_turns=5).run(_brief(executor), executor)

    assert answers.partial is True
    assert answers.partial_reason == "no_progress"
    assert len(executor.transcript) == 5
    nudge = (
        "\n\n[sextant] You have made this exact call three times. The result "
        "will not change; write your answers with what you have, or try a "
        "different call."
    )
    results = [entry["result"] for entry in executor.transcript]
    assert results[2].endswith(nudge)
    # The nudge lands on the THIRD identical call only — never repeated on
    # the fourth or fifth.
    assert not results[3].endswith(nudge)
    assert not results[4].endswith(nudge)


def test_the_nudge_never_pushes_a_result_past_the_byte_cap(tmp_path: Path):
    """Fix round 1, M1: `ToolExecutor.execute` already caps every result at
    `MAX_RESULT_BYTES` (`_cap`, tools.py) — appending the nudge sentence
    UNCONDITIONALLY to a result already sitting at that cap would let the
    nudged entry exceed it by the nudge's own length, breaking the one
    invariant every other tool result honors. The nudge itself must stay
    intact (never truncated) and the persisted transcript must show exactly
    what the model was handed."""
    root = tmp_path / "root"
    root.mkdir()
    # A file large enough that `read_file`'s own result is capped at
    # `MAX_RESULT_BYTES` before the guard ever sees it.
    (root / "big.txt").write_text(
        "\n".join(f"line {i} " + "x" * 80 for i in range(2000)), encoding="utf-8"
    )
    executor = ToolExecutor(
        roots=(root,), redactor=Redactor.from_rules(), ignore=IgnoreRules.load(root)
    )
    call = _tool_call("read_file", {"path": "big.txt", "end": 2000}, call_id="same")
    scripted = _ToolFake(responses=[AIMessage(content="", tool_calls=[call]) for _ in range(4)])
    brief = EnrichmentBrief(
        prompt="Describe.",
        instructions="INSTR",
        tool_definitions=tuple(executor.definitions()),
        jailed_roots=(root,),
    )

    answers = _agent(scripted, max_turns=4).run(brief, executor)

    assert answers.partial_reason == "no_progress"
    third = executor.transcript[2]["result"]
    assert len(third.encode("utf-8")) <= MAX_RESULT_BYTES
    assert third.endswith("write your answers with what you have, or try a different call.")
    # The un-nudged rounds either side of it are genuinely AT the cap —
    # proof this scenario actually exercises the trim, not merely a result
    # that was always short enough to fit either way.
    assert len(executor.transcript[0]["result"].encode("utf-8")) == MAX_RESULT_BYTES
    assert len(executor.transcript[1]["result"].encode("utf-8")) == MAX_RESULT_BYTES


def test_the_no_progress_guards_key_building_never_raises_on_unserializable_args():
    """The guard's own bookkeeping (`json.dumps` over a call's args) must
    not be able to crash ahead of `ToolExecutor.execute`'s own never-raises
    guarantee — mirrors claude-api's own fix-round pin for the identical
    shape of bug. Tested directly against `_NudgeGuard` rather than through
    a full scripted run: a REAL tool call's args, arriving through
    LangChain's own `AIMessage.tool_calls`, are already JSON-plain by the
    time this adapter's handler ever sees them (LangChain's own message
    construction cannot carry an arbitrary Python object through that path
    at all) — so this defends against a hazard the guard's own code should
    survive regardless of whether Tradewind's real plumbing can produce it."""
    from sextant.agents.tradewind import _NudgeGuard

    class _Unserializable:
        def __repr__(self) -> str:
            return "<Unserializable>"

    guard = _NudgeGuard()
    args: dict[str, object] = {"pattern": _Unserializable()}
    for _ in range(2):
        assert guard.result_for("find", args, "ok") == "ok"
    nudged = guard.result_for("find", args, "ok")

    assert nudged.endswith("write your answers with what you have, or try a different call.")
    assert guard.nudged is True


def test_executor_refusal_strings_flow_back_and_the_loop_continues(tmp_path: Path):
    executor = _executor(tmp_path)
    scripted = _ToolFake(
        responses=[
            AIMessage(
                content="", tool_calls=[_tool_call("read_file", {"path": "does-not-exist.txt"})]
            ),
            AIMessage(content='[{"kind": "component"}]'),
        ]
    )

    answers = _agent(scripted).run(_brief(executor), executor)

    assert answers.partial is False
    assert answers.text == '[{"kind": "component"}]'
    assert executor.transcript[0]["result"] == "refused: does-not-exist.txt is not available"


def test_a_tradewind_failure_surfaces_as_a_loud_typed_failure_and_writes_nothing(
    tmp_path: Path,
):
    executor = _executor(tmp_path)
    # No scripted responses at all: the langchain backend's own request
    # raises the moment it tries to pop one, which Tradewind's `_run_turn`
    # catches and turns into `TurnFailed` — `Session.run()` then raises
    # `TurnExecutionFailed`, which this adapter wraps as `EnrichmentAgentError`.
    scripted = _ToolFake(responses=[])

    with pytest.raises(EnrichmentAgentError):
        _agent(scripted).run(_brief(executor), executor)

    # Nothing was ever executed through the jail — a caller that catches
    # this and reports has a transcript of exactly nothing to persist.
    assert executor.transcript == []


@pytest.mark.parametrize(
    ("auth", "backend_name"), [("api-key", "langchain"), ("subscription", "claude")]
)
def test_a_backend_failure_propagates_named_and_immediately_on_both_auth_paths(
    tmp_path: Path, auth: str, backend_name: str
):
    """2O Task 11's pin, and the invariant is the CLI's own: an enrichment
    run that fails must fail LOUDLY and at once, so a person watching a
    long-running model turn learns the run is dead instead of waiting on a
    silent retry that is not happening.

    Three things are asserted together because each alone is satisfiable
    without the others: the failure arrives TYPED (`EnrichmentAgentError`,
    which `api.enrich` turns into an `EnrichmentError` and `cli/app.py` into
    a `ClickException`), it NAMES what failed (the backend's own error text,
    not just "run failed"), and the backend was asked to run EXACTLY ONCE —
    the pin against a retry loop or a wait quietly appearing between the
    caller's call and the raise. `max_turns=20` makes that count meaningful:
    an adapter that retried, or that let the turn loop grind on past a failed
    turn, would show more than one invocation here.

    **Both auth paths**, because they run different backends and only the
    wrapper between them is Sextant's: `auth="api-key"` selects Tradewind's
    langchain backend and `auth="subscription"` its claude backend
    (`tradewind._AUTH_BACKEND`), and nothing above this adapter re-checks
    either.

    **Scoped (§5.4):** what is measured is SEXTANT's own layer — this
    adapter adds no retry and no wait of its own. Whether the backend SDK
    retried internally inside that single invocation is NOT measured here and
    is not claimed anywhere: the fake backend fails on its first request, so
    a real provider SDK's own backoff never runs.
    """
    executor = _executor(tmp_path)
    invocations: list[str] = []
    agent = TradewindAgent(
        auth=auth,  # type: ignore[arg-type]
        model="fake-model",
        max_turns=20,
        session_store=Path(":memory:"),
        backend_factories=_failing_backend_factories(backend_name, invocations),  # type: ignore[arg-type]
    )

    with pytest.raises(EnrichmentAgentError) as raised:
        agent.run(_brief(executor), executor)

    assert "tradewind run failed" in str(raised.value)
    assert _BACKEND_ERROR in str(raised.value)
    assert isinstance(raised.value.__cause__, TurnExecutionFailed)
    assert len(invocations) == 1
    # Nothing reached the jail, so a caller that catches this has a
    # transcript of exactly nothing to persist — the same promise the
    # real-backend failure above keeps.
    assert executor.transcript == []


def test_missing_api_key_refuses_before_any_client_is_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The pre-client check (module docstring): the key's absence is
    refused, naming the variable, before Tradewind — and so the network —
    is ever reached. No `backend_factories` override is even supplied:
    if this check silently stopped taking effect, the real langchain
    backend would be built next and fail some other, less honest way."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    executor = _executor(tmp_path)
    agent = TradewindAgent(auth="api-key", model="fake-model")

    with pytest.raises(EnrichmentAgentError) as raised:
        agent.run(_brief(executor), executor)

    assert "ANTHROPIC_API_KEY" in str(raised.value)
    assert executor.transcript == []


def test_max_turns_above_the_api_key_ceiling_is_refused_at_construction():
    """2N design §1: the langchain backend's own hard ceiling is 25 model
    iterations; a `max_tool_rounds` of N costs N+1 iterations, so 25 is
    refused up front rather than discovered as a late `TurnFailed`."""
    with pytest.raises(ValueError, match="24 model iterations"):
        TradewindAgent(auth="api-key", model="fake-model", max_turns=25)

    # 24 itself is the highest value that never reaches the ceiling.
    TradewindAgent(auth="api-key", model="fake-model", max_turns=24)


def test_a_negative_max_turns_is_refused_up_front_naming_the_flag():
    """Fix round 1, M2: a negative `--max-turns` used to fail LATE, inside
    Tradewind's own `TurnRunner` (`ConfigError`, wrapped into an unnamed
    `EnrichmentAgentError`) without ever naming `--max-turns` — refused here
    instead, at construction, the same way the ceiling is. `0` stays legal
    on EITHER auth mode: Tradewind ends it honestly (one model response, no
    tool execution permitted), not an error."""
    with pytest.raises(ValueError, match="--max-turns must be >= 0"):
        TradewindAgent(auth="api-key", model="fake-model", max_turns=-1)
    with pytest.raises(ValueError, match="--max-turns must be >= 0"):
        TradewindAgent(auth="subscription", model="fake-model", max_turns=-1)

    TradewindAgent(auth="api-key", model="fake-model", max_turns=0)
    TradewindAgent(auth="subscription", model="fake-model", max_turns=0)


def test_the_api_key_ceiling_does_not_apply_to_subscription_auth():
    """The claude (subscription) backend has no equivalent hard ceiling —
    only `auth="api-key"` is checked."""
    TradewindAgent(auth="subscription", model="fake-model", max_turns=25)


def test_api_key_store_lands_at_the_module_local_path(tmp_path: Path):
    module_root = tmp_path / "mod"
    module_root.mkdir()
    agent = TradewindAgent(auth="api-key", model="fake-model")

    path = agent._store_path((module_root, module_root / ".sextant" / "facts"))

    assert path == module_root / ".tradewind" / "sessions.sqlite"
    # `TradewindConfig`'s sqlite store does not mkdir its own parent — the
    # adapter must (module docstring).
    assert path.parent.is_dir()


def test_api_key_store_with_no_jailed_roots_is_a_named_failure_not_an_index_error():
    """Fix round 1, M8: the one production caller (`cli/app.py`) never
    builds a brief with no jailed roots, but a bare `IndexError: tuple
    index out of range` would tell a caller nothing about WHAT went wrong —
    named here instead, the same honesty every other refusal in this
    adapter has."""
    agent = TradewindAgent(auth="api-key", model="fake-model")

    with pytest.raises(EnrichmentAgentError, match="no jailed roots"):
        agent._store_path(())


def test_subscription_auth_writes_no_store(tmp_path: Path):
    module_root = tmp_path / "mod"
    module_root.mkdir()
    agent = TradewindAgent(auth="subscription", model="fake-model")

    assert agent._store_path((module_root,)) is None
    assert agent._config((module_root,)).store is None


def test_an_explicit_session_store_overrides_the_per_auth_default(tmp_path: Path):
    override = tmp_path / "custom" / "elsewhere.sqlite"
    agent = TradewindAgent(auth="subscription", model="fake-model", session_store=override)

    path = agent._store_path((tmp_path / "mod",))

    assert path == override
    assert override.parent.is_dir()


def test_memory_session_store_is_the_documented_opt_out(tmp_path: Path):
    """`Path(":memory:")` needs no mkdir of a real directory (module
    docstring): its parent (`.`) already exists, so this is a no-op rather
    than an error."""
    agent = TradewindAgent(auth="api-key", model="fake-model", session_store=Path(":memory:"))

    assert agent._store_path((tmp_path / "mod",)) == Path(":memory:")
