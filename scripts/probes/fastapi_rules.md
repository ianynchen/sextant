# FastAPI's rules, quoted from its source (plan 2, Task 0)

Every rule the FastAPI reader mirrors (DR-6) is quoted here from FastAPI's own source, with
`file:function` and line numbers. `fastapi_rules.py` runs the same rules inside FastAPI and prints
its answer; `fastapi_shapes.py` counts the shapes in four corpora.

**Version scope.** FastAPI **0.162.0**, **0.141.1** and **0.115.12**, each as the running
process reported it through `fastapi.__version__`. Every verdict below holds for those three and
for no other version. pydantic is 2.14.3 in all three runs; Starlette is 1.10.0 (0.162.0 and
0.141.1) and 0.46.2 (0.115.12).

**Versions.**

| Version | Role | How it was run |
|---|---|---|
| 0.162.0 (Starlette 1.10.0, pydantic 2.14.3) | newest; lazy include | its own throwaway environment, offline from the uv cache |
| 0.141.1 | first version of the lazy include that the plan names | the cached package on `PYTHONPATH`, over the 0.162.0 environment's Starlette and pydantic (the cache holds only its unpacked files, not an installable wheel) |
| 0.115.12 (Starlette 0.46.2, pydantic 2.14.3) | dispatch's pin; eager include | its own throwaway environment, fetched once |

The environments are in
`/private/tmp/claude-501/-Users-yining-programming-ai-sextant/b41977ee-16aa-4b60-bc7d-9fd84edb2c95/scratchpad/fastapi-probe/`.
Nothing was installed in the repository's `.venv`.

**How to read this file.** "Probe" lines are the output of `fastapi_rules.py`. Where 0.162.0 and
0.141.1 gave the same answer, one line is shown. They differ from each other nowhere. Of 111
compared output values, 0.115.12 differs from 0.162.0 in the places marked **0.115.12** below,
and nowhere else.

Paths are relative to `fastapi/` (FastAPI) or `starlette/`. "R" means 0.162.0 line, "E" means
0.115.12 line.

## Observations

Verbatim from the table that `fastapi_rules.py --table` generated from the JSON of three runs of
`scripts/probes/fastapi_rules.py`. Each column header is the version that run's own
`fastapi.__version__` printed, not the version the environment was asked to install: the
0.141.1 column is a different package (the cached files on `PYTHONPATH`), and its `loaded from`
line below shows the path the process imported. The table lists the rules that differ between
versions, or that the plan relies on most; the sections after it quote the source for all rules.

| Rule | 0.162.0 | 0.141.1 | 0.115.12 |
|---|---|---|---|
| route added to a router after it was included | served | served | not served |
| a router included in itself | raises | raises | accepted |
| `methods=[]` | raises | raises | raises |
| `Annotated[Request, Depends(f)]` | accepted | accepted | raises |
| `x: Optional[int]` with no default | required | required | required |
| unmarked `x: list[int]` is a | body | body | body |
| `Annotated[int, Query(alias="first"), Query(alias="second")]` alias | second | second | second |
| `user_agent: str = Header()` wire name | user-agent | user-agent | user-agent |
| `response_model` for `-> None` | None | None | <class 'NoneType'> |

- 0.162.0: `fastapi.__version__` printed 0.162.0, starlette 1.10.0, pydantic 2.14.3, Python 3.12.13; loaded from `/private/tmp/claude-501/-Users-yining-programming-ai-sextant/b41977ee-16aa-4b60-bc7d-9fd84edb2c95/scratchpad/fastapi-probe/v0.162.0/lib/python3.12/site-packages/fastapi`
- 0.141.1: `fastapi.__version__` printed 0.141.1, starlette 1.10.0, pydantic 2.14.3, Python 3.12.13; loaded from `/Users/yining/.cache/uv/archive-v0/eaXNlJFXNTKdmKA0/fastapi`
- 0.115.12: `fastapi.__version__` printed 0.115.12, starlette 0.46.2, pydantic 2.14.3, Python 3.12.13; loaded from `/private/tmp/claude-501/-Users-yining-programming-ai-sextant/b41977ee-16aa-4b60-bc7d-9fd84edb2c95/scratchpad/fastapi-probe/v0.115.12/lib/python3.12/site-packages/fastapi`

