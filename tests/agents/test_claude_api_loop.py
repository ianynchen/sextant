"""`ClaudeApiAgent`'s Messages-API tool-use loop (2K design §3, Task 6
brief; fix round 1). The suite never touches the network (2K design §9):
every test drives the loop through a scripted fake standing in for
`_send`, the one seam that talks to the `anthropic` SDK, and
`tests/agents/conftest.py`'s autouse fixture strips `ANTHROPIC_API_KEY`
from every test's environment as a second, independent guard — if a
`_send` patch below ever silently stopped taking effect (a rename, say),
the real `_send` body would raise `EnrichmentAgentError` for a missing key
rather than place a real, billed call. `ClaudeApiAgent` is exercised
against a REAL `ToolExecutor` (2K Task 5's jail) over a small `tmp_path`
fixture, so a tool result the loop feeds back is a genuine one, not a
stand-in, and a tool-executor refusal is the executor's own refusal
string, not one invented for the test.
"""

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from sextant.agents.claude_api import _NUDGE, ClaudeApiAgent
from sextant.application.enrich.tools import ToolExecutor
from sextant.application.ports.enrichment import EnrichmentAgentError, EnrichmentBrief
from sextant.domain.ignorefile import IgnoreRules
from sextant.domain.redaction import Redactor


@dataclass
class _Block:
    """A duck-typed stand-in for one `anthropic.types.ContentBlock` — the
    loop only ever reads `.type`, and then `.text` or `.name`/`.input`/
    `.id`, so a scripted test never needs the real SDK's pydantic models."""

    type: str
    text: str = ""
    name: str = ""
    input: dict[str, object] = field(default_factory=dict)
    id: str = ""


def _text(text: str) -> _Block:
    return _Block(type="text", text=text)


def _tool_use(name: str, args: dict[str, object], call_id: str = "toolu_1") -> _Block:
    return _Block(type="tool_use", name=name, input=args, id=call_id)


@dataclass
class _Message:
    content: list[_Block]
    # Real `end_turn` for a genuine final answer; a scripted test overrides
    # this to prove the loop distrusts any OTHER finish (fix round 1,
    # Important 1) even when there is no tool request alongside it.
    stop_reason: str = "end_turn"


