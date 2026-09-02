"""What every schema format's branch shares: the two origins a payload can
have, D01 §5's element descriptor readers, and the `GeneratedNaming` seam.

Its own module because `interpret.descriptors` dispatches to the per-format
branches and the branches need these — one of the two directions had to stop
importing the other, and the shared vocabulary is the half that depends on
nothing. Nothing here understands a schema format: that is each branch's job,
and confining it to one module per format is what
`tests/architecture/test_protobuf_confinement.py` enforces.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

# The two origins a payload can have, and the two evidence tiers they earn.
type Origin = Literal["compiled", "source"]


@dataclass(frozen=True)
class SchemaLocation:
    """Where one declared type sits in its schema, in the schema's own terms.

    Everything a code generator needs to name the class it produced, and
    nothing that presumes which generator ran: `options` are the file's
    codegen options under the names the schema itself gives them, and
    `declared_names` the type names the file declares at top level — which one
    generator needs to avoid a collision and another may ignore.
    """

    schema_format: Literal["protobuf", "avro"]
    # The schema file's own name (`order.proto`); empty where the format has
    # no file identity of its own, as an Avro record does not.
    file_name: str
    # The schema's package or namespace, as it declares it.
    package: str
    # The nesting path to the type, outermost first: `("OrderRequest",
    # "Line")` for a message declared inside another.
    path: tuple[str, ...]
    options: Mapping[str, object]
    declared_names: frozenset[str]


class GeneratedNaming(Protocol):
    """How a schema type is named once a code generator has compiled it into a
    class.

    Per-language knowledge, which is why it is a seam rather than a function
    here: the interpreter is the one place that understands a schema format,
    and it stays a place that understands no language (ARCHITECTURE §10). The
    implementation lives in the language adapter that owns the naming rules,
    and the composition root wires it in.
    """

    def class_symbol(self, location: SchemaLocation) -> str:
        """The symbol of the generated class a payload of this type travels
        as, in the fact stream's grammar (D00 §5a)."""
        ...


def evidence_for(origin: Origin) -> Literal["compiler", "declared"]:
    """A schema compiled into the artifact was written by a compiler; a schema
    file in the repository is a declaration about what the build ought to
    ship (2G design §3)."""
    return "compiler" if origin == "compiled" else "declared"


def wire_type_of(described: Mapping[str, object]) -> str:
    return str(described["wire_type"])


def wire_format_of(described: Mapping[str, object]) -> str | None:
    found = described["wire_format"]
    return None if found is None else str(found)


def item_of(described: Mapping[str, object]) -> dict[str, object] | None:
    """What a collection holds, when the described type is one."""
    held = described.get("item")
    return held if isinstance(held, dict) else None


def shape_ref_of(described: Mapping[str, object]) -> str | None:
    """The shape an object reference points at, when the described type is
    one."""
    found = described.get("shape_id")
    return None if found is None else str(found)
