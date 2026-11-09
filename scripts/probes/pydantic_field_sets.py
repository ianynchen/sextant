"""Which fields a pydantic model publishes per direction, and where that differs from what the
class bodies of the model and its bases declare (plan 2, Task 9c).

Run it inside a throwaway environment that has `pydantic` and `pydantic-settings`, never inside
the repository's `.venv`:

    uv venv /tmp/probe && uv pip install -p /tmp/probe/bin/python pydantic==2.14.3 pydantic-settings
    /tmp/probe/bin/python -I scripts/probes/pydantic_field_sets.py

It was also run with polar's own interpreter (pydantic 2.14.1, pydantic-settings 2.16.1), the
corpus's truth: every result is the same (`pydantic_field_sets.md`).

For each case it prints the property names of `model_json_schema` in validation and in
serialization mode, `additionalProperties`, and the keys `model_dump(mode="json")` writes for one
instance, beside the annotated names the class bodies declare. Sextant itself never imports a
model (spec 7); this probe does so on purpose.
"""

from __future__ import annotations

import ast
import inspect
import json
from typing import Any, ClassVar

import pydantic
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetCoreSchemaHandler,
    RootModel,
    computed_field,
    field_serializer,
    model_serializer,
)
from pydantic_core import CoreSchema, core_schema
from pydantic_settings import BaseSettings, SettingsConfigDict


def schema_keys(model: type[BaseModel], mode: str) -> tuple[list[str] | str, object]:
    schema = model.model_json_schema(mode=mode)
    if "properties" not in schema:
        return f"<no properties: type={schema.get('type')!r}>", schema.get("additionalProperties")
    return sorted(schema["properties"]), schema.get("additionalProperties")


def report(name: str, model: type[BaseModel], instance: Any) -> None:
    validation, extra_v = schema_keys(model, "validation")
    serialization, extra_s = schema_keys(model, "serialization")
    dumped = instance.model_dump(mode="json")
    print(f"## {name}")
    print(f"  model_fields:          {sorted(model.model_fields)}")
    print(f"  validation properties: {validation}  additionalProperties={extra_v!r}")
    print(f"  serialization props:   {serialization}  additionalProperties={extra_s!r}")
    print(f"  model_dump keys:       {sorted(dumped) if isinstance(dumped, dict) else dumped!r}")


def own_annotations(cls: type) -> dict[str, str]:
    """The annotated assignments a class body writes, as source text (what Sextant reads)."""
    tree = ast.parse(inspect.getsource(cls))
    body = tree.body[0].body  # type: ignore[attr-defined]
    return {
        node.target.id: ast.unparse(node.annotation)
        for node in body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }


print(f"pydantic {pydantic.VERSION}")

# 0. The library base itself: every annotated name BaseModel's class body declares.
print("## 0. BaseModel's own annotated class-body names")
for attribute, annotation in own_annotations(BaseModel).items():
    print(f"  {attribute}: {annotation}")

print("## 0b. BaseSettings' own annotated class-body names")
for attribute, annotation in own_annotations(BaseSettings).items():
    print(f"  {attribute}: {annotation}")
print(f"  BaseSettings.model_config extra = {BaseSettings.model_config.get('extra')!r}")
print(f"  BaseSettings.model_fields = {sorted(BaseSettings.model_fields)}")


# 1. A plain model.
class Plain(BaseModel):
    a: int
    b: str = "x"
    c: ClassVar[int] = 3
    _p: int = 0


report("1. plain model", Plain, Plain(a=1))


# 2. A library-style base that declares fields, and a subclass.
class LibraryBase(BaseModel):
    id: int
    created: str = "now"


class Child(LibraryBase):
    name: str


report("2. base with fields", Child, Child(id=1, name="n"))


# 3. extra='allow', own and inherited, and extra='forbid'/'ignore'.
class Allows(BaseModel):
    model_config = ConfigDict(extra="allow")
    a: int


class InheritsAllow(Allows):
    b: int


class Forbids(BaseModel):
    model_config = ConfigDict(extra="forbid")
    a: int


report("3a. extra='allow'", Allows, Allows(a=1, z=2))
report("3b. inherited extra='allow'", InheritsAllow, InheritsAllow(a=1, b=2, z=3))
report("3c. extra='forbid'", Forbids, Forbids(a=1))
report("3d. extra unset (ignore)", Plain, Plain(a=1, z=2))  # type: ignore[call-arg]


class SettingsAllow(BaseSettings):
    model_config = {"extra": "allow"}
    a: int = 1


report("3e. BaseSettings with extra='allow'", SettingsAllow, SettingsAllow())


# 4. computed_field.
class Computed(BaseModel):
    a: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def doubled(self) -> int:
        return self.a * 2

    @computed_field(alias="Tripled")  # type: ignore[prop-decorator]
    @property
    def tripled(self) -> int:
        return self.a * 3

    @computed_field  # type: ignore[prop-decorator]
    def bare(self) -> int:  # pydantic wraps a bare function in a property
        return self.a


