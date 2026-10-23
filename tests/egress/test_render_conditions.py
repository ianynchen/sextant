"""Every row a conditional bean derives states where it exists (spec 2026-10-22-conditional-
beans §3): an outbound call, a scheduled job and an error handler get the two detail lines an
inbound endpoint got in PR #61, all read from ONE index over `bean_conditions` and
`bean_presence` — never from per-kind copies, and "holds in N of M" from `bean_presence` alone
(two mutually exclusive factories would otherwise read as "exists nowhere")."""

from pathlib import Path

from sextant.application.ports.detector import ModuleModel
from sextant.application.resolve.pipeline import ResolveReport
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
    )
    block = _block(document, "Users#all")
    assert (
        "  - Exists only when: no other bean of type `UserService` is registered — decided from "
        "this module's beans only (`partial`): `LdapUserService` (not in any environment; "
        f"{LDAP_NOTE})\n"
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
    )
    block = _block(document, "Users#all")
    assert (
        "a bean of type `UserService` is registered — decided from this module's beans only "
        "(`partial`): `Other` (in `prod`; not in `default`, `staging`)"
    ) in block
