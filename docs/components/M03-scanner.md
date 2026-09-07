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
| `typed_signatures` | Structured parameter and return types — the field a body-parameter or `response_arg` join reads instead of a positional guess ([D00](D00-fact-schema.md) §5a) |
| `type_annotations` | `nullable` on contract fields, per reference — never `required`, which comes from presence machinery ([D00](D00-fact-schema.md) §5b) |
| `string_constants` | Topic and URL literals |
| `invokedynamic` | Lambdas, and therefore functional routing |
| `constant_propagation` | A URL assembled from a constant and a literal |
| `chain_reconstruction` | The whole `fluent` style |
| `control_flow` | Honest sequence diagrams |
| `kotlin_metadata` | Nullability and data-class shapes |
| `call_site` | Every call-site-driven engine — [D02](D02-catalog-schema.md)'s `single_call` and `fluent` both |
| `implemented_interfaces` | The `interface_implementation` style — matching a registered receiver's own type against an interface a catalog names |
| `generic_interfaces` | Capability 9.14 — the parameterized superinterface references `implemented_interfaces` erases. `derived_resource` reads it for a repository's entity type |
| `superclass` | Capability 9.13 — a class symbol fact's erased direct superclass, read regardless of whether its signature is generic. [D00](D00-fact-schema.md) §4's `relationship_kind: extends`, made real |
| `array_arguments` | Capability 9.15 — a call-site argument produced by an array construction reads as `{kind: array, elements: […]}` rather than one opaque `unresolved`. Every `String...` API in the estate depends on it |
| `nested_annotation_args` | Capability 9.16 — an annotation-valued annotation argument reads as a nested `{annotation, args}` use of its own, recursively, rather than being dropped with no key at all ([D00](D00-fact-schema.md) §5) |
| `lambda_body` | Capability 9.17 — a `dynamic` call site carries `implementation`, the symbol of the lambda body its dispatch will run, where `target` names only the bootstrap factory. A traversal that follows call targets reaches a lambda's statements instead of stopping at `LambdaMetafactory` |
| `class_file_version` | The class-file major each document was read from (JVMS 4.1), taken from the bytes rather than from ASM's constants so it is available even for a class the reader refused. Consumers: the accepted-range test, multi-release selection's target fallback, and language labelling |
| `method_returns` | Capability 9.18 — a `method_return` fact per return instruction, naming the value the method hands back ([D00](D00-fact-schema.md) §5). The last link in a round trip: a returned call result joins by `source` to the site that produced it |

**Fifteen of the scanner's now-eighteen designed capabilities are shipped**, and the shipped
set is **`Capabilities.ALL` in the extractor jar** — the scanner DECLARES what it can read,
and the caller asks it (`--capabilities`), which is what a catalog's `requires:` is checked
against. *It was `ingress/extract/jvm/scanner.py`'s `_CAPABILITIES`, a Python-side list
making an unverified claim about a subprocess built by a separate step; that constant is
gone (W1).* `annotation_args`, `typed_signatures`,
`type_annotations` and `kotlin_metadata` since Phase 2A/2B; `call_site`, `string_constants`
and `chain_reconstruction` from Phase 2C's dataflow pass (below); `implemented_interfaces`
from a class symbol fact's own `interfaces` list, in declaration order
([D00](D00-fact-schema.md) §5a); `superclass`, `generic_interfaces`, `array_arguments`
and `nested_annotation_args` — capabilities 9.13, 9.14, 9.15 and 9.16 — from Phase 2O; and
`lambda_body` and `method_returns` — capabilities 9.17 and 9.18 — from 2Q.
*The four 2O capabilities were absent from this table until the 2O documentation sweep,
which is the §5.1 failure of documenting a schema in one file and shipping it in another.*

