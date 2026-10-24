# A schedule set in configuration, read per environment — design

**Status: BUILT 2026-10-23 (branch `cov/scheduled-placeholders`) — option A ruled.** As built,
three things differ from or sharpen the design below: `resolved_schedules` carries the job's
`expression` after `trigger` (§3b), because `@Schedules` can put two placeholder crons on one
method and `(handler, trigger)` alone would attribute both jobs' values to one; the
delimiters and key matching are read by `resolve/config.py::placeholder_rule(model)`, beside
`substitute`; and relaxed matching keeps the dot as a separator, so `orders.sweepCron`
matches `orders.sweep-cron` (both `orders.sweepcron`) and never `orderssweepcron`.

Closes the one gap in Spring Boot's Async cell (COVERAGE §5.12, `@Scheduled` row 3: "◐
shipped as `unresolved`, expression carried verbatim … Closes when a non-wire row can read `resolved_config`, which needs an environment
column this table does not have"). Moves Spring Boot's §2c Async cell from `◐ (1 limited)` to
✅.

## 1. The ruling (2026-10-23)

**Option A:** a per-environment answer BESIDE `scheduled_work`, which keeps one row per job.
The user was shown option B as well (one `scheduled_work` row per job per environment) and
chose A. Under ruling 1(b) of spec 2026-10-23-deployment-set-conditions this is a VALUE, not
an existence verdict, so it is reported as what the repository configures per environment,
labelled as such — as peers and paths are.

A cost first stated as "graph schema 7 for a new view" stands, for a different reason (§3b):
the answer is a derived TABLE, because the placeholder rule it must use lives in Python.

## 2. Measured first

The 7 analysed modules under `examples/` that schedule anything hold 12 jobs, none written with
a placeholder. The standing rule ("nothing in the corpus" is about the corpus) applies: a
configurable cron is the ordinary production form, and the COVERAGE row cites its own example,
`@Scheduled(cron = "${orders.sweep.cron}")`. The fixture gains one (§3e).

## 3. What changes

### 3a. One placeholder rule, not two

`resolve/config.py::_substitute` is the project's placeholder rule: the catalog's delimiters
and `default_separator` (D02 §2i), `${key:default}`, a literal default never re-substituted,
nested references, cycles, and relaxed or exact key matching per the model. *Amended
2026-10-23 (final review, ruled):* "a literal default never re-substituted" was the walk's
behaviour, not Spring's. The walk ended a placeholder at the first closer, so
`${missing:${a}}` gave the literal `${a}`; CP-48 (`spring-core` 7.0.9) measured that
`PlaceholderParser` ends a placeholder at the closer that balances it (counting the catalog's
new `placeholders.nest`, `{`) and resolves a default's placeholders through the same
resolver. `substitute` now does both, and the change moves `resolve_config` on a nested
default as well as the schedules. Today it can only
look a key up in the layered map `resolve_config` builds and discards.

It is split into the parsing rule and the lookup:
- `substitute(raw, placeholders, lookup)` — the delimiter/default walk, unchanged in
  behaviour, where `lookup(ref_key) -> (value | None, reason | None)`;
- `resolve_config` passes the recursive, layered lookup it has today;
- a code expression passes a lookup over ONE environment's `resolved_config` rows, keyed as the
  model's `key_matching` says (`normalize_key` for relaxed). Those values are already fully
  substituted, so no recursion is needed there.

`resolved_peers`' SQL single-placeholder substitution (no defaults) is NOT moved onto it here:
nothing reads that query today (it is logged instead, §4).

### 3b. `resolved_schedules`, a derived table

```text
handler               trigger    expression                         environment  keys                     value          unresolved_reason
OrderSweeper#sweep()  cron       ${orders.sweep.cron:0 0 * * * *}   default      ["orders.sweep.cron"]    0 0 * * * *    NULL
OrderSweeper#sweep()  cron       ${orders.sweep.cron:0 0 * * * *}   prod         ["orders.sweep.cron"]    0 */5 * * * *  NULL
OrderSweeper#purge()  fixedRate  ${orders.purge.rate}               prod         ["orders.purge.rate"]    NULL           missing_key
```

- One row per (`scheduled_work` row whose `expression` holds the placeholder opener, environment of
  `resolved_config`), carrying that row's `handler`, `trigger` and `expression` — the job's
  whole identity, so two jobs on one method under `@Schedules` are told apart (as built; the
  first sketch had no `expression` column). A job with no placeholder gets no rows; its
  `scheduled_work` row already says everything. With no resolved environment, the table is
  empty for the reason `resolved_peers` gives.
