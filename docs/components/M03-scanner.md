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

**One file at a time, with the headers of the files it imports** (round 1, user choice A,
2026-11-07; `project.py`). An import binds a name by path, `from app.models import Order` the
member `Order` of the module `app/models`, or the module `app/models/Order` when such a file
is in the import roots, and then, where another file of the module is the one named, through
that file's HEADER: its module-level names (imports, re-exports, aliases, `NewType`s), its
classes' written bases and type parameters, each `def`'s declared return, each class
body's attribute declarations and the type each module-level type alias is. Nothing else of
its bodies is read. A re-export or an alias is
followed to where the name is defined (a class of the module, or a library's defining symbol),
as a library re-export is; a `NewType` names the class it wraps, and a call of it
(`AccessibleOrganizationID(oid)`) is no construction: no call is written, and the value is the
argument; a name the other file binds to a module-level type alias (`DbSession =
Annotated[Session, Depends(get_db)]`, `X: TypeAlias = ...`, `type X = ...`; plan
2026-11-08-python-fastapi-inbound N2) is the type the alias is, followed through each alias of
another file to the type the last one is; a name the other file binds to any other value
(`SaveFixture = Callable[...]`) names no type here, rather than a path that is no class. A header is parsed once per scan however many files ask, and is bound against an index
that reads no headers, so what a file reads never depends on which file asked first. A name
that two branches bind differently is a closed list of both, in written order.

**Reuse and headers.** Every header a file's reading consulted is one of the questions it
asked the module index (`("header", module)`), and its answer is the header's digest: the
syntax tree without function bodies and without statements that bind no name. Editing
another file's header re-reads the files that read it; editing its bodies does not. A file's
own digest is kept in its reuse record, so a warm run answers the question without parsing a
file that did not change.

**What it writes** (spec §3a, D00 §1 and §5a):

- `module` symbol per file, `class` (or `protocol`, `enum`) per class, with the written
  parents as `superclass` and then `interfaces`, in written order, up to the first base
  the file cannot name as a class; nothing after it is written, and the document is
  `partial` with one `partial_reason` line per such class;
- `<clinit>` per module and class body, `<init>` for `__init__`, one `method` per `def`;
- a `field` per name a module or class body assigns or annotates, and a `field_write` from
  that body's `<clinit>` where it is given a value. A module's names are `static`. In a class
  body an annotated name not written `ClassVar` (bare, dotted, in a string, or as
  `Annotated`'s first argument) declares an instance variable, `static: false`, whatever its
  value (PEP 526); a name assigned with no annotation, or a `ClassVar`, is the class's own,
  `static: true`. An instance variable's annotation that is not a plain type is evaluated in the
  class body after the value and written as `signature.annotation_value`, and a `TypedDict` key
  the typing specification lets be left out carries `modifiers.not_required` (D00 §5a). The
  instance variable's value is still its class-body `field_write`, which a
  `self.x` read takes with every class's writes (ruling R33);
- typed signatures from the written annotations (rule 1); `self` and `cls` are receivers,
  not parameters. Every type a fact carries (a signature's parameters and return, a field's
  type, a bound, a generic parent) has D00 §5b's `wire_type` at every level where the
  language fixes it: `str` string, `int` integer, `float` number, `bool` boolean; `list`,
  `set`, `frozenset`, `tuple`, `deque`, and `Sequence`, `MutableSequence`, `Collection`,
  `Iterable`, `MutableSet` in their `typing` and `collections.abc` spellings, array; `dict`,
  `defaultdict`, `OrderedDict`, `Counter`, and `Mapping`, `MutableMapping` in both spellings,
  map; a type parameter of the enclosing class or function (`T` of `class C[T]`, of
  `Generic[T]` or of a function's `TypeVar`, and `Self` in a class) object, as the JVM's `T`
  is; any other class object. `bytes`, `bytearray` and the classes of
  `datetime`, `uuid` and `decimal` are written as a scalar the serializer chooses, so they
  carry none and are left to a catalog's `known_types`; so do `None` (a field written `None`
  is a `null` on the wire, a return written `None` no payload), a special form
  (`Any`, a union, `Literal`) and a written text that names no type. `wire_format` is never
  set: the language fixes no format (a Python `int` has no width). The types the scanner
  reads with (a header, a receiver's type) carry none;
- decorators as `call_site` facts in the enclosing body's `<clinit>`: each decorator
  expression in written order, then each application from the bottom up, with the
  function as a `lambda` argument or the class as a `class` argument. A call on a value
  is `__call__` with that value's id as `receiver`;
- **a decorated `def` holds its decorators' result** (`f = dec(f)`, design
  `2026-11-06-reading-decorators-design.md` §3e, ruled option A): a module-level one is a
  static field of the module and a class-level one a field of the class, with a
  `field_write` of the outermost decorator's result, and the name is read as that field
  afterwards (a value `field`, a call `cli()` a `virtual` `__call__` with
  `receiver_field`, a call on it `cli.group()` with `receiver_field`). The function itself
  is the `lambda` the innermost decorator receives, and keeps its method symbol and body.
  The language's own method kinds keep the method model: `staticmethod`, `classmethod`,
  `property` (and `@x.setter`, `getter`, `deleter` of that property),
  `functools.cached_property`, `typing.overload` and `abc.abstractmethod`, matched by the
  symbol the decorator names, never its text. A `def` with one of them and another
  decorator holds the outermost decorator's result. A nested `def`'s local name already
  held it. An attribute read (`self.m()`, `C.m()`) still names the method;

A call's owner is named where the file can tell: a class of the file is its `<init>`; a
function of the file, or a member of another module, is a static call on that module's
type, and the resolver reads it as the construction where the member is a class. A call on
a name the file assigns names the static field (`receiver_field`); its owner is the name's
type where the file gives it one (below), and is otherwise left to the resolver (D00 §5's
virtual call with a receiver).

**Calling a class gives an instance of it** (ruling R17; design
`2026-11-06-reading-decorators-design.md` §3b option A, extended to constructions). The
scanner knows a member of another module is a class by that module's header (a class of
the module) or by the library's own file: the static call's result is then that class, its
type parameters filled as the library's constructor fills them. So `app = FastAPI()` makes
`app.get(...)` a call on `fastapi/applications/FastAPI#`, and `s = Session()` with `Session`
from another file makes `s.get()` a call on that `Session`, in a function body or at module
level. The class gets a type header (below). **A name holding a class object** is the class
`X` where the code writes `type[X]`: a parameter or local annotated so, a call whose written
return is `type[X]` (a library's, or a `def` of the module), or a module-level name every
write to which in its file is such a call. Another file's name is read through that file's
header (`ModuleHeader.factories`, the function each write calls: polar's `APIRouter = get_api_router_class(APIRoute)`).
Calling such a name is the `virtual <init>` of `X` with the name's field as
`receiver_field` (R37: `X` or a subclass), and its result is an `X`. **What a class call makes is
read as the typing specification reads it.** A metaclass (the class's own, or a base's) that
defines its own `__call__` decides: where the overloads the arguments choose all return a type
variable or `Self`, the result is an instance (`HTTPStatus(200)`); where one returns a class
object, the call makes a new class (`Enum("Color", "RED GREEN")`), which has no class symbol,
so the result has no type. The functional `NamedTuple(...)` and `TypedDict(...)` make a new
class too: the name they are bound to is a `new_class` (as a `NewType` is a `new_type`), which
names no type and whose call names no owner. A class of another file is constructed only
where its module binds the name to that class alone (`class Session` then `Session = Client`
is no `Session`), as the resolver reads it (`effective_calls._class_calls`). A module-level name of
another file that holds an instance is not typed in the file that reads it: a write in a
third file cannot be seen, and the resolver follows the name's writes.

**A module-level name has the type of the values written to it in its file** (design
`2026-11-06-reading-decorators-design.md` §3b): an assignment, or a `def` or `class` with
its decorators applied. Where every write gives one class (or one callable, below), a call
on the name, anywhere in the file, has that owner (`cli.group()` is `click/core/Group#`,
`_PATTERN.match(…)` is `re/Pattern#`). Two types are a closed list and give no owner,
never one of them; so does a write whose type is not known, and any binding not read as a
write (a loop or `with` target, an import, `del`, `:=`, `except … as`, a `match` capture,
`+=`, `global` in a function). A write from another file is not seen; the resolver's
field walk answers those. A call of a function the file defines stays the static call to
it. The file is read once with the writes read so far, and kept where every answer it
gave is the one all the writes give; otherwise it is read again until no reading finds a
new type for a name it asked about, at most one reading per module-level name plus one.
A name written from another module-level name of the file (`alias = module`) takes that
name's type in the same readings. Reaching the limit would be a defect in the rule (it only
ever adds a type): the file is then read once more with no module-level types, and the
uncovered list says `<file>: the types of its module-level names did not settle in N
readings, so none is written`. The analysis goes on.

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
- `for x in xs` is the call `xs.__iter__()`, then `__next__()` on its result at the head
  of every pass, and `x` is that result (OI-324): javac writes `iterator()` and `next()`
  for a for-each loop, and the facts keep the same shape. `async for` calls `__aiter__` and
  `__anext__`, and `x` has the type the awaited step gives; a comprehension's `for` is the
  same, a generator expression's `__iter__` running at once and its `__next__` when it is
  consumed. A tuple target (`for k, v in d.items()`) takes a `tuple[A, B]` of as many parts
  apart by position; any other value, or a starred name, leaves its names untyped;
- `xs[i]` is the call `xs.__getitem__(i)`. A slice is an `unresolved` argument (the
  grammar holds no slice object) that chooses a `slice` overload. Subscripting a class
  object makes a type (`__class_getitem__`), never the instance's `__getitem__` (ruling
  R37): no `__getitem__` is written for a subscript in a type expression (a class base,
  `cast`'s type, `isinstance`'s or `issubclass`'s class), nor for one of a class of this
  file, a builtin, a typing form or a library class. Where the subscripted name is one such
  class or form, the subscript is the `static` call `<form>#__class_getitem__`, one argument
  per index element in written order (plan 2026-11-08 N2): `Annotated[int, Depends(f)]` is
  `typing/Annotated#__class_getitem__` with `int` and the `Depends` call's result, and
  `list[Item]` is `builtins/list#__class_getitem__(Item)`. Where it names none or several,
  the parts are read and no call is written. A name imported from another file of the
  module may be a class too, which this file cannot see: the call is written, and the
  resolver answers a path whose receiver is the class itself `not_readable` ("a type
  form"), so no edge reaches the class's own `__getitem__`; the same holds for `__iter__`
  and `__next__` ("iterating a class runs its metaclass"). A value written `type[X]` or
  `Type[X]`, or a library result written so, is the class object too: an explicit call
  through it (`c.create()`) keeps the owner `X`, but a call syntax makes on it gets none.
  Calling a class object constructs it (R37): `cls()` in a `@classmethod` and `c()` with
  `c: type[X]` are a `virtual` `<init>` on `X`, whose dispatch is `X`'s constructor and each
  subtype's own (the class it was called through is `X` or a subclass), and whose result is
  an instance of `X`; never the instance's `__call__`. A store (`xs[i] = v`) and other operators are not calls here;
- a constructor call gives an `instance` whose `source` is the constructor's receiver;
- an f-string, or `+` with a string literal, is `concat`, filled by a `dynamic`
  `builtins/str#format` site; a list or a tuple is `array`; a function is `lambda`;
  `a if c else b` and `a or b` are `merge`; `await x` is `x`;
- arguments are written as the call writes them (ruling R27): positional ones in order, then
  each keyword one with its name in `keyword` (D00 §5); an unpacked argument is `unresolved`
  with `keyword` `*` (`f(*items)`) or `**` (`f(**options)`). The resolver binds them;
- `X.__init__(…)` names the method `<init>`, as the definition does; a `@classmethod` is
  `modifiers.static` (bound to the class, as D00 §5a defines the word), and `cls` is not a
  parameter;
- every parameter of a signature carries its `kind` (`positional_only`, `positional`,
  `var_positional`, `keyword_only`, `var_keyword`, D00 §5a);
- **a parameter carries what its default and its annotation evaluate to** (plan
  2026-11-08-python-fastapi-inbound N1, N2; D00 §5a): a `def` evaluates its defaults, then
  each annotation that is not a plain type, where it is defined, so their calls are written
  in the body that runs it (the owner's `<clinit>`, or the enclosing function for a nested
  `def`), and the parameter's `default` and `annotation_value` name them, with
  `declares_default`. An `Annotated[...]` annotation is the `__class_getitem__` call below;
  a name bound to a module-level type alias (`X = Annotated[T, ...]`, `X: TypeAlias = ...`,
  `type X = ...`, in this file or, through its header, another) is that alias's `field`, and
  the parameter's type is `T`. A `type X = v` statement is read as `X = v` is (ruling R6):
  its calls in the body, and a `field_write` of the result to `X`; Python evaluating `v` when
  it is first asked for changes when it runs, not what it is. `...` is the field
  `builtins#Ellipsis.`.

**Types the module's own code declares** (OI-324 part 2):

- **A declared return** (`def load() -> list[User]`) of a function or method of this file —
  a module-level function, or the method a class of this file defines for the receiver by C3,
  its type variables filled by the receiver's type arguments — types what is read OFF the
  call's result through a library's signature: an element (`for u in load()`), a tuple part,
  a subscript, an attribute declared on a class of this file. The call made directly on the
  result keeps its owner to the resolver, which follows the body's returns first and takes
  the declaration where they give no type (M04). A decorated name's declaration is not read:
  its call is the decorators' result. `type[X]` declared is the class object (R37).
- **A container literal is its class**, with its elements' types where every one is known:
  `[u, u]` is `list[User]`, `{"a": c}` `dict[str, Client]`, `{u}` `set[User]`, `(u, c)`
  `tuple[User, Client]` by position; a list, set or dict comprehension the same, from what
  each pass adds. Several element types are their union, never one of them; an empty literal,
  a starred element, a `**` mapping or an element of no known type gives the class alone. A
  local holding a literal (or a comprehension) is read once as written: after that it is its
  class alone, since the code it was handed to may have written to it. Writes into it
  (`.append(x)`, `d[k] = v`) are not followed. The facts still read `array` or `unresolved`.
- **A return written `Self`** is the receiver's own class, the class the call was made
  through (D00 §5a); the signature keeps `Self` as written.
- **Another file's declarations** answer as this file's do, through its header: its declared
  returns type what is read off a result (`for r in rows()`, `rows() -> Iterator[dict]` in
  another file, gives `dict` rows), its class bodies type `obj.x`, and library methods its
  classes inherit are read where the library defines them.
- **An attribute declared in a class body** (`client: HttpClient`, PEP 526, any class: a
  dataclass's, a `NamedTuple`'s, a `TypedDict`'s, a pydantic model's) is the type of
  `obj.client` where `obj`'s class is one of this file (by C3): no fact names such a read, so
  the type is the owner of a call on it. `self.client` keeps its owner to the resolver, which
  reads the object's writes first (ruling R33); what is read off it is typed from the
  declaration. A declared class that is a descriptor (it defines `__get__`, as SQLAlchemy's
  `Mapped[T]` does) gives what its `__get__` is written to return for an instance, never the
  descriptor; a class whose methods are not read may be one, so it gives nothing. A bare
  `Final` or `ClassVar` is no type. The scanner takes these types from the declaration, never
  from the same file's body or writes (logged, round 1 item 5: a callee's returns are read
  after its callers in file order, and a body that answers differently from its declaration
  gives a union, which names no owner here anyway; the resolver reads the body first).
- **`isinstance(x, C)` narrows a local** inside the body of its `if`, and `not isinstance`
  inside the `else`; `a and b` narrows each name it tests; a tuple of classes is their union.
  Past the `if`, the narrowing holds only where its body is the one path reaching the join
  (the other returned, raised, broke or continued: `if not isinstance(x, C): raise`). A write
  to the name ends it. The narrowed type wins over the name's annotation. `assert
  isinstance(...)` narrows nothing: `python -O` drops it. The value keeps every field.
- **A class's written parents keep their type arguments** in `supertype` and
  `generic_interfaces`, and a `Generic[...]` class writes its `type_parameters` (D00 §5a),
  for the resolver to map a generic class's parameters through a subclass in another file.

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
reachable. A generator has one `unresolved` return, and each `yield` is a `method_return`
marked `yielded`, numbered before it (D00 §5, N10). An `@overload` stub, and an abstract or
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
`sys.platform` test gives both branches. That holds for every read of a library file, its
names, its signatures and the facts its type headers are read from alike (ruling R22,
2026-11-08; `imports.version_test`, one rule): only the arm that Python runs is read, so
typeshed's `enum.pyi`, which defines `IntEnum` once per version range, gives the header of
the running arm, `IntEnum(int, ReprEnum)` on 3.12, not the last arm written. The test is
decided by what its name is bound to, not by its spelling: `sys.version_info` where the
module's imports bind the name to the module `sys` under any name (`import sys as _sys`),
or `version_info` where they bind it to `sys.version_info` (`from sys import version_info`);
a name an import also binds to something else is not decided (`imports.version_tests`).
The comparison is CPython's, against the whole `sys.version_info` where the environment
states it (`pyvenv.cfg`'s `version_info = 3.12.4`; the running Python's where there is no
environment): on 3.12.4 `> (3, 12)` holds and `<= (3, 12)` does not, and `>= (3, 12, 1)`
holds. Where only the minor version is known (a `site-packages` path, or a `pyvenv.cfg`
that does not state it), a test is decided only where every release of that minor version
gives one answer; `>= (3, 12, 1)` on a bare 3.12 reads both arms. The whole version is in
the libraries' fingerprint, so a micro upgrade re-reads every file.
Every pass over a library file reads the live arm only: the names it binds, its bodies, the
types of its module-level names, its declared returns and class members, and the class
statements headers are read from, so a function written once per version has the live
arm's return, never both. The module's own files are read whole, every branch.

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
  owner. An argument the scanner knows the type of (a parameter written `int`, the result
  of a typed call, a slice) is checked by class: it fits a class it is or has in its lookup
  order, and does not fit one its read order lacks unless that one is a protocol whose
  methods it all has (then the fit is not decided). A literal is never callable, so it does not fit a `Callable` parameter
  (`Group.command("analyze")` takes the overload with `*args`, not `__func: Callable`). A
  function or a class argument fits a bare `Callable`, `Callable[..., Any]`, `object` and
  `Any` (`@cli.command` with no parentheses is `Command`), and no literal type; a class also
  fits `type` and `type[Any]`. Whether it fits a listed signature (`Callable[[int], str]`),
  a written return (`Callable[..., Awaitable[int]]`) or `type[X]` is not read here, so such
  overloads stay a closed list.
- **A type variable in a library return takes the type that fills it** (OI-324; the
  typing specification's generic classes). A class's type parameters are its PEP 695 list,
  else its `Generic[...]` or `Protocol[...]` list, else the type variables of its written
  bases in order. The type written for the receiver (`list[User]`, `dict[str, Client]`,
  a class of this file `Bag[User]`) gives them by position, and each written base maps
  them on to its own (`class Users(list[User])` is a list of `User`; `dict_items[K, V]`
  is `ItemsView[K, V]`, which defines `__iter__`). The method is found in the receiver's
  class or its bases by C3 order. A method a class of this file defines is a body: the
  resolver follows it, and its declared return types only what is read off its result
  (above). `Self` is the receiver's own
  type, a subclass's where the receiver is one. A function's own type variable is the
  type of the argument whose parameter writes it, directly or through a class of the
  argument's lookup order (`sorted(Iterable[T]) -> list[T]` on a `list[User]`); a
  constructor's own `__new__` or `__init__` fills the class's parameters the same way
  (`enumerate(users)` is an `enumerate[User]`). `X | None` is `X`, as `Optional[X]` is
  (None has no method). A tuple's parameter is the union of its parts (`tuple[A, B]`), and
  `pair[1]` with a literal index is that part. The overload is chosen first; the type
  variables are filled after it. Where one is not filled (a bare `list`, `Any`, an unknown
  receiver), or two arguments fill one differently, the result has no type. On a union
  receiver the result has a type only where every member gives the same one: several
  types are never one. `List`, `Dict` and typing's other aliases of builtin and
  `collections` classes are those classes (PEP 585), and `LiteralString` is `str`.
- **A result written `Callable[[P, ...], R]` is a callable** (design
  `2026-11-06-reading-decorators-design.md` §3b, a decorator factory's result:
  `click.group()` returns `Callable[[F], Group]`). Calling it gives `R` where `R` is a
  class; where `R` is a type variable, the type of the positional argument whose parameter
  is that variable. Where that is not a class either (`option(…)`'s `Callable[[FC], FC]`
  applied to a function), the result has no type. `evidence` stays `declared`, as for
  every written type.
- **What is written of a library is its type headers, as on the JVM** (ruled A,
  2026-11-06; D00 §5 `type_header`). After the module's own files, one synthetic
  `header_only` document, `__type_headers__.jsonl` labelled `<environment>`, holds a
  `type_header` for every library type the module's facts name (a call's owner, a class
  or instance argument, a written base, a parameter or return type), then for each of its
  written bases, transitively: the defining symbol, the construct kind, the first base as
  `superclass` and the rest as `interfaces` (as a module class's), no annotation, and the
  `origin`, and for every library class a static call names as a member of its module
  (`FastAPI()` names `fastapi/applications/FastAPI#`). A named type no library holds counts
  in `type_headers_unlocated`, except such a member, which may be a function; `object` is
  the boundary and gets none. A library class whose bases are not all read gets none
  either, with a line on the uncovered list. No library member, document or `symbol` fact
  is written, so library methods are not "found" (`method_resolution` answers `external`),
  `coverage.documents` counts the module's files only, and the `symbols` view holds the
  module's own. Library signatures are used only inside the scanner, to type the module's
  own calls (above).
- **A header reads its class statement, not its module** (ruling R20, 2026-11-08). What a
  header carries (the construct kind, the written parents and whether they stop early) is
  read from the class statement alone: its bases are looked up against the names the
  module binds and, for a nested class, each outer class body's, as the module's own facts
  would look them up, so a re-export or a module attribute (`base.Speaks`) is followed to
  its defining class as before. A module is a type with no parents. The whole module is
  read, as before, only where one statement cannot say: a class name two class statements
  of the file hold (a class defined on two branches, or one of its name inside a
  function), since which one the facts keep is the whole file's question; a name no class
  statement holds is no class. The arm of a version test the environment's Python does not
  run holds no class statement, for either read. The headers are byte for byte what reading every module
  whole writes (`test_type_headers_from_class_statements_equal_a_whole_module_read`; polar
  and Sextant's own fact trees). On polar the pass went from 596 whole-module reads (45 s)
  to 8 (3 s), then 3 once version tests were decided, and a cold run from 69 s to 51 s.
- **A header carries its class body** (fact schema 12, plan 2026-11-08 task 9c;
  `structure.class_members`). The same class statement gives each name its body declares
  (typed, `static`, the value written and the call that made it, the calls in an `Annotated`
  annotation's metadata) and each function it defines (its return type and decorators), read
  against the names the class body sees, through the blocks `file_facts` reads. A value is read
  as `file_facts` reads a literal or a name, with no call-site fact to point at; a call is
  named as its call-site row would be once read as a construction where it calls a class
  (the library tells a class from a function, `Libraries._is_class`). A header answered by the
  whole-module read carries no body (not read), so the class-statement and whole-module
  headers are equal apart from it. **A class body's dict display with text keys** is written
  as the `dict(key=...)` call it builds, in the module's facts and in a header, so a
  configuration written `model_config = {...}` is read as one written `ConfigDict(...)` is.
- **An opted-in library's bodies** (`extract_libraries`, D04 §2a) are read whole, as a
  jar is: the detector reports the environment's `site-packages` as the library root of
  each named distribution the module declares and has installed, and the library's own
  scan reads exactly the `.py` files its `RECORD` lists, with no folder walk (a namespace
  folder another distribution shares gives none of the other's), into `facts/lib/pypi/<name>/`
  with `origin: <name>` and the dependency tier.

**A re-run reads only what changed** (OI-325; [D01](D01-graph-schema.md) §7 "Reuse"). The
scan stage hands the scanner what the previous scan into the same workspace recorded about
each document (`ScanRequest.previous`, one `ReuseRecord` per document), and the scanner keeps
a document's fact file where a fresh read would write the same bytes: the file's content
hash, the document's stamps, Sextant's code, the module's identity, the libraries and the
Python are the same, and so is every answer the module index gave the file (which other
files exist). A kept document adds to the report what it added the first time: its fact
count, its uncovered lines and its library notes. The library type headers are kept the
same way, while the libraries and the types every document names are the same (D01 §7
"The type headers"). An opted-in library's scan keeps nothing:
its subtree is discarded before every run. A file the scan neither keeps nor writes — deleted,
newly ignored, or no longer readable — loses its fact file, as on a first run. On polar
`server/`, a run with no file changed scans in 1.5 s instead of 14 s.

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
