# Coverage — Python

**The Python reader's foundation ships; no web framework is read yet.** Built by OI-208 plan 1
(`docs/superpowers/plans/2026-11-06-python-reader-foundation.md`, spec
`docs/superpowers/specs/2026-11-06-python-reader-design.md`), and proved on Sextant's own code
(`tests/e2e/test_sextant_reads_itself.py`). FastAPI is next, then Flask, then Django (ruled
2026-10-26). Detection shapes are defined in [COVERAGE.md](../COVERAGE.md) §1. The typing
problem this language creates is analysed in [COVERAGE.md](../COVERAGE.md) §10.

> **Scope.** [COVERAGE.md](../COVERAGE.md) §5 is canonical for tier and status,
> organised by protocol. No Python protocol row ships yet, so every Python cell there is still
> a plan. This file holds what does not fit a protocol row: what the reader reads, what it
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
| Cold analysis (target 60 s, ceiling 300 s) | 8.7 s | 27.2 s |
| Warm analysis, no file changed (target 10 s, ceiling 30 s) | 8.8 s | 27.6 s: **target missed** |

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
- **Warm is as slow as cold** because nothing is reused: the scan is not cached by content
  hash and not run in parallel, although spec §5 planned both. Reaching 10 s needs the scan
  reused for unchanged files and the resolve skipped for an unchanged fact set; the
  performance file has the arithmetic.

## What is not read, and why

Every item is recorded in the plan's ledger (`.superpowers/sdd/2026-11-06-python-reader-foundation/progress.md`)
or a task report, with its ruling where one was made. "Unknown" below always means a reason
from the one reason list, never a guessed value.

**Types the reader does not work out.** Measured on Sextant at plan 1's end: 2,541 of its
2,996 `not_readable` sites called a `dict`, `list`, `str`, `set` or `tuple` method. The
type-variable rule and iteration (OI-324, first part) type 254 of the 2,558 such sites on
`main` at e45b88fe, and move 250 more to `external` (their receiver is now a library call's
result); the rest are the shapes below. Figures and commands:
`docs/research/2026-11-06-python-performance.md`.

| Shape | What happens | Why |
|---|---|---|
| an element of a container whose type is not written: a bare `list`, `list[Any]`, a parameter with no annotation | `not_readable`, or `external` where the container is a library call's result | nothing fills the type variable, and nothing is guessed |
| a container literal (`found = []`, `d = {}`), then `found.append(x)` | `not_readable` | a literal's class is not read as the owner (the largest remaining group: of the container-method sites still `not_readable`, 1,176 of 2,159 on Sextant and 1,408 of 2,042 on polar have a receiver no call produced: a literal, a `merge` or an untyped local) |
| the result of a call into the scanned code (`workspace.query(...)`, a `Protocol` method) | the value walk follows its body; where there is none, or it returns a value of no type, `not_readable` | a scanned function's written return type is not read as its result's type |
| a union receiver whose members give different element types (`list[A] \| list[B]`) | the element has no owner; the resolver leaves it unbound | several types are never one, and a call site holds one owner: one row per member would need a fact field (not built, a question for the user) |
| a tuple of unknown arity (`tuple[A, ...]`), or a starred target | the names stay untyped | the arity is not written |
| a class of another file as the receiver (`r: Repo[Order]`, `Repo` imported) | its library-inherited methods are not typed | its bases are in a file this scanner does not read (M03), and a class's written bases carry no type arguments in the facts |
| a field declared only by a class-level annotation (dataclass, `NamedTuple`) | `not_readable` | the annotation is not read as the field's type |
| a value typed `Any`, narrowed by `isinstance` | `external` | `isinstance` tests are not read; `is not None` is |
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
| a parameter's default value | not a fact | R27 note: FastAPI's `Depends(...)` defaults will need one (plan 2) |
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
| **`ast` (stdlib) + typeshed + the installed environment** | Syntax, decorators, literals, written types, library signatures | **Built.** Reads one file at a time and writes the existing facts, runs nothing and downloads nothing. Does not substitute generics or read `isinstance` (above). |
| `mypy` in-process | Declared and inferred types, overloads, generics | Its documented API returns report text only, and its plugin system is "experimental" (mypy's documents); a project's mypy plugins would run the scanned environment's code. Measured: 2.7 s cold on Sextant, 4.8 s on polar's package without libraries. A candidate for the four shapes above. |
| `pyright` | Best inference available | Runs on Node.js (the PyPI wrapper downloads Node at run time when none is installed); used as a language server answering per position. That it has no programmatic API is not checked |
| Pyrefly, ty | Fast inference (ty: "written in Rust") | Language servers as well, each one more package to ship; neither states a release status on its front page |
| `PyCG` | Call graph | Named in the literature as the reference Python call-graph tool (see §10) |

There is no artifact equivalent to a `.class` file. `.pyc` bytecode exists but is *less*
informative than the source, and it is tied to one interpreter version. **For Python we read
source.** The full comparison, with what was measured and what comes from the tools' documents,
is `docs/research/2026-11-06-python-type-tools.md`.

---

**The sections below are the inventory the framework plans start from.** None of their rows is
read yet: they say what each framework and library writes, and how hard it is to read.

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
| **Pydantic** (`class Order(BaseModel)`) | **Fully** | Fields, types, defaults, `Optional`, aliases via `Field(alias=…)`. As good as a Java DTO. Used by FastAPI and Litestar, so the *modern* frameworks come with typed payloads attached. |
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
