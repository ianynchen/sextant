# M03 — Scanner

## Purpose

Turn code and artifacts into facts.

This is the only module that reads code, and the only one that knows a language exists.
Everything downstream sees facts ([D00](D00-fact-schema.md)) and nothing else.

## Interface

Two ports, because code and artifacts are different problems.

```
Scanner
  accepts(languages)  -> bool
  capabilities()      -> {Capability}
  rank()              -> int
  scan(module, model) -> [Fact]

ArtifactReader
  accepts(file_kind)  -> bool
  read(files, model)  -> [Fact]
```

**Implementations are keyed by backend, never by language.** One ASM scanner declares
`accepts({java, kotlin})`. `if language == "java"` does not appear anywhere.

### Selection, and why only one may run

Several scanners may accept a language. The highest `rank` wins, unless configuration pins
one.

**Exactly one scanner runs per language per run.** Two scanners writing facts for the same
file means reconciling two versions of the truth at query time — a defect that surfaces as
reconciliation clauses accumulating in the stitcher, each one a place where two accounts
must be argued into one. Selection happens once.

Artifact readers do not compete; they read different file kinds.

### Capabilities

A scanner declares what it can do, and catalogs declare what they need
([D02](D02-catalog-schema.md)). A catalog whose requirement is unmet **does not run, and the
skip is reported**. This is how a weaker scanner degrades visibly instead of silently
finding fewer endpoints.

| Capability | Gates |
|---|---|
| `annotation_args` | Every annotation-driven framework |
| `type_annotations` | `nullable` on contract fields, per reference — never `required`, which comes from presence machinery ([D00](D00-fact-schema.md) §5b) |
| `string_constants` | Topic and URL literals |
| `invokedynamic` | Lambdas, and therefore functional routing |
| `constant_propagation` | A URL assembled from a constant and a literal |
| `chain_reconstruction` | The whole `fluent` style |
| `control_flow` | Honest sequence diagrams |
| `kotlin_metadata` | Nullability and data-class shapes |

## Inputs

The `RepositoryModel` from [M02](M02-detector.md). Class files, jars, and artifact files.
Exclusion and redaction from [D04](D04-config-and-exclusion.md).

## Output

Facts as JSONL, one file per **source file**, plus the uncovered-source list.

## Behaviour

### The JVM scanner

ASM over class files. See [ARCHITECTURE.md](../ARCHITECTURE.md) DR-1 for why this rather
than a source indexer. Two of its eight capabilities are hard, and the rest are
straightforward.

### The hard part: control flow

[D00](D00-fact-schema.md) requires every call site to carry its position in the method's
control flow, so a sequence diagram can show alternatives and loops rather than claiming
four calls all happen when two of them are branches of one `if`.

**Source code states this directly. Bytecode does not** — it has jump instructions, not `if`
and `for`. Recovering the structure means building a control-flow graph from jump targets
and the exception table, finding loops from their back edges, and grouping branches into
regions with dominators.

This is well-trodden work — it is what a decompiler does — but it is real work, and it is a
cost of reading bytecode that was **not weighed when bytecode was chosen**. It is recorded
here rather than discovered during implementation.

Three possible scopes:

| Scope | A sequence diagram can show | Cost |
|---|---|---|
| Loops only | `loop`. Everything else flat. | Small. A back edge is a jump to an earlier offset — exact and unambiguous. |
| **Loops, optional, grouped alternatives** | `loop`, `opt`, `alt` with unnamed branches | Moderate. Dominators and post-dominators. |
| Full structuring | `alt` labelled `if order.isExpress` | Large. Requires reading the comparison expression. |

**The middle scope is the version 1 commitment** (signed off 2026-08-27; named conditions stay out and are a recorded gap). Loops and optionality are where the lie lives:
a diagram showing `shipFast` and `shipNormal` as consecutive steps is wrong, and grouping
them as alternatives fixes that even without naming the condition. Irreducible control flow
exists but is rare in compiled Java; where the structure cannot be recovered, the region is
marked `sequential` and the fact says so.

### The other hard part: chain reconstruction

A `single_call` catalog reads one instruction. A `fluent` catalog needs one value followed
across several:

```
NEW okhttp3/Request$Builder
INVOKEVIRTUAL Request$Builder.url  (Ljava/lang/String;)…
INVOKEVIRTUAL Request$Builder.post (Lokhttp3/RequestBody;)…
INVOKEVIRTUAL Request$Builder.build ()…
```

This is a small abstract interpretation over the operand stack and local variables. It gates
every builder-based client library, which is most modern HTTP and messaging clients.

**Two hard problems in one module is a reason to watch its size.** If it grows, control-flow
reconstruction is the piece that splits out first, because it is self-contained: instruction
stream in, region tree out.

