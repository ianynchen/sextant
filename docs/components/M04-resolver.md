# M04 — Resolver

## Purpose

Turn facts into a graph.

The largest module, because everything between "what was observed" and "what can be
rendered" happens here — and none of it knows a language exists.

## Interface

```
Resolver
  resolve(workspace, model, catalogs, overlays) -> ResolveReport
```

One implementation. Its internals are staged, but the stages are private — they are not
plug-in points and not commands.

**Where the code lives.** The resolver is `application/resolve` — core computation, not an
adapter. It talks to the workspace only through the `Workspace` port; the SQL bodies of the
named derivations it orchestrates live in `storage/duckdb` as the implementation of
[D01](D01-graph-schema.md). The semantics and the ordering are owned here; the dialect is
owned there.

The module is **language-blind by construction**: it reads facts and catalogs, and branches
on capabilities, never on names. An architecture test asserts that no language name appears
in it.

## Inputs

Facts from [M03](M03-scanner.md). The `RepositoryModel` from [M02](M02-detector.md).
Catalogs ([D02](D02-catalog-schema.md)). Claims from [M01](M01-overlay.md).

## Output

Every derived table in [D01](D01-graph-schema.md), and a report of what could not be
resolved. As its final act, `analyze` writes `metadata.json`
([D05](D05-manifest-and-state.md)) — the workspace's self-description, stamped by the
pipeline that computed it so an agent never finds it absent or describing a previous graph.

## Behaviour

Six passes, in order. Each reads what the previous produced.

### 1. Load

Facts into the workspace, **in bulk**. Per-row insertion across a fact set is a defect
(NFR-11): the difference is orders of magnitude — minutes against seconds on a real fact
set.

Only changed documents are reloaded, by delete and reinsert on `document_id`. Everything
after this pass is **rebuilt whole** — a derived row is a join across files, and adding one
implementation of an interface invalidates dispatch edges in files that did not change.

### 2. Configuration resolution

**Every profile found, not one.** A module analysis is not tied to an environment — the
expensive work before and after this pass is identical across all of them, so resolving each
profile once is the only sensible arrangement. `resolved_config` carries an environment
column; consumers select.

Layer configuration by profile, then resolve placeholders, including placeholders whose
values contain further placeholders.

**Endpoints keep the expression, not the value.** A listener on `${orders.topic}` stores that
expression; what it resolves to in each environment lives here. Only hosts and topic names
vary by environment — protocol, path template, gRPC method and payload shapes come from code
and do not — so making the whole endpoint environment-scoped would over-react to a variation
touching two fields.

A key that cannot be resolved is recorded as unresolved **with a reason and an environment**.
*Unresolved for `prod`, resolved for `dev`* says the profile is incomplete; a bare
"unresolved" suggests the code is unreadable. And a value that was redacted is a different
reason from a value that is missing, or somebody goes looking for a setting that is there.

**The per-environment peer join is a query, not a write.** `resolved_peers` answers, for
every client-side endpoint and every environment, what that row's own address expression
substitutes to: every placeholder filled from `resolved_config` for that environment by the
one placeholder rule (`resolve/config.py::substitute`, so `${key:default}` takes its
default), never a rewrite of the endpoint row itself. It is `resolve/resolved_peers.py`.

### 3. Symbol graph

Intern identifiers, build containment and its closure, build the type hierarchy, and
materialise the edge kinds [D01](D01-graph-schema.md) keeps.

The four type-reference edge kinds are built here — a substantial fraction of the graph,
kept deliberately. They exist for blast radius, which is on the requirement list; they are
exactly the kinds a diagrams-only tool would drop as unused.

### 4. Dispatch resolution

For each call site, the set of method bodies that could run.

| Opcode | Result |
|---|---|
| Static, constructor, private, super | Exactly one target |
| Virtual or interface | Every non-abstract subtype of the owner declaring a matching method |
| Virtual constructor (Python only: `cls()`, `c()` with `c: type[X]`) | `X`'s constructor and each known subclass's own constructor, one each (`narrowed`), plus `external` where a lookup order leaves the scanned code; the result is an instance of each class. A call or subscript that syntax makes on a class object (`X[...]`, `for _ in X`) never binds to the instance's method: it is a type form or the metaclass's method, answered `not_readable` (ruling R37) |

Then narrowed by **rapid type analysis**: a candidate survives only if the program creates
an instance of that type somewhere. This removes a large part of the noise for about a
hundred lines. **In version 1, by sign-off 2026-08-27** — added from the start rather than
after the graph becomes unreadable.

