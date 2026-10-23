"""Every row a conditional bean derives states where it exists (spec 2026-10-22-conditional-
beans §3): an outbound call, a scheduled job and an error handler get the two detail lines an
inbound endpoint got in PR #61, all read from ONE index over `bean_conditions` and
`bean_presence` — never from per-kind copies, and "holds in N of M" from `bean_presence` alone
(two mutually exclusive factories would otherwise read as "exists nowhere")."""

from pathlib import Path

from sextant.application.ports.detector import ModuleModel
from sextant.application.query.trace import Step, Trace
from sextant.application.resolve.pipeline import ResolveReport
from sextant.application.resolve.roots import Root, RootIdentity
from sextant.domain.closed_sets import Resolution, RootKind, TraceStop
from sextant.egress.render.document import render_module_document

MODULE = ModuleModel(
    module_id="com.acme:orders-service",
    coordinates="com.acme/orders-service",
    version="1.0.0",
    root=Path("fixtures/orders-service"),
    kind="service",
    languages=frozenset({"java"}),
    source_roots=(),
    output_dirs=(),
)

COORDS = "s maven c 1 "
CLIENT = COORDS + "com/acme/BillingClient#"
JOBS = COORDS + "com/acme/Jobs#"
ADVICE = COORDS + "com/acme/Advice#"
USERS = COORDS + "com/acme/Users#"
CONFIG = COORDS + "com/acme/UserConfig#"
ENVIRONMENTS = ("default", "prod", "staging")

PROFILE_PROD = '{"expressions": ["prod"]}'
PROFILE_STAGING = '{"expressions": ["staging"]}'


def _condition(
    bean: str,
    kind: str | None,
    expression: str | None,
    holds: dict[str, str],
    *,
    via: str | None = None,
    bean_kind: str = "class",
    resolution: str = "resolved",
    evidence: object = "compiler",
) -> list[dict[str, object]]:
    """One condition of one route of `bean`, a row per environment."""
    return [
        {
            "bean": bean,
            "bean_kind": bean_kind,
            "via": via,
            "kind": kind,
            "expression": expression,
            "environment": environment,
            "holds": verdict,
            "resolution": resolution,
            "evidence": evidence[environment] if isinstance(evidence, dict) else evidence,
        }
        for environment, verdict in holds.items()
    ]


def _presence(
    bean: str, holds: dict[str, str], resolution: str = "resolved"
) -> list[dict[str, object]]:
    return [
        {
            "bean": bean,
            "environment": environment,
            "holds": verdict,
            "resolution": resolution,
            "evidence": None,
        }
        for environment, verdict in holds.items()
    ]


PROD_ONLY = {"default": "false", "prod": "true", "staging": "false"}


def _belongs(symbol: str, bean: str) -> dict[str, object]:
    """One `symbol_beans` row: the bean a code symbol belongs to, as the workspace's one rule
    (own symbol first, then owner class) decided it — the document reads it, never re-derives
    it (Task 5, ruling 1)."""
    return {"symbol": symbol, "bean": bean}


def _document(**tables: list[dict[str, object]]) -> str:
    report = ResolveReport(facts_loaded=1, coverage={"documents": 1}, **tables)  # type: ignore[arg-type]
    return render_module_document(MODULE, report, "a3f91c")


def _outbound(caller: str) -> dict[str, object]:
    return {
        "protocol": "http",
        "direction": "outbound",
        "method": "GET",
        "path": "/billing/balances",
        "peer": "billing",
        "caller": caller,
        "resolution": "resolved",
        "format": None,
    }


def _inbound(handler: str) -> dict[str, object]:
    return {
        "protocol": "http",
        "direction": "inbound",
        "method": "GET",
        "path": "/ops/status",
        "handler": handler,
        "resolution": "resolved",
        "format": None,
    }


def _block(document: str, header: str) -> str:
    """The detail block whose header line contains `header`, up to the next blank line that
    is followed by something that is not part of the block."""
    lines = document.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("- ") and header in line)
    end = start + 1
    while end < len(lines) and (lines[end].startswith("  ") or lines[end] == ""):
        end += 1
    return "\n".join(lines[start:end])


