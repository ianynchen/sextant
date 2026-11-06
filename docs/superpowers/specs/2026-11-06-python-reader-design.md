# Python: reading Python code, the command-line boundary, and FastAPI — design

**Status: DRAFT 2026-11-06, for the user's approval.** Plane OI-208 = SEXTANT-201 (language order 2,
ruled 2026-10-26). Agreed in conversation on 2026-11-06. Points the user ruled are marked **(ruled)**.
Points that are my call are marked **(my call)**, and the user can reject them.

## 1. Intent

Java and Kotlin are complete. Python is next. The goal is the same as for the JVM (ruled): point
Sextant at a Python service and get its architecture from the code alone:
- the routes it serves and the commands it accepts;
- the services it calls and the programs it starts;
- the shapes of the data on each;
- the configuration values behind each address;
- the path a request takes through the code.

Without types, Python services cannot be stitched together. So Sextant needs its own type
inference, not only the types written in the code (ruled).

Order of work (ruled 2026-10-26): FastAPI, then Flask, then Django.

## 2. What was measured (2026-11-06)

Eleven open-source projects were cloned into `examples/py-*` (shallow clones, commit in brackets):
- FastAPI: polar (0e5a3f1), dispatch (dd2837e), mealie (c3dc906), full-stack-fastapi-template (aabb901)
- Flask: redash (09740ea), CTFd (a6a81dd)
- Django: netbox (3baeb0a), zulip (82b428a), saleor (1d707dc)
- other: httpie `cli` (5b604c3), microservices-demo (c7cb6d5, five Python gRPC services)

Scripts, to produce the numbers again: `scripts/probes/python_shapes.sh`,
`python_typed_share.py`, `python_call_kinds.py` (run with `python -I` over `examples/py-*`).

**Written types (function inputs with a written type, outside tests and migrations):**

| polar | zulip | mealie | dispatch | saleor | netbox | redash | CTFd | Sextant |
|---|---|---|---|---|---|---|---|---|
| 99% | 99% | 88% | 82% | 56% | 2% | 1% | 1% | 100% |

FastAPI projects are typed, because FastAPI cannot run without types. Flask and Django projects are
mostly untyped. zulip is the exception, because it is checked with mypy.

**What a call needs before its target is known (rough sort by code shape, not a real resolver):**

| Needs | redash | CTFd | netbox | polar | dispatch |
|---|---|---|---|---|---|
| only the name (function, imported module, built-in, `self.method`) | 54% | 56% | 57% | 66% | 69% |
| what another function returns (variable set from a call, chained call, `self.field`) | 19% | 20% | 21% | 21% | 12% |
| an untyped parameter's type | 4.5% | 2.3% | 5.1% | 0% | 4.0% |
| a typed parameter's type | 0.1% | 0% | 0.1% | 4.1% | 6.1% |
| other (loop variables, complex expressions) | 22% | 22% | 16% | 9% | 8% |

**How often each shape appears (text counts, rough):** FastAPI route decorators (polar 608, dispatch 291,
mealie 290). Flask `.route` (CTFd 167, redash 31). Django `path()` (netbox 395, zulip 234). REST
Framework `register` (netbox 147). `requests` in every project. `httpx` (polar 497). Background tasks
(saleor 544, polar 242). Command-line commands (polar 233, zulip 123, redash 35, dispatch 32).

**Sextant itself:** 9 `click` commands, 8 `subprocess` calls (in `api.py`, `detect/gradle.py`,
`detect/maven.py`, `extract/jvm/scanner.py`, `read/proto_source.py`), and 100% written types.

## 3. Goals

1. **A Python reader** (my call, after options were compared; ruled "option 1"). It is our own code
   over Python's built-in `ast` parser. It does not use a type checker, and it does not run the project.
2. **Our own type inference** (ruled). The rules are in §6. Rules 1–4 ship with the first release, and
   rules 5–6 ship with Flask and Django (ruled).
