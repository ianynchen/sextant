"""The descriptor-interpretation seam `analyze` wires in (2G design §3).

`ingress.interpret.descriptors.interpret_descriptors` is the one place in the
system that understands a schema format, and it needs a `GeneratedNaming` the
JVM-confinement rule says only the cli composition root may construct
(`JvmGeneratedNaming` lives under `ingress.extract.jvm`). `application` sits
below `ingress` in the layering contract, so `analyze` cannot import either of
those directly — this Protocol is what it accepts instead, satisfied by an
adapter cli constructs and passes down: an object Protocol with a named
method, the same shape every other port here uses (`Scanner`, `Detector`,
`ArtifactReader`) — never a bare callable, so this seam does not stand out as
the one port that is shaped differently."""

from collections.abc import Sequence
from typing import Protocol

from sextant.domain.facts import DeclaredShapeFact, EmbeddedDescriptorFact


class DescriptorInterpreter(Protocol):
    def interpret(
        self, descriptors: Sequence[EmbeddedDescriptorFact]
    ) -> tuple[list[DeclaredShapeFact], list[str]]: ...
