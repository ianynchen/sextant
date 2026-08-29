"""The Workspace port (ARCHITECTURE §7). Its surface is deliberately narrow —
bulk load, the named derivations, the named queries of D01 — so that it cannot
decay into a SQL pass-through.

**The names stay strings.** D01 declares these sets, so an enum in `domain`
would put them under the same discipline as every other closed set and let
mypy reject a typo. Considered and declined: six values across eleven call
sites, and the failure it prevents — a mistyped name — raises immediately and
is caught by any test that exercises the path. The reading cost at every call
site outweighs it. Revisit if the sets grow or a second Workspace appears."""

from pathlib import Path
from typing import Protocol


class Workspace(Protocol):
    def load_facts(self, fact_root: Path) -> int:
        """Bulk-ingest every fact file under fact_root. Returns rows loaded."""

    def derive(self, name: str, **params: object) -> None:
        """Run one named derivation, rebuilding its tables whole. `params`
        are bound into the derivation's SQL by name — this is how a generic
        engine (D02) passes catalog data in without the SQL ever containing
        the catalog's literals."""

    def query(self, name: str, **params: object) -> list[dict[str, object]]:
        """Run one named query. Unknown names raise KeyError."""

    def export_tables(self, destination: Path) -> list[str]:
        """Write the bundle's graph tables as Parquet, one file per table."""

    def export_facts(self, destination: Path) -> int:
        """Write the raw facts as Parquet, one file per document."""

    def close(self) -> None: ...
