# Spotify Portal's `shunt` plugin, and the query surface it suggests for Sextant

Research date: 2026-09-18. Sextant snapshot: `36c1d26`. Plugin snapshot:
[spotify/portal-ai-plugins](https://github.com/spotify/portal-ai-plugins) `main`, last
commit 2026-08-17; marketplace v0.1.0, `shunt` v0.2.0.

**Status: recorded as a deferred enhancement in [PROJECT.md](../PROJECT.md) § Deferred.
Gated (ruled 2026-09-18) on full support for Java/Kotlin, Go, Rust, Python and
TypeScript/JavaScript. No design has been done.**

## What the plugin is

Not about Spotify the music product. The repository is a Claude Code (also Codex and
Cursor) plugin marketplace wrapping **Portal by Spotify**, Spotify's commercial
Backstage-based developer portal, so a coding agent can query a company's software catalog
from the terminal. Two plugins ship:

- **`portal`** — six skills, each a thin wrapper over `npx @spotify/portal-cli`: `setup`,
  `doctor` (read-only readiness), `search` (catalog and TechDocs), `service` (owner,
  on-call, runbook, build/deploy/incident status), `actions` (discover and invoke Portal
  actions, `--dry-run --json` before any mutation, execute only after the user
  authorizes), `feedback`.
- **`shunt`** — routes I/O-heavy agent work to a cheaper model. The Spotify Engineering
  post of 2026-09-03 ([Portal by Spotify cut my Claude Code token usage by 90%](https://engineering.atspotify.com/2026/9/portal-by-spotify-cut-my-claude-code-token-usage-by-90))
  measured 82–94% token savings on bulk reads against a 162K-line Java monorepo.

## How `shunt` saves tokens

The saving is about *whose context* a file enters.

Without it, the agent's `Read` of a 4,000-line file pastes ~34,000 tokens into the
expensive model's context, where they are re-sent on every later turn. With it:

1. A `PreToolUse` hook on `Read` (and on `Bash` for `cat`/`head`/`tail`/`less`) refuses a
   full read of any file over 350 lines and tells the agent to use `bulk-read` instead.
   Targeted reads — offset/limit, pipes, redirections — pass through.
2. `bulk-read --question … --paths …` sends the files and the question to a cheap worker
   model (an "AiKA mode": named instructions + model + temperature, resolved server-side
   through the Portal CLI's actions registry). The worker returns terse structured
   bullets. Only those ~800 tokens enter the expensive model's context.
3. `code-write --spec … --reference … --target …` runs the other way: the worker generates
   boilerplate matching a reference file and writes it to disk, so the generated code never
   enters the expensive model's context at all.

Every call is one-shot and stateless. Skills tell the agent when *not* to delegate:
debugging, editing (the summary loses line precision), small files (10–30 s round trip
outweighs the saving), architectural decisions. 51 evals cover the hooks and transport
without Portal access.

## Why it matters to Sextant

`shunt` still pays a model to read the file, every time, and hands the agent a *summary*
it has to trust. Sextant read the module once, deterministically, and stored what it found
in a DuckDB workspace. The question `shunt` sends to a worker — "which methods write to
the database?" — is a query against tables that exist today:

```sql
SELECT caller, target, terminal_kind, target_kind
FROM call_edges
WHERE terminal_kind = 'persistence' AND target_kind = 'database';
```

(`src/sextant/storage/duckdb/schema.sql:569`; `symbols.line_start`/`line_end` at line 756
give the exact range to read.)

Two things the graph does that a worker model cannot:

- **Turn a whole-file read into an exact small read.** `source` returns the method's line
  range on the trace, so the read that remains is the right 40 lines, not 4,000 — the same
  saving, with no summary in between and no worker tokens.
- **Answer structural questions with no read at all** — callers, callees, implementations,
  uses, impact, path between two symbols, trace from an endpoint, who consumes a shape,
  who reads a config key. A model reading files answers these badly at any price.

What the graph does not replace: "what does this method actually do" — the conditions and
arithmetic inside it. That still needs source; the honest claim is that Sextant makes that
read small and exact. Going further — stating the business rules on a trace — is the
separate deferred item in [codetospec-comparison.md](codetospec-comparison.md).

## Where this stands in the repository

This is [M09 Query](../components/M09-query.md), "the module the agent requirement rests
on" — designed, not built. Nine of the ten named queries in
[D01 §5](../components/D01-graph-schema.md) do not exist; `trace_of` is a Python function
with no CLI and no rendered consumer; there is no `sextant module query` verb.
[suggestions.md](../suggestions.md) §3a and §6.6 argued for the same surface in July 2026.

`shunt` supplies the delivery shape that was missing: a coding-agent plugin with a skill
("ask Sextant before you read") and, optionally, a `PreToolUse` hook that answers a large
`Read` with what the graph knows about the file and the line ranges that matter.

## When the gate opens — the questions a design must settle first

Recorded so the brainstorming does not start from zero. Not decisions.

- First surface: CLI verb (`sextant module query <module> <named-query> --json`) or an MCP
  server. The plugin can wrap either.
- Whether the hook *blocks* a large read and redirects, as `shunt` does, or only *advises*
  with the graph's answer attached.
- Which named queries ship first. The smallest end-to-end slice is `source`, `callers`,
  `callees`, `trace` over the existing DuckDB.
- Multi-language: the surface must be language-blind (GUIDELINES: behaviour selected by
  declared extractor capability, never by language), which is why the gate is full
  language coverage — a query surface designed against one extractor's facts will encode
  that extractor's shape.

Deviations: none.
