"""The Workspace port (ARCHITECTURE §7). Its surface is deliberately narrow —
bulk load, the named derivations, the named queries of D01 — so that it cannot
decay into a SQL pass-through."""

from pathlib import Path
from typing import Protocol


class Workspace(Protocol):
    def load_facts(self, fact_root: Path) -> int:
        """Bulk-ingest every fact file under fact_root. Returns rows loaded."""

    def derive(self, name: str) -> None:
        """Run one named derivation, rebuilding its tables whole."""

    def query(self, name: str, **params: object) -> list[dict[str, object]]:
        """Run one named query. Unknown names raise KeyError."""

    def close(self) -> None: ...
