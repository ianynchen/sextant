"""YAML config files (D00 §5c). `pyyaml` parses structure — mappings,
sequences, multi-document streams — but its default scalar resolution
coerces bare `true`/`123`/`null`/dates into Python `bool`/`int`/`float`/
`datetime`, and a config value is "verbatim, always a string, never
coerced" (D00 §5c: a value is a claim to resolve, not a typed answer).

The fix is a resolver-free *construction*, not a resolver-free *load*: the
implicit-tag resolver still runs (it has to, to pick a constructor), but
every scalar constructor that would coerce is replaced with one that
returns the node's raw text instead. `tag:yaml.org,2002:str` already does
this by construction, so only `null`, `bool`, `int`, `float` and
`timestamp` need overriding. This also means a YAML *key* that looks like a
number or a boolean loads as that same literal string, which is the
consistent reading of "never coerced" — a key is a scalar like any other."""

import yaml

from sextant.application.ports.artifacts import ReadRequest
from sextant.domain.facts import ConfigEntryFact, Document, Fact
from sextant.ingress.read import build_document


class _RawScalarLoader(yaml.SafeLoader):  # type: ignore[misc]
    """A SafeLoader whose non-string scalar tags construct their literal
    text instead of a typed Python value."""


def _construct_raw(loader: yaml.SafeLoader, node: yaml.Node) -> str:
    return str(loader.construct_scalar(node))


for _tag in (
    "tag:yaml.org,2002:null",
    "tag:yaml.org,2002:bool",
    "tag:yaml.org,2002:int",
    "tag:yaml.org,2002:float",
    "tag:yaml.org,2002:timestamp",
):
    _RawScalarLoader.add_constructor(_tag, _construct_raw)


def _flatten(value: object, prefix: str, doc_index: int, document_id: str) -> list[Fact]:
    """Nested maps flatten to dot-joined paths; a list value normalizes to
    indexed segments (`foo[0]`, `foo[1]` — Spring's own canonical form and a
    neutral one, D00 §5c). Recursion order is the map's/list's own iteration
    order, which is declaration order: `dict` preserves insertion order, and
    `_RawScalarLoader` builds each mapping by inserting keys in the order
    `safe_load` reads them off the document (NFR-1)."""
    if isinstance(value, dict):
        facts: list[Fact] = []
        for raw_key, child in value.items():
            path = f"{prefix}.{raw_key}" if prefix else str(raw_key)
            facts.extend(_flatten(child, path, doc_index, document_id))
        return facts
    if isinstance(value, list):
        facts = []
        for index, child in enumerate(value):
            facts.extend(_flatten(child, f"{prefix}[{index}]", doc_index, document_id))
        return facts
    # Every scalar constructed by _RawScalarLoader is already a plain str
    # (see module docstring) — verbatim, never coerced.
    return [
        ConfigEntryFact(
            document_id=document_id,
            # No relaxed-binding normalization happens at ingestion (M04
            # pass 2's `key_matching` catalog knob owns that) — the dotted
            # path is built purely by joining the literal keys as written,
            # so key_raw and key_path name the same string here.
            key_raw=prefix,
            key_path=prefix,
            value=value if isinstance(value, str) else str(value),
            doc_index=doc_index,
        )
    ]


class YamlConfigReader:
    """Keyed by extension `yml`/`yaml` (M03); both normalize to the one
    `yaml` format on the Document (D00 §5c: the format, never the raw
    extension)."""

    def accepts(self, file_kind: str) -> bool:
        return file_kind in ("yml", "yaml")

    def read(self, request: ReadRequest) -> list[tuple[Document, list[Fact]]]:
        pairs: list[tuple[Document, list[Fact]]] = []
        for file in request.files:
            content = file.read_bytes()
            try:
                # Forced eager so a failure partway through a multi-document
                # stream is caught here, not left for a caller iterating a
                # generator — D00 §5c: an unparseable file yields zero
                # entries, not the entries from whichever documents happened
                # to parse before the one that broke.
                documents = list(yaml.load_all(content, Loader=_RawScalarLoader))
            except yaml.YAMLError as error:
                document = build_document(
                    file=file,
                    root=request.root,
                    module_id=request.module_id,
                    language="yaml",
                    content=content,
                    partial=True,
                    partial_reason=f"unparseable yaml: {error}",
                )
                pairs.append((document, []))
                continue

            document = build_document(
                file=file,
                root=request.root,
                module_id=request.module_id,
                language="yaml",
                content=content,
            )
            facts: list[Fact] = []
            for doc_index, parsed in enumerate(documents):
                if parsed is None:
                    # An empty document (e.g. a bare `---` with nothing
                    # after it) — a real, zero-key document, not an error.
                    continue
                facts.extend(_flatten(parsed, "", doc_index, document.document_id))
            pairs.append((document, facts))
        return pairs
