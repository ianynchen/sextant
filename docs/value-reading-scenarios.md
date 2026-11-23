# How a value is read: the scenarios Sextant handles

This is the reference for every language reader. Before a new reader (or a new framework) adds
a rule for a code shape, find the shape here. If it is here, the reader uses the same answer
and the same mechanism. If it is not here, it is a case to **bring to the user with a count
from real projects** (GUIDELINES §8.9); it is not a case to solve locally.

**How to use this file (mandatory, GUIDELINES §8.9):** before a design question goes to the
user, and before any new word, fact or rule is proposed, find the ROLE of the code shape here
— first in "Find it by role", then in the tables — and quote the row. For a framework in a
new language, first name the Java or Kotlin construct that has the same role. A question or a
proposal that does not quote the row it checked, or say "searched: no row", is not ready.

## Find it by role

| The code does this | Look at |
|---|---|
| A value comes through a helper, a return, a field, a branch | "Helpers", "Branches", "Fields, builders, callables, inheritance" |
| A list or array of values, held in a name or written in place | "Lists and arrays" |
| A route gets its prefix from a mount | "Mounts and prefixes" |
| A handler gives the request to another handler | "Which handler answers" (`shapes/pass_through.py`, catalog word `passes_on`) |
| A marker on the handler (an annotation, a decorator) states the method | "Role → existing catalog word(s)": `annotations[].method`, `method_from` |
| A class handles requests by the names of its methods | "Role → existing catalog word(s)": `dispatch`, `bypassed_by`; an override that calls its parent keeps the rows |
| A route names no method | `verbless_serves: any`; `all_methods` |
| A value is behind a call (`URI.create(x)`, `include(x)`, `X.as_view()`) | value-model forms `returns`, `returns_receiver`, `result_returns`, `result_calls`; `url_via`, `channel_via`, `identified_by` |
| Something a deployment decides | rule 8, "not evaluated" |
| Code that is not there | reasons `external`, `escapes`. A library that a project uses IS there. |

Sextant reads code. It does not run it. Each answer below is what the engine says today, with
the test that proves it. A row marked † cites a test whose name and docstring were read, not
its full body. Surveyed on `main` at 75d0018d (2026-11-23).

Short names: `values.py` = `src/sextant/application/resolve/values.py`;
`TV` = `tests/application/test_values.py`; `TM` = `tests/application/test_mounts.py`;
`FR` = `tests/application/test_fastapi_routes.py`; `FP` = `tests/application/test_fastapi_prefixes.py`.

## The answer vocabulary

A value answers as `literal`, `expression` (a template with holes), `absent` (the code states
there is no value), or `unresolved` with exactly one of six reasons (`values.py:172-184`):

| Reason | Meaning |
|---|---|
| `external` | the producer is in code that was not scanned |
| `not_readable` | the producer was scanned and nothing names its value |
| `non_enumerable` | the members of a set cannot be listed (also every cap) |
| `escapes` | the value was handed to code that can change it, and that code was not read |
| `no_writer` | no reported write of the field was found |
| `cycle` | the walk returned to a position on its own path |

Two marks on an answer: `inexact` (a URL publishes at `partial`; a channel is refused) and
`narrowed` (one of several known values).

## The ten rules

1. **The unit is the path, not the position.** A helper called twice gives one binding per
   caller, and all slots of one binding agree on the caller. Never the cross product.
   `values.py:16-28`; `TV:1953`; mounts `TM:223`; Python `FP:313`.
2. **Follow the value through all code we have**: parameters to callers, returns to callees,
   fields to their writes, a hand-off into module code. Unknown starts only where code is
   absent (`external`).
3. **Enumerable is exact.** Members that are written constants give one path each. A set that
   cannot be listed gives ONE `unresolved`, stated, never dropped and never guessed.
4. **No model of a library method's semantics.** Nothing knows what `substring`, `trim` or
   `format` does. `x` merged with `f(x)` answers the root `x`, `inexact` (`values.py:4137-4150`;
   `TV:3346`). The declared exceptions are data: `identified_by` entries in
   `catalogs/value-models/` (which argument of a producing call carries the value).
5. **A call on a branch is not a call on every path.** One branch call gives two exact rows;
   two or more make every row `partial` (`values.py:3505-3535`; `TV:6364`, `TV:6382`).
