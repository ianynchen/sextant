# Quartz — design

**Status: DRAFT 2026-10-29, self-reviewed, all questions ruled; awaiting approval** (branch `cov/quartz`). Plane SEXTANT-177,
Java/Kotlin framework order 2 (`docs/COVERAGE.md` "Priority order"). Moves COVERAGE §5.12's
Quartz row from `◐ partial, 0/1` to ✅, and takes `quartz` off the ```delivery Async row
(`docs/java-kotlin-delivery-list.md:63`). The Async cell does not reach ✅ from this item:
`akka-pekko-actors` (order 4) stays on that row.

## 1. The rulings (2026-10-28)

| # | Question | Ruling |
|---|---|---|
| 1 | Corpora | **Pull open-source projects, as usual.** No user codebase. |
| 2 | Schedules kept in a database table | **Stop at the dispatcher.** *"We don't assume we can read the database. Leave the schedule as a value unknown. The scheduling part should be a partial."* Seed SQL in the repo is not read. |
| 3 | Several triggers on one job | **Each trigger is its own entry,** *"so that user is aware there are multiple triggers for the same job."* |
| 5 | Telling two entries on one job apart | **A: by the trigger's own name,** the way Quartz identifies triggers (`TriggerKey`). OI-183 (`@Schedules`) stays open. |
| 7 | A branch between literals in the value walk (2026-10-29) | **`narrowed`, with its candidates.** Changes the 2026-10-21 merged-values answer for a merge with no common root whose candidates are all literals; every consumer of the walk sees it. |
| 6 | How it is built | **Holistically.** *"We shouldn't be building these as separate pieces. Call chains are the same, assignments are the same."* Quartz reuses the chain, value and trace machinery every other catalog uses (§3d). |
| 4 | Non-cron schedules | **The builder chain, as written.** No English summary: that needs an LLM (optional in Sextant) or a template per builder method ([one rule, not one parser per method], 2026-10-21). *"We want deterministic logic where applicable."* |

## 2. Measured first

### 2a. The six corpora

All cloned shallow into `examples/` (git-ignored).

| Corpus | Commit | Form | Trigger sites in `src/main` |
|---|---|---|---|
| `spring-boot`, `smoke-test/spring-boot-smoke-test-quartz` (sparse) | `6922eaa` | **in code:** `@Bean JobDetail` + `@Bean Trigger`, joined by `forJob(name, group)` | 5 |
| `quartz`, `examples/` module | `741ccc3` | **in code:** builders passed together to `scheduler.scheduleJob(job, trigger)`; also `quartz_data.xml` | many (15 examples) |
| `RuoYi-Vue` | `13db1fc` | **database table** `sys_job`, seeded by `sql/ry_*.sql` | 1 |
| `ruoyi-vue-pro` | `ac022b1` | **database table** `infra_job`, seeded by `sql/*/ruoyi-vue-pro.sql`; ~25 `JobHandler` beans picked by name | 2 (infra + iot) |
| `NBlog` | `b8e537c` | **database table** `schedule_job`, seeded by `blog-api/nblog.sql` | 1 |
| `aurora` | `07e9524` | **database table** `t_job`, seeded by `aurora-springboot/sql/aurora.sql` | 1 |
| `dolphinscheduler` | `21968bc` | **database table**, rows made by users at runtime, none seeded | 1 |

**Every real application keeps its schedules in a database table.** Only the two official
samples write them in code. In the table form the code holds exactly one `JobBuilder` chain
and one `TriggerBuilder` chain: the cron is an argument read off a row object
(`job.getCronExpression()`), and the job class is a generic dispatcher that looks its target
up by a name from the same row (a bean name, or a string like `ryTask.ryParams('ry')`).

### 2b. Bytecode, from the smoke test

Compiled with JDK 21 against `spring-boot-starter-quartz` (Spring Boot 4.0.0) in a scratch
Maven module. Each chain arrives in order inside one method, with constant arguments:

```
everyTwoSecTrigger():
  invokestatic  TriggerBuilder.newTrigger()
  ldc "helloJob"; ldc "samples"
  invokevirtual TriggerBuilder.forJob(String, String)
  ldc "sampleTrigger"
  invokevirtual TriggerBuilder.withIdentity(String)
  invokestatic  SimpleScheduleBuilder.simpleSchedule()
  iconst_2
  invokevirtual SimpleScheduleBuilder.withIntervalInSeconds(int)
  invokevirtual SimpleScheduleBuilder.repeatForever()
  invokevirtual TriggerBuilder.withSchedule(ScheduleBuilder)
  invokevirtual TriggerBuilder.build()

helloJobDetail():
  ldc class SampleJob
  invokestatic  JobBuilder.newJob(Class)
  ldc "helloJob"; ldc "samples"
  invokevirtual JobBuilder.withIdentity(String, String)
  …usingJobData, storeDurably, build
```

Two facts the design depends on:
- **The schedule builder is a nested chain,** the argument of `withSchedule(...)`, not a step
  of the trigger chain.
- **Named constants are gone.** `Calendar.TUESDAY` compiles to `iconst_3`, and
  `atHourAndMinuteOnGivenDaysOfWeek(3, 0, 1, 2, 3, 4, 5)` compiles to an `Integer[]` built
  element by element. The recorded chain says `3`, not `TUESDAY`.

### 2c. The real dispatchers are spread across methods

Found by the builder check and confirmed in the sources. In every real corpus, the trigger, the
job and their pairing are in different methods, and sometimes in different classes:

| Corpus | Job class | Trigger | Paired by |
|---|---|---|---|
| RuoYi-Vue, aurora | a helper `getQuartzJobClass(job)` returns a ternary of two class literals (`QuartzJobExecution` / `QuartzDisallowConcurrentExecution`, both inheriting `AbstractQuartzJob.execute`) | in `createScheduleJob`; the cron builder passes through a helper `handleCronScheduleMisfirePolicy(job, cb)` | `scheduler.scheduleJob(jobDetail, trigger)` |
| ruoyi-vue-pro | `newJob(JobHandlerInvoker.class)` in `addJob`; the IoT manager's `newJob(jobClass)` takes a parameter | built and returned by a private `buildTrigger(...)` | `scheduleJob(jobDetail, trigger)` in `addJob` |
| dolphinscheduler | `QuartzJobDetailBuilder.build()`: `newJob(ProcessScheduleTask.class)` | `QuartzCornTriggerBuilder.build()`, another class; the schedule builder comes from a factory call | `scheduleJob(jobDetail, Sets.newHashSet(trigger), true)` |
| NBlog | as RuoYi | as RuoYi; plus `updateScheduleJob` rebuilds an existing trigger with `trigger.getTriggerBuilder()…build()` for `rescheduleJob` | `scheduleJob(jobDetail, trigger)` |

So a rule confined to one method finds no job for any real application. The value walk
(`resolve/values.py`, spec 2026-09-22) already crosses returns, parameters and callers, and the
standing rule is to follow a value as far as anything Sextant parses. §3 uses it.

## 3. What changes

### 3a. One entry per new trigger

Each `TriggerBuilder.newTrigger()` root in the module's own code, followed forward to its
`build()`, is one entry in `scheduled_work`. A trigger rebuilt from an existing one
(`trigger.getTriggerBuilder()`, for `rescheduleJob`) is the same trigger with a new schedule,
not another one, so it is not an entry (NBlog's `updateScheduleJob`). A `newTrigger()` chain
whose job and schedule kind are both unknown says nothing and is not derived.

| Column | Value |
|---|---|
| `handler` | the method Quartz runs for the job (§3c), or NULL where the job is not found |
| `trigger` | the schedule kind (§3b), or NULL where it is not found |
| `expression` | the schedule (§3b), or NULL where it is not a value in the code |
| `resolution` | `resolved` when handler and expression are both known and the expression holds no placeholder; `unresolved` when the only gap is a `${…}` placeholder; `narrowed` when the job class is one of several on a branch and they reach different handlers (§3c); `partial` otherwise |
| `evidence` | `compiler` |
| `catalog_id` | `quartz` |

### 3b. The schedule

The argument of `withSchedule(...)` is followed with the value walk to the root of its own
builder chain, across returns and helpers.

**Kind.** The catalog maps the root's owner to the kind:

| Root owner | `trigger` |
|---|---|
| `org.quartz.CronScheduleBuilder` | `cron` |
| `org.quartz.SimpleScheduleBuilder` | `simple` |
| `org.quartz.CalendarIntervalScheduleBuilder` | `calendarInterval` |
| `org.quartz.DailyTimeIntervalScheduleBuilder` | `dailyTimeInterval` |

Where the walk ends before a root (a helper whose body passes the builder through, a factory in
a jar), the kind is read from the **declared type** of the value that reached `withSchedule`:
the return type of the call that produced it, as the descriptor states. A helper declared to
return `CronScheduleBuilder` produces a `cron` schedule whatever it does inside. That is a fact
the compiler wrote, not a model of the helper. Only a value typed as the interface
`ScheduleBuilder` leaves the kind NULL.

**Expression.**
- **`cronSchedule(String)`:** the string the walk finds, verbatim, exactly as `@Scheduled(cron
  = …)` is recorded today. Steps after the root (`withMisfireHandling…()`, `inTimeZone(…)`) are
  not part of it, as they are not for `@Scheduled`. An `@Value` field or parameter gives its
  `${…}` expression, `unresolved`, and `resolved_schedules` picks it up with no change there.
- **Every other root, including the other `CronScheduleBuilder` factories:** the whole chain,
  written as `root(args).step(args)…`: method names as compiled; constants as their literal text
  (strings quoted, numbers in decimal, a class literal as its simple name, an array as its
  elements); a nested builder argument written the same way
  (`startingDailyAt(TimeOfDay.hourAndMinuteOfDay(9, 0))`). Ruling 4.
- **Any argument the walk does not resolve to a constant** (`job.getCronExpression()`, a value
  read from a row): the expression is NULL and the row is `partial`. Ruling 2.

### 3c. The job

The trigger's job is found from whatever pairs them, as Quartz pairs them. The value walk
runs backward, so each pairing call is the starting point: from its arguments the walk reaches
the `build()` of a trigger chain and of a job chain. A `newTrigger()` chain no pairing call
reaches is still an entry (§3a), with its job unknown.

The pairing calls are the `fluent` engine's existing **execute-join** (`terminal_via_argument`,
`_JoinFilter`): a built value handed to the call that consumes it, the shape that already
pairs an SQS request with `SqsClient.sendMessage(request)`. The join is within one method
today. Here it finds its arguments through the value walk, which lets it cross methods; that
is a change to the join, so it applies to every catalog that uses it.
1. **`Scheduler.scheduleJob(JobDetail, Trigger)`:** the walk from the trigger argument reaches
   this trigger's `build()`, and the walk from the job argument gives the `JobDetail`.
2. **`Scheduler.scheduleJob(JobDetail, Set<Trigger>, boolean)`** and
   **`scheduleJobs(Map<JobDetail, Set<Trigger>>, boolean)`:** the same, through the collection's
   elements. Where the collection is made in a jar (`Sets.newHashSet(trigger)`), the walk
   answers `external` and the job is not found from this consumer.
3. **`forJob(JobDetail)`:** the walk from that argument, including a `@Bean` method reference.
4. **`forJob(String name, String group)`, `forJob(String name)`, `forJob(JobKey)`**, with
   arguments the walk resolves to constants: the `JobBuilder` chain anywhere in the module whose
   `withIdentity` names the same key. A missing group is Quartz's `DEFAULT`, as `JobKey`
   defines it.

From the `JobDetail` chain, the walk from `newJob(...)`'s argument gives the job class.

**The handler** is the method Quartz calls, mirroring the framework (DR-6). Quartz calls
`Job.execute(JobExecutionContext)` on an instance of the job class, so the handler is the body
the JVM's dispatch rule picks for that receiver class. `resolve/dispatch.py` already computes
that, over `ancestry_of`, and is used; nothing here walks superclasses on its own.

When that body is in a jar, the chain stops there, as it does for any call into a jar. Spring's
`QuartzJobBean.execute` is the case that matters: it calls the subclass's
`executeInternal(JobExecutionContext)`. Which method a framework's template calls on a subclass
is catalog data, in the vocabulary `jakarta-servlet.yml` already uses for `HttpServlet.service`
calling `doGet`: a `supertype` and its `dispatch` list. The Quartz catalog states
`QuartzJobBean` → `executeInternal`.

**Several job classes.**
- **Several paths** (callers passing different classes): one entry per path, each `resolved`.
  This is the walk's existing multiplicity, and a closed set is exact.
- **One path with a branch** (RuoYi's ternary, a `merge` with no common root whose candidates
  are all literals): the value walk answers `narrowed` and lists the candidates (ruling 7).
  This is a change to `values.py` for every consumer, not a Quartz rule: a merge whose
  candidates are not all literals stays `non_enumerable`, and consumers that refuse an inexact
  answer (`channel_of_answer`) keep refusing it. `dispatch.py` then gives each candidate's
  body. Where every candidate reaches the same body (RuoYi: both inherit
  `AbstractQuartzJob.execute`), the entry is one row; otherwise one row per body, `narrowed`.
  Nothing in the Quartz catalog or engine reads the merge's candidates around the walk.

**After the handler, the call graph does the rest.** The dispatcher is a root, and the trace
continues through `call_edges` as it does from any root:
- **ruoyi-vue-pro:** `JobHandlerInvoker.executeInternal` calls `jobHandler.execute(param)`
  through the `JobHandler` interface. The dispatch rule resolves that call to every in-module
  `JobHandler` implementation, `narrowed`, so all ~25 job beans are reached from the dispatcher
  with no Quartz-specific rule.
- **RuoYi-Vue, aurora, NBlog:** the dispatcher calls its target by reflection
  (`Method.invoke(bean, …)`), which names no callee. The trace stops there, correctly.

### 3d. Engine and catalog (ruling 6)

Quartz is a catalog on machinery that already exists. Each existing piece keeps its one job:

| Concern | Existing component | What Quartz uses it for |
|---|---|---|
| Reading a builder chain: roots, steps, captures, `argN` | the `fluent` chain walk | `newTrigger()`, `newJob(…)` and schedule builder chains |
| Pairing a built value with the call that consumes it | `fluent`'s execute-join (`terminal_via_argument`) | `scheduleJob(job, trigger)` and its overloads |
| A value that crosses methods | `resolve/values.py` | a trigger returned by a helper, a class from a helper, a cron from a getter |
| An `@Value` field or parameter to its `${…}` | the field ladder, `shapes/arguments.py` | a configured cron |
| Which body runs for a receiver class | `resolve/dispatch.py` | the job's handler |
| A framework template calling a subclass method | the `supertype` + `dispatch` catalog vocabulary | `QuartzJobBean` → `executeInternal` |
| Compiler-emitted artefacts read as the source wrote them | `resolve/effective_calls.py` | autoboxing (§3g) |
| Per-environment values for a `${…}` | `resolve/resolved_schedules.py` + `placeholder_rule` | configured crons, unchanged |
| What the job does | `call_edges` + every other catalog | Kafka, REST, event bus or reactive calls inside the job |

**The one structural change: the chain walk leaves `fluent.py`.** Today the walk lives inside
the `fluent` engine, and its context also carries what only endpoints need (client bases,
metadata, channel bindings, verbs). Adding a `scheduled_work` output to that engine would put
scheduling and endpoint derivation in one module. So:
1. **Move, with no change in behaviour,** the chain walk (roots, steps, captures, folding,
   joins, bean hops) into its own module under `resolve/shapes/`. It produces the folded
   captures for each chain and knows nothing about what row they become. `fluent` keeps the
   endpoint derivation and calls the walk. This step is pinned by the existing suite and by
   `scripts/field_check.py` on every pin, before any Quartz work starts.
2. **Add the scheduled-work derivation** as its own engine, which turns a chain's captures into
   `scheduled_work` rows. The annotation engine (`engines/scheduled_work.py`) stays as it is. The
   two are different shapes of evidence for one table, D02's rule that a style is a shape of
   evidence, not a framework.

The catalog `src/sextant/catalogs/quartz.yml` holds every owner, method, consumer signature
and the kind map; neither engine names a Quartz type. Writing a chain as text (§3b) is a pure
function in `resolve/shapes/`, beside the walk, not inside an engine. Placeholder detection uses
the config model's `placeholder_rule`, not a hard-coded `${`.

### 3e. Schema

`scheduled_work` today promises that `expression` is never NULL and that `resolution` is
`resolved` or `unresolved`. Both promises change: `handler`, `trigger` and `expression` may be
NULL, and `resolution` may be `partial` or `narrowed`. `GRAPH_SCHEMA_VERSION` goes 8 → 9, and
the D01 version table gains its row. A row with a NULL handler is not a trace root (`roots.py`
skips it).

**A new column, `name`** (ruling 5): the trigger's key as Quartz builds it from
`withIdentity(name, group)` or `withIdentity(name)` (group `DEFAULT`, as `TriggerKey`
defines it), written `group.name`, when the walk resolves both to constants; NULL otherwise
(RuoYi's runtime `getTriggerKey(jobId, …)`, and every `@Scheduled` row). The boundary
vocabulary's `schedule` identity becomes `(handler, trigger, name)`, the `resolved_schedules`
join gains `name`, and `BOUNDARY_VOCABULARY_VERSION` is bumped. Two rows that still share all
three are OI-183's case, which stays open.

The document's "Scheduled work" table shows a NULL cell as "not in the code". A `partial` row
whose expression is NULL says why in its detail block, naming where the walk stopped: for
example, "read at runtime from `SysJob.getCronExpression()`".

### 3f. Fixture

`fixtures/orders-quartz`, a Spring Boot module on Quartz 2.5.x, JDK 21, primed in
`tests/fixture_build.py`. It reproduces the forms measured above, across methods as the
corpora have them:
- a `@Bean JobDetail` and two `@Bean Trigger`s on it by `forJob(name, group)`, one `simple`
  and one `cron` literal (ruling 3);
- a trigger joined by `forJob(jobDetailBean())`;
- a cron from `@Value("${orders.sweep.cron}")`, with the key in `application.properties`;
- a `dailyTimeInterval` chain with a nested `TimeOfDay` argument and a boxed `onDaysOfTheWeek`;
- the RuoYi shape: a helper returning a two-class ternary, a trigger built from a row getter
  through a misfire helper typed `CronScheduleBuilder`, `scheduleJob(job, trigger)`, and an
  update method using `getTriggerBuilder()`;
- the ruoyi-vue-pro shape: the trigger built and returned by a private method;
- the dolphinscheduler shape: job and trigger built in two other classes and paired through
  `scheduleJob(job, Set, true)`, with the set made by `java.util.Set.of(trigger)`, which is
  also in a jar;
- one job extending `QuartzJobBean`, one implementing `Job` through an abstract superclass.

The failing intention test goes in `tests/e2e/test_async_delivered.py` (the Async feature
already owns it) and asserts on `render` output, which is an intention marker.

### 3g. Settled after the builder check (my calls)

- **Values the compiler boxed are read as their constants.** `onDaysOfTheWeek(3, 5)` compiles
  to `Integer.valueOf(3)` per element, and the extractor records each as `unresolved` today.
  javac inserts these calls for autoboxing (JLS 5.1.7); the source wrote `3`. Reading them back
  is a third projection in `resolve/effective_calls.py`, the one place compiler-emitted
  artefacts are already undone (the Kotlin `$default` bridge, class-compiled lambdas). The
  rule covers the eight boxing conversions only: a `<Wrapper>.valueOf(<its primitive>)` whose
  argument is a constant is that constant. The extractor is unchanged, and raw `call_sites` keep
  the bytecode's own statement. Engines read the projection, so `scripts/field_check.py` runs
  on the pins.
- **The kind from the declared return type** (§3b): a compiler fact, not a model of the helper.
- **Entries come from `newTrigger()` roots** (§3a); `getTriggerBuilder()` rebuilds are not new
  triggers.
- **The chain walk moves out of `fluent.py` before Quartz is added** (§3d), so endpoint and
  scheduling derivation stay in separate modules.
- **The handler comes from `dispatch.py`; `QuartzJobBean` → `executeInternal` is catalog
  data** in the servlet `dispatch` vocabulary (§3c).
- **Pairing reuses the execute-join,** made to find its arguments through the value walk
  (§3c).

## 4. What it does NOT do

- **Read seed SQL or any database** (ruling 2).
- **Add any rule for the dispatcher's targets.** Where the dispatcher calls them through an
  interface (ruoyi-vue-pro), the call graph already reaches them. Where it uses reflection
  (RuoYi-Vue, aurora, NBlog), the trace stops, as for any reflective call.
- **`quartz_data.xml` and `quartz.properties` jobs.** Stated as a COVERAGE boundary; none of
  the real corpora uses them.
- **`@DisallowConcurrentExecution`, `@PersistJobDataAfterExecution`, job data maps.**
  Concurrency and state policy, not a schedule. The §5.12 row's wording is corrected.
- **Jobs with no trigger** (`storeDurably()` jobs run on demand by `scheduler.triggerJob`).
  No schedule, so no entry.
- **Kotlin.** The same bytecode, but no corpus and no fixture; COVERAGE says so.
- **Spring's `JobDetailFactoryBean` / `CronTriggerFactoryBean`.** Zero uses in all six
  corpora. Stated, not built.

## 5. Cost (§8.7)

One read of `call_sites` filtered to the catalog's owners per resolve, and one module-wide map
of `withIdentity` keys. The corpora have 1–5 `newTrigger()` roots per module. Each root starts
at most three value walks (the schedule argument, the consumer's job argument, `newJob`'s
argument), on the `ValueIndex` the resolve already builds. No per-row query.

## 6. Predictions: verify what it closes

These are predictions until the "As built" section measures them.

| Corpus | Predicted entries |
|---|---|
| spring-boot smoke test | 5: `helloJob` ×3 and `anotherJob` ×2, all `SampleJob.executeInternal`, all `resolved` |
| RuoYi-Vue, aurora, NBlog | 1 each: `cron`, expression NULL, `partial`. Handler: the inherited `execute` (one row; both branches reach the same body). |
| ruoyi-vue-pro | 2: `JobHandlerInvoker.executeInternal` and the IoT manager's job (handler from its callers' class arguments), `cron`, expression NULL, `partial`. The trace from the first reaches all ~25 `JobHandler` implementations. |
| dolphinscheduler | 1: handler NULL (the trigger set is made in Guava), `cron` from the factory's declared type, expression NULL, `partial`. Not a trace root. |

## 7. Open — for the user

Nothing. Ruling 7 closed the last question.
