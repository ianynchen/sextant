# Python FastAPI inbound (plan 2 of 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sextant reads a FastAPI service end to end from its code: every route FastAPI serves,
with its full prefix, its verbs, its query/header/cookie parameters and their requirement, its
request and response shapes (Pydantic, with their wire names), and the dependencies FastAPI runs
for it. `fixtures/orders-fastapi` pins every row against FastAPI's own route table.

**Architecture:**
- **Facts.** The Python scanner writes what a parameter's default and annotation evaluate to, as
  the values they are (OI-328), keeps the metadata of `Annotated[...]`, and corrects two shape
  facts (PEP 526 instance fields, the language's wire projection).
- **One general resolver pass,** `parameter_markers`: for each parameter, the calls that produced
  its default and its `Annotated` metadata. Three readers use it: request parameters, the request
  body rule, and the DI-recipe hop.
- **Catalog data.** All FastAPI and Pydantic knowledge is in four files:
  - `catalogs/fastapi.yml` (`fluent`, routes and mounts);
  - `value-models/fastapi.yml` (a route decorator hands the function back);
  - `bean-models/fastapi.yml` (`Depends`);
  - `shape-models/pydantic.yml` (naming, known types).

**Tech Stack:** Python 3.12+ stdlib `ast`; DuckDB; YAML catalogs. FastAPI 0.162.0 and 0.115.12,
pydantic 2.14, pyhumps 3.8 are read from the installed environment, never imported by Sextant.
The test setup builds the fixture with `uv sync --frozen --offline`.

**Spec:** `docs/superpowers/specs/2026-11-06-python-reader-design.md` (APPROVED v2), §3c (minus
`httpx`, `verb_arg`, `.model_dump()`: plan 3) and done-when item 2. It extends
`2026-11-06-reading-decorators-design.md` (approved; §6 sketched one polar route) and
`2026-11-05-di-recipe-hop-design.md` (approved).

## Needs approval

**All thirteen items are APPROVED by the user, 2026-11-08, as recommended:** N1 option A (two
new fields), N11 option A (extra root rows), N13 option B (one shape, `partial`), and N3, N4,
N6–N10, N12 as written. N2 (option A) and N5 (option A, beside callers) were decided by the truth
rule. **Task 0 runs first. Each task names the items it uses.**

Format: what the item is, the options, then **Recommend**.

**N1 — A parameter's default and annotation, as values (OI-328; spec §3c, §8).**
- **What the spec approved.** "`Query`/`Path`/`Header`/`Body`/`Field` normalized into
  `Parameter.annotations`; defaults into `declares_default`."
- **What the code shows.**
  - An annotation argument is a `LiteralValue` (`facts.py:16`). It holds strings, numbers,
    booleans, class and enum references, annotations and lists. It cannot hold:
    - a function reference (`Depends(get_db)`);
    - `None` (`Query(None)`);
    - `...` (`Query(...)`, which means required);
    - a call result (`Depends(Authenticator(...))`: polar 69 aliases, mealie 12).
  - `declares_default` is a boolean, and the answer depends on the default's value:
    - `= Query()` writes a default, yet the parameter is required;
    - `= Query(None)` is optional;
    - `= Query(...)` is required.
  - The scanner already writes every default expression as calls in the body that runs the
    `def` (`structure.py:489-492`). The parameter just does not point at them.
- **Option A — the two values `inspect.signature` gives FastAPI.** New optional fields on
  `Parameter`, in the existing argument grammar (`CallArgument`):
  - `default`: the default's value;
  - `annotation_value`: the annotation's value, written only where it is not a plain type (an
    `Annotated[...]`, or a name bound to a module-level alias).
  - A `source` in either names a call of the body that runs the `def`: the owner type's
    `<clinit>` for a module function or a method, or the enclosing function for a nested `def`.
  - `declares_default` joins the pydantic `Parameter` model. D00 §5a documents it, but
    `facts.py:58-90` lacks it. It is written `true` wherever `default` is.
  - Pro: no loss, and it follows values through the code (aliases in other files, call
    results). Con: two new fields, and a deviation from the spec's wording.
- **Option B — the spec's normalization into `annotations`.** Pro: no new field. Con: it loses
  every shape listed above, and duplicates calls the facts already hold.
- **Option C — B for literals, A for the rest.** Con: two readers for one question.
- **Recommend A.** It is the smallest form that tells the truth. It also gives Python an
  unfilled argument's value, which is general (N1 is used by Task 4).

**N2 — Keep `Annotated` metadata; read type aliases (no new field).**
- Today a subscripted type form evaluated as a value writes its parts' calls and drops the
  form (`calls.py:2012-2027`, value `_UNKNOWN`). So `Db = Annotated[int, Depends(get_db)]`
  writes `Depends(...)` with nothing pointing at it. `d: Db` is written as the bare text `Db`.
- **Option A — write the subscript as the call R37 names.**
  - A subscript of a type form, evaluated as a value, is the static call
    `<form>#__class_getitem__`. Each index element is one argument, in written order. Its
    result is the form.
  - A module-level `X = Annotated[T, …]`, `X: TypeAlias = …` or `type X = …` is a type alias.
    A parameter annotated `X` has the type `T`. `annotation_value` is `{kind: field, symbol:
    <X's field>}`, also across files, through the headers reader.
  - `...` is the builtin constant it is: `{kind: field, symbol: builtins#Ellipsis.}` (the
    existing `field` kind).
  - Pro: one general rule, no new field. Polar has 179 such aliases; dispatch has 582 params
    typed by one.
- **Option B — a new `metadata: list[CallArgument]` field on `Parameter`.** Con: a cross-file
  alias still needs A's link.
- **Recommend A.**

**N3 — Request parameters read from a parameter's marker call.**
- Today mechanism 4 of D02 §2k reads call-naming entries off a command's decorators.
  Mechanism 1 reads parameter *annotations*.
- FastAPI's markers are calls (`fastapi.param_functions.Query/Header/Cookie/Path`). FastAPI
  reads them off `param.default` or off `Annotated` metadata, and the last FastAPI marker in
  `Annotated` wins (`dependencies/utils.py` `analyze_param`, 0.162.0).
- **Option A — the call-naming entry, matched on a handler parameter's markers.** New keys on
  an entry:
  - `required_when: { arg: <reference>, equals_field: <dotted static field> }`: required when
    that argument is that constant (`builtins.Ellipsis`);
  - `default_arg` may be a list of references (`default`, `default_factory`);
  - `annotated_default: parameter`: a marker in `Annotated` takes the parameter's own default
    (`declares_default`), FastAPI's rule;
  - `spelling: { replace: { "_": "-" }, unless: { arg: <reference>, equals: <literal> } }`: the
    name written nowhere is respelled. This is `Header`'s `convert_underscores`, default true.
  - Pro: reuses the entry, `name_arg`, `optional_when` and argument references. Con: four new
    keys.