3. **The command-line boundary** (ruled): a command is an inbound endpoint. The first project read is
   Sextant itself, which tests the reading of Python code (ruled). Only the command line counts as
   inbound for now. Library functions (`sextant.api.*`) are not endpoints (ruled).
4. **The program-start boundary** (my call): `subprocess.run([...])` and its relatives are outbound
   endpoints.
5. **FastAPI inbound, `requests` and `httpx` outbound, Pydantic shapes**, and Python configuration
   values for addresses.

Flask and Django are the next two items, each with its own design. They are decided against the real
service projects above (ruled).

## 4. Non-goals and anti-goals

**Not in this design:**
- Flask, Django, Django REST Framework, Celery and other background tasks, messaging, gRPC.
- `sextant.api` library functions as endpoints.

**Anti-goals.** Any of these makes the work a failure, even if it runs:
- importing or running the scanned project's code;
- downloading or installing anything (ruled: no flag, no network for Python);
- a type checker's guess, or any guess, shown as `resolved`;
- framework names in general code instead of in catalogs;
- a second pipeline beside the JVM one.

## 5. Finding Python modules (M02)

**Rule (ruled):** a project file marks one module, and the kind of file gives the language. This is
the rule Java and Kotlin already use.

| File at a folder's top | Module |
|---|---|
| `pyproject.toml`, `setup.cfg`, `requirements*.txt`, `Pipfile` | Python |
| `setup.py` | Python, **only** when there is no `pyproject.toml` or `setup.cfg` beside it |
| `pom.xml`, `build.gradle(.kts)` | JVM (unchanged) |
| `package.json`, `go.mod` | listed as found, language not read yet |

- **`.py` files are required.** A Python module counts only when `.py` files are under it.
- **Why `setup.py` is limited:** CTFd has ordinary code files called `CTFd/forms/setup.py` and
  `CTFd/constants/setup.py`, so the name alone would make false modules.
- **A folder of `.py` files with no project file is not analysed** (ruled). It is listed in the
  report as "Python files with no project file". Pointing Sextant directly at that folder analyses it.
- **Mixed repositories are normal.** microservices-demo has 10 services in three languages, with one
  project file each. polar has one Python service, four more Python projects and six JS/TS ones. Each
  is its own module.

**Identity (my call, following OI-273 "what the build tool gives"):**
- **With `pyproject.toml`:** `[project] name` and `version`. Poetry's `[tool.poetry]` is read when
  `[project]` is absent. The names are normalized as the package index does (PEP 503).
- **A dynamic version** (`dynamic = ["version"]`): the version is `.`, because no file states it.
- **No `pyproject.toml`:** the module is unpublished. Its id is the folder's path in the repository,
  and the symbol fields for manager, package and version are `.` (D00 "unpublished service").
- **Symbol scheme:** `sextant-python pypi <name> <version> <descriptors>`. Descriptors follow D00's
  SCIP grammar, with the module path as namespaces: `app/api/routes/items/create_item().`,
  `app/models/Item#`.

**Libraries (ruled: no flag, nothing downloaded):**
- **Where they are found:** the project's own installed environment: `.venv`, `venv` or `env` beside
  the project file, or one named in `.python-version` and `uv` or Poetry settings. Its
  `site-packages` is read like a library jar: source and `.pyi` type files.
- **With no project file:** the `import` lines show which libraries are used. Each is looked up in an
  installed environment.
- **Not installed:** calls into the library are `external`. The detail names it, for example
  `requests is not installed in the scanned environment`.
- **`typeshed`:** the shared collection of type files ships inside the wheel as a pinned copy, so
  `requests`, Flask and similar libraries have types even when the project's environment lacks
  them (my call). The pinned version is recorded in the scan provenance.
- **`--allow-resolve`:** it exists for Maven (OI-167) and does nothing for Python.
- **Library code (my call, "follow the code we have"):** signatures, inline types and `.pyi` files are
  read for every library the project calls. Rules 2–4 run inside a library body only for functions
  the project actually reaches, and only when no written type answers.
