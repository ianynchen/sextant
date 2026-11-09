# Pydantic's naming rules, and mealie's field names (plan 2, Task 0)

Backs N12 (`shape-models/pydantic.yml`) and N13. `pydantic_naming.py` produced every result
below, with pydantic 2.14.3 (mealie locks 2.14.2) and pyhumps 3.8.0 (the version mealie locks).
Run it with mealie's `mealie/` folder as the one argument, in a throwaway environment.

**Version scope.** pydantic **2.14.3** (mealie locks 2.14.2) and pyhumps **3.8.0** (the version
mealie locks), each as the running process reported it: `pydantic.VERSION` and
`importlib.metadata.version("pyhumps")`. Every verdict below holds for those two and for no other
version.

## Observations

Verbatim from the table that `scripts/probes/pydantic_naming.py` generated. Each column header
is the version that run's own process printed (`pydantic.VERSION`, and pyhumps through
`importlib.metadata`), not the version the environment was asked to install. A cell `n/a` means
the question is not about that library. The sections below give the other results.

| Question | 2.14.3 | 3.8.0 |
|---|---|---|
| `humps.camelize` differs from `to_camel` (465 names) | n/a | 0 |
| `to_pascal` differs from `to_camel` with its first letter raised | 2 | n/a |
| `Both(Left, Right)` takes the generator of | to_pascal | n/a |
| `alias_priority=1` with `alias` and `serialization_alias` gives output name | myField | n/a |
| `serialization_alias` beats the generator: output name | Ser | n/a |
| `Optional[int]` with no default is required | True | n/a |

`pydantic.VERSION` printed 2.14.3; `importlib.metadata` printed pyhumps 3.8.0.

## 1. `to_camel`, `to_pascal` and `humps.main.camelize` on mealie's field names

mealie's base model is `MealieModel` (`schema/_mealie/mealie_model.py:53`):
`ConfigDict(alias_generator=camelize, populate_by_name=True)`, with `camelize` imported from
`humps.main`. Two other mealie models use `pydantic.alias_generators.to_camel`
(`schema/recipe/recipe_nutrition.py:23`).

The probe reads every class that reaches `BaseModel` by name (ast only; 357 classes) and takes
every annotated name in the class body that does not start with `_`: **465 distinct field names**
(5 underscore names skipped).

| Question | Answer |
|---|---|
| `to_camel(name) != humps.camelize(name)` for any of the 465 names | **none**. They agree on all 465. |
| names that either one changes | 311 (the same 311) |
| `to_pascal(name) != to_camel(name)` with its first letter raised | **2**: `passwordConfirm` and `versionLatest` (written camel-case in the model). `to_pascal` gives `Passwordconfirm` and `Versionlatest`; `to_camel` leaves them. |

So N12's rule holds: `humps.main.camelize` maps to the `camel` strategy, because it agrees with
`to_camel` on every mealie field name. The agreement is measured on mealie's names, not proved
for all strings. `humps.camelize` and `to_camel` differ on some inputs (`HTTP_code` gives `httpCode` and
`HTTPCode`; `user_ID` gives `userId` and `userID`; `my__field` gives `my__Field` and `myField`;
`x_1y` gives `x1Y` and `x1y`); no mealie field name has them. `to_pascal` lower-cases the rest
of a word that is already camel-case, so `camel` and `pascal` must stay two separate words.

## 2. Which alias a field gets

Source: `pydantic/_internal/_fields.py:_apply_alias_generator_to_field_info` (lines 170-225 in
2.14.3).

```python
# Apply an alias_generator if
# 1. An alias is not specified
# 2. An alias is specified, but the priority is <= 1
if (
    field_info.alias_priority is None
    or field_info.alias_priority <= 1
    or field_info.alias is None
    or field_info.validation_alias is None
    or field_info.serialization_alias is None
):
    ...
    # if priority is not set, we set to 1 ...
    if field_info.alias_priority is None or field_info.alias_priority <= 1:
        field_info.alias_priority = 1
    # if the priority is 1, then we set the aliases to the generated alias
    if field_info.alias_priority == 1:
        field_info.serialization_alias = get_first_not_none(serialization_alias, alias)
        field_info.validation_alias = get_first_not_none(validation_alias, alias)
        field_info.alias = alias
    # if any of the aliases are not set, then we set them to the corresponding generated alias
    if field_info.alias is None:
        field_info.alias = alias
    if field_info.serialization_alias is None:
        ...
    if field_info.validation_alias is None:
        ...
```

`Field(alias=..., serialization_alias=..., validation_alias=...)` sets `alias_priority` to 2 when
any of the three is written, unless `alias_priority` is passed.

Probe results (the field is `my_field: int = 0`; `to_camel` is the generator unless stated).
"Output name" is the key in `model_dump(by_alias=True)`. "Input names" are what
`model_validate` accepts.

