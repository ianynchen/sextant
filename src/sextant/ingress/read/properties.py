"""`.properties` config files (D00 §5c). Hand-rolled on purpose — the format
is `key=value` or `key: value` lines, comments, and nothing else worth a
dependency for."""

from sextant.application.ports.artifacts import ReadRequest
from sextant.domain.facts import ConfigEntryFact, Document, Fact
from sextant.ingress.read import build_document

# The delimiter is the first unescaped `=` or `:` on the line, whichever
# comes first. A backslash immediately before one of these two characters
# escapes it — see `_entry` — no other escape sequence is interpreted.
_DELIMITERS = "=:"


def _entry(line: str) -> tuple[str, str, str] | None:
    """One line's key_raw, key_path, and value, or None for a comment, a
    blank line, or a line with no delimiter — which does not kill the file
    (D00 §5c: a reader degrades honestly, it never crashes on one bad
    line).

    A backslash immediately before a delimiter escapes it — `a\\:b=v` is
    one key `a:b`, not the key `a\\` the naive first-delimiter scan would
    find. `key_raw` keeps the still-escaped, as-written spelling (`a\\:b`);
    `key_path` carries the unescaped form (`a:b`) — the raw-vs-path
    distinction D00 §5c states exists precisely for a case like this one,
    where the two fields genuinely differ (2F review fix round 1: a flat
    format is the first reader to make that distinction real — YAML's own
    key_raw/key_path stay equal, since joining literal segments verbatim
    is not the same kind of transform as unescaping one). No other escape
    sequence is interpreted (`\\n`, `\\uXXXX`, a literal `\\\\`) — read
    literally, the same "never interpreted" discipline that leaves `${x}`
    untouched.

    A trailing backslash line continuation (the format's own multi-line
    value syntax) is unsupported and left as-is: the backslash stays part
    of the value verbatim, and the next line is parsed as its own entry
    rather than being joined to it."""
    stripped = line.lstrip(" \t")
    if not stripped or stripped[0] in "#!":
        return None
    index = 0
    while index < len(stripped):
        char = stripped[index]
        if char == "\\" and index + 1 < len(stripped) and stripped[index + 1] in _DELIMITERS:
            index += 2  # an escaped delimiter is key content, not the split point
            continue
        if char in _DELIMITERS:
            key_raw = stripped[:index].rstrip(" \t")
            key_path = key_raw.replace("\\:", ":").replace("\\=", "=")
            # Only the whitespace immediately after the delimiter is not
            # part of the value, matching how the format is conventionally
            # read; everything past that — including trailing spaces — is
            # verbatim (D00 §5c), never trimmed.
            value = stripped[index + 1 :].lstrip(" \t")
            return (key_raw, key_path, value) if key_raw else None
        index += 1
    return None


class PropertiesReader:
    """Keyed by extension `properties` (M03)."""

    reads_schema_sources = False

    def accepts(self, file_kind: str) -> bool:
        return file_kind == "properties"

    def read(self, request: ReadRequest) -> list[tuple[Document, list[Fact]]]:
        pairs: list[tuple[Document, list[Fact]]] = []
        for file in request.files:
            content = file.read_bytes()
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError as error:
                document = build_document(
                    file=file,
                    root=request.root,
                    module_id=request.module_id,
                    language="properties",
                    content=content,
                    partial=True,
                    partial_reason=f"not valid utf-8: {error}",
                )
                pairs.append((document, []))
                continue

            document = build_document(
                file=file,
                root=request.root,
                module_id=request.module_id,
                language="properties",
                content=content,
            )
            facts: list[Fact] = []
            # Declaration order is line order (NFR-1) — a properties file has
            # no nesting, so no further ordering question arises.
            for line in text.splitlines():
                parsed = _entry(line)
                if parsed is None:
                    continue
                key_raw, key_path, value = parsed
                facts.append(
                    ConfigEntryFact(
                        document_id=document.document_id,
                        key_raw=key_raw,
                        key_path=key_path,
                        value=value,
                    )
                )
            pairs.append((document, facts))
        return pairs
