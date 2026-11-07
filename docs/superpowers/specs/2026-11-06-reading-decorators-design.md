# Python: reading decorators — routes, commands and the decorators between — design

**Status: APPROVED 2026-11-06 (user: "option A").** Keys 1–6 of §10 are approved. Key 7
(`path_join: space`) is dropped. It is replaced by a rule: an `entry_point` catalog joins its
words with one space (§4). It unblocks Task 9 of
`docs/superpowers/plans/2026-11-06-python-reader-foundation.md` (stopped NEEDS_CONTEXT, report
`.superpowers/sdd/2026-11-06-python-reader-foundation/task-9-report.md`). It extends
`2026-11-06-python-reader-design.md` §3a–§3c and §6. Nothing here is built.

Marks:
- **(ruled):** the user decided it.
- **(my call):** my decision; the user can reject it.
- **(needs approval):** a new catalog key, a new value of a key, or a fact change.

## 1. Intent

A Python framework declares most of what it serves with decorators. A decorator is a call
that gets a function and returns something. The Python spec writes each decorator as the call
it is, never as an annotation (§3a, ruled). Task 9 found four things the catalogs cannot yet
read: keyword arguments (gap 1), the type of an object a decorator factory makes (gap 2), a
command's word taken from its function's name (gap 3), and the decorators between a function
and its registration, with the link from an option to its command (gap 4).

This design closes the four for Sextant's own commands in plan 1 (ruled: §6 option A, commands
are `entry_point` roots). It must also be the right design for FastAPI and Flask in plan 2,
so plan 2 does not redo it. §6 shows one polar route read with the same rules.

## 2. What was measured (2026-11-06)

**Projects:** the eleven clones of the Python spec §2, at the same commits, plus
`src/sextant`. Folders named `tests`, `test` and `migrations`, and files named `test_*`, are
left out.

**Scripts** (`python -I`, `ast` only, nothing imported), in the session scratchpad
`deco/`: `count.py` (route and command decorators, stacks, receivers, names), `options.py`
(click options and mount calls), `ctors.py` (router constructors).

**Which decorators were counted.** A *route decorator* is a call `X.get|post|put|patch|delete|
head|options|trace|route|api_route|websocket(...)` whose first positional argument, if any,
is a string. A *command decorator* is `X.command(...)`, `X.group(...)` or `X.callback(...)`.
Django has neither: its routes are in `urls.py` lists, so netbox, zulip and saleor show
zero below. httpie uses `argparse` and shows zero. microservices-demo has one Flask route.

### 2a. Keyword arguments

| Project | Route decorators | … with a keyword | Most used keywords |
|---|---|---|---|
| polar | 576 | 563 | `response_model` 371, `summary` 316, `responses` 290, `name` 186, `status_code` 101, `methods` 66 |
| dispatch | 290 | 283 | `response_model` 254, `dependencies` 101 |
| mealie | 289 | 254 | `response_model` 230, `dependencies` 61, `status_code` 39 |
| full-stack-fastapi-template | 23 | 18 | `response_model` 15, `dependencies` 6 |
| redash (Flask) | 12 | 11 | `endpoint` 6, `methods` 5 |
| CTFd (Flask) | 71 | 30 | `methods` 27 |

- **Mount and router calls.** `include_router(..., prefix=)`: polar 17, dispatch 50, mealie
  10, template 1. FastAPI declares `prefix` keyword-only, so it has no position at all.
  `APIRouter(prefix=)` at construction: polar 79, mealie 52, template 4, dispatch 1.
- **click options** (`option`, `argument`, `password_option`, `version_option`):
  Sextant 24, dispatch 57, redash 59, CTFd 7. Their keywords: `type` (Sextant 17,
  dispatch 14), `default`, `help`, `is_flag` (Sextant 4, dispatch 9, redash 4, CTFd 1),
  `required` (dispatch 10).
- **A route's path written as a keyword (`path=`):** 0 everywhere. **A `**mapping` or a
  `*sequence` in any of these decorators:** 0 everywhere.

**So:** almost every FastAPI route carries a keyword argument, and every FastAPI prefix is one.
Positions alone cannot read them.

### 2b. Stacked decorators

A function's decorators are written top to bottom and applied bottom to top. "Between" means
below the route or command decorator, so applied to the function first.

