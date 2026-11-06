# First-principles review — `docs/superpowers/specs/2026-11-06-python-reader-design.md`

Reviewer: read-only, 2026-11-06. Every number below was measured on the clones in
`examples/py-*` (or on Sextant's own tree) during this review; probe scripts are in this
scratchpad (`instance_recv.py`, `modlevel.py`, `dupdefs.py`, `parse_time.py`).

## 0. What the goal actually requires

Goal: the same architecture Sextant extracts from JVM code, so Python services stitch. The
stitcher (M06) matches on protocol, wire identity (path template / topic / RPC name) and
payload structure, per environment. So the minimum a Python reader must produce is:

1. **Inbound rows** with method + path *template* (prefixes joined) and handler.
2. **Outbound rows** with method + address *template*, the address followed to config.
3. **Payload shapes with WIRE names** (not Python attribute names) on both.
4. **Call edges** good enough for the trace from handler to outbound call.
5. The CFG positions the value walk needs so addresses are per-path rather than `partial`.

What the JVM got from javac for free and Python must replace: (a) a resolved call target
(owner + name) for each call; (b) intra-procedural value flow (ASM frames: receiver/result
ids, merges). Everything *inter*-procedural — returns, parameters from callers, field
writes, per path — is already done, language-free, by `application/resolve/values.py`.

So the minimum new machinery is: a name resolver (imports, scopes, import roots), the
written-type reading javac would do (rule 1, including the typing forms real code uses),
intra-procedural flow + CFG fields, catalog data, and nothing that re-implements the walk.
The design's biggest deviation is building rules 2–4 a second time, inside the scanner.

---

## Findings (ranked)

### C1 — Critical — §6 "Where it runs" + rules 2–4: inter-procedural inference in the scanner duplicates the value walk and breaks its per-path rule

**What is wrong.** Rules 2 (returns from bodies, "repeated through calls"), 3 (parameter types
from every caller) and 4 (field types from every write) are exactly the three crossings the
resolver's value walk already makes (`values.py`: `return_flows`, `bound_to_parameter`,
`written_by`/`field_writes`), with the same `cycle`/`external`/`escapes`/`no_writer`
vocabulary — the design even says rule 3 answers "as the value walk answers today". Putting
them in the scanner:

- **Contradicts M03's contract**: "No cross-file reasoning. A fact is about one document.
  Joining is downstream." and "No derivation" (M03 §What it must not do). Rule 3 needs every
  caller in the module *and sibling modules*; rule 4 needs writes "from any code in those
  modules". A file's facts would depend on other files' bodies.
