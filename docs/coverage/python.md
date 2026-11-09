# Coverage — Python

**The Python reader's foundation ships, and FastAPI inbound is read.** The foundation was built
by OI-208 plan 1 (`docs/superpowers/plans/2026-11-06-python-reader-foundation.md`, spec
`docs/superpowers/specs/2026-11-06-python-reader-design.md`) and proved on Sextant's own code
(`tests/e2e/test_sextant_reads_itself.py`). FastAPI inbound was built by plan 2
(`docs/superpowers/plans/2026-11-08-python-fastapi-inbound.md`) and proved against FastAPI's own
route table (`tests/e2e/test_orders_fastapi.py`). Outbound HTTP clients are next (plan 3), then
Flask, then Django (ruled 2026-10-26). Detection shapes are defined in [COVERAGE.md](../COVERAGE.md) §1. The typing
problem this language creates is analysed in [COVERAGE.md](../COVERAGE.md) §10.

> **Scope.** [COVERAGE.md](../COVERAGE.md) §5 is canonical for tier and status,
> organised by protocol. The FastAPI REST-inbound row ships; every other Python cell there is
> still a plan. This file holds what does not fit a protocol row: what the reader reads, what it
> does not, the toolchain verdict, the payload story, and the structural oddities of the
> language.

---

## What is read today

Python is read with the JVM's pipeline. A new scanner writes the existing facts, and every step
after the facts is the existing one, extended where Python needs it.

- **Modules** (M02). A new detector reads `pyproject.toml` (`[project]`, Poetry's table,
  `[build-system]`, `[tool.uv.workspace]` members, `[project.scripts]`), `setup.cfg`
  `[metadata]` and `console_scripts`, and `requirements*.txt` or `Pipfile` for a service with
  nothing else. A uv workspace root with no code of its own is not a module. A `setup.py`
  inside a package is not a module. When it looks for modules it skips folders that a
  `.gitignore` in the repository or `.sextantignore` names, and it does not enter a folder that
  holds `.git` (a folder for a clone or submodule, a file for a git worktree:
  `is_other_repository`), noting it as another repository. So a nested checkout such as
  `.claude/worktrees/*` is not a second module (pinned by
  `tests/ingress/test_python_detector.py::test_a_folder_holding_git_is_another_repository_and_is_not_entered`). A repository read by several detectors (a Maven project with a Python
  tool beside it) keeps every module found.
- **Each file** (M03), one at a time, with the standard library's `ast`. A module is a type
  (`app/api/items#`), its body is that type's `<clinit>`, classes are types and functions are
  methods. Every call is a `call_site` with its receiver, result, arguments (keyword
  arguments by name, `*` and `**` marked) and its place in the body's control flow. Returns,
  including the implicit `return None`, are `method_return` facts. Module-level names and
  `self.x = …` are `field_write` facts. A decorated `def` holds its decorators' result, and a
  decorator is the call it is (`@router.get("/x")` is `router.get("/x")(f)`), never an
  annotation.
- **Types written in the code:** annotations, `Optional`, unions, `type[X]`, `@overload` chosen
  by argument types (a closed list where they cannot be told apart), PEP 695 type parameters,
  and the library signatures of the installed environment (`.venv`, `venv`, or the one uv or
  Poetry names) and of typeshed, pinned at commit `13ffe24f`. A type variable in a library
  return takes the type the receiver's type arguments, the class's written bases or the
  arguments fill it with (`list[User].pop()` is a `User`, `dict[str, Client].get(k)` a
  `Client`, `class Users(list[User])` a list of users, `-> Self` the receiver's own class;
  OI-324). `for x in xs` is written as the `__iter__` and `__next__` calls it is, as javac
  writes `iterator()` and `next()`, so `x` has the element type; comprehensions and `async
  for` too, and `for k, v in d.items()` takes the `tuple[K, V]` apart. `xs[i]` is the call
  `xs.__getitem__(i)`, and a slice keeps the list's, `str`'s or tuple's own type. Library classes are
  `type_header` facts, hierarchy only. A call into a library stays `external`; library bodies
  are read only under the existing `extract_libraries` opt-in.
- **Receiver binding** (M04). A call whose owner one file cannot know is bound by the value
  walk, from what produced the receiver: a constructor, a callee's returns, a parameter's
  callers, a field's writes. One row per path, never combined (ruling M-1). Lookup through
  class parents follows C3, the module fact naming the rule (`lookup: c3`).
- **Commands.** `catalogs/click.yml` makes each click command an `entry_point` root, its path
  the command words (`sextant module analyze`), and each `click.argument` and `click.option`
  a `request_params` row (`argument`, `option` or `flag`). A trace starts at each command.
