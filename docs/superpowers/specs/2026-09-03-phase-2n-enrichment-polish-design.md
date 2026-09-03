# Phase 2N — Enrichment polish: the Tradewind adapter, config verdicts, the flight fixes

Status: approved design, pre-plan. Binding for the 2N implementation plan.

Phase 2N is gap area D of the 2026-09-02 gap analysis. It replaces the enrichment
agent's direct Anthropic loop with the user's Tradewind library, makes config-shaped
uncertainty addressable by verdicts (all three 2026-09-03 flight agents independently
hit that wall), fixes the flight-1 INSTRUCTIONS ambiguities, and validates the verdict
engine end to end for the first time. The roadmap after 2N: 2O → 2P → 2J →
version-bump gate → call graph → L.

User rulings folded in: the claude-api adapter is REMOVED, not deprecated; the
langchain profile persists its session mirror to a module-local
`<module>/.tradewind/sessions.sqlite`; Sextant's usage never spawns subagents or
forks, so history scope is left to Tradewind's own truthful per-backend defaults.

## §1 The Tradewind adapter

New `src/sextant/agents/tradewind.py` implementing `EnrichmentAgent.run(brief,
executor) -> EnrichmentAnswers` through Tradewind's PUBLIC client only — one
`Tradewind(config)` per run, one session (caller-minted UUID), one `session.run(...)`
turn. Tradewind is pinned as a git dependency at an exact commit (≥ 0.6.0; its 0.6.0
breaking change — `TurnContext.load_history` as an async lazy closure — touches only
custom `Backend` implementations, which Sextant does not write).

- **Tools:** each of the executor's four definitions registers as a Tradewind
  `Tool(name, description, input_schema, handler)` whose handler wraps
  `executor.execute(name, args)` — the jail and its redaction ride in-process,
  unchanged. The executor's transcript remains the record Sextant persists to
  `enrich-transcript.jsonl`; Tradewind's mirror is an additional audit trail, not a
  replacement.
- **The loop contract, mapped:** `system_prompt` = the INSTRUCTIONS text; the user
  prompt = the brief; `max_tool_rounds` = `--max-turns`; the answer = `final_text`
  (in-band JSON, unparsed by the adapter). `end_reason` maps to the port's honesty
  fields: `end_turn` → `partial=False`; `max_tokens` → `partial=True,
  "stop:max_tokens"`; `max_tool_rounds` → `partial=True, "max_turns"`;
  `interrupted` → `partial=True, "no_progress"` when Sextant's own guard ended the
  run. The no-progress guard moves adapter-side: the tool handlers see every call, and
  on the third identical `(name, canonical args)` the handler returns the nudge text
  once, then the adapter calls `session.stop()`.
- **Auth is explicit, never guessed:** `--auth subscription` (Tradewind's `claude`
  backend — the machine's logged-in Claude Code; that engine disables its own built-in
  dev tools, so only the registered jailed tools exist and the jail guarantee holds)
  or `--auth api-key` (the `langchain` backend; the key is read from
  `ANTHROPIC_API_KEY` by SEXTANT and passed into `TradewindConfig` — Tradewind never
  reads env, and the missing-key refusal keeps naming the variable before any client
  is built). Default: `--agent tradewind --auth subscription`; `.sextant.yml
  enrich:` may set both, flags win. `AGENT_REGISTRY` maps `tradewind` to the
  constructor; `claude-api` is deleted from the registry, the codebase, and
  `pyproject.toml` (the `anthropic` dependency and its confinement test go with it —
  the confinement pattern itself moves to `tradewind`: importable only in
  `agents/tradewind.py`, with the same positive-control architecture test).
- **The session store:** the `api-key`/langchain profile — where the mirror is the
  system of record — persists it to `<module>/.tradewind/sessions.sqlite`
  (module-local: the audit trail sits beside the workspace it explains, and
  `history()` on a module's store shows only that module's runs). The `subscription`
  profile keeps Tradewind's ephemeral default: the Claude Code engine already keeps
  its own native record, and a second copy adds nothing. `.sextant.yml enrich:
  session_store:` overrides the path (`:memory:` opts out). Consequences, both
  ruled: `.tradewind/` joins the JAIL-SPECIFIC exclusions (the model reading its own
  prior conversation is the same feedback loop that excluded the overlay file in 2K)
  — invisible to all four tools, tested; and the store is an audit LOG, so re-analyze
  does not clear it (unlike `render/`). The bundle never copies it (export copies
  named artifacts only — pinned). Docs tell users to gitignore `.tradewind/`; the
  fixtures' own ignore rules gain the entry. Everything in the mirror already passed
  the jail's redaction (tool results) and the brief's `redact_text` — the database
  holds masked content only, and the spec says so where the store is documented.