**VTA — variable type analysis — is the recorded next tier**, deferred from version 1 but
expected to be needed: it narrows per call site by what can actually flow to the receiver,
removing RTA's one-`new`-anywhere-keeps-it-everywhere imprecision. Two things make the
upgrade cheap when it comes: the candidate-set shape in [D01](D01-graph-schema.md) is
already per-call-site, so VTA changes the contents of `dispatch` rows and nothing
downstream; and Go's toolchain ships VTA natively, so language two will exercise the shape
before the JVM implementation exists.

**The tier follows from the indexed boundary, not from judgement.** If nothing outside the
indexed set can extend or implement the type, the set is complete — `narrowed`. If the type
is visible outside it, `partial`. The boundary is [M02](M02-detector.md)'s classpath
tiering, which is why that tiering is load-bearing rather than an optimisation.

The tier lives on the **call site**. It says how much is known about the call; it does not
rank candidates.

Java's own resolution rules have to be respected: the superclass chain before interface
default methods, bridge methods so a generic override is not missed, package-private
methods overridden only within a package.

**One lookup order per type** (`resolve/dispatch.py` `Dispatch.lookup_order`, spec
2026-11-06 §3b). Which type declares the method a call names is the first type in the
owner's lookup order that declares it. The order is one of two named rules, chosen by the
module fact's `lookup` (D00 §5, DR-6):
- `jvm` — JVMS 5.4.3.3: the class, its superclass chain to exhaustion, then the
  superinterfaces breadth-first, then `java/lang/Object`; constructors and static
  initializers are not inherited. An unread type is a position in the order that is never
  asked; the first one is the boundary.
- `c3` — Python's method resolution order: C3 linearization over the written parents, in
  written order (`superclass`, then `interfaces`), then `builtins/object`. `__init__` is
  inherited. A library type is placed by its `type_header`, and the order ends at it,
  since its methods are not read. A parent not read (`parents_unread`, or a type with
  neither facts nor a header) ends the order where it would come in, as far as the order
  is certain without it. A hierarchy C3 cannot order is only the class itself.

Where the order ends at an unread type, the lookup answers `external` with that type in
the detail (`method_resolution`); where it read every type and none declares the method,
`not_readable`.

**Receiver binding** (`resolve/receiver_binding.py`, spec 2026-11-06 §3b). A `virtual` call
whose facts name no owner (D00 §5) is bound from what produced its receiver, on the value
walk (`values.producer_paths`, `which_object`): a construction to its class, a call to what
its callee returns, a parameter to the arguments at its callers, a field to its writes. Each
path the walk reaches the receiver by is one row of the derived table `bound_receivers`
(`caller`, `ordinal`, `path_id`, `owner`, `evidence` `syntax`, `resolution`, and `reason`/
`detail` where the path names no type) — per path, never combined (ruling M-1). Several types
from a closed list are `narrowed`; a path that ends without a type is `external` (a parameter
nothing in the scanned code calls), `escapes` (a parameter of a function the module hands on
as a value, or a path that crossed out of one) or the walk's own reason, and the site's bound
rows are then `partial`. It never writes a fact: `call_edges` reads the fact's owner where it
names one and these rows' where it does not, one edge per owner, evidence `syntax`; a site
nothing bound is one row with no target, `unresolved`.

