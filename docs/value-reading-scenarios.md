# How a value is read: the scenarios Sextant handles

This is the reference for every language reader. Before a new reader (or a new framework) adds
a rule for a code shape, find the shape here. If it is here, the reader uses the same answer
and the same mechanism. If it is not here, it is a case to **bring to the user with a count
from real projects** (GUIDELINES §8.9); it is not a case to solve locally.

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

### Dispatch (existing, not a value walk)

| Scenario | Answer | Evidence |
|---|---|---|
| Dispatcher keyed by message class (Akka) | a send reaches the first matching registration | `tests/application/test_dispatch_registrations.py:187`† |
| Dispatcher keyed by object (a queue) | linked when it is one object | `tests/application/test_dispatch_objects.py:92`† |

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
