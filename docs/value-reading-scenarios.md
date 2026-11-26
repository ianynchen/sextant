# How a value is read: the scenarios Sextant handles

This is the reference for every language reader. Before a new reader (or a new framework) adds
a rule for a code shape, find the shape here. If it is here, the reader uses the same answer
and the same mechanism. If it is not here, it is a case to **bring to the user with a count
from real projects** (GUIDELINES §8.9); it is not a case to solve locally.

**How to use this file (mandatory, GUIDELINES §8.9):** before a design question goes to the
user, and before any new word, fact or rule is proposed, find the ROLE of the code shape here
— first in "Find it by role", then in the tables — and quote the row. For a framework in a
new language, first name the Java or Kotlin construct that has the same role. A question or a
proposal that does not quote the row it checked, or say "searched: no row", is not ready.

## Find it by role

| The code does this | Look at |
|---|---|
| A value comes through a helper, a return, a field, a branch | "Helpers", "Branches", "Fields, builders, callables, inheritance" |
| A list or array of values, held in a name or written in place | "Lists and arrays" |
| A route gets its prefix from a mount | "Mounts and prefixes" |
| A handler gives the request to another handler | "Which handler answers" (`shapes/pass_through.py`, catalog word `passes_on`) |
| A marker on the handler (an annotation, a decorator) states the method | "Role → existing catalog word(s)": `annotations[].method`, `method_from` |
| A class handles requests by the names of its methods | "Role → existing catalog word(s)": `dispatch`, `bypassed_by`; an override that calls its parent keeps the rows |
| A route names no method | `verbless_serves: any`; `all_methods` |
| A value is behind a call (`URI.create(x)`, `include(x)`, `X.as_view()`) | value-model forms `returns`, `returns_receiver`, `result_returns`, `result_calls`; `url_via`, `channel_via`, `identified_by` |
| Something a deployment decides | rule 8, "not evaluated" |
| A module that holds the settings of one deployment (a profile file on the JVM, `application-prod.yml`; a Django settings module) | config-model `sources`: a file pattern with `{-profile}`, or `{from_module_holding: root_setting}` (each module that holds the root setting is an environment named by the module; one `resolved_config` row per name it holds, the value read by the walk, through `from .base import *`). `tests/application/test_django_settings.py::test_each_module_holding_the_root_setting_is_an_environment`, `::test_a_settings_module_holds_what_a_star_import_gives_it` |
| A test on a value the code fixes (a parameter each caller passes a literal for, a name written once) | "Branches": decided per path |
| Code that is not there | reasons `external`, `escapes`. A library that a project uses IS there. |

Sextant reads code. It does not run it. Each answer below is what the engine says today, with
the test that proves it. A row marked † cites a test whose name and docstring were read, not
its full body. Surveyed on `main` at 75d0018d (2026-11-23).

Short names: `values.py` = `src/sextant/application/resolve/values.py`;
`TV` = `tests/application/test_values.py`; `TM` = `tests/application/test_mounts.py`;
`FR` = `tests/application/test_fastapi_routes.py`; `FP` = `tests/application/test_fastapi_prefixes.py`.

## The answer vocabulary

A value answers as `literal`, `expression` (a template with holes), `absent` (the code states
there is no value), or `unresolved` with exactly one of six reasons (`values.py:172-184`):

| Reason | Meaning |
|---|---|
| `external` | the producer is in code that was not scanned |
| `not_readable` | the producer was scanned and nothing names its value |
| `non_enumerable` | the members of a set cannot be listed (also every cap) |
| `escapes` | the value was handed to code that can change it, and that code was not read |
| `no_writer` | no reported write of the field was found |
| `cycle` | the walk returned to a position on its own path |

Two marks on an answer: `inexact` (a URL publishes at `partial`; a channel is refused) and
`narrowed` (one of several known values).

## The ten rules

1. **The unit is the path, not the position.** A helper called twice gives one binding per
   caller, and all slots of one binding agree on the caller. Never the cross product.
   One bound: a path that enters one helper on two calls (`f(1)(f(2)(v))`) holds the first
   call alone, so a value read through that helper on that path is `not_readable`, for every
   reader (the walk's guard, `resolve_positions_on_paths`; ruled 2026-11-25; the exact
   answer is OI-558).
   `values.py:16-28`; `TV:1953`; mounts `TM:223`; Python `FP:313`.
2. **Follow the value through all code we have**: parameters to callers, returns to callees,
   fields to their writes, a hand-off into module code. Unknown starts only where code is
   absent (`external`).
3. **Enumerable is exact.** Members that are written constants give one path each. A set that
   cannot be listed gives ONE `unresolved`, stated, never dropped and never guessed.
4. **No model of a library method's semantics.** Nothing knows what `substring`, `trim` or
   `format` does. `x` merged with `f(x)` answers the root `x`, `inexact` (`values.py:4137-4150`;
   `TV:3346`). The declared exceptions are data: `identified_by` entries in
   `catalogs/value-models/` (which argument of a producing call carries the value).
5. **A call on a branch is not a call on every path.** One branch call gives two exact rows;
   two or more make every row `partial` (`values.py:3505-3535`; `TV:6364`, `TV:6382`).
6. **A field is read per object and per write** (`TV:4428`, `TV:4441`).
7. **A value handed to code we do not have `escapes`.** An immutable value (a string) is never
   a hand-off (`TV:5562`, `TV:5599`). In Python too (ruled 2026-11-26): a parameter written
   `str`, `bytes`, `int`, `float` or `bool`
   (`tests/application/test_environment_reads.py::test_a_text_parameter_joined_into_another_text_is_still_read`).
   A parameter with no written type is OI-497.
8. **What a deployment can change is "not evaluated"**: the row exists and its condition is
   stated (`tests/application/test_bean_conditions.py:2826`†; Python
   `tests/application/test_fastapi_conditions.py:59`). A test on a value the code fixes is
   not something a deployment can change: it is decided (ruled 2026-11-25, row in "Branches").
9. **Framework behaviour is mirrored, measured by a probe** (a refused mount gives no row).
10. **Caps answer `non_enumerable`**: 256 paths in one window, 25,000 computes per root, depth
    80 (`values.py:349-371`; `TV:6558`; `tests/application/test_walk_cost.py:170`, `:237`).

## Scenarios

### Constants and text

