# Reuse review: docs/superpowers/specs/2026-11-06-python-reader-design.md

Reviewer brief: find every place the design invents something that existing code or docs already
cover (or could cover by extension), and every place it reuses something that does not fit Python.
Read only. Every "exists" claim below was checked in the file named.

Severity follows the realistic-shapes rule: Critical/Major only for shapes real Python code produces.

---

## Critical

### C1. Rules 2–4 of type inference re-implement the resolver's value walk, inside the scanner (§6 "Where it runs", "Which callers count")

**Design.** The Python scanner runs rules 2–4: return types from function bodies, parameter types
from every caller "in the scanned module and its sibling modules, exactly as the JVM value walk
crosses to callers today", and field types from every write. It then writes `call_site` facts
whose target is already resolved.

**What exists.** Each rule is an edge the value walk already follows, in the resolver, over the
whole workspace:
- Rule 2 is `method_return` joined to `call_site.result`: `resolve/return_flow.py`, and
  `values._entry` through in-module callee returns (`values.py` ~4282).
- Rule 3 is `values._Walk._parameter` → `ValueIndex.callers`, with `external` where there is no
  caller and `escapes` for a function passed as a value. That is the same scope and the same
  answers the design asks for. The DI-recipe hop (spec 2026-11-05-di-recipe-hop §2) already
  plugs into it.
- Rule 4 is the walk's "sixth edge" over `field_write` (`values.py` ~4270–4300).
- "What type is this receiver" is already answered by type in the resolver.
  `values.producer_paths` / `producers_of` follow an object to its producer. `instance` arguments
  carry the concrete constructed type (D00 §5). `shapes/mounts.py` uses exactly this
  ("`router_producers` … derived from the facts by type") to decide which router a route belongs to.

**Why it breaks.**
1. The scanner is per module (`ScanRequest` holds one module plus its dependency archives), so it
   cannot see sibling modules' callers. The design's own rule 3 scope cannot be met there.
2. D00 §7 partitions facts per source file, keyed by the file's content hash. Under the design, a
   callee file's facts depend on its callers' files, so editing a caller silently invalidates
   another file's facts.
3. It is a second resolver beside the first. That is the design's own anti-goal ("a second
   pipeline beside the JVM one").

**Reuse instead.**
- The scanner writes rule 1 only (written types, `.pyi`, typeshed) plus the raw facts it already
  plans to write (`method_return`, `field_write`, `call_site` with receiver/result ids).
- A call whose owner depends on a receiver's runtime type is resolved in the resolver, by the
  existing producer walk.
- Rules 2–4 then become one extension of the walk ("answer a TYPE as well as a value"), not a new
  inference engine.

### C2. Decorators written as `annotation` uses lose the receiver object (§7 "decorators as `annotation` uses", §8a, §8c)

**Design.** A decorator becomes an `AnnotationFact`: "the decorator's resolved symbol, plus its
literal arguments".

**What exists, and why it does not fit.**
- An `AnnotationUse` (`facts.py:37`) carries a symbol and literal `args`. It has no receiver value
  id.
- Real FastAPI routes are `@router.get("/x")` on an `APIRouter` instance, mounted later by
  `app.include_router(router, prefix=...)`. Real click commands are `@group.command("analyze")` on
  a group object, nested by `add_command`. The prefix and the command path both depend on WHICH
  object the decorator was called on. An annotation fact cannot say.
- `annotation_driven` matches annotation TYPES: `_catalog_symbol` / `type_descriptor` append `#`
  (`symbols.py:220`). A decorator that is a method (`APIRouter#get().`) or a function never matches.
- polar alone has 608 decorator routes, almost all on routers with prefixes.

**Reuse instead.** Write what Python executes, `handler = router.get("/x")(handler)`, as `call_site`
facts in the enclosing scope:
- the `get` call, with `receiver` = the router's value id and the path literal;
- the application of the returned decorator, with a `lambda` argument naming the handler. D00 §5
  already names `lambda` "the canonical cross-language kind for 'this argument is that function' …
  a Python nested function or reference".

The existing styles then apply unchanged:
- `single_call` / `fluent` with `handler_arg`: the Ktor, Javalin and Vert.x
  `router.get(path, handler)` shape, and COVERAGE §1's `registration_call`;