EXISTS_PROD = "  - Exists only when: the active profile matches one of: `prod`\n"
OF_ENVIRONMENTS = (
    "  - Of this module's environments: holds in 1 of 3 environments — not in `default`, `staging`"
)


def test_an_outbound_call_of_a_conditional_bean_states_where_it_exists():
    """A client class under `@Profile("prod")`: its outbound row gets the two lines its
    caller's bean carries — the call exists only where its bean does."""
    caller = CLIENT + "balances()."
    document = _document(
        endpoints=[_outbound(caller)],
        bean_conditions=_condition(CLIENT, "profile", PROFILE_PROD, PROD_ONLY),
        bean_presence=_presence(CLIENT, PROD_ONLY),
        symbol_beans=[_belongs(caller, CLIENT)],
    )
    block = _block(document, "BillingClient#balances")
    assert EXISTS_PROD in block + "\n"
    assert OF_ENVIRONMENTS in block


def test_a_scheduled_job_of_a_conditional_bean_states_where_it_exists():
    handler = JOBS + "nightly()."
    document = _document(
        scheduled_work=[
            {
                "handler": handler,
                "trigger": "cron",
                "expression": "0 0 * * *",
                "resolution": "resolved",
                "evidence": "compiler",
                "catalog_id": "spring-scheduling",
            }
        ],
        bean_conditions=_condition(JOBS, "profile", PROFILE_PROD, PROD_ONLY),
        bean_presence=_presence(JOBS, PROD_ONLY),
        symbol_beans=[_belongs(handler, JOBS)],
    )
    block = _block(document, "Jobs#nightly")
    assert EXISTS_PROD in block + "\n"
    assert OF_ENVIRONMENTS in block


def test_an_error_handler_of_a_conditional_bean_states_where_it_exists():
    handler = ADVICE + "notFound()."
    document = _document(
        error_handlers=[
            {
                "handler": handler,
                "advice": "com/acme/Advice#",
                "declared_by": "org/springframework/web/bind/annotation/ControllerAdvice#",
                "scope": None,
                "exception": "com/acme/OrderNotFound#",
                "status": None,
                "response_shape": None,
                "resolution": "resolved",
                "evidence": "compiler",
                "catalog_id": "spring-advice",
            }
        ],
        bean_conditions=_condition(ADVICE, "profile", PROFILE_PROD, PROD_ONLY),
        bean_presence=_presence(ADVICE, PROD_ONLY),
        symbol_beans=[_belongs(handler, ADVICE)],
    )
    block = _block(document, "Advice#notFound")
    assert EXISTS_PROD in block + "\n"
    assert OF_ENVIRONMENTS in block


def test_an_inbound_endpoint_is_found_the_same_way():
    """One lookup for every derived thing: the inbound block reads the same index."""
    handler = CLIENT + "status()."
    document = _document(
        endpoints=[_inbound(handler)],
        bean_conditions=_condition(CLIENT, "profile", PROFILE_PROD, PROD_ONLY),
        bean_presence=_presence(CLIENT, PROD_ONLY),
        symbol_beans=[_belongs(handler, CLIENT)],
    )
    block = _block(document, "BillingClient#status")
    assert EXISTS_PROD in block + "\n"
    assert OF_ENVIRONMENTS in block


def test_a_lambda_that_is_its_own_bean_is_found_before_its_owner_class():
    """The view's order: the row's own symbol first. A lambda a `@Bean` factory creates is
    the factory's bean, with the factory's route; its owner class's rows are not consulted."""
    lambda_body = CLIENT + "lambda$balances$0()."
    document = _document(
        endpoints=[_outbound(lambda_body)],
        bean_conditions=[
            *_condition(
                lambda_body,
                "profile",
                PROFILE_STAGING,
                {"default": "false", "prod": "false", "staging": "true"},
            ),
            *_condition(CLIENT, "profile", PROFILE_PROD, PROD_ONLY),
        ],
        bean_presence=[
            *_presence(lambda_body, {"default": "false", "prod": "false", "staging": "true"}),
            *_presence(CLIENT, PROD_ONLY),
        ],
        symbol_beans=[_belongs(lambda_body, lambda_body)],
    )
    block = _block(document, "lambda$balances$0")
    assert "  - Exists only when: the active profile matches one of: `staging`\n" in block + "\n"
    assert "holds in 1 of 3 environments — not in `default`, `prod`" in block