| Scenario | Answer | Evidence |
|---|---|---|
| Literal at the call site | `literal` | `TV:3042` |
| Class reference, enum constant | `literal`, kind `symbol`, never text | `TV:3042`, `TV:2846` |
| Field written from a constant | the constant | `tests/e2e/test_kafka_delivered.py:95` (Java); `FR:291` (Python) |
| Static field | one value for every reader | `TV:3825` |
| Concat, every part a literal | ONE joined `literal` | `TV:2981` |
| Concat, one part unknown | `expression` with the hole kept | `TV:3009`; Python prefix hole `<prefix>/x` at `partial`, `FP:410` |
| Concat hole with several callers | one answer per caller | `TV:4702`, `TV:4725`; `FP:313` |
| `${KEY}` placeholder, environment read | `expression` `${KEY}`; a key that is not a literal is `non_enumerable` | `TV:4714`†; `tests/application/test_environment_reads.py:44` (Python only) |
| A read of a setting on the framework's settings object (`settings.API_HOST` on `django.conf.settings`; the role of `@Value("${k}")` and of a pydantic settings field) | `expression` `${API_HOST}`: the configuration key of that name (value-model `key_reads`, ruled 2026-11-25). No settings module's literal is the answer: the deployment selects the module. Each module's value is a `resolved_config` row of its environment. A route path built from a key and a text (`path(settings.API_PREFIX + 'u/', v)`, an environment read too) is `unresolved` today, the text lost (OI-571) | `tests/application/test_django_settings.py::test_a_read_of_a_django_setting_is_its_key` (Python only) |
| `"/<org>{}".format(x)` on a literal | a template, read as a concat: `expression` with `x` as its part (ruled 2026-11-23). By name too (`"{a}".format(a=x)`). A conversion or format spec the reader does not model (`{0!r}`, `{:>8}`) leaves the value unread, as before. So does a text that holds `{}` (`'{{}}/{}'.format(x)`, an f-string too): the template's holes are `{}` (OI-519) | `tests/ingress/extract/python/test_calls.py::test_format_on_a_literal_is_its_template`, `::test_format_the_reader_does_not_model_is_unread`, `::test_a_template_whose_text_holds_braces_that_are_no_hole` (Python only) |
| Any other transforming call used as the value (`old_url.lstrip("/")`) | rule 4: no model of the library method; `x` merged with `f(x)` answers the root `x`, `inexact` | `tests/application/test_values.py::test_a_merge_of_a_parameter_and_a_call_on_it_resolves_to_every_caller_inexactly` |

### Helpers

| Scenario | Answer | Evidence |
|---|---|---|
| Value passed as a parameter, one caller | the caller's value | `TV:1970`; `FR:510` |
| Several callers | one binding per caller (rule 1) | `TV:1953`; `FP:313` |
| Deep chain of helpers | followed as deep as the code goes (caps: rule 10) | `TV:3053` |
| No caller in the module | `external` | `TV:2511` |
| Recursion | `cycle` | `TV:2965` |
| Parameter left to its default | Python: the default value (`tests/application/test_values_defaults.py:43`). Kotlin bridge: a reason, never the pushed mask (`TV:3110`) | both |
| Helper returns the value | the value | `TV:2040` |
| Several returns | one path per return. A return under a test decided false on the path is not taken (Python, `method_return.guards`, ruled 2026-11-25; row "A test on a value the code fixes" in "Branches") | `TV:1981`; `tests/application/test_django_verbs.py::test_a_return_under_a_test_not_decided_stays_one_path_per_return` |
| Helper changes the value, then returns it | `escapes` for a plain value | `TV:2025` |
| Factory sets a part on one branch, then returns | two exact rows | `TV:6464` |
| Helper builds, mounts and returns a router; called twice | each route under its own caller's prefix | `TM:223`; `FP:313`, `:429` |
| A mount call inside a helper | each caller's route takes that caller's mount path | `TM:439` |
| A helper's router mounted by one caller only | both ways are served (rule 3) | `TM:389` |

### Branches

| Scenario | Answer | Evidence |
|---|---|---|
| Two literals on two branches | both, each `narrowed` | `TV:3361` |
| A literal and a non-literal | ONE `non_enumerable` | `TV:3444` |
| `x` or `f(x)` | the root `x`, `inexact` | `TV:3346` |
| A registration under a test a deployment decides | row exists, condition "not evaluated"; each call of a helper takes its own test. A write to a name under a test carries the same record as a call (`field_write.guards`, ruled 2026-11-25): a value read through that write is read on a path that names it (`Path.written_under`). A verb read through such a write (`if T: VERBS += MORE`, `methods=VERBS`) gives its row that condition, never a `resolved` row with none. A value read through a `return` under a test not decided (`if w: return ['get', 'post']`) is named on the path the same way and gives its row the condition (`::test_a_value_read_through_a_return_under_a_test_carries_the_test`); a value in both arms carries both tests (OI-564) | `tests/application/test_fastapi_conditions.py:59`, `:260`, `::test_a_verb_added_to_a_held_list_under_a_test_carries_the_test`; `tests/ingress/extract/python/test_guards.py::test_a_field_write_carries_the_tests_it_runs_under` (Python only; the JVM writes no test record, OI-552) |
| A test on a value the code fixes (`def create_app(database)`: `if database: ...`, callers pass `True` and `False`; `DEV = False`, `if DEV: urlpatterns += ...`) | decided (ruled 2026-11-25, R2), per path: where the test is one name (`if x:`), `not x`, `x is None` or `x is not None` (`guards[].value`, `when`), and the walk gives the name exactly ONE written literal on the path (each caller is its own path, rule 1). The truth is the language's: `None`, `False`, `0`, `""`, an empty written list are false; a function or a class is true. Decided true: no condition from that test on that path. Decided false: the call, the write or the `return` gives nothing on that path. NOT decided, "not evaluated" as before: a name an environment read, a configuration key, a settings field or `${...}` gives; a name with several values on one path (two writes, a branch, a loop variable; an addition to a held list is a write, `api = []`, `api.append(v)`, `if api:`, and the count is of every write of the name, whatever element of it the row reads); a member of a list; an object built from a class; a value read through a write under a test; every other form (`==`, `in`, `isinstance`, `and`, `or`). A parameter is read as the method was entered with it; an empty list in a parameter decides nothing. A module name written `None` is not decided (its write reads `not_readable`). The test of a WRITE is decided within cost bounds (OI-563): for a name read on the shared upward path, where a caller or a write gives the tested value a literal one step away. A value that comes from a write a star import of its module can replace (`DOCS = False`, `from .local_config import *`; a star source not read; a star in a `try`) decides nothing, however far it travels to the test: through a parameter (`create_app(config.DOCS)`), a local name, a second module name, a return (ruled 2026-11-25, R10; the scan fact `field_write.replaceable`, read by the decide step alone, so a plain read of the value is not changed, OI-565). A name star imports alone give is decided on the last star that gives it, unless a star of the module is not read or the source's own value can be replaced. The arm a constant test or `TYPE_CHECKING` never runs is decided false by the same rule (OI-562) | `tests/application/test_fastapi_conditions.py::test_a_test_on_a_value_each_caller_fixes_is_decided_per_caller`, `::test_a_registration_under_a_test_decided_false_on_every_path_gives_no_row`, `::test_a_test_on_a_value_not_fixed_stays_not_evaluated`, `::test_a_star_import_that_binds_the_tested_name_decides_nothing`, `::test_a_star_import_of_a_module_not_read_decides_nothing`, `::test_a_star_import_that_does_not_bind_the_tested_name_leaves_it_decided`, `::test_a_value_a_star_import_can_replace_decides_nothing_at_any_depth`, `::test_a_value_no_star_import_can_replace_is_decided_at_any_depth`, `::test_a_name_star_imports_alone_give_is_decided_on_the_last_that_gives_it`, `::test_a_plain_read_of_a_value_a_star_import_can_replace_is_not_changed`; `tests/ingress/extract/python/test_calls.py::test_a_write_of_a_name_a_star_import_can_replace_says_so`; `tests/application/test_django_includes.py::test_a_list_added_under_a_test_the_code_fixes_is_decided`, `::test_a_test_on_a_list_written_more_than_once_is_not_decided`, `::test_a_test_on_an_empty_list_never_written_again_is_decided`; `tests/ingress/extract/python/test_guards.py::test_a_test_of_one_value_states_the_value_and_when_it_is_true` (Python only; Java is OI-553) |
| A test on a setting (`if settings.DEBUG: urlpatterns += ...` on `django.conf.settings`; the role of `@ConditionalOnProperty`) | the row exists, its condition is kind `property` on the key `DEBUG`, and each environment's value (each settings module's) is the evidence. Decided PER ENVIRONMENT (ruled 2026-11-25, R3, the approved note), the way a `@Profile` condition is decided in its own environment: where the test has one of the forms of a decided test (`x`, `not x`, `x is None`, `x is not None`), the environment's settings module gives the key exactly one written literal, and no door is in its chain. True in one environment and false in another is the normal case. A door: an environment read; a write a star import can replace (`field_write.replaceable`, R10) anywhere in the chain of settings modules the key is read through; a module that runs a text as its own code (`exec(code)`, the same mark on every name it writes); a value that is not one literal (a list, two writes). Then "not evaluated" as before (rule 8; ruling 2026-10-23), and the evidence of a key the module writes with no one value is the detail of its `resolved_config` row ("sets no readable value: `APPS` has 2 values in this module (a list, or a write under a test): not one value"), never "a placeholder this module does not fill". A key the settings module writes beside a star import that binds it too (`from .base import *`, then `DEBUG = True`) is not decided: the order of the two is not read (OI-565). No row is removed and none is copied per environment | `tests/application/test_django_settings.py::test_a_test_on_a_setting_is_decided_per_environment`, `::test_a_test_on_a_setting_is_decided_in_the_forms_of_a_decided_test`, `::test_a_test_on_a_setting_with_a_door_in_its_chain_is_not_evaluated`, `::test_a_setting_a_star_import_alone_gives_is_decided_on_its_source`, `::test_a_setting_written_with_no_one_value_says_why_in_the_evidence`; `tests/egress/test_render_conditions.py::test_a_test_decided_in_an_environment_states_where_the_row_exists` (Python only) |
| The routes of a root (`ROOT_URLCONF = 'app.urls'`) | each row reached through the root has the condition "`ROOT_URLCONF` is `app.urls`", kind `property`, "not evaluated", with what each environment sets as evidence (ruled 2026-11-25, R3). Two settings modules naming one root give one condition | `tests/application/test_django_settings.py::test_the_routes_of_a_root_exist_where_the_root_setting_names_it`, `::test_two_settings_modules_naming_one_root_give_one_condition` |

