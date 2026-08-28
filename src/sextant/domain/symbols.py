"""The SCIP symbol grammar as a string format (D00 §1). No indexer involved."""

import hashlib
from dataclasses import dataclass

NOT_APPLICABLE = "."


@dataclass(frozen=True)
class Symbol:
    scheme: str
    package_manager: str
    package: str
    version: str
    descriptor: str

    def __str__(self) -> str:
        return (
            f"{self.scheme} {self.package_manager} {self.package} {self.version} {self.descriptor}"
        )

    @property
    def short_id(self) -> str:
        """A prefixed, content-derived handle. Never bare hexadecimal: these
        get pasted into YAML and spreadsheets, which coerce types."""
        digest = hashlib.sha256(str(self).encode("utf-8")).hexdigest()[:8]
        return f"sym_{digest}"