def test_a_row_of_an_unconditional_bean_has_no_condition_lines():
    caller = CLIENT + "balances()."
    document = _document(
        endpoints=[_outbound(caller), _inbound(JOBS + "status().")],
        scheduled_work=[
            {
                "handler": JOBS + "nightly().",
                "trigger": "cron",
                "expression": "0 0 * * *",
                "resolution": "resolved",
                "evidence": "compiler",
                "catalog_id": "spring-scheduling",
            }
        ],
    )
    assert "Exists only when" not in document
    assert "Of this module's environments" not in document
    assert "Exists when any of these" not in document


# --- Several routes ---------------------------------------------------------------------

FACTORY_PROD = CONFIG + "prodUsers(sig_aa)."
FACTORY_STAGING = CONFIG + "stagingUsers(sig_bb)."


def _two_exclusive_factories() -> list[dict[str, object]]:
    return [
        *_condition(
            USERS,
            "profile",
            PROFILE_PROD,
            {"default": "false", "prod": "true", "staging": "false"},
            via=FACTORY_PROD,
            bean_kind="factory",
        ),
        *_condition(
            USERS,
            "profile",
            PROFILE_STAGING,
            {"default": "false", "prod": "false", "staging": "true"},
            via=FACTORY_STAGING,
            bean_kind="factory",
        ),
    ]


def test_two_exclusive_factories_state_each_route_and_the_presence_verdict():
    """Neither factory's row holds everywhere, and read as one list of conditions the bean
    would exist nowhere. It exists in `prod` (one factory) and `staging` (the other): the
    count is `bean_presence`'s, the routes are spelled one line each."""
    handler = USERS + "all()."
    document = _document(
        endpoints=[_inbound(handler)],
        bean_conditions=_two_exclusive_factories(),
        bean_presence=_presence(USERS, {"default": "false", "prod": "true", "staging": "true"}),
        symbol_beans=[_belongs(handler, USERS)],
    )
    block = _block(document, "Users#all")
    assert "  - Exists when any of these registers it:\n" in block + "\n"
    assert "| `UserConfig#prodUsers` | the active profile matches one of: `prod` |" in block
    assert "| `UserConfig#stagingUsers` | the active profile matches one of: `staging` |" in block
    assert "  - Of this module's environments: holds in 2 of 3 environments — not in `default`" in (
        block
    )
    assert "Exists only when" not in block


def test_an_unconditional_route_reads_always_and_a_constructed_one_says_it_is_not_decided():
    handler = USERS + "all()."
    document = _document(
        endpoints=[_inbound(handler)],
        bean_conditions=[
            *_condition(USERS, "profile", PROFILE_PROD, PROD_ONLY),
            *_condition(
                USERS,
                None,
                None,
                {"default": "true", "prod": "true", "staging": "true"},
                via=FACTORY_STAGING,
                bean_kind="factory",
            ),
            *_condition(
                USERS,
                None,
                None,
                {"default": "unresolved", "prod": "unresolved", "staging": "unresolved"},
                via=COORDS + "com/acme/Wiring#build().",
                bean_kind="constructed",
                resolution="unresolved",
                evidence="also constructed outside any factory, in Wiring#build",
            ),
        ],
        bean_presence=_presence(USERS, {"default": "true", "prod": "true", "staging": "true"}),
        symbol_beans=[_belongs(handler, USERS)],
    )
    block = _block(document, "Users#all")
    assert "| `Users` | the active profile matches one of: `prod` |" in block
    assert "| `UserConfig#stagingUsers` | always |" in block
    assert "| `Wiring#build` | constructed outside any bean factory — not decided |" in block
    assert "holds in 3 of 3 environments" in block