- **A library that is not installed:** its names are still known from the `import` lines
  (`from fastapi import APIRouter`), so catalogs match on the imported name. Routes are still found,
  but types from that library are unknown.
- **Test fixtures and field pins:** "nothing downloaded" applies to Sextant, not to the test setup.
  `fixtures/orders-fastapi` commits a `uv.lock` and the test setup runs `uv sync` into the fixture's
  `.venv`, as the JVM fixtures are built with Maven and Gradle. The field-pin script does the same for
  polar's server, dispatch and mealie at their pinned commits.

## 6. Type inference (the core)

Every rule gives one of three answers:
- an exact type;
- a closed list of types (one row each, per "enumerable is exact");
- unknown, with one general reason and a detail.

Never a guess. The rules run in this order, and each is used only where the earlier ones gave no
answer:

1. **Written types and library type files.** Annotations in the project, then `.pyi` files and inline
   types of installed libraries, then the pinned `typeshed`. This covers `typing` forms: `Optional`,
   unions, generics, `Annotated`, `TypeVar`, `Protocol`, and `Self`. A union in a written type is a
   closed list.
2. **Return types from the function body.** With no written return type, the types of its `return`
   lines are read and combined, repeated through calls. A recursion cycle is `cycle`. Generators,
   `async def` and `await` are read as Python defines them.
3. **Parameter types from every caller.** If a parameter has no written type, it takes the types
   passed at every call in the project. One type gives an exact answer. Several types give a closed
   list. A function called from outside the project, or passed as a value, gives `external` or
   `escapes`, as the value walk answers today.
4. **Field types from every write.** `self.x = ...` in any method of the class, plus class-level
   assignments and dataclass/Pydantic fields, give the field's type, with the same three answers.

Shipped later, with Flask and Django:

5. **Framework rules in catalogs.** Runtime behavior with no static form: Django managers
   (`Model.objects` → QuerySet of that model), Flask's `request` and `g`. This is catalog data, never
   code (the JVM rule).
6. **Shapes from use.** For a payload with no declared type, the shape comes from both ends: the
   caller's dict literal (`json={"id": ..., "items": [...]}`) and the handler's reads
   (`request.json["id"]`). The row is `partial` and lists the fields seen.

**Python's dynamic features**, decided by the same rule:
- `getattr` with a string that is not a literal, monkey-patching, and `__getattr__` without a type
  file are unknown (`not_readable`), with a detail naming the construct.
- `getattr(obj, "literal")` is read as the attribute.
- Decorators that wrap a function keep the function's identity for routing (the framework sees the
  wrapped function). For type flow, a decorator with a written or library type gives the decorator's
  return type. Without one, the inference passes straight through `functools.wraps`, and anything else
  is unknown.
- `import` inside a function, `importlib.import_module("literal")` and `if TYPE_CHECKING:` imports
  are all read.

**Where it runs (my call):** the Python scanner, because M03 is the only module that knows a language
exists. The scanner writes `call_site` facts whose target is either the resolved function or
unresolved with a reason. The resolver stays language-free. The value walk (addresses and
configuration) runs on these facts.

