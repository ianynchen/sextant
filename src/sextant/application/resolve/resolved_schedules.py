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

**Every exit masks a value by the keys it was read through.** Each row carries `keys`, every
key `substitute` asked the environment's lookup for, in order (a JSON array, the
`participants.aliases` convention). A schedule IS the value of the key that configures it,
so where that key names a secret — `app.token.cleanup.cron`, whose value `resolved_config`
masks by the key rule — the schedule masks whole as well; `redact_schedule_value` is that
decision, called by the bundle export and the document alike.

**What it does not do.** A SpEL `#{…}` expression holds no placeholder opener and gets no
rows; nothing here evaluates one (spec §4). A job with a literal expression gets none either:
its `scheduled_work` row already says everything.
"""

import json
from collections.abc import Callable, Sequence

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.config import placeholder_rule, substitute
from sextant.domain.config_keys import normalize_key
from sextant.domain.redaction import REDACTED, Redactor


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
            asked: list[str] = []
            value, reason = substitute(
                str(job["expression"]), placeholders, _recording(lookup, asked)
            )
            rows.append(
                {
                    "handler": job["handler"],
                    "trigger": job["trigger"],
                    "expression": job["expression"],
                    "environment": environment,
                    "keys": json.dumps(list(dict.fromkeys(asked))),
                    "value": value,
                    "unresolved_reason": reason,
                }
            )
    if rows:
        workspace.derive("resolved_schedules_insert", rows=rows)


def redact_schedule_value(redactor: Redactor, keys: Sequence[str], value: str) -> str:
    """A configured schedule as an exit may print it: masked WHOLE when any key it was read
    through names a secret — the test `redact_value` masks a configuration value by, so the
    schedule and the `resolved_config` row it was read from mask alike — and otherwise
    through `redact_text`, the value patterns and URL userinfo stripping. The one decision
    for `resolved_schedules.value`; the bundle export and the document both call it."""
    if any(redactor.masks_key(key) for key in keys):
        return REDACTED
    return redactor.redact_text(value)


def _recording(
    lookup: Callable[[str], tuple[str | None, str | None]], asked: list[str]
) -> Callable[[str], tuple[str | None, str | None]]:
    """`lookup`, noting in `asked` every key it is asked for."""

    def recorded(ref_key: str) -> tuple[str | None, str | None]:
        asked.append(ref_key)
        return lookup(ref_key)

    return recorded


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
