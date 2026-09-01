"""`.avsc` Avro schema source files (2G design §2). A reader here reads the
neutral shape of the file — one embedded schema payload, verbatim — and never
interprets it into declared fields: understanding a schema format is
`ingress.interpret.descriptors`'s job alone (2G design §3), run later,
module-wide, by `analyze` over every `embedded_descriptor` fact regardless of
which reader or scanner produced it."""

import json

from sextant.application.ports.artifacts import ReadRequest
from sextant.domain.facts import Document, EmbeddedDescriptorFact, Fact
from sextant.ingress.read import build_document


class AvscReader:
    """Keyed by extension `avsc` (M03)."""

    reads_schema_sources = True

    def accepts(self, file_kind: str) -> bool:
        return file_kind == "avsc"

    def read(self, request: ReadRequest) -> list[tuple[Document, list[Fact]]]:
        pairs: list[tuple[Document, list[Fact]]] = []
        for file in request.files:
            content = file.read_bytes()
            try:
                text = content.decode("utf-8")
                schema = json.loads(text)
                name = str(schema["name"])
            except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
                # A reader degrades honestly, it never crashes on one bad
                # file: no `symbol` to name here (there is no schema to read
                # one off), so this file yields no embedded_descriptor fact
                # at all — `partial` is the whole story.
                document = build_document(
                    file=file,
                    root=request.root,
                    module_id=request.module_id,
                    language="avro",
                    content=content,
                    partial=True,
                    partial_reason=f"unreadable avro schema: {error}",
                )
                pairs.append((document, []))
                continue

            document = build_document(
                file=file,
                root=request.root,
                module_id=request.module_id,
                language="avro",
                content=content,
            )
            namespace = schema.get("namespace")
            # Display identity only — `DeclaredShapeFact.schema_name` is the
            # cross-origin join key the interpreter derives on its own, so
            # nothing here has to match protoc's or avro-tools' naming rule.
            symbol = f"{namespace}.{name}" if namespace else name
            fact = EmbeddedDescriptorFact(
                document_id=document.document_id,
                symbol=symbol,
                schema_format="avro",
                # Verbatim, exactly as the file reads — the same "no
                # interpretation" contract a compiled payload's own emitter
                # keeps (EmbeddedDescriptorFact's own docstring).
                payload=text,
                origin="source",
            )
            pairs.append((document, [fact]))
        return pairs