- **Option B — normalize in the scanner.** Con: framework names in general code.
- **Recommend A.**

**N4 — Unmarked parameters and the body rule.**
- FastAPI (`analyze_param`) treats a parameter with no marker as follows:
  - a path variable → path;
  - a scalar type → query;
  - otherwise → body.
- Typed `Request`, `Response`, `WebSocket`, `HTTPConnection`, `BackgroundTasks` or
  `SecurityScopes` → no parameter at all.
- `Body`/`Form`/`File` markers → body.
- **Option A — catalog data:**
  - a request-params entry `{ unmarked: true, kind: query, requirement: required,
    scalar_only: true }`, optional where the parameter `declares_default`. "Scalar" means the
    wire projection is a scalar or a shape-model `known_type`. Note that `list[int]` is not a
    scalar: FastAPI reads it as a body unless it is marked.
  - `request_body` (an `annotation_driven` key today) is allowed on an inbound `fluent`
    catalog, with:
    - `marker_calls: [Body, Form, File]`;
    - `fallback: sole_unbound`;
    - `bound_by_calls` (the other markers);
    - `implicit_bindings: [path_variable, scalar]` (new word `scalar`);
    - `excludes` (the six types).
  - Several body parameters keep `sole_unbound`'s existing rule ("several unbound: no
    contract"). Measured: polar 1, mealie 6 (multipart). The issue is logged.
  - Pro: existing block and rule. Con: two new keys and one new word.
- **Option B — one `fastapi_parameters` block.** Con: a framework-shaped key.
- **Recommend A.**

**N5 — `Depends`: `injection: names_recipe` (the mode is spec-approved; its keys are not).**
```yaml
# bean-models/fastapi.yml
id: fastapi
injection: names_recipe
recipe_calls:
  - { owner: fastapi.param_functions, method: Depends,  recipe_arg: { arg: 0, keyword: dependency } }
  - { owner: fastapi.param_functions, method: Security, recipe_arg: { arg: 0, keyword: dependency } }
empty_recipe: parameter_type     # Depends() with nothing: the parameter's type is the recipe
```
- **The recipe is a value, and calling it uses the existing rules:**
  - a function → its returns (a generator → its yields, N10);
  - a class → a construction (R37), whose `__init__` parameters are the recipe's parameters;
  - an instance → its class's `__call__` (R29).
- **Where the hop sits.** Dagger's hop goes **before** callers (di-recipe-hop §5). Here the
  framework's fill is **one more path beside** the in-module callers. A dependency called
  directly with an argument is that caller's own path.
  - Option A: beside callers. Pro: per-path truth (M-1). Con: one more rule in `_parameter`.
  - Option B: before callers, like Dagger. Con: a direct caller's argument is lost.
- **Recommend A, with the keys above.**

**N6 — `dependencies=` on routes, routers, includes and apps.**
- Measured `dependencies=`: dispatch 101 routes, mealie 61; `include_router` 2,
  `APIRouter` 1, `FastAPI` 1.
- FastAPI runs each of these before the handler. Their own parameters join the route's
  parameters (`_build_dependant_with_parameterless_dependencies`; `for_include` joins
  `parent_router.dependencies`).
- **Option A — one new capture name, `dependencies`,** read as a list of marker calls:
  - on a root (`{ keyword: dependencies }`);
  - on `router_holds` (N7);
  - on a mount entry (`dependencies_arg`).
- **Recommend A.** Without it, the requirements of 160 measured routes are missing.

**N7 — A prefix the router holds from its construction.**
- `APIRouter(prefix="/orders")` is not a mount. Two mounts on one router are two serving
  places (`mounts.py:17-19`), but FastAPI composes its prefixes:
  - `add_api_route`: `self.prefix + path`;
  - `for_include`: `parent_router.prefix + prefix`.
- **Option A — a `mount`-block sibling:**
  `router_holds: [{ owner, method: <init>, prefix_arg: { keyword: prefix }, dependencies_arg:
  { keyword: dependencies } }]`. The held prefix goes in front of every route registered on
  that router, and of every mount made on it.
- **Two new refusal words** (DR-6). FastAPI's assertion fails the app's start:
  - `trailing_slash` (`prefix.endswith("/")`);
  - `empty_path` ("Prefix and path cannot be both empty").
  - The existing `refuses_unrooted_path` covers "must start with '/'".
- **Option B — `client_base` with `value_arg`** (decorator design §6). Con: an outbound ladder
  bent to fit a router.
- **Recommend A.**

**N8 — Verbs read from a list, with FastAPI's default.**
- `api_route`/`add_api_route` take `methods`. FastAPI's rule is
  `{m.upper() for m in methods or ["GET"]}` (`routing.py:1072-1074`).
- **Option A:** `http_method: { keyword: methods, absent: GET, case: upper }`. A list or set
  written there gives one row per element (enumerable is exact).
- **Recommend A.** Measured: polar `methods=` 66.
- **Corrected by Task 0 (DR-6):** the source is `if methods is None: methods = ["GET"]`. So `absent`
  means not written or `None`. An empty list is a refused registration (`generate_unique_id`
  asserts `route.methods`), never GET.

**N9 — The response when `response_model` is not written.**
- FastAPI's rule (`routing.py:1134-1155`):
  - `response_model` written → that type (`None` → no model);
  - else the return annotation;
  - a `Response` subclass → none.
- Measured: return annotation only, polar 205; neither written, dispatch 35 and mealie 52.
- **Option A:** `response_fallback: { from: handler_return, none_types:
  [starlette.responses.Response] }` (subtypes included). With no annotation, the response is
  the handler's returned values' one type (`return_flow`). Several types, or none read →
  `partial`, recorded as `single_call` records an unread `response_arg`.
- **Recommend A.**

**N10 — What a generator yields.**
- A generator's one `method_return` is `unresolved` (`calls.py:34,434`). FastAPI hands a yield
  dependency's first yield to the parameter (`get_db`: template, mealie). `contextmanager`'s
  `with … as v` (design §3e) needs the same fact.
- **Option A — `method_return.yielded: true`,** one fact per `yield` value. The generator object
  return stays as it is.
- **Option B — log it.** The declared type beside it (R40) keeps the call graph typed.
  Con: "unknown only where code is absent" is broken.
- **Recommend A.**

