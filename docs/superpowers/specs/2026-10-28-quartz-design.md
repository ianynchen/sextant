# Quartz — design

**Status: DRAFT 2026-10-28, awaiting approval** (branch `cov/quartz`). Plane SEXTANT-177,
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

The trigger's job is found by following, with the value walk, whatever pairs them, as Quartz
pairs them:
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

**The handler** is the method Quartz calls, mirroring the framework (DR-6): `execute(
JobExecutionContext)` as declared on the job class or the nearest superclass that declares it;
where that declaration is Spring's `QuartzJobBean.execute`, it is the class's own
`executeInternal(JobExecutionContext)` instead, which is what `QuartzJobBean.execute` calls.

**Several job classes.**
- **Several paths** (callers passing different classes): one entry per path, each `resolved`.
  This is the walk's existing multiplicity, and a closed set is exact.
- **One path with a branch** (RuoYi's ternary, a `merge` with no common root): the walk answers
  `non_enumerable` today and keeps the candidates in the fact. Here the candidates are class
  literals, and the question is only which METHOD Quartz will run. Where every candidate
  reaches the same handler (RuoYi: both inherit `AbstractQuartzJob.execute`), that handler is
  the answer whichever branch runs, and the entry is one row. Where they reach different
  handlers, one row per candidate at `narrowed` (one of them runs; we cannot say which).
  `narrowed` is D00's existing word for that.

The dispatcher is then the handler, and the trace continues into it as it does from any root.
What it calls by a name read from the row stays unknown.

### 3d. Engine and catalog

A new non-wire catalog `src/sextant/catalogs/quartz.yml`, detected on
`org.quartz-scheduler:quartz`, with no `protocol` and no `direction` (the
`spring-scheduling.yml` rule). The owners, method names, consumer signatures and kind map in
§3a–§3c live in the catalog; the engine names no Quartz type.

The current `scheduled_work` engine reads annotations only, and the `fluent` engine writes
endpoints only. Whether one of them grows a builder-chain reader for `scheduled_work`, or a
new style uses `fluent`'s chain walk and `values.py`, is left to the plan. It may not copy either.

### 3e. Schema

`scheduled_work` today promises that `expression` is never NULL and that `resolution` is
`resolved` or `unresolved`. Both promises change: `handler`, `trigger` and `expression` may be
NULL, and `resolution` may be `partial` or `narrowed`. `GRAPH_SCHEMA_VERSION` goes 8 → 9, and
the D01 version table gains its row. A row with a NULL handler is not a trace root (`roots.py`
skips it). The identity question is §7.

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
  The fix is in the extractor, as a rule about what javac emits for autoboxing: a
  `Integer/Long/Short/Byte/Character/Boolean/Float/Double.valueOf` whose only argument is a
  constant of its primitive type is that constant. It is the same kind of rule as reading a
  constant-folded `static final`, not a model of a library method. It is a fact-level change,
  so it gets a probe, every fixture is rebuilt with JDK 21, and `scripts/field_check.py` is
  run on the pins.
- **The kind from the declared return type** (§3b): a compiler fact, not a model of the helper.
- **Entries come from `newTrigger()` roots** (§3a); `getTriggerBuilder()` rebuilds are not new
  triggers.
- **The same handler from every branch is one exact answer** (§3c); different handlers are
  `narrowed`.

## 4. What it does NOT do

- **Read seed SQL or any database** (ruling 2).
- **Name the dispatcher's targets.** The `JobHandler` beans in ruoyi-vue-pro stay methods no
  code is shown to call.
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
| RuoYi-Vue, aurora, NBlog | 1 each: `AbstractQuartzJob.execute` (or the project's equivalent), `cron`, expression NULL, `partial` |
| ruoyi-vue-pro | 2: `JobHandlerInvoker.executeInternal` and the IoT manager's job (handler from its callers' class arguments), `cron`, expression NULL, `partial` |
| dolphinscheduler | 1: handler NULL (the trigger set is made in Guava), `cron` from the factory's declared type, expression NULL, `partial`. Not a trace root. |

## 7. Open — for the user

**How two entries on the same job are told apart (OI-183).** The boundary vocabulary
identifies a `schedule` by `(handler, trigger)`. Ruling 3 makes collisions ordinary: the smoke
test's `sampleTrigger` and `every-day` are both `SampleJob.executeInternal` + `simple`. This is
the `@Schedules` collision OI-183 already holds open. The answer decides a `scheduled_work`
column (inside the same 8 → 9 bump), the vocabulary's `schedule` identity, and the
`resolved_schedules` join.
