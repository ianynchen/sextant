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
| `typed_signatures` | Structured parameter and return types — the field a body-parameter or `response_arg` join reads instead of a positional guess ([D00](D00-fact-schema.md) §5a). **Completed in W5**: a parameter's type now comes from the `Signature` attribute where the method has one, as the return type and a field's type already did, so `List<String>` keeps `String` at a parameter position and a type variable stays `T` instead of arriving as its erasure |
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
| `annotation_default` | JVMS 4.7.22 — what an annotation element falls back to when a use omits it. **NO CONSUMER, and W4a went looking for the one this row used to name.** It said "a catalog reading the real default instead of a number typed in from documentation". No shipped catalog does that: every `default` in the estate is a config KEY (`spring.cloud.stream.default-binder`), a framework media type (`application/hal+json`), a strategy NAME, a Spring config convention, or a COMPUTED rule (`namespace_default: reversed_package`, which the runtime derives from the package — reading `AnnotationDefault` there answers `""`). So the vocabulary W4a would have added is a catalog key with no reader, which is `detect.coordinates`'s own defect — declared by 41 catalogs and read by nothing. **This is §2.3's "read, no consumer yet" and it is now stated with what would end it**: a catalog needing an element's declared default, which none does today. **Falsified by** a framework whose meaningful default is a literal on the annotation type rather than a rule its runtime computes |
| `concat_template` | A `StringConcatFactory` site's recipe, so an address the code ASSEMBLES reads as a template (`/api/{}/orders`) rather than as `unresolved`. Consumer: the outbound address a catalog reads, and — once a matching tier exists — the server route it lines up with |
| `constant_value` | JVMS 4.7.2 — a compile-time constant field's value, which gives D00 §5's `constant` fact its first producer. Consumer: topic and URL resolution, where `static final String TOPIC = "orders"` is how a great many real listeners name their destination |
| `enclosing_class` | JVMS 4.7.6/4.7.7 — the class file's own statement of what encloses a nested class, including the enclosing METHOD for an anonymous one. Consumer: **W4b**, which replaces deriving nesting by splitting a binary name on `$` |
| `class_file_version` | The class-file major each document was read from (JVMS 4.1), taken from the bytes rather than from ASM's constants so it is available even for a class the reader refused. Consumers: the accepted-range test, multi-release selection's target fallback, and language labelling |
| `type_parameters` | W5 — the formal type parameters a class or method declares, with their bounds, in declaration order ([D00](D00-fact-schema.md) §5a). The name and the position are what a generic substitution binds, and `typed_signatures` can now emit a bare type variable that would otherwise be attached to nothing. **No consumer yet, deliberately**: **W25** is where substitution reads it — §2.3's legitimate "read, no consumer yet", as against "declared, never read" |
| `source_file` | W6 — JVMS 4.7.10, the NAME of the file a class was compiled from, as the class file states it rather than as its own path implies. It replaces a derivation that was javac's conventions in code (`.java`, everything from the first `$` cut off), under which every Kotlin class named a `.java` file that does not exist. Consumer: `relative_path`, which is what an index hands a reader who wants to OPEN a declaration |
| `line_numbers` | W6 — JVMS 4.7.12, the source lines a method's code came from, as `line_start`/`line_end`. **Every line number in the estate was 0** (measured: mall-admin, 1,428 symbols), so Sextant could say what exists and never where. 0 still means "not stated" — a class carries no such table, and neither does an abstract method. Consumer: **W35**, the index |
| `local_variable_names` | W6 — JVMS 4.7.13, the names a source file gave a method's locals, which cover its parameters. Fills a parameter name only where `MethodParameters` stated none: measured on spring-web 6.1.6 (1,117 classes), 1,048 of 9,164 names come from here and nowhere else |
| `merge_candidates` | Capability 9.19 — a call-site argument whose value has several producers reads as `{kind: merge, candidates: [...]}` ([D00](D00-fact-schema.md) §5a) rather than as one sourceless `unresolved`. The fact says "one of these" and chooses none; what a rooted merge resolves to is the walk's business (spec `2026-10-21-merged-values-design.md`) |
| `method_returns` | Capability 9.18 — a `method_return` fact per return instruction, naming the value the method hands back ([D00](D00-fact-schema.md) §5). The last link in a round trip: a returned call result joins by `source` to the site that produced it |

**Twenty-three of the scanner's now-twenty-six designed capabilities are shipped**, and the shipped
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

### The Python scanner

`ingress/extract/python` reads `.py` source with the standard library's `ast` (spec
`2026-11-06-python-reader-design.md` §3a). It never imports or runs the code it reads, and
it downloads nothing. It accepts `{python}`, ranks 0, and declares `typed_signatures`,
`annotation_args`, `type_annotations` and `value_ids`. It writes D00 §5's rule 9 flow fields,
as the JVM scanner does, and like it does not declare `control_flow`, which is the regions a
sequence diagram needs (above).

