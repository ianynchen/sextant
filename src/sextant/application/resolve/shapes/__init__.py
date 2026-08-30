"""Roots a shape by unwrapping declared envelope wrappers (D02 §2a), expands
the rooted type into wire fields (D2), and points each endpoint at the shapes
its handler declares (D01 §3 Contracts)."""

from sextant.application.resolve.shapes.contracts import derive_endpoint_shapes
from sextant.application.resolve.shapes.expansion import ExpandedShapes, derive_shapes
from sextant.application.resolve.shapes.rooting import RootedType, root_type

__all__ = [
    "ExpandedShapes",
    "RootedType",
    "derive_endpoint_shapes",
    "derive_shapes",
    "root_type",
]
