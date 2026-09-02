"""`ClaudeApiAgent`'s Messages-API tool-use loop (2K design §3, Task 6
brief). The suite never touches the network (2K design §9): every test
drives the loop through a scripted fake standing in for `_send`, the one
seam that talks to the `anthropic` SDK — `ClaudeApiAgent` is exercised
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


class _ScriptedSend:
    """Stands in for `ClaudeApiAgent._send`: hands back one canned
    `_Message` per call, in order, and records every call it received so a
    test can assert on turn count and on what the loop actually sent
    (e.g. that the no-progress nudge landed in the conversation)."""

    def __init__(self, responses: list[_Message]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def __call__(self, *, messages, system, tools):
        self.calls.append({"messages": messages, "system": system, "tools": tools})
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
    assert len(scripted.calls) == 3
    assert [entry["name"] for entry in answers.transcript] == ["list_dir", "read_file"]
    assert answers.transcript[0]["result"] == "notes.txt"
    assert answers.transcript[1]["result"] == "first line\nsecond line"
    # The transcript IS `executor.transcript` — the caller (2K Task 7)
    # persists that one list, not a copy the loop assembled itself.
    assert answers.transcript is not executor.transcript
    assert answers.transcript == executor.transcript


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
    assert answers.text == ""
    assert len(scripted.calls) == 2
    assert len(answers.transcript) == 2


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
    assert answers.text == '{"claims": [], "note": "gave up"}'
    nudge_turn = scripted.calls[3]["messages"]
    assert any(message.get("content") == _NUDGE for message in nudge_turn)


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
