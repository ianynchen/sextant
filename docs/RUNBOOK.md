# RUNBOOK

Lessons learned on this project. Read before starting a task; add to it when something
costs time that a note would have saved.

One entry per lesson. State what went wrong, and what to do instead.

---

## Documentation and diagrams

### Mermaid reserves `graph` as an identifier

A node named `graph` fails to parse:

```
    store[(Derived graph)]     ← works
    graph[(Derived graph)]     ← Parse error … got 'GRAPH'
```

`end`, `subgraph`, `class` and `click` are also reserved. Prefer a short unambiguous
identifier and put the words in the label.

### Verify Mermaid by rendering it, not by reading it

Two diagram bugs reached a file in this project because they looked correct. Render before
claiming a diagram works:

```bash
npx @mermaid-js/mermaid-cli -i diagram.mmd -o out.svg
```

Puppeteer ships no browser here. Point it at the installed one:

```bash
export PUPPETEER_EXECUTABLE_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

### Keep Mermaid labels plain

Quoted labels, `<br/>`, quoted subgraph titles and parallelogram shapes with quotes inside
are all rejected by some renderers. Plain unquoted labels using only letters, digits, spaces
and hyphens, with `[]` and `[()]` shapes, work everywhere.

### VS Code does not render Mermaid on its own

Its built-in Markdown preview shows nothing. It needs an extension:

```bash
code --install-extension bierner.markdown-mermaid
```

Check this before debugging diagram syntax. GitHub renders Mermaid natively.

---

## Design discipline

### Derive the fact set from the deliverables, never the other way round

A graph built facts-first ends up with **most of its edges having no consumer at all** —
produced because they seemed natural, read by nothing. The cause is always the same: facts
produced first, consumers assumed to arrive later. They do not arrive.

Before adding a fact kind or an edge kind, name the requirement that consumes it. This is
NFR-6, and it is why the four type-reference edge kinds are kept while `imports` and field
access are not.

### Separate what is certain from what produced it from who wins

"Confidence" means three different things and therefore none of them. One field grading
extractor quality cannot also express "one of these four".
Keep `resolution`, `evidence` and `precedence` separate — see
[ARCHITECTURE.md](ARCHITECTURE.md) DR-3.

### Two producers for one file means reconciling them forever

A two-tier extraction design pays for itself in reconciliation clauses accumulating in the
stitcher — typically to recover facts that **no deliverable reads**. One producer per file. Where a language genuinely needs two readers, the
adapter owning that language merges them internally and the pipeline sees one stream.

### Bulk load. Never per-row.

Per-row insertion runs **orders of magnitude** slower than bulk load — minutes against
seconds on a real fact set — and a per-row loader left as a placeholder is never revisited.

### A stale cache is a correctness bug wearing an efficiency costume

Include every input that could change the result in the cache key: content hash, scanner
identity, scanner version, catalog hash, redaction pattern set. Omit one — the mapper
version, say — and stale facts get served until someone forces a cold rebuild by hand.

### A stored value that is a pure function of another field is policy leaking into data

`precedence` was stored on every fact, yet it was entirely determined by `evidence` —
human 90, model 10, code 50. Storing it made illegal states representable and froze the
rank table into published bundles, so a policy change would have required re-extracting the
estate. The test: *could two rows with the same source field ever legitimately differ?* If
not, derive it at use time and never store it.

### A table whose rows are copies of another table is a query

Materialised traces duplicated every shared subtree once per endpoint that reached it — a
validator on 150 endpoints' paths appeared 150 times, and the copies would have dwarfed the
`edges` table they came from. Everything in a trace except membership and the cycle marker
was already in other tables. The fix: a named query (`trace_of`) plus one slim summary
table for the numbers findings need. Before materialising a derivation, ask what it
contains that its inputs do not.

### An arbitrary bound truncates the wrong thing

A depth limit on a trace spends its budget on accessors and stops before the call that
mattered. Remove the noise instead of capping the depth. Where termination genuinely needs a
stop, use cycle detection, which is a correctness requirement rather than a limit.

Path enumeration is the exception that proves it: routes between two symbols grow
exponentially, so return the union subgraph of all routes rather than a truncated list.

---

## Working practice

### A library earns its place by absorbing mechanics, never by setting policy

The tool-capability audit ran four dependency decisions through one test. `jsonref` was
taken for pointer mechanics — but remote-fetch policy, cycle semantics and gap reporting
stayed in our loader, because the library's defaults did all three wrong. The Gradle
Tooling API was *rejected* because its hard part (an injected model builder) was ours to
write anyway, leaving only a dependency and a version matrix. `click` and `rich` were taken
without hesitation because a CLI router and a status display carry zero policy. Ask first:
which part is mechanics, which part is policy? Take the tool for the first, never let it
decide the second.

### Verify, then claim

Three defects in this project were found by running something rather than reading it: two
Mermaid parse errors, and a broken cross-reference. Cheap checks that have already paid for
themselves:

```bash
# every markdown link resolves
for f in **/*.md; do grep -oE '\]\([^)#][^)]*\.md' "$f" | ...; done
```

Per `GUIDELINES.md` §13.6, "the diagrams are written but I have not rendered them" is the
honest statement when a check has not been run. Better to run the check.

### The specification is a contract

`GUIDELINES.md` §1.1. A decomposition, a dependency choice, a schema shape — none of these
are agent decisions, even when they look obvious. Proposing a component breakdown before
writing seventeen documents against it saved rewriting all of them.