**A capability with no consumer is a half-shipped feature (GUIDELINES §2), so name the
consumers.** 9.13's `superclass` is read by `resolve/shapes/parse_binding.py`'s ancestry
walk and by `error_advice`'s throwable-root walk; 9.14's `generic_interfaces` by
`engines/derived_resource.py`. **9.15's `elements` has three consumers, all wired in 2O
Task 13** — `engines/combinator.py`'s `media_values` predicate (through
`shapes/arguments.py::_expanded_arguments`), `all_strings`
(`shapes/arguments.py::_all_string_channels`), and `shapes/arguments.py::channels_of`, the
array-aware sibling of `channel_of`. **9.16 has exactly one**: `engines/scheduled_work.py`'s
`_folded`, which reads a repeatable container's array of annotations so that a method
carrying two `@Scheduled` yields both schedules. **No consumer reads a nested annotation's
own ATTRIBUTE as an address**, and that is a refusal rather than an omission: giving
`@RabbitListener` a `path_from: [bindings]` would publish a `@QueueBinding`'s JSON text as
a queue name. `docs/COVERAGE.md` carries that boundary and the condition that closes it.

**9.17 and 9.18 both have a consumer now, and each names a different one.** 9.18's
`method_return` is read by `resolve/return_flow.py`, which joins it to `call_sites` to link
a callee's returned value to the caller's own `result` id (2Q's `G3`, closing OI-15), and
again by `resolve/dispatch.py`, whose "did we read a body" test is the presence of the
fact. 9.17's `implementation` is read by `resolve/call_edges.py`, which makes an
`invokedynamic` site an edge into the **lambda body it creates** rather than into the
bootstrap factory its own target names (2Q's `G4`, closing OI-14) — without which every
lambda in a module is a platform terminal and a `forEach(x -> mapper.insert(x))` reports
`forEach` and never the persistence. Measured on `macrozheng/mall`'s `mall-admin`: fifteen
bodies reached this way, seven of them holding a terminal no other path reaches.
*Both were listed here as having no consumer until 2Q's `G3` and `G4` shipped, which is the
state this file's own rule — a capability with no consumer is a half-shipped feature —
exists to make visible while it lasts.*

**`chain_reconstruction` means exactly this: receiver and result value ids are present on
`call_site` facts** ([D00](D00-fact-schema.md) §5) — a `fluent` catalog's steps are a join
over those links, nothing more. `invokedynamic` stays undeclared as a general capability, but **string
concatenation is no longer among its unread cases** (W4): a `StringConcatFactory` site
carries a RECIPE holding the literal parts, so `"/api/" + version + "/orders"` reads as the
template `/api/{}/orders` rather than as `unresolved`. That is reading what the class file
states, not decompiling — the hole stays a hole. Every other bootstrap's arguments remain
honestly `unresolved`; a lambda's own bootstrap handle is captured separately,
through the `lambda` argument kind ([D00](D00-fact-schema.md) §5) wherever a lambda or
method reference is passed as an argument, and — since 9.17 — through the site's own
`implementation`, which does not need the lambda to reach an argument slot at all.
`constant_propagation` and `control_flow` remain unshipped, each for the reason recorded
below.

## Inputs

The `RepositoryModel` from [M02](M02-detector.md). Class files, jars, and artifact files.
Exclusion and redaction from [D04](D04-config-and-exclusion.md).

## Output

Facts as JSONL, one file per **source file**, plus the uncovered-source list.

## Behaviour

### The JVM scanner

ASM over class files. See [ARCHITECTURE.md](../ARCHITECTURE.md) DR-1 for why this rather
than a source indexer. Two of its fifteen capabilities are hard, and the rest are
straightforward.

**Two forms of class input, one answer.** The scan is pointed either at a directory tree of
loose `.class` files — a module's own build output — or at a **jar**, read as a zip, which
is what an opted-in library arrives as ([D04](D04-config-and-exclusion.md) §2a). Both yield
class-relative names in one **sorted** order, and the sort is load-bearing rather than
tidy: a zip's entry order is whatever the archiver happened to write, and declaration order
in the workspace is derived from the order facts load in, so following the archive would
make a scan's output depend on how the jar was built (NFR-1). Every `.class` entry is
scanned and nothing else is opened, so a jar nested inside a jar is invisible and a
multi-release jar's versioned copies are each their own document.

**A library scan stamps its origin.** Where the scan was pointed at a library, each
document records the coordinate it was extracted from and reads `origin_tier: dependency`
([D00](D00-fact-schema.md) §2). A module's own scan writes no origin key at all — not one
spelled null — so its fact files stay byte-identical to what they were before library
extraction existed.

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

**Configuration readers are shipped** (Phase 2F): `PropertiesReader` and `YamlConfigReader`,
model-blind over [M02](M02-detector.md)'s own `resource_roots` — a `.properties` line
becomes one `config_entry` per key, dotted verbatim; a YAML document flattens nested maps to
the same dotted `key_path`, a list element becomes an indexed segment (`foo[0]`), and a
multi-document file's own `doc_index` travels with each entry ([D00](D00-fact-schema.md)
§5c). Neither reader layers profiles, resolves a placeholder, or interprets what a key
means — that is [M04](M04-resolver.md) pass 2's job, over facts these readers already wrote.
A malformed file degrades to `partial`, never kills the run.

Two more are worth naming.

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
- An input the scan was pointed at that holds **no class file at all** — a readable
  archive or directory with nothing in it to scan is a finding about the input, and goes
  on the uncovered list rather than being reported as a clean scan of nothing. An input
  that cannot be read at all is a different thing and fails the run outright.
- Class files with no source attribution, which no ignore rule could be applied to.
- Every capability the chosen scanner lacks, so a skipped catalog traces back to a cause.
- Regions where control flow could not be structured.
- That redaction occurred, and which pattern class matched — never the value.

## Open decisions

| Decision | Blocks |
|---|---|
| How far constant propagation follows a value across method boundaries | Endpoint URL resolution |
| Whether a partially-structured method is a fact-level or document-level `partial` | [D00](D00-fact-schema.md) |

One decision formerly here was closed by Phase 2C's approved design (2026-08-29):

- **Chain reconstruction is split, not sited in one place.** The extractor emits the
  linked value ids — `receiver`/`result` on every `call_site` fact
  ([D00](D00-fact-schema.md) §5) — and stops there; walking those links into a chain is
  the derivation's job, a join the `fluent` engine performs over facts already on disk.
  Module size stays bounded on the extractor side because there is nothing left to grow
  there: one dataflow pass, not a graph walk.

## How a scanner declares its capabilities, and what that costs

**Over the subprocess contract, as a command-line question**: the JVM extractor
answers `--capabilities` with `{"capabilities": [...]}` on stdout, the same
channel it answers a scan on, and repeats the list inside every scan report so
what a workspace records and what its catalogs were gated on cannot disagree.
It is asked once per scanner instance and cached. *This said "before any scan"
until a review checked it: `analyze` asks at the point it needs the answer, which is when
it hands the set to `resolve` — after the module scan and every library scan. Nothing turns
on the order, because the jar's answer does not depend on having scanned; the claim was
simply not true.* Capabilities
decide which catalogs run. Measured at 0.02s — the JVM starts and exits without
opening a class file.

Chosen over a jar-manifest attribute for two reasons. A manifest is **JVM-only**,
and `capabilities()` is on the port every backend implements, so it would make
the JVM a special case. And Gradle writes the manifest, so the capability list
would have to live in `build.gradle.kts` as well as in the Java that implements
it — the duplication this whole change removes. (Library *versions* are the
opposite case and do go in the manifest: Gradle is the thing that resolves them,
so it genuinely owns them.)

### The consequence, stated: every scanner needs something we build

**A command-line protocol assumes we control the scanner's entry point.** A
third-party analyzer we did not write will not answer `--capabilities`, so
adopting one means writing a WRAPPER for it — a thin executable that declares
what that analyzer can read and translates its output into the fact stream.
That is a real cost per backend and it is accepted deliberately, not overlooked:

- The alternative — inferring capabilities from a version string — is what
  Sextant did until Step 1, and it is why a field named for a library version
  held `"9.18"`, a capability number. **A version cannot be interrogated**; you
  can only look it up in a table someone maintains by hand, which is a second
  copy of the declaration with none of its authority.
- A wrapper is needed regardless. A third-party analyzer does not emit D00 facts,
  so something must already stand between it and the workspace; declaring
  capabilities is one more line in a component that has to exist anyway.
- It keeps the rule uniform. Every scanner answers the same question the same
  way, whoever built it, and no backend gets a private mechanism.