class _ScriptedSend:
    """Stands in for `ClaudeApiAgent._send`: hands back one canned
    `_Message` per call, in order, and records every call it received so a
    test can assert on turn count and on what the loop actually sent (2K
    Task 6 fix round 1, Important 3) — the nudge landing in the
    conversation, `system`/the first user message, and how `messages`
    grows round over round. Each recorded call stores a SHALLOW COPY of
    `messages` taken at call time, not the live list `run` keeps mutating
    afterward — the two are the same object otherwise, and every earlier
    call's snapshot would silently grow to match the final state."""

    def __init__(self, responses: list[_Message]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def __call__(self, *, messages, system, tools):
        self.calls.append({"messages": list(messages), "system": system, "tools": tools})
        return self._responses.pop(0)


def _executor(tmp_path: Path) -> ToolExecutor:
    root = tmp_path / "root"
    root.mkdir()
    (root / "notes.txt").write_text("first line\nsecond line\n", encoding="utf-8")
    return ToolExecutor(
        roots=(root,), redactor=Redactor.from_rules(), ignore=IgnoreRules.load(root)
    )


def _brief(executor: ToolExecutor) -> EnrichmentBrief:
    return EnrichmentBrief(
        prompt="Describe the module.",
        instructions="You are Sextant's enrichment agent.",
        tool_definitions=tuple(executor.definitions()),
        jailed_roots=(),
    )


def _agent(scripted: _ScriptedSend, max_turns: int = 50) -> ClaudeApiAgent:
    agent = ClaudeApiAgent(model="claude-test", max_turns=max_turns)
    agent._send = scripted  # the one seam this suite ever patches (2K design §9)
    return agent


def test_happy_path_runs_two_tool_rounds_then_returns_the_final_answer(tmp_path: Path):
    executor = _executor(tmp_path)
    scripted = _ScriptedSend(
        [
            _Message([_tool_use("list_dir", {"path": "."})]),
            _Message([_tool_use("read_file", {"path": "notes.txt"})]),
            _Message([_text('{"claims": []}')]),
        ]
    )
    agent = _agent(scripted)

    answers = agent.run(_brief(executor), executor)

    assert answers.text == '{"claims": []}'
    assert answers.partial is False
    assert answers.partial_reason is None
    assert len(scripted.calls) == 3
    assert [entry["name"] for entry in answers.transcript] == ["list_dir", "read_file"]
    assert answers.transcript[0]["result"] == "notes.txt"
    assert answers.transcript[1]["result"] == "first line\nsecond line"
    # The transcript IS `executor.transcript` — the caller (2K Task 7)
    # persists that one list, not a copy the loop assembled itself.
    assert answers.transcript is not executor.transcript
    assert answers.transcript == executor.transcript


def test_the_loop_sends_correct_request_content_across_rounds(tmp_path: Path):
    """2K Task 6 fix round 1, Important 3: pin what the loop actually
    SENDS, not just what it returns — a regression here (a dropped
    `system`, a `tool_use_id` that stops matching its own call, messages
    that stop growing) could otherwise hide behind scripted responses that
    still happen to produce the right final answer."""
    executor = _executor(tmp_path)
    scripted = _ScriptedSend(
        [
            _Message([_tool_use("list_dir", {"path": "."}, call_id="call-1")]),
            _Message([_tool_use("read_file", {"path": "notes.txt"}, call_id="call-2")]),
            _Message([_text('{"claims": []}')]),
        ]
    )
    agent = _agent(scripted)
    brief = _brief(executor)

    agent.run(brief, executor)

    # `system` is `brief.instructions`, verbatim, on every turn.
    assert all(call["system"] == brief.instructions for call in scripted.calls)

    # The very first turn is just the user prompt — nothing else.
    assert scripted.calls[0]["messages"] == [{"role": "user", "content": brief.prompt}]

    # `messages` grows by exactly one assistant turn and one user
    # (tool-result) turn per round: 1 -> 3 -> 5.
    assert [len(call["messages"]) for call in scripted.calls] == [1, 3, 5]

    # Round 1's tool_result pairs `call-1`, never a stale or swapped id.
    round_1_result = scripted.calls[1]["messages"][2]
    assert round_1_result["role"] == "user"
    assert round_1_result["content"] == [
        {"type": "tool_result", "tool_use_id": "call-1", "content": "notes.txt"}
    ]

    # Round 2's tool_result pairs `call-2` — the FINAL turn's full history,
    # both rounds present and in order.
    final_messages = scripted.calls[2]["messages"]
    assert final_messages[2]["content"][0]["tool_use_id"] == "call-1"
    assert final_messages[4]["content"][0]["tool_use_id"] == "call-2"
    assert final_messages[4]["content"][0]["content"] == "first line\nsecond line"


def test_max_turns_cap_ends_the_run_with_partial_answers_marked(tmp_path: Path):
    executor = _executor(tmp_path)
    scripted = _ScriptedSend(
        [
            _Message([_tool_use("find", {"pattern": "*.txt"})]),
            _Message([_tool_use("find", {"pattern": "*.md"})]),
        ]
    )
    agent = _agent(scripted, max_turns=2)

    answers = agent.run(_brief(executor), executor)

    assert answers.partial is True
    assert answers.partial_reason == "max_turns"
    assert answers.text == ""
    assert len(scripted.calls) == 2
    assert len(answers.transcript) == 2


def test_stale_interim_text_from_an_earlier_turn_is_never_returned_as_the_answer(
    tmp_path: Path,
):
    """2K Task 6 fix round 1, Important 2: a turn can legally mix
    commentary with a tool request ("Let me check the file... <tool_use>").
    That text must NOT survive to become the answer if a LATER turn — the
    one that actually ends the run — has no text of its own; only the
    FINAL response's text counts."""
    executor = _executor(tmp_path)
    scripted = _ScriptedSend(
        [
            _Message(
                [_text("Let me check the file first."), _tool_use("find", {"pattern": "*.txt"})]
            ),
            _Message([_tool_use("find", {"pattern": "*.md"})]),  # no text — the final turn
        ]
    )
    agent = _agent(scripted, max_turns=2)

    answers = agent.run(_brief(executor), executor)

    assert answers.partial is True
    assert answers.partial_reason == "max_turns"
    assert answers.text == ""  # never "Let me check the file first."


def test_a_max_tokens_truncated_finish_with_no_tool_request_is_marked_partial(tmp_path: Path):
    """2K Task 6 fix round 1, Important 1: a response with no `tool_use`
    block used to be treated as an unconditional clean answer. A
    `max_tokens`-truncated finish looks identical in shape — no tool
    request — but its text is possibly a mid-object JSON fragment, and
    must be marked partial rather than accepted as whole."""
    executor = _executor(tmp_path)
    scripted = _ScriptedSend(
        [_Message([_text('{"claims": [{"kind": "component", "na')], stop_reason="max_tokens")]
    )
    agent = _agent(scripted)

    answers = agent.run(_brief(executor), executor)

    assert answers.partial is True
    assert answers.partial_reason == "stop:max_tokens"
    assert answers.text == '{"claims": [{"kind": "component", "na'


def test_a_refusal_finish_with_no_tool_request_is_marked_partial(tmp_path: Path):
    executor = _executor(tmp_path)
    scripted = _ScriptedSend([_Message([_text("I can't help with that.")], stop_reason="refusal")])
    agent = _agent(scripted)

    answers = agent.run(_brief(executor), executor)

    assert answers.partial is True
    assert answers.partial_reason == "stop:refusal"


def test_a_clean_end_turn_finish_is_never_marked_partial(tmp_path: Path):
    """The positive control for Important 1's `stop_reason` check: an
    ordinary final answer's `stop_reason` really is `"end_turn"`, so the
    new check does not turn every clean answer into a partial one."""
    executor = _executor(tmp_path)
    scripted = _ScriptedSend([_Message([_text('{"claims": []}')], stop_reason="end_turn")])
    agent = _agent(scripted)

    answers = agent.run(_brief(executor), executor)

    assert answers.partial is False
    assert answers.partial_reason is None


def test_no_progress_guard_fires_on_three_identical_calls_then_ends_the_run(tmp_path: Path):
    executor = _executor(tmp_path)
    identical = _tool_use("find", {"pattern": "*.txt"})
    scripted = _ScriptedSend(
        [
            _Message([identical]),
            _Message([identical]),
            _Message([identical]),
            _Message([_text('{"claims": [], "note": "gave up"}')]),
        ]
    )
    agent = _agent(scripted, max_turns=50)

    answers = agent.run(_brief(executor), executor)

    # Three identical calls, then exactly one more turn carrying the nudge
    # — never a fourth identical call, never the full `max_turns` budget.
    assert len(scripted.calls) == 4
    assert answers.partial is True
    assert answers.partial_reason == "no_progress"
    assert answers.text == '{"claims": [], "note": "gave up"}'
    nudge_turn = scripted.calls[3]["messages"]
    assert any(message.get("content") == _NUDGE for message in nudge_turn)


def test_no_progress_guard_key_building_never_raises_on_unserializable_args(tmp_path: Path):
    """2K Task 6 fix round 1, minor (b): the guard's own bookkeeping
    (`json.dumps` over a call's `input`) must not be able to crash the loop
    ahead of `ToolExecutor.execute`'s own never-raises guarantee — an
    argument shape `json.dumps` cannot serialize on its own (nothing a real
    Messages-API tool call would ever send, but the guard must not assume
    that) is exactly the kind of surprise `default=repr` exists to absorb."""

    class _Unserializable:
        def __repr__(self) -> str:
            return "<Unserializable>"

    executor = _executor(tmp_path)
    identical = _tool_use("find", {"pattern": _Unserializable()})
    scripted = _ScriptedSend(
        [
            _Message([identical]),
            _Message([identical]),
            _Message([identical]),
            _Message([_text("{}")]),
        ]
    )
    agent = _agent(scripted, max_turns=50)

    answers = agent.run(_brief(executor), executor)

    assert answers.partial_reason == "no_progress"
    assert len(scripted.calls) == 4


def test_tool_executor_error_strings_flow_back_and_the_loop_continues(tmp_path: Path):
    executor = _executor(tmp_path)
    scripted = _ScriptedSend(
        [
            _Message([_tool_use("read_file", {"path": "does-not-exist.txt"})]),
            _Message([_text('{"claims": []}')]),
        ]
    )
    agent = _agent(scripted)

    answers = agent.run(_brief(executor), executor)

    assert answers.partial is False
    assert answers.partial_reason is None
    assert answers.text == '{"claims": []}'
    assert answers.transcript[0]["result"] == "refused: does-not-exist.txt is not available"
    assert len(scripted.calls) == 2


def test_an_api_error_from_send_surfaces_as_a_loud_typed_failure_and_writes_nothing(
    tmp_path: Path,
):
    executor = _executor(tmp_path)

    def _boom(*, messages, system, tools):
        raise EnrichmentAgentError("claude-api call failed: connection reset")

    agent = ClaudeApiAgent(model="claude-test", max_turns=50)
    agent._send = _boom

    with pytest.raises(EnrichmentAgentError):
        agent.run(_brief(executor), executor)

    # Nothing was ever executed through the jail — a caller that catches
    # this and reports has a transcript of exactly nothing to persist.
    assert executor.transcript == []


def test_tool_definitions_are_mapped_to_the_messages_api_shape(tmp_path: Path):
    """`ToolDefinition.schema` must reach the API as `input_schema` — the
    field name the Messages API actually reads (2K design §3)."""
    executor = _executor(tmp_path)
    scripted = _ScriptedSend([_Message([_text("{}")])])
    agent = _agent(scripted)

    agent.run(_brief(executor), executor)

    sent_tools = scripted.calls[0]["tools"]
    sent_names = {tool["name"] for tool in sent_tools}
    assert sent_names == {"list_dir", "find", "grep", "read_file"}
    for tool in sent_tools:
        assert "input_schema" in tool
        assert "schema" not in tool


def test_a_multi_call_turn_keeps_every_call_distinct_for_the_no_progress_guard(tmp_path: Path):
    """Two DIFFERENT calls in the same turn must not look like a repeat of
    each other — the guard only fires on three *identical* (name, args)
    calls, however they are distributed across turns."""
    executor = _executor(tmp_path)
    scripted = _ScriptedSend(
        [
            _Message(
                [
                    _tool_use("find", {"pattern": "*.txt"}, call_id="a"),
                    _tool_use("find", {"pattern": "*.md"}, call_id="b"),
                ]
            ),
            _Message([_text("{}")]),
        ]
    )
    agent = _agent(scripted)

    answers = agent.run(_brief(executor), executor)

    assert answers.partial is False
    assert len(scripted.calls) == 2


def test_max_turns_must_be_at_least_one():
    """2K Task 6 fix round 1, minor (c): `run`'s final-turn fallback relies
    on the loop body executing at least once (`response` is never `None`
    when `max_turns` is exhausted) — a construction-time refusal is the
    honest failure mode, not a loop that silently never runs at all."""
    with pytest.raises(ValueError):
        ClaudeApiAgent(model="claude-test", max_turns=0)
    with pytest.raises(ValueError):
        ClaudeApiAgent(model="claude-test", max_turns=-1)


def test_send_forwards_max_output_tokens_to_the_api(tmp_path: Path, monkeypatch):
    """2K Task 6 fix round 1, minor (f): `max_output_tokens` (default
    8192) must actually reach the API call's `max_tokens` — exercised
    through `_send`'s real body, with the SDK's own client class stubbed
    out so nothing here reaches the network."""
    import anthropic

    captured: dict[str, object] = {}

    class _FakeMessages:
        def create(self, **kwargs: object) -> _Message:
            captured.update(kwargs)
            return _Message([_text("{}")])

    class _FakeClient:
        def __init__(self, api_key: str) -> None:
            self.messages = _FakeMessages()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.setattr(anthropic, "Anthropic", _FakeClient)

    executor = _executor(tmp_path)
    agent = ClaudeApiAgent(model="claude-test", max_output_tokens=2048)

    agent.run(_brief(executor), executor)

    assert captured["max_tokens"] == 2048


def test_max_output_tokens_defaults_to_8192():
    assert ClaudeApiAgent(model="claude-test")._max_output_tokens == 8192
