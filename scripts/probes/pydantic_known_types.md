# What pydantic writes on the wire for `shape-models/pydantic.yml`'s `known_types` (plan 2, Task 9)

Backs N12's `known_types`. `pydantic_known_types.py` produced every result below.

**Version scope.** pydantic **2.14.3**, as the running process reported it (`pydantic.VERSION`),
in FastAPI 0.162.0's throwaway environment (`fastapi_rules.md`). Every verdict below holds for
that version and for no other.

## Observations

Verbatim from the output of `scripts/probes/pydantic_known_types.py`: for each type, the Python
type of the value `model_dump(mode="json")` writes, then the `type` and `format` of the field in
`model_json_schema(mode="serialization")`. The column header is the version the run's own process
reported (`pydantic.VERSION`), not the version the environment was asked to install.

| Type | 2.14.3 |
|---|---|
| `datetime.datetime` | str; string, date-time |
| `datetime.date` | str; string, date |
| `uuid.UUID` | str; string, uuid |
| `decimal.Decimal` | str; string, no format |
| `bytes` | str; string, binary |
| `pydantic.types.UUID4` | str; string, uuid4 |

## What the shape model declares

Each type is a `string` on the wire. The `format` is the schema's where D00 §5b's vocabulary has
the word: `date-time`, `date` and `uuid`. `binary` (bytes) and `uuid4` are pydantic's schema
words, not this vocabulary's, so `bytes` is a string with no format and `UUID4` a `uuid`, as the
plan's N12 states them. A JSON Schema reader distinguishes them; DR-5's comparison does not.