- the `mount` block (`shapes/mounts.py`) for `include_router` and `add_command`.

Keep `annotation` facts only for decorators whose callee is a type or a module-level function
(`@dataclass`, `@abstractmethod`), where no receiver exists.

### C3. The symbol and descriptor shape conflicts with the call-join arithmetic (§5 "Symbol scheme", §6 "Disambiguator", "Call kinds")

**Design.**
- Symbols like `app/api/routes/items/create_item().`: a free function with no `#` owner and an
  empty disambiguator.
- "The plan states how the existing descriptor hashing treats an empty one."
- "A plain function call is `static`."

**What exists.**
- `CallSiteFact._only_a_throw_names_no_method` (`facts.py:514–540`) refuses any non-throw site
  without `owner`, `name` and `descriptor`. Every plain call under the design's symbol has no owner,
  so the run stops at fact validation.
- The caller-to-callee join is `method_descriptor(owner, name, descriptor)` = `owner + name +
  "(" + sig_<sha256(descriptor)[:8]> + ")."` (`symbols.py:173–212`). It is used in `dispatch.py`
  (5 sites), `call_edges.py:313`, `values.py:1931/4543`, `effective_calls.py`, `dispatch_hops.py`
  and `dispatch_registrations.py`. It always emits `sig_…`, so `name().` never equals what it
  computes.
- Overrides are found by the SAME descriptor under the subtype (`dispatch.candidates`, `with_owner`).
  A Python override with different parameters would get a different `sig_` and never be found.
- `descriptor_parameter_types`, `returned_type`, `parameter_types` and `descriptor_slots` parse JVM
  descriptors and raise on a string with no `)`.

**Reuse instead.**
- Give every Python function an owner type, as Kotlin does with its file facade (`FileKt#fn(sig).`):
  the Python module as a type (`construct_kind: module` already exists),
  `app/api/routes/items#create_item(sig_….).`.
- Write one constant descriptor string per Python method (for example `()`), hashed by the
  unchanged `disambiguator_of` on both sides. This keeps "caller to callee is arithmetic" and makes
  overrides join by name.
- State in the design, not the plan, which of the six `symbols.py` descriptor parsers Python sites
  reach, and that `arg_types` / `descriptor:` keys in catalogs cannot be written for Python rows.

---

## Major

### M1. "A `call_site` with no target, plus `reason` and `detail`" (§7)

**Why it breaks.**
- The validator above refuses it.
- Every consumer does `str(site["owner"])`, so `None` becomes the string `"None"`. `dispatch.py`'s
  THROW comment documents exactly this failure.
- `call_edges._edge` returns `(None, [])` for a site with no target, so the edge is DROPPED. The
  call vanishes from traces instead of becoming the `unresolved` terminal (`TerminalKind` already
  has it).
- `call_edges` stamps `evidence: compiler` and says "the compiler named that target exactly" on
  every row (`call_edges.py:262–281`). That is false for an inferred Python target.

**Reuse.**
- The resolver already produces "not found" answers with one general word and a detail: D00 §4's
  `method_resolution` (`external` / `not_readable` + `detail`), from `dispatch.boundary`.
- Keep the target the code names: the name, and the best-known owner from rule 1 or the producer
  walk. Let the resolver answer.
- Mark Python edges `evidence: syntax` (already in the closed set).
- Where the scanner alone knows why it gave up (a non-literal `getattr`), reuse the existing
  "scanner declined, here is why" key spelling, `AnnotationUse.unresolved` (`facts.py:49`), with a
  word from the one reason list. Do not add a parallel `reason`/`detail` pair.

### M2. A module-level scope symbol `__module__().` is invented (§7 "Module-level code")

**What exists.** D00 already covers code that runs once when a file or type loads:
- `<clinit>`, the static initializer, owns it.
- Its assignments are `field_write` on static fields (PUTSTATIC since 2026-10-26, with a call
  result as `value`).
- Reads of them are `field` arguments and `receiver_field` (`facts.py:475`).
- `values.py` ~4280 resolves a file-level `val client = HttpClient(…)` this way already.

**Reuse.** Module type (C3) + `<clinit>` + static fields for module globals. A class body (Pydantic
`model_config = …`, class-level assignments) is the class's own `<clinit>` by the same rule. No new
scope symbol and no new resolver path.

