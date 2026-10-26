"""A catalog's `<owner>#<member>` tables and the static-field verb read (D02 §2's
`combinator` and `fluent` styles).

`combinator` and `fluent` both turn a verb written in code into a catalog word, and the
framework decides how the code writes it. Ktor 3.0.3 reads `HttpMethod.Get` through a
getter on the companion object (`verb_values.getters`); Ktor 3.6.0 reads it straight off
a static field (`verb_values.fields`, the `getstatic` the facts carry as a `field`-kind
argument). Both forms are keyed the same way, so one table builder and one validity rule
serve the two, and the static-field read lives here once instead of in each engine.
"""

from typing import Any

from sextant.domain.symbols import bare_descriptor, member_name, owner_of


def member_table(declared: dict[str, Any]) -> dict[tuple[str, str], str]:
    """A `getters:` or `fields:` table — `"<owner>#<member>": <value>` — keyed as the facts
    key a call or a field: the dotted spelling converted to the descriptor form
    (`type_descriptor`'s own conversion, so the owner half compares as every rule owner
    does), then split by the symbol seam into the owner's descriptor and the member's name.
    Only ever called on a table `names_members` already passed."""
    table: dict[tuple[str, str], str] = {}
    for key, value in declared.items():
        descriptor = member_descriptor(str(key))
        table[(str(owner_of(descriptor)), member_name(descriptor))] = str(value)
    return table


def member_descriptor(key: str) -> str:
    """A table key in the descriptor form the facts carry: the dotted owner becomes the
    slashed one, the `#` and the member name stay as written — exactly what
    `type_descriptor` does to a rule owner, applied to a member spelling."""
    return key.replace(".", "/")


def names_members(declared: Any) -> bool:
    """Whether a table is a mapping whose every key is exactly one owner and one member
    name — the seam's owner, the seam's member, and nothing between or after them."""
    return isinstance(declared, dict) and all(
        isinstance(key, str) and _names_a_member(member_descriptor(key)) for key in declared
    )


def _names_a_member(descriptor: str) -> bool:
    owner = owner_of(descriptor)
    member = member_name(descriptor)
    return owner is not None and bool(member) and owner + member == descriptor


def static_field_value(
    argument: dict[str, Any] | None, fields: dict[tuple[str, str], str]
) -> str | None:
    """A constant read straight off a STATIC FIELD (`HttpMethod.Get` on Ktor 3.x): the
    argument is `field`-kind and its `symbol` names the owner and the field, looked up in
    the declared table. Anything else — another kind, or a field the table does not name —
    reads as nothing: one measured member at a time, never a name guessed to be its value.
    One dict read per argument (GUIDELINES §8.7)."""
    if argument is None or argument.get("kind") != "field" or argument.get("symbol") is None:
        return None
    descriptor = bare_descriptor(str(argument["symbol"]))
    return fields.get((str(owner_of(descriptor)), member_name(descriptor)))