| Written | `alias` | `validation_alias` | `serialization_alias` (output name) | Input names |
|---|---|---|---|---|
| nothing | none | none | none (output `my_field`) | `my_field` |
| generator only | `myField` | `myField` | `myField` | `myField` |
| `alias="Explicit"` and the generator | `Explicit` | `Explicit` | `Explicit` | `Explicit` |
| `alias="Explicit", alias_priority=1` and the generator | `myField` | `myField` | `myField` | `myField` (the generator replaces the alias) |
| `serialization_alias="Ser"` and the generator | `myField` | `myField` | `Ser` | `myField` |
| `alias="Al", serialization_alias="Ser"` and the generator | `Al` | `Al` | `Ser` | `Al` |
| `alias="Al", serialization_alias="Ser", alias_priority=1` and the generator | `myField` | `myField` | `myField` | `myField` (both written aliases are replaced) |
| `validation_alias=AliasChoices("a", "b")`, no generator | none | the choices | none (output `my_field`) | `a`, `b` |
| `alias="Al", validation_alias="Val"` | `Al` | `Val` | `Al` | `Val` |
| `AliasGenerator(validation_alias=to_pascal, serialization_alias=to_camel)` | none | `MyField` | `myField` | `MyField` |
| generator `up(name) = name.upper()` (a user function) | `MY_FIELD` | `MY_FIELD` | `MY_FIELD` | `MY_FIELD` |

The output name is: `serialization_alias` if written; else `alias` if written (priority 2);
else the generator's name; else the field name. A written `validation_alias` alone never changes
the output name. This is N12's order, and it holds while `alias_priority` is unset or 2.
**With `alias_priority=1` the generator wins over `alias` and `serialization_alias`**
(`UpdatedAtField` in mealie sets `alias_priority=2`, the safe value; no corpus field uses 1).

### Input by field name (`populate_by_name`)

| Config | Input `my_field=5` gives |
|---|---|
| generator, no `populate_by_name` | `0` (the name is ignored as an extra key; with `extra="forbid"` it is rejected) |
| generator and `populate_by_name=True` | `5` |

So a field that has a generated or written alias accepts its field name too only under
`populate_by_name` (pydantic 2.11+ also has `validate_by_name`; no corpus code uses it). A
`validation_alias` that is not the output name is accepted instead of the output name: the
output name `my_field` is **not** accepted as input in the `AliasChoices("a", "b")` row above.
That is N13's case: the input names and the output name differ.

## 3. Config across bases

Source: `pydantic/_internal/_config.py:ConfigWrapper.for_model` (R lines 169-173):
```python
config_new = ConfigDict()
for base in bases:
    config = getattr(base, "model_config", None)
    if config:
        config_new.update(config.copy())
```
then the class's own `model_config` (and class keyword arguments) on top.

Probe:

| Class | Generator it gets |
|---|---|
| `Child(Parent)`, no `model_config` | the parent's (`to_camel`), and `populate_by_name=True` |
| `Child(Parent)` with `ConfigDict(alias_generator=to_pascal)` | `to_pascal` (the child's key replaces the parent's); `populate_by_name` stays from the parent |
| `Child(Parent)` with `ConfigDict(alias_generator=None)` | none (an explicit `None` replaces the parent's) |
| `Child(Parent)` with `ConfigDict(str_strip_whitespace=True)` | the parent's generator stays; the merged config has all three keys |
| `Both(Left, Right)`, `Left` has `to_camel`, `Right` has `to_pascal` | **`to_pascal`**: the **last** base listed wins, not the first. The method resolution order is `Both, Left, Right, BaseModel`. |

The merge follows the order the bases are **written**, the last one winning, and the class's own
`model_config` last of all. It is not the method-resolution (C3) order, which would pick `Left`.
For a single-inheritance chain the two orders agree. In the corpora the field names of a
model's parents come from the C3 order (for the fields themselves) while the config comes from
the written order.

## 4. Required fields, private attributes, class variables

Probe (`Misc`, generator `to_camel`):

| Written | Required in validation | Notes |
|---|---|---|
| `needs: int` | yes | |
| `opt_no_default: Optional[int]` | **yes** | `Optional` with no default is required |
| `opt_none: Optional[int] = None` | no | |
| `ell: int = Field(...)` | yes | |
| `empty_field: int = Field()` | yes | |
| `factory: list[int] = Field(default_factory=list)` | no | |
| `_private: int = 0` | not a field | listed in `__private_attributes__` |
| `cv: ClassVar[int] = 1` | not a field | listed in `__class_vars__` |

This matches N12's `required: no_default` (a field is required when it writes no default) and
`private_prefix: "_"`.

## 5. `Field` in `Annotated` metadata (task 9 review M1)

Part 3 of `pydantic_naming.py` (`AnnotatedFields`), pydantic 2.14.3 as the process reported it.
Source: `pydantic/fields.py:FieldInfo.from_annotated_attribute` merges every `FieldInfo` in the
metadata in written order, then the assigned value's last (`merge_field_infos`), each
overriding only the attributes it sets; `Field(alias=...)` sets `alias`,
`serialization_alias` and `validation_alias` alike. A plain assigned value is the default.

| Written | alias / serialization / validation | required |
|---|---|---|
| `Annotated[str, Field(alias="PlainAlias")]` | PlainAlias / PlainAlias / PlainAlias | True |
| `Annotated[int, Field(default=3)]` | none | False |
| `Annotated[list[int], Field(default_factory=list)]` | none | False |
| `Annotated[int, Field(alias="A1")] = Field(alias="A2")` | A2 / A2 / A2 | True |
| `Annotated[int, Field(alias="B1")] = Field(default=3)` | B1 / B1 / B1 | False |
| `Annotated[int, Field(alias="C1")] = 4` | C1 / C1 / C1 | False |
| `Annotated[int, Field(alias="D1"), Field(alias="D2")]` | D2 / D2 / D2 | True |
| `Annotated[int, Field(default=1)] = Field(alias="E")` | E / E / E | False |
| `Annotated[int, Field(serialization_alias="G1")] = Field(alias="G2")` | G2 / G2 / G2 | True |
| `Annotated[int, Field(validation_alias="V")] = 0` | none / none / V | False |
