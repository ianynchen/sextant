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

---

## Implementation

### An explicit `read_json` column spec silently nulls out NDJSON

`read_json(path, columns={'json': 'JSON'})` looks for a field literally named `json` in
every record. A newline-delimited fact file has no such field, so every row still loads —
row counts look right — and every column comes back `NULL`. Nothing errors. `read_ndjson_objects(path)`
is the form that actually reads one-JSON-object-per-line files; see `load_facts` in
`workspace.py`. The lesson is not "use this one function" — it's that an ingestion path can
fail by going silently null instead of loudly wrong, and a passing row count does not rule
that out. Spot-check a value, not just a count.

### "Ruff clean" is a claim, not a result

Two implementers reported the lint gate clean while `ruff` was in fact reporting an error.
The controller only caught it by running the linters itself rather than trusting the report.
Reported gate output is not gate output — run it yourself before believing it.

### A test asserting on a return code needs `check=False`

`subprocess.run(..., check=True)` raises before a test gets to assert on
`result.returncode` — the assertion never runs, and a red test looks like a crash instead.
Pass `check=False` explicitly whenever the return code itself is under test; the linter
that insists on an explicit `check=` argument is catching a real bug here, not
bikeshedding.

### Shadow's classic plugin ID doesn't work under Gradle 9

`com.github.johnrengelman.shadow` fails on Gradle 9 with an opaque `MissingPropertyException`
that points nowhere near the real cause. The maintained coordinates are
`com.gradleup.shadow` — that's what `extractor-jvm/build.gradle.kts` declares.

### Pre-declare a table that only a derivation creates

`derive_endpoints.sql` runs only when a catalog's required capabilities are met, and every
catalog can legitimately be skipped — capability gating exists precisely so a weaker
scanner degrades instead of failing. But the named `endpoints` query didn't know that:
with no catalog run, the table never existed, and the query crashed on exactly the path
whose entire purpose is to report rather than fail. Fix: `schema.sql` pre-declares an empty
`endpoints` table with `CREATE TABLE IF NOT EXISTS`; `derive_endpoints.sql` replaces it
whole with `CREATE OR REPLACE TABLE` whenever at least one catalog runs. A named query
against a sometimes-created table needs the table declared unconditionally, not just
populated conditionally.