**N11 — The recipes FastAPI runs, on the route's trace.**
- **Option A — one more `roots` row per recipe,** at the route's wire address (`root_kind
  inbound_endpoint`). The table's grain (handler, kind, address) allows it. It needs a meaning
  sentence in D01.
- **Option B — call edges from the handler to the recipes.** Con: a lie, because the handler
  does not call them.
- **Option C — log it.**
- **Recommend A.** Auth and session code is where a request goes first.

**N12 — `shape-models/pydantic.yml`: naming read off calls.**
- Pydantic 2.14's output name is the first of these that applies:
  1. `serialization_alias`;
  2. `alias`;
  3. the model's `alias_generator(name)`;
  4. the name.
- New keys:
  - `name_from` entries of the form `{ call: pydantic.fields.Field, arg: { keyword:
    serialization_alias } }`. They read the producer of the field's class-body value.
  - `name_generator`:
    - `{ config_field: model_config, config_call: pydantic.config.ConfigDict, arg: { keyword:
      alias_generator } }`;
    - merged over the written bases in written order, the last base winning, then the class's own
      (pydantic `ConfigWrapper.for_model`; corrected by Task 0 — not the C3 order);
    - `functions: [{ function, strategy, by }]`.
  - Two strategy words, `camel` and `pascal`, which are pydantic's `to_camel`/`to_pascal`
    exactly. `humps.main.camelize` (mealie) maps to `camel` only if Task 0's probe shows they
    agree on every mealie field name. Otherwise it gets its own word.
  - `required: no_default`: a field is required when it writes no default (validation mode).
  - `private_prefix: "_"`: pydantic's private attributes are not fields.
  - `alias_priority`: the order above holds while it is unset or 2. A literal `alias_priority=1` lets
    the generator replace `alias` and `serialization_alias` (Task 0); a value not readable →
    `partial`. A `Field` wrapper that passes these through `**kwargs` (mealie `UpdatedAtField`) →
    `partial`.
- A generator no entry names → those fields are `unresolved` and the shape is open. This is
  §2g's "not guessed at".
- **Recommend as written.** Alternative: per-model strategies in code (con: framework
  knowledge in code).

**N13 — Input names that differ from output names.**
- A shape is one per type, but pydantic accepts other input names: `validation_alias`
  (polar 90, most of them `AliasChoices`), `populate_by_name` (mealie, dispatch).
- **Option A — split shapes by direction where names differ.** A new shape-id form: a D01
  change, and the stitcher sees two ids.
- **Option B — one shape with output names.** A field whose accepted input names differ gets
  `resolution: partial`. The issue is logged with the counts. No format change. A request
  never shows a name as `resolved` when it would refuse it.
- **Option C — ignore it.** Con: a lie on request shapes.
- **Recommend B now, A logged** for a ruling with the stitcher.

## Global Constraints

- **Rules from the spec and the rulings:**
  - The scanner reads one file at a time. Nothing scanned is imported or run by Sextant; only
    the test setup imports the fixture (spec §7).
  - Existing words first. Only N1–N13 as approved are new.
  - A guess is never `resolved`. Every unknown carries one word of `values._REASONS` and a
    detail.
  - One row per path (M-1).
- **Framework behaviour mirrored (DR-6),** with versions and lines quoted in
  `scripts/probes/fastapi_rules.md` (Task 0):
  - **Route paths and prefixes:**
    - a route path is router prefix + path;
    - an include is parent prefix + include prefix + the route's path;
    - a Starlette `mount` path is `rstrip("/")`;
    - HEAD is never added to GET.
  - **Parameter defaults:**
    - `Optional[X]` with no default is required;
    - `list[X]` unmarked is a body;
    - `Header` names convert `_` to `-`.
  - **Responses:** `response_model` comes before the return annotation.
  - **Registrations FastAPI refuses** (assertions at registration) derive no row. Each files a
    `refused_registration` open question. The detail says FastAPI raises at import, so the app
    does not start.
  - **The include rule follows 0.141+ and 0.162.0 (lazy include):**
    - Lazy include: a route added to a router after it was included is served.
    - 0.115.12 (dispatch) copies at include time instead.
    - The difference is stated in the catalog and logged as Minor: no corpus registers after
      including.
- **Truth on handlers:**
  - The row's handler is what FastAPI calls, through the decorator walk (design §3d). A
    library wrapper with no value-model entry makes the row `partial`, `external`.
  - FastAPI reads the signature of `__wrapped__` (`inspect.signature`). A module-code
    `functools.wraps` wrapper is logged: 0 FastAPI routes in the corpus.
- **Performance** (spec §5; polar `server/`): the ceiling is 300 s cold and 30 s warm; the
  target is 60 s and 10 s. Report the time after every task that changes a pass. Missing the
  ceiling stops the work for a ruling.
- **Reuse:**
  - New `Parameter` fields bump the facts version (`domain/version.py`). Every document is
    re-read once.
  - Alias types come through the headers reader. Its digest already keeps module-level
    assignments (`project.header_digest`), so editing an alias re-reads the files that import
    it.
  - The resolve key is unchanged in form.
  - Task 2 pins both in `tests/api/test_analyze_reuse.py`.
- **Project rules:**
  - JDK 21 (`JAVA_HOME=/opt/homebrew/opt/openjdk@21`).
  - The gate is `scripts/check.sh` (full), plus the six field pins (`scripts/field_check.py`).
  - ASD-STE-100 comments; GUIDELINES §1–4, §13.5.
  - No framework names in general code (`tests/architecture/test_source_rules.py`). No Python
    names outside the Python scanner and its recorded exceptions
    (`test_language_confinement.py`).
  - Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  - Docs land with the task that builds them: D00, D02, D01 (N11), M03, M04, COVERAGE and the
    Python essay.
  - New issues are logged from OI-345, in Plane plus the id map in `docs/open-issues.md`.
- **Not in scope:**
  - OI-327: FastAPI needs no `passes_on`, the only reader of `exact_methods`
    (`pass_through.py:478`, `fluent.py:1597-1605`).
  - OI-341: routes and mounts read routers through `values.producer_paths`, which constructs
    through a `virtual <init>` already (`values.py:4571-4581`). The three readers it names are:
    - `arguments._linked_constructor`;
    - `client_base` (`client_base.py:982`);
    - `chains._chain_key`, for a constructor *root*.

    No FastAPI catalog entry reaches any of them. Task 6 pins polar's factory shape to prove it.
    Plan 3 owns the `client_base` case (`httpx.Client` built through a class object).
  - websocket routes, `Form`/`File` multipart shapes, `Body(embed=True)`, `computed_field`,
    and pydantic v1 `class Config`: each is logged with its count.

## Review Focus

1. **A dependency through an alias in another file**
   - Shape: `db_session: DbSession`, with `DbSession = Annotated[Session, Depends(get_db)]` in
     `deps.py` (dispatch: 582 parameters typed by a bare name).
   - Expected:
     - no query row for `db_session`;
     - the recipe `get_db` is found;
     - `db_session.query(...)` binds to `Session`.
   - Pinned in Task 8.
2. **A sub-application mount above nested includes**
   - Shape: `app.mount("/api/v1", app=api)`, then `api.include_router(r, prefix="/{organization}/auth")`
     (dispatch `main.py:268`, `api.py:91`).
   - Expected: `GET /api/v1/{organization}/auth/…`, never `/{organization}/auth/…`.
   - Pinned in Task 6.
3. **A router class from a factory typed `type[APIRouter]`**
   - Shape: `APIRouter = get_api_router_class(APIRoute)`, then
     `router = APIRouter(prefix="/orders")` in another file (polar, 80 of 83 router files).
   - Expected: the construction prefix applies under the include's prefix (`/v1/orders/…`).
   - Pinned in Task 6.
4. **An inherited `alias_generator`**
   - Shape: `class Base(BaseModel): model_config = ConfigDict(alias_generator=to_camel)`, and
     `class OrderOut(Base): created_at: datetime = Field(serialization_alias="createdOn")`
     (mealie).
   - Expected: `createdOn`, and `orderId` for an unaliased `order_id`.
   - Pinned in Task 9.
5. **Optional, required and defaulted query parameters**
   - Shapes and expected requirements:
     - `limit: int = 10` → optional;
     - `q: str | None` → required (pydantic v2);
     - `q: str = Query(...)` → required;
     - `q: str | None = Query(None, alias="search")` → optional, named `search`;
     - `x_trace_id: Annotated[str, Header()] = "-"` → optional, named `x-trace-id`.
   - Pinned in Task 7.

---

### Task 0: Probe FastAPI and pydantic, measure the corpus, time polar

**Needs:** nothing.

**Files:**
- Create:
  - `scripts/probes/fastapi_rules.md`, `scripts/probes/fastapi_rules.py`;
  - `scripts/probes/fastapi_shapes.py` (ast only, `python -I`);
  - `scripts/probes/pydantic_naming.md`.
- Modify: `docs/research/2026-11-06-python-performance.md`.

**Interfaces:**
- **`fastapi_rules.md` quotes `file:function` at 0.162.0 and 0.115.12 for:**
  - prefix composition, `include_router` assertions, `Mount.__init__`;
  - `methods` default and case, HEAD;
  - `analyze_param` (markers, the last-wins rule, error assertions, unmarked classification,
    `convert_underscores`, `Optional` without a default);
  - `_build_dependant_with_parameterless_dependencies`;
  - the `response_model` placeholder rule;
  - `get_typed_signature` (`__wrapped__`);
  - lazy versus eager include.
- **`fastapi_rules.py`:** run inside a throwaway uv environment, it prints FastAPI's own answer
  for each rule (the flattened dependant, the effective routes).
- **`fastapi_shapes.py <root>…`:** the counts quoted in N1–N13, for polar, dispatch, mealie and
  the template.
- **`pydantic_naming.md`:** `to_camel`, `to_pascal` and `humps.camelize` on every field name of
  mealie's models, and the alias priority rules (`alias_priority`, the generator against
  `alias`).

- [ ] **Step 1:** Write the probes. Run them. Record the counts and the quotes. Note that the
  uv cache already holds `fastapi-0.162.0` and `0.141.1`. 0.115.12 is fetched once, at dev
  time, into the probe environment.
- [ ] **Step 2:** Time polar cold and warm on main (the baseline for every later task).
- [ ] **Step 3:** If a probe contradicts a rule written in this plan, change the plan text and
  tell the controller before Task 1.
- [ ] **Step 4:** Commit (`docs(probes): FastAPI and pydantic rules, corpus shapes (OI-208 plan 2 task 0)`).

### Task 1: `fixtures/orders-fastapi`, its environment, and FastAPI's own route table

**Needs:** nothing. The fixture is code; its pins arrive with later tasks.

**Files:**
- Create the fixture, `fixtures/orders-fastapi/`:
  - `pyproject.toml`: `fastapi==0.162.0`, `pydantic==2.14.*` pinned exactly, `pyhumps==3.8.0`;
  - `uv.lock` (committed); `.gitignore` (`.venv/`);
  - `app/main.py`: `app = FastAPI(dependencies=[Depends(request_id)])`, `api = FastAPI()`,
    `app.mount("/api", app=api)`, `api.include_router(v1, prefix="/v1")`,
    `@app.get("/health")`;
  - `app/routing.py`: the polar factory `def router_class(route: type[APIRoute]) ->
    type[APIRouter]`, then `APIRouter = router_class(APIRoute)`;
  - `app/deps.py`:
    - a yield dependency `get_db`, and `DbSession = Annotated[Session, Depends(get_db)]`;
    - `class Authenticator` (`__init__(scope)`, `__call__(x_api_key: Annotated[str,
      Header()])`), and `Principal = Annotated[User, Depends(Authenticator("orders:read"))]`;
    - `class Paging` (`__init__(limit: int = 20, offset: int = 0)`);
    - `audit` and `request_id`, each reading one header;
  - `app/services.py`: `class OrderService`, and the module singleton `orders = OrderService()`;
  - `app/schemas.py`:
    - `Base` with `alias_generator=to_camel` and `populate_by_name=True`;
    - `OrderIn` (`note: str | None = None`, `total: Decimal = Field(alias="grandTotal")`,
      `customer_id: int`);
    - `OrderOut` (`order_id: UUID`, `created_at: datetime`, `status: str =
      Field(serialization_alias="state")`, `_secret: str = PrivateAttr()`);
    - `Legacy` (`alias_generator=camelize`, from humps);
  - `app/orders.py`, every remaining §3c row:
    - `router = APIRouter(prefix="/orders", dependencies=[Depends(audit)])`;
    - `get` with `order_id: UUID`, `db: DbSession`, `who: Principal`, `verbose: bool = False`,
      `q: str | None = Query(None, alias="search")`, `x_trace_id: Annotated[str | None,
      Header()] = None`, `session_id: Annotated[str, Cookie()]`, and `response_model=OrderOut`;
    - `post("")`, with `body: OrderIn` and `svc: OrderService = Depends(get_service)`,
      returning `-> OrderOut`;
    - `api_route(".../cancel", methods=["post", "PUT"])`;
    - `add_api_route("/export", export, methods=["GET"])`;
    - an f-string route path from a module constant;
    - `response_model=None` with `-> Response`;
    - a function under two route decorators;
    - `paged(p: Paging = Depends())`;
    - a call `orders.create(...)` on the singleton;
  - `app/admin.py`: `admin = APIRouter()`, included with `prefix="/admin"` and
    `dependencies=[Depends(audit)]`.
  - **Left for plan 3:** `app/clients.py` and `app/settings.py` (`env_file`) are listed in the
    fixture README and not written.
- Create the harness:
  - `tests/fixture_python.py`: `synced(root: Path, *, offline: bool) -> Path` runs
    `uv sync --frozen` (`--offline` in the suite) and returns the environment. CI's priming step
    runs it online.
  - `tests/e2e/fastapi_oracle.py`: run with the fixture's own interpreter, it prints JSON. For
    each effective route (`fastapi.routing._iter_routes_with_context`, recursing into `Mount`
    apps):
    - the methods, the path and the endpoint qualname;
    - the response model name;
    - each flat-dependant query/header/cookie parameter (`alias`, `required`);
    - the body parameter names.
- Modify:
  - `tests/conftest.py`: a session fixture `orders_fastapi_env`;
  - `.github/workflows/pr.yml`: a priming step;
  - `tests/fixture_build.py`: if it lists primed fixtures, add this one.
- Test: `tests/e2e/test_orders_fastapi.py::test_fastapi_serves_the_fixture_routes`.

- [ ] **Step 1: Failing test.** It reads the oracle output and asserts the hand-written expected
  set:
  - `GET /health`;
  - `GET /api/v1/orders/{order_id}`;
  - `POST /api/v1/orders`;
  - `POST` and `PUT /api/v1/orders/{order_id}/cancel`;
  - `GET /api/v1/orders/export`, `/api/v1/orders/v2/stats`, `/api/v1/orders/raw`,
    `/api/v1/orders/a`, `/api/v1/orders/b`, `/api/v1/orders/paged`;
  - the admin rows.

  Then each route's parameter list. This pins the fixture against FastAPI, not against
  Sextant.
- [ ] **Step 2:** Run; expect FAIL (no fixture).
- [ ] **Step 3:** Write the fixture. Run `uv lock` once, online. Commit `uv.lock`.
- [ ] **Step 4:** Run; expect PASS. Run `uv run sextant module analyze fixtures/orders-fastapi`:
  it completes. Record the fact count and the time.
- [ ] **Step 5:** Commit.

### Task 2: Parameter values, `Annotated` forms and type aliases in the facts

**Needs:** N1, N2.

**Files:**
- Modify:
  - `src/sextant/domain/facts.py` (`Parameter.default`, `annotation_value`, `declares_default`);
  - `domain/version.py` (facts +1, with a history note);
  - `ingress/extract/python/structure.py` (`_signature`);
  - `calls.py` (`_type_form` → the `__class_getitem__` call; `...` as `builtins#Ellipsis.`);
  - `typing_rules.py` (aliases);
  - `project.py` (`ModuleHeader.aliases: dict[str, TypeRef]`);
  - D00 §5a, M03.