6. **A field is read per object and per write** (`TV:4428`, `TV:4441`).
7. **A value handed to code we do not have `escapes`.** An immutable value (a string) is never
   a hand-off (`TV:5562`, `TV:5599`).
8. **What a deployment can change is "not evaluated"**: the row exists and its condition is
   stated (`tests/application/test_bean_conditions.py:2826`†; Python
   `tests/application/test_fastapi_conditions.py:59`).
9. **Framework behaviour is mirrored, measured by a probe** (a refused mount gives no row).
10. **Caps answer `non_enumerable`**: 256 paths in one window, 25,000 computes per root, depth
    80 (`values.py:349-371`; `TV:6558`; `tests/application/test_walk_cost.py:170`, `:237`).

## Scenarios

### Constants and text

| Scenario | Answer | Evidence |
|---|---|---|
| Literal at the call site | `literal` | `TV:3042` |
| Class reference, enum constant | `literal`, kind `symbol`, never text | `TV:3042`, `TV:2846` |
| Field written from a constant | the constant | `tests/e2e/test_kafka_delivered.py:95` (Java); `FR:291` (Python) |
| Static field | one value for every reader | `TV:3825` |
| Concat, every part a literal | ONE joined `literal` | `TV:2981` |
| Concat, one part unknown | `expression` with the hole kept | `TV:3009`; Python prefix hole `<prefix>/x` at `partial`, `FP:410` |
| Concat hole with several callers | one answer per caller | `TV:4702`, `TV:4725`; `FP:313` |
| `${KEY}` placeholder, environment read | `expression` `${KEY}`; a key that is not a literal is `non_enumerable` | `TV:4714`†; `tests/application/test_environment_reads.py:44` (Python only) |

### Helpers

| Scenario | Answer | Evidence |
|---|---|---|
| Value passed as a parameter, one caller | the caller's value | `TV:1970`; `FR:510` |
| Several callers | one binding per caller (rule 1) | `TV:1953`; `FP:313` |
| Deep chain of helpers | followed as deep as the code goes (caps: rule 10) | `TV:3053` |
| No caller in the module | `external` | `TV:2511` |
| Recursion | `cycle` | `TV:2965` |
| Parameter left to its default | Python: the default value (`tests/application/test_values_defaults.py:43`). Kotlin bridge: a reason, never the pushed mask (`TV:3110`) | both |
| Helper returns the value | the value | `TV:2040` |
| Several returns | one path per return | `TV:1981` |
| Helper changes the value, then returns it | `escapes` for a plain value | `TV:2025` |
| Factory sets a part on one branch, then returns | two exact rows | `TV:6464` |
| Helper builds, mounts and returns a router; called twice | each route under its own caller's prefix | `TM:223`; `FP:313`, `:429` |
| A mount call inside a helper | each caller's route takes that caller's mount path | `TM:439` |
| A helper's router mounted by one caller only | both ways are served (rule 3) | `TM:389` |

### Branches

| Scenario | Answer | Evidence |
|---|---|---|
| Two literals on two branches | both, each `narrowed` | `TV:3361` |
| A literal and a non-literal | ONE `non_enumerable` | `TV:3444` |
| `x` or `f(x)` | the root `x`, `inexact` | `TV:3346` |
| A registration under a test a deployment decides | row exists, condition "not evaluated"; each call of a helper takes its own test | `tests/application/test_fastapi_conditions.py:59`, `:260` (Python only) |

### Lists and arrays

| Scenario | Answer | Evidence |
|---|---|---|
| Every element a written constant | one path per element | `TV:1990` |
| Empty list, explicit null | `absent` | `TV:2946` |
| One member has no name | the readable members plus ONE trailing `not_readable` | `TV:2000` |
| The array was not read at all | ONE `non_enumerable` | `TV:2049` |
| Varargs, `List.of("a","b")` | one array argument; one row per element | `TV:2767`, `TV:2746` |
| Unpacked argument (`*rest`, `**options`) | the parameter it may fill is `not_readable`, not the default | `tests/application/test_values_defaults.py:93` (Python only) |
| **A list held in a module name, used later** (`VERBS = ['get']`, `methods=VERBS`) | TODAY: not read, `unresolved` (`FR:547`, `:567`, Python only). **RULED 2026-11-23, not built yet:** the list is read when its exact values are known; an alteration we can see (`+=`, `.append`, `.extend` of known values) does not make it unknown. Only a list whose exact values are not known keeps a reason | ruling; the two tests change with it |

