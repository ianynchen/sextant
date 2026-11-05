# In-process dispatch — design note

**Status: APPROVED 2026-11-05** ("Yes, but why kotlin later? We said we want to achieve Java and kotlin complete"): every JVM kind is built on this branch; only Go waits for a Go scanner. Amends the Akka/Pekko actors design
(`2026-11-04-akka-pekko-actors-design.md`, built on `cov/akka-actors`). The user ruled **A** on
2026-11-05: the catalog pieces built for actors (`message_handlers` style, `message_sends`,
`message_class_via`) were *"invented just for one framework"* and read too close to
messaging. Make them one general mechanism that reuses existing words, prove it with a
second framework, and take Go channels into account.

## 1. The one idea

**In-process dispatch:** code hands a value to a framework or a channel, and the framework
calls the handler(s) that receive it. No address goes on a wire. It is a trace **hop**, never
an endpoint row (the self-call ruling of 2026-10-25). It is not messaging: messaging names an
address a broker or bus routes on (Kafka topic, JMS queue, event-bus address) and keeps its
endpoint rows.

Two things decide which handler receives the value:

| Key | Who receives | Examples | In `examples/` (main code) |
|---|---|---|---|
| **type** — the value's class | handlers registered for that class | Akka/Pekko `tell` → `onMessage(C.class, h)`; Spring `publishEvent(e)` → `@EventListener m(E e)`; CDI `fire(e)` → `@Observes E` | Spring 21 send / 14 listen (apollo-portal, dolphinscheduler, yudao, petclinic-genai); CDI 30; Akka 83 |
| **object** — which channel object | code that receives from the same object | Kotlin `Channel.send` → `receive`/`for (x in ch)`; Java `BlockingQueue.put` → `take`; Go `ch <- v` → `<-ch` | Kotlin Channel 8, SharedFlow 39, BlockingQueue 8 (apollo, dolphinscheduler); Go: no project yet |

And one rule says how many receive:

| Match | Meaning | Who |
|---|---|---|
| `first` | the first registration in its group that matches | Akka/Pekko behaviors |
| `all` | every registration that matches | Spring, CDI listeners; a broadcast flow |
| `one` | exactly one receiver takes each value (any of them) | a queue/channel with several consumers: a hop to each, since which one takes it is decided at run time |

## 2. Catalog words — reuse first

| Need | Word | Reused from |
|---|---|---|
| Where a value is handed over | `dispatch_sends: [{owner, method, descriptor, value_arg}]` — a catalog block any style may carry (replaces `message_sends`/`message_arg`) | the per-entry owner/method/descriptor matching `declared_call_sites` already does; `value_arg` is `body_arg`'s position |
| A call-style registration (Akka) | `dispatch_registrations: [{owner, method, descriptor, class_arg \| value_arg, handler_arg, predicate_arg?, returns_value?}]` on an ordinary `fluent` chain (roots/steps/terminal, `case` capture) | `fluent` chains and `chain_ends`; `class_arg` is the existing name for a class literal |
| An annotation-style registration (Spring, CDI) | the `annotation_driven` style with three additions: select a method by a **parameter** annotation (`@Observes`); key = the payload parameter's type (`path_fallback: payload_type`); output = a dispatch registration, not an endpoint | `annotation_driven`, `request_body` (picks the parameter), `path_from` (reads `@EventListener(classes=…)`) |
| A receive site, object key | `dispatch_receives: [{owner, method, descriptor, object: receiver, handler: enclosing \| lambda_arg}]` | the same entry matching |
| How dispatch works for the catalog | `dispatch: { key: type \| object, match: first \| all \| one }` | — (the one genuinely new setting) |
| The class a key carries (Akka service key) | `channel_via` entries may also name `class_arg`, read from the same producing call in the same walk | `channel_via` (replaces `message_class_via` and its second walk) |

No `message_*` word remains. No word names a framework.

## 3. Tables

- `message_handlers` (graph schema 15, approved 2026-11-04) is renamed **`dispatch_registrations`**:
  `group` (was `behavior`), `position`, `key_type`, `key_value`, `predicated`, `handler`,
  `delivers`, `match`. Still one new table; schema stays 15 (not yet released).
- Hops stay in `rpc_hops`, renamed **`hops`** (it already has two writers: gRPC stubs and
  dispatch). `protocol` = the catalog's protocol (`grpc`, `actor`) or `in_process` for a
  catalog with none.
- `dispatch_registrations` also carries **`key_object`**: for an object key, the producing call
  `caller#ordinal` of the channel object, from `values.producer_paths(…, which_object=True)` (the
  object-following the Vert.x client reader already uses). NULL for a type key. Still schema 15.

## 4. What changes in this branch

1. Rename the words, the table and the code (`message_handlers.py` → `dispatch_registrations.py`,
   `message_hops.py` → `dispatch_hops.py`), the docs (D01/D02, CHANGELOG, spec As-built).
2. Akka/Pekko catalogs re-expressed in the general words; their rows and hops must come out
   identical (the 33 checked on the Pekko samples, the fixture pins).
3. `channel_via` gains `class_arg`; `message_class_via` and its second walk go.
4. `reachable_handlers` gains `match: all` (and `one`).
5. **Spring application events.** `publishEvent(Object)` and `publishEvent(ApplicationEvent)` on
   `ApplicationEventPublisher` (and `ApplicationContext`, which inherits it) are sends;
   `@EventListener` and `@TransactionalEventListener` methods are registrations keyed by their
   parameter's type (or the annotation's `classes`), `match: all`. **`ApplicationListener<E>`
   implementations** are registrations keyed by the parameter type of their own
   `onApplicationEvent(E)` — the non-bridge method (a compiler bridge carries `bridge_of`, D00) —
   so no fact change is needed. Done when apollo-portal's and dolphinscheduler's publish sites
   hop to their listeners, each checked by hand, and the six field pins still pass (apollo-portal
   is one: any moved row is checked true or false).
6. **CDI events (Quarkus).** `Event.fire`/`fireAsync` are sends; a method whose parameter carries
   `@Observes`/`@ObservesAsync` is a registration keyed by that parameter's type, `match: all`.
   Checked on the Quarkus examples.
7. **Object keys: Kotlin `Channel`, Kotlin `SharedFlow`/`StateFlow`, Java `BlockingQueue`.**
   Sends: `send`/`trySend`, `emit`/`tryEmit`/`value =`, `put`/`offer`/`add`. Receives: `receive`/
   `tryReceive`/`for (x in ch)` (an `iterator()` call), `collect`, `take`/`poll`. A send hops to
   every receive site on the same object: `match: one` for a channel or queue (one consumer takes
   each value, decided at run time, so a hop to each), `all` for a shared flow. Checked on the
   koog/kotlinconf and apollo/dolphinscheduler examples.

## 5. Later

- **Go channels**, when the Go scanner lands: same tables, `key: object`.
- **Vert.x event-bus local consumers** keep their endpoint rows (they have an address); a send to
  an address the module consumes becomes a hop by the existing self-call rule.

## 6. Cost

Same as built: one chain walk per registration catalog, one value read per send. Spring and CDI
add one annotation pass each (the one `annotation_driven` already runs per catalog). Object keys
add one cached object walk per send and receive site, then a dictionary join on the producer.