---

## 1. Prefix composition

A route's path is its router's prefix plus the path written on the route. An include adds the
parent's prefix plus the include's prefix in front of the route's path.

- `routing.py:APIRouter.add_api_route` (R 3045, E 934):
  `self.prefix + path,`
- `routing.py:_RouterIncludeContext.for_include` (R 1375):
  `prefix=parent_router.prefix + prefix,`
- `routing.py:_RouterIncludeContext.path_for` (R 1418-1419):
  `return self.prefix + route.path`
- `routing.py:APIRouter.include_router` (E 1303):
  `prefix + route.path,` handed to `self.add_api_route`, which adds `self.prefix` (E 934).

So for a route reached through nested includes, the path is: the outermost parent's own prefix,
then each include's `prefix=`, then each router's constructor `prefix=` on the way down, then the
route's path. The router's own prefix is already part of the path of every route registered on it
(it is added at `add_api_route`), so an include does not add it again.

Probe (`composition`): `inner = APIRouter(prefix="/inner")` with routes `/leaf` and `""`;
`middle = APIRouter(prefix="/middle")` includes `inner` with `prefix="/a"`; the app includes
`middle` with `prefix="/b"`. Served paths: `/b/middle/a/inner/leaf` and `/b/middle/a/inner`. The
same router included twice (once plain, once with `prefix="/twice"`) serves both `/p` and
`/twice/p`. All three versions agree.

## 2. `include_router` assertions, and what the router constructor refuses

- `routing.py:APIRouter.include_router` (R 3382-3385, E 1258-1261):
  ```python
  if prefix:
      assert prefix.startswith("/"), "A path prefix must start with '/'"
      assert not prefix.endswith("/"), (
          "A path prefix must not end with '/', as the routes will start with '/'"
      )
  else:
      for route, route_context in _iter_routes_with_context(
          router.routes
      ):  # E: for r in router.routes:
          ...
          if path is not None and not path:
              raise FastAPIError(f"Prefix and path cannot be both empty (path operation: {name})")
  ```
  (R 3399, E 1268 for the `raise`.) Only an empty include prefix triggers the empty-path check.
  The check looks at the included router's route paths, which already carry that router's own
  prefix. So `APIRouter(prefix="/r")` with a route `""`, included with no prefix, is accepted.
- `routing.py:APIRouter.__init__` (R 2611-2612): the same two prefix assertions run on the
  constructor's `prefix`.
- 0.141+ also asserts (R 3373-3380): a router cannot be included in itself, and cannot include a
  router that already includes it (`_contains_router`).

Probe (`include_assertions`), all registrations done at import time, so the app does not start:

| Written | Result |
|---|---|
| include `prefix="a"` | `AssertionError: A path prefix must start with '/'` |
| include `prefix="/a/"` | `AssertionError: A path prefix must not end with '/'...` |
| include `prefix="/"` | the same trailing-slash assertion (a lone `/` is refused) |
| include `prefix=""`, route path `""`, no router prefix | `FastAPIError: Prefix and path cannot be both empty (path operation: endpoint)` |
| include `prefix=""`, route path `""`, `APIRouter(prefix="/r")` | accepted; serves `/r` |
| include `prefix="/a"`, route path `""` | accepted; serves `/a` |
| `APIRouter(prefix="/r/")` | `AssertionError` (trailing slash) |
| `APIRouter(prefix="r")` | `AssertionError` (leading slash) |
| route path `"x"` (no leading slash), no prefix | **accepted**; served path is `x` |
| route path `"x"`, `APIRouter(prefix="/r")` | **accepted**; served path is `/rx` |
| include a router in itself, or a cycle | **0.162.0, 0.141.1:** `AssertionError`. **0.115.12:** no assertion |

FastAPI does not check a route's own path for a leading slash. Only prefixes are checked.

### `Mount.__init__`