### Lists and arrays

| Scenario | Answer | Evidence |
|---|---|---|
| Every element a written constant | one path per element | `TV:1990` |
| Empty list, explicit null | `absent` | `TV:2946` |
| One member has no name | the readable members plus ONE trailing `not_readable` | `TV:2000` |
| The array was not read at all | ONE `non_enumerable` | `TV:2049` |
| Varargs, `List.of("a","b")` | one array argument; one row per element | `TV:2767`, `TV:2746` |
| Unpacked argument (`*rest`, `**options`) | the parameter it may fill is `not_readable`, not the default | `tests/application/test_values_defaults.py:93` (Python only) |
| **A list held in a module name, used later** (`VERBS = ['get']`, `methods=VERBS`) | Ruled 2026-11-23, built (plan 2026-11-23-python-django-redesign Tasks 2–6): the list answers with its members, one path each, as an array written in place does. A name written as another list (`Y = X`) is followed. The members of one written list do not count against `PATH_CAP`, by its own name or another; the alternative writes of a name read through another name do (OI-517). A list whose exact values are not known keeps a reason (rows below) | `tests/application/test_values.py::test_a_list_held_in_a_field_answers_with_its_members`, `::test_a_name_for_another_list_is_followed`, `::test_the_members_of_one_held_list_do_not_count_against_the_path_cap`, `::test_a_second_name_for_a_long_list_reads_every_member`, `::test_the_alternatives_a_second_name_reads_count_against_the_path_cap`; `tests/application/test_fastapi_routes.py::test_a_verb_list_held_in_a_module_name_is_read` (Python only) |
| A copy of a list (`B = list(A)`, `[*A]`) | the scanner writes `[*A]` with the members `A` holds at that line: a member added to `A` later is not in the copy. A name written under a test or in a loop has no one value from there on, so a later copy stays a read of the name (every write of it). An unpacked `*x` whose value is reached through no list or tuple element (`list(S)`, `S = 'get'`) is `not_readable`: its members are characters no fact names |  `tests/ingress/extract/python/test_calls.py::test_list_of_a_value_is_the_list_of_its_members`, `::test_a_copy_of_a_module_list_holds_the_elements_at_its_line`, `::test_a_name_written_under_a_test_or_in_a_loop_keeps_its_read`; `tests/application/test_fastapi_routes.py::test_a_verb_list_held_in_a_module_name_is_read` |
| An addition to a held list (`x.append(v)`, `x.extend(vs)`, `x += other.attr`, `x = f() + b`) | written as the list `[*x, v]`, `[*x, *vs]`: known, not a reason. Only on a name this file writes as a list; `count += 1` stays a number | `tests/ingress/extract/python/test_calls.py::test_append_and_extend_on_a_module_list_are_writes`, `::test_a_sum_onto_a_list_name_is_a_list` |
| Any other call on a held list (`remove`, `pop`, `clear`, `insert`, `sort`, `reverse`), an element store `x[i] = v` or delete `del x[i]` | `escapes` for the list: it is not exactly known. The scanner writes an element store and delete as the calls the language makes, `__setitem__` and `__delitem__`, an element inside a tuple target too (`x[0], b = v`, `del (x[0], b)`). Limit: a store two levels down (`x[0][1] = v`) shows no call on `x` (OI-515). A read the language makes (`__iter__`, `__getitem__`, `in`, `len`) keeps the members | `tests/application/test_values.py::test_a_call_on_a_held_list_that_is_not_a_write_makes_it_not_known`, `::test_a_read_the_language_makes_on_a_held_list_keeps_its_members`; `tests/ingress/extract/python/test_calls.py::test_an_element_store_and_delete_are_the_calls_the_language_makes`, `::test_an_element_inside_a_tuple_target_is_stored_or_deleted` |
| A held list passed whole as an argument (`keep(VERBS)`) | still read (ruled 2026-11-23): the walk tracks no hand-over of a field, in Python as in Java. Where the body it is handed to is read and makes a call on the parameter it fills that is not a read (`def keep(v): v.append(x)`), there or in a body it hands that parameter on to, the list is `escapes`, as a call made on it by name (OI-510) | `tests/application/test_values.py::test_a_held_list_handed_to_a_call_is_still_read`; `tests/application/test_fastapi_routes.py::test_a_verb_list_held_in_a_module_name_is_read` |
| A held list changed through a second name (`VERBS = BASE`, `VERBS.remove(v)`) | not known by either name (`escapes`): it is one list (OI-516) | `tests/application/test_values.py::test_a_list_changed_through_a_second_name_is_not_known_by_that_name`, `::test_a_list_changed_through_a_second_name_is_not_known_by_its_first`; `tests/application/test_fastapi_routes.py::test_a_verb_list_held_in_a_module_name_is_read` |

