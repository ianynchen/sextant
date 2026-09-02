# Phase 2K — Enrich Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `sextant module enrich` — an agentic LLM overlay (components, extension guides, algorithm descriptions, simplified diagrams, verification verdicts) added onto machine output with `evidence: llm` labels; redaction and `.sextantignore` shipped first; dual markdown/HTML output with pan-zoom diagrams; milestone 2 (analyze → resolve → enrich → render → export, nothing stubbed).

**Architecture:** Security surfaces first (one redactor at three exits; gitignore-semantics ignore file at every Python-side walk). The overlay is a pure program artifact (`.sextant-enrichment.json`) validated by construction and assembled add-only by render — all agent-independent and testable with golden files. The agent side is a port (`EnrichmentAgent`) + a `claude-api` tool-use loop adapter in a new `agents/` outer group, driving four in-process jailed redacting tools; `enrich` composes the brief, runs the agent (or `--dry-run`/`--ingest`), validates, writes the overlay, and auto-assembles both output formats.

**Tech Stack:** Python (new pinned deps: `pathspec`, `anthropic` — the latter import-confined to one adapter file), pydantic schemas, vendored `mermaid.min.js` (pinned asset + license), vanilla pan-zoom JS (ours), DuckDB workspace reads.

**Spec:** docs/superpowers/specs/2026-09-02-phase-2k-enrich-design.md

## Global Constraints

- **No version bumps** (SEXTANT_VERSION/FACT_SCHEMA_VERSION/GRAPH_SCHEMA_VERSION frozen; no extractor changes this phase).
- **DR-2 as amended (§8)**: the deterministic pipeline never calls a model; `enrich` is the one sanctioned caller behind the port. **NFR-1 as amended**: brief composition, validation, and assembly are byte-deterministic; only the agent call is excluded. Double-run byte-identity over every deterministic output incl. `architecture.html`.
- **The network never runs in tests**: `FakeEnrichmentAgent` + scripted-fake-model loop tests; ONE opt-in integration test gated on `ANTHROPIC_API_KEY`, skipped otherwise.
- **Redaction can widen, never narrow**; built-in ignore patterns are non-negatable; API key from environment only (never flag, never config); no shell/network/write tools; answers in-band; Sextant holds the pen.
- **Add-only**: LLM content never replaces or edits machine text — new labeled sections at closed-set anchors only.
- **Validation by construction**: a claim naming a phantom symbol/file/question is refused at ingest, never written; staleness at render is visible, never silent.
- **Honesty rules travel to the model** (instructions): cite what you read; elide but never invent; `unanswered` beats a guess.
- Exact-list pins from live fixture runs only; suite baseline 1008 passed/1 skipped; hooks pass; uv.lock untracked; comments state constraints; no adjacent refactors; framework/provider names confined (`anthropic` to its adapter; no provider word in application/domain).

## File Structure

| File | Responsibility |
|---|---|
| `src/sextant/domain/redaction.py` (+ `.sextant.yml` `redact:` in `ingress/read/sextant_config.py`) | T1: one redactor, rule set + hash |
| `src/sextant/egress/render/*`, `egress/export/manifest.py` | T1: redaction at render/export; `redaction_set_hash` produced |
| `src/sextant/domain/ignorefile.py` + walk sites (`stages/analyze.py`, readers) | T2: `.sextantignore` via pathspec, builtins non-negatable |
| `src/sextant/domain/enrichment.py` | T3: overlay schema (pydantic), claim kinds, anchors |
| `src/sextant/application/enrich/validate.py` | T3: validation-by-construction + staleness |
| `src/sextant/egress/render/document.py` (+ assembly module) | T3: add-only assembly at anchors with labels |
| `src/sextant/egress/render/html.py` + `egress/render/assets/{mermaid.min.js, panzoom.js, LICENSE-mermaid}` | T4: HTML emitter, vendored assets, controls |
| `src/sextant/application/enrich/tools.py` | T5: list/find/grep/read_file, jail, redaction-on-read |
| `src/sextant/application/ports/enrichment.py`, `src/sextant/agents/claude_api.py` (+ registry) | T6: port + loop adapter, agents/ outer group, contracts |
| `src/sextant/application/enrich/brief.py`, `src/sextant/enrich/INSTRUCTIONS.md`, `cli/app.py` | T7: brief, instructions, CLI verb, doors, auto-assembly |
| ARCHITECTURE (DR-2/NFR-1 notes), D04/D06/M-docs, README, roadmap | T8: docs + milestone 2 |