- `starlette/routing.py:Mount.__init__` (R 383-385, E 381-383):
  ```python
  assert path == "" or path.startswith("/"), "Routed paths must start with '/'"
  assert app is not None or routes is not None, "Either 'app=...', or 'routes=' must be specified"
  self.path = path.rstrip("/")
  ```

Probe (`mounts`): `Mount("/x/").path == "/x"`, `Mount("/").path == ""`, `Mount("").path == ""`,
`Mount("/x//").path == "/x"` (`rstrip` strips every trailing slash), `Mount("x")` raises, a mount
with neither `app` nor `routes` raises.

## 3. `methods`: default, case, and HEAD

- `routing.py:_populate_api_route_state` (R 1072-1074; `APIRoute.__init__` in E 492-494):
  ```python
  if methods is None:
      methods = ["GET"]
  route.methods = {method.upper() for method in methods}
  ```
  The default applies only when `methods` is `None`. It is not `methods or ["GET"]`.
- `utils.py:generate_unique_id` (R 98): `assert route.methods`. An empty list gives an empty set,
  and this assertion then stops the registration.
- `starlette/routing.py:Route.__init__` (R 246-247, E 245-246): `if "GET" in self.methods:
  self.methods.add("HEAD")`. This is Starlette's `Route` only. FastAPI's `APIRoute` does not call
  it.

Probe (`methods_and_head`; all three versions agree):

| Written | Methods |
|---|---|
| `@app.get(...)`, `@app.post(...)` | `GET`; `POST` |
| `add_api_route(path, f)` and `@app.api_route(path)` | `GET` |
| `methods=["get", "Post"]` | `GET`, `POST` (upper-cased) |
| `methods={"put", "DELETE"}` | `DELETE`, `PUT` |
| `methods=["GET", "HEAD"]` | `GET`, `HEAD` (HEAD only when written) |
| `methods=[]` | **the registration fails**: `AssertionError` with an empty message |
| `app.add_route(path, f)` (a Starlette route) | `GET`, `HEAD` |

A real request: `HEAD /get` on a FastAPI `@app.get` route answers 405. `HEAD` on a Starlette
route answers 200.

## 4. `analyze_param`

`dependencies/utils.py:analyze_param` (R 409-592, E 348-540). The rules below are listed with the
line of the statement that makes them. Both versions have them unless a line says otherwise.

**Markers and the last-wins rule** (R 436-460, E 366-390):
```python
fastapi_annotations = [
    arg for arg in annotated_args[1:] if isinstance(arg, (FieldInfo, params.Depends))
]
fastapi_specific_annotations = [
    arg
    for arg in fastapi_annotations
    if isinstance(arg, (params.Param, params.Body, params.Depends))
]
if fastapi_specific_annotations:
    fastapi_annotation = fastapi_specific_annotations[-1]
```
Only `Param` (`Query`, `Path`, `Header`, `Cookie`), `Body` (`Body`, `Form`, `File`) and `Depends`
(`Security`) count. A plain `pydantic.Field(...)` in `Annotated` is a `FieldInfo` but not one of
the three, so it is not the winner. The last of the three wins, whatever its kind.

Probe: `Annotated[int, Query(alias="first"), Query(alias="second")]` → alias `second`.
`Annotated[int, Query(), Body()]` → body. `Annotated[int, Body(), Header()]` → header.
`Annotated[int, Depends(a), Query()]` → a query parameter, no dependency.
`Annotated[int, Query(), Depends(a)]` → the dependency. A non-marker after the marker
(`"note"`) does not change the winner.

**A marker in `Annotated` takes the parameter's own default** (R 462-475, E 392-402): the marker's
default must be unset, and then `field_info.default = value` (the `=` default) or `RequiredParam`.
So `x: Annotated[int, Query()] = 4` is optional, with default 4.

**Error assertions** (each is an `AssertionError` at registration; R lines, E same text):