### Loops

| Scenario | Answer | Evidence |
|---|---|---|
| A value built in a loop | `not_readable`; the facts carry no "this was a loop" claim | rule at `values.py:4337-4341`; **no test** |
| A setter after the use, in the same loop | two rows: unset `resolved`, set `partial` | `TV:6581` |
| A comprehension | recorded as a loop (flow only) | `tests/ingress/extract/python/test_flow.py:303` |

### Fields, builders, callables, inheritance

| Scenario | Answer | Evidence |
|---|---|---|
| Field assigned from a constructor parameter, class built twice | one row per construction | `tests/e2e/test_kafka_delivered.py:61` |
| Constructor that nothing calls | `external` | `TV:2218` |
| Field read on an object from outside | `external`; never another object's value | `TV:3792` |
| Builder handed to a helper in the module | the helper's calls join the chain | `TV:5522` |
| Builder handed to code we do not have | `escapes` | `TV:5562` |
| Chain started in a helper, sent by the caller | one row, the caller's | `tests/application/test_call_engines.py:7102` |
| Lambda body reads a captured value | the captured value | `TV:2247` |
| Handler as a method reference with two implementations | one `narrowed` row each | `tests/application/test_pass_through.py:971`† |
| A decorator written in the module that returns its function | walked into; handler `resolved` | `FR:438` (Python only) |
| A library wrapper a value model states (`functools.wraps`) | `result_returns` / `result_calls` in `value-models/python-wrappers.yml` | model file |
| A library decorator no model states | row `partial`, handler NULL, question `handler_pass_through` | `FR:602` |
| Inherited mappings | each concrete class's rows, each with its own prefix | `tests/e2e/test_rest_inbound_delivered.py:2059`† |

### Mounts and prefixes