- **FastAPI routes** (`catalogs/fastapi.yml`, plan 2). Every rule is FastAPI's own, quoted with
  source lines in `scripts/probes/fastapi_rules.md` and measured on FastAPI 0.115.12 and 0.162.0.
  - A route is the decorator call it is (`@router.get("/x")`), or `add_api_route` and
    `api_route`. Each verb is one row; `methods=None` is `GET`.
  - The path is kept as written and joined to its prefixes by plain concatenation, as FastAPI
    joins them: the router's own `prefix`, each `include_router` prefix, and each sub-application
    `mount`. A router subclass that passes its prefix to `super().__init__` holds it. A router
    that a factory builds per caller gets each caller's prefix and verbs.
  - The handler is the decorated function, or the bound method or function given to
    `add_api_route`.
  - The response is `response_model=` where it is written, else the return annotation. A
    generic model (`ListResource[X]`, `list[X]`) is read as the type it names. `-> None` and a
    `Response` subclass give no response model.
  - Shapes FastAPI refuses at start-up (`methods=[]`, an empty prefix and path, a prefix that
    does not start with `/` or ends with `/`) give no row and say why. No more such shapes are
    detected: code that does not start is not Sextant's concern (ruled 2026-11-08).
  - A route, include or mount registered only under a test Sextant does not decide
    (`if settings.DEBUG:`, `if not os.path.exists(...): return`, in its own body or in every
    caller of the function that makes it) keeps its row, and `endpoint_existence` says it
    exists "not evaluated", naming each test as the code writes it (OI-368, ruling of
    2026-10-23: a deployment decides such a test). A constant test and `TYPE_CHECKING` are
    decided. A `sys.version_info` test in the module's own code is not: the deployment picks
    the interpreter. An arm that always raises guards nothing (`if bad: raise ...` decides only
    whether the app starts), and neither does `if __name__ == "__main__":`, an entry point. A
    helper called once under a test and once not gives each row the test of the call it was
    derived through (the call that gave its router, route, path or prefix); a row it cannot
    tie to one call is "not evaluated", never served on the strength of another call. Measured: polar's 192 `/backoffice` rows, mealie's 3
    single-page-app routes and one unread dynamic route; no other row moved.
