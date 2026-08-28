import sys
import time
from typing import TypedDict

from rich.console import Console
from rich.live import Live
from rich.table import Table

_PENDING, _RUNNING, _DONE, _FAILED = "·", "⠸", "✓", "✗"


class _Row(TypedDict):
    state: str
    label: str
    detail: str
    started: float | None
    elapsed: float


class RichProgress:
    """Live in-place task display on stderr, with elapsed time per task and a
    one-line reason on failure (M00). Falls back to plain lines when stderr is
    not a terminal."""

    def __init__(self) -> None:
        self._console = Console(stderr=True)
        self._rows: dict[str, _Row] = {}
        self._live: Live | None = None
        self._plain = not self._console.is_terminal

    def _render(self) -> Table:
        table = Table.grid(padding=(0, 2))
        for row in self._rows.values():
            elapsed = (
                row["elapsed"]
                if row["state"] in (_DONE, _FAILED)
                else (time.monotonic() - row["started"] if row["started"] else 0.0)
            )
            table.add_row(row["state"], row["label"], row["detail"], f"{elapsed:5.1f}s")
        return table

    def _refresh(self) -> None:
        if self._plain:
            return
        if self._live is None:
            self._live = Live(self._render(), console=self._console, refresh_per_second=8)
            self._live.start()
        else:
            self._live.update(self._render())

    def define(self, task_id: str, label: str) -> None:
        self._rows[task_id] = {
            "state": _PENDING,
            "label": label,
            "detail": "pending",
            "started": None,
            "elapsed": 0.0,
        }
        self._refresh()

    def start(self, task_id: str) -> None:
        row = self._rows[task_id]
        row["state"], row["detail"], row["started"] = _RUNNING, "", time.monotonic()
        if self._plain:
            print(f"start  {self._rows[task_id]['label']}", file=sys.stderr)
        self._refresh()

    def finish(self, task_id: str, detail: str = "") -> None:
        self._stop_row(task_id, _DONE, detail)

    def fail(self, task_id: str, reason: str) -> None:
        self._stop_row(task_id, _FAILED, reason)

    def _stop_row(self, task_id: str, state: str, detail: str) -> None:
        row = self._rows[task_id]
        row["elapsed"] = time.monotonic() - (row["started"] or time.monotonic())
        row["state"] = state
        row["detail"] = detail
        if self._plain:
            print(f"{state}  {row['label']}  {detail}  {row['elapsed']:.1f}s", file=sys.stderr)
        self._refresh()

    def close(self) -> None:
        if self._live is not None:
            self._live.stop()