def test_a_bean_open_in_every_environment_is_not_evaluated_in_any():
    handler = USERS + "all()."
    unresolved = {"default": "unresolved", "prod": "unresolved", "staging": "unresolved"}
    document = _document(
        endpoints=[_inbound(handler)],
        bean_conditions=_condition(
            USERS,
            "other",
            '{"annotation": "org/springframework/boot/autoconfigure/condition/ConditionalOnClass#"}',
            unresolved,
            resolution="unresolved",
        ),
        bean_presence=_presence(USERS, unresolved, "unresolved"),
        symbol_beans=[_belongs(handler, USERS)],
    )
    block = _block(document, "Users#all")
    assert "not evaluated by this analysis in any of the 3 environments" in block


# --- Bean-presence conditions ----------------------------------------------------------

MISSING = (
    '{"annotation": "org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean#",'
    ' "annotations": [], "mode": "missing", "names": [], "types": ["com/acme/UserService#"]}'
)
PRESENT = (
    '{"annotation": "org/springframework/boot/autoconfigure/condition/ConditionalOnBean#",'
    ' "annotations": [], "mode": "present", "names": [], "types": ["com/acme/UserService#"]}'
)
PARTIAL = "decided from this module's beans only; a library or the processing order may differ"
LDAP_NOTE = "profile `ldap` is named but this module has no `ldap` environment"


def _competitors(entries: str) -> str:
    return f"{PARTIAL}; competitors: {entries}"


def test_a_missing_bean_condition_names_its_competitors_and_the_profile_nobody_activates():
    handler = USERS + "all()."
    holds = {"default": "true", "prod": "true", "staging": "true"}
    listed = (
        '[{"bean": "' + COORDS + 'com/acme/LdapUserService#", "holds": "false", '
        '"note": "' + LDAP_NOTE + '", "via": "' + CONFIG + 'ldapUsers()."}]'
    )
    document = _document(
        endpoints=[_inbound(handler)],
        bean_conditions=_condition(
            USERS,
            "presence",
            MISSING,
            holds,
            resolution="partial",
            evidence=_competitors(listed),
        ),
        bean_presence=_presence(USERS, holds, "partial"),
        symbol_beans=[_belongs(handler, USERS)],
    )
    block = _block(document, "Users#all")
    assert (
        "  - Exists only when: no other bean of type `UserService` is registered — decided from "
        "this module's beans only (`partial`); the other beans of that type: `LdapUserService` "
        f"(not in any environment; {LDAP_NOTE})\n"
    ) in block + "\n"
    assert "competitors" not in block
    assert "[{" not in block


def test_a_bean_condition_names_a_competitor_by_where_it_exists():
    handler = USERS + "all()."
    holds = {"default": "false", "prod": "true", "staging": "false"}
    entries = {
        environment: '[{"bean": "'
        + COORDS
        + 'com/acme/Other#", "holds": "'
        + ("true" if environment == "prod" else "false")
        + '", "via": null}]'
        for environment in holds
    }
    document = _document(
        endpoints=[_inbound(handler)],
        bean_conditions=_condition(
            USERS,
            "presence",
            PRESENT,
            holds,
            resolution="partial",
            evidence={e: _competitors(v) for e, v in entries.items()},
        ),
        bean_presence=_presence(USERS, holds, "partial"),
        symbol_beans=[_belongs(handler, USERS)],
    )
    block = _block(document, "Users#all")
    assert (
        "a bean of type `UserService` is registered — decided from this module's beans only "
        "(`partial`); the other beans of that type: `Other` (in `prod`; not in `default`, "
        "`staging`)"
    ) in block


