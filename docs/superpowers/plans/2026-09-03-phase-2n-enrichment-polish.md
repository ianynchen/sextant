# Phase 2N Implementation Plan — Enrichment polish

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** the Tradewind adapter replacing claude-api, config-shaped verdicts, the INSTRUCTIONS fixes, the library facade, and the first verdict-engine validation flight — per the approved spec.

**Architecture:** a new agents adapter behind the unchanged `EnrichmentAgent` port; an untagged union widening the overlay's verdict identity; composition extracted from `cli/app.py` into functions both the CLI and a new `sextant.api` call.

**Tech Stack:** existing + `tradewind` (git dependency, commit-sha pinned via `[tool.uv.sources]`); `anthropic` direct dependency removed.

**Spec:** docs/superpowers/specs/2026-09-03-phase-2n-enrichment-polish-design.md (binding; revised after adversarial review — §1's guard redesign, §2's field-for-field identity, and the honesty statements are requirements, not suggestions).

## Global Constraints

- No network in tests, ever; the one live test is gated (subscription or key) AND excluded from the default run; the §5 flight is a phase act, not a suite member.
- Determinism NFR-1 (the agent call excepted); DR-2 amended note: Tradewind is the sanctioned caller's implementation.
- Unresolved-is-an-answer; a refusal names its reason; nothing model-visible carries a raw host path or credential (the 2K exits are settled law).
- Framework names in catalogs only; no resolve-engine changes.
- CLI behavior is byte-unchanged by the facade extraction (Task 5's whole claim); goldens move only for the instructions-hash line.
- uv.lock never committed; no version bumps.
- Style §13.5; scripts/check.sh green at every commit; suite baseline 1469 passed / 2 skipped (branch head 0f7c89d-era), zero regressions.

---

### Task 1: Config-shaped verdict identities

**Files:**
- Modify: `src/sextant/domain/enrichment.py` (the identity union), `src/sextant/application/enrich/validate.py` (config-verdict matching + placement), `src/sextant/egress/render/document.py` (render a config verdict beside the coverage table's unresolved listing).
- Test: `tests/domain/test_enrichment_schema.py`, `tests/application/test_enrich_validate.py`, `tests/egress/test_render_assembly.py`.

**Interfaces:**
- Produces: `ConfigQuestionRef(key: str, source: str | None, environment: str, kind: str)` frozen, `extra="forbid"`; `VerdictClaim.question: OpenQuestionRef | ConfigQuestionRef` as an UNTAGGED union (disjoint required fields `protocol` vs `key` make the parse unambiguous — a test proves an ambiguous-shape payload is refused, not guessed). Matching: a config verdict must equal a workspace `resolved_config` unresolved row field-for-field, `redact_text` canonicalization on `key` and `source` both sides, `source` compared as the ROW'S OWN spelling. `unanswered` exempts the answer, never the referent (existing law, extended).
- Consumes: the resolver's five-reason rows already in the workspace.

- [ ] **Step 1: failing schema tests** — config shape accepted; endpoint shape unchanged (an existing overlay fixture validates byte-identically); nullable `source`; extra field refused; the ambiguity probe.
- [ ] **Step 2: failing validate tests** — match against a real unresolved row (environment-distinguished: two rows differing only by environment, verdict matches exactly one); phantom row refused; userinfo-bearing source matches after redact_text both sides; unanswered referent still checked.
- [ ] **Step 3: failing render test** — a config verdict renders beside the coverage table's unresolved-configuration listing (the `beside-open-question` anchor's config placement), endpoint verdicts unchanged.
- [ ] **Step 4: implement; suite; hooks; commit** `feat: config-shaped verdict identities — the coverage table becomes answerable`.

### Task 2: The brief files config questions

**Files:**
- Modify: `src/sextant/application/enrich/brief.py` (print unresolved-config rows as copyable identity rows in the open-questions section — including the `spring.config.import`/remote-source rows).
- Test: `tests/application/test_enrich_brief.py`.

**Interfaces:**
- Consumes: Task 1's `ConfigQuestionRef` field names — the brief prints exactly those fields with exactly the workspace spellings, so a model copying a row back always matches.
- Produces: the brief's open-questions section carrying both identity shapes; byte-determinism preserved.

- [ ] **Step 1: failing tests** — a workspace with two environment-distinguished unresolved rows yields two identity rows spelled `{key, source, environment, kind}` with the row's own source spelling (nullable rendered honestly); a workspace with none renders the existing "None open" line; brief bytes deterministic.
- [ ] **Step 2: implement; suite; hooks; commit** `feat: the brief prints config questions a verdict can copy`.

### Task 3: INSTRUCTIONS fixes

**Files:**
- Modify: `src/sextant/enrich/INSTRUCTIONS.md` (three one-sentence ambiguity fixes: cite paths are module-root-relative as find/grep print them; members use the short `pkg/Class#` form; a how-to section anchors after-endpoint-table when it concerns endpoints, else end-of-document — plus the config-verdict worked example, answered and `unanswered` forms, stating identities come from the printed rows, cites from the tools), `fixtures/orders-service/.sextant-enrichment.json` (instructions_hash regenerated, the pin's deliberate act).
- Test: existing hash pin; one new INSTRUCTIONS-content pin per sentence (substring pins, so wording can breathe but the teachings cannot vanish).

- [ ] **Step 1: edit; regenerate hash; new pins; suite; hooks; commit** `docs: INSTRUCTIONS — the flight-1 ambiguities closed, config verdicts taught`.

### Task 4: The Tradewind adapter

**Files:**
- Create: `src/sextant/agents/tradewind.py`, `tests/agents/test_tradewind_loop.py`, `tests/integration/test_tradewind_live.py` (opt-in, gated, default-excluded — replaces the claude-api live test).
- Delete: `src/sextant/agents/claude_api.py`, `tests/agents/test_claude_api_loop.py` (its scenarios move, not die — every loop behavior re-pins against the new adapter).
- Modify: `pyproject.toml` (+`tradewind` via `[tool.uv.sources]` commit-sha pin; −`anthropic` direct dep), `src/sextant/agents/__init__.py` (registry: `"tradewind"` → a LAZY factory importing inside the callable; `claude-api` gone), `src/sextant/cli/app.py` (`--auth {subscription,api-key}` flag + `.sextant.yml enrich: auth:`/`session_store:` keys, flags win; default `--agent tradewind --auth subscription`; `--max-turns` default 50→20; on api-key a value >24 refused: `--max-turns 25 exceeds the api-key backend's own ceiling of 24 model iterations`), `src/sextant/application/stages/enrich.py` (textless-partial ruling: empty text + partial → a loud failure naming the partial reason, never MalformedAnswersError), `src/sextant/application/enrich/tools.py` (`.tradewind/` joins the jail-specific exclusions), `tests/architecture/test_agents_confinement.py` (confinement moves to `tradewind` importable only in agents/tradewind.py, positive control kept; `anthropic` importable NOWHERE — the removal pin), fixture ignore rules (+`.tradewind/`).
- Test: the scripted-fake set via Tradewind's public `backend_factories` seam (`FakeMessagesListChatModel` subclass with no-op `bind_tools`, injected through `LangchainBackend(profile, native, chat_model_factory=...)`).

**Interfaces:**
- Consumes: the unchanged `EnrichmentAgent` port; `ToolExecutor.definitions()/execute()`.
- Produces: `TradewindAgent(auth: Literal["subscription","api-key"], model: str, max_turns: int, session_store: Path | None)`. Spec-pinned mechanics: async handlers invoked `handler(**arguments)` wrapping `executor.execute`, one `asyncio.run` bridge; the nudge = the third identical `(name, canonical-json args)` call EXECUTES normally and its result gains one appended sentence: `\n\n[sextant] You have made this exact call three times. The result will not change; write your answers with what you have, or try a different call.`; termination is `max_tool_rounds` only (`session.stop()` never used); `end_reason` mapping per spec §1 including `"no_progress"` when the cap ends a nudged run; `partial_reason` vocabulary = {None, "stop:max_tokens", "max_turns", "no_progress"} and the port docstring amended to say vocabularies are adapter-defined; key read from `ANTHROPIC_API_KEY` by Sextant only, refusal names the variable pre-client; store: api-key → `<module>/.tradewind/sessions.sqlite` (mkdir first; `TradewindConfig.store`; `Path(":memory:")` opt-out), subscription → ephemeral; `history_scope` never passed (docstring states why); subscription's preset-APPEND divergence stated in the docstring.

- [ ] **Step 1: failing loop tests (scripted fake, no network)** — happy path (tool round-trip through OUR handler, in-band JSON out, `partial=False`); cap → `"max_turns"`; nudged-then-capped → `"no_progress"` and the nudge sentence present in that call's transcript entry; executor refusal strings continue the loop; a Tradewind failure → `EnrichmentAgentError`, nothing written; api-key store lands at the module-local path, subscription writes none; `--max-turns 25 --auth api-key` refused with the ceiling message; textless partial → the stage's loud named failure.
- [ ] **Step 2: failing jail + confinement tests** — `.tradewind/` invisible to all four tools; `tradewind` import confined with positive control; `anthropic` importable nowhere; registry refuses `claude-api` naming the known list; the lazy factory imports nothing until called (pin: `import sextant.agents` leaves `sys.modules` without `tradewind`).
- [ ] **Step 3: implement; delete claude-api; suite; hooks; commit** `feat: the Tradewind adapter — one sanctioned caller, honestly mapped`.

### Task 5: The library facade

**Files:**
- Create: `src/sextant/api.py` (four verbs, frozen result objects, the `SextantError` family), `tests/api/test_facade.py`.
- Modify: `src/sextant/cli/app.py` (command bodies become thin wrappers over the extracted composition — extraction only, no behavior change in this commit), `README.md` (the ten-line embedding example + the v1 contract: synchronous, quiet, not thread-safe per module, embedded enrich is api-key territory).
- Test: facade tests assert results and typed errors; THE EXISTING CLI SUITE UNCHANGED is the extraction's proof — any CLI test edit in this task is a review Critical.

**Interfaces:**
- Produces: `analyze(path, *, allow_resolve=False) -> AnalyzeResult(modules: tuple[ModuleOutcome, ...])`, `render(path) -> RenderResult(markdown: Path, html: Path)`, `enrich(path, *, agent="tradewind", auth="api-key", max_turns=None, dry_run=False, ingest=None) -> EnrichResult(overlay: Path | None, accepted: int, refused: int, partial_reason: str | None)`, `export(path) -> ExportResult(bundle: Path)`; every refusal raised as a `SextantError` subclass carrying the same message the CLI prints.
- Consumes: Task 4's adapter (sequenced after it — same composition path).

- [ ] **Step 1: failing facade tests** — analyze a fixture copy programmatically and assert the result object; a refused detection raises `SextantError` (not SystemExit) with the CLI's message; enrich dry-run returns the brief path; the api default auth is `api-key` (a library host has no login).
- [ ] **Step 2: extract; wrap; suite (CLI tests untouched and green); hooks; commit** `feat: sextant.api — the four verbs, embeddable`.

### Task 6: Flight, docs, roadmap

**Files:**
- Modify: `docs/components/D04-*.md` (the agent story rewritten: Tradewind, auth split, the preset-append divergence, the store + jail exclusion), `README.md` (usage), `docs/ARCHITECTURE.md` (DR-2 note names Tradewind), the roadmap (2N delivered row).
- The flight (a phase act, results in the task report, nothing committed): `enrich --agent tradewind --auth subscription` against `fixtures/orders-service` (the jms parse-binding question) and one petclinic module (a §2 config question) — acceptance: at least one verdict claim of EACH shape validates and renders beside its question.

- [ ] **Step 1: the flight; record results** (verdict engine exercised end to end for the first time — the counts and any refusals go in the report verbatim).
- [ ] **Step 2: docs, every sentence checked against shipped code; suite; hooks; commit** `docs: 2N — enrichment polish delivered`.

---

## Plan Self-Review (run before execution)

1. **Spec coverage:** §1→T4 (+stage ruling, cap, store, jail exclusion, confinement); §2→T1; §3→T2; §4→T3; §5→T6; §5b→T5; §6 boundaries respected (no codex/cursor, no history_scope, no engine changes); §7's pins distributed to their tasks. The e7eab1b gap-sentence fix already sits on the branch (rides with T6's docs commit narrative).
2. **Placeholder scan:** exact nudge sentence, ceiling message, default values, store path, result-object fields all stated; no TBDs.
3. **Type consistency:** `ConfigQuestionRef` fields (T1) = the brief's printed rows (T2) = the INSTRUCTIONS example (T3); `TradewindAgent` kwargs (T4) = the CLI flags and `sextant.api.enrich` signature (T5); `partial_reason` vocabulary consistent across T4's adapter, stage ruling, and T5's `EnrichResult`.
4. **Ordering:** T1→T2→T3 (schema→brief→teaching); T4 independent of them; T5 explicitly AFTER T4 (spec §5b's sequencing rule — same composition path, and its review treats any CLI change as Critical); T6 last, consuming everything.