- Test:
  - `tests/ingress/extract/python/test_parameter_values.py`;
  - `tests/domain/test_facts.py`;
  - `tests/api/test_analyze_reuse.py`.

**Interfaces:**
- **Produces, on Python parameters:**
  - `Parameter.default: CallArgument | None`;
  - `Parameter.annotation_value: CallArgument | None`;
  - `Parameter.declares_default: bool = False`.
- **Produces, on call sites:** the type-form call `typing/Annotated#__class_getitem__`
  (`invoke_kind: static`), with one argument per index element.
- **Consumes:** the defaults already written as calls (`structure.py:489-492`).

- [ ] **Step 1: Failing tests:**
  - `test_a_literal_default_is_the_parameter_default`: `limit: int = 10` →
    `default.kind == "int"`, `declares_default`.
  - `test_a_call_default_names_its_call_in_the_body_that_runs_the_def`: `db = Depends(get_db)`
    → `default.source` is the ordinal of the `Depends` call in `<clinit>`.
  - `test_a_method_default_is_read_in_the_class_body`.
  - `test_inline_annotated_writes_its_form_call_and_points_at_it`.
  - `test_an_alias_in_another_file_is_its_type_and_its_field`: `d: DbSession` → `type` is
    `Session`; `annotation_value == {kind: field, symbol: app/deps#DbSession.}`.
  - `test_ellipsis_is_the_builtin_constant`.
  - `test_a_plain_type_annotation_writes_no_annotation_value`.
  - `test_jvm_parameters_validate_unchanged` (`declares_default` from raw JSON).
  - `test_editing_an_alias_rereads_the_files_that_import_it` and
    `test_editing_a_body_beside_an_alias_rereads_only_that_file` (reuse).
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement. Update D00 §5a (both fields, where a `source` points, the alias
  rule, the `...` rule) and M03.