| Text | R line | Probe case |
|---|---|---|
| `` `Query` default value cannot be set in `Annotated` for 'x'. Set the default value with `=` instead. `` | 464 | `Annotated[int, Query(5)]` raises. `Annotated[int, Query(...)]` does not (`...` is `RequiredParam`) and is required. |
| `Path parameters cannot have default values` | 468 | path variable, `Annotated[int, Path()] = 5` raises. An unmarked `x: int = 5` on a path variable does not raise, and is required. |
| ``Cannot specify `Depends` in `Annotated` and default value together for 'x'`` | 478 | raises |
| ``Cannot specify a FastAPI annotation in `Annotated` and `Depends` as a default value together`` | 482 | (not probed; same family) |
| ``Cannot specify FastAPI annotations in `Annotated` and default value together for 'x'`` | 489 | `Annotated[int, Query()] = Query()` raises |
| ``Cannot use `Query` for path param 'x'`` | 553 | a path variable marked `Query()` raises |
| ``Cannot specify FastAPI annotation for type <Request>`` | 517 | `request: Request = Query()` raises |
| ``Cannot specify `Depends` for type`` | **E 441 only** | **0.115.12:** `Annotated[Request, Depends(f)]` raises. **0.162.0:** it is accepted, and the dependency wins (R 505: `if depends is None and lenient_issubclass(...)`; E 429 has no such test). |

**Unmarked parameter classification** (R 520-548, E 446-472), in this order:
```python
if is_path_param:
    field_info = params.Path(...)
elif is_uploadfile_or_nonable_uploadfile_annotation(type_annotation) or ...:
    field_info = params.File(..., default=default_value)
elif not field_annotation_is_scalar(annotation=type_annotation):
    field_info = params.Body(..., default=default_value)
else:
    field_info = params.Query(..., default=default_value)
```
`default_value = value if value is not inspect.Signature.empty else RequiredParam`
(R 521, E 447). The special types are tested before this (R 502-518, E 429-446): a parameter
typed `Request`, `WebSocket`, `HTTPConnection`, `Response`, `BackgroundTasks` or `SecurityScopes`
(`lenient_issubclass`, so subclasses count) is no request parameter at all.

Probe (all versions agree):

| Written | FastAPI's answer |
|---|---|
| `x: int` | query, required |
| `x: int = 3` | query, optional |
| `x: Optional[int]` (no default) | query, **required** |
| `x: Optional[int] = None` | query, optional |
| `x: list[int]`, `x: list[int] = [1]`, `x: dict[str, int]`, `x: Item` | **body** (required; optional with a default) |
| `x: list[int] = Query()` | query, required |
| `x: UploadFile` | body (a `File`) |
| `a: Item, b: Other` | two body fields |
| `x: int` on a path with `{x}` | path, required |
| `x: int = Query(...)`, `Query()`, `Annotated[int, Query()]` | query, required |
| `x: int = Query(None)`, `Query(5)`, `Query(default_factory=...)` | query, optional |
| `request: Request`, `response: Response`, `tasks: BackgroundTasks` | no request parameter |

`Query()` with no argument writes a default expression but is required: the default is unset.

**`convert_underscores`** (R 582-585, E 484-487):
```python
if not field_info.alias and getattr(field_info, "convert_underscores", None):
    alias = param_name.replace("_", "-")
else:
    alias = field_info.alias or param_name
```
Only `Header` has `convert_underscores`, default `True`. Probe: `user_agent: str = Header()` →
wire name `user-agent`. `Header(convert_underscores=False)` → `user_agent`. `Header(alias="x_ua")` →
`x_ua` (a written alias is used as written). The same in `Annotated`. A `Query` name is never
changed.

**`Depends()` with no argument** (R 497-501, E 425-427): `depends.dependency = type_annotation`.
Probe: `x: Item = Depends()` is the dependency `Item` (its `__init__` parameters are the request
parameters).

**Aliases and `type` statements** (R 413-416 only): `if is_typealiastype(annotation): annotation =
annotation.__value__`. A PEP 695 `type X = Annotated[...]` is unpacked in 0.162.0. In 0.115.12 it
is not (and Python 3.12 is the oldest it meets this syntax).

## 5. `_build_dependant_with_parameterless_dependencies`

