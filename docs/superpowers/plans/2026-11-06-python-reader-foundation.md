# Python reader foundation (plan 1 of 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sextant analyses a Python project with the existing pipeline: a Python detector and
scanner write the existing facts, the resolver binds what one file cannot know, and Sextant's own
`click` commands become `entry_point` roots with traces.

**Architecture:**
- A new detector (`ingress/detect/python.py`) and a new scanner backend (`ingress/extract/python/`)
  write the existing D00 facts, with two approved extensions:
  - a `call_site` whose owner is bound later;
  - a per-module `lookup` rule.
- The resolver gains one general lookup order (JVM rule unchanged, C3 for Python) and a
  receiver-binding pass on the existing value walk.
- A catalog flag sends command rows to `roots` as `entry_point`.

**Tech Stack:** Python 3.12+ stdlib `ast`/`tomllib`, pydantic facts, DuckDB, YAML catalogs, a pinned
`typeshed` copy in the wheel.

**Spec:** `docs/superpowers/specs/2026-11-06-python-reader-design.md` (APPROVED v2). Reviews:
`2026-11-06-python-reader-review-first-principles.md`, `…-review-reuse.md`.

**The three plans:**
1. **This plan:** the reader foundation (spec §3a, §3b, §3e, §5, §6, done-when items 1 and 4).
2. **Plan 2:** FastAPI inbound, Pydantic `shape_model`, `Depends` (§3c, done-when item 2).
3. **Plan 3:** `requests`/`httpx` outbound, configuration (§3d), field pins on polar, dispatch and
   mealie (done-when item 3).

Each plan ends in working software.

## Global Constraints

**Rules from the spec:**
- **Reading:** the scanner reads one file at a time (M03: no reasoning across files). It never
  imports or runs scanned code, and nothing is downloaded.
- **Pipeline:** existing facts and words first. New fields are only the two named in the spec:
  - `call_site.target.owner` absent when `receiver` is set and `invoke_kind == "virtual"`;
  - `module.lookup ∈ {"jvm", "c3"}`.
- **Truth:** a guess is never `resolved`. Every unknown carries one word of `values._REASONS`, plus a
  detail.
- **Evidence:** a written type is `evidence: declared`. An inferred one is `evidence: syntax`, with
  `resolution: narrowed` for a closed list.
- **Symbol scheme:** `sextant-python pypi <name> <version> <descriptors>`, with `.` fields for an
  unpublished module.
  - A Python module (file) is a type: `app/api/items#`.
  - A module body or class body is that type's `<clinit>`. `__init__` is `<init>`.
  - Every method's descriptor is `disambiguator_of(PY_SIGNATURE)`, where `PY_SIGNATURE = "(*)"`, one
    constant for every Python method.
- **Performance budget** (polar `server/`, this machine):

  | | Ceiling (stop and ask) | Target |
  |---|---|---|
  | cold analysis | 300 s | 60 s |
  | warm analysis | 30 s | 10 s |

  Report the time after every task that changes a pass.
- **Project rules:**
  - JDK 21 for every test run (`JAVA_HOME=/opt/homebrew/opt/openjdk@21`).
  - ASD-STE-100 comments; GUIDELINES §1–4, §13.5.
  - New catalog words and format changes beyond the two above need the user's approval before
    building.
  - Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Language confinement:** Python-specific names (`<clinit>` for a module, `c3`, `__init__`)
  appear only in the Python detector and scanner, and in the named `c3` lookup rule.
  `tests/architecture/test_language_confinement.py` records each exception.

## Review Focus

1. **A repository with both a `pom.xml` and a `pyproject.toml`** (in different folders): both
   modules are found, each with its own language. Pinned in Task 3.
2. **A name bound in two places** (`try: import ujson as json` / `except ImportError: import json`):
   two bindings, a closed list, never the first one silently. Pinned in Task 4.
3. **A call on a module-level singleton imported from another file** (`from app.svc import order`,
   then `order.create()`): bound to `OrderService.create` by the resolver, not left unbound. Pinned
   in Task 8.
4. **A diamond class hierarchy** (`class D(B, C)`, both overriding `m`): `D().m()` reaches `B.m` by
   C3, never `C.m`. Pinned in Task 7.
