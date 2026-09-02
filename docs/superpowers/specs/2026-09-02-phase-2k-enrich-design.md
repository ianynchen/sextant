# Phase 2K — Enrich: the agentic overlay, redaction, and the ignore file

**Status:** approved in brainstorm 2026-09-02; this document records the design.
**Depends on:** 2B §6 (the overlay reservation), 2F/2G/2H (`open_questions` + doubtful-row
evidence), 2I (`.sextant.yml`), DR-2 (amended here, §8), D06 (`redaction_set_hash`).
**Roadmap row:** `sextant module enrich` — LLM-written sections as overlay claims at
`evidence: llm`; the verification seat; redaction-before-wire; first network dependency.
Closing this phase declares **milestone 2**: analyze → resolve → enrich → render →
export, nothing stubbed.

## The thesis

The machine half of the document is done; what remains is what machines cannot derive —
why components exist, how to extend them, how an algorithm works, and a diagram a human
can actually read. 2K adds those as an **agentic enrichment**: Sextant composes a brief,
an LLM agent searches the module through four jailed, redacting tools, and its answers
land as **add-only overlay claims at `evidence: llm`** that render assembles beside —
never inside — machine text. Two security surfaces ship first because the wire demands
them: **internal redaction** (which also closes a live exposure: `resolved_config`
values export verbatim today) and **`.sextantignore`**.

User rulings that shaped the design: the LLM call is wrapped behind a port
(`claude-api` adapter now, tradewind later; Codex/Cursor/humans ride the dry-run/ingest
door from day one); the agent gets tools and iterates (a tool-use loop, not one-shot);
the four content kinds are components + purposes, extension guides, algorithm
descriptions, simplified class/sequence diagrams; **add-only, clearly marked** —
LLM output never replaces machine output or even sections; redaction is built
internally and default-on; `.sextantignore` works like `.gitignore`; the overlay is a
**pure program artifact in JSON** — no human editing, so 2B §6's promote-or-correct
clause is retired for v1 (add-only made rank competition moot; recorded amendment);
model/agent selection via `--agent`/`--model` flags with `.sextant.yml` defaults and
the API key from the environment only.

## 1. Redaction — one redactor, three exits, default-on

A pure domain module (`domain/redaction.py`) applied wherever data crosses the trust
boundary: **render** (docs get shared), **export** (bundles leave by design), and the
**enrich tools' read path** (the wire). The workspace stays verbatim — analysis needs
real values locally, and the user's own disk is not the boundary.

- Built-in rules: key-pattern masking (`password`, `secret`, `token`, `credential`,
  `api[-_]?key`, `private[-_]?key`, `authorization`, `passphrase` — case- and
  format-insensitive against normalized config keys), URL userinfo stripping
  (`scheme://user:pass@host` → `scheme://host`), applied to `resolved_config` values,
  config-entry facts served by tools, and any endpoint column carrying an address
  expression. Masked values render as the stable marker `«redacted»` (byte-identity and
  comparability survive; a masked value still counts as present).