def test_a_missing_bean_condition_names_every_competitor_in_order():
    """Apollo portal's shape: `DefaultUserService` stands back for three other `UserService`
    beans, each under a profile no environment of the module activates. Every one is named,
    sorted, after the lead-in — none dropped, none merged."""
    handler = USERS + "all()."
    holds = {"default": "true", "prod": "true", "staging": "true"}
    listed = (
        "["
        + ", ".join(
            '{"bean": "' + COORDS + f'com/acme/{name}#", "holds": "false", "note": '
            f'"profile `{profile}` is named but this module has no `{profile}` environment", '
            '"via": null}'
            for name, profile in (
                ("LdapUserService", "ldap"),
                ("OidcLocalUserServiceImpl", "oidc"),
                ("SpringSecurityUserService", "auth"),
            )
        )
        + "]"
    )
    document = _document(
        endpoints=[_inbound(handler)],
        bean_conditions=_condition(
            USERS, "presence", MISSING, holds, resolution="partial", evidence=_competitors(listed)
        ),
        bean_presence=_presence(USERS, holds, "partial"),
        symbol_beans=[_belongs(handler, USERS)],
    )
    block = _block(document, "Users#all")
    assert (
        "no other bean of type `UserService` is registered — decided from this module's beans "
        "only (`partial`); the other beans of that type: "
        "`LdapUserService` (not in any environment; profile `ldap` is named but this module "
        "has no `ldap` environment), "
        "`OidcLocalUserServiceImpl` (not in any environment; profile `oidc` is named but this "
        "module has no `oidc` environment), "
        "`SpringSecurityUserService` (not in any environment; profile `auth` is named but this "
        "module has no `auth` environment)\n"
    ) in block + "\n"


def test_one_route_with_two_conditions_joins_them_with_and():
    """A bean registered ONE way under two conditions exists where both hold, so its line
    joins them with "and" — one sentence about the bean, not PR #61's one pair per
    condition (presence is per bean)."""
    handler = USERS + "all()."
    property_expression = (
        '{"having_value": "on", "keys": ["users.enabled"], "match_if_missing": false}'
    )
    document = _document(
        endpoints=[_inbound(handler)],
        bean_conditions=[
            *_condition(USERS, "profile", PROFILE_PROD, PROD_ONLY),
            *_condition(
                USERS,
                "property",
                property_expression,
                {"default": "true", "prod": "true", "staging": "false"},
            ),
        ],
        bean_presence=_presence(USERS, PROD_ONLY),
        symbol_beans=[_belongs(handler, USERS)],
    )
    block = _block(document, "Users#all")
    assert (
        "  - Exists only when: the active profile matches one of: `prod` and the configuration "
        "key `users.enabled` is `on`\n"
    ) in block + "\n"
    assert block.count("Exists only when") == 1


# --- Narrowed call sites (spec §3, second bullet; Task 5) --------------------------------

API = COORDS + "com/acme/Api#"
SENDER_SEND = "com/acme/Sender#send()."
KAFKA = COORDS + "com/acme/KafkaSender#"
REDIS = COORDS + "com/acme/RedisSender#"
DEFAULT_USERS = COORDS + "com/acme/DefaultUserService#"
LDAP_USERS = COORDS + "com/acme/LdapUserService#"


def _narrowed_trace(*callees: str, target: str = SENDER_SEND) -> Trace:
    """`Api#handle` (an inbound root) calls `Api#send`, whose one call site dispatches to
    each of `callees` with none picked."""
    send = API + "send()."
    steps = [
        Step(
            depth=1,
            caller=API + "handle().",
            ordinal=0,
            invoke_kind="virtual",
            target="com/acme/Api#send().",
            callee=send,
            result=None,
            resolution=Resolution.RESOLVED,
            stop=None,
        ),
        *(
            Step(
                depth=2,
                caller=send,
                ordinal=0,
                invoke_kind="interface",
                target=target,
                callee=callee,
                result=None,
                resolution=Resolution.NARROWED,
                stop=TraceStop.BOUNDARY,
            )
            for callee in callees
        ),
    ]
    return Trace(
        root=Root(
            handler=API + "handle().",
            kind=RootKind.INBOUND_ENDPOINT,
            identities=(RootIdentity(protocol="http", method="POST", path="/send"),),
        ),
        steps=tuple(steps),
        response=(),
    )


def _candidate(
    callee: str, bean: str | None, holds: dict[str, str], resolution: str = "resolved"
) -> list[dict[str, object]]:
    """`candidate_presence` rows for one candidate of `Api#send`'s site."""
    return [
        {
            "caller": API + "send().",
            "ordinal": 0,
            "callee": callee,
            "bean": bean,
            "environment": environment,
            "holds": verdict,
            "resolution": resolution,
        }
        for environment, verdict in holds.items()
    ]