- **History scope is a deliberate non-choice:** Sextant never spawns subagents or
  forks, so `"tree"` has nothing to fold, and the adapter passes no `history_scope`
  at all — Tradewind's per-backend defaults are already truthful (`flat` where the
  mirror rebuilds, `none` where the engine resumes natively), an enrichment session
  is single-turn so even `flat` reads nothing, and an explicit `"flat"` on the
  `claude` backend would be refused by Tradewind's own no-silent-dropping rule. The
  adapter docstring states this reasoning.
- **Testing without the network:** the scripted-fake loop tests move to Tradewind's
  public `backend_factories` seam — a `FakeMessagesListChatModel` subclass with a
  no-op `bind_tools`, injected via `LangchainBackend(profile, native,
  chat_model_factory=...)` (the shape proven in the live smoke, twice). Covered:
  happy path (tool round-trip through OUR handler, in-band answer), the cap
  (`end_reason="max_tool_rounds"` → `partial_reason="max_turns"`), the no-progress
  guard (nudge once, then stop → `"no_progress"`), executor refusal strings flowing
  back as tool results, a Tradewind failure surfacing as `EnrichmentAgentError`
  (nothing written), and the store landing at the module-local path for `api-key`
  while `subscription` writes none. One opt-in live test, key-gated and excluded from
  the default run, replaces the claude-api one.

## §2 Verdicts for config-shaped questions

The overlay's verdict `question` becomes a discriminated union of two identities:

- the existing endpoint shape `{protocol, method, path, kind}` — unchanged, so every
  existing overlay validates as before;
- a config shape `{key, source, kind}` matching the coverage table's
  unresolved-configuration rows (`kind` is the row's unresolved reason class;
  `source` the file that carried the key, module-root-relative; both pass the same
  canonical-spelling rule — `redact_text` on both sides — the endpoint shape uses).

The brief prints config open-questions as copyable identity rows exactly as it prints
endpoint ones. `validate_overlay` extends by construction: a config verdict must match
a real unresolved-config row in the workspace, and renders beside the coverage table's
unresolved listing (the `beside-open-question` anchor gains that placement for config
identities). `unanswered` semantics carry over unchanged: the answer is exempt, the
referent never is.

## §3 Boundaries that file questions

Only rows the machine already computes gain an address; no new detection:

- Unresolved-configuration rows (the resolver's five-reason set) become addressable
  via §2 — they are already in the workspace and the coverage table.
- `spring.config.import` / remote-source rows — the exact rows all three flight
  agents wanted to answer and legally could not — get identity rows in the brief's
  open-questions section, carrying the config shape.

The config-constructed-in-code and expose-vs-call boundaries stay silent in 2N: the
machine computes no row for them, and a question the machine cannot state precisely
is a guess wearing a question's clothes.

## §4 INSTRUCTIONS fixes

One sentence each, closing the flight-1 ambiguities: cite paths are module-root-
relative (the spelling `find`/`grep` print); member symbols use the short
`pkg/Class#` form the examples show; a how-to `section` anchors
`after-endpoint-table` when it concerns the endpoints, else `end-of-document`. Plus
one worked config-verdict example (§2's shape, both answered and `unanswered`
forms). The golden overlay's `instructions_hash` regenerates once, deliberately, as
its pin requires.

## §5 Validation flight and docs

- One live flight through the REAL `--agent tradewind --auth subscription` path on a
  module with genuine open questions — `fixtures/orders-service` carries the jms
  parse-binding row, and §3 gives the petclinic examples config rows — exercising
  the verdict engine end to end for the first time (2K's flights all landed on
  question-free modules). The flight's acceptance: at least one verdict claim
  validates and renders beside its question; results recorded in the phase report,
  not committed as fixtures.
- Docs: D04's agent story rewritten for Tradewind (auth selection, the store, the
  jail exclusion); README usage updated; DR-2's amendment note names Tradewind as
  the sanctioned caller's implementation; the committed Maven-gap-sentence fix
  (e7eab1b, already on this branch) rides; COVERAGE/ARCHITECTURE untouched otherwise.

## §6 Non-goals

Codex/Cursor profiles (Tradewind supports them; Sextant wires them when wanted),
`history_scope`/subagent features, new open-question detection beyond §3's
re-addressing, INSTRUCTIONS rewrites beyond §4's named sentences, any resolve-engine
change, and the call-graph phase (scheduled after 2J).

## §7 Testing summary

No network in tests, ever; the one live test is key/subscription-gated and excluded
from the default run. New pins: the adapter loop set (§1), the jail's `.tradewind/`
exclusion, the store-path rules per auth mode, config-verdict validation (match,
refusal, unanswered-referent, canonical spelling), the brief's config identity rows,
the INSTRUCTIONS hash regeneration, and removal pins — `anthropic` importable
nowhere, `claude-api` refused by the registry with the known list naming `tradewind`.