- **Contradicts ruling M-1** (values.py header: "The unit of resolution is the PATH, not the
  position … a per-position memo is precisely what discards the correlation and mints the
  fabrication back"). Rule 3 as written is per position: "Several types give a closed list."
  For `def _send(client, url): client.post(url)` called as `_send(httpx_client, A)` and
  `_send(requests_session, B)`, the scanner writes `client.post` with targets {httpx, requests}
  per position; the resolver then derives rows per catalog target and walks `url` per path,
  giving `httpx → A, httpx → B, requests → A, requests → B` — two rows no code produces, at
  `resolved`. That is the lie the owner ranks worse than unknown.
- **Two implementations of one semantics** that will drift (the "removing the cause beats
  detecting it" and "one rule" rulings).

**The design's own justification** — "M03 is the only module that knows a language exists" —
covers rule 1 only. Rules 2–4 are language-neutral; nothing Python-specific happens in
"follow the return", "follow the caller", "follow the field write".

**Alternative.** Split along the line javac/ASM already draws for the JVM:
- *Scanner*: name resolution, rule 1 (written types + library signatures), and
  **intra-procedural** flow (locals, receiver/result/merge ids, module-level bindings).
  Where that names a receiver type, write the target as the JVM does (`Owner#name().`,
  dispatch finds the declaring class). Where it does not, write the call with its receiver
  value id and the attribute name and no owner.
- *Resolver*: one new pass binds owner-less sites by running the existing walk's
  `producers_of` on the receiver (a constructor call or a typed callee's return gives the
  type), per path, then re-derives `call_edges`; iterate until no site changes (the chain
  depth bounds it — measure it). Rules 2–4 then cost nothing new and inherit M-1, the reason
  vocabulary and the guard test.
- If the owner rejects this, at minimum rule 3/4's answers must be stored per path
  (caller-keyed), never as a per-position closed list.

### C2 — Critical — §8c/§7 Pydantic shapes: wire names are not modelled, so shapes would publish Python attribute names as wire names

**What is wrong.** §8c says "Pydantic shapes" and §9 pins mealie, but the design never says how
a field's wire name is decided. FastAPI serialises responses `by_alias=True` and validates by
alias. Measured: mealie's base model `mealie/schema/_mealie/mealie_model.py:53` sets
`model_config = ConfigDict(alias_generator=camelize, populate_by_name=True)` — every mealie
schema is camelCase on the wire. `Field(alias=…)`: polar 127, mealie 129, dispatch 26;
`validation_alias/serialization_alias`: polar 93. Built as written, every mealie shape is
`resolved` with snake_case names that never appear on the wire, and step 3 of the stitcher
compares the wrong names.

**Alternative.** State the wire-name rule in §8c as catalog data (Pydantic's own rules: alias,
serialization vs validation alias, `alias_generator`, `by_alias` on the route). A library
generator (`pydantic.alias_generators.to_camel`) is catalog-known; a project function
(`camelize`) is code we can follow only if it is a literal mapping — otherwise the field's wire
name is `unresolved` (`not_readable`, detail naming the generator), never the attribute name.
Add an alias generator to the fixture.

### M1 — Major — §3 goal 1 / §6 rule 1: "our own type inference" re-implements a type checker for the part a type checker already does exactly

**What is wrong.** For the first release (FastAPI), the projects are almost fully typed
(params typed: polar 99%, zulip 99%, mealie 88%, dispatch 82%; returns typed: polar 99%,
mealie 62%, dispatch 36%). The decisive rule is rule 1, and rule 1 as listed — typeshed,
`Optional`, unions, generics, `TypeVar`, `Protocol`, `Self` — *is* a type checker's core,
and it is understated: typeshed's stdlib alone has **2,540 `@overload`s** (subprocess.pyi 36,
os 31, builtins 254); `subprocess.run`, `dict.get`, `os.environ.get` return types are chosen
by overload resolution. The design never mentions overloads (and §6 says "Python has no
overloads"), `ParamSpec`, `type[X]`, descriptors/`property`, metaclasses or
`dataclass_transform` (how Pydantic models get their constructor signature). Hand-written
overload/generic solving is the most likely place to emit a confidently wrong type. The
options comparison the spec cites ("ruled option 1") is not recorded anywhere in `docs/`.

**Alternative.** Record a DR-1-style decision with the options weighed. The option not visible
in the spec: **mypy as a library, in-process** (pure Python, MIT, already in Sextant's dev
environment at 2.3.1 with typeshed bundled; it parses, never imports or runs the scanned
code, and answers overloads, generics, `type[X]`, `dataclass_transform`). Use only its
types at receivers, treat `Any` as unknown, never load plugins from the scanned
environment (that would run its code), and keep rules 2–4 in the walk (C1). If the ruling
stands, the plan must at least list overload resolution, `type[X]`, `ParamSpec`, `property`
and `dataclass_transform` in rule 1 and size them.

### M2 — Major — §6 rules 1–4: module-level bindings are not covered by any rule, yet routers, apps, clients and service singletons live there

**What is wrong.** Rule 4 covers `self.x` and class-level assignments; nothing covers a module
global such as `order = OrderService()` (polar `order/service.py`, last line) imported
elsewhere as `from polar.order.service import order as order_service`. Measured: calls on an
imported, unannotated module-level instance — polar **878**, redash 176, dispatch 164, CTFd
119. These are the handler→service hops every polar trace runs through. Module-level
`APIRouter(`/`FastAPI(`/`httpx.Client(`/`Blueprint(` assignments: polar 86, mealie 63,
dispatch 56 — the receivers of every route decorator. The §2 probe hides this: it labels a
call on any imported name "only the name".

**Alternative.** Treat a module global as a binding with writers (the same `field_write`
shape, module scope as owner) so the walk answers it per path; §7's module-scope symbol
(`__module__().`) already gives the writes an owner.

### M3 — Major — §7 decorators "as `annotation` uses": the wrong mapping for receiver-mounted routing

**What is wrong.** `@router.get("/x")` is not an annotation type; it is a call on an object,
`h = router.get("/x")(h)`. Recording it as an annotation with "the decorator's resolved
symbol" (`APIRouter#get().`) keeps the literal path but loses *which router*, and FastAPI's
prefix is a property of the router object (`APIRouter(prefix=…)`, then
`include_router(router, prefix=…)`, nested — polar `api.py:74–89`). click has the same shape:
`sextant module analyze` exists only because `module` is the *result* of `@cli.group()`
applied to `def module` (`src/sextant/cli/app.py:27,62`). An annotation fact cannot express
either chain. The existing Vert.x catalog already models exactly this ("A router is the
OBJECT a producer made, reached along one call path", `vertx-web.yml` `router_type`/`mount`).

**Alternative.** Desugar each decorator into the call sites Python executes (decorator
expression → result id → call with the function as a `lambda`-kind argument → result bound
to the name), and write FastAPI/Flask/click as `fluent`/mount catalogs over receiver ids,
reusing the Vert.x mount machinery. Keep an annotation-style record only for decorators that
are plain names with no receiver, if any catalog needs it.

### M4 — Major — §5 module finding: the rule does not do what it claims, and file presence is a convention M02 forbids

**What is wrong.**
- The `setup.py` limit fixes nothing it cites: `CTFd/forms/setup.py` has no `pyproject.toml`
  or `setup.cfg` beside it, so it still marks a module. Measured false modules of this
  kind: `py-CTFd/CTFd/forms`, `py-CTFd/CTFd/constants`, `py-redash/redash/handlers`,
  `py-polar/server/polar/organization_review/collectors` — every one sits inside a package
  (`__init__.py` beside it).
- `setup.cfg` is not a project file by itself: CTFd's holds only `[nosetests]`. A
  tool-only `pyproject.toml` (`[tool.ruff]` alone) is common too.
- A uv workspace root (`py-full-stack-fastapi-template/pyproject.toml`: no `[project]`,
  `[tool.uv.workspace] members = ["backend"]`) becomes a module whose `.py` files are
  `backend`'s — two overlapping modules, double rows.
- `py-polar/sdk/generator/python/template` (a Jinja template project) is nested in
  `sdk/generator`; no ownership rule for nested modules is stated.
- M02: "Discovery reads the build, never a convention" — the claim "this is the rule Java and
  Kotlin already use" is not true; they read `<modules>`/`include`.

**Alternative.** A folder is a Python module when its `pyproject.toml` has `[project]` or
`[tool.poetry]`, or its `setup.cfg` has `[metadata] name`, or its `setup.py` calls
`setup(` — and never when the folder is inside a package (`__init__.py` beside it). A
workspace manifest (`[tool.uv.workspace] members`, Poetry/Hatch equivalents) lists modules
and is not one. A `.py` file belongs to the nearest enclosing module. `requirements*.txt`
alone stays a marker only for the no-`pyproject` case (microservices-demo), with the
nearest-module rule.

### M5 — Major — §5/§6: import roots are never decided, and every cross-file name depends on them

**What is wrong.** 54–69% of calls need "only the name" (§2), and every one of them crossing
files needs `from polar.order.service import …` mapped to a file. That needs the import root:
dispatch is src-layout (`[tool.hatch…] packages = ["src/dispatch"]`), polar's server has no
build system at all (root is `server/`, the working directory at run time), zulip edits
`sys.path` in 15 non-test files. The design's descriptor example
(`app/api/routes/items/create_item().`) does not say whether the namespace is the file path or
the import path; they differ for every src-layout project.

**Alternative.** Import roots from the build backend's package declaration (hatch `packages`,
setuptools `package-dir`/`packages.find where`, poetry `packages`), else from an installed
environment's editable-install `.pth`/`direct_url.json`, else the module folder, with the
choice recorded. Descriptors use the import path.

### M6 — Major — §5 identity + §5 libraries: a library name has two identities (re-export vs definition), so catalogs and cross-module joins split

**What is wrong.** `from fastapi import APIRouter` names a class defined in
`fastapi.routing`; `requests.get` is defined in `requests.api`; `httpx.get` in `httpx._api`.
With the library installed the scanner can follow the re-export to the definition; without it
(no clone has a `.venv`) it only has the imported spelling. Same call, two symbols, depending on
the machine — against D00 §1 "Two runs produce the same string; two modules seeing the same
library type produce the same string", and catalogs (which match on `owner` text) would need
both spellings. The design says only "catalogs match on the imported name".

**Alternative.** Decide one canonical form: the public import path as written in the catalog
(what code writes), with the scanner recording the definition path as a separate attribute
when it is known; or always the definition path, with the uninstalled case `external`. Either
way the symbol must not depend on whether a venv exists.

### M7 — Major — §6 rule 1: `type[X]` and factory-built classes decide polar's routes

**What is wrong.** 80 of polar's 83 router files import `APIRouter` from `polar.routing`, where
`APIRouter = get_api_router_class(APIRoute)` and
`def get_api_router_class(...) -> type[_APIRouter]` returns a class defined inside the
function (`polar/kit/routing.py:268`). The claim "Routes are still found" when FastAPI is not
installed rests on matching `from fastapi import APIRouter`, which these files do not do. The
routes are found only if rule 1 reads `type[X]` and treats calling a `type[X]` value as
producing an `X`. `type[...]` is not in rule 1's list.

**Alternative.** Add `type[X]` (and class objects as values generally) to rule 1, and put a
polar-shaped router factory in `fixtures/orders-fastapi`.

### M8 — Major — §8d/§7: f-strings and other string building are not mapped to the template argument kind

**What is wrong.** Outbound addresses are the stitching key, and Python builds them with
f-strings. Measured f-string first arguments to `.get/.post/…(`: polar 17, netbox 14, CTFd 6,
saleor 4, mealie 3 (single-line grep, so a floor); f-strings overall: polar 2,295. D00 already
has the JVM's `StringConcatFactory` recipe → template (`/api/{}/orders`). The design does not say
`JoinedStr`, `+`, `%` and `str.format` produce that same argument kind, so these addresses
would be `unresolved` and never match.

**Alternative.** §7: a `JoinedStr` (and `+` of strings, `%`/`.format` with a literal format)
is written as the existing concat-template argument with its parts as value ids. Add one to
the fixture.

### M9 — Major — §8e `.env` files "beside the project file": the code decides which file is read, and a deployment decides where it is

**What is wrong.** pydantic-settings reads only the file named by `env_file`, resolved against
the process's working directory. Measured: the FastAPI template reads `env_file="../.env"`
(`backend/app/core/config.py`), not the file beside its project file; polar picks `.env`,
`.env.test` or `.env.testing` by `POLAR_ENV` at import time (`polar/config.py:75–81`). Reading
"every `.env` beside the project file" as config would publish values the app never loads, at
`resolved`.

**Alternative.** A `.env` is read only where code names it (`env_file=` literal or a value the
walk resolves to an enumerable set, `load_dotenv(path)`); because its location depends on the
working directory and its choice may depend on the environment, its values are repo
evidence under the 2026-10-23 "deployment decides what it can set" ruling, the same standing
as a Spring profile file.

### M10 — Major — §6 "Disambiguator": "Python has no overloads" is false for identity; same-named defs collide in every project

**What is wrong.** Names defined more than once in one scope (`@property`/`@x.setter`,
`@overload`, conditional definitions, redefinition): polar 38 (22 overload, 16 property),
saleor 10, zulip 10, redash 8, netbox 8, dispatch 7, CTFd 4, mealie 3, Sextant 1. With
`name().` and no disambiguator they all mint one symbol — a getter and its setter become the
same method, against D00 §1's uniqueness.

**Alternative.** `@overload` stubs are signatures of the one implementation symbol (not
symbols); property accessors take a content-derived disambiguator from the accessor role
(`x(setter).`); conditional definitions of one name are one symbol whose bodies are a closed
list. State it in §7.

### M11 — Major — §10 performance deferred, against GUIDELINES §8.7

**What is wrong.** §8.7: "A spec or design that adds a read, a pass … states how many times it
runs per resolve and over how many rows". §10 defers it ("measure reads per resolve … before
building"). The design adds a whole-program fixed point (rules 2–4) over project + reached
library bodies, in-process Python. Parsing is not the cost (measured: Sextant's own
site-packages, 4,560 files / 1.19 M lines, `ast.parse` in 2.6 s; polar's `polar/` 210 k lines
in 0.5 s); the fixed point is, and polar's lock has 257 packages.

**Alternative.** Before approval, state the pass count and rows for polar (47,716 call sites in
`polar/` by `ast` count) for whichever split C1 settles on, and the iteration bound.

### M12 — Major — §9 item 3: the OpenAPI oracle does not count what the code serves

**What is wrong.** polar's published OpenAPI (`docs/openapi/2027-01.openapi.json`) has **194
operations** against **608** route decorators: it is filtered by tag for public docs, 44
routes set `include_in_schema=False`, and versions are pruned (`polar/kit/versioning.py`). A
count check against it would fail correctly-read output or push the reader toward the filter.

**Alternative.** The oracle is FastAPI's own `app.routes` listing, produced in the test setup
(which may install and import; the anti-goal binds Sextant only), or a hand-checked sample
where that is not possible.

### M13 — Major — §3/§9 first-release scope: more than the goal needs at once

**What is wrong.** One item carries: the reader, rules 1–4, CFG, library + typeshed reading,
MRO, two new protocol words with stitch-free rows, FastAPI, two HTTP clients, Pydantic,
pydantic-settings, `.env`, three field pins. The "one feature done beats ten half-done" rule
asks for one COVERAGE cell end to end. `process` is not JVM parity (the JVM reader extracts no
`ProcessBuilder` rows) and neither `cli` nor `process` is a stitcher protocol (M06 step 1 lists
http, soap, grpc, kafka, jms, sqs, pubsub), so they do not serve "so Python services can be
stitched".

**Alternative.** Release A: reader + rule 1 + local flow + resolver walk (C1) + CFG fields +
FastAPI + httpx/requests + Pydantic wire names + config, pinned on the fixture and polar/
dispatch/mealie. The ruled `cli` boundary on Sextant can stay as the reader's first test if
the owner wants it, at 6 rows (m1). Defer `process` or ship it for the JVM as well.

---

### m1 — Minor — §9 item 1: Sextant has 6 commands, not 9

`src/sextant/cli/app.py` has 9 decorators: 3 groups (`cli`, `module`, `system`) and 6
commands (`module analyze/render/enrich/export/diff`, `system analyze`). A group a user cannot
run is not an endpoint. Pin 6 rows, or state that groups are rows and why.

### m2 — Minor — §8a: entry points and CLI libraries beyond `[project.scripts]` + click

httpie (`py-cli`) declares its programs in `setup.cfg [options.entry_points] console_scripts`
(`http`, `https`, `httpie`) and uses argparse (23 files); polar's commands are typer (107
files); zulip's are argparse/Django management commands. Read `[tool.poetry.scripts]` and
`console_scripts` too; log argparse/typer with these numbers.

### m3 — Minor — §6 "Written or inferred" marker duplicates `evidence`

D00 §5a: "doubt about what we managed to work out is what `resolution` and `evidence` … are
for, and duplicating them inside the value would let one fact disagree with itself." A written
annotation is `declared`; a type the walk derived is `syntax`. Use the existing field.

### m4 — Minor — §7 keyword arguments: binding to parameters is not stated

Adding the keyword to an argument is not enough: a catalog's `arg0` misses `requests.get(url=…)`
(CTFd `auth.py:587`). Catalogs should address arguments by parameter name, and the binding
(positional/keyword → parameter) needs the callee's signature — from the library, or from the
catalog when the library is not installed.

### m5 — Minor — §2 probe miscounts what it reports

`python_call_kinds.py` counts only calls inside functions (calls outside any function: polar
12.8%, CTFd 15.0%, netbox **57.8%** — model/serializer field declarations), labels calls on
imported instances as "only the name" (M2), and counts annotated locals as "needs another
function's return" (polar 727 calls). Fix before it becomes the §9 item 4 baseline.

### m6 — Minor — §5 identity details

A dynamic version (dispatch, netbox) is stated by the installed project's own
`*.dist-info` when an environment exists — the build tool's report, preferable to `.`.
httpie's name/version live in `setup.cfg [metadata]`, which §5 does not read.

### m7 — Minor — §5 typeshed claim

Flask is not in typeshed (it ships inline types); typeshed's `requests` stubs carry their own
version (`types-requests`), which may not match the project's lock. Record the stub version beside
the library version; prefer stub packages installed in the environment (PEP 561 order).

### m8 — Minor — §5 libraries: bodies of third-party libraries by default vs D04 §2a opt-in

The JVM never walks the dependency tree ("a transitive jar nobody named stays invisible");
library bodies are read only by `extract_libraries` opt-in. Reading signatures of every called
library is the classpath equivalent and fine; running inference inside third-party bodies by
default is a parity break. Use the same opt-in for bodies.

### m9 — Minor — §8b program starts

`asyncio.create_subprocess_exec/shell` and `os.exec*/spawn*` are missing; with `shell=True` the
program name is the shell's parse of a string (pipelines), which should be `not_readable`
beyond the first literal token.

### m10 — Minor — §6 control flow: the scope is smaller than stated, but two Python rules are missing

D00 needs five per-site fields, not region structuring, and an AST is already structured — the
bytecode work M03 describes does not apply. What the design misses: in Python any expression
can raise (attribute, subscript), so exception edges enter a handler from before each
statement, not only calls; and a `with` block's `__exit__` may swallow the exception
(`contextlib.suppress`), so code after a `with` is not dominated by code inside it.

### m11 — Minor — M03 capabilities not declared

The Python scanner must answer `capabilities()`; which of `annotation_args`, `call_site`,
`chain_reconstruction`, `concat_template`, `merge_candidates`, `method_returns`, `control_flow`
it declares decides which catalogs run. Not stated.

---

## What the design gets right (kept)

- No running, no importing, no downloading; unknown with one general reason.
- `.py`-required module rule, mixed repositories, path identity for unpublished modules.
- Module-level scope symbol for module-body code (§7) — needed and well-placed.
- CFG fields are required by the per-path walk; the design does not try to skip them.
- FastAPI handler parameters come from the request, not callers; `Depends` parameters
  belong to every route using them.
- Re-measuring the call table from the real resolver before and after (§6, §9.4).