### Loops

| Scenario | Answer | Evidence |
|---|---|---|
| A value built in a loop | `not_readable`; the facts carry no "this was a loop" claim | rule at `values.py:4337-4341`; **no test** |
| A setter after the use, in the same loop | two rows: unset `resolved`, set `partial` | `TV:6581` |
| A comprehension | recorded as a loop (flow only) | `tests/ingress/extract/python/test_flow.py:303` |

### Fields, builders, callables, inheritance

| Scenario | Answer | Evidence |
|---|---|---|
| Field assigned from a constructor parameter, class built twice | one row per construction | `tests/e2e/test_kafka_delivered.py:61` |
| Constructor that nothing calls | `external` | `TV:2218` |
| Field read on an object from outside | `external`; never another object's value | `TV:3792` |
| Builder handed to a helper in the module | the helper's calls join the chain | `TV:5522` |
| Builder handed to code we do not have | `escapes` | `TV:5562` |
| Chain started in a helper, sent by the caller | one row, the caller's | `tests/application/test_call_engines.py:7102` |
| Lambda body reads a captured value | the captured value | `TV:2247` |
| A Python nested function or `lambda` reads a name of its enclosing function | the captured value, as for a Java lambda. The scanner writes the capture (a `dynamic` site `types/FunctionType#<init>`, `captures: N`); in a Python body the captured values sit after the written parameters (ruled 2026-11-23). A function handed to a call and one only returned (`return w`) are captured alike, where they are made. A name written again after the `def`, or written by a loop the `def` is in (each pass writes it again, OI-535), is captured `unresolved`. A name a function nested deeper holds itself (its parameter, a function it defines) is no capture of the functions around it (OI-536) | `tests/ingress/extract/python/test_calls.py::test_a_nested_function_captures_the_outer_names_it_reads_after_its_parameters`, `::test_a_name_written_again_after_the_def_is_captured_unread`, `::test_a_name_a_loop_writes_is_captured_unread_by_a_def_in_the_loop`, `::test_a_name_a_deeper_function_holds_itself_is_no_capture_of_the_middle`; `tests/application/test_values.py::test_a_python_body_reads_its_captured_value_where_the_function_was_made`; `tests/application/test_receiver_binding.py::test_the_wrappers_call_of_its_argument_reaches_the_decorated_function` |
| A wrapper that hands the request on (`@wraps(f) def inner(request, *a, **k): return f(request, *a, **k)`) | stands for the function it wraps: the handler is `f`, never `inner`. Where the captured function is not read, the answer is a reason, never the wrapper. The call's result must go into what the body returns, as it is or inside it (`return JsonResponse(f(request))` is `f`). What is called may be what a call on the captured function gives (`return log(f)(request)`): what runs is read through that call, and a reason where the call is not read. A call whose result is only tested (`if test(request):`) or not used (`logger(request)`) is no hand-over, and a body with no hand-over is itself what runs. One wrapper entered again on one path by another call of it (`@guard('a') @guard('b')`, `log(log(view))`) is read once per call: only the same position under the same innermost call is `cycle` (OI-537). Each module wrapper the request runs through is a `roots` row at the route's address, `inbound_endpoint`, as a recipe the framework runs first is, so its own calls are on the route's trace (OI-534) | `tests/application/test_receiver_binding.py::test_a_decorator_whose_wrapper_calls_what_it_captured_runs_the_wrapped_function`; `tests/application/test_values.py::test_a_wrapper_that_hands_its_unpacked_arguments_on_stands_for_the_wrapped`, `::test_a_wrapper_whose_captured_function_is_not_read_never_names_the_wrapper`, `::test_a_wrapper_that_wraps_what_its_captured_function_gives_stands_for_it`, `::test_a_wrapper_whose_return_takes_two_captured_functions_results_stands_for_both`, `::test_a_captured_function_whose_result_is_not_used_is_no_hand_over`, `::test_a_wrapper_that_calls_what_a_call_on_its_captured_function_gives_stands_for_it`, `::test_a_wrapper_that_calls_what_an_unread_call_on_its_captured_function_gives_is_a_reason`, `::test_one_wrapper_entered_twice_on_one_path_stands_for_the_view`, `::test_one_decorator_factory_applied_twice_stands_for_the_view`, `::test_a_recursive_wrapper_is_a_cycle`; `tests/application/test_django_verbs.py::test_one_decorator_factory_applied_twice_to_one_view_names_the_view`, `::test_a_module_wrapper_the_view_runs_through_is_a_root_at_the_address` |
| A method decorator applied inside a project decorator or held in a name (`return csrf_exempt(require_POST(f))`, `get_or_post = require_http_methods([...])`) | read on the path the value walk takes to the view: each stated call the walk passes is on the path (`Path.passed`), and the `annotations` among them narrow the row; a list argument they take (`require_http_methods(ms)` in `only(ms)`) is read on that same path, so each view gets its own call's list. A path that passed such a call under two calls of the helper holding the list holds the first alone (`Path.entered_twice`): the list is not read (the walk's guard, rule 1, the same for every reader of a value on that path), one row naming no method, `unresolved`. Paths that allow different methods make every row `partial` | `tests/application/test_django_verbs.py::test_a_project_decorator_that_applies_require_post_narrows`, `::test_a_held_require_http_methods_decorator_narrows`, `::test_require_post_on_one_branch_of_a_project_decorator_is_partial`, `::test_one_project_decorator_factory_on_two_views_narrows_each_by_its_own_list`, `::test_one_project_decorator_factory_applied_twice_reads_no_method`; `tests/application/test_values.py::test_a_value_read_through_a_helper_the_path_entered_on_two_calls_is_not_read` |
| A decorator made in one method and applied in another (`d = user_passes_test(t)` in a helper, `d(view)` in its caller) | the call that made the decorator is looked up in the value models: the result is the argument it is applied to | `tests/application/test_values.py::test_a_decorator_a_library_made_in_a_helper_and_applied_in_its_caller_is_its_argument` |
| A library class's method body (`class MyView(LoginRequiredMixin, View)`) | read where a module class extends the library class (every class in the lookup order, a nested one (`lib.Outer.Inner`) too (OI-545); ruled 2026-11-23, option B), as a module method is: `super().dispatch(...)` in a library `dispatch` is the `special` call. Rows that come from those bodies are not the module's: the borrowed-rows rule drops them, unless the module opts into that library (`extract_libraries`): then the body is in the library's own document too and its rows are published (ruled 2026-11-25, R9; `tests/application/test_python_outbound.py::test_an_opted_in_librarys_outbound_call_is_published`). A library class no module class extends stays unread: its verbs give `partial` rows, and a class of no verb method gives its unread `dispatch`'s any-method row, `partial` (OI-549) | `tests/ingress/extract/python/test_libraries.py::test_a_library_class_in_a_lookup_order_has_its_method_bodies_read`, `::test_a_nested_library_class_in_a_lookup_order_has_its_method_bodies_read`; `tests/application/test_django_class_views.py::test_a_library_dispatch_that_calls_its_parent_on_one_branch_keeps_the_verbs`, `::test_a_library_class_no_module_class_extends_keeps_its_dispatch_unread`, `::test_an_unread_library_dispatch_on_a_class_of_no_verbs_is_its_any_method_row`; `tests/application/test_python_outbound.py::test_a_session_subclass_publishes_only_the_modules_own_calls` |
| A class view below a base not read (`class V(Mixin, TemplateView)`, `Mixin` not read; `V.as_view()`) | `as_view` is read through the one stated type among the read ancestors, `inexact`. Past the type not read, the read types' own C3 order (that type taken as having no parents) gives the verb methods: one row per verb, its handler the method (`TemplateView.get`), every row `partial` since the type not read may define them. Where no read type gives a verb, one any-method row naming no handler, `partial` (OI-541) | `tests/application/test_django_class_views.py::test_a_class_whose_base_is_not_read_is_partial`, `::test_a_verb_of_a_library_base_past_a_base_not_read_is_partial`, `::test_no_member_found_past_a_base_not_read_names_no_method` (Python only) |
| A handler that is an object (`path('rss', Feed())`) | a call of an object runs its class's `__call__`, the first in the class's lookup order (a library base's whose body was read too): that method is the handler. Where the order meets a type not read first, no handler, `partial` (OI-539) | `tests/application/test_django_class_views.py::test_a_view_object_names_its_class_call_method`, `::test_a_view_object_of_a_library_class_names_the_librarys_call_method`, `::test_a_view_object_below_a_base_not_read_names_no_handler` (Python only) |
| Handler as a method reference with two implementations | one `narrowed` row each | `tests/application/test_pass_through.py:971`† |
| A decorator written in the module that returns its function | walked into; handler `resolved` | `FR:438` (Python only) |
| A library wrapper a value model states (`functools.wraps`) | `result_returns` / `result_calls` in `value-models/python-wrappers.yml` | model file |
| A decorator usable bare or with arguments (`def lr(function=None, x=1)`: `if function: return actual(function)`; `return actual`) | the view alone, both uses (ruled 2026-11-25, R5). Project copy: which `return` runs is decided on the path (`method_return.guards`, the row "A test on a value the code fixes"): with `@lr` the parameter holds the view, a function, true; with `@lr(x=2)` or `@lr()` it holds its default `None`, false. `actual` as a `def` or a `lambda`. Library copy (`login_required`, `staff_member_required`): the value-model entry states both forms of argument 0, `result_calls` where the call writes it and `result_returns` where it does not (D02 §1f). A test not decided keeps one path per return | `tests/application/test_django_verbs.py::test_a_decorator_usable_bare_or_with_arguments_names_the_view`, `::test_a_decorator_that_hands_back_a_bare_function_on_one_path_names_both`, `::test_a_stated_decorator_called_without_the_view_hands_the_view_on`; `tests/application/test_entry_point_roots.py::test_the_loader_reads_the_two_uses_of_one_argument`; `tests/ingress/extract/python/test_guards.py::test_a_return_carries_the_tests_it_runs_under` (Python only) |
| A library decorator no model states | row `partial`, handler NULL, question `handler_pass_through` | `FR:602` |
| Inherited mappings | each concrete class's rows, each with its own prefix | `tests/e2e/test_rest_inbound_delivered.py:2059`† |

### Mounts and prefixes

| Scenario | Answer | Evidence |
|---|---|---|
| Mount with a string prefix | the router's routes serve under it | `TM:290`; `FP:45`; `tests/application/test_flask_prefixes.py:29` |
| Nested mounts | prefixes compose, outermost first | `TM:315`; `FP:83` |
| **A mount of a router the module does not build** (a library's router) | **adds nothing: no prefix, no row, no question** | `TM:270`; `FP:266` |
| A router that is never mounted | served at its own prefix | `FP:249`; `TM:270` docstring |
| A router mounted twice | one row per mount | `FP:231` |
| A router handed in as a parameter and mounted here | one object; served under the mount only | `TM:485` |
| A prefix that cannot be read | the named hole `<prefix>/x` at `partial`, question `mount_prefix`; never the empty prefix | `FP:410`; Java `TM:552`† |
| A mount the framework refuses | no row, or the refusal is recorded (rule 9) | `TM:449`, `TM:528`; `FP:161` |
| A router factory in another file; a router subclass | the prefix is held | `FP:125`, `FP:335`; `TM:562`† |
| A call that returns its receiver | the same router | `TM:462` |
| A registration made on nothing (Django `path()` in a list) | joined top-down: from each root (the module a written `ROOT_URLCONF` names, catalog word `root_setting`) and through each mount (`path(p, include(x))`), the members of the lists are read by the value walk, each under its mount's prefix. A list that no root and no readable mount reaches is published behind the hole `<prefix>/x` at `partial` with `mount_prefix`, never at the root; a repository with no written root has no `resolved` row; a call into code that is not read that takes a route list (as an argument, unpacked `*x` too) and whose result is read as a route list (`i18n_patterns(*x) + urls`) is a mount whose prefix is not read: the lists it takes are behind the hole `<prefix>/x` at `partial`, with `mount_prefix` naming the call, also where a root reaches them another way (ruled 2026-11-24, OI-550). A call, mount or module already open on the read's path is not entered again (the walk's `cycle`): `urlpatterns = f(urlpatterns)` keeps the earlier write's rows, and a module that includes itself gives its own rows only (OI-530). A mount written under a test gives its routes that condition; so does a list added under a test (`if T: urlpatterns += dev.urlpatterns`, `urlpatterns = urlpatterns + other`) and a root written under a test (`if T: ROOT_URLCONF = 'b'`): the routes are at their real address, "not evaluated", read from the test record of the write (`field_write.guards`, ruled 2026-11-25, OI-508, OI-509) | `tests/application/test_django_includes.py::test_the_root_is_the_module_root_urlconf_names`, `::test_a_list_no_mount_and_no_root_reaches_is_the_hole`, `::test_a_repository_with_no_root_urlconf_has_no_resolved_row`, `::test_a_library_call_that_takes_the_list_is_a_mount_whose_prefix_is_not_read`, `::test_a_call_already_open_on_the_read_is_not_entered_again`, `::test_a_module_that_includes_itself_is_read_once`, `::test_a_mount_written_under_a_test_gives_its_routes_the_condition`, `::test_a_list_added_under_a_test_gives_its_routes_the_condition`, `::test_a_list_added_under_a_test_in_a_mounted_module_keeps_the_mount_and_the_test`, `::test_a_root_setting_written_under_a_test_gives_its_routes_the_condition` (Python only) |
| A mount of a library's URL module (`include("django_scim.urls")`) | adds nothing, as a mount of a router the module does not build | `tests/application/test_django_includes.py::test_a_mount_of_a_library_module_adds_nothing` |

### More rows of the same rules

| Scenario | Answer | Evidence |
|---|---|---|
| A field written from a constant the walk has no literal kind for | `not_readable`; the site is kept | `TV:2304` |
| Concat with no part filled | `expression`, the template verbatim | `TV:2972` |
| Compiler-inserted `String.valueOf(obj)` in a concat | passed through only for an identity that yields an authority (`value-models/jdk.yml`, `preserves: authority`) | `TV:2555` |
| One position reached two ways | two bindings, two paths | `TV:3062` |
| Return through an interface with two implementations | listed as a branch, neither picked | `tests/application/test_return_flow.py:145` |
| Return through a call whose dispatch nothing names | `not_readable` (not `external`) | `TV:2057` |
| One branch read twice (`p + "/x/" + p`) | `(/a,/a)` and `(/b,/b)`, never crosswise | `TV:3395` |
| A value below the top level of an argument handed out | `escapes` | `TV:5780` |
| An object built again each time round a loop | unset row exact; set row `partial` | `TV:6625` |
| For-each over a Kotlin channel | a receive (dispatch, not a value) | `tests/application/test_dispatch_kotlin_channels.py:94`† |
| No reported write of a field | `no_writer` | `TV:2206` |
| A setter on an object of unknown origin | the value is kept, `inexact`, beside the exact one | `TV:4506` |
| A field written from a call's result | the walk crosses to the call; a library factory is `external` | `TV:2325` |
| An undeclared call ON the value before its use | `escapes` | `TV:2072` |
| Declared configuring calls, calls that return their receiver | they join the value's chain in order | `TV:2162` |
| A hand-off with two callees | two paths, one chain each | `TV:5611` |
| A symbol answer past a hand-off (identity is not content) | survives `escapes` / `cycle` | `TV:2090`† |
| A send helper that sets the address itself | row `partial` | `tests/application/test_call_engines.py:9259` |
| A value stored in a field inside the body, or captured by a lambda that acts | `escapes` | `TV:5592` |
| A producer the identity table names (`URI.create(..)`) | the producer's own argument is the value | `TV:2598`, `TV:2618` |
| A handler object whose class is not scanned | `external`; scanned with no handler: `not_readable` | `tests/application/test_pass_through.py:564`† |
| A lambda as the VALUE of an argument | `not_readable` | `TV:2937` |
| A bound method reference | the target's parameter is `external`, never the captured receiver | `TV:2295` |
| A wrapper (Java) that calls what it wraps through an interface a lambda implements | `escapes`; through an interface no lambda implements: walked into | `TV:5801` |
| `next()` on a received context (Vert.x) | passes the request on | `tests/application/test_pass_through.py:662`† |
| A handler declared as a module type | runs every override below it | `tests/application/test_pass_through.py:472`† |
| A router built in a base class, routes added in an override, mounted by a third method | served under the mount | `TM:177` |
| A parameter the container fills (DI recipe) | the recipe's return; a recipe in unscanned code is `external` | `tests/application/test_fastapi_depends.py:90` |

### Dispatch (existing, not a value walk)

| Scenario | Answer | Evidence |
|---|---|---|
| Dispatcher keyed by message class (Akka) | a send reaches the first matching registration | `tests/application/test_dispatch_registrations.py:187`† |
| Dispatcher keyed by object (a queue) | linked when it is one object | `tests/application/test_dispatch_objects.py:92`† |

## Which handler answers

When a framework hands a request to a handler and that handler gives the request it received
to another handler, the row belongs to the handler that answers
(`src/sextant/application/resolve/shapes/pass_through.py`). There are three outcomes, each
about one handler:

- it **passes on**: the request it received is handed to the next handler, in its own body,
  in a module method it calls, or in a lambda that captured it;
- it **answers**: its body is read and nothing above is reached;
- it is **not readable here**: the request is handed to code that is not read, or stored
  where the walk cannot follow it. The row is `partial`.

Tests, in `tests/application/test_pass_through.py`:
`test_a_next_on_the_received_context_passes_on`,
`test_a_context_handed_to_another_handler_passes_on_with_it`,
`test_a_context_handed_to_a_body_outside_the_module_is_unreadable`. Vert.x states the call
with the catalog word `passes_on`. A Django view that calls another view with its `request`
has the same role (ruled 2026-11-23).

**"Any method"** (ruled 2026-11-23, built in plan 2026-11-23-python-django-redesign Task 7a).
A row that serves every method (`verbless_serves: any`) says the endpoint answers every
method. It is `resolved` only when nothing in the code doubts it. It is `partial`, method not
read, when the handler or a wrapper the path ran through reads the request's method (a
`request_reads` entry of kind `method`, only `django.yml` declares one), in its own body or in
module code it hands the request to; when it hands the request to another view; or when its
body was not read. A request handed only to a library function (`render(request, ...)`) is
no doubt. Example: `def v(request): if request.method == "POST": ...` gives one row, method
NULL, `partial`. The row's question `not_read` (ruled 2026-11-25, R4) names the column
`method`, the reason and the code: `not_readable` at the call that reads the method (or at
the registration, where the row names no handler), `external` at a library handler whose
body was not read. One question per wire identity. Tests:
`tests/application/test_django_verbs.py::test_a_view_that_reads_request_method_files_a_not_read_question`,
`::test_a_helper_that_reads_the_method_is_the_code_the_question_names`,
`tests/application/test_django_class_views.py::test_an_unread_library_dispatch_files_a_not_read_question`,
`tests/application/test_django_verbs.py::test_a_view_that_reads_request_method_is_partial`,
`::test_a_view_that_hands_its_request_to_a_helper_that_reads_the_method_is_partial`,
`::test_a_view_that_calls_another_view_with_its_request_is_partial`,
`::test_a_view_that_hands_its_request_only_to_a_library_function_is_resolved`,
`::test_a_wrapper_that_reads_no_method_keeps_the_row_resolved`.

## Catalog-level roles (survey of 2026-11-23)

Every row names the existing word and one catalog line. The survey read the catalogs and the
format document; a test named here is a name match unless a table above cites it.

### Role → existing catalog word(s)

| role | word(s) | style | example |
|---|---|---|---|
| method fixed by the registration call | `captures.http_method: GET` | fluent | `src/sextant/catalogs/flask.yml:44-45` |
| method fixed by the rule | `verb: GET` | combinator | `src/sextant/catalogs/ktor-routing.yml:313` |
| method fixed by the annotation type | `annotations[].method: [GET]` | annotation_driven | `src/sextant/catalogs/spring-mvc.yml:163` |
| method from an attribute of the annotation | `method_from` | annotation_driven | `src/sextant/catalogs/spring-mvc.yml:116`; `src/sextant/catalogs/quarkus-reactive-routes.yml` `method_from: methods` |
| method from a keyword/list argument | `http_method: { keyword, absent, case }` | fluent | `src/sextant/catalogs/flask.yml:43` |
| method from one argument (enum/field) | `http_method: argN` + `verb_values.fields` | fluent | `src/sextant/catalogs/vertx-web.yml:111-112, 66-97` |
| method from one argument | `verb_arg` + `verb_values.{fields,getters}` | combinator | `src/sextant/catalogs/ktor-routing.yml:255, 282-300` |
| method added by a later chained call | step `captures.http_method` + `repeats` | fluent | `src/sextant/catalogs/vertx-web.yml:173-174` |
| method set for a whole nested block | prefix rule with `verb_arg` | combinator | `src/sextant/catalogs/ktor-routing.yml:254-255` |
| method = handler's method name | `dispatch: [{name, parameters, method}]` | supertype_dispatch | `src/sextant/catalogs/jakarta-servlet.yml:123-144` |
| no method -> closed list, one row each | `all_methods: [...]` | annotation_driven, combinator | `src/sextant/catalogs/spring-mvc.yml:157`, `src/sextant/catalogs/ktor-routing.yml:237` |
| no method -> ONE row "any" | `verbless_serves: any` (column `method_kind`) | fluent, annotation_driven | `src/sextant/catalogs/vertx-web.yml:51`, `src/sextant/catalogs/quarkus-reactive-routes.yml:56` |
| no method at all, never fanned out | `verb: none` (+ `registered_verb`) | combinator | `src/sextant/catalogs/ktor-routing.yml:334-335` |
| empty method list is an error | (engine) `refused_registration` / `no_methods` | fluent | `src/sextant/application/resolve/engines/fluent.py:1324-1326` |
| no path -> every path | `pathless_serves` | fluent | `src/sextant/catalogs/vertx-web.yml:55` |
| route text is a regex | `url_is: pattern` / `pattern_from` (column `path_kind`) | fluent / annotation_driven | `src/sextant/catalogs/vertx-web.yml:114`, `src/sextant/catalogs/quarkus-reactive-routes.yml:62` |
| framework refuses a path with no `/` | `refuses_unrooted_path` | fluent | `src/sextant/catalogs/vertx-web.yml:61` |
| handler = argument | `handler: argN`/`{arg, keyword}`; `handler_arg` | fluent; combinator | `src/sextant/catalogs/flask.yml:56`; `src/sextant/catalogs/ktor-routing.yml:313` |
| handler = decorated function | step `{ method: __call__, captures: { handler: arg0 } }` + value-model `result_returns` | fluent | `src/sextant/catalogs/flask.yml:61`, `src/sextant/catalogs/value-models/flask.yml:15` |
| route with no handler | `handler: none` | combinator | `src/sextant/catalogs/spring-cloud-gateway.yml:152` |
| handler object -> which method runs | `handler_methods` | fluent | `src/sextant/catalogs/vertx-web.yml:347` |
| middleware passes on | `passes_on`, `framework_handlers` | fluent | `src/sextant/catalogs/vertx-web.yml:311-314, 338` |
| chain call that reads nothing | `continuations[].pass_through: true`; capture-less step with `returns_receiver: true` | combinator; fluent | `src/sextant/catalogs/spring-cloud-gateway.yml:172`; `src/sextant/catalogs/vertx-web.yml:233` |
| class handler: entry point replaced | `bypassed_by` | supertype_dispatch | `src/sextant/catalogs/jakarta-servlet.yml:182-186` |
| class handler: inherited mapped methods | `mapping.inherit_unoverridden` | annotation_driven | `src/sextant/catalogs/spring-mvc.yml:102` |
| prefix on the class | `prefix_annotation` + `prefix_from` + `path_separator` | annotation_driven | `src/sextant/catalogs/spring-mvc.yml:106,110,158` |
| constant prefix | `path_prefix` | annotation_driven | `src/sextant/catalogs/spring-actuator.yml:89` |
| prefix by a nesting block | `vocabulary.prefixes[]` (`path_arg`, `body_arg`/`subtree_arg`) | combinator | `src/sextant/catalogs/ktor-routing.yml:250-251` |
| prefix by mounting a router object | `router_type` + `mount[]` (`router_arg`, `prefix_arg` \| `prefix_from: receiver_path`) | fluent | `src/sextant/catalogs/vertx-web.yml:288-301`, `src/sextant/catalogs/flask.yml:99-105` |
| prefix held by the router's constructor | `router_holds[]` | fluent | `src/sextant/catalogs/fastapi.yml:136-140`, `src/sextant/catalogs/flask.yml:83-85` |
| mount prefix replaces the held one | `prefix_replaces_own: true` | fluent | `src/sextant/catalogs/flask.yml:102` |
| how prefix + path join | `path_join: leading_slash \| concatenate \| single_slash`; `path_separator` | fluent/combinator; annotation_driven | `src/sextant/catalogs/fastapi.yml:156`, `src/sextant/catalogs/flask.yml:78`, `src/sextant/catalogs/ktor-routing.yml:186`, `src/sextant/catalogs/spring-mvc.yml:110` |
| mount on a host | `host_arg`; step `collects: {kind: host,...}` | fluent | `src/sextant/catalogs/fastapi.yml:154-155`; `src/sextant/catalogs/vertx-web.yml:189-190` |
| framework refuses a mount/prefix | `refuses: [...]` | fluent | `src/sextant/catalogs/fastapi.yml:144` |
| same object across statements | `returns_receiver: true` | fluent step, value model | `src/sextant/catalogs/vertx-web.yml:174` |
| value behind a producer call | `url_via`, `channel_via`, value-model `identified_by` | fluent, single_call | `src/sextant/catalogs/vertx-webclient.yml:118` |
| value behind a DI bean | `bean_via` | fluent | `src/sextant/catalogs/spring-integration-amqp.yml:114` |
| receiver made by a call | `request_reads[].via` | all inbound | `src/sextant/catalogs/flask.yml:129` |
| chain result consumed as an argument | `terminal_via_argument`; `via_argument_of` + `continue` | fluent | `src/sextant/catalogs/okhttp.yml:92`; `src/sextant/catalogs/spring-integration-amqp.yml:126` |
| annotation on the method that BUILDS the chain | `method_annotation: {annotation, arg, into}` | fluent root | `src/sextant/catalogs/spring-integration-amqp.yml:120-121` |
| request parameter marker | `request_params[]` (annotation or marker call) | annotation_driven, fluent | `src/sextant/catalogs/spring-mvc.yml:73-96`, `src/sextant/catalogs/fastapi.yml:181-208` |
| request read in the body | `request_reads[]` | all inbound | `src/sextant/catalogs/jakarta-servlet.yml:91-93` |
| route demands a header/param | `request_requirement`, `request_requirement_attrs` | combinator, annotation_driven | `src/sextant/catalogs/ktor-routing.yml:258-259`, `src/sextant/catalogs/spring-mvc.yml:149` |
| two handlers on one address is an error | `mapping.duplicate: conflict` | annotation_driven | `src/sextant/catalogs/spring-mvc.yml:127` |
| route disabled / removed | `serves` capture, `poisons` | fluent | `src/sextant/catalogs/vertx-web.yml:194-199` |
| automatic HEAD/OPTIONS | NO word; stated boundary, not published | all | C |
| router named by a string / module / class | `mount[].router_named: {variable}` (approved 2026-11-22); the root module by `root_setting` (approved 2026-11-23) | fluent | `src/sextant/catalogs/django.yml` (D02 §2 `fluent`) |
| decorator/annotation on the handler changes a fluent route | `matches.annotations` (`fqn`, `method`, `method_from`), the `annotation_driven` words, read by the fluent engine (ruled 2026-11-23) | fluent | `src/sextant/catalogs/django.yml` (D02 §2 `fluent`) |

### Words that have the same role under different names

1. `url_is: pattern` (fluent) = `pattern_from: [attr]` (annotation_driven). Evidence: D02 `:2475` "(`annotation_driven` spells the same marker `pattern_from`, an attribute list; the column is `path_kind`.)"; `src/sextant/catalogs/quarkus-reactive-routes.yml:57-62` "Same row Vert.x Web's `getWithRegex` derives."
2. `verbless_serves: any` in `matches` (fluent) = `mapping.verbless_serves: any` (annotation_driven): the SAME word, one validator (`src/sextant/application/resolve/shapes/inbound_routes.py:93-106`: "the word `fluent` and `annotation_driven` catalogs share"). The combinator style has no equal; it has `all_methods` (fan-out) and `verb: none`.
3. `all_methods` under `mapping` (annotation_driven, `src/sextant/catalogs/spring-mvc.yml:157`) = top-level `matches.all_methods` (combinator, `src/sextant/catalogs/ktor-routing.yml:237`, `src/sextant/catalogs/spring-cloud-gateway.yml:124`): same name, same role, different place and different readers (`sql:628` vs `src/sextant/application/resolve/engines/combinator.py:620`).
4. `captures.http_method: <LITERAL>` (fluent) = `verb: <LITERAL>` (combinator) = `annotations[].method: [..]` (annotation_driven) = `dispatch[].method` (supertype_dispatch). Four names for "this entry pre-sets the method".
5. `captures.http_method: argN` (fluent) = `verb_arg: N` (combinator) = `method_from: <attr>` (annotation_driven): "read the method from a position". Value tables: `verb_values` is shared by fluent (`src/sextant/application/resolve/engines/fluent.py:3902`, top of `matches`) and combinator (`src/sextant/application/resolve/engines/combinator.py:618-619`, under `vocabulary`): same word, two places.
6. `captures.handler: argN` (fluent) = `handler_arg: N` (combinator). `handler: none` (combinator) has no fluent twin (fluent: no `handler` capture / every handler passes on -> no row).
7. `captures.url: argN` (fluent) = `path_arg: N` / `path: ""` (combinator) = `path_from` / `path_from_siblings` (annotation_driven) = `address: {annotation, args}` (supertype_dispatch).
8. Prefix: `prefix_annotation`+`prefix_from` (annotation_driven) / `vocabulary.prefixes[].path_arg` (combinator) / `mount[].prefix_arg` + `router_holds[].prefix_arg` (fluent) / `path_prefix` constant (annotation_driven).
9. Join rule: `path_join` (fluent, combinator) vs `path_separator: "/"` (annotation_driven, `src/sextant/catalogs/spring-mvc.yml:107-110`: "joins a class prefix to a method path with exactly one `/`") — the same behaviour as `path_join: single_slash`.
10. `url_via` = `channel_via` = value-model `identified_by` (D02 `:635-639`, `src/sextant/application/resolve/shapes/chains.py:2695-2698`: "one grammar, `{owner, method, arg}`, two positions").
11. `pass_through: true` (combinator continuation) ~ a capture-less fluent step with `returns_receiver: true`: both mean "a call in the chain that carries it on and reads nothing". NOT the same as `passes_on` (which handler answers) or the `handler_pass_through` question. Three different things share the words "pass" / "through".
12. `request_requirement` (combinator rule) = `request_requirement_attrs` (annotation_driven) = step `collects: {kind, name, value}` (fluent): "the route declaration demands this of the request".
13. `inherit_unoverridden` (annotation_driven) vs the supertype_dispatch member union over scanned intermediates (`src/sextant/application/resolve/engines/supertype_dispatch.py:179-189`, no word): both answer "a handler declared on a scanned base class serves under the subclass".
14. `terminal_via_argument` (on a terminal) vs `via_argument_of` + `continue` (on a root/step): the same join (chain result -> argument of a named call), declared from the two ends (`src/sextant/application/resolve/shapes/chains.py:2870-2874`: "`via_argument_of` without `continue` would be an execute-join on a root, which `terminal_via_argument` already is").


## Cases with no rule today

No rule reads these. The first three are ruled not supported (2026-11-23): the row keeps its
reason, and no rule enumerates the values. A copy (`list(x)`) and `.format` were in this
table; they are ruled and built now (rows in "Lists and arrays" and "Constants and text").

| Case | Example | Seen in |
|---|---|---|
| A registration call inside a loop or a comprehension | `for r in REDIRECTS: urls += [path(r.old_url, ...)]` | **RULED 2026-11-23: not supported.** Counted in 14 Python projects: about 15 places, 9 over a run-time registry, 6 over written values (zulip 4, redash 1, home-assistant 1). Measured 2026-11-24 on zulip: 22 rows with no path stand for 149 Django patterns. The question that names the registration is filed (ruled 2026-11-25, R4): `not_read`, column `path`, `non_enumerable`, the registering method and its call (`tests/application/test_django_routes.py::test_a_registration_in_a_loop_whose_path_is_not_read_files_a_question`). A path not read outside a loop files none (OI-566) |
| A map or dict as a value source, a lookup by key | `handlers[request.method]`; `Map.of(...)`; `switch` | **RULED 2026-11-23: not supported.** zulip `rest_dispatch`: 295 routes, 829 Django (method, route) pairs (OI-504) |
| A `**kwargs` parameter (the left-over keywords) | `rest_path("realm", GET=f, PATCH=g)` | **RULED 2026-11-23: not supported.** zulip, the same 295 routes: one any-method row each, `partial` (OI-503) |
| A constant read from another class (Java) | `Other.TOPIC` | no test found (the "Static field" row is the nearest rule) |

## Known disagreements in the code's own text

- `values.py:38-43` says "There is no cap"; `values.py:349-371` defines three caps.
- `values.py:5463-5466` says an environment read's default is never read;
  `tests/application/test_environment_reads.py:1-4` says it renders as `${KEY:-default}`.
- A hand-off into a library named in `extract_libraries` is stated as followed
  (`docs/superpowers/specs/2026-11-02-per-path-truth-design.md` rule 1); no walk-level test
  was found.
