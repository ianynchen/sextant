"""What pydantic writes on the wire for the types `shape-models/pydantic.yml` maps (plan 2,
Task 9, N12 `known_types`).

Run it inside a throwaway environment that has pydantic installed, never inside the
repository's `.venv`:

    uv venv /tmp/probe && uv pip install -p /tmp/probe/bin/python fastapi==0.162.0
    /tmp/probe/bin/python scripts/probes/pydantic_known_types.py

For each type it builds a one-field model and prints three answers pydantic gives: the Python
type of the value `model_dump(mode="json")` writes, and the `type` and `format` of the field in
`model_json_schema(mode="serialization")`, the schema of what pydantic SENDS. What the results
mean is in `pydantic_known_types.md`. The probe imports pydantic and builds models on purpose.
Sextant itself never does that (spec 7).
"""

from __future__ import annotations

import datetime
import json
import uuid
from decimal import Decimal

import pydantic
from pydantic import UUID4, BaseModel

# Each mapped type, by the dotted name the shape model writes, with one value of it.
_CASES: dict[str, tuple[object, object]] = {
    "datetime.datetime": (
        datetime.datetime,
        datetime.datetime(2026, 11, 9, 12, 0, 0, tzinfo=datetime.UTC),
    ),
    "datetime.date": (datetime.date, datetime.date(2026, 11, 9)),
    "uuid.UUID": (uuid.UUID, uuid.UUID("12345678-1234-5678-1234-567812345678")),
    "decimal.Decimal": (Decimal, Decimal("1.50")),
    "bytes": (bytes, b"abc"),
    "pydantic.types.UUID4": (UUID4, uuid.UUID("9b2b1c4e-8d1a-4f3e-9c2b-6a1d2e3f4a5b")),
}


def main() -> None:
    results: dict[str, object] = {"pydantic": pydantic.VERSION}
    for name, (annotation, value) in _CASES.items():
        model = pydantic.create_model("Probe", field=(annotation, ...))
        assert issubclass(model, BaseModel)
        dumped = model(field=value).model_dump(mode="json")["field"]
        schema = model.model_json_schema(mode="serialization")["properties"]["field"]
        results[name] = {
            "json value type": type(dumped).__name__,
            "schema type": schema.get("type"),
            "schema format": schema.get("format"),
        }
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
