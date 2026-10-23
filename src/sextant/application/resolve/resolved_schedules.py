"""A schedule set in configuration, read per environment (spec
2026-10-23-configured-schedules §3b, option A ruled 2026-10-23).

`scheduled_work` keeps one row per job, and a job written
`@Scheduled(cron = "${orders.sweep.cron}")` stays `unresolved` there with its expression
verbatim: the schedule that runs is the deployment's. What the REPOSITORY configures for it
is a value, environment by environment, and this pass writes it beside the job — one
`resolved_schedules` row per (job whose expression holds the placeholder opener, environment
of `resolved_config`), carrying the job's own `handler`, `trigger` and `expression`.

**One placeholder rule.** The expression is substituted by `resolve/config.py::substitute`,
the walk `resolve_config` itself uses, with the config model's own delimiters and
`default_separator` (D02 §2i) — so `${key:default}`, a literal default and an unclosed
opener mean here exactly what they mean in a configuration file. Only the LOOKUP is this
pass's: one environment's `resolved_config` rows, keyed as the model's `key_matching` says.
Those values are already fully substituted, so the lookup never recurses.

**What it does not do.** A SpEL `#{…}` expression holds no placeholder opener and gets no
rows; nothing here evaluates one (spec §4). A job with a literal expression gets none either:
its `scheduled_work` row already says everything.
"""

from collections.abc import Callable

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.config import placeholder_rule, substitute
from sextant.domain.config_keys import normalize_key


def record_resolved_schedules(workspace: Workspace, catalogs: list[Catalog]) -> None:
    """Replaces `resolved_schedules` whole. Reads `scheduled_work` once and
    `resolved_config` once, joined in memory (spec §5): rows written are
    jobs-with-placeholders × environments.

    Only the FIRST declared config model's delimiters and key matching are read — the
    family's base catalog's (D02 §2i: one per framework family; only `spring-web.yml`
    declares one today). `resolve_config` resolves every declaring catalog into the one
    `resolved_config`, which carries no model column, so its rows cannot be split by
    model and a second family's would be looked up under the first's rule. With no model
    declared there is no `resolved_config` either, and so nothing to read."""
    workspace.derive("resolved_schedules_reset")
    model = next((c.config_model for c in catalogs if c.config_model), None)
    if model is None:
        return
    placeholders, key_matching = placeholder_rule(model)
    jobs = [
        job
        for job in workspace.query("scheduled_work")
        if placeholders["open"] in str(job["expression"])
    ]
    if not jobs:
        return
    by_environment: dict[str, list[dict[str, object]]] = {}
    for row in workspace.query("resolved_config"):
        by_environment.setdefault(str(row["environment"]), []).append(row)
    rows: list[dict[str, object]] = []
    for environment in sorted(by_environment):
        lookup = _environment_lookup(by_environment[environment], key_matching)
        for job in jobs:
            value, reason = substitute(str(job["expression"]), placeholders, lookup)
            rows.append(
                {
                    "handler": job["handler"],
                    "trigger": job["trigger"],
                    "expression": job["expression"],
                    "environment": environment,
                    "value": value,
                    "unresolved_reason": reason,
                }
            )
    if rows:
        workspace.derive("resolved_schedules_insert", rows=rows)


def _environment_lookup(
    config: list[dict[str, object]], key_matching: str
) -> Callable[[str], tuple[str | None, str | None]]:
    """`substitute`'s lookup over ONE environment's resolved rows. Where relaxed matching
    folds two configured spellings onto one key, the first row in the `resolved_config`
    named query's order (`ORDER BY environment, key`) wins — the alphabetically first
    spelling. That DIVERGES from `resolve/config.py::_normalized_index`, which takes the
    first in merged-layering order; a known divergence, logged rather than matched here,
    because `resolved_config` keeps no layering order to match it with. A row resolved to
    no value answers its own reason; a key no row names is `missing_key`, as
    `resolve_config` answers a reference to a key its layering never declared."""

    def keyed(key: str) -> str:
        return normalize_key(key) if key_matching == "relaxed" else key

    index: dict[str, tuple[str | None, str | None]] = {}
    for row in config:
        value = row["value"]
        answer = (
            (str(value), None)
            if value is not None
            else (None, str(row["unresolved_reason"] or "missing_key"))
        )
        index.setdefault(keyed(str(row["key"])), answer)

    def lookup(ref_key: str) -> tuple[str | None, str | None]:
        return index.get(keyed(ref_key), (None, "missing_key"))

    return lookup
