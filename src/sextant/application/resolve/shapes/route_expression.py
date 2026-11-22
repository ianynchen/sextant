"""The paths a route expression serves (`url_is: expression`, D02; design 2026-11-22 §5c,
rulings R15 and R16): three structural reads of the text, never a regular-expression parser.

1. `^` and the final `$` are dropped and each named group `(?P<name>...)` becomes `<name>`.
2. A `?` after one literal character or one group makes that piece optional: the path with and
   without it, a closed set (two optional pieces at most, four paths).
3. Anything else the scan does not recognise (an unnamed group that is not optional, `|`
   outside a named group, a class, a quantifier, a backslash other than `\\.`, `\\-`, `\\/`, a
   `^` that is not first) is not exact: the expression as written.

The anchors follow the framework's match (`scripts/probes/django_rules.md`, "`re_path`"): an
endpoint is matched whole only when it ends in `$` (`fullmatch`; otherwise `search`, which
also serves longer paths); a mount prefix is a prefix match, exact when it starts with `^` and
has no final `$`."""

from itertools import product

# The `url_is` word saying a captured route is a route expression (D02).
URL_IS_EXPRESSION = "expression"

# The escapes that stand for their own character.
_ESCAPED = frozenset("./-")
# Characters that are regular-expression syntax wherever the scan meets them.
_SYNTAX = frozenset("[]{}*+.|^$)?\\(")
_MOST_OPTIONAL = 2


def paths_of(expression: str, *, prefix: bool = False) -> tuple[tuple[str, ...], bool]:
    """The paths `expression` serves and whether they are exact; not exact, the expression as
    written. `prefix` for a mount prefix, matched at the start of what is left of the path."""
    anchored, ended = expression.startswith("^"), expression.endswith("$")
    if ended and expression.endswith("\\$"):
        ended = False
    if not (anchored and not ended if prefix else ended):
        return (expression,), False
    pieces = _pieces(expression[int(anchored) : len(expression) - int(ended)])
    optional = [index for index, (_, may_drop) in enumerate(pieces or ()) if may_drop]
    if pieces is None or len(optional) > _MOST_OPTIONAL:
        return (expression,), False
    paths = []
    for kept in product((False, True), repeat=len(optional)):
        dropped = {index for index, keep in zip(optional, kept, strict=True) if not keep}
        paths.append(
            "".join(text for index, (text, _) in enumerate(pieces) if index not in dropped)
        )
    return tuple(paths), True


def _pieces(body: str) -> list[tuple[str, bool]] | None:
    """`body` as pieces `(text, optional)` in one left-to-right scan; None where any part of it
    is not one of the three reads."""
    pieces: list[tuple[str, bool]] = []
    at = 0
    while at < len(body):
        char = body[at]
        if char == "?":
            # Optional: the piece just read, once.
            if not pieces or pieces[-1][1]:
                return None
            pieces[-1] = (pieces[-1][0], True)
            at += 1
        elif char == "\\":
            if body[at + 1 : at + 2] not in _ESCAPED:
                return None
            pieces.append((body[at + 1], False))
            at += 2
        elif char == "(":
            end = _closing(body, at)
            if end is None:
                return None
            group = _group(body[at + 1 : end], body[end + 1 : end + 2] == "?")
            if group is None:
                return None
            pieces.append((group, False))
            at = end + 1
        elif char in _SYNTAX:
            return None
        else:
            pieces.append((char, False))
            at += 1
    return pieces


def _group(inner: str, optional: bool) -> str | None:
    """A named group's `<name>`; an optional unnamed group of literal text its text; else None."""
    if inner.startswith("?P<"):
        name, closed, _ = inner[3:].partition(">")
        return f"<{name}>" if closed and name.isidentifier() else None
    literal = _pieces(inner) if optional and not inner.startswith("?") else None
    if literal is None or any(may_drop for _, may_drop in literal):
        return None
    return "".join(text for text, _ in literal)


def _closing(body: str, start: int) -> int | None:
    """The index of the `)` that closes the `(` at `start`: escapes and classes skipped."""
    depth, at, in_class = 0, start, False
    while at < len(body):
        char = body[at]
        if char == "\\":
            at += 2
            continue
        if in_class:
            in_class = char != "]"
        elif char == "[":
            in_class = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return at
        at += 1
    return None