- [ ] **Step 4:** Run, then the full gate and the field pins: JVM output must be identical.
  Time polar.
- [ ] **Step 5:** Commit.

### Task 3: Two shape facts — PEP 526 fields, Python wire projection

**Needs:** nothing new (both correct existing values).

**Files:**
- Modify: `ingress/extract/python/structure.py` (around `:446`), `typing_rules.py`, M03, D00
  §5b.
- Test: `tests/ingress/extract/python/test_shape_facts.py`, `tests/application/test_receiver_binding.py`.

**Interfaces:**
- **Produces:**
  - An annotated class-body name not written `ClassVar` is an instance field,
    `static: false`, whatever its value. Its value stays the class-body `field_write` (PEP 526:
    "declares an instance variable").
  - `TypeRef.wire_type`/`wire_format` for what the language fixes:
    - `str` → string; `int` → integer; `float` → number; `bool` → boolean;
    - `list`/`set`/`frozenset`/`tuple`/`Sequence` → array;
    - `dict`/`Mapping` → map;
    - every other class → object.

    `bytes`, `datetime`, `UUID` and `Decimal` are the serializer's (N12 `known_types`).

- [ ] **Step 1: Failing tests:**
  - `test_an_annotated_class_name_with_a_default_is_an_instance_field`;
  - `test_classvar_and_unannotated_names_stay_static`;
  - `test_a_self_read_still_takes_the_class_body_write` (R33 unchanged);
  - `test_builtin_types_carry_their_wire_type`;
  - `test_optional_list_of_str_is_a_nullable_array_of_string`.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run, then the gate and the field pins. Re-run Sextant on itself and on polar:
  report the change in bound receivers. It must be explained, never only accepted.
- [ ] **Step 5:** Commit.

### Task 4: `parameter_markers` and defaults for unfilled arguments

**Needs:** N1, N2.

**Files:**
- Create: `src/sextant/application/resolve/parameter_markers.py`.
- Modify: `application/resolve/values.py` (`_parameter`: an unfilled slot reads `default`), M04.
- Test: `tests/application/test_parameter_markers.py`, `tests/application/test_values_defaults.py`.