- `unresolved_reason` is D01's closed set (`missing_key`, `placeholder_cycle`, …), from the
  lookup.
- Written by a new pass after `resolve_config` and after the scheduled-work engine, reset whole
  per resolve like every derived table.
- Exported in the bundle. ~~Its `value` is masked by `redact_text` (a cron, rate or delay is
  neither a credential nor keyed, and `redact_text` applies the module's value patterns)~~ —
  *amended 2026-10-23 (final review, ruled):* the premise was wrong. A schedule IS the value
  of the key that configures it, and the key rule masks that key's value in
  `resolved_config` (`app.token.cleanup.cron` holds `token`, a built-in pattern), so a
  `value` masked by `redact_text` alone shipped what `resolved_config` hid. Each row carries
  `keys`, every key the substitution asked the lookup for, in order (a JSON array), and both
  exits mask through one function beside the writer, `redact_schedule_value(redactor, keys,
  value)`: whole when any key matches the key rule (`Redactor.masks_key`, the test
  `redact_value` applies), `redact_text` otherwise. The export ratchet requires the export
  query.
- `GRAPH_SCHEMA_VERSION` 6 → 7: a new derived table. The D01 version table gains the row.

### 3c. What the document says

The scheduled-work table keeps its columns. A job whose expression holds a placeholder gains its
per-environment values, labelled as the repository's configuration:

```text
OrderSweeper#sweep()   cron   ${orders.sweep.cron:0 0 * * * *}   unresolved
  as configured in this repository: `0 0 * * * *` in `default`; `0 */5 * * * *` in `prod`
```

Environments with the same value share one entry. An unresolved environment states its reason
(`missing_key`, …). *As built,* the line is an entry of the detail block under the table — the
place a job's conditions already go, and in the same block — headed by the job's handler,
trigger and expression (`` `OrderSweeper#sweep()` — cron `${orders.sweep.cron:0 0 * * * *}` ``),
so two jobs on one method each carry their own line; a job with no rows renders as before.
The `resolution` column of `scheduled_work` stays `unresolved`: the job's schedule is still the deployment's (ruling 1(b)), and the per-environment values are what the
repository says.

### 3d. The diff

Unchanged. The `schedule` kind keeps identity `(handler, trigger)` and attributes
`(expression, resolution)`. A configuration edit is a `boundary-property` change, as ruling 3
of 2026-10-23-deployment-set-conditions decided for conditions.

### 3e. Fixture

A Spring fixture already carrying `@Scheduled` (`orders-service`, or the one
`tests/e2e/test_vertical_slice.py` reads `scheduled_work` from) gains:
- one `@Scheduled(cron = "${orders.sweep.cron:0 0 * * * *}")`, the key set in a profile file
  only;
- one `@Scheduled(fixedRateString = "${orders.purge.rate}")`, the key set nowhere
  (`missing_key`).

It is rebuilt with JDK 21. *As built:* `orders-service` carried no `@Scheduled` before
this — the one `tests/e2e/test_vertical_slice.py` reads — so both jobs are a new class,
`scheduling/OrderSweeper`, and the key is set in `application-prod.yml`. The class moves the
fixture's document, call-edge and root counts by one class file, re-pinned where asserted.

## 4. What it does NOT do

- **`resolved_peers` keeps its SQL substitution** and still cannot read a `:default`. Logged as
  an OI: it closes when something reads that query, by moving it onto `substitute`.
- **SpEL (`#{…}`) is not evaluated.** A `#{…}` expression stays verbatim and gets no rows.
- **`initialDelay`, `zone` and the rest** stay unread, as the catalog states today.

## 5. Cost (§8.7)

One read of `scheduled_work` and one of `resolved_config` per resolve, joined in memory. Rows
written: jobs-with-placeholders × environments.

## 6. Verify what it closes

- COVERAGE §5.12 `@Scheduled` row 3 → ✅ shipped, citing this spec and its pins; regenerate the
  §2c grid (`scripts/coverage_matrix.py`) and confirm Spring Boot's Async cell reads ✅.
- The field pins (`scripts/field_check.py`) are unaffected (no corpus job has a placeholder);
  run them anyway.