report("4. computed_field", Computed, Computed(a=1))
print(f"  model_computed_fields: {sorted(Computed.model_computed_fields)}")
print(
    f"  serialization required: {Computed.model_json_schema(mode='serialization').get('required')}"
)


class ComputedChild(Computed):
    b: int


report("4b. inherited computed_field", ComputedChild, ComputedChild(a=1, b=2))


# 5. RootModel.
class Tags(RootModel[list[str]]):
    pass


report("5. RootModel[list[str]]", Tags, Tags(["a"]))
print(f"  RootModel own annotations: {own_annotations(RootModel)}")


# 6. model_serializer.
class Serialized(BaseModel):
    a: int

    @model_serializer
    def dump(self) -> dict[str, Any]:
        return {"renamed": self.a, "extra": 1}


report("6. model_serializer (plain)", Serialized, Serialized(a=1))


class WrapSerialized(BaseModel):
    a: int

    @model_serializer(mode="wrap")
    def dump(self, handler: Any) -> dict[str, Any]:
        out = handler(self)
        out["added"] = True
        return out


report("6b. model_serializer (wrap)", WrapSerialized, WrapSerialized(a=1))


# 7. __get_pydantic_core_schema__, one that keeps the schema (polar's ListResource) and one
# that replaces it.
class KeepsSchema(BaseModel):
    a: int

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: type[BaseModel], handler: GetCoreSchemaHandler, /
    ) -> CoreSchema:
        result = handler(source)
        result["ref"] = cls.__name__  # type: ignore[typeddict-unknown-key]
        return result


report("7a. __get_pydantic_core_schema__ keeping handler(source)", KeepsSchema, KeepsSchema(a=1))


class ReplacesSchema(BaseModel):
    a: int

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: type[BaseModel], handler: GetCoreSchemaHandler, /
    ) -> CoreSchema:
        return core_schema.no_info_after_validator_function(
            lambda value: cls.model_construct(a=value), core_schema.int_schema()
        )


try:
    report("7b. __get_pydantic_core_schema__ replacing it", ReplacesSchema, ReplacesSchema(a=1))
except Exception as error:  # noqa: BLE001
    print(f"## 7b. __get_pydantic_core_schema__ replacing it\n  {type(error).__name__}: {error}")


# 8. field_serializer: the field set is unchanged (the TYPE may change).
class FieldSerialized(BaseModel):
    a: int

    @field_serializer("a")
    def as_text(self, value: int) -> str:
        return str(value)


report("8. field_serializer", FieldSerialized, FieldSerialized(a=1))
print(
    "  a in serialization: "
    + json.dumps(FieldSerialized.model_json_schema(mode="serialization")["properties"]["a"])
)


# 9. computed_field(exclude_if=...): polar writes it on five; the field may be left out.
class ComputedExcludeIf(BaseModel):
    a: int

    @computed_field(exclude_if=lambda value: value > 5)  # type: ignore[prop-decorator]
    @property
    def doubled(self) -> int:
        return self.a * 2


report("9. computed_field(exclude_if=...)", ComputedExcludeIf, ComputedExcludeIf(a=3))
print(
    "  serialization required: "
    f"{ComputedExcludeIf.model_json_schema(mode='serialization').get('required')}"
)
print(f"  model_dump(a=1): {ComputedExcludeIf(a=1).model_dump()}")


# 10. A generator names computed fields too; `alias=` on the decorator wins over it.
class ComputedGenerated(BaseModel):
    model_config = ConfigDict(alias_generator=pydantic.alias_generators.to_camel)
    some_field: int = 1

    @computed_field  # type: ignore[prop-decorator]
    @property
    def some_total(self) -> int:
        return 1

    @computed_field(alias="Fixed")  # type: ignore[prop-decorator]
    @property
    def other_total(self) -> int:
        return 1


report("10. computed_field under an alias_generator", ComputedGenerated, ComputedGenerated())
print(f"  model_dump(by_alias=True): {sorted(ComputedGenerated().model_dump(by_alias=True))}")


# 11. A configuration written as a plain dict and as `SettingsConfigDict(...)`.
class DictAllow(BaseModel):
    model_config = {"extra": "allow"}
    a: int = 1


report("11a. model_config as a dict, extra='allow'", DictAllow, DictAllow(z=1))


class SettingsDictAllow(BaseSettings):
    model_config = SettingsConfigDict(extra="allow")
    a: int = 1


report("11b. SettingsConfigDict(extra='allow')", SettingsDictAllow, SettingsDictAllow())


# 12. A child setting extra='ignore' over a parent's 'allow': the child's wins.
class ChildIgnores(Allows):
    model_config = ConfigDict(extra="ignore")


report("12. child extra='ignore' over a parent's 'allow'", ChildIgnores, ChildIgnores(a=1, z=2))


# 13. Configuration written as class keywords (`ConfigWrapper.for_model`): alone, inherited,
# beside `model_config` (which one wins), and a generator given that way.
class KeywordAllow(BaseModel, extra="allow"):
    a: int = 1


class KeywordHeir(KeywordAllow):
    b: int = 1