- **Request parameters and bodies.** `Query`, `Header`, `Cookie` (the functions and the
  `fastapi.params` classes), in a default or in `Annotated`, give `endpoint_metadata` rows with
  the wire name (an `alias`, or the header's spelling with `-`), and `required` or `optional`
  as FastAPI decides it. An unmarked scalar is a query parameter; a path variable is part of the
  path, not a row. A pydantic model parameter is the body; several body parameters, or
  `Body(embed=True)`, or one non-model `Form`/`File` parameter, make an embedded body with one
  field per parameter. A class-typed `Query()` parameter (a query model) gives one row per
  field.
- **Dependencies** (`Depends`, `Security`). A parameter filled by a recipe takes the recipe's
  return (a generator's first `yield`), as one more path beside its in-module callers. A
  recipe's own query, header and cookie parameters join the route's. Route, router, include and
  app `dependencies=` lists join the routes they reach; a mounted sub-application does not take
  its parent's. Each recipe FastAPI runs for a route is a `roots` row at the route's address.
- **pydantic shapes** (`catalogs/shape-models/pydantic.yml`). The wire name comes from
  `serialization_alias`, `alias` or `validation_alias`, else the model's `alias_generator`
  (configuration merged over the written bases as pydantic merges it), else the field name. A
  field whose accepted input names differ from its output name is `partial` (one shape for both
  directions). `required` follows pydantic: a field with no default is required; an unreadable
  default is NULL (unknown). `exclude=True` drops a field from a shape only responses reach.
  `@computed_field` adds an output field. Library base classes' fields are read from their
  headers, so a shape is closed where every field is read; `extra="allow"`, a custom
  serializer hook or an unread base keeps it open.

## Measured

On the development Mac, Python 3.14.10. Full figures and commands:
`docs/research/2026-11-06-python-performance.md`.

| | Sextant | polar `server/` |
|---|---|---|
| Files read | 171 | 2,053 (no installed environment: typeshed only) |
| Call sites | 23,482 | 129,009 |
| Owner written by the scanner | 82.7% | 61.4% |
| Owner bound by the resolver (`resolved`, `narrowed`, `partial`) | 126 (0.5%) | 9,712 (7.5%) |
| A call of a function value, whose edge enters that function's body (ruling R29) | 34 (0.1%) | 304 (0.2%) |
| Unresolved, with a reason from the one reason list (several reasons, one per path, on 104 / 172 of them) | 3,893 (16.6%) | 39,774 (30.8%) |
| **No owner and no reason** | **0** | **0** |
| Cold analysis (target 60 s, ceiling 300 s) | 9.9 s | 29.2 s |
| Warm analysis, no file changed (target 10 s, ceiling 30 s) | 3.9 s | 3.0 s |
| Warm analysis, one file edited | 5.8 s | 16.1 s |

- **The table is plan 1's.** Since OI-324's first part writes `for` loops and subscripts as
  the `__iter__`, `__next__` and `__getitem__` calls they are, both trees have more call sites
  (Sextant 35,653, polar 146,852) and longer cold runs (12.1 s, 32.0 s); polar's warm run on a
  branch without reuse is 31.9 s, over the 30 s ceiling. The figures are in the performance
  file.
- **Sextant's six commands** are six `entry_point` roots with traces, and their 24 parameters
  (7 arguments, 13 options, 4 flags) are `request_params` rows. Both lists were read by hand
  from `src/sextant/cli/app.py` and are pinned by the test.
- **dispatch** (`examples/py-dispatch`, a reviewer probe in task 9b): 27 roots, 56 parameters.
- **polar:** 31,770 call edges enter a function body.
- **A re-run reads only what changed** (OI-325, D01 §7 "Reuse"): each unchanged file's facts
  are kept, and with no fact changed the resolve is kept too. One edited file still pays the
  whole resolve (13 s on polar), which only an incremental resolve would shorten. The scan is
  not run in parallel, which spec §5 also planned; it would shorten the cold run. The
  performance file has the measurements.

### FastAPI (plan 2)

Measured on 2026-11-09 at the end of plan 2, on the development Mac (Python 3.14.10). FastAPI's
own route table is printed by `tests/e2e/fastapi_oracle.py`, run in each service's own
environment: it imports the app and asks FastAPI. Sextant never runs the code it reads.

| | `fixtures/orders-fastapi` | polar `server/` | mealie |
|---|---|---|---|
| FastAPI routes (method, path pairs) | 13 (14) | 625 (671) | 289 (289) |
| Sextant FastAPI rows | 14 | 720 | 293 |
| Pairs FastAPI serves that Sextant finds | 14 of 14 | 668 of 671 | 289 of 289 |
| Rows `resolved` / `partial` / `unresolved` | 14 / 0 / 0 | 614 / 61 / 45 | 245 / 47 / 1 |
| Cold analysis (target 60 s, ceiling 300 s) | 2.4 s | 53.5 s | 15.2 s |
| Warm analysis, no file changed (target 10 s) | | 2.2 s | 1.3 s |

- **The fixture equals FastAPI.** `tests/e2e/test_orders_fastapi.py` compares each route's
  method, path, handler and response model, its parameters (kind, wire name, required), its
  body, and the recipes FastAPI runs for it, with FastAPI's answer. The wire names and required
  fields of `OrderIn` (as a request reads it) and `OrderOut` (as a response writes it) equal
  pydantic's own JSON schema. Every row Sextant writes for the fixture is pinned: an extra row
  fails.
- **polar.** The 3 pairs not found are the versioned `GET /2026-04/openapi.json`,
  `/2026-10/openapi.json` and `/2027-01/openapi.json`, which Sextant gives as one `partial` row,
  `/{}/openapi.json`. 30 rows are apps written inside `tests/`, which FastAPI's table for
  `polar.app` does not hold. 1 row is the checkout-link app that polar serves only through
  `app.host(...)`, published at `/{client_secret}` with no host and as existing wherever the
  module runs: `app.host` is not read as a mount yet, so the test it is under
  (`if settings.CHECKOUT_LINK_HOST is not None:`) does not reach the route (OI-368's second
  half).
- **mealie.** The 3 rows FastAPI does not serve are the single-page-app routes, registered only
  when `settings.PRODUCTION and not settings.TESTING` and the static-files directory exists
  (`mealie/app.py`, `routes/spa/__init__.py`). The oracle ran with `PRODUCTION=true` and no
  static files, so FastAPI returned before registering them. Sextant publishes all three as
  existing "not evaluated" under both tests.
- **dispatch** (`examples/py-dispatch`) was not measured: it has no installed environment.

## What is not read, and why

Every item is recorded in the plan's ledger (`.superpowers/sdd/2026-11-06-python-reader-foundation/progress.md`)
or a task report, with its ruling where one was made. "Unknown" below always means a reason
from the one reason list, never a guessed value.

**Types the reader does not work out.** Measured on Sextant at plan 1's end: 2,541 of its
2,996 `not_readable` sites called a `dict`, `list`, `str`, `set` or `tuple` method. The
type-variable rule and iteration (OI-324, first part) type 254 of the 2,558 such sites on
`main` at e45b88fe. Its second part (declared returns, container literals, class-body
attribute declarations, `isinstance` narrowing, generic parents across files) and its first
review round (`Self`, the headers of imported module files, re-exports followed) type 1,321 of
them (1,229 by the scanner, 92 by the resolver), and 683 of polar's 2,261 (581 and 102); the
rest are the shapes below. Figures and commands:
`docs/research/2026-11-06-python-performance.md`.

| Shape | What happens | Why |
|---|---|---|
| an element of a container whose type is not written: a bare `list`, `list[Any]`, a parameter with no annotation | `not_readable`, or `external` where the container is a library call's result | nothing fills the type variable, and nothing is guessed |
| what a local container literal holds after its first read (`found = []; found.append(u); found[0].save()`) | `found.append` is a `list`'s; `found[0].save()` stays unowned | the code the list was handed to may have written to it; writes are not followed (OI-324 part 2, option b): following them is exact only where the list is never handed out, aliased or captured |
| an element of what a method reached through a value the resolver binds declares it returns (`for row in self.workspace.query(...)` with `workspace` untyped) | the call on the result binds the declared class; `__iter__` and the element stay unowned | the resolver has no library signatures (ruling A); where the scanner can name the callee (a module function or a typed receiver, in this file or another), it types the element from the other file's header |
| a union receiver whose members give different element types (`list[A] \| list[B]`), and any union a value that is not a parameter holds (`[u, c][0]`, `isinstance(x, (A, B))`) | the call on it has no owner and no rows | no fact names the closed list of a value that is not a parameter: one row per member needs a field (measured: 4 + 15 Sextant sites, 6 + 16 polar; not built, a question for the user) |
| a tuple of unknown arity (`tuple[A, ...]`), or a starred target | the names stay untyped | the arity is not written |
| a subscript of a class another file defines (`make(Page[User])`, `R = Repo[User]`) | a `__getitem__` call site, answered `not_readable` ("a type form") on each path whose receiver is the class itself; no edge to the class's own `__getitem__` | ruling R37: subscripting a class object is `__class_getitem__`; this file cannot see the name is a class, the resolver can |
| a class of another file as the receiver (`r: Repo[Order]`, `Repo` imported) | its declared returns are filled through the subclass's written parents (`ProductRepository(RepositoryBase[Product])`); its library-inherited methods are not typed, and a type argument written at the use (`Repo[Order]`) fills nothing | the resolver reads no library signatures and holds no type arguments for a value |
| `obj.client` where `obj`'s type is not written (`def f(obj): obj.client.get()`) | unowned | no fact names an attribute read on a value other than `self` (R24's shape for writes); a typed `obj` of any module file's class is typed, through that file's header |
| a type name another file binds by a star import (`from .x import *`) | the path is kept as written (polar: 10 sites, one owner) | a header's star imports are not followed |
| a written attribute type that is a library class (`client: httpx.AsyncClient`) read on `self` by the resolver | not bound from the declaration (the scanner still types what is read off it) | a library class's methods are not read in the resolver, so it cannot tell a descriptor (`Mapped[T]`, whose read gives a `T`) from a plain class |
| a parameter written `AsyncSession` whose callers pass a value from a library this environment does not hold (polar's 351 `self.session` reads) | unbound: `escapes`, `external`, `non_enumerable`, `not_readable` per path | callers answer first (round 2); the written type stands beside every caller path with no value (round 3, R40), but a library type the environment does not hold names no class the workspace knows, so it adds nothing |
| a body whose returns or writes give a different class than the declaration, in the scanner | the scanner types elements from the declaration | logged (round 1 item 5): the resolver reads the body first; the scanner would need a second reading of the file |
| `assert isinstance(x, C)`, or `isinstance` on an attribute (`self.x`) | not narrowed | `python -O` drops an assert; only a local name is narrowed |
| an attribute of a library module: `pytest.mark`, `alembic.op` | `no_writer` (12,683 polar rows) | a library field has no writer in the scanned code, as the JVM answers `System.out` (ruling R26, logged) |
| a library that is not installed | `external`, and the report says so | library symbols come only from the scanned environment; nothing is downloaded (spec §3e) |
| a file written for a newer Python than the one running Sextant | the file is uncovered, naming the version that read it | the grammar is the running Python's (ruled 2026-11-06: run Sextant on the newest Python) |
| names a `sys.path` change makes visible | `external` | `sys.path` changes are not followed (spec §3e) |
| a name whose defining distribution is not installed, though another installed one re-exports it | keeps the import path, with an uncovered note | Task 7 fix round 1, accepted: no fact field names the missing definer |
| a re-export cycle between library modules | keeps the written name | Task 7 fix round 1, accepted |
| a type written in the code | `evidence: declared` on the document only, not per symbol | Task 4, deferred |
| a class base that is a name the file does not bind | `parents_unread` with `external`, the detail "a name this file does not bind"; a base imported from a library is written as a class, so `external` fires only for unbound names | Task 5b fix round 1, parked |

The comparison with a type checker, which solves the first four exactly, is
`docs/research/2026-11-06-python-type-tools.md`.

**Values and bodies:**

| Shape | What happens | Ruling or record |
|---|---|---|
| `obj.x = v` on another object (`app.state.x = v`) | not written | R24: only `self` field writes are facts, as on the JVM; reads of the field keep the class's own value (OI-340) |
| a module-level `for`, `with … as` or `except … as` target | not a write, so a function reading the name gets the earlier value, marked `resolved` | final review, logged as OI-339 (rare; the fix is cheap) |
| a nested `def` reading a name of its enclosing function (a closure) | the trace stops at the wrapper's `fn(*a)` | R30: logged, kept as a strict xfail |
| a class whose parent cannot be named | parents kept up to that one, then `parents_unread`; lookup ends `external` | R11, R11b; mixins after it are not found |
| 13 standard-library classes (typing's `Protocol`, `Generic`; `IntEnum`) | no type header | R23: typeshed declares them as values |
| the value after a `with` that swallows, around a body that always returns | the implicit `None` is missing | R18, parked |
| `break` or `continue` after a `finally` | unresolved where the `finally` value is exact | Task 6, parked |
| an unreachable call | written, with no dominator and both flow flags false | R15: never a wrong true |
| a call inside a `with` block | never `on_every_exit`; the call after is dominated by `__enter__` only | R16 |
| a parameter's default value | a fact since plan 2 (`Parameter.default`, `annotation_value`) | plan 2 task 2 |
| a function-level `try` import binding a class on each branch | the last binding is taken | Task 5, deferred |
| two import roots holding one relative path | one file's facts overwrite the other's | Task 4, deferred |
| `@x.setter`, `@x.deleter` | the setter's receiver is not tied to `x`; the deleter reads as a second body | Task 4, deferred |
| the value of `f()` through a `result_calls` wrapper (`lru_cache`) | the library's, not `f`'s return (15 polar edges) | Task 9b, logged |
| a decorator built once and reused (`deco = click.option(...)`, then `@deco`) | not followed | Task 9b: `result_returns` reads the same method only |
| a decorator factory no value model states (`lru_cache(maxsize)`, `retry(...)`) | unstated | Task 9b, logged |
| `self.m()` or `C.m()` on a decorated method | still names the method, not the decorator's result; the `external` detail does not name the decorator there | Task 9a, parked for 9b; 9b named the decorator on `__call__` sites only |
| a classmethod (written `static: true`, R28) | `exact_methods` (`shapes/pass_through.py:478`) treats it as never overridden, though `cls` can reach an override | Task 8 re-review round 3, parked: **must be fixed before a Python catalog reads pass-through** |
| a closed list (a name bound on several branches) reached through a dotted head (`a.b.c`) | loses its field | Task 5, deferred |
| a name rebound through `globals()` or `setattr` | not followed | Task 9a, parked (contrived) |
| calling a wrapper a library types (`_lru_cache_wrapper`) | two edges: the library's `__call__` and the wrapped function | Task 9b concern 4, accepted: both run |
| a wrapped handler's own parameters (`__wrapped__`; CTFd has 56 such routes) | not read | Task 9b §9, plan 2 |

**Commands:**

| Shape | What happens | Record |
|---|---|---|
| typer, `argparse`, an entry point naming a function that calls a group | not read (mealie, netbox, httpie) | Task 9b, logged |
| a group's own options and callback; `invoke_without_command=True` | not read | Task 9b, logged |
| `--shout/--no-shout`; a parameter's type; `password_option`, `version_option` | not flags; no column; no row | Task 9b, logged |
| `@click.group` or `@cli.command` with no parentheses | not read | Task 9b, logged (none in the corpus) |
| a command behind a library decorator no value model states (`pass_context`) | a root row with no handler, and no reason column to say why | Task 9b: `roots` has no reason column |
| a command no entry point names | its path is `<program>`: the outermost word is the program's name, and no entry point gives it | design `2026-11-06-reading-decorators-design.md` §5 (`path_fallback`, program name); Task 9b concern 6 |
| a command named from its function (`path_fallback`) whose handler is unread | the row's path is NULL: the name would be the wrapper's | Task 9b fix round 1, logged |
| a group whose class comes from a library that is not installed (redash's flask `AppGroup`) | 0 roots: nothing has an owner | Task 9b fix round 1 (reviewer probe); follows the not-installed rule |
| an `optional_when` whose value is not a literal | `requirement` NULL | Task 9b fix round 2, accepted: the column's words are `required` and `optional` only |
| a keyword argument reference (`{keyword: name}`) in a catalog | read on `fluent` captures, `mount`, `request_params` and `single_call`; every other style's `*_arg` takes a position | Task 9b deviation 1 and fix round 1 |
| a keyword-form capture under `--shadow` | not seen by the shadow ask reader | Task 9b §9 item 11, logged |
| a group made by a class constructor | not tied to its entry-point name | Task 9b re-review, logged |
| a program started by the code (`subprocess`, `java -jar`) | not recorded | OI-323 |

**FastAPI and pydantic** (each an open issue in Plane; the full list is OI-347 to OI-409 in
`docs/open-issues.md`):

| Shape | What happens | Record |
|---|---|---|
| `app.host(host, app)` | not read as a mount: the app's routes are published with no host, and a test the host call is under does not reach them | OI-368 (second half) |
| a type written as text (`"Annotated[int, Field(alias='S')]"`, a quoted alias) | not read: the name, the body or the marker is lost | OI-348 |
| a dependency's own body parameters | no request body | OI-378 |
| a `@dataclass` or library class as a recipe; a bound method or staticmethod recipe | no parameters and no root; `not_readable` | OI-379, OI-380 |
| `response_model=Out` written as a keyword | the descriptor says `nullable: true` (the JVM class-literal rule) | OI-362 |
| `response_model=List[X]` (`typing.List`, `Dict`) | `unresolved` | OI-395 |
| `-> Iterator[X]` on a function that is not a generator | no response | OI-361 |
| `APIRouter.mount`; a decorator alias on two paths | not read | OI-369, OI-364 |
| a subclass of `params.Query` or of `Request`; a parameter typed `object` | not a marker; a body | OI-374, OI-371, OI-375 |
| shapes FastAPI refuses or accepts only at start-up | not all mirrored (ruled: no more are added) | OI-370, OI-367 |
| `class Config:` (pydantic 1 style); `validate_by_alias=False`; `response_model_by_alias=False` | not read | OI-388, OI-389 |
| `create_model(...)` as a base; a pydantic dataclass's `config=`; `RootModel` redeclaring `root` | a closed shape that is wrong | OI-401, OI-402, OI-406 |
| `Field(exclude_if=...)` on a plain field; `@field_serializer` | required; the annotation's type | OI-403, OI-346 |
| `UploadFile` | its header attributes as fields | OI-407 |
| a field default made through `*args`, or by a library helper | `required` NULL | OI-396, OI-408 |
| a recipe path over `PATH_CAP` | `non_enumerable` (10 polar sites) | OI-377 |

**Finding modules:**

| Shape | What happens | Record |
|---|---|---|
| a JVM repository with an incidental Python project | becomes multi-module, so `--workspace` is refused | R7 |
| a `tests/` folder with its own `requirements.txt` inside a `pyproject` module | its own module | Task 2, deferred |
| `.egg-info`, a Windows `Lib/site-packages` | not read | Task 2, deferred |
| a Poetry checkout with no installed environment | a note on every run | Task 2, deferred |
| two modules with one id in one repository (polar's two `polar-sdk`) | both kept, each id followed by `@<folder>` | R6 |
| an unreadable root `pyproject.toml` in a JVM repository | the whole analysis is refused, loudly | R8b: only "no module found" is passed over |
| a detector that reports an empty module list | dropped without a note | Task 3, deferred |
| a `pyproject.toml` with only `[build-system]` | no module, and no note saying why | Task 2, deferred |
| the own-code check, in one order of nested files | an edge case can take the wrong order (`detect/python.py`) | Task 2, deferred |
| a `.gitignore` that cannot be read | detection stops with `OSError` | Task 4, deferred |
| a module's own git-ignored files (generated code) | read by the scanner; git-ignored folders are skipped only when looking for modules | R9 |
| a folder named `site-packages` or `.mypy_cache` that is not an environment | read: only a folder holding `pyvenv.cfg` is an environment | Task 4, deferred |
| an opted-in library sharing a `pypi` folder name with a Maven group | its fact folder can collide | Task 7, logged (real input cannot trigger it) |
| a `RECORD` path written with a backslash | not refused | Task 7, parked (harmless off Windows) |

**Out of this essay's scope**, though in the ledger: items that change no answer a user reads.
These are stale docstrings and error texts (Task 1), test hygiene (Task 2's Poetry cache
tests, Task 3's failure-test order), Task 0's measurement notes, a redundant assignment
(Task 2), a guard test's blind spots (Tasks 9a and R31), the walk's `_copy` cost (Task 6, not
measurable), the order of two honest reasons in receiver binding (Task 8), and the JVM-only
`requireNonNull` entry (Task 9b). `control_flow` is not declared as a capability (R14): the
flow fields are written, as on the JVM, which does not declare it either.

---

## Toolchain — why our own reader

| Route | Gives | Why not, or why |
|---|---|---|
| **`ast` (stdlib) + typeshed + the installed environment** | Syntax, decorators, literals, written types, library signatures | **Built.** Reads one file at a time and writes the existing facts, runs nothing and downloads nothing. Substitutes generics within a file and through a subclass's written parents, and reads `isinstance` on locals (above). |
| `mypy` in-process | Declared and inferred types, overloads, generics | Its documented API returns report text only, and its plugin system is "experimental" (mypy's documents); a project's mypy plugins would run the scanned environment's code. Measured: 2.7 s cold on Sextant, 4.8 s on polar's package without libraries. A candidate for the four shapes above. |
| `pyright` | Best inference available | Runs on Node.js (the PyPI wrapper downloads Node at run time when none is installed); used as a language server answering per position. That it has no programmatic API is not checked |
| Pyrefly, ty | Fast inference (ty: "written in Rust") | Language servers as well, each one more package to ship; neither states a release status on its front page |
| `PyCG` | Call graph | Named in the literature as the reference Python call-graph tool (see §10) |

There is no artifact equivalent to a `.class` file. `.pyc` bytecode exists but is *less*
informative than the source, and it is tied to one interpreter version. **For Python we read
source.** The full comparison, with what was measured and what comes from the tools' documents,
is `docs/research/2026-11-06-python-type-tools.md`.

---

**The sections below are the inventory the framework plans start from.** Only FastAPI and
Pydantic are read today (above); the other rows say what each framework and library writes, and
how hard it is to read.

## Inbound HTTP

| Framework | Shape | Detection | Types available? |
|---|---|---|---|
| **FastAPI** | `@app.get("/items/{id}")` on a function whose parameters and return are annotated; `response_model=` | `annotation` | **Yes, reliably** — FastAPI *cannot function* without them. It builds validation and OpenAPI from the annotations. |
| **Litestar** | `@get("/items/{id:int}")`, typed handlers | `annotation` | Yes, same reason |
| Flask | `@app.route("/items", methods=["GET"])`, or `@app.get(...)` | `annotation` | **No.** Body reached via `request.json[...]`, `request.form[...]` — untyped `dict` access |
| Flask blueprints | `bp = Blueprint(...)`; `app.register_blueprint(bp, url_prefix="/api")` | `annotation` + `registration_call` | Prefix is joined at registration, in another module |
| **Django** | `urlpatterns = [path("items/<int:id>/", views.item)]` in `urls.py`, nested with `include()` | `registration_call` | **The path and the view are in different files**, joined by a list of call results, often nested several levels. No annotation exists on the view at all. |
| **Django REST Framework** | `router.register(r"users", UserViewSet)` | `runtime_dynamic` | **One line produces six or more endpoints** by convention (`list`, `create`, `retrieve`, `update`, `partial_update`, `destroy`), with paths and verbs generated at runtime from the ViewSet's class hierarchy and `@action` decorators. Nothing in the source states them. |
| aiohttp | `app.router.add_get("/items", handler)` | `registration_call` | No |
| Starlette | `Route("/items", endpoint, methods=["GET"])` in a list | `registration_call` | No |
| Sanic / Tornado / Bottle | decorator or handler-class based | `annotation` / class convention | No |
| `drf-spectacular`, `flask-smorest` | emit OpenAPI | — | **If present, read the OpenAPI instead.** Cheapest correct answer for DRF and Flask. |

**Django and DRF are the structural problem.** Every other framework in this table puts the path next to the handler. Django puts it in a separate routing module; DRF puts it nowhere.

---

## Outbound HTTP

| Library | Shape | Detection |
|---|---|---|
| `requests` | `requests.get(url)`, `session.post(url, json=…)` | `registration_call` — the verb is the function name, the URL the first argument. The easiest outbound form in any language. |
| `httpx` | same shape, sync and async | `registration_call` |
| `aiohttp` | `session.get(url)` inside `async with` | `registration_call` |
| `urllib3` | `http.request("GET", url)` | `registration_call` — verb is a string argument |

---

## Messaging and RPC

| Protocol | Library | Shape | Detection |
|---|---|---|---|
| Kafka | `confluent-kafka-python` | `c.subscribe(["topic"])`, `p.produce("topic", value)` | `registration_call` |
| Kafka | `kafka-python`, `aiokafka` | `KafkaConsumer("topic", …)` — **topic is a constructor argument** | `registration_call` |
| Kafka | `faust-streaming` | `app.topic("orders")` + `@app.agent(topic)` | `annotation` + `registration_call` |
| **SQS** | **`boto3`** | `boto3.client("sqs").send_message(QueueUrl=…, …)` | **`runtime_dynamic` — see below** |
| Pub/Sub | `google-cloud-pubsub` | `publisher.publish(topic_path, data)`; `subscriber.subscribe(sub_path, callback)`; paths built by `publisher.topic_path(project, topic)` | `fluent_chain` — the topic is assembled from a helper call |
| gRPC | `grpcio` | generated `_pb2_grpc.py`: `class FooServicer`, `add_FooServicer_to_server(impl, server)`, `FooStub(channel)` | `registration_call` |
| Protobuf | `protobuf` | generated `_pb2.py` embeds the serialized `FileDescriptorProto`; `DESCRIPTOR` is importable | `generated_descriptor` |
| Celery | `celery` | `@app.task` and `task.delay(...)` / `.apply_async(queue=…)` | `annotation` — a genuine async boundary that is *not* a protocol, and is easy to miss |
| AMQP | `pika`, `kombu` | `channel.basic_publish(exchange, routing_key, …)` | `registration_call` |

### boto3 is a special problem, and it is worth stating plainly

`boto3` builds its clients **at runtime** from JSON service descriptions shipped inside `botocore`. `client.send_message` is not defined anywhere in any Python file — it is synthesised by `__getattr__`. So:

- No AST reader will ever see the method.
- No type checker resolves it either, except through the separately maintained `boto3-stubs` / `mypy_boto3_*` stub packages ⚠️.
- The only static signal is the **service string**: `boto3.client("sqs")`.

That means AWS usage in Python must be detected as *"this variable came from `boto3.client("sqs")`, and this method name on it looks like an SQS operation"* — a name-match, `evidence: name_match`, and honestly `resolution: narrowed` at best. Compare the AWS SDK for JavaScript v3, which uses explicit `SendMessageCommand` classes and is statically visible.

---

## Payloads

Ranked by how much we can recover:

| Style | Recoverable | Note |
|---|---|---|
| **Pydantic** (`class Order(BaseModel)`) | **Fully** | Fields, types, defaults, `Optional`, aliases via `Field(alias=…)`. As good as a Java DTO. Used by FastAPI and Litestar, so the *modern* frameworks come with typed payloads attached. **Read since plan 2** (`shape-models/pydantic.yml`, above). |
| `dataclasses`, `attrs`, `TypedDict`, `msgspec` | Fully | Declared fields with annotations |
| `marshmallow` schemas | Fully | `fields.Str(required=True)` — declarative, and carries `required` explicitly |
| Django / DRF serializers | Mostly | Declarative fields; `ModelSerializer` derives them from the model, so the model must be read too |
| Annotated function signatures | Partly | Median annotation coverage across real libraries is low — see [COVERAGE.md](../COVERAGE.md) §10 |
| **Raw `dict`** | **Not statically** | `request.json["customer"]["id"]` — the shape exists only as a set of subscript expressions scattered through the handler. This is the case the LLM overlay is for. |

---

## Verdict

Python splits cleanly in two, and the split is by framework age rather than by anything about the language:

- **FastAPI / Litestar / Pydantic** — types are mandatory for the framework to work, so they are present and trustworthy. Coverage here can be nearly as good as Java's.
- **Flask / Django / bare `dict`** — the wire shape is never declared and must be inferred from field accesses.

Implement the first, and be explicit in the output that the second is `resolution: partial`. Do not average the two into a single quality claim.