**Calling a function value runs that function** (ruling R29, task 9a fix round 2). The walk
binding a `__call__` asks what a call of the value runs (`producer_paths(..., functions=True)`):
a path that ends at a function value (a `lambda` argument: a `def` passed or returned, a
decorator that hands its function back) ends naming its body, and the call is an edge to
exactly that body, the rule a JVM call on a lambda's functional interface reaches the lambda's
body by (`call_edges._edge`'s `dynamic` lookup; the row keeps the site's `virtual`). No owner
is written to `bound_receivers` for such a path: it has no row there, and counts in the site's
tier as one more thing the call may run (a function on one path and a `Runner` on another are
two edges, `narrowed`). Every other reader keeps a function value as a body and not a value
(ruled 2026-09-22), and an f-string (`concat`) is never one (R19b). The bodies reach
`call_edges` from the binder in memory and are stored in no other table (ruling R31): nothing
redraws `call_edges` after binding, which `tests/architecture/test_call_edges_drawn_last.py`
holds (two callers, the pipeline's first draw and the binder's, the binder's last).

**A library call a value model states hands back an argument** (`returns_argument`, D02 §1f,
design 2026-11-06-reading-decorators §3d/§3e, task 9b). The walk reads it where a value's
producer is that call (`values._Walk._stated_value`): `returns: N` is the call's argument N;
the result of a `__call__` whose receiver a `result_returns: N` call made, in the same method,
is that `__call__`'s argument N (a decorator stack: `@click.option(...)` applied to a function
is the function); and, for the call reader only, a value a `result_calls: N` call made stands
for its argument N where that is a function (`@functools.cache def f`: `f()` runs `f`). The
binder also walks a `__call__` whose owner the facts name and whose body no edge reaches — a
library type's: `_lru_cache_wrapper`, or a parameter written `Callable[...]` — for function
bodies alone, by ruling R29: its owner stays the facts', it gets no `bound_receivers` row, and
each function is an edge beside the library edge (`call_edges._with_wrapped`). `values.decorators_passed` names the stated decorators a
registration's argument passed, by the same rule, for the engines that read them.

Two readings the walk applies for a call one file cannot know, both inert on the JVM:
- **a static call naming a type is its construction** (`effective_calls`): the file that
  writes `Session()` for a class imported from another cannot see it is a class, so the call
  `app/a#Session` reads as `special` `<init>` on `app/a/Session#` where the workspace holds
  that type, and its `result` is an instance of it;
- **a binding nothing writes that names a type is that type** (`values._Walk._named_type`):
  an imported class used as a value is read as a module field (`app/a#Session.`), declared as
  no field.

A call whose owner the facts leave out returns, on each path, what the method its bound type
runs returns (`values._Walk._bound_returns`), so a chain through such calls binds in one walk.
A receiver that is a parameter whose written type is a union (`Session | Client`) is each
member, one row each, `narrowed`; a `None` member is left out and the detail says so, and a
union holding the unknown type or the root type is no closed list.

