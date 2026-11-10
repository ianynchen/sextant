# What pydantic writes on the wire for `shape-models/pydantic.yml`'s `known_types` (plan 2, Task 9)

Backs N12's `known_types`. `pydantic_known_types.py` produced every result below.

**Version scope.** pydantic **2.14.3**, as the running process reported it (`pydantic.VERSION`),
in FastAPI 0.162.0's throwaway environment (`fastapi_rules.md`). Every verdict below holds for
that version and for no other.

## Observations

Verbatim from the output of `scripts/probes/pydantic_known_types.py`: for each type, the Python
type of the value `model_dump(mode="json")` writes, then the `type` and `format` of the field in
`model_json_schema(mode="serialization")` and `(mode="validation")`. The column header is the
version the run's own process reported (`pydantic.VERSION`), not the version the environment
was asked to install. `email-validator` 2.3.0 was put on the path for `EmailStr` (pydantic
imports it to build that schema).

| Type | 2.14.3 |
|---|---|
| `datetime.datetime` | str; string, date-time (both modes) |
| `datetime.date` | str; string, date (both modes) |
| `uuid.UUID` | str; string, uuid (both modes) |
| `decimal.Decimal` | str; string, no format (serialization); a number or a string (validation) |
| `bytes` | str; string, binary (both modes) |
| `pydantic.types.UUID4` | str; string, uuid4 (both modes) |
| `pydantic.networks.EmailStr` | str; string, email (both modes) |
| `pydantic.networks.HttpUrl` | str; string, uri (both modes) |
| `pydantic.networks.AnyUrl` | str; string, uri (both modes) |
| `pydantic.networks.IPvAnyAddress` | str; string, ipvanyaddress (both modes) |
| `pydantic.networks.PostgresDsn` | str; string, multi-host-uri (both modes) |
| `pydantic.types.AwareDatetime` | str; string, date-time (both modes) |
| `pydantic.types.FutureDatetime` | str; string, date-time (both modes) |
| `pydantic.types.DirectoryPath` | str; string, directory-path (both modes) |
| `pydantic.json_schema.SkipJsonSchema[int]` | int (kept out of the schema) |

## What the shape model declares

Each type is a `string` on the wire with the format pydantic's schema states (ruling: formats
follow the probe), the same in both modes; `Decimal` states none. `SkipJsonSchema[X]` writes the
`X` it holds, so `fastapi.yml` declares it a `wrappers` envelope (D02 §2a), not a known type.