### M3. Constructors: the design says a plain call is `static`; D00 already maps `__init__`, and dispatch's JVM constants break Python (§6 "Call kinds")

**What exists.**
- D00 §5: "`<init>` is the canonical constructor call-site name every extractor normalizes to —
  Python's `__init__` maps in."
- `<init>` is load-bearing in 56 resolver sites and 87 catalog entries: `made_by`, `client_base`,
  value-models `identified_by`, chains and mounts. `httpx.Client(base_url=…)` needs it.

**Not fitting.**
- `dispatch._NOT_INHERITED = {"<init>", "<clinit>"}` encodes JLS 8.8. Python's `__init__` IS
  inherited, so `class Settings(BaseSettings): …; Settings()` finds no constructor.
- `_OBJECT = "java/lang/Object#"` is the lookup's last stop. Python's is `object`.

**Reuse.** Emit `Foo(...)` as `special` `<init>` on `Foo#` with an `instance` result, per D00.
Move "which names are not inherited" and "the root type" out of `dispatch.py` constants into the
lookup-order data (M4), per language.

### M4. Two lookup rules: "a written lookup order when one is present, the JVM rule otherwise" (§6)

**Problem.** This is the special case the "generalize before special-casing" ruling forbids.
`Dispatch.ancestors` is already a per-class ordered list built from `superclass` + `interfaces`
(`dispatch.py:96–110`).

**Generalize.** One per-type `lookup_order` list (the JVM's being its JVMS 5.4.3.3 order: superclass
chain, then interfaces breadth-first) that dispatch reads for every language. Either every scanner
writes it, or the resolver derives the JVM's from the existing fields. Then `_search` is one loop and
Python's C3 is just data.

### M5. "Did we read a body" means "a `method_return` fact exists" (dispatch.py docstring); Python breaks it twice (§7)

1. A Python function with no `return` statement must still emit a `method_return` with `value`
   `None` for its implicit fall-off. Otherwise every such body reads as abstract and every call to
   it reads as the third-party boundary.
2. `@abstractmethod` / `Protocol` stubs (`...`, `pass`, `raise NotImplementedError`) DO have bodies.
   Without a rule they become candidates, and calls drop from `resolved` to `narrowed`.

The design must state both mappings. The existing `abstract` modifier (D00 §5a) is the field for
the second one.

### M6. Keyword arguments as a new `call_site` field (§7)

**What exists.**
- Every catalog addresses arguments by integer position: `url_arg`, `body_arg`, `verb_arg`,
  `handler_arg`, value-models `arg`.
- The precedent for named arguments: kotlinc resolves Kotlin named arguments to positions, so no
  fact ever carried a name.

**Reuse.**
- The scanner maps a keyword to the callee's parameter index wherever rule 1 gives the signature
  (installed library, `.pyi`, typeshed, or in-project).
- Only where it cannot, add one optional `name` key to the existing `CallArgument`.
- Allow a catalog `*_arg` to take a name as well as an index.
- `requests.post(url, data=None, json=None, **kwargs)` makes `json` position 2. `headers` lives in
  `**kwargs` and needs the name form.

### M7. "Default values of parameters" as a new fact field, including FastAPI's `Query(...)`/`Depends(...)` defaults (§7)

**What exists.**
- `Parameter.declares_default` (D00 §5a, shared, set by Kotlin and planned for .NET).
- `Parameter.annotations: list[AnnotationUse]` (`facts.py:69`).
- `annotation_default` (a `LiteralValue` default on a symbol).
- D02 §2k `request_params`, which reads a handler parameter's marker annotation, name attribute,
  default attribute and `optional_types`.

**Reuse.**
- Normalize FastAPI's markers, whether in default position (`q: str = Query(None, alias="x")`) or
  in `Annotated[str, Query()]`, into `Parameter.annotations`, as an `AnnotationUse` with the
  marker's literal args. Pydantic `Field(...)` on fields gets the same treatment.
- `request_params` then works unchanged (`{annotation: fastapi.Query, kind: query, name_attrs:
  [alias], …}`).
- A literal default is `declares_default: true` plus a value in the existing argument grammar.