### The easy parts, which still have to be right

Throw sites: an `ATHROW` instruction is recorded as a call-site-shaped fact with invoke
kind `throw` and the thrown type as target — it is what gives traces their `throws`
terminal, and it costs one case in the instruction visitor.

Annotation values including nested annotations, arrays and enums. Type annotations from
**both** the visible and invisible type-annotation attributes — a codebase compiled over a
decade carries several nullability spellings at different retentions: JSpecify's is
`RUNTIME` and lands in the visible table, while `javax.annotation.Nullable` and the
JetBrains spellings are mostly `CLASS` and land in the invisible one, so reading only one
table silently misses the other. Measured elsewhere as the one real case where a source
tier saw something the bytecode already held. The constant-value attribute. Source file and
line numbers. Kotlin metadata for nullability.

### Artifact readers

Configuration, build files, Kubernetes manifests, Helm charts, OpenAPI documents, protobuf
descriptors. Each declares which file kinds it accepts.

Two are worth naming.

**Protobuf is never read by parsing `.proto` text.** The preferred source is the
**descriptor embedded in the generated classes** — protobuf's Java output carries the
serialised `FileDescriptorProto` in a static field, and the JVM scanner is already reading
those class files. That gives the schema fully resolved, with imports followed, with **no
`protoc` on the machine and no import paths to configure** — and it is the schema the code
was actually built from, which is what [ARCHITECTURE.md](../ARCHITECTURE.md) DR-4 asks for.
A `.proto` file present in the repository is compared against it, and a difference is drift.
Running `protoc --descriptor_set_out` is the fallback where no generated classes exist.

The mechanism, verified: the descriptor bytes sit as **string literals in the generated
class's static initializer** — chunked, ISO-8859-1-encoded — so extraction is the same
string-constant machinery the scanner already has, and parsing the recovered bytes is the
Python `protobuf` package's job. In-house: the chunk reassembly. Provided: everything
after it.

**OpenAPI `$ref`s resolve through `jsonref`, with policy in our loader.** The library owns
the mechanics — pointer escapes, splicing, laziness; our loader owns every decision: a
relative file is read and cached; a **remote URL is refused by default and reported as a
gap naming the URL and the incomplete shape**; under `--allow-resolve` it is fetched,
cached, and its **content hash recorded as an input** so a silently-changed remote schema
is visible, not absorbed. A `$ref` cycle becomes a shape reference — which is what
`Order ⟷ OrderLine` should be — never an error.

**Helm is rendered by the Helm binary** and the output parsed as ordinary Kubernetes YAML,
reusing that reader unchanged. **Each values file found is rendered, not one** — a module
analysis serves every environment, so deployment facts carry the environment they came from.
This is bounded: a chart has a handful of values files. It needs the `helm` binary, chart
dependencies already built, and a release name; charts using cluster lookup functions will
not render, and that is reported rather than silently empty.

Every declared contract records **whether the build consumes it**, which is what
[ARCHITECTURE.md](../ARCHITECTURE.md) DR-4 turns into authority. And every contract's
payload structures are emitted as `declared_shape` facts — wire names, field numbers where
the format has them, wire types per [D00](D00-fact-schema.md) §5b — because a contract
without its payloads can be catalogued but never compared, and comparison is the point.

### Redaction

Runs here, before a fact is written — not at load, not at render. A value that reaches a
fact file is already on disk and may already be inside a published bundle. See
[D04](D04-config-and-exclusion.md) for the two strategies and the mark a redaction leaves.

### Coverage

Every source file in a compiled source set that has no corresponding class file goes on the
uncovered list. **A non-empty list stops the run**, unless `--allow-uncovered` is given — in
which case the run proceeds and the workspace is recorded as partial, so every document
derived from it says so.

## What it must not do

- **No derivation.** No edges, no endpoints, no dispatch resolution. Facts only.
- **No workspace access.** It writes files; [M04](M04-resolver.md) loads them.
- **No cross-file reasoning.** A fact is about one document. Joining is downstream.
- **No guessing.** An unresolvable call target is `unresolved` with a reason, never a
  plausible name.
- **No language name outside the adapter owning that language.**

## Honesty obligations

- The uncovered-source list, in full.
- Class files with no source attribution, which no ignore rule could be applied to.
- Every capability the chosen scanner lacks, so a skipped catalog traces back to a cause.
- Regions where control flow could not be structured.
- That redaction occurred, and which pattern class matched — never the value.

## Open decisions

| Decision | Blocks |
|---|---|
| Whether chain reconstruction is inside the ASM extractor or a pass over its output | Module size |
| How far constant propagation follows a value across method boundaries | Endpoint URL resolution |
| Whether a partially-structured method is a fact-level or document-level `partial` | [D00](D00-fact-schema.md) |