class KeywordOverConfig(BaseModel, extra="allow"):
    model_config = ConfigDict(extra="forbid")
    a: int = 1


class KeywordGenerator(BaseModel, alias_generator=pydantic.alias_generators.to_camel):
    a_b: int = 1


class KeywordUnderChildConfig(KeywordAllow):
    model_config = ConfigDict(extra="ignore")


report("13a. class keyword extra='allow'", KeywordAllow, KeywordAllow(z=1))
report("13b. inherited class keyword extra='allow'", KeywordHeir, KeywordHeir())
report(
    "13c. keyword extra='allow' beside model_config extra='forbid'",
    KeywordOverConfig,
    KeywordOverConfig(),
)
report("13d. class keyword alias_generator", KeywordGenerator, KeywordGenerator())
report(
    "13e. child model_config extra='ignore' over a parent's keyword",
    KeywordUnderChildConfig,
    KeywordUnderChildConfig(),
)


# 14. A plain field's `Field(exclude_if=...)`: it may be left out of output.
class FieldExcludeIf(BaseModel):
    a: int = 1
    b: int = Field(exclude_if=lambda value: value == 0)


report("14. Field(exclude_if=...)", FieldExcludeIf, FieldExcludeIf(b=1))
print(
    "  serialization required: "
    f"{FieldExcludeIf.model_json_schema(mode='serialization').get('required')}; "
    f"validation required: {FieldExcludeIf.model_json_schema(mode='validation').get('required')}"
)


# 15. A name annotated only under `if TYPE_CHECKING:` or `if False:` is no field.
from typing import TYPE_CHECKING


class CheckedOnly(BaseModel):
    a: int = 1
    if TYPE_CHECKING:
        hinted: int
    if False:
        never: int


report("15. annotations under TYPE_CHECKING / if False", CheckedOnly, CheckedOnly())


# The observation table's column: one answer per question, from this run's own models.
def _serialized(model: type[BaseModel]) -> str:
    keys, _ = schema_keys(model, "serialization")
    return keys if isinstance(keys, str) else ", ".join(keys)


def _validated(model: type[BaseModel]) -> str:
    keys, _ = schema_keys(model, "validation")
    return keys if isinstance(keys, str) else ", ".join(keys)


print("## Observations column")
print(f"| `pydantic.VERSION` | {pydantic.VERSION} |")
public = [
    name
    for name, annotation in own_annotations(BaseModel).items()
    if not name.startswith("_") and "ClassVar" not in annotation
]
print(f"| `BaseModel` names neither `ClassVar` nor `_`-prefixed | {public or 'none'} |")
print(f"| base with fields, child: serialization | {_serialized(Child)} |")
print(
    f"| `extra='allow'`: additionalProperties | {Allows.model_json_schema()['additionalProperties']} |"
)
print(
    f"| inherited `extra='allow'`: additionalProperties | {InheritsAllow.model_json_schema()['additionalProperties']} |"
)
print(
    f"| dict `{{'extra': 'allow'}}`: additionalProperties | {DictAllow.model_json_schema()['additionalProperties']} |"
)
print(
    f"| child `extra='ignore'` over `allow`: additionalProperties | {ChildIgnores.model_json_schema().get('additionalProperties')} |"
)
print(f"| `@computed_field`: validation | {_validated(Computed)} |")
print(f"| `@computed_field`: serialization | {_serialized(Computed)} |")
print(
    f"| `exclude_if` computed field required (serialization) | {'doubled' in (ComputedExcludeIf.model_json_schema(mode='serialization').get('required') or [])} |"
)
print(f"| generator with computed fields: serialization | {_serialized(ComputedGenerated)} |")
print(f"| `RootModel[list[str]]`: serialization | {_serialized(Tags)} |")
print(f"| `@model_serializer`: serialization | {_serialized(Serialized)} |")
print(
    f"| `__get_pydantic_core_schema__` keeping `handler(source)`: serialization | {_serialized(KeepsSchema)} |"
)
print(
    f"| `@field_serializer` field type (serialization) | {FieldSerialized.model_json_schema(mode='serialization')['properties']['a']['type']} |"
)
print(
    "| keyword `extra='allow'`: additionalProperties | "
    f"{KeywordAllow.model_json_schema().get('additionalProperties')} |"
)
print(
    "| keyword `extra='allow'` beside `model_config` `forbid`: additionalProperties | "
    f"{KeywordOverConfig.model_json_schema().get('additionalProperties')} |"
)
print(f"| keyword `alias_generator`: serialization | {_serialized(KeywordGenerator)} |")
print(
    "| child `model_config` `ignore` over a parent's keyword: additionalProperties | "
    f"{KeywordUnderChildConfig.model_json_schema().get('additionalProperties')} |"
)
print(
    "| `Field(exclude_if=...)`: serialization required | "
    f"{FieldExcludeIf.model_json_schema(mode='serialization').get('required')} |"
)
print(f"| `TYPE_CHECKING` / `if False` annotations: fields | {sorted(CheckedOnly.model_fields)} |")