| Project | Functions | … with decorators between | What sits between |
|---|---|---|---|
| polar routes | 576 | 22 | `version` 21 (module code, returns the function itself); a second `router.get` 1 |
| polar typer commands | 93 | 72 | `typer_async` 72 (module code, returns a `functools.wraps` wrapper) |
| dispatch routes | 290 | 1 | `limiter.limit` 1 (slowapi, a library) |
| dispatch click commands | 38 | 23 | `click.option` 44, `click.argument` 10, `click.password_option` 2, `click.version_option` 1 |
| mealie, template routes | 312 | 0 | — |
| redash click commands | 35 | 23 | `option` 32, `argument` 27, `with_appcontext` 1 (flask, a wrapper) |
| redash routes | 12 | 4 | `login_required` 3, `require_super_admin` 3 (module code) |
| CTFd routes | 71 | 56 | `admins_only` 31, `ratelimit` 7, `authed_only` 6, 11 others (all module code); a second route decorator on 6 functions |
| Sextant commands | 9 | 6 | `click.option` 17, `click.argument` 7 |

- **Above the route or command decorator: 0 decorators in every project.** The
  registration is always outermost. It always receives the result of the whole stack below.
- **The deepest stack:** 10 decorators (dispatch). Sextant's deepest is 9 (`module enrich`).
- Between decorators are of three kinds: **library calls that return the function
  unchanged** (click options), **module code** (polar, CTFd, redash), and **library calls that
  return a new function** (slowapi, flask's `with_appcontext`: 2 in the corpus).

### 2c. Decorator factories (module-level names made by calling a library call's result)

Where the receiver of a route or command decorator comes from:

| Project | Made by a constructor (`router = APIRouter()`, `cli = typer.Typer()`) | A decorated function (`@click.group() def cli`) | Imported or other |
|---|---|---|---|
| polar | 572 routes, 93 commands | 0 | 4 |
| dispatch | 290 routes | 36 commands | 2 |
| mealie, template | 312 routes, 3 commands | 0 | 0 |
| redash | 29 commands (`AppGroup(...)`) | 5 commands | 13 |
| CTFd | 47 routes | 0 | 29 |
| Sextant | 0 | 8 commands | 1 (`click` itself) |

**So:** the missing type (gap 2) is a click need. FastAPI, Flask and typer routers are class
instances, and their type is already read (§3a, including polar's `type[_APIRouter]` factory).

### 2d. Names taken from the function

| Project | Commands with no name written | … whose function name has `_` |
|---|---|---|
| polar (typer) | 85 of 93 | 41 |
| dispatch | 5 of 38 | 4 |
| redash | 18 of 35 | 2 |
| template | 3 of 3 | 2 |
| Sextant | 3 of 9 (the groups `cli`, `module`, `system`) | 0 |

A route's path is never taken from the function. FastAPI's `name` (polar: 389 routes do
not write it) and Flask's `endpoint` default to the function name. They name the route for
`url_for` and the OpenAPI document, not for its address.

**The measured naming rules:**
- click 8.5.0 (`decorators.py`, `command`): lower case, `_` → `-`, then a last part `command`,
  `cmd`, `group` or `grp` after a `-` is removed (since 8.2). `init_data_command` → `init-data`.
- typer 0.27.1 (`main.py`, `get_command_name`): lower case, `_` → `-`. No suffix is removed.

### 2e. Entry points

| Project | Declared where | Names |
|---|---|---|
| Sextant | `[project.scripts]` | `sextant = sextant.cli.app:cli` (the group object) |
| dispatch | `[project.scripts]` | `dispatch = dispatch.cli:entrypoint` (a function that calls the group) |
| mealie, netbox | `[project.scripts]` | a `main` function each |
| httpie | `setup.cfg` `console_scripts` | `http`, `https`, `httpie` (functions, argparse) |

## 3. The four gaps

### 3a. Gap 1 — addressing a keyword argument

**What D02 says today.** `single_call` says "Arguments are addressed by position or name".
Only the position is built. Every argument key is an integer (`url_arg: 0`) or an `argN`
capture, and one function reads them all: `shapes/arguments._arg_at(arguments, index)`. The
`name` in a `single_call` row is the **method's** name (`{ name: postForObject, … }`). The
sentence dates from the first design (commit 0f9b8d5b, 2026-08-27) and was never built. The
only by-name reads today are of **annotation attributes** (`name_attrs`, `required_attr`,
`default_attr`, `path_from`).

**A hidden defect found here.** The scanner writes a call's positional arguments first, then
its keyword ones (ruling R27). `_arg_at` counts every argument. So on
`click.option("--dry-run", is_flag=True)`, `arg1` reads `True`. On the JVM no argument has a
`keyword`, so the JVM is not affected. Any fix below must count positions over positional
arguments only.

**Option A — one keyword form for every argument reference (needs approval).**
- Wherever a catalog names an argument (`*_arg: N`, a capture `argN`, `prefix_arg`,
  `router_arg`), it may write instead:
  - `{ keyword: is_flag }` — the argument written with that name;
  - `{ arg: 0, keyword: path }` — Python's rule for a parameter that is positional or named:
    position 0 if at least one positional argument is written, else the keyword `path`.
- `argN` and `N` count positional arguments only (the defect above).
- If a `*sequence` is written at or before the position, or the keyword is absent and a
  `**mapping` is written, the value is unknown: reason `not_readable`, detail "the argument may
  come from an unpacked `*`/`**` value". Measured 0 times, so this only keeps the answer true.
- Files: `shapes/arguments.py` (`_arg_at` takes a reference, not an index); the loaders in
  `ingress/catalogs/yaml_source.py` and `shapes/mounts.py`; D02 §2.
- FastAPI: `url: { arg: 0, keyword: path }`, `response: { keyword: response_model }`,
  `prefix_arg: { keyword: prefix }`. Flask: `http_method: { keyword: methods }`.
- **Pro:** one form and one reader for every style; D02's sentence becomes true. Cost: one
  pass over one call's arguments per read. **Con:** a new catalog form.

**Option B — the scanner binds keywords to positions by the library's signature** (no
format change).
- **Con:** click's `option(*param_decls, **attrs)` gives `is_flag` no parameter. FastAPI's
  `response_model` and `prefix` are keyword-only, so they have no position. It also breaks
  R27 (arguments are written as written).

**Option C — the catalog writes the callee's parameter list, and the resolver binds by
`values.parameter_slots`** (new key).
- **Pro:** it reuses the one calling rule.
- **Con:** it copies library signatures into catalogs, where they can drift. `**attrs` still
  needs a keyword name, so it is option A plus a copy.

**Recommendation: A** (my call). It is the smallest change that reads all of §2a. B cannot
read most of them. C is A with a copied signature.

### 3b. Gap 2 — the type of an object a decorator factory makes

`click.group()` returns `Callable[[F], Group]`. Its result is then called with `cli`. Today the
scanner gives the call no type, because a `Callable` return is "no class". So `cli` has no
type, and `cli.group()` and `module.command(...)` carry no owner. No `fluent` root, no
`single_call` row and no mount can match a call that has no owner.

**Option A — a scanner rule, no format change (my call; inside §3a's approved "read as the
typing specification defines them").**
- Calling a value of type `Callable[[…], R]` gives `R`. A type variable in `R` takes the type
  of the argument that fills it. Where `R` is still not a class (`Callable[[FC], FC]` applied to
  a function), the result stays untyped, as today.
- A module-level name read later in the same file has the type of the values written to it in
  that file: one type, or the closed list of them. A write from another file cannot be seen
  (M03). The resolver's field walk stays the answer for those.
- The result: `cli`, `module` and `system` are `click/core#Group`, and `module.command(...)` is
  written with `owner: click/core#Group`. `evidence: declared`, as for every written type.
- Files: `ingress/extract/python/libraries.py` (`call_returns` returns "a callable that returns
  R"), `calls.py` (the `__call__` result; module-level names), M03.
- FastAPI and Flask: not needed (§2c), and not harmful.
- Overloads: `Group.command("analyze")` must choose the overload whose first parameter is not
  `Callable` (a string is not callable). The existing overload rule does this if it treats a
  string literal as not callable. The builder checks it.
- **Pro:** it is the typing specification, read once per call in the scanner. No new key. It
  serves every decorator-factory library. Cost: one cached lookup per call of a value.
- **Con:** it touches Task 5 and Task 7 code again.

**Option B — engines read the resolver's bound owners.** It does not help. Binding stops at
`external` on a library result (ruling A on Task 7), and library members are never saved.

**Option C — a catalog key that names what a factory makes** ("applying the result of
`click.decorators.group` makes a `click.core.Group`").
- **Con:** a new key that restates the library's own signature, once per catalog.

**Recommendation: A.** It is the type the library already writes, read by the rule the
approved spec already names.

### 3c. Gap 3 — a command's word from its function's name

**Option A — extend the existing `path_fallback` (needs approval).**
- Today `path_fallback` (`annotation_driven`, D02 §2) says what the declared name is when no
  attribute names it. Its word `construct_name` is "the construct's own name". For a decorator,
  the construct is the function the registration receives (the handler, §3d).
- Two extensions:
  1. `path_fallback` may be written on a `fluent` or `single_call` catalog (`matches`, or one
     root). It applies where the root's `url` capture reads no argument.
  2. A mapping form that states the framework's respelling as data:
     `{ name: construct_name, lower: true, replace: { "_": "-" }, drop_suffixes: [command,
     cmd, group, grp] }`. Each part applies in that order. `drop_suffixes` removes a last part
     named in the list, and the `-` before it, where the name has a `-`. click's rule is that
     whole mapping. typer's is the mapping without `drop_suffixes`.
- Files: `shapes/chains.py` and `engines/fluent.py` (the `url` capture), `engines/single_call.py`,
  the loader, D02.
- FastAPI and Flask: not needed for an address (§2d). The same form can later name a route
  (`name`, `endpoint`) if that is ever published.
- **Pro:** it extends an existing key and its existing word. The framework's rule stays in
  the catalog. Cost: one string change per row with no name.
- **Con:** a new form of the key.

**Option B — new closed words** (`hyphenated_construct_name`, and one with click's suffixes).
- **Con:** click's suffix list would live in general code. That is framework knowledge outside
  a catalog. A third framework's rule would need a third word.

**Option C — no rule.** A command with no written name gets the named hole `<name>`, `partial`.
- **Con:** true, but Sextant's two groups then read `sextant <name> analyze`. That fails the
  plan's own test.

**Recommendation: A.**

### 3d. Gap 4 — the decorators between, and which options belong to which command

**Gap 4 and the option-to-command link are one need.** The registration
(`module.command("analyze")`, applied by `__call__`) receives the function through every
decorator below it. Follow that argument back to the function. The calls the walk passes
through are the command's other decorators. So one walk answers both: which function is the
handler, and which `click.option` calls are its options.

**It is an instance of OI-262.** OI-262 is "a value passed through a library call that returns
its argument (`Objects.requireNonNull(c)`) ends the producer walk". Applying the result of
`click.option(...)` returns its argument the same way (`_param_memo(f, …); return f`, click
8.5.0). So the general need is: **a stated library call returns one of its arguments, and the
producer walk goes on through that argument.**

**What the walk does.** The `handler` capture of a `__call__` terminal is followed back with
the existing producer walk (`values.producer_paths`):
- a function (`lambda` argument): the handler;
- a call into module code: the walk goes into the code, as it does today (a call → its
  return values; a parameter → its arguments). polar's `version` returns the function, so the
  handler is the function. CTFd's `admins_only` returns a `functools.wraps` wrapper, so the
  handler is the wrapper. This is true: the framework calls the wrapper. This assumes Task 8's
  binding of a call on a function value; the builder checks it;
- a call into a library that a value model states returns its argument: the walk goes on
  through that argument, and the call is recorded as one of the handler's decorators;
- any other library call: the handler is not read. The row is `partial`, reason `external`,
  detail naming the call (slowapi, `with_appcontext`, click's `pass_context`: 2 in the corpus).

**Option A — a value-model statement, `returns_argument` (needs approval).**

```yaml
# value-models/click.yml
returns_argument:
  - { owner: click.decorators, method: option,   result_returns: arg0, by: scripts/probes/click_commands.md }
  - { owner: click.decorators, method: argument, result_returns: arg0, by: scripts/probes/click_commands.md }
# OI-262 would use the same key, measured separately:
#  - { owner: java.util.Objects, method: requireNonNull, returns: arg0, by: … }
```

- `returns: argN` — this call returns its argument N.
- `result_returns: argN` — calling this call's result returns that call's argument N.
- `by` is required, as for `identified_by` (D02 §1f). One entry per measured method.
- Files: `values.py` (the producer walk goes through a stated call), the value-model loader in
  `yaml_source.py`, `engines/fluent.py` and `shapes/chains.py` (the `handler` capture is walked
  and its decorators kept), D02 §1f.
- FastAPI: `APIRouter.get` and the other verbs `result_returns: arg0` (its `decorator` returns
  `func`), so a function under two route decorators (polar 1) is two rows. Flask: `route` the
  same (CTFd 6 such functions).
- **Pro:** one general rule in the value walk, data in value models. It also closes OI-262's
  class of cases. Cost per registration: one hop per decorator (at most 10 measured), each a
  hash lookup, on the walk the resolve already caches.
- **Con:** a new value-model key. Each entry needs a probe.

**Option B — a scanner rule: a signature `(T) -> T` returns its argument** (a fact change, to
make the result the same value as the argument).
- **Con:** false for a common typed idiom, `def deco(f: F) -> F: … return cast(F, wrapper)`.
  A wrong `resolved` is a lie (ruled). It also needs a fact change.

**Option C — a click-only catalog key, `passes_function: [option, argument, …]`.**
- **Con:** framework knowledge kept per catalog, a key one catalog uses, and OI-262 stays
  open.

**Recommendation: A.**

**Options as `request_params` (needs approval).** The decorators the walk recorded are
matched by an extension of §2k's `request_params`. On a `fluent` or `single_call` catalog, an
entry names a call instead of an annotation, and the attribute keys read that call's
arguments:

```yaml
request_params:
  - { owner: click.decorators, method: argument, kind: argument, name_arg: 0,
      requirement: required, required_arg: { keyword: required }, default_arg: { keyword: default } }
  - { owner: click.decorators, method: option, kind: option, name_arg: 0,
      requirement: optional, required_arg: { keyword: required }, flag_arg: { keyword: is_flag } }
```

- `requirement` is the framework's default. `required_arg` written as a literal boolean
  replaces it. A `default_arg` that is written makes the entry `optional` (click's `Argument`).
- `flag_arg` written as the literal `True` makes the row's kind `flag`: the option takes no
  value.
- New `kind` values: `argument` (a positional word), `option` (a named value), `flag` (a named
  switch). §2k's kinds are a closed set, so these need approval.
- Rows go to `endpoint_metadata` as today. They carry `caller` = the handler, `direction =
  inbound`, `protocol` and `method` NULL, `path` = the command words and `row_id` NULL (no
  `endpoints` row exists for an `entry_point`).
- FastAPI and typer: not used. Their parameters are the function's own (§3c `Depends`,
  `Query`, `typer.Option`), read by §2k's parameter form.

## 4. Groups, and the program's name

Spec §3c says click groups use the `mount` block. Two things make that work.

**A group's chain makes a router (needs approval: one new value).** A mount today receives its
router as an argument (`router_arg: N`). `@cli.group() def module` makes the router: the
`Group` that `cli.group()`'s result returns when applied to `module`. A mount entry may say
`router_arg: chain_result`:
- The entry is matched on a **root** call (`Group.group`).
- The router is what that chain's terminal returns.
- The prefix is that chain's own path (`prefix_from: receiver_path`): the word `module`.
- As for every mount chain, the chain makes no row of its own (D02 §2 `fluent`, Vert.x's
  `subRouter`).
- The mount call is itself the producer of the router it mounts, so no return type is
  needed. Python call sites carry no return type.

**Words are joined by spaces (ruled: a rule, no key).** A catalog with `root_kind: entry_point`
joins each word to the words before it with one space. A command is typed that way. The
catalog already says `root_kind`, so no `path_join` value is added. `path_join`'s one value
`leading_slash` stays as it is for endpoints.

**The outermost word is the program's name (my call; a rule, no key).** A program is started by
the name it is installed under. click ignores the top group's own name and uses the program's
name (`_detect_program_name`, click 8.5.0). The rule, for a `root_kind: entry_point` catalog:
- The outermost router's word is the name of the `entry_points` entry that names it (field
  approved).
- Where no entry names it, the word is the named hole `<program>`, `partial`, reason
  `external`, detail "the program is named by how it is installed".

## 5. Worked example: Sextant's own commands

**Facts** (`sextant/cli/app#<clinit>`, the report's measured ordinals for `module analyze`;
the others are written the same way):

```
c0  click/decorators#group()                   result r0
c1  __call__ recv r0 (lambda cli)              result r1   → field cli
c2  click/core#Group.group() recv cli          result r2      (owner from gap 2, 9a)
c3  __call__ recv r2 (lambda module)           result r3   → field module
c4  click/core#Group.group() recv cli          result r4
c5  __call__ recv r4 (lambda system)           result r5   → field system
c7  click/core#Group.command("analyze") recv module       result 10
c9  click/decorators#argument("path", type=<11>)          result 12
c11 click/decorators#option("--workspace", "workspace_dir", type=…, default=None)  result 14
c12 click/decorators#option("--allow-resolve", "allow_resolve", is_flag=True, …) result 15
c13 click/decorators#option("--shadow", "shadow", is_flag=True, …)               result 16
c14 __call__ recv 16 (lambda module_analyze)  result 17
c15 __call__ recv 15 (17)                     result 18
c16 __call__ recv 14 (18)                     result 19
c17 __call__ recv 12 (19)                     result 20
c18 __call__ recv 10 (20)                     result 21  → field module_analyze
```

Module fact: `entry_points: { sextant: "sextant.cli.app:cli" }` (9a; the approved shape, program
name → target as written).

**The catalog** (`src/sextant/catalogs/click.yml`, abridged):

```yaml
id: click
style: fluent
root_kind: entry_point                     # approved 2026-11-06
measured:
  - { artifact: click, versions: ["8.5.0"], identity: reported, by: scripts/probes/click_commands.md }
matches:
  path_fallback: { name: construct_name, lower: true, replace: { "_": "-" },
                   drop_suffixes: [command, cmd, group, grp] }
  roots:
    - { owner: click.core.Group, method: command, captures: { url: { arg: 0, keyword: name } } }
    - { owner: click.decorators, method: command, captures: { url: { arg: 0, keyword: name } } }
    - { owner: click.core.Group, method: group,   captures: { url: { arg: 0, keyword: name } } }
    - { owner: click.decorators, method: group,   captures: { url: { arg: 0, keyword: name } } }
  steps:
    - { method: __call__, captures: { handler: arg0 } }
  terminal: [__call__]
  router_type: [click.core.Group]
  mount:
    - { owner: click.core.Group, method: group, router_arg: chain_result, prefix_from: receiver_path }
    - { owner: click.decorators, method: group, router_arg: chain_result, prefix_from: receiver_path }
  request_params:   # the two entries of §3d
```

**The resolve, for `module analyze`:**
1. Root c7 matches `Group.command` (owner from gap 2). Its `url` is `{arg: 0, keyword: name}`:
   position 0 is `"analyze"`.
2. Terminal c18 captures `handler: arg0`, the value 20. The walk (gap 4): 20 is the result of
   c17. c17 calls result 12, made by `click.decorators#argument`, which `result_returns: arg0`.
   So go on to c17's argument, 19. The same happens at c16 and c15 (`option`), and at c14,
   which receives `lambda module_analyze`. The handler is `sextant/cli/app#module_analyze`.
   Recorded decorators: c9, c11, c12, c13.
3. The prefix (§4): c7's receiver is field `module`, written from c3. c3 is the terminal of a
   chain rooted at c2, a mount with `router_arg: chain_result`. c2 names no word, so
   `path_fallback` applies to c3's function: `module` → `module`. That chain's receiver is
   field `cli`, written from c1. c1 ends a chain rooted at c0, another mount. `cli` is the
   router the entry point `sextant` names, so its word is `sextant`, not `cli`.
4. Words joined with spaces: `sextant module analyze`.

**`roots` rows** (6; `root_kind = entry_point`; `protocol`, `method`, `method_kind`,
`path_kind` NULL):

| `path` | `handler` |
|---|---|
| `sextant module analyze` | `sextant/cli/app#module_analyze(…).` |
| `sextant module render` | `sextant/cli/app#module_render(…).` |
| `sextant module enrich` | `sextant/cli/app#module_enrich(…).` |
| `sextant module export` | `sextant/cli/app#module_export(…).` |
| `sextant module diff` | `sextant/cli/app#module_diff(…).` |
| `sextant system analyze` | `sextant/cli/app#system_analyze(…).` |

The groups `cli`, `module` and `system` are mount chains, so they make no row.

**`request_params` rows for `sextant module analyze`** (`endpoint_metadata`, `caller` = the
handler, `value` NULL, `resolution: resolved`):

| `kind` | `name` | `requirement` | Why |
|---|---|---|---|
| `argument` | `path` | `required` | an argument with no `default` and no `required=` |
| `option` | `--workspace` | `optional` | no `required=True` |
| `flag` | `--allow-resolve` | `optional` | `is_flag=True` |
| `flag` | `--shadow` | `optional` | `is_flag=True` |

Over the six commands: 24 rows (7 `argument`, 13 `option`, 4 `flag`: `--allow-resolve`,
`--shadow`, `--dry-run`, `--allow-producer-change`).

**Not in these rows: the type.** `type=click.Path(...)` has no column. `endpoint_metadata` has
none, and §2k's `value` is a demanded value, not a type. The plan's test "`path` is a required
argument of type path" drops "of type path" (my call). A type column is a separate request.

## 6. The same rules on one polar route (plan 2, sketch)

```python
# polar/webhook/endpoints.py
router = APIRouter(prefix="/webhooks", tags=[...])    # APIRouter from a type[_APIRouter] factory

@router.get("/endpoints/external/{external_id}", summary=..., response_model=WebhookEndpointSchema, ...)
@version(starting_from=V2027_01)                       # polar/kit/versioning.py: returns `endpoint`
async def get_external_webhook_endpoint(external_id: str, auth_subject: WebhooksRead, ...): ...

# polar/api.py:  router = APIRouter(prefix="/v1"); router.include_router(webhook_router)
# polar/app.py:  app.include_router(router)
```

- **Owner.** `router.get` is `fastapi/routing#APIRouter`, by §3a's `type[X]` rule. Gap 2's rule
  is not used.
- **Root.** `{ owner: fastapi.routing.APIRouter, method: get, captures: { http_method: GET,
  url: { arg: 0, keyword: path }, response: { keyword: response_model } } }` (gap 1).
- **Handler.** The `__call__` terminal's argument is the result of applying `version(...)`'s
  result. `version` is module code. The walk goes into it: it returns its inner `decorator`,
  which returns its parameter `endpoint`, which is the function (gap 4, no value model needed).
  A route under two route decorators uses `result_returns: arg0` on `APIRouter.get`.
- **Prefix.** `include_router` is `mount: { router_arg: { arg: 0, keyword: router },
  prefix_arg: { keyword: prefix } }` (gap 1 on an existing key). The router's own
  `prefix="/webhooks"` and `prefix="/v1"` are set when it is made. Plan 2 decides how they are
  read: a base the router holds, as `client_base` reads a client's base (§1g), with
  `value_arg: { keyword: prefix }`. This design gives it the keyword form only.
- **Row.** `GET /v1/webhooks/endpoints/external/{external_id}`, response
  `WebhookEndpointSchema`, handler `get_external_webhook_endpoint`. Its parameters come from
  the function (§3c), not from decorators.

The same handler walk serves Flask. CTFd's `@admin.route(...)` over `@admins_only` gives the
`functools.wraps` wrapper as the handler, which is what Flask calls. `methods=["GET", "POST"]`
is a closed list, so it gives one row per verb.

## 7. The two detector items

### 7a. `[project.scripts]` is not recorded

Spec §3e says the detector reads `console_scripts`/`[project.scripts]`. It does not.
**Recommendation (my call):** read the entry points into the approved `entry_points` field:
- `[project.scripts]` (Sextant, dispatch, mealie, netbox);
- `setup.cfg` `[options.entry_points] console_scripts` (httpie);
- `[tool.poetry.scripts]`. It is not in the corpus, but the detector already reads Poetry's
  table, and it has the same form.

Each entry keeps its name and its target as written (`sextant.cli.app:cli`). The resolver turns
the target into a symbol: a module-level name (field `sextant/cli/app#cli.`) or a function.
`[project.gui-scripts]` and `setup.py` `entry_points=` are not read (`setup.py` is a program,
§3e). Cost: one table read per build file already opened.

### 7b. An agent worktree is found as a second `sextant` module

`.claude/worktrees/agent-…/` holds a `.git` **file** (a git worktree). It is not git-ignored
here, so the walk enters it and finds a second `pyproject.toml` named `sextant`.

- **Option A (recommended, my call):** a folder below the given root that holds `.git` (a
  folder or a file) is another checkout: a clone, a worktree or a submodule. It is not entered,
  and the report notes "another repository, not analysed: <path>". The given root is always
  read. The rule goes in `is_skipped_folder`, which the detector and the scanner share.
  **Pro:** git's own boundary, no list of names; it also covers nested clones. **Con:** a
  submodule is skipped too. No Python project in the corpus has one, so submodules are logged,
  not built (ruled: issues real input cannot trigger get logged). Cost: one `stat` per folder.
- **Option B:** add `.claude` to the skipped names. **Con:** a special case for one tool.
- **Option C:** git-ignore `.claude/worktrees`. **Con:** it fixes only this repository.

## 8. Performance (GUIDELINES §8.7)

| Rule | Cost |
|---|---|
| Keyword reference (gap 1) | one pass over one call's arguments per read; no new pass |
| `Callable` result type (gap 2) | scanner only: one cached `call_returns` per call of a value; one table per file for module-level names |
| `path_fallback` mapping (gap 3) | one string change per row with no written name |
| Handler walk through `returns_argument` (gap 4) | one hop per decorator per registration (at most 10 measured), each a hash lookup, on the resolve's cached walk |
| `router_arg: chain_result` | one producer per group chain, read with the existing mount reads |
| Detector items | one table read per build file; one `stat` per folder |

Base for Sextant: 8.5 s cold and warm (report). polar: 576 routes × at most 2 hops. Each task
records the measured time against the spec §5 target, as Task 1 set.

## 9. Non-goals, and what is left to the builder

**Not in this design** (each is logged with the next free OI id when Task 9 commits):
- typer, argparse, and entry points that name a function (mealie, netbox, httpie). An
  entry-point function that calls a group (dispatch: `entrypoint` → `dispatch_cli()`) is the
  next step of the same rule.
- A group's own options; a group's function as a hop before its commands;
  `invoke_without_command=True` (polar's typer, 2).
- Options with two spellings (`-v`, `--verbose`; dispatch 9): §2k's rule applies until ruled
  (`name` NULL). Boolean pairs (`--shout/--no-shout`) as flags. A parameter's type (§5).
- Library decorators that return a new function: the handler is `partial`, `external`.
- A wrapped handler's parameters (FastAPI reads `__wrapped__`; CTFd 56 routes), the FastAPI
  and Flask catalogs, and a router's construction prefix: plan 2.
- The `requireNonNull` entry that would close OI-262 with the same key. It needs its own
  measurement on the 11 corpora (ruled 2026-11-03).

**Left to the builder:**
- Error texts, and the loader's exact checks for each new form.
- Where the program-name rule lives (`roots.py` or `mounts.py`).
- Checking that Task 8 binds a call on a function value (§3d, module-code decorators). Sextant
  does not need it in plan 1.
- The overload choice for `Group.command("analyze")` (§3b).
- The `evidence` word on the new rows: the one the Python reader already writes.

## 10. What the user must approve

1. **Keyword argument reference:** `{ keyword: <name> }` and `{ arg: N, keyword: <name> }`,
   accepted wherever a catalog names an argument; `argN` counts positional arguments only.
2. **`returns_argument`** (value models): `{ owner, method, returns: argN | result_returns: argN,
   by }` — a stated library call returns one of its arguments, or calling its result does.
3. **`path_fallback` on `fluent`/`single_call`, and its mapping form** `{ name: construct_name,
   lower, replace, drop_suffixes }` — a word from the handler's name, respelled as the catalog
   states.
4. **`request_params` naming a call** — `{ owner, method, kind, name_arg, requirement,
   required_arg?, default_arg?, flag_arg? }`, read off the decorators the handler walk passed.
5. **Three `kind` values:** `argument`, `option`, `flag`.
6. **`mount[].router_arg: chain_result`** — the router is what the chain this root starts
   returns; its prefix is that chain's own path.
7. ~~`path_join: space`~~ — dropped (user, 2026-11-06). Replaced by the rule in §4: an
   `entry_point` catalog joins words with one space.

Not keys, for review only: the `Callable` result-type scanner rule (gap 2), the program-name
rule and the space-join rule (§4), the nested-checkout rule (§7b), and reading entry points into the approved field.

## 11. Replacement Task 9 outline

Split in two (my call). 9a is facts and modules. Each of its parts shows in Sextant's own
facts or module list, with its own tests, so a reviewer can approve it alone. 9b is the
catalog and its engines, which cannot be approved in halves: a key with no catalog that reads
it is the half-built shape the implementer stopped on.

### Task 9a: decorator-factory types and entry points

- **Files:** `ingress/extract/python/libraries.py`, `calls.py`, `ingress/detect/python.py`,
  `ModuleModel`/`ModuleFact` (`entry_points`, approved), M02, M03, D00.
- **Tests:** calling a `Callable` result gives its return type (`cli` is `click/core#Group`);
  `module.command("analyze")` has owner `click/core#Group`; an applied `option(...)` stays
  untyped; a module-level name keeps the types written in its file; `[project.scripts]` and
  `console_scripts` become entry points; a folder with a `.git` file or folder is another
  repository.
- **Done when:** Sextant's own facts carry owner `click/core#Group` on its 8 group and command
  calls. Detecting the repository root with a worktree present finds one `sextant` module, with
  `entry_points = [sextant → sextant.cli.app:cli]`. Gate and six field pins pass. The time is
  recorded.

### Task 9b: commands as `entry_point` roots

- **Files:** create `catalogs/click.yml`, `catalogs/value-models/click.yml`,
  `scripts/probes/click_commands.md` (the click 8.5.0 rules quoted in §2d, §3d and §4). Modify
  `shapes/arguments.py`, `ingress/catalogs/yaml_source.py`, `shapes/mounts.py`,
  `shapes/chains.py`, `shapes/inbound_routes.py`, `engines/fluent.py`, `engines/single_call.py`,
  `values.py`, `request_requirements.py`, `roots.py`, `endpoints.py` (an `entry_point`
  catalog has no wire style), D02 (§1f, §2 `single_call`/`fluent`/`mount`, §2k),
  `docs/open-issues.md` (OI-22 closes, the OI-323 id-map row, the §9 items logged).
- **Tests** (`tests/application/test_entry_point_roots.py` and the loader tests): the plan's
  four (`request_params` without the type); a group named from its function (click's suffix
  rule, and typer's data without it); a keyword read by name; a position that skips keyword
  arguments; an unpacked mapping that makes a keyword `not_readable`; the walk through a stated
  decorator; an unstated library decorator that leaves the handler `partial`; the entry-point
  name as the outermost word, and `<program>` with none; the loader refusing each malformed
  new form.
- **Done when:** exactly the 6 `roots` rows of §5, each with a trace of at least one hop. Exactly
  the 24 `request_params` rows, checked by hand. Every JVM catalog derives the same rows as
  before (gate and six field pins). D02 states each approved form. The time is recorded against
  the spec §5 target.