def _traced(trace: Trace, **tables: list[dict[str, object]]) -> str:
    report = ResolveReport(facts_loaded=1, coverage={"documents": 1}, **tables)  # type: ignore[arg-type]
    return render_module_document(MODULE, report, "a3f91c", traces=[trace])


def test_a_narrowed_site_states_which_candidates_exist_in_each_environment():
    """Two `@ConditionalOnProperty` senders behind one interface call — `sender-type=kafka`
    in `application-kafka.yml`, `redis` in `application.yml`. The trace still lists both; the
    block then says which one exists in each environment. Nothing is dropped."""
    kafka_send, redis_send = KAFKA + "send().", REDIS + "send()."
    trace = _narrowed_trace(kafka_send, redis_send)
    document = _traced(
        trace,
        candidate_presence=[
            *_candidate(kafka_send, KAFKA, {"default": "false", "kafka": "true"}),
            *_candidate(redis_send, REDIS, {"default": "true", "kafka": "false"}),
        ],
    )
    block = _block(document, "Api#handle")
    assert (
        "  - `Api#send` calls `Sender#send`, answered by one of: `KafkaSender`, `RedisSender`\n"
        "  - in `default`: `RedisSender`\n"
        "  - in `kafka`: `KafkaSender`\n"
    ) in block + "\n"
    # Both candidates stay in the step table and in the diagram's `alt` block.
    assert block.count("narrowed") == 2
    assert "alt KafkaSender" in document and "else RedisSender" in document


def test_a_partial_candidate_says_it_was_decided_from_this_modules_beans_only():
    """A `@ConditionalOnMissingBean` default beside a `@Profile("ldap")` override: where the
    default exists it exists by a verdict from the module's own beans (`partial`), and its
    line says so; an unconditional candidate is listed everywhere; an open one is not
    evaluated."""
    default_find, ldap_find, plain_find = (
        DEFAULT_USERS + "find().",
        LDAP_USERS + "find().",
        COORDS + "com/acme/CachedUserService#find().",
    )
    open_find = COORDS + "com/acme/RemoteUserService#find()."
    trace = _narrowed_trace(
        default_find, ldap_find, plain_find, open_find, target="com/acme/UserService#find()."
    )
    document = _traced(
        trace,
        candidate_presence=[
            *_candidate(
                default_find, DEFAULT_USERS, {"default": "true", "ldap": "false"}, "partial"
            ),
            *_candidate(ldap_find, LDAP_USERS, {"default": "false", "ldap": "true"}),
            *_candidate(plain_find, None, {"default": "true", "ldap": "true"}),
            *_candidate(
                open_find,
                COORDS + "com/acme/RemoteUserService#",
                {"default": "unresolved", "ldap": "unresolved"},
                "unresolved",
            ),
        ],
    )
    block = _block(document, "Api#handle")
    assert (
        "  - in `default`: `CachedUserService`, `DefaultUserService` (decided from this module's "
        "beans only)\n"
        "  - in `ldap`: `CachedUserService`, `LdapUserService`\n"
        "  - not evaluated in `default`, `ldap`: `RemoteUserService`\n"
    ) in block + "\n"


def test_environments_with_the_same_candidates_share_one_line():
    kafka_send, redis_send = KAFKA + "send().", REDIS + "send()."
    holds_redis = {"default": "true", "kafka": "false", "test": "true"}
    document = _traced(
        _narrowed_trace(kafka_send, redis_send),
        candidate_presence=[
            *_candidate(kafka_send, KAFKA, {"default": "false", "kafka": "true", "test": "false"}),
            *_candidate(redis_send, REDIS, holds_redis),
        ],
    )
    block = _block(document, "Api#handle")
    assert "  - in `default`, `test`: `RedisSender`\n" in block + "\n"
    assert "  - in `kafka`: `KafkaSender`\n" in block + "\n"


