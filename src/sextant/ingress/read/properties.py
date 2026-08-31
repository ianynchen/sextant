"""`.properties` config files (D00 §5c). Hand-rolled on purpose — the format
is `key=value` or `key: value` lines, comments, and nothing else worth a
dependency for."""

from sextant.application.ports.artifacts import ReadRequest
from sextant.domain.facts import ConfigEntryFact, Document, Fact
from sextant.ingress.read import build_document

# `key` is unambiguous once a delimiter is found: the first `=` or `:` on
# the line, whichever comes first. Neither is escapable in this reader —
# escape sequences (`\:`, `\=`, `\n`, `\uXXXX`) are read literally, the same
# "never interpreted" discipline that leaves `${x}` untouched.
_DELIMITERS = "=:"


def _entry(line: str) -> tuple[str, str] | None:
    """One line's key and value, or None for a comment, a blank line, or a
    line with no delimiter — which does not kill the file (D00 §5c: a
    reader degrades honestly, it never crashes on one bad line).

    A trailing backslash line continuation (the format's own multi-line
    value syntax) is unsupported and left as-is: the backslash stays part
    of the value verbatim, and the next line is parsed as its own entry
    rather than being joined to it."""
    stripped = line.lstrip(" \t")
    if not stripped or stripped[0] in "#!":
        return None
    for index, char in enumerate(stripped):
        if char in _DELIMITERS:
            key = stripped[:index].rstrip(" \t")
            # Only the whitespace immediately after the delimiter is not
            # part of the value, matching how the format is conventionally
            # read; everything past that — including trailing spaces — is
            # verbatim (D00 §5c), never trimmed.
            value = stripped[index + 1 :].lstrip(" \t")
            return (key, value) if key else None
    return None


class PropertiesReader:
    """Keyed by extension `properties` (M03)."""

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
                key, value = parsed
                facts.append(
                    ConfigEntryFact(
                        document_id=document.document_id,
                        key_raw=key,
                        # No relaxed-binding normalization happens at
                        # ingestion (that is M04 pass 2's `key_matching`
                        # catalog knob) — a properties key is already the
                        # dotted form, so key_path equals key_raw verbatim.
                        key_path=key,
                        value=value,
                    )
                )
            pairs.append((document, facts))
        return pairs