**Interfaces:**
- **Produces:**
  - `parameter_markers(index: ValueIndex) -> Mapping[tuple[str, int], tuple[Marker, ...]]`,
    cached on the index like `suffixes` (ruling R14: `workspace.once` cannot read the derived
    tables `producer_paths` needs);
  - `Marker(site: Mapping[str, Any], where: Literal["default", "annotation"], order: int,
    path: int)`:
    - the producing call of the default, or of each `Annotated` metadata element, in written
      order: `order` is the element's written position among the metadata (slot index − 1;
      0 for a default);
    - `path` is the index of the producer path it was read on, among that `where`'s paths:
      markers sharing a `path` hold together, two paths are alternatives (task 4 review);
    - read through `values.producer_paths`, so aliases (module fields, other files) are
      followed;
    - one marker per path.
- **The rule for an unfilled argument:** a call that fills no argument for a parameter passes
  the parameter's `default`. This is Python's rule, read where the parameter has one.
  Language-blind: no JVM parameter has a `default`.
- **Cost:** one producer read per parameter that has a `default` or an `annotation_value`
  (polar: about 2,100), each cached; aliases are read once each.

- [ ] **Step 1: Failing tests:**
  - `test_a_default_marker_is_found`;
  - `test_an_annotated_marker_is_found_in_written_order`;
  - `test_an_alias_marker_in_another_file_is_found`;
  - `test_a_marker_two_paths_give_is_two_markers`;
  - `test_a_call_that_omits_an_argument_passes_the_default`: `fetch(url)` with
    `timeout=10` → `10`, resolved;
  - `test_a_jvm_module_has_no_markers`.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement. No second walk.
- [ ] **Step 4:** Run, then the gate. Time polar (target: under 1 s added).
- [ ] **Step 5:** Commit.

### Task 4b: The scanner types constructions (ruling R17)

