# Follow the object — eight fixes before Vert.x

**Status: RULED 2026-10-30, for planning.** Every ruling below is the user's, made one finding
at a time on 2026-10-30. Built **before** the Vert.x Web/WebClient work
(`2026-10-30-vertx-web-design.md`, branch `cov/vertx`), which depends on rulings 1, 4 and 5.

## 1. Why

The Vert.x spec review found three places where the design read a value without the object
or the call path it belongs to. The user asked (2026-10-30): *how many places have we done
this wrong in the existing code?* Three independent reviewers then audited the resolver:
the chain/tree engines, the value walk, and every other engine. Each finding below was
confirmed by a throwaway test unless marked "by reading".

**The principle, as the user stated it:** a value is read by following the call graph and
the OBJECT it belongs to, with its calling context. One factory called twice is two objects;
two calls on one object are one object; a helper's parameter is the argument at the call it
came through. A thing is identified by what it IS, never by an attribute a later step can
change.

**Anti-goals:**
- No fix that detects a mixed answer instead of removing the cause ("removing the cause
  beats detecting it").
- No fix shaped to one catalog where the defect is general ("generalize before
  special-casing").

## 2. The eight rulings

### Ruling 1 (Critical) — a field's value is read per object, not per field name

**Defect.** `values.py` `_binding` (~2477) answers a field read with every write to that
field anywhere in the module (`writers` / `constants` / `produced`, keyed by the field
symbol). `Row a = new Row(); a.setCron("A"); Row b = new Row(); b.setCron("B");
one(a.getCron())` answers `{A, B}`, exact. `pair(a.getCron(), a.getZone())` crosses two
objects' setters. A field written in two methods and read twice pairs `(h1, h2)`. Shape
present in ruoyi-vue-pro (`WebProperties` builds two `Api` objects).

**Ruling: build the second half of the 2026-10-18 sixth-edge spec's step 2 now.**
- A widened `field_write` fact carrying `from_value` (the instruction index of the value
  stored), as that spec's §1 step 2 specifies.
- Receiver-aware field resolution: where the walk knows the read's receiver came from
  construction A, the read answers A's writes only.
- Graph schema bump, shared with ruling 7. Fixtures rebuilt on JDK 21; the six field pins
  and `measure_value_walk.py` re-run on the same corpora state.
- §4's `setTopic("a"); setTopic("b")` over-report on one object is in scope if the same
  fact answers it; otherwise it stays logged.

### Ruling 2 (Critical) — a value id always travels with its method

**Defect.** Value ids are per-method numbers. `chains.py` `_captures_of_body` (~1986) folds
a lambda body's captures into the enclosing chain; only `parameter` arguments are stamped
with their own method (`_own_parameter`, ~2141). `arguments.py`
`_properties_getter_expression` (~1186) then looks a lambda's bare `source` id up in the
ENCLOSING method's call sites. `uri(b -> b.path(other.compute("k")))` beside an unrelated
`props.getUrl()` with the same id published `GET ${billing.url}` at `resolved`. The bean
hop (`_fold_bean_captures`) lifts captures the same way (by reading).

**Ruling: wherever captures are lifted out of another method (lambda bodies, the bean
hop), stamp every argument with the method it belongs to, and make every reader of a value
id look it up in that method.** A guard fails any lifted argument without its method.

### Ruling 3 (Critical) — a configured prefix applies to the rows its dispatcher serves

**Defect.** `catalogs/server-models/spring-boot.yml` declares
`[server.servlet.context-path, spring.mvc.servlet.path]` for protocols `http, sse`, and
`path_prefix.py` (~137) applies them to every inbound row of that protocol.
`spring.mvc.servlet.path=/api` turned a `@WebServlet("/legacy")` into `GET /api/legacy` at
`resolved`; Spring serves `/legacy`. Same mechanism (by reading) for Jersey rows and for a
WebFlux module carrying a leftover servlet key.

**Ruling: each prefix key names the dispatcher it prefixes, and each inbound catalog names
the dispatcher that serves its rows; a row takes only its own dispatcher's prefixes.**
- `server.servlet.context-path` → every servlet-container dispatcher;
  `spring.mvc.servlet.path` → the DispatcherServlet only.
- Catalog tags such as `dispatcher-servlet`, `servlet`, `jersey`, `reactive`.
- A key/dispatcher pairing is declared only once a probe measures it; Jersey's
  `spring.jersey.application-path` and the actuator's management port stay undeclared, and
  unprefixed, until then.
- The same shape serves Quarkus (`quarkus.http.root-path` / `quarkus.resteasy.path`) and
  Micronaut.

### Ruling 4 (Major) — a call that returns its own receiver configures it, in both walks

**Defect.** The forward chain walk (`chains.py` `_walk`, ~725) forks on sibling calls that
share a receiver unless they are void; the backward walk
(`producer_paths(along_receivers=True)`, used by `scheduled_chain`) goes from `build()`
straight to the root and never sees separate statements on the variable. Confirmed:
- OkHttp `b.url(u); b.post(body); newCall(b.build())` published `GET`, path NULL,
  `unresolved` (true: `POST u`);
- Quartz `tb.withIdentity("x"); tb.withSchedule(cronSchedule(…)); tb.build()` published a
  simple trigger with no name, `partial` (true: `DEFAULT.x`, cron);
- an AWS SQS `SendMessageRequest.builder()` held in a variable lost its queue.

By reading: JDK `HttpRequest.Builder`, `MessageBuilder.setHeader`, a Spring Integration
spec held in a variable. The fork also drops a WebClient response shape: an `onStatus` fork
derives first, and the real row is deduplicated away.

**Ruling: build the `returns_receiver: true` step flag (Vert.x spec §3a item 5) once, in
BOTH walks, and flag every shipped catalog's builder methods that return `this`.**
- The forward walk folds such a call like a void call. The backward walk, at a declared
  call, also gathers the flagged calls made on the same receiver value before it, in
  ordinal order.
- Each method gets the flag only after `javap` or its Javadoc confirms it returns `this`;
  never from memory.
- Candidates: OkHttp `Request.Builder`, JDK `HttpRequest.Builder`, Quartz
  `TriggerBuilder`/`JobBuilder`, AWS SDK v2 request builders, Spring `MessageBuilder`,
  Spring Integration specs, the WebClient/RestClient specs.
- Each catalog gets a fixture row written in the variable style.

### Ruling 5 (Major) — a builder returned from a helper is followed across the return

**Defect.** The forward walk stays inside one method, so
`Builder base() { return SendMessageRequest.builder().queueUrl(q); }` with
`sqs.sendMessage(base().messageBody(m).build())` has a root without a terminal in one
method and a terminal without a root in the other: no row. Same for an OkHttp builder from
a helper. Shape in Mesh's test helpers (`UpgradedApiClient.java:74-110`).

**Ruling: build the Vert.x spec §3d cross-method walk as a general `fluent` capability,
and pin it beyond Vert.x.**
- Where a terminal's receiver reaches no root in its method, walk back across returns and
  parameters with `producer_paths(along_receivers=True)` to the root.
- Fold the captures of every method on that path, including ruling 4's flagged siblings.
- Each caller of a shared helper gets its own values (path-aware, as everywhere above).
- Fixture rows for an SQS helper and an OkHttp helper, beside Vert.x's
  `newQueryRequest(…).send()`.

### Ruling 6 (Major) — string concatenation keeps every calling context

**Defect.** `values.py` (~1669, `settled`) keeps only the contexts where a concatenation
operand answered a string literal; contexts answering unknown or `${key}` are dropped.
`fetch(String host){ get("http://" + host + "/x"); }`, called once with `"svc-a"` and once
with an unbound parameter, answered one exact `http://svc-a/x`. That defeats
`authority_of`'s several-peers refusal and loses config keys. `values.py` (~2029) already
states the rule this violates: "a path this entry cannot carry is REPLACED, never dropped".

**Ruling: apply that rule to concatenation holes; every calling context produces its own
template.**
- A literal fills the hole.
- A configuration expression fills it as `${key}`.
- An unknown leaves the hole unfilled: named `{param}`, or `<host>` where it leads the
  address (the `OI-152` ruling).

Field-pin and value-walk movements are expected; each is reviewed before it is accepted.

### Ruling 7 (Major) — an endpoint row has a stable identity

**Defect.** The combinator's `route_requirements` stash is keyed on the path as minted.
`apply_path_prefixes` (`pipeline.py` ~253) rewrites `endpoints.path`, and
`record_request_requirements` (`request_requirements.py` ~127) then joins on the path, so a
route's header/query requirements vanish once a prefix applies. `config_join` writes the
same stash. Rows are matched by mutable columns throughout;
`prefix_endpoint_paths.sql` notes `(protocol, direction, method, path)` is not unique.

**Ruling: every endpoint row gets a stable id when it is minted, and every later pass that
matches rows (the requirements stash, the prefix rewrite, `reclassify_protocol`,
`stamp_format`, and any other) matches on it.** The schema bump is shared with ruling 1.

### Ruling 8 (Major) — a controller's inherited, non-overridden mappings are its rows

**Defect.** `effective_annotations.py` (~431) takes candidates only from methods a class
itself declares. `abstract class CrudController<T> { @GetMapping("/list") list() }`, with
`@RequestMapping("/orders") OrderController` and `/products ProductController` extending it,
publishes nothing. Spring serves `/orders/list` and `/products/list`. If the base is itself
a mapped controller, only its own `/base/list` appears. Overridden methods already get the
right subclass prefix; nothing is crossed, rows are only lost.

**Ruling: each concrete handler class's candidates include the mapped methods it inherits
and does not override, as the framework's own scan finds them.**
- Spring: `MethodIntrospector` walks the bean class, its superclasses and its interfaces.
- The row's handler is the declaring method; the subclass supplies the prefix and the bean.
- Applied to every annotation catalog on this engine, each switched on only after a probe
  confirms its framework dispatches inherited methods (DR-6).
- `(subclass, path)` rows that share one handler stay distinct through shapes, dedup and
  ruling 7's row id.

## 3. Order

Each step is its own branch and PR, following the per-item loop: failing fixture first,
gate, review, Critical and Major findings fixed, the rest recorded, then commit.

| Step | Ruling | Why here |
|---|---|---|
| 1 | 7, stable row id | The schema others build on; ruling 8 needs distinct rows per handler |
| 2 | 2, value id with its method | Small and local; removes a `resolved` lie |
| 3 | 6, concatenation keeps every context | Value walk only; pins move, reviewed |
| 4 | 1, field per object (`from_value`) | Extractor and schema; the largest step |
| 5 | 4, `returns_receiver` in both walks | Vert.x depends on it |
| 6 | 5, cross-method fluent walk | Builds on 4; Vert.x depends on it |
| 7 | 3, prefix by dispatcher | Independent; before Vert.x adds more inbound rows |
| 8 | 8, inherited mappings | Independent; uses step 1's row id |

Then Vert.x Web/WebClient, whose spec takes rulings 4 and 5 as built rather than as its own
work.

## 4. Recorded, not fixed (Minor)

These were found by the same review. Each is logged in Plane with the open-issues id map,
and none is triggered by real input today.
- **A writer's parameter is read in the reader's frames** when the writer is on the current
  stack (`values.py` `_binding_writes`). A variant of ruling 1, which may close it.
- **The dead-write filter drops only uncalled private methods** (`values.py` ~627). A
  private method called only by another dead one still publishes its writes.
- **The walk memo key omits frames** (`values.py` ~1134), which can go stale under
  recursion. Not observed.
- **The `fluent` dedup key keeps the first object's shapes and metadata.** Mostly closed by
  ruling 4.
- **The backward prefix walk misses a base URL set as a statement on a held builder**
  (`WebClient.builder()` then `b.baseUrl(…)`). Closed by ruling 4 if the flag reaches
  `_prefix_captures`.
- **The installed prefix is chosen from the handler's declaring type**, not the controller
  class, for an `@HttpExchange` interface default method (`path_prefix.py` ~597).
- **`config_join` picks binding candidates by method name across every class**, first
  symbol winning, with no `@Bean` check (~526).
- **Row presence is decided per class, not per bean** (`schema.sql` `symbol_beans` /
  `endpoint_conditions`): two `@Profile` beans of one class both read as present. By
  reading; ruling 1 is its prerequisite.

## 5. Predictions — to verify, not to trust

- Ruling 1: ruoyi-vue-pro's `getAdminApi().getPrefix()` reads answer `/admin-api` only.
- Rulings 4 and 5: the confirmed probes above become fixture rows, each with the true row.
- Ruling 6: some field-pin sites gain a second answer; each is reviewed.
- Ruling 7: a prefixed functional route keeps its requirement.
- No other pinned corpus output moves except where a ruling says it should. Each movement
  is explained in its PR.
