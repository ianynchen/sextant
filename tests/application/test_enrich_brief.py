"""`compose_brief` (2K design §5): the deterministic prompt every door hands
an agent (or writes to disk for `--dry-run`) before a single tool call is
made. Every test here is about what the brief CONTAINS and how it is built —
never about a model's answer, which does not exist yet at this point in the
pipeline."""

import json
from pathlib import Path

from sextant.application.enrich.brief import compose_brief
from sextant.application.enrich.tools import ToolDefinition
from sextant.domain.redaction import Redactor

METADATA = {
    "module": {"id": "com.acme:orders", "kind": "service", "languages": ["java"]},
    "gaps": ["call_graph_not_implemented", "config_as_code_not_read"],
}
ARCHITECTURE_MD = "# com.acme:orders\n\nGenerated from commit `abc123`.\n"
TOOLS = (
    ToolDefinition(name="list_dir", description="list", schema={"type": "object"}),
    ToolDefinition(name="read_file", description="read", schema={"type": "object"}),
)
ROOTS = (Path("/module"),)


class _Workspace:
    """The three named queries `compose_brief` reads, and nothing else — a
    hand-built double so these tests are about brief composition, not about
    an analysed fixture's own content."""

    def __init__(
        self,
        open_questions: list[dict[str, object]] | None = None,
        endpoints: list[dict[str, object]] | None = None,
        resolved_config: list[dict[str, object]] | None = None,
    ) -> None:
        self._open_questions = open_questions or []
        self._endpoints = endpoints or []
        self._resolved_config = resolved_config or []

    def query(self, name: str, **params: object) -> list[dict[str, object]]:
        if name == "open_questions":
            return list(self._open_questions)
        if name == "endpoints":
            return list(self._endpoints)
        if name == "resolved_config":
            return list(self._resolved_config)
        raise AssertionError(f"compose_brief asked for an unexpected query: {name}")


def _compose(workspace: _Workspace, redactor: Redactor | None = None):
    return compose_brief(
        workspace,
        Path("/module"),
        "the instructions text",
        ARCHITECTURE_MD,
        METADATA,
        redactor or Redactor.from_rules(),
        TOOLS,
        ROOTS,
    )


def test_the_brief_carries_the_instructions_and_tool_shape_unchanged():
    brief = _compose(_Workspace())
    assert brief.instructions == "the instructions text"
    assert brief.tool_definitions == TOOLS
    assert brief.jailed_roots == ROOTS


def test_the_prompt_embeds_the_rendered_document_verbatim():
    brief = _compose(_Workspace())
    assert ARCHITECTURE_MD.rstrip("\n") in brief.prompt


def test_the_prompt_names_every_known_gap():
    brief = _compose(_Workspace())
    assert "call_graph_not_implemented" in brief.prompt
    assert "config_as_code_not_read" in brief.prompt


def test_open_questions_reach_the_prompt_as_the_verdict_schema_shape():
    """ "Verbatim" (2K design §5) means a model can copy the row straight into
    a `verdict` claim's `question` field — so it is printed as exactly the
    JSON shape `OpenQuestionRef` carries."""
    question = {
        "protocol": "jms",
        "method": None,
        "path": "relay-queue",
        "question": "payload_binding",
        "candidates": "[]",
        "evidence": "two callers parse the body differently",
    }
    brief = _compose(_Workspace(open_questions=[question]))
    expected = json.dumps(
        {"protocol": "jms", "method": None, "path": "relay-queue", "kind": "payload_binding"},
        sort_keys=True,
    )
    assert expected in brief.prompt
    assert "two callers parse the body differently" in brief.prompt


def test_an_open_questions_path_is_redacted_before_it_reaches_the_prompt():
    """2K Task 7 ruling 1: "the brief IS the wire" — an address-shaped value
    a repo's own `redact:` section would mask must never reach the model
    unmasked, because the model has no other way to see it."""
    redactor = Redactor.from_rules()
    question = {
        "protocol": "http",
        "method": "GET",
        "path": "https://user:pass@billing.example.com/x",
        "question": "format_conflict",
        "candidates": "[]",
        "evidence": None,
    }
    brief = _compose(_Workspace(open_questions=[question]), redactor)
    assert "user:pass" not in brief.prompt
    assert "https://billing.example.com/x" in brief.prompt


def test_a_module_with_no_open_questions_says_so_rather_than_omitting_the_section():
    brief = _compose(_Workspace())
    assert "None open." in brief.prompt


def test_the_digest_lists_unresolved_and_narrowed_endpoints_but_not_resolved_ones():
    endpoints = [
        {"protocol": "http", "method": "GET", "path": "/a", "resolution": "unresolved"},
        {"protocol": "kafka", "method": None, "path": "topic-b", "resolution": "narrowed"},
        {"protocol": "http", "method": "GET", "path": "/c", "resolution": "resolved"},
    ]
    brief = _compose(_Workspace(endpoints=endpoints))
    assert "http GET /a — resolution: unresolved" in brief.prompt
    assert "kafka topic-b — resolution: narrowed" in brief.prompt
    assert "/c" not in brief.prompt


def test_the_digest_lists_unresolved_config_keys_with_their_reason():
    resolved_config = [
        {
            "key": "billing.url",
            "value": None,
            "environment": "prod",
            "unresolved_reason": "missing_key",
        },
        {
            "key": "orders.url",
            "value": "http://orders",
            "environment": "prod",
            "unresolved_reason": None,
        },
    ]
    brief = _compose(_Workspace(resolved_config=resolved_config))
    assert "billing.url — missing_key in prod" in brief.prompt
    assert "orders.url" not in brief.prompt


def test_the_digest_says_so_when_the_graph_is_unsure_about_nothing():
    brief = _compose(_Workspace())
    assert "None recorded." in brief.prompt


def test_the_prompt_names_all_four_content_kinds_and_the_verification_seat():
    brief = _compose(_Workspace())
    assert "Components and their purposes" in brief.prompt
    assert "Extension guides" in brief.prompt
    assert "Algorithm descriptions" in brief.prompt
    assert "class or sequence diagrams" in brief.prompt
    assert "unanswered" in brief.prompt


def test_the_prompt_names_every_closed_anchor_value():
    brief = _compose(_Workspace())
    for anchor in (
        "after-component-overview",
        "after-endpoint-table",
        "beside-open-question",
        "end-of-document",
    ):
        assert anchor in brief.prompt


def test_composing_the_same_inputs_twice_is_byte_identical():
    """NFR-1's amendment (2K design §8): brief composition is deterministic —
    only the agent's own response is excluded from that promise."""
    workspace = _Workspace(
        open_questions=[
            {
                "protocol": "jms",
                "method": None,
                "path": "q",
                "question": "payload_binding",
                "candidates": "[]",
                "evidence": None,
            }
        ],
        endpoints=[{"protocol": "http", "method": "GET", "path": "/a", "resolution": "unresolved"}],
    )
    first = _compose(workspace)
    second = _compose(workspace)
    assert first.prompt == second.prompt