### Task order and why

Security first (redaction gates the wire; ignore gates the jail); overlay+assembly and HTML next (agent-independent, testable with golden files — the render side is DONE before any agent exists); tools, then the loop that calls them; the CLI stitches; docs declare milestone 2.

---

### Task 1: Redaction — one redactor, three exits

**Files:**
- Create: `src/sextant/domain/redaction.py`
- Modify: `src/sextant/ingress/read/sextant_config.py` (the `redact:` section), `src/sextant/egress/render/document.py` + `metadata.py` (values pass the redactor), `src/sextant/egress/export/manifest.py` (produce `redaction_set_hash`), whatever export path emits `resolved_config` (masked values), `fixtures/orders-service/src/main/resources/application.yml` (+ a planted fake credential row `orders.db.password: hunter2-fixture`), fixture `.sextant.yml` (`redact:` addition)
- Test: `tests/domain/test_redaction.py`, live re-pins across render/export tests

**Interfaces:**
- Produces: `Redactor.from_rules(builtins + repo_additions)` with `redact_value(key, value) -> str`, `redact_text(text) -> str` (URL userinfo + value-regex application), `rule_set_hash: str` (sha256 over canonical serialization). Consumed by T5 (tools) and the two egress exits.

- [ ] **Step 1: failing unit tests** — key patterns (`password`, `secret`, `token`, `credential`, `api-key`/`api_key`/`apiKey`, `private-key`, `authorization`, `passphrase`; case/format-insensitive against normalized keys — reuse 2F's `normalize_key`); non-matching keys untouched; URL userinfo stripped (`https://u:p@h/x` → `https://h/x`) wherever values are URLs; masked marker exactly `«redacted»`; repo additions widen (extra key pattern, extra value regex); malformed `redact:` refused loudly; hash stable across dict ordering, changes when a rule changes.
- [ ] **Step 2: implement + wire the exits.** Render: `resolved_config`-derived lines and any address expression column pass `redact_value` before formatting. Export: the `resolved_config` table's `value` column masked at export time (workspace stays verbatim — mask in the export SELECT or a projection, state which); manifest gains `redaction_set_hash` (the reserved field finally produced — read `egress/export/manifest.py:26`'s comment first).
- [ ] **Step 3: fixture + live pins** — the planted credential renders `«redacted»` in `architecture.md`, exports masked in `resolved_config.parquet`, while a non-secret value (`soap.billing.uri`) stays verbatim; `redaction_set_hash` present in the manifest and changes when the fixture's `redact:` addition changes. Expect broad mechanical re-pins (masked where verbatim) — from live output only. Double-run identity.
- [ ] **Step 4: full suite, hooks, commit** `feat: redaction — one redactor at the render and export exits`.

### Task 2: `.sextantignore`

**Files:**
- Create: `src/sextant/domain/ignorefile.py`, `fixtures/orders-service/.sextantignore`
- Modify: `pyproject.toml` (`pathspec`, pinned), `src/sextant/application/stages/analyze.py` + reader walk sites (config/schema/resource enumerations filter through the matcher)
- Test: `tests/domain/test_ignorefile.py`, `tests/application/test_analyze_ignore.py`

**Interfaces:**
- Produces: `IgnoreRules.load(repo_root)` → `.matches(path) -> bool`; `BUILTIN_PATTERNS` (non-negatable: `.env`, `.env.*`, `*.pem`, `*.p12`, `*.jks`, `id_rsa*`, `id_ed25519*`, `secrets/**`, `*.keystore`). Consumed by every walk + T5's jail.

- [ ] **Step 1: failing tests** — gitignore semantics via pathspec (negation among repo patterns, dir-only `build/`, anchoring, `**`); builtins match with NO `.sextantignore` present; a repo `!.env` does NOT re-admit (builtins evaluated separately, non-negatable — implement as two layers, builtin match short-circuits); missing file → builtins only; malformed lines behave as git behaves (pathspec's own semantics — don't invent stricter).
- [ ] **Step 2: wire the walks** — an ignored config/schema/resource file is never read (test: an ignored `application-secret.yml` contributes zero config entries; an ignored `.wsdl` contributes zero shapes); fixture `.sextantignore` ignores a planted decoy file, live-pinned.
- [ ] **Step 3: full suite (pins for the decoy), hooks, commit** `feat: .sextantignore — gitignore semantics over every read surface`.