**What the code declares answers where what it runs does not** (OI-324 part 2, the type
reader `producer_paths(..., declared_types=True)`, which only receiver binding uses). A
call's result is what its callee's body returns, path by path, first; a return path the body
answers with no type, and a method with no body (a `Protocol`'s, an abstract one), answer
with the method's declared return (`signature.returns`): the one the path's body declares,
else the one the method the call names declares on the receiver's class (its lookup order's
first). A read of an attribute takes its writes first (ruling R33's namespace); a write the
walk reads no type of, a write by code not scanned, and no write at all (a dataclass's
generated `__init__`) take the declarations of that attribute on every type of the namespace
(`client: HttpClient`, PEP 526). Each class of a declared union is one row, `narrowed`; such a
row's `evidence` is `declared`. A declared type answers only where it names a class the
workspace knows (a class of the module or a type header): `Any`, the root type, a type
variable left unfilled, an alias another file assigns or a re-export path is no answer. A
type variable of the class that declares the method is filled through the receiver's class:
its written parents' type arguments (`supertype`, `generic_interfaces`) map each generic
ancestor's `type_parameters`, up every parent (`_Walk._mapping`); two parents giving one
class two different arguments fill nothing. Three things a declaration does not settle are
not read from one: a call syntax makes (`__call__`, `__getitem__`, `__iter__`, `__next__`,
`__aiter__`, `__anext__`) on a declared value, since the facts write `type[X]` as `X` and a
class and an instance differ there (ruling R37) — `not_readable`, with a detail; the call of a
decorated name, which is its decorators' result; and a function reached through a `__call__`
on a value, whose result is the wrapper's. A path whose body answers from code not scanned
(`return Mock()`, `external`) keeps that answer beside the declared rows, so the site is
`partial`: the declaration may not hold on it. **A return written `Self`** is the class the call
was made through, on each path: the owner the walk bound for the receiver (`Order.from_session
(s)` is an `Order`, though `Order` is another file's class bound by the resolver), or, for a
call on the method's own receiver (`self.m()`, `cls.m()`), that class and each subclass, one
row each (R37's list); the body (`return cls(...)`) is not read for it. **A parameter's callers
answer first**, path by path (round 2; round 1's "a written parameter type is that type" gave a
wrong `resolved` where a caller passes a subclass, a structural implementation or a mock, and is
withdrawn): where any caller path ends with no value — no caller, `external`,
`not_readable`, `non_enumerable`, `cycle`, any reason but `escapes` (ruling R40, round 3) — that
path keeps its row and the classes the parameter is written to hold stand beside it, `declared`,
so the site is `partial`. The written type is the code's own statement and replaces nothing; it
holds on every path into the parameter, so it is one row per class on the parameter's own path,
not one per open path (the path cap counts them). An `escapes` path has a value, changed after
it was made, and gains nothing. An attribute's declaration answers only where its
class is one of the module whose lookup order is read and defines no `__get__` (a descriptor's
read runs `__get__`, and a library class's methods are not read here).

**Each parameter's and binding's paths upward are worked out once** (ruling R39, round 2;
`walkbug-report.md`). A parameter's answer, and a binding read plainly (not on an object, not
unseen, outside an object walk), is the set of its paths upward, worked out once per `(position,
frames)` on the empty path and joined onto every path that reaches it by the coherence rule
(`_combine`): a path that chose another context than the prefix already chose is dropped, as
the walk dropped it at that crossing, so the paths are the same and stay apart (M-1). The
receiver reader keeps these sets on the index (`ValueIndex.suffixes`), shared by every site of a
round and emptied with each round's new index; every other reader keeps its own. An answer
resting on a position still being worked out (a cycle) is not kept, as before. **`PATH_CAP`
bounds the work, not only the answer**: a parameter's loop over its callers and a binding's
writes stop once past 256 paths, `non_enumerable`, so the work is positions × 256 rather than the
paths through them (polar's `self.session` was 833,097 paths over 4,655 parameters, 48 distinct
ends, about 13 s per site and per round; a 2 × 18 lattice of 262,144 paths now resolves in
0.2 s). A set past the cap now closes where it is built rather than at the window above, so a
`non_enumerable` row can sit lower on a path than before: on the six JVM field pins and on polar
no answer changed; on Sextant's own tree five unbound sites in the recursive walk code keep the
same reasons on fewer path rows.

**Arguments are bound by name** (ruling R2, user ruling A) where the module's lookup rule is
`c3`, by Python's calling rule over each parameter's `kind` (D00 §5a): positionals fill the
positional parameters in order and the rest go to `*args`; a keyword fills the positional or
keyword-only parameter of its name and the rest go to `**kwargs`; after a `*` argument no
later positional's place is known, and a `**` argument may fill any parameter left
(`values.parameter_slots`), the one calling rule: the scanner writes arguments as written
(R27). **A call that fills no argument for a parameter passes its `default`** (Python's
rule, plan 2026-11-08-python-fastapi-inbound Task 4, rulings R15 and R16), on that caller's
path: the parameter's `default` (D00 §5a) is resolved in the frame of the body that runs the
`def` (`values.defining_body`), with the rest of that body as its `escapes` window. `= None`
is `absent`, so the type reader adds no declared type beside it (R40 adds one only beside an
open path); the answer carries `null`, so a receiver read there says the value is None, where
an empty collection (`()`, `[]`, also `absent`) says it is one. A parameter a call's unpacked argument may fill is not left to its default
(`values.unpacked_may_fill`): a `*` value may fill a `positional_only` or `positional`
parameter, a `**` mapping a `positional` or `keyword_only` one. That path, a parameter with no
default and a `*args`/`**kwargs` parameter are `not_readable` on that caller's path, naming
the parameter. No JVM parameter has a `default`.

**The body that runs a `def`** is read from the naming rule D00 §5a and M03 state, since no
fact names it (ruling R15): a name with no `$` (a module function or a method) is run by its
owner's `<clinit>`, the module or class body; `outer$inner` by `outer`; `lambda$<m>$<n>` by
`<m>`, where `static` is `<clinit>` and `new` is `<init>`. A Python name holds no `$`, so the
split is exact; where a function named `static` or `new` and the body that name stands for
are both declared, the body is not known and no default is read.

**Parameter markers** (`resolve/parameter_markers.py`, N1, N2, ruling R14): for each
parameter, the call that produced its `default` and the call that produced each element of
its `Annotated` metadata (the static `__class_getitem__` call of `typing/Annotated#` or
`typing_extensions/Annotated#`, R8, after its first argument, flattened where that argument
is itself such a form), in written order, one `Marker` per path: `order` is the element's
written position among the metadata, and `path` the index of the path it was read on, so
markers on one path hold together and two paths stay alternatives. Each value is read through
`values.producer_paths`, so an alias in a module field or another file's field, an alias of an
alias, a helper returning the call and each write of a field are followed; a path ending
anywhere but a call (a literal, a construction, a value the walk cannot read) gives no
marker. The producer reader keeps two ends at two library calls apart (`Answer.made_by`), as
it keeps two ends at two parameters apart. Built once per `ValueIndex` and kept on it, as
the walk's upward paths are: the index reads derived tables, so `Workspace.once` cannot hold
it, and the function takes the index, so it cannot be asked before the catalog-aware index
exists. It names no framework; which marker calls mean what is catalog data. A constructor is bound by its `__init__`'s parameters, as any callee. A method called
through its class — a `static` call on a class, or a call whose receiver is a name that is a
class (`Base.__init__(self, x)`, `H.use(h, x)`) — to a method that takes `self` is handed
`self` as its first positional argument (`values.call_slots`); a classmethod or staticmethod
takes none. A parameter no edge binds is `external` only where no call in the module names its
method; a method that never returns normally has no body the edges reach, and its parameter is
`not_readable`, saying so. Every JVM argument is positional, slot for slot.

A bound call becomes an edge, and an edge is a caller, so binding runs in rounds until one
binds nothing new, at most eight; a receiver still unbound when the eighth round bound
something is `not_readable "receiver of <name> not followed after 8 rounds"`. After the first
round only a site whose walk read the callers of a method a newly bound call reaches is walked
again (R25), over the walk's index with those callers added from the same dispatch answer;
`call_edges` is drawn once more after the last round. The table is the one a whole re-walk
over `call_edges` redrawn each round leaves (`bind_until_settled(incremental=False)`, measured
equal on polar).

**None of the above is built.** The pass as designed — `dispatch`, `dispatch_site`, RTA
narrowing, the indexed-boundary tier — does not exist in `src/`, and neither does the
`edges` layer it would sit beside. What DOES exist is 2Q `G3`'s subset
(`resolve/return_flow.py`): the same opcode table above, applied per call site to answer
which method a returned value came from, with the two tiers this repository's closed set
already has (`resolved` for one candidate, `narrowed` for several) and **no rapid type
analysis** — a candidate is not filtered by whether the program constructs its type
anywhere. So its `narrowed` sets are wider than this pass's would be, never narrower, and
the difference is over-report rather than a wrong answer. It is a duplicate of this rule
the day the designed pass lands, and is recorded as one (`docs/open-issues.md`, OI-16).

### 5. Endpoints, in two halves

**The halves exist because shapes and endpoints depend on each other**, and the naive
ordering deadlocks: a shape is a type that crosses a boundary, so you cannot know which
types are shapes until endpoints are found — but an endpoint is not complete until its
shapes are attached.

**5a. Find the boundaries.** Catalog engines run in a fixed order: inbound, then outbound,
then reclassification. A path a module both exposes and calls keeps TWO rows (F5 §6.1,
W27) — merging them asserted that the thing called is the thing served — and a
`self_exchange` question names each side and its address so a reader can settle it. Each
endpoint records its protocol, wire identity, handler and/or caller, and the **type
references** of its request and response — not yet their contents.

**One style runs last, because it depends on pass 2's own output.** `config_join`
([D02](D02-catalog-schema.md) §2d) joins a bean's own name to the configuration key that
names its destination, so it cannot run until `resolved_config` exists — pass 2, not a
scanner capability, is what gates it (a PIPELINE-declared capability, D02 §1). Within the
outbound/inbound ordering above, every `config_join` catalog runs after every other style.

**A base address may also climb to configuration.** Where a catalog declares
`field_sources` ([D02](D02-catalog-schema.md) §2j), an outbound engine reads a DECLARED
base address — a directly-read field, a constructor-injected value, an
`@ConfigurationProperties` class — through to the same `resolved_config` table, so the
address a builder composes is an expression the per-environment peer join (§2's
`resolved_peers`) can answer, rather than one this stage leaves NULL.

**Every catalog whose required capabilities are unmet is skipped and reported.** This is the
mechanism that keeps a weaker scanner visible instead of silently producing a shorter
catalog.

**5b. Expand the shapes**, rooted at exactly those type references — after **unwrapping
envelopes by catalog rule** ([D02](D02-catalog-schema.md) §2a): `Mono<ResponseEntity<T>>`
roots at `T`, and the `semantics` peeled on the way there (`async`, `optional`,
`http_envelope`) are what settle presence and protocol reclassification. They are also what
a consumer reads to judge structural performance risk — the scenario formerly numbered FR-14,
which W51 moved out of the requirements because Sextant reports the structure and never ranks
it. The paragraph beginning **"No findings are computed here, and none ever were"**, forty-odd
lines below, states that correction in full — cited by its own words rather than by a line
number, which is what this wave's ratchet was written to encourage.
That chain is consumed where it is produced rather than stored on the endpoint: it describes
the route to the payload, not the contract, and everything it decides already has a column of
its own — a second copy could only ever disagree with them. An undeclared wrapper is left
unwrapped and reported, never guessed at. Fields resolved to **wire identity** — the
serialised name after any naming strategy or explicit annotation, or the field number where
the format makes a number the identity. **Required-ness comes from presence machinery and
from nothing else** ([D00](D00-fact-schema.md) §5b): a wrapper the catalog declares
`optional` is what makes a field omittable. A nullability annotation answers the other
question — Bean Validation's `@NotNull` constrains the value at validation time and says
nothing about whether the field may be absent — so reading one as a presence rule publishes a
`required` nobody declared. Expansion follows nested types transitively, and stops at
platform types.

Where a format publishes compatibility rules, those rules are applied rather than
reimplemented. A hand-rolled approximation would disagree with what the runtime actually
does, which is worse than not answering.

**5c. Attach** each shape to the endpoint that rooted it.

Rooting expansion at boundary types rather than expanding everything also bounds the cost: a
service has tens of contracts and thousands of types.

### 6. Trace summaries and findings

Traces are **not materialised** — the named query `trace_of` computes each walk on demand
([D01](D01-graph-schema.md)), because storing traces would copy every shared subtree once
per endpoint that reaches it. What this pass builds is `trace_summary`: one row per inbound
endpoint with hop counts, services involved, terminal counts by kind, and endpoints reached
more than once — the numbers findings need without walking everything. It also denormalises
each call site's control-flow position onto its `calls` edge, which is what lets the walk
run from the graph alone.

**Every terminal kind has a named producer.** `outbound_call` from the endpoint engines;
`returns` and `ends_silently` from the method descriptor; `unresolved` from dispatch;
`cycle` from the walk; `persistence` and `async_handoff` from **catalog classifications**
([D02](D02-catalog-schema.md) §2b), applied here to call sites; `throws` from the scanner's
throw-site facts. A terminal with no producer would be a decorative enum value — the audit
that added this sentence found three.

**No depth bound.** A trace is a subgraph, so its size grows with the code reached, not with
branching. It stops at a terminal — and `cycle` is a terminal detected during the walk, a
correctness requirement rather than a limit.

**No findings are computed here, and none ever were** (W51). This paragraph read *"Findings
are computed here rather than in the renderer, so M09 can serve them too — refactor findings,
design findings, and structural performance risk"*, and nothing in `src/` computes any of
them. They were FR-11 … FR-14, and the user has ruled they are not requirements of Sextant at
all: they are things a consumer DERIVES from what Sextant reports. `REQUIREMENTS.md` states
them as usage scenarios now, each naming what it waits on.

**A symbol is reported unreachable only where no `unresolved` call site exists in the scope
searched.** Otherwise the finding is withheld and the unresolved site reported instead. A
dead-code claim is the most dangerous output on the list, because acting on it deletes
something.

## What it must not do

- **No code.** Facts are the only input describing a codebase.
- **No language names.** Enforced by test.
- **No framework logic.** Engines interpret catalogs; a framework name never appears in
  code here.
- **No prose.** Names and purposes are overlays applied at render.
- **No materialised blast radius.** It is a query.
- **No patching of derived tables.** Rebuild whole.

## Honesty obligations

- Counts by resolution tier, which are how much of this graph to trust.
- Every catalog skipped, and the capability that was missing.
- Configuration keys unresolved, distinguishing redacted from missing.
- Call sites `unresolved`, grouped by reason — and an `external` site whose code is in a
  classpath entry that failed to resolve reported separately, because it is the only one
  fixable with a setting.
- Findings withheld because of unresolved sites in scope.

## Open decisions

| Decision | Blocks |
|---|---|
| Whether findings is one table with a kind column or one per family | [D01](D01-graph-schema.md) |
| How a trace crossing an `async_handoff` is recorded — stop, or continue on the other side | FR-6 |
| Whether shape extraction follows types into third-party signatures without limit | Graph size |
