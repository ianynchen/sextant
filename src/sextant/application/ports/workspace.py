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

from sextant.domain.redaction import Redactor


class Workspace(Protocol):
    def load_facts(self, fact_root: Path) -> int:
        """Bulk-ingest every fact file under fact_root. Returns rows loaded."""

    def derive(self, name: str, **params: object) -> None:
        """Run one named derivation, rebuilding its tables whole. `params`
        are bound into the derivation's SQL by name — this is how a generic
        engine (D02) passes catalog data in without the SQL ever containing
        the catalog's literals."""

    def query(self, name: str, **params: object) -> list[dict[str, object]]:
        """Run one named query. Unknown names raise KeyError.

        The rows may be shared between calls — a query over facts alone is read once
        per load and the same list handed back after that — so a caller reads them and
        never writes into a row. A JSON column the storage names as decoded arrives as
        an object (a dict, a list, or `None`), not as text; every other JSON column is
        text and the caller decodes it."""

    def export_tables(self, destination: Path, redactor: Redactor) -> list[str]:
        """Write the bundle's graph tables as Parquet, one file per table.

        `redactor` masks on the way out (2K design §1) — the tables themselves
        stay verbatim, so the parameter is not optional: a bundle is written to
        leave, and an implementation with nowhere to put the rule set would be
        one that cannot say what it masked."""

    def export_facts(self, destination: Path, redactor: Redactor) -> int:
        """Write the raw facts as Parquet, one file per document.

        `redactor` masks on the way out, as `export_tables` does and for the
        same reason: everything the bundle carries leaves, so a masked graph
        table beside an unmasked fact file would mask nothing. The workspace's
        own fact rows stay verbatim."""

    def close(self) -> None: ...