**Input.** Python runs from source, so the module's import roots are what is read: the
detector reports them as the module's `output_dirs`, and the scan stage hands them over as
`classes_dir` and `more_classes_dirs`. Every `.py` file under them is one document, written
to `<relative path>.jsonl`. Folders on the detector's skip list are not entered, and a path
`.sextantignore` or its built-in layer excludes is not read (`ScanRequest.ignore`, matched
as `resource_files.list_files` matches). A git-ignored file IS read: generated code such as
`*_pb2.py` is often git-ignored and is part of the module. A file that cannot be opened (a
broken link) goes on the uncovered list with its reason.

**One file at a time.** An import binds a name by PATH only: `from app.models import
Order` is the class `app/models/Order#`, or the module `app/models/Order` when such a file
is in the import roots. The other file's body is not read. A name that two branches bind
differently is a closed list of both, in written order.

**What it writes** (spec §3a, D00 §1 and §5a):

- `module` symbol per file, `class` (or `protocol`, `enum`) per class, with the written
  parents as `superclass` and then `interfaces`, in written order, up to the first base
  the file cannot name as a class; nothing after it is written, and the document is
  `partial` with one `partial_reason` line per such class;
- `<clinit>` per module and class body, `<init>` for `__init__`, one `method` per `def`;
- a static `field` per name a module or class body assigns, and a `field_write` from that
  body's `<clinit>`;
- typed signatures from the written annotations (rule 1); `self` and `cls` are receivers,
  not parameters;
- decorators as `call_site` facts in the enclosing body's `<clinit>`: each decorator
  expression in written order, then each application from the bottom up, with the
  function as a `lambda` argument or the class as a `class` argument. A call on a value
  is `__call__` with that value's id as `receiver`.

A call's owner is named where the file can tell: a class of the file is its `<init>`; a
function of the file, or a member of another module, is a static call on that module's
type. Whether an imported member is a class is in a file this scanner does not read, so
the resolver decides. A call on a name the file assigns names the static field
(`receiver_field`) and leaves the owner to the resolver (D00 §5's virtual call with a
receiver).

**A file Python cannot parse** goes on the uncovered list with the reason, and the rest
of the module is scanned. The grammar is the one of the Python that runs Sextant, and the
reason names that version: a file written for a newer Python than that is not read.

**Calls, values and returns in every body** (`calls.py`, D00 §5). Every call in a module
body, a class body, a function, a nested function and a `lambda` is a `call_site`, with
expression statements, `+=`, the iterated value of a `for`, `with ... as` and
comprehensions included:

- `static` for a function, `virtual` for a call on an object, `special` for `<init>` and
  for `super().m()` (on the class's first written parent);
- a call on `self` names the class; a call on a parameter or a local with a written type
  names that type; any other call on a value names the receiver's value id and leaves the
  owner to the resolver;
- `with x as y` is the call `x.__enter__()`, and `y` is its result;
- a constructor call gives an `instance` whose `source` is the constructor's receiver;
- an f-string, or `+` with a string literal, is `concat`, filled by a `dynamic`
  `builtins/str#format` site; a list or a tuple is `array`; a function is `lambda`;
  `a if c else b` and `a or b` are `merge`; `await x` is `x`;
- a keyword argument is put at its parameter's position where this file writes the
  callee's parameter list (a function or a constructor of this file, by a `static` or
  `special` call), else it keeps its name in `keyword` (D00 §5).

A nested function is a method of the same owner named `outer$inner`; a `lambda` is
`lambda$<method>$<n>`, numbered per method, with `static` for a module or class body and
`new` for `__init__`; a class inside a function is `outer$Local`. A nested function or a
`lambda` sees the method's `self` as its receiver, as a JVM lambda body sees `this`. A name
defined twice is one method: its bodies share one set of call ordinals, value ids and return
ordinals. An attribute is named by a field symbol only where every name before it is a
module or a class; an attribute of a variable (`app.state.client`) is a value, and a call on
it names only its receiver. An import that branches of a function bind differently is the
same closed list as at module level.

A local name holds the last value written to it on the path; where paths join with
different values it is a `merge` of them (only paths that reach the join count; a loop's
`continue`s and `break`s, and the values an exception may leave a `try` or a swallowing
`with` with, are paths), and `unresolved` where a path does not set it or sets a value not
followed. A list held in a local is read once as written, and
`unresolved` after that, because the code it was handed to can change it.

Every `return` is a `method_return`, plus `return None` where the end of the body is
reachable. A generator has one `unresolved` return. An `@overload` stub, and an abstract or
`Protocol` method whose body is only `...`, `pass` or a docstring, has no body and no
`method_return`. `self.x = …` and `C.x = …` are `field_write`s; a write to an attribute of
another object is not written. A module-level name that branches bind to several imports is
a static field with one `field_write` per import, and a module-level alias of an imported
name (`DecodeError = jwt.DecodeError`) is bound as that import is.