| Scenario | Answer | Evidence |
|---|---|---|
| Mount with a string prefix | the router's routes serve under it | `TM:290`; `FP:45`; `tests/application/test_flask_prefixes.py:29` |
| Nested mounts | prefixes compose, outermost first | `TM:315`; `FP:83` |
| **A mount of a router the module does not build** (a library's router) | **adds nothing: no prefix, no row, no question** | `TM:270`; `FP:266` |
| A router that is never mounted | served at its own prefix | `FP:249`; `TM:270` docstring |
| A router mounted twice | one row per mount | `FP:231` |
| A router handed in as a parameter and mounted here | one object; served under the mount only | `TM:485` |
| A prefix that cannot be read | the named hole `<prefix>/x` at `partial`, question `mount_prefix`; never the empty prefix | `FP:410`; Java `TM:552`† |
| A mount the framework refuses | no row, or the refusal is recorded (rule 9) | `TM:449`, `TM:528`; `FP:161` |
| A router factory in another file; a router subclass | the prefix is held | `FP:125`, `FP:335`; `TM:562`† |
| A call that returns its receiver | the same router | `TM:462` |

### More rows of the same rules

| Scenario | Answer | Evidence |
|---|---|---|
| A field written from a constant the walk has no literal kind for | `not_readable`; the site is kept | `TV:2304` |
| Concat with no part filled | `expression`, the template verbatim | `TV:2972` |
| Compiler-inserted `String.valueOf(obj)` in a concat | passed through only for an identity that yields an authority (`value-models/jdk.yml`, `preserves: authority`) | `TV:2555` |
| One position reached two ways | two bindings, two paths | `TV:3062` |
| Return through an interface with two implementations | listed as a branch, neither picked | `tests/application/test_return_flow.py:145` |
| Return through a call whose dispatch nothing names | `not_readable` (not `external`) | `TV:2057` |
| One branch read twice (`p + "/x/" + p`) | `(/a,/a)` and `(/b,/b)`, never crosswise | `TV:3395` |
| A value below the top level of an argument handed out | `escapes` | `TV:5780` |
| An object built again each time round a loop | unset row exact; set row `partial` | `TV:6625` |
| For-each over a Kotlin channel | a receive (dispatch, not a value) | `tests/application/test_dispatch_kotlin_channels.py:94`† |
| No reported write of a field | `no_writer` | `TV:2206` |
| A setter on an object of unknown origin | the value is kept, `inexact`, beside the exact one | `TV:4506` |
| A field written from a call's result | the walk crosses to the call; a library factory is `external` | `TV:2325` |
| An undeclared call ON the value before its use | `escapes` | `TV:2072` |
| Declared configuring calls, calls that return their receiver | they join the value's chain in order | `TV:2162` |
| A hand-off with two callees | two paths, one chain each | `TV:5611` |
| A symbol answer past a hand-off (identity is not content) | survives `escapes` / `cycle` | `TV:2090`† |
| A send helper that sets the address itself | row `partial` | `tests/application/test_call_engines.py:9259` |
| A value stored in a field inside the body, or captured by a lambda that acts | `escapes` | `TV:5592` |
| A producer the identity table names (`URI.create(..)`) | the producer's own argument is the value | `TV:2598`, `TV:2618` |
| A handler object whose class is not scanned | `external`; scanned with no handler: `not_readable` | `tests/application/test_pass_through.py:564`† |
| A lambda as the VALUE of an argument | `not_readable` | `TV:2937` |
| A bound method reference | the target's parameter is `external`, never the captured receiver | `TV:2295` |
| A wrapper (Java) that calls what it wraps through an interface a lambda implements | `escapes`; through an interface no lambda implements: walked into | `TV:5801` |
| `next()` on a received context (Vert.x) | passes the request on | `tests/application/test_pass_through.py:662`† |
| A handler declared as a module type | runs every override below it | `tests/application/test_pass_through.py:472`† |
| A router built in a base class, routes added in an override, mounted by a third method | served under the mount | `TM:177` |
| A parameter the container fills (DI recipe) | the recipe's return; a recipe in unscanned code is `external` | `tests/application/test_fastapi_depends.py:90` |

### Dispatch (existing, not a value walk)

| Scenario | Answer | Evidence |
|---|---|---|
| Dispatcher keyed by message class (Akka) | a send reaches the first matching registration | `tests/application/test_dispatch_registrations.py:187`† |
| Dispatcher keyed by object (a queue) | linked when it is one object | `tests/application/test_dispatch_objects.py:92`† |

## Which handler answers

When a framework hands a request to a handler and that handler gives the request it received
to another handler, the row belongs to the handler that answers
(`src/sextant/application/resolve/shapes/pass_through.py`). There are three outcomes, each
about one handler:

- it **passes on**: the request it received is handed to the next handler, in its own body,
  in a module method it calls, or in a lambda that captured it;
- it **answers**: its body is read and nothing above is reached;
- it is **not readable here**: the request is handed to code that is not read, or stored
  where the walk cannot follow it. The row is `partial`.

Tests, in `tests/application/test_pass_through.py`:
`test_a_next_on_the_received_context_passes_on`,
`test_a_context_handed_to_another_handler_passes_on_with_it`,
`test_a_context_handed_to_a_body_outside_the_module_is_unreadable`. Vert.x states the call
with the catalog word `passes_on`. A Django view that calls another view with its `request`
has the same role (ruled 2026-11-23).

## Catalog-level roles (survey of 2026-11-23)

Every row names the existing word and one catalog line. The survey read the catalogs and the
format document; a test named here is a name match unless a table above cites it.

### Role → existing catalog word(s)

| role | word(s) | style | example |
|---|---|---|---|
| method fixed by the registration call | `captures.http_method: GET` | fluent | `src/sextant/catalogs/flask.yml:44-45` |
| method fixed by the rule | `verb: GET` | combinator | `src/sextant/catalogs/ktor-routing.yml:313` |
| method fixed by the annotation type | `annotations[].method: [GET]` | annotation_driven | `src/sextant/catalogs/spring-mvc.yml:163` |
| method from an attribute of the annotation | `method_from` | annotation_driven | `src/sextant/catalogs/spring-mvc.yml:116`; `src/sextant/catalogs/quarkus-reactive-routes.yml` `method_from: methods` |
| method from a keyword/list argument | `http_method: { keyword, absent, case }` | fluent | `src/sextant/catalogs/flask.yml:43` |
| method from one argument (enum/field) | `http_method: argN` + `verb_values.fields` | fluent | `src/sextant/catalogs/vertx-web.yml:111-112, 66-97` |
| method from one argument | `verb_arg` + `verb_values.{fields,getters}` | combinator | `src/sextant/catalogs/ktor-routing.yml:255, 282-300` |
| method added by a later chained call | step `captures.http_method` + `repeats` | fluent | `src/sextant/catalogs/vertx-web.yml:173-174` |
| method set for a whole nested block | prefix rule with `verb_arg` | combinator | `src/sextant/catalogs/ktor-routing.yml:254-255` |
| method = handler's method name | `dispatch: [{name, parameters, method}]` | supertype_dispatch | `src/sextant/catalogs/jakarta-servlet.yml:123-144` |
| no method -> closed list, one row each | `all_methods: [...]` | annotation_driven, combinator | `src/sextant/catalogs/spring-mvc.yml:157`, `src/sextant/catalogs/ktor-routing.yml:237` |
| no method -> ONE row "any" | `verbless_serves: any` (column `method_kind`) | fluent, annotation_driven | `src/sextant/catalogs/vertx-web.yml:51`, `src/sextant/catalogs/quarkus-reactive-routes.yml:56` |
| no method at all, never fanned out | `verb: none` (+ `registered_verb`) | combinator | `src/sextant/catalogs/ktor-routing.yml:334-335` |
| empty method list is an error | (engine) `refused_registration` / `no_methods` | fluent | `src/sextant/application/resolve/engines/fluent.py:1324-1326` |
| no path -> every path | `pathless_serves` | fluent | `src/sextant/catalogs/vertx-web.yml:55` |
| route text is a regex | `url_is: pattern` / `pattern_from` (column `path_kind`) | fluent / annotation_driven | `src/sextant/catalogs/vertx-web.yml:114`, `src/sextant/catalogs/quarkus-reactive-routes.yml:62` |
| framework refuses a path with no `/` | `refuses_unrooted_path` | fluent | `src/sextant/catalogs/vertx-web.yml:61` |
| handler = argument | `handler: argN`/`{arg, keyword}`; `handler_arg` | fluent; combinator | `src/sextant/catalogs/flask.yml:56`; `src/sextant/catalogs/ktor-routing.yml:313` |
| handler = decorated function | step `{ method: __call__, captures: { handler: arg0 } }` + value-model `result_returns` | fluent | `src/sextant/catalogs/flask.yml:61`, `src/sextant/catalogs/value-models/flask.yml:15` |
| route with no handler | `handler: none` | combinator | `src/sextant/catalogs/spring-cloud-gateway.yml:152` |
| handler object -> which method runs | `handler_methods` | fluent | `src/sextant/catalogs/vertx-web.yml:347` |
| middleware passes on | `passes_on`, `framework_handlers` | fluent | `src/sextant/catalogs/vertx-web.yml:311-314, 338` |
| chain call that reads nothing | `continuations[].pass_through: true`; capture-less step with `returns_receiver: true` | combinator; fluent | `src/sextant/catalogs/spring-cloud-gateway.yml:172`; `src/sextant/catalogs/vertx-web.yml:233` |
| class handler: entry point replaced | `bypassed_by` | supertype_dispatch | `src/sextant/catalogs/jakarta-servlet.yml:182-186` |
| class handler: inherited mapped methods | `mapping.inherit_unoverridden` | annotation_driven | `src/sextant/catalogs/spring-mvc.yml:102` |
| prefix on the class | `prefix_annotation` + `prefix_from` + `path_separator` | annotation_driven | `src/sextant/catalogs/spring-mvc.yml:106,110,158` |
| constant prefix | `path_prefix` | annotation_driven | `src/sextant/catalogs/spring-actuator.yml:89` |
| prefix by a nesting block | `vocabulary.prefixes[]` (`path_arg`, `body_arg`/`subtree_arg`) | combinator | `src/sextant/catalogs/ktor-routing.yml:250-251` |
| prefix by mounting a router object | `router_type` + `mount[]` (`router_arg`, `prefix_arg` \| `prefix_from: receiver_path`) | fluent | `src/sextant/catalogs/vertx-web.yml:288-301`, `src/sextant/catalogs/flask.yml:99-105` |
| prefix held by the router's constructor | `router_holds[]` | fluent | `src/sextant/catalogs/fastapi.yml:136-140`, `src/sextant/catalogs/flask.yml:83-85` |
| mount prefix replaces the held one | `prefix_replaces_own: true` | fluent | `src/sextant/catalogs/flask.yml:102` |
| how prefix + path join | `path_join: leading_slash \| concatenate \| single_slash`; `path_separator` | fluent/combinator; annotation_driven | `src/sextant/catalogs/fastapi.yml:156`, `src/sextant/catalogs/flask.yml:78`, `src/sextant/catalogs/ktor-routing.yml:186`, `src/sextant/catalogs/spring-mvc.yml:110` |
| mount on a host | `host_arg`; step `collects: {kind: host,...}` | fluent | `src/sextant/catalogs/fastapi.yml:154-155`; `src/sextant/catalogs/vertx-web.yml:189-190` |
| framework refuses a mount/prefix | `refuses: [...]` | fluent | `src/sextant/catalogs/fastapi.yml:144` |
| same object across statements | `returns_receiver: true` | fluent step, value model | `src/sextant/catalogs/vertx-web.yml:174` |
| value behind a producer call | `url_via`, `channel_via`, value-model `identified_by` | fluent, single_call | `src/sextant/catalogs/vertx-webclient.yml:118` |
| value behind a DI bean | `bean_via` | fluent | `src/sextant/catalogs/spring-integration-amqp.yml:114` |
| receiver made by a call | `request_reads[].via` | all inbound | `src/sextant/catalogs/flask.yml:129` |
| chain result consumed as an argument | `terminal_via_argument`; `via_argument_of` + `continue` | fluent | `src/sextant/catalogs/okhttp.yml:92`; `src/sextant/catalogs/spring-integration-amqp.yml:126` |
| annotation on the method that BUILDS the chain | `method_annotation: {annotation, arg, into}` | fluent root | `src/sextant/catalogs/spring-integration-amqp.yml:120-121` |
| request parameter marker | `request_params[]` (annotation or marker call) | annotation_driven, fluent | `src/sextant/catalogs/spring-mvc.yml:73-96`, `src/sextant/catalogs/fastapi.yml:181-208` |
| request read in the body | `request_reads[]` | all inbound | `src/sextant/catalogs/jakarta-servlet.yml:91-93` |
| route demands a header/param | `request_requirement`, `request_requirement_attrs` | combinator, annotation_driven | `src/sextant/catalogs/ktor-routing.yml:258-259`, `src/sextant/catalogs/spring-mvc.yml:149` |
| two handlers on one address is an error | `mapping.duplicate: conflict` | annotation_driven | `src/sextant/catalogs/spring-mvc.yml:127` |
| route disabled / removed | `serves` capture, `poisons` | fluent | `src/sextant/catalogs/vertx-web.yml:194-199` |
| automatic HEAD/OPTIONS | NO word; stated boundary, not published | all | C |
| router named by a string / module / class | NO word | — | E (NOT FOUND) |
| decorator/annotation on the handler changes a fluent/combinator route | NO word | — | A(vii), L (NOT FOUND) |

### Words that have the same role under different names

1. `url_is: pattern` (fluent) = `pattern_from: [attr]` (annotation_driven). Evidence: D02 `:2475` "(`annotation_driven` spells the same marker `pattern_from`, an attribute list; the column is `path_kind`.)"; `src/sextant/catalogs/quarkus-reactive-routes.yml:57-62` "Same row Vert.x Web's `getWithRegex` derives."
2. `verbless_serves: any` in `matches` (fluent) = `mapping.verbless_serves: any` (annotation_driven): the SAME word, one validator (`src/sextant/application/resolve/shapes/inbound_routes.py:93-106`: "the word `fluent` and `annotation_driven` catalogs share"). The combinator style has no equal; it has `all_methods` (fan-out) and `verb: none`.
3. `all_methods` under `mapping` (annotation_driven, `src/sextant/catalogs/spring-mvc.yml:157`) = top-level `matches.all_methods` (combinator, `src/sextant/catalogs/ktor-routing.yml:237`, `src/sextant/catalogs/spring-cloud-gateway.yml:124`): same name, same role, different place and different readers (`sql:628` vs `src/sextant/application/resolve/engines/combinator.py:620`).
4. `captures.http_method: <LITERAL>` (fluent) = `verb: <LITERAL>` (combinator) = `annotations[].method: [..]` (annotation_driven) = `dispatch[].method` (supertype_dispatch). Four names for "this entry pre-sets the method".
5. `captures.http_method: argN` (fluent) = `verb_arg: N` (combinator) = `method_from: <attr>` (annotation_driven): "read the method from a position". Value tables: `verb_values` is shared by fluent (`src/sextant/application/resolve/engines/fluent.py:3902`, top of `matches`) and combinator (`src/sextant/application/resolve/engines/combinator.py:618-619`, under `vocabulary`): same word, two places.
6. `captures.handler: argN` (fluent) = `handler_arg: N` (combinator). `handler: none` (combinator) has no fluent twin (fluent: no `handler` capture / every handler passes on -> no row).
7. `captures.url: argN` (fluent) = `path_arg: N` / `path: ""` (combinator) = `path_from` / `path_from_siblings` (annotation_driven) = `address: {annotation, args}` (supertype_dispatch).
8. Prefix: `prefix_annotation`+`prefix_from` (annotation_driven) / `vocabulary.prefixes[].path_arg` (combinator) / `mount[].prefix_arg` + `router_holds[].prefix_arg` (fluent) / `path_prefix` constant (annotation_driven).
9. Join rule: `path_join` (fluent, combinator) vs `path_separator: "/"` (annotation_driven, `src/sextant/catalogs/spring-mvc.yml:107-110`: "joins a class prefix to a method path with exactly one `/`") — the same behaviour as `path_join: single_slash`.
10. `url_via` = `channel_via` = value-model `identified_by` (D02 `:635-639`, `src/sextant/application/resolve/shapes/chains.py:2695-2698`: "one grammar, `{owner, method, arg}`, two positions").
11. `pass_through: true` (combinator continuation) ~ a capture-less fluent step with `returns_receiver: true`: both mean "a call in the chain that carries it on and reads nothing". NOT the same as `passes_on` (which handler answers) or the `handler_pass_through` question. Three different things share the words "pass" / "through".
12. `request_requirement` (combinator rule) = `request_requirement_attrs` (annotation_driven) = step `collects: {kind, name, value}` (fluent): "the route declaration demands this of the request".
13. `inherit_unoverridden` (annotation_driven) vs the supertype_dispatch member union over scanned intermediates (`src/sextant/application/resolve/engines/supertype_dispatch.py:179-189`, no word): both answer "a handler declared on a scanned base class serves under the subclass".
14. `terminal_via_argument` (on a terminal) vs `via_argument_of` + `continue` (on a root/step): the same join (chain result -> argument of a named call), declared from the two ends (`src/sextant/application/resolve/shapes/chains.py:2870-2874`: "`via_argument_of` without `continue` would be an execute-join on a root, which `terminal_via_argument` already is").


## Cases with no rule today

No rule and no test exists for these. Each is a decision for the user, taken with a count.

| Case | Example | Seen in |
|---|---|---|
| A registration call inside a loop | `for r in REDIRECTS: urls += [path(r.old_url, ...)]` | **RULED 2026-11-23: not supported.** Counted in 14 Python projects: about 15 places, 9 over a run-time registry, 6 over written values (zulip 4, redash 1, home-assistant 1), and the zulip ones need more than the loop. The row keeps its reason and a question names the line; no rule enumerates the loop |
| A map or dict as a value source, a lookup by key | `handlers[request.method]`; `Map.of(...)`; `switch` | zulip `rest_path`: 259 routes, 731 method pairs |
| A `**kwargs` parameter (the left-over keywords) | `rest_path("realm", GET=f, PATCH=g)` | zulip, same 259 routes |
| A copy of a collection | `list(x)`, `List.copyOf(x)` | zulip: 95 pairs |
| A transforming call used directly as the value | `old_url.lstrip("/")`, `String.format(...)` | zulip redirects |
| A constant read from another class (Java) | `Other.TOPIC` | no test found |

## Known disagreements in the code's own text

- `values.py:38-43` says "There is no cap"; `values.py:349-371` defines three caps.
- `values.py:5463-5466` says an environment read's default is never read;
  `tests/application/test_environment_reads.py:1-4` says it renders as `${KEY:-default}`.
- A hand-off into a library named in `extract_libraries` is stated as followed
  (`docs/superpowers/specs/2026-11-02-per-path-truth-design.md` rule 1); no walk-level test
  was found.