def test_an_unconditional_narrowed_site_renders_unchanged():
    """A narrowed site none of whose candidates is a conditional bean has no
    `candidate_presence` rows, and its trace renders byte for byte as it did before — no
    empty per-environment block. Rows for a site this trace never reaches change nothing."""
    trace = _narrowed_trace(
        COORDS + "com/acme/JdbcRepo#send().", COORDS + "com/acme/JpaRepo#send()."
    )
    elsewhere = [
        {**row, "caller": COORDS + "com/acme/Elsewhere#run()."}
        for row in _candidate(KAFKA + "send().", KAFKA, {"default": "true"})
    ]
    before = _traced(trace)
    after = _traced(trace, candidate_presence=elsewhere)
    assert after == before
    assert "answered by one of" not in after


def test_an_environment_where_no_candidate_exists_says_so():
    """Every candidate conditional and none holding in `default` (the ruoyi module that sets
    no `sender-type`): the line says none of them, rather than leaving the environment out."""
    kafka_send, redis_send = KAFKA + "send().", REDIS + "send()."
    document = _traced(
        _narrowed_trace(kafka_send, redis_send),
        candidate_presence=[
            *_candidate(kafka_send, KAFKA, {"default": "false", "kafka": "true"}),
            *_candidate(redis_send, REDIS, {"default": "false", "kafka": "false"}),
        ],
    )
    block = _block(document, "Api#handle")
    assert "  - in `default`: none of them\n  - in `kafka`: `KafkaSender`\n" in block + "\n"


# --- An inherited body (ruled 2026-10-22) ----------------------------------------------

ABSTRACT_SEND = COORDS + "com/acme/AbstractSender#send()."
LOCAL = COORDS + "com/acme/LocalSender#"
KAFKA_HEIR = COORDS + "com/acme/KafkaSender#"
LOCAL_ONLY = {"default": "true", "prod": "false", "staging": "false"}


def test_a_row_in_an_inherited_body_names_each_heir_as_a_route():
    """An outbound call in `AbstractSender#send`, which two `@Component` heirs run: the body's
    rows are its heirs' routes, each named by the heir class, and it exists where either does."""
    property_expression = (
        '{"having_value": "local", "keys": ["sender-type"], "match_if_missing": true}'
    )
    document = _document(
        endpoints=[_outbound(ABSTRACT_SEND)],
        bean_conditions=[
            *_condition(ABSTRACT_SEND, "property", property_expression, LOCAL_ONLY, via=LOCAL),
            *_condition(ABSTRACT_SEND, "profile", PROFILE_PROD, PROD_ONLY, via=KAFKA_HEIR),
        ],
        bean_presence=_presence(
            ABSTRACT_SEND, {"default": "true", "prod": "true", "staging": "false"}
        ),
        symbol_beans=[_belongs(ABSTRACT_SEND, ABSTRACT_SEND)],
    )
    block = _block(document, "AbstractSender#send")
    assert (
        "| `LocalSender` | the configuration key `sender-type` is `local` (or is absent) |"
    ) in block
    assert "| `KafkaSender` | the active profile matches one of: `prod` |" in block
    assert "holds in 2 of 3 environments — not in `staging`" in block


def test_a_row_in_an_inherited_body_no_bean_runs_says_it_is_not_decided():
    unresolved = {"default": "unresolved", "prod": "unresolved", "staging": "unresolved"}
    document = _document(
        endpoints=[_outbound(ABSTRACT_SEND)],
        bean_conditions=_condition(
            ABSTRACT_SEND,
            None,
            None,
            unresolved,
            bean_kind="inherited",
            resolution="unresolved",
            evidence="no bean of this module runs this inherited body",
        ),
        bean_presence=_presence(ABSTRACT_SEND, unresolved, "unresolved"),
        symbol_beans=[_belongs(ABSTRACT_SEND, ABSTRACT_SEND)],
    )
    block = _block(document, "AbstractSender#send")
    assert (
        "  - Exists only when: no bean of this module runs this inherited body — not decided\n"
    ) in block + "\n"
    assert "not evaluated by this analysis in any of the 3 environments" in block
