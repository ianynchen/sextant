# Python: reading Python code with the JVM's pipeline — design

**Status: DRAFT v2 2026-11-06, for the user's approval.** Plane OI-208 = SEXTANT-201 (language order 2,
ruled 2026-10-26). v1 was agreed in conversation on 2026-11-06. It was then reviewed twice: once from
first principles, and once adversarially for reuse ("stick to the current design, reuse, extend
existing terms before adding new ones" — user, 2026-11-06). v2 takes both reviews in. The reviews are
kept beside this file as `2026-11-06-python-reader-review-first-principles.md` and
`2026-11-06-python-reader-review-reuse.md`.

Marks:
- **(ruled):** the user decided it.
- **(my call):** my decision; the user can reject it.
- **(DECIDE):** open for the user.

## 1. Intent

Java and Kotlin are complete. Python is next. The goal is the same as for the JVM (ruled): from the
code alone, get:
- what a service serves;
- what it calls;
- the shapes of the data on each;
- the configuration values behind each address;
- the path a request takes through the code.

Python services must stitch together, so types the code does not write must be worked out (ruled).
FastAPI comes first, then Flask, then Django (ruled 2026-10-26). Sextant's own code is the first
project read, to test the reading of Python (ruled).

**The governing principle of v2:** Python adds a **scanner** that writes the existing facts. Every
step after the facts is the existing one, extended where Python needs it. Nothing runs beside it.

## 2. What was measured (2026-11-06)

**Projects:** eleven open-source projects, shallow-cloned into `examples/py-*`:

| Framework | Projects (commit) |
|---|---|
| FastAPI | polar 0e5a3f1, dispatch dd2837e, mealie c3dc906, full-stack-fastapi-template aabb901 |
| Flask | redash 09740ea, CTFd a6a81dd |
| Django | netbox 3baeb0a, zulip 82b428a, saleor 1d707dc |
| other | httpie `cli` 5b604c3, microservices-demo c7cb6d5 |

**Scripts:** `scripts/probes/python_shapes.sh`, `python_typed_share.py`, `python_call_kinds.py`
(run with `python -I`).

**Written types** (function inputs with a written type, outside tests and migrations):

| polar | zulip | mealie | dispatch | saleor | netbox | redash | CTFd | Sextant |
|---|---|---|---|---|---|---|---|---|
| 99% | 99% | 88% | 82% | 56% | 2% | 1% | 1% | 100% |

**Facts the reviews measured, which decide parts below:**

| Measured | Where |
|---|---|
| 878 calls on imported module-level singletons (`order = OrderService()`, then `order.create(...)`); 86 routers, apps and clients assigned at module level | polar |
| 80 of 83 router files get `APIRouter` from a factory whose return is written `type[_APIRouter]` | polar |
| `Field(alias=…)`: 127 / 129 / 26 uses | polar / mealie / dispatch |
| a base-model `alias_generator=camelize`: every shape is camelCase on the wire | mealie |
| at least 17 outbound URLs are f-strings | polar |
| 194 operations in the published OpenAPI against 608 route decorators (tag filters, 44 `include_in_schema=False`, version pruning) | polar |
| calls outside any function: 12.8% / 57.8%; the §2 call table of v1 left these out | polar / netbox |
| names defined twice in one scope (property setters, `@overload`, conditional definitions): 38 / 10 / 10 | polar / saleor / zulip |
| 2,540 `@overload`s (`subprocess.run` is one) | typeshed's standard library |
| 6 commands in 3 groups | Sextant |
| commands: typer, 107 files | polar |
| commands: `argparse`, programs declared in `setup.cfg` `console_scripts` | httpie |

## 3. The architecture (my call, from both reviews)

### 3a. The scanner (M03) reads one file at a time, as M03 requires

The Python scanner is a new `Scanner` backend (`ingress/extract/python`, `accepts({python})`). M03's
rule holds: no reasoning across files. Per file, it writes the existing facts:

- **Symbols.**
  - A Python module (file) is a type, `app/api/items#`. This is the Kotlin file-facade precedent
    (`FooKt#`), which owns top-level functions.
  - Classes are types. Functions and methods are methods.
  - A module body is the module type's static initializer (`<clinit>`). A class body is that class's
    `<clinit>`. D00 already maps `__init__` to `<init>`.
  - Module-level names (`app = FastAPI()`, `order = OrderService()`, `urlpatterns = [...]`) are
    static fields, written by `field_write` from `<clinit>`. They are not `constant`, because a
    Python global can be rebound.
- **Descriptors.**
  - Python has no overloads. Every method's descriptor is one constant signature string, hashed by
    the existing `disambiguator_of`, so a call and its callee meet by arithmetic, as on the JVM.
  - A name defined twice in one scope is handled by its kind:
    - a property's getter and setter are two members (`x` and `x=`);
    - `@overload` stubs are type information, not bodies;
    - two real definitions (conditional ones) are a closed list of bodies, one row each.
- **Types written in the code (rule 1),** through imports bound to symbols:
  - `Optional[X]` is `TypeRef.nullable`.
  - A union is `TypeRef` arguments.
  - `type[X]` returns `X` itself (polar's router factory).
  - `@overload` signatures are chosen by argument types. Where they cannot be told apart, the
    result is the closed list of their return types.
  - `TypeVar`, generics, `Protocol`, `Annotated`, `Self`, ParamSpec and `dataclass_transform`
    (needed for Pydantic and SQLModel) are read as the typing specification defines them.
- **Flow inside one function:**
  - value ids;
  - `merge` arguments;
  - the per-path fields (`dominator`, `on_every_exit`, `post_dominator`, `reaches_return`,
    `loop_group`);
  - f-strings and `+` as `concat` arguments;
  - lists and tuples as `array` arguments;
  - keyword arguments bound to parameter positions where the callee's signature is known.

  For control flow, every expression may raise, and a `with` block may swallow an exception.
- **Calls whose owner is not known in this file:** the call names its receiver's value id and the
  method name. The owner is bound later (§3b). **This is the one `call_site` format extension:**
  `target.owner` may be absent when `receiver` is present and `invoke_kind` is `virtual`. It is
  approved with this design.
- **Decorators are written as the calls they are.** `@router.get("/x")` on `def f` is the call
  `router.get("/x")` and the call of its result with `f` (a `lambda`/method-reference argument).
  `@click.command()` and typer's `@app.command()` are the same. So the router or group a route
  belongs to is kept. They are never written as `annotation` facts.
- **Evidence:**
  - a type written in the code is `evidence: declared`;
  - a type worked out by a rule is `evidence: syntax` with `resolution: narrowed` where it is a
    closed list (D00's existing words).

  No new marker.

### 3b. The resolver binds what one file cannot know

Rules 2–4 of v1 moved here, onto the existing value walk ("follow the object", ruled 2026-10-30).
The receiver of an unbound call is followed to what produced it:
- a constructor call → that class;
- a call → that callee's `return` values, by `return_flow`;
- a parameter → the arguments at its callers, crossing per path;
- a field → every `field_write` to it, per object;
- a static field (module-level name) → its write in `<clinit>`.

**Per path, never combined (ruling M-1):** a parameter whose callers pass a requests session on one
path and an httpx client on another gives two rows, each with its own URL. Never four.

**Which callers count:** the walk's existing rule. Callers in the scanned module and its sibling
modules count. No caller means `external`. A function passed as a value is `escapes` unless a catalog
says who calls it. Python has no enforced `private`, so the JVM's "private and never called" test is
not applied to Python.

**Lookup through class parents:**
- `Dispatch.ancestors` becomes one per-type **lookup order** that every language provides.
- The JVM's order stays as it is. Python's is C3 linearization, worked out in the resolver from the
  written parents.
- The rule is named by the module fact (`lookup: jvm | c3`). These are two named rules, because the
  languages differ (DR-6).
- `_NOT_INHERITED` and the `java/lang/Object` end are JVM rules inside the JVM order. Python's
  `__init__` is inherited.
- An unread parent ends the order with `external`, as an unscanned JVM ancestor does.

**A body exists** when a `method_return` fact exists. The scanner writes the implicit `return None`.
`@overload` stubs, `Protocol` members and `...` bodies of abstract methods are not bodies.

### 3c. Catalogs hold all framework knowledge, in existing words

| Python need | Existing word it uses (D02) |
|---|---|
| FastAPI routes, Flask routes | `single_call`/`fluent` with `handler_arg` (decorator as call, §3a) |
| `include_router(prefix=)`, click/typer groups | the `mount` block (`shapes/mounts.py`) |
| `Depends(...)` | the DI-recipe hop (`bean_model`), with one new `injection` mode: the parameter names its recipe. A dependency's own parameters join the route's `request_params` (§2k), as FastAPI does. |
| query, path, header, cookie, body parameters | `request_params` (§2k), with `Query`/`Path`/`Header`/`Body`/`Field` normalized into `Parameter.annotations`; defaults into `declares_default` |
| Pydantic shapes | a `shape_model` (`pydantic.yml`, §1b), naming by §2f, which must read `Field(alias=)`, `serialization_alias` and a model's `alias_generator`; `known_types` (§2g) for `datetime`, `UUID`, `Decimal` |
| `response_model=` and the return type | `response` words, FastAPI's own rule: `response_model` first |
| `httpx.Client(base_url=)` | `client_model`/`client_base` (§1g) |
| `.request("GET", url)` | `verb_arg` |
| `.model_dump()` as a body | value-model data, not a per-method rule |
| `subprocess.run([...])` | `single_call` (if §6 keeps program starts) |

### 3d. Configuration values (my call, reusing the JVM's)

- **`os.environ[...]`, `.get`, `os.getenv`:** value-model data. The address keeps the expression
  (`${KEY}`), and `resolved_peers` answers per environment, `external` where nothing in the
  repository sets it. This is how the JVM treats a placeholder.
- **pydantic-settings `BaseSettings`:** the field-sources ladder (§2j rung 3). The environment name
  comes from `env_prefix` plus the field name or alias.
- **`.env`:** a `config_model` source, **only the file the code names** (`env_file=`), resolved as a
  value. A file chosen by an environment variable is `external`. A `.env` the code never names is
  not read.

### 3e. Finding modules (M02) and their libraries

M02 is keyed by build system, and languages are observed, not taken from file names. v1 said the
opposite and was wrong.

**The detector:**
- **Build systems:** a new Python detector beside Maven and Gradle. It reads:
  - `pyproject.toml` (`[project]`, Poetry's table, `[build-system]`);
  - `[tool.uv.workspace]` members;
  - `setup.cfg [metadata]`;
  - `console_scripts`/`[project.scripts]`.
- **uv workspaces:** a workspace root with no code of its own is not a module. Its members are.
- **`requirements*.txt`, `Pipfile`:** a service with only these is a module whose build system is
  "requirements" (the five microservices-demo services).
- **`setup.py`:** a module only when it is not inside a package (no `__init__.py` beside it or
  above it) and no folder above it is already a module. This removes the four false modules
  measured (CTFd ×2, redash, polar). A `setup.cfg` with no `[metadata]` (CTFd's holds only
  `[nosetests]`) does not mark a module.
- **The language** is observed: `.py` files under the module.
- **A folder of `.py` files with no project file** is listed, not analysed (ruled).

**Import roots** (the folders a name like `app.api` is found from):
- the build system's package settings (setuptools, hatch, poetry `packages`, a `src/` layout);
- otherwise the module folder.

A `sys.path` change in code is not followed (zulip, 15 files). Names it would make visible are
`external`, with the detail naming the change.

**Identity** (OI-273 "what the build tool gives"):
- `[project]`/Poetry/`setup.cfg` name and version, normalized by PEP 503.
- A dynamic version comes from the installed project's `.dist-info` when there is one, otherwise `.`.
- With no build file, the module is unpublished (D00 `.` fields, its folder path as id).
- The symbol scheme is `sextant-python pypi <name> <version> <descriptors>`.

**Libraries (ruled: no flag, nothing downloaded):**
- **Read from the project's installed environment:** `.venv`, `venv`, or the environment uv or Poetry
  settings name. `.python-version` names an interpreter, not an environment, and is not used.
- **What is read:** library signatures and type files are read for every library. Library bodies are
  read only under D04 §2a's existing opt-in (`extract_libraries`), as for jars.
- **Library symbols are always the defining symbol** (`fastapi.routing.APIRouter`), never a
  re-export. A library that is not installed has no symbols. So its routes and calls are not read,
  and the report says `fastapi is not installed in the scanned environment`. This keeps symbols the
  same on every machine.
- **Catalogs** are selected by `detect.coordinates` against the module's declared dependencies, as
  on the JVM.
- **`typeshed`:** a pinned copy ships in the wheel, for libraries that do not ship their own types
  (`requests`). Flask, FastAPI and Pydantic ship their own. Each fact read from typeshed carries
  typeshed's commit and the stub package's version as provenance.
- **`--allow-resolve`:** does nothing for Python.

**Scanner capabilities** (they decide which catalogs run), stated in the plan:
- `typed_signatures`, `annotation_args`, `type_annotations`;
- control-flow fields;
- value ids;
- library signatures.

## 4. Non-goals and anti-goals

**Not in this design:** Flask, Django, Django REST Framework, background tasks, messaging, gRPC, and
`sextant.api` library functions as endpoints (ruled).

**Anti-goals:**
- importing or running scanned code (Sextant itself never does; the test setup may, §7);
- downloading anything;
- a guess shown as `resolved`;
- framework names in general code;
- a second pipeline;
- a new word where an existing one fits.

## 5. Performance (GUIDELINES §8.7, decided here, not later; my call)

- **The scanner:** one pass per file, cached by content hash as the JVM extractor caches per class,
  run in parallel.
- **The resolver:** receiver binding is the existing value walk. Its pass count is bounded by the
  depth of producer chains, and the walk already caps that.
- **Budget, measured on polar's server** (2,382 files, 47,716 call sites, 257 locked packages, this
  machine): a cold analysis under 5 minutes, and a warm one with no file changed under 30 seconds.
- **The first plan task** measures reads per resolve on polar before building the passes, and stops
  for a ruling if the budget cannot be met.

## 6. Command-line commands and program starts (DECIDE)

Both reviews found that v1's two new protocol words are the weakest part:

- **Not stitched.** `cli` and `process` rows never link to anything. Linking needs the same protocol
  on both ends, and the two paths cannot be compared.
- **A slot exists already.** A program's starting point has a slot: D00 `root_kind: entry_point`, a
  member with no producer (OI-22, "closes with a catalog declaring the entry point").
- **Program starts are not JVM parity.** The JVM side does not record them either.

Options:

- **A. Commands fill the existing `entry_point` root** (no new word). Each `click`/typer/`argparse`
  command becomes a trace root, its options become the root's `request_params`, and its handler is
  the root.
  - Sextant's 6 commands become 6 roots with traces, which tests the reader end to end.
  - The same catalog rule later gives picocli and Clikt `main` roots, and closes OI-22 for the JVM
    too.
  - Program starts are logged for later.
  - **Pro:** no new word, closes an open JVM issue, and tests the reading as ruled.
  - **Con:** commands are roots, not inbound endpoint rows, so they do not appear in the endpoint
    table.
- **B. One new protocol word for both ends:** inbound commands, and outbound program starts, with the
  program as `peer` and the command words as `path`. Sextant's `java -jar extractor` call and the
  extractor's own command would then link.
  - **Pro:** the endpoint table shows them, and the two ends can link.
  - **Con:** a new protocol word, and new rules for the stitcher.
- **C. Skip both.** FastAPI end to end comes first, and Sextant is read only as a reader test.
  - **Pro:** the smallest first release.
  - **Con:** it goes against "start with Sextant" (ruled).

**My recommendation: A.** It reuses an existing slot, closes OI-22, and does what "start with
Sextant" was for, which is testing the reader on code we know. B can follow when a real pair of
programs needs to link.

## 7. Done when

1. **Sextant reads itself.** Every call in Sextant's own code has a known target, or a reason. The
   §2 call table is produced by the real resolver, before and after receiver binding. If §6 is A:
   6 command roots, each with traces and `request_params` checked by hand.
2. **A FastAPI test project** (`fixtures/orders-fastapi`, our own) covering every row of §3c and §3d:
   - routers built by a factory with `type[...]`;
   - module-level singletons;
   - `alias_generator`;
   - f-string URLs;
   - an `env_file` setting.

   Its `uv.lock` is committed, and the test setup runs `uv sync`, as JVM fixtures are built with
   Maven and Gradle. Every row is pinned.
3. **Field pins: polar's server, dispatch and mealie** at the pinned commits, installed by the
   field-pin script with `uv sync`.
   - **The route oracle** is FastAPI's own `app.routes`, produced by the test setup importing the
     app (never by Sextant). Published OpenAPI is not the oracle; it filters routes (§2).
   - A sample of outbound rows is checked by hand.
4. **The performance budget** of §5 is met, and the numbers are recorded.
5. **Truth:** no `resolved` row carries a guessed type or value. Every unknown has one general reason
   and a detail, and the guard test covers the Python rows.
6. **Docs:**
   - D00: the `call_site` owner extension, the `lookup` field, the scheme;
   - D02: the new `injection` mode, `pydantic.yml`;
   - M02 and M03: the Python detector and scanner;
   - COVERAGE: Python rows, §3 and §3a versions;
   - `docs/research`: the type-tool comparison (own reader vs a type checker, including mypy
     in-process).
7. **The full check passes.**

## 8. Left to the plan

- Exact field names, approved before building, beyond the two named here (`call_site` owner
  extension, `lookup`).
- The scanner's internal layout.
- The fixture's exact contents.
- The pinned typeshed commit.
