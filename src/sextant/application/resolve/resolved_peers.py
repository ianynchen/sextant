"""The address of every client-side row, read per environment (M04 job 3, D02 §2d).

An endpoint row keeps its address expression (`${orders.url}/invoices`), and
`resolved_config` keeps the values. This reader joins the two for each environment and
writes nothing: one answer per (client-side row, environment of `resolved_config`).

**One placeholder rule.** `path` and `peer` are each filled by
`resolve/config.py::substitute`, the rule `resolve_config` and `resolved_schedules` use,
with the config model's delimiters, `default_separator` and key matching (D02 §2i). So
every placeholder in an address is filled, `${key:default}` takes its default, and a
reference reads here as it reads in a configuration file (CP-48). A text with no
placeholder is its own answer.

`direction <> inbound` rather than `= outbound`: a `both` row is a path the module both
exposes and calls (D02 §3's merge), so it carries a caller's address as an outbound row
does.

`path` and `peer` are filled independently. The one `unresolved_reason` reports `path`'s
answer first, and `peer`'s only when `path` had nothing to say; `unresolved_detail` is
the same answer's text. With no resolved environments the answer is empty: "the same
rows, unresolved" and "no environments to resolve against" are different claims.
"""

from collections.abc import Callable, Mapping

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.config import (
    Unresolved,
    config_model_of,
    environment_lookup,
    placeholder_rule,
    substitute,
)


def resolved_peers(workspace: Workspace, catalogs: list[Catalog]) -> list[dict[str, object]]:
    """One row per (client-side endpoint row, environment), ordered by environment, then
    by the row's own `protocol, method, path, peer, caller` (NFR-1), an absent value last.
    Reads `endpoints` once and `resolved_config` once."""
    placeholders, key_matching = placeholder_rule(config_model_of(catalogs))
    by_environment: dict[str, list[dict[str, object]]] = {}
    for row in workspace.query("resolved_config"):
        by_environment.setdefault(str(row["environment"]), []).append(row)
    candidates = [
        row
        for row in workspace.query("endpoints")
        if row["direction"] is not None and row["direction"] != "inbound"
    ]
    answers: list[dict[str, object]] = []
    for environment in sorted(by_environment):
        lookup = environment_lookup(by_environment[environment], key_matching)
        for row in candidates:
            path, path_failure = _filled(row["path"], placeholders, lookup)
            peer, peer_failure = _filled(row["peer"], placeholders, lookup)
            failure = path_failure or peer_failure
            answers.append(
                {
                    "protocol": row["protocol"],
                    "direction": row["direction"],
                    "method": row["method"],
                    "path": row["path"],
                    "peer": row["peer"],
                    "caller": row["caller"],
                    "catalog_id": row["catalog_id"],
                    "environment": environment,
                    "resolved_path": path,
                    "resolved_peer": peer,
                    "unresolved_reason": None if failure is None else failure.reason,
                    "unresolved_detail": None if failure is None else failure.detail,
                }
            )
    answers.sort(
        key=lambda a: tuple(
            (a[column] is None, str(a[column] or ""))
            for column in ("environment", "protocol", "method", "path", "peer", "caller")
        )
    )
    return answers


def _filled(
    expression: object,
    placeholders: Mapping[str, str],
    lookup: Callable[[str], tuple[str | None, Unresolved | None]],
) -> tuple[str | None, Unresolved | None]:
    """An address half with every placeholder filled, or the first failure. An absent half
    has nothing to fill and no failure."""
    if expression is None:
        return None, None
    return substitute(str(expression), placeholders, lookup)
