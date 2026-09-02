"""`.wsdl` / `.xsd` contract files (2I design §3). A reader here reads the
neutral shape of the file — one embedded schema payload, verbatim — and never
interprets it: understanding a schema format is
`ingress.interpret.descriptors`'s job alone (2G design §3), and even the
standard-library XML parser this module deliberately does not import is
confined there (`tests/architecture/test_protobuf_confinement.py`).

Two extensions, ONE `schema_format`, because they are one type universe and
not two formats: a WSDL declares its payload types by embedding XSD in its
`<types>` element, and the `.xsd` beside it is the same schema split across a
file boundary by an `xsd:import`. Which of the two a given file was is still
recorded — as the Document's `language`, which is where D00 §2 puts the
format of a source file.

Nothing here reads a name out of the file, for the same reason the SDL reader
does not: a WSDL is meaningless without the schemas it imports, so the merge
only makes sense module-wide and happens once, later, in the interpreter. The
`symbol` is therefore the file's own path under the schema root — which is
also what a sibling's relative `schemaLocation` has to be resolved against, so
a name read out of the document could not have served.
"""

from sextant.application.ports.artifacts import ReadRequest, file_kind
from sextant.domain.facts import Document, EmbeddedDescriptorFact, Fact
from sextant.ingress.read import build_document


class WsdlXsdReader:
    """Keyed by extensions `wsdl` and `xsd` (M03) — the service contract and
    the schema it declares its payloads in."""

    reads_schema_sources = True

    def accepts(self, file_kind: str) -> bool:
        return file_kind in ("wsdl", "xsd")

    def read(self, request: ReadRequest) -> list[tuple[Document, list[Fact]]]:
        pairs: list[tuple[Document, list[Fact]]] = []
        for file in request.files:
            content = file.read_bytes()
            language = file_kind(file)
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError as error:
                # The one failure a reader that never parses can still have.
                # XML that is text but not well-formed is NOT this failure:
                # only the interpreter may decide that, and it reports it as
                # that payload's gap. No `symbol` to name here without reading
                # the document, so this file yields no embedded_descriptor
                # fact at all — `partial` is the whole story, as it is for an
                # unreadable `.avsc`.
                document = build_document(
                    file=file,
                    root=request.root,
                    module_id=request.module_id,
                    language=language,
                    content=content,
                    partial=True,
                    partial_reason=f"unreadable {language} contract: {error}",
                )
                pairs.append((document, []))
                continue

            document = build_document(
                file=file,
                root=request.root,
                module_id=request.module_id,
                language=language,
                content=content,
            )
            fact = EmbeddedDescriptorFact(
                document_id=document.document_id,
                # The file's own path under the schema root, the same
                # path-derived display identity the SDL reader records — and
                # the name a gap carries when the interpreter cannot read this
                # file. It is never the cross-origin join key
                # (`DeclaredShapeFact.schema_name` is that), and one contract
                # file declares many types, so no single type name could stand
                # for it. The interpreter also resolves relative
                # `schemaLocation` references against it.
                symbol=file.relative_to(request.root).as_posix(),
                schema_format="wsdl",
                payload=text,
                origin="source",
            )
            pairs.append((document, [fact]))
        return pairs
