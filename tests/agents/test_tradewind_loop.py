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
"""

from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

# `tradewind.adapters.langchain_backend` (and `tradewind` itself) is
# import-confined to `sextant.agents.tradewind` everywhere in Sextant's OWN
# source (`tests/architecture/test_agents_confinement.py`) — this test file
# is not source Sextant ships, so importing Tradewind's own public testing
# seam directly here is the intended shape (the brief's own Test bullet:
# "injected through LangchainBackend(profile, native,
# chat_model_factory=...)").
from tradewind.adapters.langchain_backend import LangchainBackend

from sextant.agents.tradewind import TradewindAgent
from sextant.application.enrich.tools import ToolExecutor
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