**Which callers count (my call, the JVM's rule):**
- **The callers that count:** for rule 3, a parameter's callers are the calls in the scanned module
  and its sibling modules, exactly as the JVM value walk crosses to callers today.
- **No caller found:** the answer is `external` (called by something unscanned, such as a framework
  or a test). Python has no enforced `private`, so the JVM's "private and never called means dead"
  test is not applied.
- **A function used as a value** (passed, stored, registered by a decorator) can be called from
  anywhere, so it is `escapes`, unless a framework catalog says who calls it. A FastAPI route
  handler's parameters come from the request (§8c), not from callers.
- **Rule 4:** it counts writes from any code in those modules, `obj.x = ...` from outside the class
  included.

**Calls through a class hierarchy (my call):**
- **Lookup order:** Python's method lookup order (C3 linearization, with multiple parents) is not
  the JVM's lookup. The scanner works it out from the class headers it reads and writes it, in
  order, with each class (an addition to `type_header`, §7). The resolver's dispatch uses a written
  lookup order when one is present, and the JVM rule otherwise.
- **Lookup order with no type known:** a class whose parents are not all read gets the order up to
  the first unread parent, and the lookup stops there with `external`, the same answer the JVM
  gives for an unscanned ancestor.
- **Call kinds:** a call on an object is `virtual`. A plain function call is `static`.
- **Overrides:** a call on `self` may reach an override in a subclass, and the existing
  override search handles it.
- **Disambiguator:** Python has no overloads, so a method's descriptor is `name().` with no
  disambiguator. The plan states how the existing descriptor hashing treats an empty one.

**Control flow (my call, required by the goal):** the value walk decides per path using the fields
`dominator`, `on_every_exit`, `post_dominator`, `reaches_return`, `loop_group`, the value ids and
`merge` arguments. Without them, addresses come out `partial`. "The same as Java and Kotlin"
(ruled) needs them, so the scanner builds a control-flow graph from the syntax tree:
- `if`/`elif`/`else`, `for`/`while` with `else`, `break` and `continue`;
- `try`/`except`/`else`/`finally`, `with`, `return`, `raise`;
- `async`/`await`, `yield`, comprehensions, `match`.

This is a large part of the scanner, and the plan sizes it as its own task.

**Written or inferred (my call):** an inferred type that reaches a fact (a parameter's, a
field's, a shape) is marked as inferred, beside the written ones, the way `nullable_resolution`
already marks nullability. Nothing inferred reads as declared. The truth guard checks the marker on
Python rows.

**Measure, do not promise:** the §2 call table is produced again from the real resolver, before and
after rules 2–4, on Sextant, polar's server, dispatch and mealie.

## 7. Facts (D00) — format additions, need approval

The Python scanner writes the existing fact kinds wherever they fit:
- `document`, `module`, `symbol`, `call_site`, `method_return`, `field_write`, `constant`,
  `config_entry`, `type_header`;
- decorators as `annotation` uses: the decorator's resolved symbol, plus its literal arguments.

Additions the design expects. The plan names exact fields, and each one is approved before it is built:
- **A call whose target is unknown:** `call_site` carries no target, plus `reason` and `detail` from
  the general list.
- **Module-level code:** a module body's assignments and calls. Python keeps routes and configuration
  there (`app = FastAPI()`, `app.include_router(...)`, `urlpatterns = [...]`). A module-level scope
  symbol, for example `app/main/__module__().`, owns these calls.
- **Keyword arguments:** Python calls name their arguments (`requests.post(url, json=...)`), and a
  `call_site` argument needs its keyword.
- **Class lookup order:** each class's method lookup order, written by the scanner (§6).
- **Written or inferred:** a marker on every type that reaches a fact.
- **Default values of parameters:** literal defaults (`def f(timeout=30)`) and FastAPI's
  `Query(...)`/`Depends(...)` defaults.
- `GRAPH_SCHEMA_VERSION` and the facts version are raised as the changes require.

## 8. Boundaries

### 8a. Command-line commands — inbound (new protocol word, needs approval)

- **Protocol `cli`, direction inbound.**
- **`path`:** the command's full path as the user types it, for example `sextant module analyze`. The
  program name comes from `[project.scripts]` (Sextant: `sextant = "sextant.cli.app:cli"`), and the
  group and command names follow it. A program with no entry point uses `.` for the first word.
- **`method`:** NULL.
- **Request shape:** the arguments and options, with names, types (`click.Path`, `int`, choices as a
  closed list), required or not, and flags.
- **`handler`:** the decorated function.

The libraries are catalog data: `click` first, because Sextant uses it. `argparse` and `typer` follow
in the same item if the plan has room; otherwise they are logged. The word is general, so Java's
picocli, Kotlin's Clikt and Go's cobra use it later.

### 8b. Program starts — outbound (new protocol word, needs approval)

- **Protocol `process`, direction outbound.**
- **`path`:** the program name when the code gives it: the first item of the argument list, or a
  constant or configuration value it resolves to. For example `java` or `mvn`, or the path of the
  extractor jar resolved as a value.
- **Shape:** the argument list as written (literal items, plus placeholders for computed ones).
- **Calls covered:** `subprocess.run`, `Popen`, `check_output`, `check_call`, `call`, and
  `os.system`. These are catalog data.

### 8c. FastAPI — inbound

- **Routes:** `@app.get(...)` and the other verbs, `api_route`, `APIRouter`.
- **Prefixes:** `include_router(router, prefix=...)`, followed across modules, with nested routers
  and prefixes joined in order.
- **Path parameters:** read from the path. Query parameters come from the handler's parameters
  (`Query`, plain types).
- **Request body:** a Pydantic model parameter or `Body`. Headers and cookies come from `Header` and
  `Cookie`.
- **`Depends(...)` chains:** followed as calls. A dependency's own parameters (query, header) belong to
  every route that uses it, which is what FastAPI does.
- **Response shape:** `response_model=` when given, otherwise the written return type (FastAPI's own
  rule).
- **WebSocket routes:** the existing `websocket` protocol.
- **Pinned version:** the latest FastAPI release as of the plan, recorded in COVERAGE §3a.

### 8d. `requests` and `httpx` — outbound

- **Calls:** module functions (`requests.get(url)`), `Session`/`Client`/`AsyncClient` methods, and a
  base URL on the client (`httpx.Client(base_url=...)`) joined with each call's path.
- **Verb:** from the method name, or from the string argument of `.request("GET", url)`.
- **Body shape:** `json=` with a Pydantic `.model_dump()` gives the model's shape. A dict literal
  gives rule 6 (later). Anything else is unknown.
- **Address:** a value. The existing value walk follows it to its source.

### 8e. Configuration values (Python)

Reads that feed an address:
- `os.environ[...]`, `os.environ.get(...)`, `os.getenv(...)`;
- `.env` files beside the project file;
- pydantic-settings `BaseSettings` classes (field name to environment name, with `env_prefix` and
  aliases);
- module-level constants.

A value set only by the deployment is `external` with the key as its detail (ruling 2026-10-23,
"deployment decides what it can set"). Django `settings.py` comes with Django.

## 9. Done when

1. **Sextant reads itself:**
   - 9 `cli` rows, each with its options as the request shape and its handler;
   - one `process` row per program start, with the program name where the code gives it.

   Each row is checked by hand against the source and pinned in an end-to-end test.
2. **A FastAPI test project** (`fixtures/orders-fastapi`, our own) covering every point of §8c, §8d
   and §8e. Every row is pinned.
3. **Field pins on real projects:** polar's server, dispatch and mealie. Route counts are checked
   against each project's own OpenAPI output where it publishes one. A sample of outbound rows is
   checked by hand. Added to `scripts/field_check.py`.
4. **The type-rule table:** §2's call table produced by the real resolver, before and after rules 2–4.
5. **Truth:** no `resolved` row carries a guessed type or value. Every unknown has one general reason
   and a detail, and the guard test `tests/application/test_one_reason_list.py` covers the Python
   rows.
6. **Docs:**
   - COVERAGE: the Python rows, §3 language readiness and §3a versions;
   - D00 and D02: the new facts and words;
   - M02 and M03: the detector and scanner.
7. **The full check passes.**

## 10. Left to the plan and the builder

- Exact fact field names (approved before building), and module layout under `ingress/extract/python`
  and `ingress/detect`.
- How rules 2–4 are computed (fixed point over the module, order of passes), within the "exact,
  closed list, or unknown" rule.
- Which `typeshed` commit is pinned.
- Whether `argparse` and `typer` fit in this item.
- The fixture's exact contents.
- Performance: measure reads per resolve on polar's server (2,382 files) before building (GUIDELINES
  §8.7, "optimize early").