### M8. `Depends(...)` "followed as calls" (§8c)

**Problem.** The handler does not call its dependency. FastAPI does, and injects the result. A call
edge from handler to provider is a fabricated call.

**What exists.** The approved DI-recipe hop (spec 2026-11-05 §2; D02 §1c `injection`): "a parameter
the container fills receives the value of the one recipe the container chooses for it", consulted
before callers in `values._Walk._parameter`.

**Reuse.**
- Add a third `injection` mode to a `bean-models/fastapi.yml`, in which the parameter's marker
  annotation (M7) names its recipe directly (`Depends`'s argument 0, a `lambda` argument).
- The provider's own query and header parameters reach the route through `request_params` read on
  the recipe, following the same hop.

### M9. "Written or inferred" marker on every type (§6, §7)

**What exists.** D00 §3 already has two stored trust fields with closed vocabularies:
- `evidence`: `declared` for an annotation the author wrote, `syntax` for something read off code
  structure;
- `resolution`: a closed list of inferred types is `narrowed`, by definition.

`nullable_resolution` itself uses the `resolution` vocabulary (`shapes/nullability.py:104`).

**Reuse.** Spell the marker with those words on `TypeRef`. Do not add a new written/inferred word.
The truth guard then checks existing values.

### M10. "A union in a written type is a closed list" (§6 rule 1)

**Why it breaks.** `Optional[X]` / `X | None` is the most common annotation in FastAPI and Pydantic
code. D00 §5b decides it as NULLABILITY on the type reference (`TypeRef.nullable`, resolved by the
type system, the Kotlin `String?` precedent). Read as a two-type closed list, every optional field
becomes two `narrowed` rows.

**Reuse.**
- `None` in a union → `nullable: true`.
- A real union of two or more types is recorded verbatim as `TypeRef(symbol=typing.Union,
  arguments=[…])`. `TypeRef`'s docstring already says envelopes are recorded verbatim and unwrapped
  by catalogs. Then the closed list is read from `arguments`.
- No new representation.

### M11. `cli` inbound and `process` outbound are two protocol words for two ends of one wire (§8a, §8b)

**Why they never link.**
- Linking gates on protocol equality (DR-5; the `Protocol` docstrings in `closed_sets.py` repeat
  it). A Python service that runs another in-repo program's command can therefore never link to
  that command.
- The path forms are incomparable even under one word: inbound is `sextant module analyze`,
  outbound is the program name `mvn`.

**Precedent.** `in_process` and `eventbus` are each one word for both directions, named for the kind
of hand-over.

**Reuse.**
- One protocol word for both ends.
- `peer` = the program (outbound), with the module's `[project.scripts]` name as its served
  identity (inbound).
- `path` = the subcommand words, read from literal items of the argument `array` on the outbound
  side.

**Also not addressed.** `RootKind.ENTRY_POINT` (`closed_sets.py:191–224`, OI-22) is reserved and
waiting for a catalog producer. Its docstring records that `cli_entry` was retired because "`cli`
claimed a surface nobody measured". The design should cite that ruling and say:
- why a command is an `inbound_endpoint` root rather than `entry_point`;
- that `[project.scripts]` / `if __name__ == "__main__"` are the first `entry_point` producer.

### M12. `include_router(..., prefix=)` "followed across modules, nested routers and prefixes joined in order" (§8c)

**What exists.** The `mount` block and `shapes/mounts.py`, built for Vert.x `mountSubRouter("/api",
sub)`:
- nested mounts compose;
- a router is followed to its producer;
- an unread prefix becomes a named `<prefix>` hole at `partial` with a `mount_prefix` question.

Click's `add_command` / group nesting is the same shape. The design names neither.

**Reuse.** Write `mount` entries for `include_router` and `add_command`. Only extend for differences
FastAPI really has (no trailing-wildcard rule, so `refuses` is empty), mirrored per DR-6.

### M13. `httpx.Client(base_url=…)` "joined with each call's path" and verb "from the string argument of `.request("GET", url)`" (§8d)

**What exists.**
- D02 §1g `client_model` / `client_base`: "where a client's relative calls are sent is a property
  of the CLIENT", declared once in `catalogs/client-models/` and merged by the loader.
- The `verb_arg` key (10 shipped uses).

**Reuse.**
- A `client-models/httpx.yml`.
- Extension only where httpx differs: its join is not Ktor's `replace_last_segment` (httpx appends
  under the base path), so add one value to the `join` vocabulary, measured.
