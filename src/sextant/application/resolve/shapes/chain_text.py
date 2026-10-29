"""A builder chain written as text, constants only (Quartz spec 2026-10-28 §3b, ruling 4).

A schedule that is not a cron expression is recorded as the chain that built it, written
`root(args).step(args)…` with the method names as compiled — deterministic, and never a
summary of what the chain means. The text is the whole answer or there is none: an
argument that is not a constant (or a nested call of constants) makes the whole chain
`None`, because a chain with one hole written as text would read as a complete schedule.

Pure over the rows it is handed: it names no framework, and reads no catalog.
"""

import json
from collections.abc import Mapping, Sequence
from typing import Any

from sextant.domain.symbols import bare_descriptor, simple_name

_NESTED = "unresolved"


def chain_text(
    sites: Sequence[Mapping[str, Any]], effective: Mapping[Any, Mapping[str, Any]]
) -> str | None:
    """`sites` (root to last step) as `root(args).step(args)…`, or `None` when any argument
    is neither a constant nor a nested call whose own arguments are. `effective` maps a
    value id to the call site that produced it, for a nested call argument."""
    steps = [_call(site, effective, qualified=False) for site in sites]
    if not steps or any(step is None for step in steps):
        return None
    return ".".join(str(step) for step in steps)


def _call(
    site: Mapping[str, Any], effective: Mapping[Any, Mapping[str, Any]], *, qualified: bool
) -> str | None:
    arguments = [_argument(argument, effective) for argument in site["arguments"]]
    if any(argument is None for argument in arguments):
        return None
    name = str(site["name"])
    if qualified:
        name = f"{simple_name(bare_descriptor(str(site['owner'])))}.{name}"
    return f"{name}({', '.join(str(argument) for argument in arguments)})"


def _argument(
    argument: Mapping[str, Any], effective: Mapping[Any, Mapping[str, Any]]
) -> str | None:
    kind = argument.get("kind")
    if kind == "string":
        return json.dumps(str(argument["value"]), ensure_ascii=False)
    if kind in ("int", "long"):
        return str(int(argument["value"]))
    if kind == "boolean":
        return "true" if argument["value"] else "false"
    if kind == "class":
        symbol = argument.get("symbol")
        return None if symbol is None else simple_name(bare_descriptor(str(symbol)))
    if kind == "array":
        elements = [_argument(element, effective) for element in argument.get("elements") or []]
        return (
            None
            if any(element is None for element in elements)
            else ", ".join(str(element) for element in elements)
        )
    if kind == _NESTED and argument.get("source") is not None:
        producer = effective.get(argument["source"])
        return None if producer is None else _call(producer, effective, qualified=True)
    return None