### Task 3: The overlay — schema, validation, add-only assembly

**Files:**
- Create: `src/sextant/domain/enrichment.py`, `src/sextant/application/enrich/__init__.py` + `validate.py`, `fixtures/orders-service/.sextant-enrichment.json` (golden: all four claim kinds + one claim that will be stale + provenance block)
- Modify: `src/sextant/egress/render/document.py` (assembly at anchors)
- Test: `tests/domain/test_enrichment_schema.py`, `tests/application/test_enrich_validate.py`, `tests/egress/test_render_assembly.py` + live pins

**Interfaces:**
- Produces: pydantic models — `EnrichmentOverlay {produced_by: Provenance, claims: list[Claim]}`; `Claim` = discriminated union on `kind ∈ {component, section, diagram, verdict}`; every claim has `evidence: Literal["llm"]`, `anchor ∈ {after-endpoint-table, after-component-overview, beside-open-question, end-of-document}`; `component{name, purpose, members: [symbol]}`, `section{title, body, cites: [path]}`, `diagram{mermaid, elides: str}`, `verdict{question: {protocol, method, path, kind}, assessment, because}` (or `assessment: "unanswered", searched: str`). `validate_overlay(overlay, workspace, repo_root) -> (accepted, refusals)`; `stale_claims(overlay, workspace) -> [...]`. Consumed by T4 (html renders same assembly), T7 (ingest/write).

- [ ] **Step 1: failing schema tests** — round-trip JSON; unknown kind/anchor refused; missing fields refused; `evidence` must be `llm`.
- [ ] **Step 2: failing validation tests** — component member not in `symbols` → refused with reason; diagram node not a real symbol → refused (parse mermaid participants/classes textually — a conservative identifier scan; document the extraction rule); `cites` path not in repo → refused; verdict question not in `open_questions` → refused; `unanswered` verdict valid; refusals carry claim index + reason.
- [ ] **Step 3: failing assembly tests** — claims interleave at anchors under a provenance header (`> **Enrichment — evidence: llm** (model …)`); machine text byte-untouched around them; deterministic ordering (anchor order, then claim order in file); no overlay → output byte-identical to today (regression pin); stale claim → excluded + "1 enrichment claim stale, not shown" line; live pin with the golden fixture overlay.
- [ ] **Step 4: implement; full suite; hooks; commit** `feat: the enrichment overlay — schema, validation, add-only assembly`.

### Task 4: Dual output — the HTML emitter

**Files:**
- Create: `src/sextant/egress/render/html.py`, `src/sextant/egress/render/assets/mermaid.min.js` (pinned version, downloaded once at dev time — record version + sha256 + license in `assets/LICENSE-mermaid` and a README note), `assets/panzoom.js` (ours, ~60 lines: wheel zoom, drag pan, +/−/reset buttons per diagram container)
- Modify: render entry to emit both files; export bundle carries both
- Test: `tests/egress/test_render_html.py` + double-run byte-identity + live pins

**Interfaces:**
- Consumes: the same assembled document model T3's assembly produces (markdown emitter and HTML emitter share the assembled section list — one assembly, two serializers; do NOT parse the markdown to make HTML).
- Produces: `architecture.html` — self-contained (assets inlined), every mermaid block in a `<div class="diagram">` with controls, prose escaped properly.

- [ ] **Step 1: failing tests** — HTML contains the inlined mermaid source + panzoom script exactly once; each diagram wrapped with the three controls; machine and enrichment sections present with the enrichment label rendered as a visible badge; byte-identical across two renders; no CDN/network URL anywhere in the file (grep pin); `architecture.md` unchanged by this task (byte pin).
- [ ] **Step 2: implement** (stable template, stdlib `html.escape`; assets read from package data). Asset provenance: exact mermaid version pinned in a constants module + LICENSE file; a test pins the asset's sha256 so an accidental swap fails loudly.
- [ ] **Step 3: bundle carries both files; live pins; suite; hooks; commit** `feat: dual output — self-contained HTML with pan-zoom diagrams`.

### Task 5: The four tools and the jail

**Files:**
- Create: `src/sextant/application/enrich/tools.py`
- Test: `tests/application/test_enrich_tools.py`