- `.sextant.yml` gains `redact:` — **additive only**: extra key patterns, extra value
  regexes. No reveal/unmask mechanism exists: configuration can widen redaction, never
  narrow it. Malformed sections refused loudly (Sextant's own input).
- `redaction_set_hash` — the sha256 of the effective rule set (built-ins + repo
  additions, canonically serialized) — finally gets its producer and lands in the D06
  manifest, as that field was designed for.
- Consequence stated: default-on redaction changes existing rendered docs and bundles
  (masked where verbatim); pins re-pin from live, and it is the right change.

## 2. `.sextantignore` — gitignore semantics, two layers

A root-level file with **git's own wildmatch semantics** — negation, dir-only
patterns, anchoring, `**` — implemented via the `pathspec` package (pinned; mirroring
git's behaviour exactly is the point, and hand-rolling those corners is the drift trap
DR-6 names). Clean split with `.sextant.yml`: the ignore file is *file-level* ("Sextant
does not read this, anywhere"); `redact:` is *value-level* (masking within files it
does read).

- Applies to every Python-side file enumeration: config readers, schema readers,
  resource walks, and the enrichment jail. One matcher utility in domain, applied at
  the walk sites.
- **Two layers, one safety rule**: built-in security patterns (`.env`, `.env.*`,
  `*.pem`, `*.p12`, `*.jks`, `id_rsa*`, `id_ed25519*`, `secrets/**`, `*.keystore`)
  sit beneath the repo's file and are **non-negatable** — a repo `!.env` cannot
  re-admit a credentials file into the jail. Within the repo's own patterns, full
  gitignore semantics including negation.
- Stated boundaries: root-level file only (nested per-directory files are a
  fast-follow if ever needed); the JVM extractor's `.class` walk is out of scope
  (ledgered, rarely wanted).

## 3. The port, the adapters, the CLI

**`EnrichmentAgent` port** (`application/ports/enrichment.py`): `run(brief) ->
EnrichmentAnswers`. The brief carries the composed prompt, the instructions document,
the tool *definitions*, and the jailed roots; the adapter drives whatever loop its
runtime uses, but **every tool call executes through Sextant's own executor** — the
foreign runtime maps our tools into its protocol; our code serves the bytes.

- **Adapters, registry-keyed** (`--agent`, unknown name refused with the known list):
  `claude-api` ships in v1 — a Messages-API tool-use loop (~100 lines, ours): model
  responds with tool requests, our executor runs them, results append, repeat until
  the model answers in-band or a cap trips. `max_turns` (default 50), a no-progress
  guard (identical call repeated → nudge, then end), and a full session transcript
  logged locally for audit. `claude-sdk` and `tradewind` are one-file additions later.
  The `anthropic` package is pinned and **import-confined to the adapter file** by
  structural test (the `google.protobuf` pattern). API key from `ANTHROPIC_API_KEY`
  only — never a flag, never config.
- **The universal door**: `--dry-run` writes the brief and calls nothing; any agent —
  Codex, Cursor, a human — works it with its own abilities; `--ingest answers.json`
  runs the identical validation and writes the identical overlay. Supporting a new
  tool costs zero Sextant changes. **Honesty note, stated in docs:** the redaction and
  jail guarantees are enforceable only when our loop drives; an external agent reads
  the repo under its own permissions — the user's own agent under the user's own
  control, which is DR-2's original stance, and the spec says so plainly.
- Flags: `--agent`, `--model` (adapter-interpreted, passed **verbatim** — provider
  model catalogs are not re-implemented; the provider errors loudly), `--max-turns`,
  `--dry-run`, `--ingest`. Repo defaults in `.sextant.yml` under `enrich:`; flags win.

## 4. The four tools and the jail

`list`, `find` (name patterns), `grep` (content), `read_file` (line-ranged,
size-capped) — all in-process, read-only, and jailed:

- **Path jail**: containment against an explicit allowlist of roots — the module
  source root, the fact root, and the rendered outputs. Never `$HOME`, never repo
  siblings, no symlink escape — and, since 2K Task 5's fix round 1, no symlink
  followed AT ALL: a path is visible only if it is the exact, case-included name of
  a real directory entry, reached without crossing a single symlink (root itself, an
  intermediate directory, or the final target). A caller-given path is verified
  against the real on-disk spelling segment by segment, never through the OS's own
  case-insensitive lookup, which a case-preserving-but-insensitive filesystem
  (macOS's default) would otherwise satisfy for the wrong case and hand back content
  no exclusion rule ever saw the real name of.
- **`.sextantignore` + built-ins enforced at the jail**: an ignored file is invisible
  to `list`/`find`/`grep` and unreadable by `read_file`. A derived-output directory
  (`target/`, `build/`, `out/`, `node_modules/`, `.git/`) is excluded the same way,
  as a JAIL-specific rule joining `.sextant-enrichment.json`'s own precedent — NOT
  added to `.sextantignore`'s built-in patterns, which stay the short, non-negatable
  credential layer; analysis walks are unaffected, since the jail describes
  human-authored source, never its compiled shadow. Exclusion ancestry is judged
  against a path's own MOST SPECIFIC jailed root, never an ancestor root that merely
  contains it too (2K Task 5 fix round 2): the ordinary layout nests the fact and
  render roots inside the module root, and judging against the wrong one would blank
  a module's own fact/render rows whenever its root happened to sit under a directory
  literally named `target`.
- **Nested roots, deduplicated**: the fact and render roots ordinarily sit inside the
  module root, so `find`/an unscoped `grep` walking every root independently would
  otherwise see a nested root's own files twice — 2K Task 5 fix round 2 dedupes by
  file identity.
- **One anchor, one spelling** (2K Task 5 fix round 4): every citation every tool
  prints is the file's path relative to ONE directory — the repository root the
  ignore rules were loaded for, which construction already proves contains every
  jailed root — so distinct files get distinct citations by construction and no raw
  host path can ever stand in for a name. A fact file therefore cites as
  `.sextant/facts/...`, its ancestor's spelling, rather than by its own root's;
  naming a file relative to whichever root contained it most specifically collided
  in three separate ways (nested roots, sibling roots, and a naming cache that went
  stale) before this replaced it. Resolution stays permissive — a caller-given path
  is walked from every jailed root and from the anchor — so every citation printed is
  a citation `read_file` and a scoped `grep` accept back unchanged.
- **Redaction-on-read**: config-bearing content passes the §1 redactor before entering
  a tool result — the only bytes that ever reach the wire are the brief Sextant
  composed and tool results that passed the redactor.
- No shell, no network, no write: answers return in-band, and **Sextant holds the
  pen** — it validates and writes the overlay itself. Tool descriptions are authored
  carefully once (the model's search strategy is only as good as they are).

## 5. The brief and the instructions

`enrich` requires a rendered workspace (§8's flow). The brief is deterministically
composed from: the machine-rendered `architecture.md`, `metadata.json` (gaps included),
the module's `open_questions` rows **verbatim**, a digest of `unresolved`/`narrowed`
endpoint and config rows with their recorded reasons (2F's doubtful evidence — already
in the workspace, no new dataset), and the four content requests. The **instructions
document** (`enrich/INSTRUCTIONS.md`, shipped inside Sextant, versioned, its hash in
the overlay provenance) teaches: what each Sextant artifact is and how to read it
(fact JSONL, rendered doc, metadata, open_questions), the four tools and search
strategy, the claim schema with one example per kind, and the three standing rules —
**cite what you read; elide but never invent; `unanswered` beats a guess.**

## 6. The overlay — `.sextant-enrichment.json`

A **pure program artifact**: written wholesale by `enrich` (or `--ingest`), read by
`render`/`export`, edited by no one. JSON — exact round-trips, no implicit typing;
schema-validated (pydantic) at every load, refusals loud. Lives at the module root
beside `.sextant.yml`, versionable in git (a PR diff shows what the claims changed —
reading a diff is not editing). Regeneration replaces the file entirely; its
provenance block states one run of one model against one graph
(`{model, agent, instructions_hash, redaction_set_hash, run_at, workspace_fingerprint}`).
`workspace_fingerprint` is the sha256 of `metadata.json`'s own bytes — informational,
never compared by code, and not a content-identity hash (D06's own per-row manifest
hash, Task 8, is the record for that).

Claim kinds (closed set):
- `component` — name, purpose, member **symbols that must exist**;
- `section` — prose (high-level design, extension guide, algorithm description), each
  citing the files it read;
- `diagram` — simplified mermaid class/sequence, with an explicit elision statement
  ("showing 8 of 23 classes; error paths elided"); every node/participant must
  validate against real symbols;
- `verdict` — §7.

Every claim: `evidence: llm`, a closed-set `anchor` (after-endpoint-table,
after-component-overview, beside-open-question, end-of-document), and nothing else
render needs to guess. **Validation by construction at ingest**: member symbols,
diagram nodes, cited files, and a verdict's question identity must exist — a claim
naming a phantom is refused with the reason, never written. **Staleness at render**:
a claim whose referents vanished on re-analyze renders as "N enrichment claims stale,
not shown" — visible, never silent; the file keeps the claim. **Add-only assembly**:
render interleaves claims at their anchors under a provenance header
("Enrichment — `evidence: llm`, model …"), deterministically placed, machine text
never touched or reordered. No overlay file → render behaves exactly as today.

## 6b. Dual output — markdown and HTML, diagrams you can actually read

**User-ruled:** render (and enrich's automatic assembly) emits BOTH
`architecture.md` (unchanged — mermaid fences, GitHub- and diff-friendly) and
`architecture.html`: the same content through the same deterministic assembly, one
templated HTML emitter. The HTML is **self-contained and offline**: a pinned,
vendored `mermaid.min.js` inlined into the file (no CDN — the doc must open
airgapped), plus a small vanilla pan-zoom script of our own (wheel zoom, drag pan,
`+`/`−`/`reset` controls on every diagram container — machine and LLM-simplified
diagrams alike). Determinism holds: the vendored asset's bytes are fixed (version +
license recorded beside it — a new asset class, pinned like a dependency, upgraded
deliberately), the template is stable, so same workspace + same overlay →
byte-identical HTML. Both files land in the rendered outputs and the bundle carries
both.

## 7. The verification seat

The brief carries every open question; the agent answers what it can ground:
a `verdict` claim anchors beside its question — "LLM assessment: likely `OrderProto`,
because `OrderIngest.java:41` parses it" — rendered with the label. **The graph is
immutable**: the row stays `unresolved`; no answer feeds resolve. The unanswerable
comes back `unanswered` with what was searched and why it was insufficient — the
honesty discipline extended to the model, enforced by the instructions and accepted
by validation (an `unanswered` verdict is a valid claim; it renders as such).

## 8. Architecture amendments and layering

- **DR-2, amended in place with an amendment note** (decision records append, never
  silently rewrite): the deterministic pipeline — analyze, resolve, render, export —
  never calls a model and stays under NFR-1 in full; `enrich` is the **one sanctioned
  caller**, behind the port, its output versionable overlay input validated by
  construction. Everything DR-2 protected survives: no invention (validation), no
  provider tree in the deterministic core (import-confined adapter), model churn
  decoupled (adapter + verbatim `--model`).
- **NFR-1, amendment note**: brief composition, answer validation, and overlay
  assembly are byte-deterministic (same workspace + same overlay → same document);
  only the agent call itself is excluded.
- **Flow, stated (user-ruled: no second render command)**: `analyze → render
  (machine doc) → enrich`. After validating and writing the overlay, **`enrich`
  performs the assembly itself** — it invokes the same deterministic render-assembly
  step internally and leaves the enriched document on disk; one command, done.
  `render` remains independently capable of assembling (a standalone `render` over a
  workspace with an overlay present produces the identical enriched document — same
  code path, so the two can never disagree), which is what re-renders a committed
  overlay after a later re-analyze. `enrich` still refuses a workspace with no
  rendered doc (the brief needs it — tell the user to render first, loudly, with the
  command).
- **Layering**: the adapter lives in a new outer group (`src/sextant/agents/`),
  importing no other outer group; the port in `application/ports`; the redactor and
  ignore matcher in `domain` (pure); import contracts extended accordingly.

## 9. Testing — the network never runs in tests

- `FakeEnrichmentAgent` drives every pipeline/CLI test; golden overlay files pin
  validation, staleness, and assembly (fixture-authored JSON is fine — it is a
  program format).
- The `claude-api` loop is unit-tested against a **scripted fake model** (a sequence
  of canned responses): tool dispatch, jail refusals, redaction-on-read, turn caps,
  the no-progress guard — all without network.
- One opt-in integration test for the real adapter, gated on `ANTHROPIC_API_KEY`
  presence, skipped otherwise (and skipped in the standard suite run).
- Redaction and ignore get their own unit suites plus live re-pins of render/export.

## 10. Fixtures, docs, CLI surface

Fixture: `.sextantignore` + a `redact:` addition in the fixture's `.sextant.yml`; a
planted fake-credential config row proving masking end-to-end (render, bundle, and a
tool-read all show `«redacted»`); a golden `.sextant-enrichment.json` exercising all
four claim kinds + one stale claim + one refused-at-ingest case. Docs: DR-2/NFR-1
amendment notes in ARCHITECTURE; D06 (`redaction_set_hash` produced; overlay in the
bundle story); D04/M-docs for the enrich stage; README (`enrich` usage, the two
doors, the key-from-environment rule, `.sextantignore`); COVERAGE untouched (enrich
adds no coverage rows); roadmap — 2K delivered, **milestone 2 declared**.

## 11. Boundaries, stated

External agents (dry-run/ingest) operate outside the jail/redaction guarantee — their
own permissions, the user's own control. No per-claim human suppression or promotion
in v1 (retired 2B §6 clause; revisit only on demonstrated need). Nested
`.sextantignore` files and extractor-walk ignoring are fast-follows. The overlay
never feeds resolve; only render consumes it. `system enrich` (cross-module) waits
for L. Instructions quality iterates by ordinary edits — its hash makes every
overlay say which version produced it. Every jail exclusion (`.sextantignore`, the
overlay, a derived-output directory) is PATH-SHAPED and content-blind: a copy of an
excluded file sitting somewhere none of those rules name — outside a derived-output
directory, under a different path than `.sextantignore` lists, or a hardlink included
(the same inode under another name, readable in full once the jail resolves its own,
un-excluded name for it) — still leaks, and that is a stated boundary rather than a
bug to chase further.

**Two mechanisms, two visibilities, both deliberate, ruled.** A derived-output directory
(`target/`, `build/`, `out/`, `node_modules/`, `.git/`) is hidden in the jail by the
directory's own path being excluded outright — the jail's ancestry rule covers the
directory itself, so nothing under it is ever walked to in the first place. `secrets/**`
hides differently: it is a `.sextantignore` pattern, so gitignore semantics decide what it
covers, and what it covers is *contents* — everything matching under `secrets/`, not the
directory name as a standalone entity the way the jail's own rule treats a derived-output
name. The two answer different questions (a jail-specific exclusion the model must never
even see the existence of, versus a file-level ignore rule a repository writes and a
negation could in principle touch, were the built-in layer negatable) and neither is a
weaker version of the other.
