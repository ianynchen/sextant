# M09 — Query

## Purpose

Answer structural questions about a workspace.

This is the module the agent requirement rests on. Its consumers are a person at a terminal
and an agent in a loop, and the second one shapes almost every decision below.

## Interface

```
Query
  find(term, scope)              -> [Symbol]
  answer(named_query, args)      -> Answer
```

Queries are **named and shipped as part of the schema** ([D01](D01-graph-schema.md)), not
written by each consumer. [M07](M07-renderer.md) uses the same ones. If the renderer wrote
its own reachability query, a document and a query would eventually disagree about the same
graph, and there would be no way to say which was right.

## Inputs

The graph at module or system scope. Nothing else — no code, no facts, no re-analysis.

## Output

Answers, as text for a terminal and JSON when piped.

## Behaviour

### The questions

| Question | Answers |
|---|---|
| `find` | Which symbols match these words? |
| `source` | Which file and lines hold this? |
| `callers`, `callees` | One hop, either direction |
| `implementations` | Which types implement this? **Where the candidate set surfaces.** |
| `uses` | What references this **type**? |
| `impact` | If this changes, what is affected? |
| `path` | How does A reach B? |
| `endpoint list`, `find`, `match`, `trace` | The boundary questions |

**`uses` and `callers` are different questions**, and the difference is why the four
type-reference edge kinds are kept. `callers` follows call edges and asks about functions.
`uses` follows type references and asks about a type. For a payload class, `uses` is the
useful one.

**`source` looks trivial and is not.** It is what makes the index usable: an agent asks a
structural question, gets identifiers, then asks where to read. Without it the agent has
structure it cannot act on.

### Impact crosses service boundaries through shapes, not calls

At system scope the graph is **federated** — the workspace holds `links` and `participants`
natively and reads each participant's tables from its bundle
([D01](D01-graph-schema.md)). So a query can follow a change out of one service and into
another:

```
  Money#amount → shape_fields → endpoints → links
               → the inbound endpoint on the far side
               → its handler symbol → local edges there
```

**Services exchange payloads, not method calls**, so the crossing is through shapes. A
traversal that followed only call edges would stop at every boundary.

The join needs no mapping layer: a symbol identifier carries package and version, so the same
library type is the same string in every participant. Where two services use different
versions the symbols differ, correctly — and that divergence is worth reporting rather than
papering over.

**A bundle unreachable at query time fails, naming it.** Returning a shorter answer would be
indistinguishable from finding less.

### `impact` returns three partitions, never a count

| Partition | Reachable through |
|---|---|
| **Definite** | `resolved` edges only |
| **Possible** | `narrowed` or `partial` edges, with candidates shown |
| **Unknown regions** | The `unresolved` sites hit on the frontier, each with file, line and reason |

The third is the most valuable part. It is the list of places a person has to go and look,
because the tool could not. A report that omits it looks complete and is not — and a blast
radius that can be depended on is not a number, it is a report with its own gaps named.

### `path` returns a subgraph, not a list of routes

Counting all routes between two symbols is exponential — every diamond in the call graph
doubles the count, and enterprise service code is full of diamonds. Any cap would truncate
the wrong ones.

So `path` returns the **union of every route** as a subgraph. Every route is present,
nothing is dropped, and the size grows with edges rather than with routes.

### Addressing

Approximate input, prefixed exact output. Several matches print the matches and stop.

Never bare hexadecimal, because identifiers get pasted into YAML files and spreadsheets that
coerce them to numbers.

### Filtering

Accessors, generated members, and symbols of third-party origin are hidden by default —
origin is the tier recorded at extraction, never a package-name pattern —
because they are noise in every answer. `--include-noise` turns the filter off.

**Every filtered answer states what it hid.** An answer that silently omits calls is the
same lie as a diagram that silently omits steps.

### Word search before structured search

Full text over display names, documentation, string literals and endpoint paths, plus
identifiers split on case and underscore. People and agents search in words before they
query in structure.

**The string-literal index is the root-cause path**: paste a log line, find the literal, find
its enclosing symbol, walk upward to the endpoints that reach it. Three queries.

## What it must not do

- **No analysis.** If a question cannot be answered from the graph, the answer is that it
  cannot, not a computation invented here.
- **No re-analysis.** A stale workspace is reported as stale, never silently refreshed.
- **No prose.** Structural answers only. What code is *for* is an overlay.
- **No private queries.** Anything used by more than one consumer is a named query in the
  schema.
- **No dead-code verdict.** Reachability is a query; the judgement that something is dead is
  a finding, and [M04](M04-resolver.md) withholds it where unresolved sites exist in scope.

## Honesty obligations

- Every answer carries the resolution tiers of the edges it traversed.
- Every answer names the commit the workspace was built from.
- An answer from a **partial** workspace says so.
- An answer that is empty because a filter removed everything says that, rather than
  reading as "nothing found".
- `impact` always shows the unknown-regions partition, even when it is empty — an empty one
  is a strong statement, and its absence would be indistinguishable from omission.

## Open decisions

| Decision | Blocks |
|---|---|
| Whether an agent reaches this through a served protocol as well as the command line | The agent surface |
| Whether `impact` follows shapes across service boundaries by default, or only when asked | Cost at system scope |
| Whether raw SQL is exposed alongside the named queries | Support burden |
| Whether answers are paginated, and how an agent learns there is more | Large result sets |