**Needs:** nothing new: decorator design §3b option A (approved) and spec §3a ("read as the
typing specification defines them").

**Why:** Task 5 found every route call owner-less in the facts. `app = FastAPI()` and polar's
`router = APIRouter(...)` (the class from a factory typed `type[_APIRouter]` in another file)
give their names no type, so `app.get` / `router.get` have no `target.owner` and no `fluent`
root can match (polar: 1,653 calls). The design's "already read" was not true.

**Files:** `ingress/extract/python/calls.py`, `libraries.py`, `project.py`, `typing_rules.py`;
the header pass that lists referenced types; `domain/version.py` (facts +1); M03, D00.

**Interfaces — produces:**
- Calling a class (library or project) gives an instance of it: the call's result is typed
  `X`, and a later `name.m()` on the name it is bound to is written with `owner: X`,
  `evidence: declared` (as click's `Group` in plan 1).
- A name whose value is typed `type[X]` (a parameter, a return, a module field, in this file or
  another file through the project headers) is the class `X`; calling it gives an instance of
  `X`. A `virtual <init>` stays as written where the class is not known (R37 unchanged).
- A module-level name read later in the same file takes the type of the values written to it in
  that file (design §3b): one type or the closed list. Writes from other files stay the
  resolver's.
- `referenced_types` counts a class that a static call names, so `fastapi/applications/FastAPI#`
  gets a type header.

- [ ] **Step 1: Failing tests:**
  - `test_a_library_class_call_types_the_name_it_is_bound_to` (`app = FastAPI()`, `app.get` →
    owner `fastapi/applications/FastAPI#`);
  - `test_a_type_of_x_factory_in_another_file_types_the_construction` (polar's shape);
  - `test_a_project_class_construction_types_its_name`;
  - `test_a_name_written_two_classes_is_the_closed_list`;
  - `test_a_class_only_a_static_call_names_gets_a_header`;
  - `test_a_name_rebound_in_another_file_is_not_typed_here`.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement. Update M03 and D00.
- [ ] **Step 4:** Gate and pins (JVM identical). Polar and Sextant: report owned call sites and
  bound receivers before and after, each change by cause; time polar.
- [ ] **Step 5:** Commit (`feat(python): the scanner types constructions (plan 2 task 4b)`).

### Task 5: `fastapi.yml` routes — verbs, paths, handlers, responses

**Needs:** N8, N9.

**Files:**
- Create: `src/sextant/catalogs/fastapi.yml`, `catalogs/value-models/fastapi.yml`.
- Modify:
  - `engines/fluent.py` (`http_method` from a list, `absent`, `case`; `response_fallback`);
  - `ingress/catalogs/yaml_source.py` (loader checks);
  - D02 §2 `fluent`.
- Test: `tests/application/test_fastapi_routes.py`, the loader tests.

**Interfaces:**
- **Catalog:**
  - `style: fluent`, `protocol: http`, `direction: inbound`, `detect.coordinates: [fastapi]`;
  - `measured`: 0.115.12 and 0.162.0, by `fastapi_rules.md`;
  - `shape_model: pydantic` (Task 9; until then `json`);
  - `bean_model: fastapi` (Task 8).
- **Roots.** For each owner in `fastapi.routing.APIRouter` and `fastapi.applications.FastAPI`
  (the owner spelling is confirmed on the fixture's facts):
  - `get`/`post`/`put`/`patch`/`delete`/`head`/`options`/`trace` →
    `captures: { http_method: <VERB>, url: { arg: 0, keyword: path }, response: { keyword:
    response_model } }`;
  - `api_route` → `http_method: { keyword: methods, absent: GET, case: upper }`;
  - `add_api_route` is a root that is also terminal, with `handler: { arg: 1, keyword:
    endpoint }`.
- **Steps:** `[{ method: __call__, captures: { handler: arg0 } }]`, `terminal: [__call__,
  add_api_route]`.
- **`response_fallback`:** `{ from: handler_return, none_types: [starlette.responses.Response] }`.
- **Value model:** every route decorator above has `result_returns: arg0` (its inner `decorator`
  returns `func`), so two stacked decorators give two rows.

- [ ] **Step 1: Failing tests:**
  - `test_a_decorated_function_is_a_get_row`;
  - `test_app_get_is_a_row_on_the_app`;
  - `test_api_route_methods_are_one_row_each_upper_cased`;
  - `test_api_route_without_methods_is_get`;
  - `test_add_api_route_names_its_endpoint`;
  - `test_two_route_decorators_are_two_rows_one_handler`;
  - `test_fstring_path_from_a_module_constant_resolves`;
  - `test_response_model_comes_before_the_return_annotation`;
  - `test_response_model_none_is_no_response`;
  - `test_a_response_subclass_return_is_no_response`;
  - `test_the_return_annotation_is_the_response_when_no_model_is_written`;
  - `test_no_model_no_annotation_reads_the_returned_type`;
  - `test_a_library_wrapper_under_the_route_is_partial_external`;
  - `test_every_jvm_catalog_derives_the_same_rows` (gate).
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement. D02 states `absent`, `case` and `response_fallback`.
- [ ] **Step 4:** Run, then the gate and the field pins. Time polar, and count its rows against
  the oracle's 576 decorators (information only; plan 3 pins it).
- [ ] **Step 5:** Commit.

### Task 6: Prefixes — `include_router`, the router's own prefix, sub-application mounts

**Needs:** N6 (the mount side), N7.

**Files:**
- Modify:
  - `shapes/mounts.py` (`router_holds`: a held prefix in front of routes and mounts; the
    `trailing_slash` and `empty_path` refusals);
  - `ingress/catalogs/yaml_source.py`;
  - `catalogs/fastapi.yml`;
  - D02 §2 `mount`.
- Test: `tests/application/test_fastapi_prefixes.py`.

**Interfaces:**
- **Catalog:**
  ```yaml
  router_type: [fastapi.routing.APIRouter, fastapi.applications.FastAPI]
  router_holds:
    - { owner: fastapi.routing.APIRouter, method: <init>, prefix_arg: { keyword: prefix },
        dependencies_arg: { keyword: dependencies }, refuses: [trailing_slash] }
  mount:
    - { owner: fastapi.routing.APIRouter, method: include_router, router_arg: { arg: 0, keyword: router },
        prefix_arg: { keyword: prefix }, dependencies_arg: { keyword: dependencies },
        refuses: [trailing_slash, empty_path] }
    - { owner: fastapi.applications.FastAPI, method: include_router, … the same … }
    - { owner: fastapi.applications.FastAPI, method: mount, router_arg: { arg: 1, keyword: app },
        prefix_arg: { arg: 0, keyword: path }, strip_trailing: "/" }
  refuses_unrooted_path: false   # FastAPI keeps a route path as written ("x" is served)
  # a PREFIX must start with "/": `unrooted` in a prefix entry's `refuses` (Task 0)
  ```
- **`strip_trailing`** is Starlette's `path.rstrip("/")`. If it is not expressible with the
  existing `wildcard` key, it is added to N7 before building.
- **The held prefix is read on the producer of the router**, through the same
  `producer_paths` read the mount join already makes. A construction through a `virtual
  <init>` (polar's factory) is the same producer.
- **Cost:** one cached read per router construction (polar: 85).

- [ ] **Step 1: Failing tests:**
  - `test_router_prefix_goes_before_every_route_on_it`;
  - `test_include_prefix_goes_before_the_router_prefix`;
  - `test_a_parent_router_prefix_goes_before_an_include_on_it`;
  - `test_a_sub_application_mount_prefixes_its_routes` (Review Focus 2);
  - `test_a_factory_built_router_class_keeps_its_prefix` (Review Focus 3; it also guards
    OI-341's absence);
  - `test_a_prefix_ending_in_slash_is_refused_and_the_route_has_no_row`;
  - `test_empty_prefix_and_empty_path_is_refused`;
  - `test_a_router_included_twice_is_two_rows`;
  - `test_a_router_never_included_serves_at_its_own_prefix`;
  - `test_static_files_mount_adds_no_rows`.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run, then the gate and the field pins (the Vert.x and click mounts must be
  unchanged). Time polar.
- [ ] **Step 5:** Commit.

### Task 7: Request parameters and the request body

**Needs:** N3, N4.

**Files:**
- Modify:
  - `request_requirements.py` (a call-naming entry matched on `parameter_markers`; the
    `unmarked` entry; `required_when`, `annotated_default`, `spelling`);
  - the body rule's reader (`shapes/contracts.py`'s `_REQUEST_BODY_KEYS` and its fluent use);
  - `yaml_source.py`;
  - `catalogs/fastapi.yml`;
  - D02 §2k (mechanism 4 on inbound rows), D02 §2 `request_body`.
- Test: `tests/application/test_fastapi_request_params.py`.

**Interfaces:**
- **Catalog `request_params`:**
  - one entry per marker: `Query` (`kind: query`), `Header` (`kind: header`, with `spelling`),
    `Cookie` (`kind: cookie`);
  - each has `name_arg: { keyword: alias }` and `requirement: required`;
  - `default_arg: [{ arg: 0, keyword: default }, { keyword: default_factory }]`;
  - `required_when: { arg: { arg: 0, keyword: default }, equals_field: builtins.Ellipsis }`;
  - `annotated_default: parameter`;
  - plus `{ unmarked: true, kind: query, requirement: required, scalar_only: true }`.
- **`Path` markers write no row.** The address carries the variable, as Spring writes none for
  `@PathVariable`.
- **Errors FastAPI raises in `analyze_param`:**
  - `Depends` in both `Annotated` and the default;
  - a marker in both;
  - a non-`Path` marker on a path variable;
  - a path variable with an `Annotated` default.

  Each is a refused registration (Global Constraints).

- [ ] **Step 1: Failing tests** (Review Focus 5 included):
  - `test_a_defaulted_scalar_is_an_optional_query`;
  - `test_optional_without_default_is_required`;
  - `test_query_ellipsis_is_required`;
  - `test_query_none_with_alias_is_optional_and_named_by_alias`;
  - `test_annotated_header_takes_the_parameter_default_and_hyphenates`;
  - `test_convert_underscores_false_keeps_the_name`;
  - `test_cookie_in_annotated_without_default_is_required`;
  - `test_a_path_variable_writes_no_row`;
  - `test_an_unmarked_model_is_the_body_not_a_query`;
  - `test_an_unmarked_list_is_the_body`;
  - `test_request_and_background_tasks_write_nothing`;
  - `test_depends_in_default_and_annotated_is_refused`;
  - `test_the_last_annotated_marker_wins`.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run, then the gate and the field pins (the Spring, JAX-RS and click rows must
  be unchanged). Time polar.
- [ ] **Step 5:** Commit.

### Task 8: `Depends` — the recipe hop, yields, dependency parameters, recipe roots

**Needs:** N5, N6, N10, N11.

**Files:**
- Create: `src/sextant/catalogs/bean-models/fastapi.yml`.
- Modify:
  - `application/resolve/beans.py` (the `names_recipe` mode's catalog reading; the recipe itself
    is read from `parameter_markers` in `values._parameter` at walk time, beside callers — R14);
  - `values.py` (`_parameter`: the recipe as a path beside callers; a generator recipe reads
    its yields);
  - `ingress/extract/python/calls.py` (yields, N10);
  - `domain/facts.py` (`MethodReturnFact.yielded`); `version.py`;
  - `request_requirements.py` (a recipe's own parameters join, recursively; `dependencies`
    captures from the route, `router_holds`, mounts and the app);
  - `roots.py` (recipe roots, N11);
  - `catalogs/fastapi.yml`;
  - D02 §1c, D00 §5, D01 `roots`, M04.
- Test: `tests/application/test_fastapi_depends.py`, `tests/ingress/extract/python/test_yields.py`.

**Interfaces:**
- **`injected_parameters`** gains `ProvidedBy` entries whose provider is a recipe *value*
  `(caller, CallArgument)`, not only a method symbol. `_filled_by` calls that value with the
  existing call-of-a-value rules (R29, R37).
- **The recipe's own parameters** are the callable's signature:
  - a function's own;
  - a class's `__init__` by C3 order, without `self`;
  - an instance's class `__call__`.
- **The hop's depth** is bounded by the walk's trail. The recipe set per route is cached by
  recipe (polar: the same 20 or so recipes on 576 routes).

- [ ] **Step 1: Failing tests:**
  - `test_depends_default_fills_the_parameter_with_the_recipe_return`;
  - `test_a_yield_dependency_fills_with_its_first_yield`;
  - `test_alias_dependency_in_another_file_binds_the_receiver` (Review Focus 1);
  - `test_empty_depends_constructs_the_parameter_type`;
  - `test_an_instance_recipe_runs_its_call_method` (polar `Authenticator`);
  - `test_a_direct_caller_argument_is_its_own_path`;
  - `test_a_recipe_header_joins_the_route_params`;
  - `test_a_class_recipe_init_params_are_queries` (`Paging`);
  - `test_route_router_include_and_app_dependencies_join`;
  - `test_a_router_included_twice_gets_each_include_dependencies_on_its_row`;
  - `test_each_recipe_is_a_root_at_the_route_address`;
  - `test_a_recipe_in_code_not_scanned_is_external`.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement. The Dagger and Spring answers must be byte-identical
  (`fixtures/orders-dagger*` e2e).
- [ ] **Step 4:** Run, then the gate and the field pins. Time polar. Report the bound receivers
  before and after.
- [ ] **Step 5:** Commit.

### Task 9: `shape-models/pydantic.yml` — fields, wire names, known types

**Needs:** N12, N13.

**Files:**
- Create: `src/sextant/catalogs/shape-models/pydantic.yml`.
- Modify:
  - `shapes/expansion.py` (`_wire_name` reads a `call` source on the field's class-body
    producer; `name_generator` merged along the lookup order; the strategies `camel` and
    `pascal`; `required: no_default`; `private_prefix`; N13 `partial`);
  - `ingress/catalogs/yaml_source.py` (`_check_shape_model`);
  - `catalogs/fastapi.yml` (`shape_model: pydantic`);
  - D02 §1b, §2f, §2g.
- Test: `tests/application/test_pydantic_shapes.py`.

**Interfaces:**
- **`known_types`:**
  - `datetime.datetime` → string, date-time;
  - `datetime.date` → string, date;
  - `uuid.UUID` → string, uuid;
  - `decimal.Decimal` → string (pydantic 2's JSON mode);
  - `bytes` → string;
  - `pydantic.types.UUID4` → string, uuid.

  Each entry carries the probe that read it.
- **Cost:** one producer read per field with a class-body value (polar: about 1,800), and one
  config fold per class, cached.

- [ ] **Step 1: Failing tests:**
  - `test_a_defaulted_field_is_on_the_wire_and_not_required`;
  - `test_field_alias_names_the_wire_field`;
  - `test_serialization_alias_wins_over_alias`;
  - `test_inherited_to_camel_generator_names_unaliased_fields` (Review Focus 4);
  - `test_explicit_alias_wins_over_the_generator`;
  - `test_humps_camelize_is_read_as_the_probe_said`;
  - `test_an_unknown_generator_leaves_names_unresolved_and_the_shape_open`;
  - `test_a_wrapper_of_field_with_unpacked_kwargs_is_not_readable` (mealie `UpdatedAtField`);
  - `test_private_attributes_are_not_fields`;
  - `test_validation_alias_makes_the_field_partial` (N13);
  - `test_decimal_is_a_string`.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run, then the gate and the field pins (the JVM shapes must be byte-identical).
  Time polar.
- [ ] **Step 5:** Commit.

### Task 10: `orders-fastapi` end to end, docs, measured

**Files:**
- Modify:
  - `tests/e2e/test_orders_fastapi.py`;
  - `docs/COVERAGE.md` (FastAPI and Pydantic rows, §3a versions);
  - `docs/coverage/python.md`;
  - `CHANGELOG.md`;
  - `docs/research/2026-11-06-python-performance.md`;
  - `docs/open-issues.md` (the logged items).
- Test: `test_sextant_matches_fastapi_on_the_fixture`, `test_every_fixture_row_is_pinned`.

- [ ] **Step 1: Failing tests:**
  - Sextant's `endpoints` for the fixture equal the Task 1 oracle on (method, path, handler,
    response model).
  - Its inbound `endpoint_metadata` equals the oracle's parameters (kind, name, required).
  - The request and response shapes of `OrderIn` and `OrderOut` list the exact wire names.
  - The recipe roots and the bound receiver of `orders.create` are as expected.
  - Every Sextant row of the fixture appears in the pinned list. An extra row fails.
  - The guard `tests/application/test_one_reason_list.py` covers these rows.
- [ ] **Step 2:** Run; expect PASS once Tasks 2–9 are in.
- [ ] **Step 3:** Run polar, dispatch and mealie. Record their route counts against
  `fastapi_rules.py`'s `app.routes` count (information for plan 3's pins), and cold and warm
  times against the budget.
- [ ] **Step 4:** Docs and logged items. Run the full gate and the field pins.
- [ ] **Step 5:** Commit.

## What plan 3 needs from this plan

- **`parameter_markers` and the unfilled-argument rule (Task 4).** A client handed in by
  `Depends`, and an outbound call's defaulted `timeout`/`base_url`.
- **`names_recipe` and the recipe hop (Task 8).** `httpx.AsyncClient` provided by a dependency.
  Its base address comes through the recipe's returns.
- **PEP 526 instance fields and their class-body values (Task 3).** pydantic-settings
  `BaseSettings` field defaults (§3d rung 3).
- **`pydantic.yml` (Task 9).** `json=`/`.model_dump()` bodies are described by it.
- **OI-341.** `client_base` keys an options object by an `<init>`'s receiver
  (`client_base.py:982`). Plan 3 fixes it if `httpx.Client` is ever built through a class
  object.
- **The fixture.** Plan 3 adds `app/clients.py` (f-string outbound URLs) and `app/settings.py`
  (`env_file`) to `fixtures/orders-fastapi`, and extends Task 10's pinned list.
