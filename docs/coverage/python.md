# Coverage — Python

Not in the MVP. Detection shapes are defined in [COVERAGE.md](../COVERAGE.md) §1.
The typing problem this language creates is analysed in [COVERAGE.md](../COVERAGE.md) §10;
this file is the library inventory.

> **Nothing in this file ships today** — see [COVERAGE.md](../COVERAGE.md) §2.
>
> **Scope.** [COVERAGE.md](../COVERAGE.md) §5 is canonical for tier and status,
> organised by protocol. This file holds what does not fit a protocol row: the
> toolchain verdict, the payload story, and the structural oddities of the language.

---

## Toolchain — no compiler-grade fact source exists

| Route | Gives | Problem |
|---|---|---|
| `ast` (stdlib) | Syntax, decorators, literals | **No types, no resolution.** Cannot tell which `Client` a `client.send()` is. |
| `mypy` | Declared and some inferred types | Its API is explicitly internal and unstable; defaults to `Any` in unannotated functions, so it *hides* the gap rather than reporting it |
| **`pyright`** | Best inference available; infers unannotated symbols rather than giving up | **No programmatic API.** The maintainers' answer is to run it as an LSP server and issue hover/type requests per position ⚠️ — a real integration cost and slow at repository scale |
| `PyCG` | Call graph | Named in the literature as the reference Python call-graph tool (see §10) |
| `jedi` / `griffe` | Symbol and API extraction | Signature-level, not call-level |

There is no artifact equivalent to a `.class` file. `.pyc` bytecode exists but is *less* informative than the source — it has already discarded annotations into a `__annotations__` dict of strings, and it is version-locked to the interpreter. **For Python we must read source.**

**Recommendation:** `ast` for structure and decorators, pyright-over-LSP for types where it is affordable, and an LLM overlay for shapes — with the split justified in §10.

---

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