**Each call's place in its body's control flow** (`flow.py`, D00 §5 rule 9): `dominator`,
`on_every_exit`, `post_dominator`, `reaches_return` and `loop_group` on every `call_site`,
with the JVM meanings. The graph is built from the syntax tree while the body is read, a
call as two nodes (before it runs, after it completed), with the JVM pass's algorithms on
it. Every expression may raise, so inside a `try` every statement and call has an edge to
the handlers, except after a call that is all of its statement (`a()`, `x = a()`,
`return a()`); a `with` block's manager may swallow what it raised or raise it again; a
`finally` is copied for each way out, as javac copies it; `raise`, a re-raise and a failing
`assert` lead nowhere, as an `ATHROW` does. `python -O` may drop an `assert`. A
comprehension is a loop; a generator expression's calls have no `post_dominator` and do not
reach a return, since it may run after the body returned. A call after a `return` is
written with no place: no `dominator`, `post_dominator` or `loop_group`, both flags false.

**Libraries** (`libraries.py`, spec §3e "Libraries"). A name of another module is looked up
in the libraries of the scan, read lazily, each module once:
- the distributions the module declares and its installed environment holds
  (`ScanRequest.dependency_archives`: the `site-packages` folder, and each distribution's
  `*.dist-info/RECORD` for the import names it installs);
- the standard library, from the pinned typeshed copy Sextant ships
  (`resources/typeshed`, its commit in `COMMIT`; `stdlib/VERSIONS` says which modules the
  environment's Python has);
- for a distribution that ships no types (no `py.typed`), its typeshed stub package.

A type file (`.pyi`) is read before a source file. Nothing is imported or run, and nothing
is downloaded. A `sys.version_info` test in a type file is read against the environment's
Python (`pyvenv.cfg` of `ScanRequest.environment`, else its `site-packages` path); a
`sys.platform` test gives both branches.

- **A library name is its defining symbol.** A re-export is followed through the library's
  own imports, into any distribution the environment holds (`fastapi.Request` is
  `starlette/requests/Request#`, though only fastapi is declared), and through a star
  import, which gives the names its module's `__all__` lists, or every name not starting
  with `_`. `from fastapi import APIRouter` names `fastapi/routing/APIRouter#`, and
  `requests.get(…)` is the static call `requests/api#get`. A name the library binds
  differently in branches (a platform test, an `except ImportError` fallback) is the
  closed list of its bindings, as a name of the module is. A declared library that is not
  installed has no symbols, so the name stays as the import line writes it, and the
  detector notes `<name> is not installed in the scanned environment`. Where a re-export's
  defining distribution is not installed, the name is the one the library's import gives,
  and the uncovered list says `<module>.<name>: defined in <top>, which is not installed in
  the scanned environment`. Only a declared distribution starts a lookup: a name the
  module imports from an undeclared one is not read.
- **A library call's result has the class its signature returns.** The overload is the
  first one the argument types match, as a type checker chooses. A literal is checked
  against the written type, an alias read through to what it names (`OpenTextMode` to its
  `Literal[...]` members, so `open(p, 'rb')` is a `BufferedReader`). Where an argument of
  unknown type (the receiver among them), or one whose fit this rule cannot decide (a
  protocol, a type variable, a class it does not read), is given different parameter types
  by the overloads that match, the answer is the closed list of what they return
  (`narrowed`); so is a call that unpacks `*args` or `**options`, and a function the
  library's branches define differently. A call on a `narrowed` result leaves its owner to
  the resolver. A type variable or a special form names no class, and also leaves the
  owner.
- **What is written of a library is its type headers, as on the JVM** (ruled A,
  2026-11-06; D00 §5 `type_header`). After the module's own files, one synthetic
  `header_only` document, `__type_headers__.jsonl` labelled `<environment>`, holds a
  `type_header` for every library type the module's facts name (a call's owner, a class
  or instance argument, a written base, a parameter or return type), then for each of its
  written bases, transitively: the defining symbol, the construct kind, the first base as
  `superclass` and the rest as `interfaces` (as a module class's), no annotation, and the
  `origin`. A named type no library holds counts in `type_headers_unlocated`; `object` is
  the boundary and gets none. A library class whose bases are not all read gets none
  either, with a line on the uncovered list. No library member, document or `symbol` fact
  is written, so library methods are not "found" (`method_resolution` answers `external`),
  `coverage.documents` counts the module's files only, and the `symbols` view holds the
  module's own. Library signatures are used only inside the scanner, to type the module's
  own calls (above).
- **An opted-in library's bodies** (`extract_libraries`, D04 §2a) are read whole, as a
  jar is: the detector reports the environment's `site-packages` as the library root of
  each named distribution the module declares and has installed, and the library's own
  scan reads only that distribution's files (its `RECORD`), into `facts/lib/pypi/<name>/`
  with `origin: <name>` and the dependency tier.

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