5. **A file Python cannot parse** (a Python 2 file, or a syntax error): the file is reported as not
   read, with a reason, and the rest of the module is analysed. Pinned in Task 4.

---

### Task 0: Measure before building

**Files:**
- Create: `scripts/probes/python_timing.py`
- Create: `docs/research/2026-11-06-python-performance.md`

**Interfaces:**
- Produces: `python_timing.py <path>`, which prints for a source tree:
  - file count;
  - time to read, `ast.parse` and walk every file once, cold and with a content-hash cache;
  - call-site count;
  - for comparison, the existing JVM resolver's call sites per second, read from the newest
    workspace of `examples/apollo` or `examples/mall` (whichever is analysed).

- [ ] **Step 1:** Write the probe. Run it on `examples/py-polar/server` and on `src/sextant`.
- [ ] **Step 2:** Write the research note:
  - the numbers;
  - the projected cold time (parse, plus the JVM rate times polar's 47,716 call sites);
  - whether the 60 s target is reachable.

  If the projection is over 300 s, stop and ask for a ruling.
- [ ] **Step 3:** Commit (`docs(research): Python performance baseline (OI-208 plan 1 task 0)`).

### Task 1: Fact format — the two extensions and the scheme

**Files:**
- Modify: `src/sextant/domain/facts.py`:
  - `CallSiteFact._only_a_throw_names_no_method` (≈ line 530);
  - `ModuleFact`.
- Modify: `src/sextant/domain/symbols.py` (scheme constant `PYTHON_SCHEME = "sextant-python"`,
  `PY_SIGNATURE = "(*)"`).
- Modify: `docs/components/D00-fact-schema.md` (§1 scheme, §5 `call_site` owner rule, `module.lookup`).
- Modify: `src/sextant/domain/version.py` (facts version +1, with its history note).
- Test: `tests/domain/test_facts.py`, `tests/domain/test_symbols.py`.

**Interfaces:**
- Produces:
  - `CallSiteFact` accepts `target.owner is None` iff `invoke_kind == "virtual"` and `receiver is not None`;
  - `ModuleFact.lookup: Literal["jvm", "c3"] = "jvm"`;
  - `symbols.PYTHON_SCHEME`, `symbols.PY_SIGNATURE`.

- [ ] **Step 1: Failing tests:**
  - `test_a_virtual_call_with_a_receiver_may_leave_its_owner_to_the_resolver`: constructs
    `CallSiteFact(invoke_kind="virtual", receiver=3, target=CallTarget(owner=None, name="create", descriptor="(*)"), …)`, with no error.
  - `test_a_call_with_no_owner_and_no_receiver_is_refused`: `pytest.raises(ValueError)`.
  - `test_a_static_call_with_no_owner_is_refused`: `pytest.raises(ValueError)`.
  - `test_module_lookup_defaults_to_jvm`.
  - `test_every_python_method_shares_one_disambiguator`:
    `method_descriptor("a/b#", "f", PY_SIGNATURE) == "a/b#f(" + disambiguator_of("(*)") + ")."`.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement. Update D00 and the version stamp.
- [ ] **Step 4:** Run the tests, plus `scripts/check.sh --lint`. Expect PASS.
- [ ] **Step 5:** Commit.

### Task 2: Python detector — modules, identity, import roots, environment

**Files:**
- Create: `src/sextant/ingress/detect/python.py` (`PythonDetector`).
- Modify: `src/sextant/api.py:428` (`_DETECTORS`).
- Modify: `docs/components/M02-detector.md`.
- Test: `tests/ingress/detect/test_python_detector.py` (builds trees in `tmp_path`).

**Interfaces:**
- Produces:
  - `PythonDetector.accepts(path) -> bool`;
  - `PythonDetector.detect(path, allow_resolve=False) -> RepositoryModel`. `allow_resolve` is ignored.
  - Each `ModuleModel` has:
    - `languages=frozenset({"python"})`;
    - `kind` ∈ `{"pyproject", "setup_cfg", "setup_py", "requirements"}`;
    - `coordinates`/`version` per spec §3e identity (PEP 503 normalized name; `.` when unpublished
      or dynamic with no `.dist-info`);
    - `source_roots` = import roots;
    - `output_dirs=()`;
    - `packaging="wheel"`;
    - `dependency_coordinates` = declared requirement names;
    - `dependency_versions` = installed versions;
    - `dependency_archives` = one `LibraryRoot(coordinate=<dist name>, version=<installed>, archive=<site-packages dir>)`
      per installed distribution the module declares.
  - The `.venv`/`venv` path or the uv/Poetry-named environment is recorded on the module.
    `RepositoryModel.notes` lists every folder of `.py` files with no project file, and every
    `sys.path` change found by name (`sys.path.insert`/`append`) as text.

- [ ] **Step 1: Failing tests** (one per spec §3e rule):
  - `test_pyproject_project_table_gives_name_and_version`
  - `test_poetry_table_is_read_when_project_table_is_absent`
  - `test_setup_cfg_metadata_gives_name_and_version`
  - `test_setup_cfg_without_metadata_is_not_a_module`: CTFd's `[nosetests]`-only file.
  - `test_setup_py_inside_a_package_is_not_a_module`: `pkg/__init__.py` + `pkg/forms/setup.py`.
  - `test_setup_py_under_an_existing_module_is_not_a_module`
  - `test_requirements_only_service_is_an_unpublished_module`: `coordinates == "."`, `module_id` is
    its folder path.
  - `test_uv_workspace_root_without_code_is_not_a_module_its_members_are`
  - `test_dynamic_version_reads_installed_dist_info_else_dot`
  - `test_src_layout_import_root_is_src`
  - `test_python_version_file_is_not_an_environment`
  - `test_installed_distribution_versions_come_from_dist_info`
  - `test_loose_py_folder_is_noted_not_analysed`
  - `test_sys_path_change_is_noted`
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement `PythonDetector`.
  - **Rules:** names only, plus `tomllib`/`configparser` reads of build files (M02: build files,
    never code). The `sys.path` note is a text search of build-adjacent `.py` files.
  - **Environment:** found by `pyvenv.cfg`.
  - **Installed distributions:** read from `*.dist-info/METADATA`.
- [ ] **Step 4:** Run; expect PASS. Also run `uv run sextant module analyze` on
  `examples/py-microservices-demo/src/emailservice` with no scanner yet. It must refuse with "no
  scanner reads python", not crash.
- [ ] **Step 5:** Commit.

### Task 3: Mixed repositories — every build system, not the first

**Files:**
- Modify: `src/sextant/application/ports/detector.py` (`select_detector` → add
  `detect_repository(detectors, path, allow_resolve) -> RepositoryModel`).
- Modify: `src/sextant/api.py`: callers of `select_detector(_DETECTORS, …)`.
- Modify: `docs/components/M02-detector.md`.
- Test: `tests/application/test_detect_repository.py`.

**Interfaces:**
- Produces: `detect_repository`:
  - runs every detector that `accepts(path)`, and merges their `modules` and `notes`;
  - `multi_module` is true when the merged list has more than one module;
  - two modules with the same `module_id` from different detectors are an error that names both.

  `select_detector` stays for `_KnownModuleDetector`.

- [ ] **Step 1: Failing tests:**
  - `test_a_repository_with_a_maven_build_and_a_python_service_yields_both`: root `pom.xml`, plus
    `svc/pyproject.toml` and `svc/app.py`. Use stub detectors from the test; no Maven run.
  - `test_a_python_only_repository_is_unchanged`
  - `test_two_detectors_claiming_one_module_id_is_refused`
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement. `PythonDetector.accepts` looks for Python build files at any depth.
  Maven and Gradle keep their root rule.
- [ ] **Step 4:** Run; expect PASS. Run the full check; all JVM tests must stay green.
- [ ] **Step 5:** Commit.

### Task 4: Scanner part 1 — structure, written types, decorators as calls

**Files:**
- Create:
  - `src/sextant/ingress/extract/python/__init__.py`
  - `scanner.py` (`PythonScanner`)
  - `structure.py` (symbols, `<clinit>`, static fields)
  - `typing_rules.py` (rule 1)
  - `imports.py` (name binding)
- Modify: `src/sextant/api.py:491` (`_scanners`).
- Modify: `docs/components/M03-scanner.md`.
- Test: `tests/ingress/extract/python/test_structure.py`, `test_typing_rules.py`.

**Interfaces:**
- Consumes: Task 1 constants; Task 2 `ModuleModel`.
- Produces:
  - `PythonScanner` with:
    - `accepts({"python"})`;
    - `rank() == 0`;
    - `capabilities() == {"typed_signatures", "annotation_args", "type_annotations", "value_ids", "control_flow"}`.

    `control_flow` is declared from Task 6 on.
  - `scan(ScanRequest)`:
    - reads `classes_dir` and `more_classes_dirs` as import roots;
    - writes one fact file per `.py` file (`write_fact_file`);
    - returns `ScanReport` with `uncovered` listing unparsable files.
  - `typing_rules.type_ref(node, scope) -> TypeRef | None`.

- [ ] **Step 1: Failing tests:**
  - `test_a_module_is_a_type_and_its_top_level_function_is_its_method`:
    `app/api/items#create_item(<dis>).`.
  - `test_module_body_is_clinit_and_its_names_are_static_fields_written_there`: `app = FastAPI()`
    gives a `field_write` of `app/main#app.` by `app/main#<clinit>(<dis>).`.
  - `test_init_is_init_method`
  - `test_property_getter_and_setter_are_two_members`: `x` and `x=`.
  - `test_overload_stubs_are_types_not_bodies`
  - `test_conditional_double_definition_is_two_bodies`
  - `test_optional_is_nullable`: `Optional[int]` → `TypeRef(symbol=…int#, nullable=True)`.
  - `test_union_is_type_arguments`
  - `test_type_of_x_return_means_x`: `def f() -> type[_APIRouter]`.
  - `test_written_type_has_evidence_declared`
  - `test_decorator_is_written_as_two_calls`: `@router.get("/x")` on `def f` gives a call
    `router.get` with string argument `"/x"`, and a call on its result with a method-reference
    argument naming `f`; no `annotation` fact.
  - `test_try_import_fallback_binds_a_closed_list` (Review Focus 2).
  - `test_unparsable_file_is_uncovered_and_the_rest_is_scanned` (Review Focus 5).
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement. Imports bind names to symbols across the module's import roots by
  path only (no reading of the other file's body).
- [ ] **Step 4:** Run; expect PASS. `uv run sextant module analyze .` on Sextant itself completes.
  Report the facts count and the time.
- [ ] **Step 5:** Commit.

### Task 5: Scanner part 2 — calls, values, returns

**Files:**
- Create: `src/sextant/ingress/extract/python/calls.py`.
- Test: `tests/ingress/extract/python/test_calls.py`.

**Interfaces:**
- Produces: `call_site` facts with:
  - `ordinal`, `receiver`, `result` value ids;
  - `receiver_parameter` / `receiver_field`;
  - `invoke_kind`: `static` for a function, `virtual` for a call on an object, `special` for
    `super().m()` and for `<init>`;
  - arguments: f-string or `+` → `concat`, list or tuple → `array`, function reference → `lambda`,
    keyword → bound to its position where the callee's signature is in the same file or known by
    rule 1; otherwise kept by name in the existing argument's `name` (the plan's only use of it).

  Also produces:
  - `method_return` for every `return`, plus the implicit `return None`;
  - `field_write` for `self.x = …` and `obj.x = …` with the receiver's value id.

- [ ] **Step 1: Failing tests:**
  - `test_call_on_a_typed_parameter_names_its_owner`
  - `test_call_on_an_unknown_receiver_names_only_the_receiver`: `owner is None`,
    `invoke_kind == "virtual"`.
  - `test_fstring_url_is_concat`
  - `test_keyword_binds_to_position_when_signature_known`
  - `test_implicit_return_none_is_a_method_return`
  - `test_abstract_ellipsis_body_has_no_method_return`
  - `test_field_write_from_outside_the_class_names_the_receiver`
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run; expect PASS.
- [ ] **Step 5:** Commit.

### Task 6: Scanner part 3 — control-flow fields

**Files:**
- Create: `src/sextant/ingress/extract/python/flow.py`.
- Test: `tests/ingress/extract/python/test_flow.py`.

**Interfaces:**
- Produces: on every `call_site`:
  - `dominator`, `on_every_exit`, `post_dominator`, `reaches_return`, `loop_group`;
  - `merge` arguments where a value joins from two paths.

  These are the same meanings the JVM extractor gives (read `ingress/extract/jvm` and D00 §5
  `call_site`).

- [ ] **Step 1: Failing tests:** one per construct, asserting the five fields:
  - `if`/`elif`/`else`;
  - `for`/`while` with `else`;
  - `break`, `continue`;
  - `try`/`except`/`else`/`finally`;
  - `with`, including the rule that a `with` block may swallow an exception, so a call after it is
    not `on_every_exit` of the block;
  - `return`, `raise`;
  - `async`/`await`;
  - `yield`;
  - a comprehension;
  - `match`.

  Every expression may raise: a call inside a `try` body is not a dominator of the `except` block.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement on the syntax tree (structured, no region recovery).
- [ ] **Step 4:** Run; expect PASS.
- [ ] **Step 5:** Commit.

### Task 7: Libraries, typeshed, and one lookup order

**Files:**
- Create: `src/sextant/ingress/extract/python/libraries.py`.
- Add: `src/sextant/resources/typeshed/` (pinned commit; record it in `resources/typeshed/COMMIT`).
- Modify:
  - `pyproject.toml` (package data);
  - `src/sextant/application/resolve/dispatch.py` (`Dispatch.ancestors` → `lookup_order(owner) -> list[str]`);
  - D00 §4, M03.
- Test: `tests/ingress/extract/python/test_libraries.py`, `tests/application/test_dispatch.py`.

**Interfaces:**
- Produces:
  - **Library signatures:** library symbols are always the defining symbol. A re-export maps to its
    definition through the library's own imports.
  - **Library facts:** facts for every installed library the module declares, with `origin` = the
    distribution coordinate. Signatures and types only, unless `extract_libraries` opts in
    (D04 §2a).
  - **typeshed facts:** carry `origin = "typeshed@<commit>/<stub package>@<version>"`.
  - **The lookup order:**
    - `Dispatch.lookup_order(owner)`: the JVM order, unchanged, when the owner's module has
      `lookup == "jvm"`;
    - C3 linearization over `type_header` supertypes in written order when `lookup == "c3"`;
    - an unread parent ends the order, and the lookup answers `external`.

- [ ] **Step 1: Failing tests:**
  - `test_reexported_name_resolves_to_defining_symbol`: `fastapi.APIRouter` →
    `fastapi/routing#APIRouter#`. Use a fake installed distribution in `tmp_path`.
  - `test_uninstalled_library_has_no_symbols_and_is_reported`: the detail is
    `fastapi is not installed in the scanned environment`.
  - `test_typeshed_gives_requests_types_with_provenance`
  - `test_overload_is_chosen_by_argument_types_else_a_closed_list`: `subprocess.run` from typeshed with
    `text=True` returns `CompletedProcess[str]`; with an argument of unknown type, the closed list of
    the overloads' returns at `resolution: narrowed`.
  - `test_c3_diamond_reaches_the_first_parent` (Review Focus 4).
  - `test_c3_inconsistent_hierarchy_is_not_readable`
  - `test_python_init_is_inherited`
  - `test_jvm_lookup_order_is_unchanged`: the existing dispatch tests pass unmodified.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement. Record the `c3` rule as a confinement exception.
- [ ] **Step 4:** Run; expect PASS. Run the full check.
- [ ] **Step 5:** Commit.

### Task 8: Receiver binding — the resolver binds unowned calls

**Files:**
- Create: `src/sextant/application/resolve/receiver_binding.py`.
- Modify: `src/sextant/application/resolve/pipeline.py`, around `record_call_edges` (≈ line 209).
- Modify: `docs/components/M04-resolver.md`.
- Test: `tests/application/test_receiver_binding.py`.

**Interfaces:**
- Consumes: Task 5 facts (`owner is None`, `receiver` set); `values.producer_paths`; `return_flow`;
  `field_writes`.
- Produces:
  - `bind_receivers(workspace) -> int`: the number of call sites newly bound.
  - It writes `call_sites` owner bindings per path into a new derived table `bound_receivers`
    (`caller, ordinal, path_id, owner, evidence, resolution`), with `evidence = "syntax"` and
    `resolution = "narrowed"` for a closed list.
  - It never mutates facts. `call_edges` reads `coalesce(fact owner, bound owner)`, one edge per
    bound owner.
  - The pipeline runs `record_call_edges` → `bind_receivers` → `record_call_edges` until
    `bind_receivers` returns 0, at most 8 rounds. A remaining unbound call is
    `not_readable "receiver of <name> not followed after 8 rounds"`.
  - An unbound call with no producer is `external`, or `escapes`, per the walk.

- [ ] **Step 1: Failing tests:**
  - `test_constructor_local_binds`
  - `test_return_value_binds`
  - `test_parameter_binds_per_caller_path_never_combined`: two callers pass a `Session` or a
    `Client`. Two bound rows, each on its own path.
  - `test_field_written_in_init_binds_self_field_calls`
  - `test_module_singleton_imported_from_another_file_binds` (Review Focus 3)
  - `test_function_passed_as_value_is_escapes`
  - `test_no_caller_is_external`
  - `test_rounds_stop_when_nothing_new_binds`
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement on the existing walk. No second walk.
- [ ] **Step 4:** Run; expect PASS. Run the full check: the JVM sweep shows no change, because JVM
  facts always carry an owner. Report the time on polar.
- [ ] **Step 5:** Commit.

### Task 9: Commands as `entry_point` roots

**Needs approval before building:** the catalog key `root_kind: entry_point` on a `single_call`/`fluent`
catalog, meaning "rows go to `roots` as `entry_point`, not to `endpoints`". It is the "catalog
declaring the entry point" OI-22 names.

**Files:**
- Create: `src/sextant/catalogs/click.yml`.
- Modify:
  - `src/sextant/application/resolve/roots.py`;
  - the `single_call`/`fluent` engines (route rows by `root_kind`);
  - `docs/components/D02-catalog-schema.md`;
  - `docs/open-issues.md` (OI-22 closes).
- Log a new item: "program starts as outbound" (spec §6), with the next free OI id and its Plane
  item.
- Test: `tests/application/test_entry_point_roots.py`.

**Interfaces:**
- Produces: `roots` rows with `root_kind = "entry_point"`, `protocol = NULL`, `method = NULL`, and
  `path` = the command words. The program name comes from `[project.scripts]` (the detector records
  it in Task 2), then the groups by `mount`, then the command. `request_params` rows come from the
  command's `click.option`/`click.argument` calls (name, type, required, flag).

- [ ] **Step 1: Failing tests:**
  - `test_a_click_command_is_an_entry_point_root`
  - `test_group_nesting_gives_the_full_command_path`: `sextant module analyze`.
  - `test_options_become_request_params`: `--allow-resolve` is a flag, and `path` is a required
    argument of type path.
  - `test_a_command_root_gets_a_trace`
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run; expect PASS.
- [ ] **Step 5:** Commit.

### Task 10: Sextant reads itself — end to end, measured

**Files:**
- Create: `tests/e2e/test_sextant_reads_itself.py`.
- Modify: `scripts/probes/python_call_kinds.py` (add `--workspace` to print the call table from a
  real workspace).
- Modify: `docs/research/2026-11-06-python-performance.md`.
- Modify: `docs/COVERAGE.md`: §3 Python row; §3a versions (Python 3.12+ read, typeshed commit);
  the Python essay `docs/coverage/python.md`.
- Create: `docs/research/2026-11-06-python-type-tools.md`, the comparison: own reader vs pyright,
  Pyrefly or ty over LSP, vs mypy in-process (its internal API), with the reasons from the spec.
- Modify: `CHANGELOG.md`.

- [ ] **Step 1: Failing test** `test_sextant_reads_itself`:
  - analyse the repository root;
  - exactly 6 `entry_point` roots whose paths are Sextant's 6 commands (read the list from
    `src/sextant/cli/app.py` by hand and write it into the test);
  - each root has a trace with at least one hop;
  - every `call_site` in Sextant's own code has a bound target or a reason from `values._REASONS`;
  - the guard `tests/application/test_one_reason_list.py`'s checks pass on this workspace.
- [ ] **Step 2:** Run; expect FAIL until all tasks are in. Then PASS.
- [ ] **Step 3:** Produce the call table from the real workspace, before and after `bind_receivers`,
  for Sextant and polar `server/`. Record it, and the cold and warm times against the budget.
- [ ] **Step 4:** Full check; six field pins ok.
- [ ] **Step 5:** Commit.