**Interfaces:**
- Consumes: T1 `Redactor`, T2 `IgnoreRules`.
- Produces: `ToolExecutor(roots: tuple[Path, ...], redactor, ignore)` with `definitions() -> [ToolDefinition]` (name, description, JSON schema for args) and `execute(name, args) -> str`; tools `list_dir{path}`, `find{pattern}`, `grep{pattern, path?}`, `read_file{path, start?, end?}`. Deterministic outputs (sorted), result size caps (state exact: e.g. 64KB per result, 400 lines per read default), every call+result appended to a transcript list the caller can persist.

- [ ] **Step 1: failing jail tests** — `realpath` containment post-resolution (a symlink inside a root pointing outside → refused); `../` traversal refused; absolute path outside roots refused; ignored file invisible to list/find/grep AND unreadable (builtin `.env` + repo pattern both); refusals are tool-result errors (the model sees "refused: outside the allowed roots"), never exceptions.
- [ ] **Step 2: failing behavior tests** — read_file line-ranging + cap; grep across roots with match limits; find by glob; **redaction-on-read**: reading the fixture's `application.yml` returns `«redacted»` for the planted credential (config-bearing detection: extensions the config readers claim — reuse that registry knowledge, state the rule); non-config files pass through un-redacted except `redact_text` URL-userinfo stripping (state: applied to ALL tool results — cheap and safe).
- [ ] **Step 3: implement; suite; hooks; commit** `feat: enrich tools — four jailed, redacting, read-only tools`.

### Task 6: The port and the claude-api loop

**Files:**
- Create: `src/sextant/application/ports/enrichment.py` (`EnrichmentBrief`, `EnrichmentAnswers`, `EnrichmentAgent` Protocol, `AGENT_REGISTRY`), `src/sextant/agents/__init__.py`, `src/sextant/agents/claude_api.py`, `tests/architecture/test_agents_confinement.py`
- Modify: `pyproject.toml` (`anthropic`, pinned), import-linter contracts (`agents` is an outer group importing no other outer group), `tests/architecture` allowlist (anthropic only in `agents/claude_api.py` + positive control)
- Test: `tests/agents/test_claude_api_loop.py` (scripted fake model), the architecture tests

**Interfaces:**
- Consumes: T5 `ToolExecutor`.
- Produces: `EnrichmentAgent.run(brief: EnrichmentBrief, executor: ToolExecutor) -> EnrichmentAnswers` (answers = the raw JSON text the model returned in-band + the transcript). `ClaudeApiAgent(model: str, max_turns: int)` — the Messages-API tool-use loop: send system(instructions)+user(brief) with `executor.definitions()`; while the response requests tools and turns remain: execute via `executor`, append results, repeat; the final text block is the answers. No-progress guard: identical (name, args) three times → inject a nudge message once, then end run with what exists. Transcript persisted by the caller (T7) to the workspace (`enrich-transcript.jsonl`).

