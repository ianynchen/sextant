"""Generated-class naming for the JVM (2G design §3).

A schema type that has been through a code generator travels as a class, and
the class it travels as is what the fact stream's type references name. Which
class that is, is a rule of the generator's target language: protoc reads the
file's `java_*` options, Avro puts a record's namespace where a package goes.
So the rule lives here, in the adapter that owns this platform's names
(ARCHITECTURE §10), and reaches the interpreter — which understands schema
formats and no language at all — as a `GeneratedNaming` the composition root
wires in.

The interpreter hands over a `SchemaLocation`: the schema's own package, the
nesting path, and the file's codegen options under the names the schema gives
them. Reading `java_package` out of that mapping is this module's whole
language-specific claim, and it is the claim the confinement rule wants
findable in one place.
"""

import re

from sextant.domain.symbols import type_descriptor
from sextant.ingress.interpret.descriptors import SchemaLocation

# protoc's file options that decide where a message's class lands. Names of
# option fields, read out of a descriptor the interpreter passed through.
_PACKAGE = "java_package"
_OUTER_CLASSNAME = "java_outer_classname"
_MULTIPLE_FILES = "java_multiple_files"

# The compiler's nesting notation, which is also the notation a class file
# carries and therefore the one the fact stream's symbols already use.
_NESTED = "$"


class JvmGeneratedNaming:
    """protoc's and Avro's naming rules for this platform, as one seam.

    Symbols are built through `domain/symbols.type_descriptor`, so the grammar
    stays defined in exactly one place; what this class contributes is the
    dotted name, not the grammar.
    """

    def class_symbol(self, location: SchemaLocation) -> str:
        if location.schema_format == "avro":
            # A record's namespace is the package and its name is the class:
            # Avro generates one top-level class per record, never a nested
            # one, so the path arrives already whole.
            return type_descriptor(_dotted(location.package, ".".join(location.path)))
        return type_descriptor(_dotted(_package(location), _NESTED.join(_nesting(location))))


def _package(location: SchemaLocation) -> str:
    """The declared option, or the schema's own package — protoc's fallback
    when a file names no target package."""
    return str(location.options.get(_PACKAGE, "")) or location.package


def _nesting(location: SchemaLocation) -> list[str]:
    """Messages are generated as classes inside the file's holder class,
    unless the file asks for one file per message — in which case each is
    top-level and only the message nesting remains."""
    if bool(location.options.get(_MULTIPLE_FILES, False)):
        return list(location.path)
    return [_holder_class(location), *location.path]


def _holder_class(location: SchemaLocation) -> str:
    """The declared holder name, or protoc's default for a file that names
    none: the file's base name camel-cased, with `OuterClass` appended when a
    type in the file already claims that name. Without the fallback, every
    schema that omits the option would be named after a class that does not
    exist, and the shape would join nothing."""
    declared = str(location.options.get(_OUTER_CLASSNAME, ""))
    if declared:
        return declared
    stem = location.file_name.rsplit("/", 1)[-1].removesuffix(".proto")
    camel = "".join(part[:1].upper() + part[1:] for part in re.split(r"[^A-Za-z0-9]", stem))
    return f"{camel}OuterClass" if camel in location.declared_names else camel


def _dotted(package: str, name: str) -> str:
    return f"{package}.{name}" if package else name