- `routing.py:_build_dependant_with_parameterless_dependencies` (R 908-925):
  ```python
  dependant = get_dependant(path=path, call=call, scope="function")
  for depends in dependencies[::-1]:
      dependant.dependencies.insert(0, get_parameterless_sub_dependant(depends=depends, path=path))
  ```
  0.115.12 has the same loop inline in `APIRoute.__init__` (E 406-408) and does not wrap it in a
  function.
- The route's `dependencies` are the list the route was built with. At `add_api_route` it is the
  router's own list followed by the route's list (E 924-927, 1033-1035:
  `current_dependencies = self.dependencies.copy()`, then `.extend(dependencies)`).
  At include time: `[*parent_router.dependencies, *(dependencies or [])]` (R 1377) in 0.162.0 and
  0.141.1; the include's `dependencies` then `route.dependencies` in E 1286-1290, and the parent's
  own list in front of both at `add_api_route` (E 1033).
- Each such dependency's own parameters join the route's parameters. They are inserted in front
  of the handler's own dependencies, so they run first.

Probe (`dependencies_join`): `FastAPI(dependencies=[Depends(dep_app)])`, a parent router with
`dependencies=[dep_parent_router]`, a child router with `dependencies=[dep_router]`, a route with
`dependencies=[dep_route]`, the child included in the parent with `dependencies=[dep_include]`,
the parent included in the app. FastAPI's OpenAPI lists the route's parameters in this order:
`own_q, app_q, parent_q, include_q, router_q, route_q`. (The order of a document is not a run
order. The set is what matters: all six dependencies' parameters reach the route.) 0.115.12 gave
the same six parameters in the same order, read from `route.dependant`; its dependency list is
`dep_app, dep_parent_router, dep_include, dep_router, dep_route`.

## 6. The `response_model` placeholder rule

- `routing.py:_populate_api_route_state` (R 1134-1155; `APIRoute.__init__` E 465-470):
  ```python
  if isinstance(response_model, DefaultPlaceholder):
      return_annotation = get_typed_return_annotation(endpoint)
      if lenient_issubclass(return_annotation, Response):
          response_model = None
      else:
          stream_item = get_stream_item_type(return_annotation)          # 0.162.0 only
          if stream_item is not None and is_generator: ... response_model = None
          else:
              response_model = return_annotation
  route.response_model = response_model
  ```
  The default of `response_model` is a `DefaultPlaceholder` (the "not written" marker). If it
  is written, the value is used as written and the return annotation is not looked at.

Probe (`response_models`; all versions agree except the one marked):

| Written | `route.response_model` |
|---|---|
| no annotation, no `response_model` | `None` |
| `-> Item` | `Item` |
| `-> list[Item]`, `-> Optional[Item]`, `-> dict[str, int]`, `-> Any` | the annotation |
| `-> Response`, `-> JSONResponse` | `None` |
| `-> Item \| Response` | **registration fails** (`FastAPIError: Invalid args for response field!`) |
| `-> None` | `None` in 0.162.0 and 0.141.1; **`NoneType` in 0.115.12** |
| `-> Item` and `response_model=Other` | `Other` |
| `-> Item` and `response_model=None` | `None` |
| `-> JSONResponse` and `response_model=Other` | `Other` (a written model is used even over a `Response` annotation) |
| no annotation and `response_model=Item` | `Item` |

0.162.0 also turns a generator's `-> Iterator[Item]` or `AsyncIterator[Item]` into a stream item
type (`response_model = None`) when the route is a generator (R 1139-1153). 0.115.12 has no such
rule. No corpus route needs it (plan N9 does not mention it; logged in the report).

## 7. `get_typed_signature` and `__wrapped__`

- `dependencies/utils.py:get_typed_signature` (R 242-256, E 231-244). E:
  `signature = inspect.signature(call)` and `globalns = getattr(call, "__globals__", {})`. R:
  `signature = _get_signature(call)` (R 227-239: `inspect.signature(call, eval_str=True)`) and
  `unwrapped = inspect.unwrap(call)`, `globalns = getattr(unwrapped, "__globals__", {})`.
- `inspect.signature` follows `__wrapped__` by default, so FastAPI reads the signature of the
  innermost wrapped function.
- `get_dependant` also unwraps the dependency's call (R 270, `inspect.unwrap`).

Probe (`wrapped`): `@functools.wraps(target) def wrapper(*args, **kwargs)` → FastAPI reads
`target`'s parameters (`q` query, `h` header) in all three versions. A wrapper with no
`functools.wraps` → FastAPI reads `args` and `kwargs` as two required query parameters. A string
annotation (`'Qt'`) on the wrapped function resolved to an `int` query in all three versions in
this probe, so the wrapper-versus-wrapped globals difference did not show.

## 8. Lazy versus eager include

- 0.162.0 and 0.141.1: `include_router` appends one `_IncludedRouter(original_router=router,
  include_context=...)` to `self.routes` (R 3414-3417) and then calls `_mark_routes_changed()`.
  The included router's routes are read when a request, or the OpenAPI document, asks for them.
- 0.115.12: `include_router` loops over `router.routes` and calls `self.add_api_route(prefix +
  route.path, ...)` once per route (E 1275-1355). Routes added to the router afterwards are not
  copied.

Probe (`lazy_versus_eager`): a router included in the app, then given a route; an inner router
included in an outer one, the outer in the app, then the inner given a route.

| | route added after the include | route added to a nested inner router after both includes |
|---|---|---|
| 0.162.0, 0.141.1 | served (`/late/after`) | served (`/out/in/after_nested`) |
| 0.115.12 | **not served** | **not served** |

## 9. Corpus shapes, against the numbers the plan quotes

`python -I scripts/probes/fastapi_shapes.py` over the four roots (all counts are syntactic and
are from files outside tests unless "all files" is named). Roots: polar `server/`, dispatch (the
repository), mealie `mealie/`, the full-stack template `backend/`.

| What the plan quotes | Plan says | Measured |
|---|---|---|
| N1: `Depends(<call result>)` in aliases, polar | 69 | **69** (70 with tests) |
| N1: same, mealie | 12 | mealie has no such alias; 13 `Depends(<call>)` anywhere |
| N2: `Annotated` aliases, polar | 179 | **179** (150 hold a `Depends`, 29 hold a `Query`/`Header`/... marker; 355 module-level `Annotated` aliases in all, so 179 is the ones that hold a FastAPI marker) |
| N2: parameters typed by an alias, dispatch | 712 | **582** (parameters of any function annotated with one of the 9 alias names); 556 of them on route handlers |
| N6: `dependencies=` on routes, dispatch | 101 | **101** |
| N6: same, mealie | 61 | **61** |
| N6: `include_router` / `APIRouter` / `FastAPI` | 2 / 1 / 1 | dispatch: **2 / 1 / 0**; polar: 0 / 0 / 1 (plus 3 on route decorators) |
| N8: `methods=`, polar | 66 | **66** on `api_route`, plus 1 `add_api_route` |
| N9: return annotation only, polar | 205 | **204** outside tests (235 in all files) |
| N9: neither written, dispatch | 35 | **35** |
| N9: neither written, mealie | 52 | **52** |
| N4: several body parameters, polar | 1 | **1** (a name-closure estimate: model-typed or `Body`/`Form`/`File`) |
| N4: several body parameters, mealie | 6 (multipart) | **6**, all with a `Form` or `File` marker |
| N13: `validation_alias`, polar | 90 | **90** (71 `AliasChoices`, 24 `AliasPath`) |
| N13: `populate_by_name` | mealie, dispatch | **mealie 1, dispatch 1** |

Other counts the later tasks may want (outside tests): polar `serialization_alias` 2, `Field(alias=)`
2; dispatch `Field(alias=)` 12; mealie `Field(alias=)` 5, `alias_generator` 2, `Mount` 1, `Mount`
or `.mount(` calls: polar 2, dispatch 3; pydantic v1 `class Config`: polar 1; `UpdatedAtField`
(a mealie wrapper around `Field` that sets `validation_alias`, `serialization_alias` and
`alias_priority=2`): 9 uses.