- [ ] **Step 1: failing loop tests with a scripted fake transport** (patch the adapter's single `_send` seam; never the network): happy path (two tool rounds then answers); max_turns cap ends with partial answers marked; no-progress guard fires; tool-executor errors flow back as tool results (loop continues); API errors surface as a loud, typed failure (enrich reports, nothing written).
- [ ] **Step 2: architecture tests** — `agents` imports no ingress/egress; `anthropic` import-confined with positive control; contracts file updated (5th contract or extended group list — follow `.importlinter`'s format).
- [ ] **Step 3: implement; suite; hooks; commit** `feat: EnrichmentAgent port and the claude-api tool-use loop`.

### Task 7: The brief, the instructions, the CLI verb

**Files:**
- Create: `src/sextant/application/enrich/brief.py`, `src/sextant/enrich/INSTRUCTIONS.md`, `src/sextant/application/stages/enrich.py`
- Modify: `src/sextant/cli/app.py` (the `enrich` command + `.sextant.yml` `enrich:` defaults via `sextant_config.py`), `tests/e2e` (FakeEnrichmentAgent end-to-end), one opt-in `tests/integration/test_claude_api_live.py` (skipped without `ANTHROPIC_API_KEY`; also excluded from the default suite run — follow how the suite marks slow/optional tests, or add a marker)
- Test: `tests/application/test_enrich_brief.py`, `tests/cli/test_enrich_command.py`

**Interfaces:**
- Consumes: T3 validate/assembly, T4 html, T5 tools, T6 port.
- Produces: `compose_brief(workspace, module_root, instructions) -> EnrichmentBrief` — deterministic: the machine-rendered `architecture.md`, `metadata.json` (gaps), `open_questions` rows verbatim, the unresolved/narrowed rows digest with reasons, the four content requests, the closed anchor list. The stage: refuse-if-unrendered (loud, names the command) → compose → agent (or doors) → validate (refusals reported, claim-indexed) → write `.sextant-enrichment.json` (wholesale, provenance block with model/agent/instructions_hash/redaction_set_hash/run_at/workspace fingerprint) → **auto-assemble both `architecture.md` and `architecture.html`** (the same assembly render uses — user-ruled, no second render). Doors: `--dry-run` writes `enrich-brief.json` + instructions copy, calls nothing; `--ingest answers.json` validates identically. Flags `--agent/--model/--max-turns` with `.sextant.yml` `enrich:` defaults, flags win; key from env only (adapter refuses loudly if absent, naming the variable).

- [ ] **Step 1: failing brief tests** — deterministic bytes given a workspace; contains the open_questions verbatim + the digest; instructions hash recorded.
- [ ] **Step 2: failing CLI tests with FakeEnrichmentAgent** — happy path writes overlay + BOTH outputs assembled (pin the enrichment section present in md and html); refusals reported and refused claims absent from the file; `--dry-run` writes the brief and nothing else; `--ingest` path; unrendered workspace refused; unknown `--agent` refused with the known list; defaults-from-config with flag override.
- [ ] **Step 3: INSTRUCTIONS.md** — the artifact guide (fact JSONL, rendered doc, metadata, open_questions formats), the four tools + search strategy, the claim schema with ONE example per kind (verbatim JSON), the three standing rules (cite what you read; elide but never invent; `unanswered` beats a guess). Its sha256 is the `instructions_hash`.
- [ ] **Step 4: the opt-in live test** (one small module, asserts only: valid overlay written, ≥1 accepted claim, transcript exists — no content assertions; models vary). Suite; hooks; commit `feat: sextant module enrich — the agentic overlay, end to end`.

### Task 8: Docs — amendments and milestone 2

**Files:**
- Modify: `docs/ARCHITECTURE.md` (DR-2 + NFR-1 **amendment notes appended, never rewrites**), `docs/REQUIREMENTS.md` (NFR-1 note), `docs/components/D06-*` (redaction_set_hash produced; overlay + html in the bundle story), D04/M-docs (the enrich stage, the agents group), `README.md` (enrich usage, the two doors, key-from-env, `.sextantignore`, redaction), roadmap (2K delivered; **milestone 2 declared** — analyze → resolve → enrich → render → export, nothing stubbed)
- Test: suite green (docs only)

- [ ] **Step 1**: every sentence checked against shipped code (the standing discipline — a false doc sentence is a Critical); the external-door honesty note (jail/redaction enforceable only when our loop drives) lands in README + D04.
- [ ] **Step 2**: commit `docs: 2K — enrich delivered, milestone 2`.

---

## Plan Self-Review (run before execution)

1. **Spec coverage**: §1→T1, §2→T2, §3→T6+T7 (registry/flags/doors), §4→T5, §5→T7 (brief+instructions), §6→T3, §6b→T4, §7→T3's verdict kind + T7's brief, §8→T6 (layering) + T7 (flow) + T8 (amendment notes), §9→every task's fake-first testing + T7's opt-in live test, §10→fixtures spread across T1-T4 + T8 docs, §11 boundaries→T8. The three user amendments all have homes: auto-assembly (T7), dual output (T4), JSON program artifact (T3).
2. **Placeholder scan**: clean — caps and patterns carry exact values; the one dev-time action (downloading the pinned mermaid asset) states what gets recorded (version, sha256, license).
3. **Type consistency**: `Redactor`/`IgnoreRules` (T1/T2) consumed by T5 by those names; `ToolExecutor.definitions()/execute()` (T5) consumed by T6; `EnrichmentBrief/Answers/Agent` (T6) consumed by T7; `validate_overlay` (T3) consumed by T7; the assembly model shared T3→T4.
4. **Known risks, stated**: mermaid asset size (~1.5MB inlined — acceptable for a doc, stated); the diagram-node validation is a conservative textual scan (exact rule documented in T3); config-bearing detection for redaction-on-read reuses the reader-extension registry (T5 states the rule).
