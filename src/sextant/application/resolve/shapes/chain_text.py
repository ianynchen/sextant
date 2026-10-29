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

from sextant.domain.symbols import bare_descriptor, member_name, owner_of, short_class_name

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
    written = ", ".join(str(argument) for argument in arguments)
    name = str(site["name"])
    if not qualified:
        return f"{name}({written})"
    # A nested call is written as the source wrote it: a constructor with `new`, any other
    # call on what it was called on.
    if name == "<init>":
        return f"new {short_class_name(str(site['owner']))}({written})"
    receiver = _receiver(site, effective)
    return None if receiver is None else f"{receiver}.{name}({written})"


def _receiver(site: Mapping[str, Any], effective: Mapping[Any, Mapping[str, Any]]) -> str | None:
    """What a nested call was called on, written: its type for a static call; a named
    constant of the call's own type read by `getstatic` (`TimeUnit.MINUTES`, the `enum`
    argument's own rule: a static field whose type is its owner); a nested call that is
    itself written. `None` for anything else — a call written without its receiver would be
    a call nobody wrote (`TimeUnit.toMillis(5)`)."""
    if site.get("invoke_kind") == "static":
        return short_class_name(str(site["owner"]))
    field = site.get("receiver_field")
    if field is not None:
        symbol = bare_descriptor(str(field))
        owner = owner_of(symbol)
        # The call's owner is the type the receiver is declared as, so a field of that same
        # owner is a constant of its own type.
        if owner is None or owner != bare_descriptor(str(site["owner"])) or not member_name(symbol):
            return None
        return f"{short_class_name(owner)}.{member_name(symbol)}"
    producer = effective.get(site.get("receiver")) if site.get("receiver") is not None else None
    return None if producer is None else _call(producer, effective, qualified=True)


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
        return None if symbol is None else short_class_name(str(symbol))
    if kind == "enum":
        # A GETSTATIC of a named constant of its own type (`IntervalUnit.HOUR`): a literal,
        # unlike a `field`, which is a read of something that can vary.
        symbol = bare_descriptor(str(argument.get("symbol")))
        owner = owner_of(symbol)
        constant = member_name(symbol)
        if owner is None or not constant:
            return None
        return f"{short_class_name(owner)}.{constant}"
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