- `verb_arg` for `.request`.

### M14. Python configuration values (§8e)

1. **pydantic-settings `BaseSettings`.** "Field name to environment name, with `env_prefix` and
   aliases" is D02 §2j rung 3: `properties_annotation` + `prefix_from` + §2i `key_matching`, which
   already turns a bound properties field into `${prefix.name}`. Extend it with a supertype marker
   (the class extends `BaseSettings`) and a prefix read from a class-level field. Do not write a
   settings reader.
2. **`.env` files.** These are a `config_model` `sources:` entry (§2i patterns, precedence lowest
   first) plus a `.env` reader that emits `config_entry` facts. Not a new mechanism.
3. **`os.environ[...]` / `os.getenv(...)`.** Make this catalog data (a value-model style entry: this
   call's argument N is a configuration KEY), written so that the JVM's `System.getenv` gets the
   same rule ("generalize before special-casing").
4. **The answer is wrong.** "A value set only by the deployment is `external` with the key as its
   detail (ruling 2026-10-23)" misreads both rulings:
   - "Deployment decides" covers EXISTENCE verdicts. Its scope note says resolved values are not
     affected.
   - "Trace the value to its source", rung 3, says publish THE KEY as an expression
     (`${PRICING_URL}/orders`), which the existing `${…}` placeholder path form and `resolved_config`
     join already carry.
   - With `external`, the row loses the address a reader needs.

### M15. "Pydantic shapes" without a mechanism (§3 goal 5, §8c, §8d)

**What exists.**
- D02 §1b `shape_model:`. A second serializer is a second file (`shape-models/pydantic.yml`).
- §2f `serialization.name_from` handles `Field(alias=…)`, once it is an annotation per M7.
- `default_strategy` handles `alias_generator`.
- §2g `known_types` gives wire forms for `datetime`, `UUID`, `Decimal`, `EmailStr`.

**Also.** `json=item.model_dump()` "gives the model's shape" is one library method's semantics, which
the 2026-10-21 "one rule, not one parser per method" ruling refuses as code. Express it as a
value-models `identified_by` entry (the call's result stands for its receiver), which is data with
a `by:` probe.

### M16. Library detection: "catalogs match on the imported name" (§5 "Libraries")

**What exists.**
- `detect.coordinates` on every catalog, checked against the module's dependency list:
  `ModuleFact.dependency_coordinates`, `dependency_versions`, `dependency_source` (declared vs
  resolved, with a reason), and `classpath: ClasspathEntry(path, tier, coordinates)`.
- Python's declared list is `[project.dependencies]` / requirements. Its resolved list is `uv.lock`
  or the environment's `.dist-info`, which is the "ask the build tool" answer (M02, OI-167).
- `OriginTier.platform` fits the stdlib and typeshed's stdlib stubs. `dependency` fits
  site-packages.

**Not fitting.**
- `fastapi.APIRouter` is defined at `fastapi.routing.APIRouter` and re-exported.
- With the library installed, the scanner resolves the defining module. Without it, only the import
  name is known. One type then has two spellings depending on the environment, and catalogs match
  one of them.

**Fix.**
- Pick one rule (always the defining module where known), and use D02 §3.1's list form for the
  alternate spelling.
- D02 §1 already says `type_descriptor` "becomes scheme-aware when the first non-JVM catalog
  arrives". The design must do that.

### M17. Detector: "the kind of file gives the language. This is the rule Java and Kotlin already use" (§5)

**Not accurate.**
- M02 says detectors are "keyed by build system, not by language" and record languages OBSERVED
  ("No language branching").
- Maven derives them from source-root directory names (`maven.py:381`). Gradle derives them from
  the source sets Gradle reports.
- `tests/architecture/test_language_confinement.py` forbids language names outside the extractor
  adapter. 19 source files already say "Python" in prose, so naively adding `python` to
  `LANGUAGE_NAMES` fails broadly.

**Reuse.**
- A Python-packaging detector (pyproject / requirements / Pipfile are the build system).
- Languages observed by the scanner adapter's declared file kinds.
- A plan to extend the confinement test to `ingress/extract/python`.

### M18. Rule 4 counts `obj.x = ...` writes from outside the class (§6)

**What exists.** `field_write` means a write on `this` (PUTFIELD) or a static (PUTSTATIC). The JVM
side refuses a static method's PUTFIELD as "another object's field" (`facts.py:575–590`). The
2026-10-30 rulings ("field per object") rely on that: the fact has no receiver.

**Why it breaks.** Written as `field_write`, a write to another object would be attributed to every
instance.

**Fix.** Either add an optional `receiver` value id to `field_write` (the `call_site` precedent), or
keep cross-object writes out of the fact.

### M19. `constant` facts for Python module-level "constants" (§7, §8e)

**What exists.** D00's `constant` is JVMS `ConstantValue`: a compile-time `static final` that nothing
can rebind.

**Why it breaks.** A Python module global can be rebound (`global X; X = …` in a `configure()`,
`mod.X = …`). A `constant` fact would publish the first value as `resolved` and hide the later
writer.

**Reuse.** M2's `field_write` from `<clinit>` with a literal `value`. The walk already answers that
"without crossing anything", and it sees other writers too.

---

## Minor

- **m1.** "Module" means two things in the design. One is a Python module (a file, which is D00's
  `document`). The other is a Sextant module (a build unit). "Sibling modules" in rule 3 and
  "followed across modules" in §8c are ambiguous. Use `document` for files.
- **m2.** `.python-version` names an interpreter version, not an environment. It cannot locate a
  venv.
- **m3.** A dynamic version written as `.` is "unknown", not "no meaning" (D00 §1's sense of `.`).
  The project's own editable install in `.venv` has a `.dist-info` stating the version, which is
  the build tool's answer.
- **m4.** Typeshed-derived types should carry per-fact provenance (`type_header.origin`/`version`
  style), not only scan provenance. A stub's version can differ from the installed library's.
- **m5.** The Python scanner must declare M03 capabilities that catalogs `require` (`call_site`,
  `string_constants`, `typed_signatures`, `method_returns`, `chain_reconstruction`,
  `concat_template`, `array_arguments`, `lambda_body`). The design is silent on them. Also:
  - an f-string is the existing `concat` template;
  - a list literal is `array`;
  - a dict literal and a `**` splat are `unresolved` until rule 6.
- **m6.** A CLI request shape (options, arguments, flags, choices) should reuse §2k `request_params`
  rows with new `kind` values (`option`, `argument`), rather than a new shape form.
- **m7.** Build the control-flow graph analyses (dominators, post-dominators, loop SCCs) as a
  language-free helper. The JVM's live in the Java extractor, and the next source-reading language
  (JS/TS) needs the same fields.
- **m8.** `os.system("mvn …")` needs a shell-string split, which is one library's semantics.
  Publish the first token at `partial`, or leave it `unresolved`. Do not write a shell parser.
- **m9.** `asyncio.create_subprocess_exec` / `_shell` are missing from the §8b list.

---

## What the design reuses correctly

- The existing fact kinds (`document`, `module`, `symbol`, `call_site`, `method_return`,
  `field_write`, `type_header`, `config_entry`) as the target, and "the resolver stays
  language-free".
- One reason vocabulary (`values._REASONS`) and the `test_one_reason_list.py` guard.
- "Enumerable is exact" closed lists; `external` / `escapes` / `cycle` answers.
- The rule 9 per-path fields (`dominator`, `on_every_exit`, `post_dominator`, `reaches_return`,
  `loop_group`) and `merge` arguments, rather than inventing a Python control-flow fact.
- D00's unpublished-service identity (`.` fields, folder path as id) and OI-273 "what the build tool
  gives".
- `websocket` protocol for FastAPI WebSocket routes.
- Framework runtime behaviour as catalog data (rule 5); the value walk for addresses (§8d).
- `--allow-resolve` stays Maven-only; no network.
- Field pins via `scripts/field_check.py`; a fixture built by its own tool, as the JVM fixtures are.
- Shipping typeshed inside the wheel, the same packaging decision as the extractor jar
  (ARCHITECTURE packaging row).
- M03 as the only place that knows a language exists.
