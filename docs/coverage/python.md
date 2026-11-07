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
  inside a package is not a module. When it looks for modules it skips folders that git
  ignores or that `.sextantignore` names, so a nested checkout such as `.claude/worktrees/*` is
  not a second module. A repository read by several detectors (a Maven project with a Python
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
  Poetry names) and of typeshed, pinned at commit `13ffe24f`. Library classes are
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
| Owner bound by the resolver, or a function value whose body the call enters | 0.7% | 7.8% |
| Unresolved, with one reason from the general list | 16.6% | 30.8% |
| **No owner and no reason** | **0** | **0** |
| Cold analysis (target 60 s, ceiling 300 s) | 8.7 s | 27.2 s |
| Warm analysis, no file changed (target 10 s, ceiling 30 s) | 8.8 s | 27.6 s: **target missed** |

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
from the general list, never a guessed value.

**Types the reader does not work out** (measured on Sextant: 2,541 of its 2,996 `not_readable`
sites call a `dict`, `list`, `str`, `set` or `tuple` method):

| Shape | What happens | Why |
|---|---|---|
| an element taken out of a container: `xs[0].strip()`, `for x in xs: x.strip()` | `not_readable` | a generic's type arguments are not carried to its elements |
| the result of a library method whose return is a type variable: `d.get(k).strip()` | `external` | a library return written as a type variable gives no type (Task 7) |
| a field declared only by a class-level annotation (dataclass, `NamedTuple`) | `not_readable` | the annotation is not read as the field's type |
| a value typed `Any`, narrowed by `isinstance` | `external` | `isinstance` tests are not read; `is not None` is |
| an attribute of a library module: `pytest.mark`, `alembic.op` | `no_writer` (12,683 polar rows) | a library field has no writer in the scanned code, as the JVM answers `System.out` (ruling R26, logged) |
| a library that is not installed | `external`, and the report says so | library symbols come only from the scanned environment; nothing is downloaded (spec §3e) |
| a file written for a newer Python than the one running Sextant | the file is uncovered, naming the version that read it | the grammar is the running Python's (ruled 2026-11-06: run Sextant on the newest Python) |
| names a `sys.path` change makes visible | `external` | `sys.path` changes are not followed (spec §3e) |

The comparison with a type checker, which solves the first four exactly, is
`docs/research/2026-11-06-python-type-tools.md`.

**Values and bodies:**

| Shape | What happens | Ruling or record |
|---|---|---|
| `obj.x = v` on another object (`app.state.x = v`) | not written | R24: only `self` field writes are facts, as on the JVM |
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

**Commands:**

| Shape | What happens | Record |
|---|---|---|
| typer, `argparse`, an entry point naming a function that calls a group | not read (mealie, netbox, httpie) | Task 9b, logged |
| a group's own options and callback; `invoke_without_command=True` | not read | Task 9b, logged |
| `--shout/--no-shout`; a parameter's type; `password_option`, `version_option` | not flags; no column; no row | Task 9b, logged |
| `@click.group` or `@cli.command` with no parentheses | not read | Task 9b, logged (none in the corpus) |
| a command behind a library decorator no value model states (`pass_context`) | a root row with no handler, and no reason column to say why | Task 9b: `roots` has no reason column |
| a command no entry point names | its path is `<program>` | the outermost word is the program's name |
| a group made by a class constructor | not tied to its entry-point name | Task 9b re-review, logged |
| a program started by the code (`subprocess`, `java -jar`) | not recorded | OI-323 |

**Finding modules:**

| Shape | What happens | Record |
|---|---|---|
| a JVM repository with an incidental Python project | becomes multi-module, so `--workspace` is refused | R7 |
| a `tests/` folder with its own `requirements.txt` inside a `pyproject` module | its own module | Task 2, deferred |
| `.egg-info`, a Windows `Lib/site-packages` | not read | Task 2, deferred |
| a Poetry checkout with no installed environment | a note on every run | Task 2, deferred |

---

## Toolchain — why our own reader

| Route | Gives | Why not, or why |
|---|---|---|
| **`ast` (stdlib) + typeshed + the installed environment** | Syntax, decorators, literals, written types, library signatures | **Built.** Reads one file at a time and writes the existing facts, runs nothing and downloads nothing. Does not substitute generics or read `isinstance` (above). |
| `mypy` in-process | Declared and inferred types, overloads, generics | Its build and type objects are internal (from its documents); a project's mypy plugins would run the scanned environment's code. Measured: 2.7 s cold on Sextant, 4.8 s on polar's package without libraries. A candidate for the four shapes above. |
| `pyright` | Best inference available | No programmatic API; it runs as a language server answering per position, and needs Node.js |
| Pyrefly, ty | Fast inference, in Rust | Language servers as well, each a native binary to ship; ty is a preview release |
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
