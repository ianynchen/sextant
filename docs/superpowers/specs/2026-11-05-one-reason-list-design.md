# One reason list everywhere: a general reason plus a detail — design

**Status: APPROVED 2026-11-05 (user: "Approve, build it").** Plane OI-321 = SEXTANT-315. Ruled B on 2026-11-05.
Branch `fix/one-reason-list`, cut from `cov/hilt-provides` (PR #94), which carries the first
half of the work (commit e59f0017: the `bean_*` codes and the client reader's code now use the
general list).

## 1. The problem

Sextant says why it could not resolve something in four places. Only one of them uses the
general list (`values._REASONS`: `external`, `non_enumerable`, `not_readable`, `escapes`,
`no_writer`, `cycle`). The other three each have their own words:

| Where | Today's words | Stored in |
|---|---|---|
| A configuration value | `missing_key`, `environment`, `remote_source`, `placeholder_cycle`, `multi_placeholder` | `resolved_config.unresolved_reason`, `resolved_schedules.unresolved_reason`, the `resolved_peers` query; graph: `boundary-property` (D01) |
| Which method a call reaches | `declared_here`, `inherited`, `ancestor_not_scanned`, `owner_not_scanned`, `no_declaration_found` | `method_resolution.reason` (D00 §4) |
| Where a request's context was lost | `handed_to`, `stored_in`, `produced_by`, `of_type`, `from_field`, `no_body`, `argument` | the pass-through question's `unread[].how` |

A reader who wants to know "why is this unknown?" has to learn four lists. The user's
ruling: one general reason, and a detail that says where.

## 2. The rule

**Every "not resolved" answer has two parts:**

1. `reason`: one word from the general list (`values._REASONS`). Nothing else is allowed.
2. `detail`: free text that names the place, for example
   `` orders.url is not set in application-prod.yml ``. It is written for a person, and no
   code branches on it.

**How to choose `external` or `not_readable`** (from the ruling "tell the truth, follow
the code"): `external` when the code or file that would give the answer is not in what
Sextant reads; `not_readable` when it is there but Sextant does not follow it. This is
decided where the answer is made, from the facts. It does not come from a table of old words.

A "found" answer has no reason. A success is not a reason.

## 3. Each list, word by word

### 3a. Configuration values

| Old word | Reason | Detail (example) |
|---|---|---|
| `missing_key` | `external` (the deployment sets it, see the 2026-10-23 ruling) | `orders.url is not set for prod` |
| `environment` | `external` | `orders.url comes from the environment variable ORDERS_URL` |
| `remote_source` | `external` | `orders.url comes from the config server configserver:http://cfg:8888` |
| `placeholder_cycle` | `cycle` | `a.url refers to b.url, which refers back to a.url` |
| `multi_placeholder` | `not_readable` | `the address ${host}:${port}/x has two placeholders, and only one is filled` |

`multi_placeholder` exists only because the join fills a single placeholder. That is our
limit, not something the code does. Filling each placeholder would remove this reason
completely ("removing the cause beats detecting it"). That change moves rows, so it is
logged as its own item (OI-322 = SEXTANT-316) and is not part of this design.

### 3b. Which method a call reaches

- `declared_here` and `inherited` are successes, so they get no reason. The difference
  between them stays visible: `declaring_class` equal to `class` means declared here.
- `owner_not_scanned` and `ancestor_not_scanned` become `external`, with the detail
  `com.x.Client is not in the scanned code` (or `its superclass com.x.Base …`).
- `no_declaration_found` becomes `not_readable`. The code is there and no declaration was
  found, which is a defect on our side. Detail: `no declaration of send(..) in com.x.Client
  or its scanned superclasses`.

The coverage figure (`pipeline.py`, query `method_resolution_distribution`) counts methods
by this word today. After the change it counts by `resolved` (a body was found) or by the
reason. It keeps the split the figure exists for: `external` is a scanning decision and
`not_readable` is a defect.

### 3c. Where a request's context was lost (pass-through)

| Old `how` | Reason |
|---|---|
| `handed_to`, `stored_in` | `escapes` (the context goes somewhere the walk does not follow) |
| `produced_by`, `of_type`, `from_field`, `no_body`, `argument` | `external` when the method or type is not in the scanned code, otherwise `not_readable` (§2 rule, decided at each place) |

The existing sentences ("hands the request's context to X, where it is not followed") are
already the detail. They are now made once, where the answer is made, and stored. The
document reads the stored detail, so the two copies of the phrase table (`pass_through.py`
and `document.py`) become one.

## 4. What is stored (format change: needs approval)

- `resolved_config`, `resolved_schedules`, `resolved_peers`: `unresolved_reason` takes
  only the general words, and a new `unresolved_detail TEXT` column is added beside it.
- `method_resolution`: `reason` is NULL for a found body and a general word otherwise,
  with a new `detail TEXT` column.
- Pass-through `unread[]` entries: `{how, name}` becomes `{reason, detail}`.
- Graph (D01 `boundary-property`): attributes `value`, `unresolved_reason`,
  `unresolved_detail`. **`GRAPH_SCHEMA_VERSION` 15 → 16.**
- D00 §4 drops the `method_resolution` list. D01 §resolved_config points at the general list.
  D02 and D06 text are updated. The brief (`enrich/brief.py`) reads the reason and the detail.

## 5. Done when

- No reason word outside `values._REASONS` is written anywhere. A guard test reads every
  table and graph attribute named in §4 on all fixtures and fails on any other word.
- Every fixture and the six field pins were diffed before and after. The only changes are
  the reason and detail columns, and each changed row's reason was checked against the
  §3 tables.
- The document reads the same to a person, or better (it now shows the general reason
  first, then the detail).
- The full check passes with JDK 21.

## 6. Not in this design

- Filling each placeholder of a multi-placeholder address (logged as a new item).
- Any change to which rows resolve. This design changes only how "not resolved" is said.
