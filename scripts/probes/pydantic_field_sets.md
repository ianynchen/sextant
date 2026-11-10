# Which fields a pydantic model publishes, per direction (plan 2, Task 9c)

Backs `shape-models/pydantic.yml`'s `open_when`, `output_fields` and `output_open_when` (approved
2026-11-09), and the rule that a library base's own fields, read from its type header, close a
shape. `pydantic_field_sets.py` produced every result below.

**Version scope.** pydantic **2.14.3** with pydantic-settings **2.16.2** (a throwaway
environment), and pydantic **2.14.1** with pydantic-settings **2.16.1** (polar's own `.venv`,
the corpus's truth), each as the running process reported it (`pydantic.VERSION`). The two runs
print the same lines, apart from the version line. Every verdict below holds for those versions
and for no other.

## Observations

Verbatim from the table rows that `scripts/probes/pydantic_field_sets.py` generated (its
`## Observations column` lines), one column per run. Each column header is the version that
run's own process printed (`pydantic.VERSION`), not the version the environment was asked to
install: 2.14.3 from the throwaway environment, 2.14.1 from polar's own `.venv`.

| Question | 2.14.3 | 2.14.1 |
|---|---|---|
| `BaseModel` names neither `ClassVar` nor `_`-prefixed | none | none |
| base with fields, child: serialization | created, id, name | created, id, name |
| `extra='allow'`: additionalProperties | True | True |
| inherited `extra='allow'`: additionalProperties | True | True |
| dict `{'extra': 'allow'}`: additionalProperties | True | True |
| child `extra='ignore'` over `allow`: additionalProperties | None | None |
| `@computed_field`: validation | a | a |
| `@computed_field`: serialization | Tripled, a, bare, doubled | Tripled, a, bare, doubled |
| `exclude_if` computed field required (serialization) | False | False |
| generator with computed fields: serialization | Fixed, someField, someTotal | Fixed, someField, someTotal |
| `RootModel[list[str]]`: serialization | <no properties: type='array'> | <no properties: type='array'> |
| `@model_serializer`: serialization | <no properties: type='object'> | <no properties: type='object'> |
| `__get_pydantic_core_schema__` keeping `handler(source)`: serialization | a | a |
| `@field_serializer` field type (serialization) | string | string |
| keyword `extra='allow'`: additionalProperties | True | True |
| keyword `extra='allow'` beside `model_config` `forbid`: additionalProperties | True | True |
| keyword `alias_generator`: serialization | aB | aB |
| child `model_config` `ignore` over a parent's keyword: additionalProperties | None | None |
| `Field(exclude_if=...)`: serialization required | None | None |
| `TYPE_CHECKING` / `if False` annotations: fields | ['a'] | ['a'] |
| `BaseModel.model_fields` read gives | dict (a `deprecated_instance_property`) | dict (a `deprecated_instance_property`) |

`pydantic.VERSION` printed 2.14.3 and 2.14.1. Apart from that line, the two runs' whole outputs
are identical.

## Verdicts

| § | Case | Validation fields | Serialization fields | The class bodies say it all? |
|---|---|---|---|---|
| 0 | `BaseModel`'s own annotated names | every one a `ClassVar` or a name starting with `_` | | yes: it contributes none |
| 0b | `BaseSettings` | `model_config: ClassVar[...]` only; `extra='forbid'` | | yes: none |
| 1 | a plain model (`ClassVar`, `_p` dropped) | a, b | a, b | yes |
| 2 | a base with `id`, `created`; a child adding `name` | all three | all three | yes: a base contributes its fields |
| 3a, 3b | `extra='allow'`, own or inherited | `additionalProperties: true` | the same; `model_dump` writes extra keys | **no**: open |
| 3c, 3d | `extra='forbid'`, unset | a | a | yes |
| 3e, 11a, 11b | `extra='allow'` in `BaseSettings`, a plain dict, `SettingsConfigDict` | `additionalProperties: true` | the same | **no**: open |
| 12 | a child's `extra='ignore'` over a parent's `allow` | a | a | yes: the last class writing it wins |
| 4, 4b | `@computed_field` (bare, `@property`, `alias=`), own or inherited | a | a plus each computed field, `alias=` its name, all required | **no**: output-only fields |
| 9 | `@computed_field(exclude_if=...)` | a | a, the field **not required** | output-only, may be left out |
| 10 | a generator with computed fields | `someField` | `someField`, `someTotal`, `Fixed` | the generator names a computed field; `alias=` wins |
| 5 | `RootModel[list[str]]` | no properties: the schema is the root's `array` | the same | **no**: its body says `root: RootModelRootType` |
| 6, 6b | `@model_serializer`, plain or wrap | a | no properties, `additionalProperties: true` | **no** on output; input unchanged |
| 7a | `__get_pydantic_core_schema__` returning `handler(source)` (polar's form) | a | a | yes, but only by what the method returns |
| 7b | `__get_pydantic_core_schema__` returning another schema | not the fields: an `int` is read | | **no**, either direction |
| 8 | `@field_serializer("a")` returning `str` | a (integer) | a (**string**) | the field set yes; the output TYPE differs (logged, not built) |
| 13 | configuration as class keywords (`class A(BaseModel, extra='allow')`), inherited, beside `model_config` | `additionalProperties: true`; keyword `alias_generator` names fields | the same | **no**: read as configuration, merged after `model_config` (the keyword wins), a child's `model_config` over an inherited keyword |
| 14 | a plain `Field(exclude_if=...)` | `b` required | `b` **not required** | output may leave it out (needs a key form; not built) |
| 15 | names annotated under `if TYPE_CHECKING:` / `if False:` | none | none | the blocks never run: no fields |
| 16 | `BaseModel.model_fields` (`@deprecated_instance_property @classmethod`) | | | a descriptor: its `__get__` hands back the wrapped classmethod's result, a `dict`, on the class and on an instance; reading it never gives the descriptor |

pydantic decides 7 with `_generate_schema.py`: a type's `__get_pydantic_core_schema__` is called
unless it is `BaseModel`'s own (`getattr(get_schema, '__func__', None) is not
BaseModel_.__get_pydantic_core_schema__.__func__`). `BaseModel` defines it only so a subclass can
call `super()`.

## Output (the run that printed pydantic 2.14.3)

```
pydantic 2.14.3
## 0. BaseModel's own annotated class-body names
  model_config: ClassVar[ConfigDict]
  __class_vars__: ClassVar[set[str]]
  __private_attributes__: ClassVar[Dict[str, ModelPrivateAttr]]
  __signature__: ClassVar[Signature]
  __pydantic_complete__: ClassVar[bool]
  __pydantic_core_schema__: ClassVar[CoreSchema]
  __pydantic_custom_init__: ClassVar[bool]
  __pydantic_decorators__: ClassVar[_decorators.DecoratorInfos]
  __pydantic_generic_metadata__: ClassVar[_generics.PydanticGenericMetadata]
  __pydantic_parent_namespace__: ClassVar[Dict[str, Any] | None]
  __pydantic_post_init__: ClassVar[None | Literal['model_post_init']]
  __pydantic_root_model__: ClassVar[bool]
  __pydantic_serializer__: ClassVar[SchemaSerializer]
  __pydantic_validator__: ClassVar[SchemaValidator | PluggableSchemaValidator]
  __pydantic_fields__: ClassVar[Dict[str, FieldInfo]]
  __pydantic_setattr_handlers__: ClassVar[Dict[str, Callable[[BaseModel, str, Any], None]]]
  __pydantic_computed_fields__: ClassVar[Dict[str, ComputedFieldInfo]]
  __pydantic_extra_info__: ClassVar[PydanticExtraInfo | None]
  __pydantic_extra__: Dict[str, Any] | None
  __pydantic_fields_set__: set[str]
  __pydantic_private__: Dict[str, Any] | None
## 0b. BaseSettings' own annotated class-body names
  model_config: ClassVar[SettingsConfigDict]
  BaseSettings.model_config extra = 'forbid'
  BaseSettings.model_fields = []
## 1. plain model
  model_fields:          ['a', 'b']
  validation properties: ['a', 'b']  additionalProperties=None
  serialization props:   ['a', 'b']  additionalProperties=None
  model_dump keys:       ['a', 'b']
## 2. base with fields
  model_fields:          ['created', 'id', 'name']
  validation properties: ['created', 'id', 'name']  additionalProperties=None
  serialization props:   ['created', 'id', 'name']  additionalProperties=None
  model_dump keys:       ['created', 'id', 'name']
## 3a. extra='allow'
  model_fields:          ['a']
  validation properties: ['a']  additionalProperties=True
  serialization props:   ['a']  additionalProperties=True
  model_dump keys:       ['a', 'z']
## 3b. inherited extra='allow'
  model_fields:          ['a', 'b']
  validation properties: ['a', 'b']  additionalProperties=True
  serialization props:   ['a', 'b']  additionalProperties=True
  model_dump keys:       ['a', 'b', 'z']
## 3c. extra='forbid'
  model_fields:          ['a']
  validation properties: ['a']  additionalProperties=False
  serialization props:   ['a']  additionalProperties=False
  model_dump keys:       ['a']
## 3d. extra unset (ignore)
  model_fields:          ['a', 'b']
  validation properties: ['a', 'b']  additionalProperties=None
  serialization props:   ['a', 'b']  additionalProperties=None
  model_dump keys:       ['a', 'b']
## 3e. BaseSettings with extra='allow'
  model_fields:          ['a']
  validation properties: ['a']  additionalProperties=True
  serialization props:   ['a']  additionalProperties=True
  model_dump keys:       ['a']
## 4. computed_field
  model_fields:          ['a']
  validation properties: ['a']  additionalProperties=None
  serialization props:   ['Tripled', 'a', 'bare', 'doubled']  additionalProperties=None
  model_dump keys:       ['a', 'bare', 'doubled', 'tripled']
  model_computed_fields: ['bare', 'doubled', 'tripled']
  serialization required: ['a', 'doubled', 'Tripled', 'bare']
## 4b. inherited computed_field
  model_fields:          ['a', 'b']
  validation properties: ['a', 'b']  additionalProperties=None
  serialization props:   ['Tripled', 'a', 'b', 'bare', 'doubled']  additionalProperties=None
  model_dump keys:       ['a', 'b', 'bare', 'doubled', 'tripled']
## 5. RootModel[list[str]]
  model_fields:          ['root']
  validation properties: <no properties: type='array'>  additionalProperties=None
  serialization props:   <no properties: type='array'>  additionalProperties=None
  model_dump keys:       ['a']
  RootModel own annotations: {'root': 'RootModelRootType'}
## 6. model_serializer (plain)
  model_fields:          ['a']
  validation properties: ['a']  additionalProperties=None
  serialization props:   <no properties: type='object'>  additionalProperties=True
  model_dump keys:       ['extra', 'renamed']
## 6b. model_serializer (wrap)
  model_fields:          ['a']
  validation properties: ['a']  additionalProperties=None
  serialization props:   <no properties: type='object'>  additionalProperties=True
  model_dump keys:       ['a', 'added']
## 7a. __get_pydantic_core_schema__ keeping handler(source)
  model_fields:          ['a']
  validation properties: ['a']  additionalProperties=None
  serialization props:   ['a']  additionalProperties=None
  model_dump keys:       ['a']
## 7b. __get_pydantic_core_schema__ replacing it
  ValidationError: 1 validation error for ReplacesSchema
  Input should be a valid integer [type=int_type, input_value={'a': 1}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.14/v/int_type
## 8. field_serializer
  model_fields:          ['a']
  validation properties: ['a']  additionalProperties=None
  serialization props:   ['a']  additionalProperties=None
  model_dump keys:       ['a']
  a in serialization: {"title": "A", "type": "string"}
## 9. computed_field(exclude_if=...)
  model_fields:          ['a']
  validation properties: ['a']  additionalProperties=None
  serialization props:   ['a', 'doubled']  additionalProperties=None
  model_dump keys:       ['a']
  serialization required: ['a']
  model_dump(a=1): {'a': 1, 'doubled': 2}
## 10. computed_field under an alias_generator
  model_fields:          ['some_field']
  validation properties: ['someField']  additionalProperties=None
  serialization props:   ['Fixed', 'someField', 'someTotal']  additionalProperties=None
  model_dump keys:       ['other_total', 'some_field', 'some_total']
  model_dump(by_alias=True): ['Fixed', 'someField', 'someTotal']
## 11a. model_config as a dict, extra='allow'
  model_fields:          ['a']
  validation properties: ['a']  additionalProperties=True
  serialization props:   ['a']  additionalProperties=True
  model_dump keys:       ['a', 'z']
## 11b. SettingsConfigDict(extra='allow')
  model_fields:          ['a']
  validation properties: ['a']  additionalProperties=True
  serialization props:   ['a']  additionalProperties=True
  model_dump keys:       ['a']
## 12. child extra='ignore' over a parent's 'allow'
  model_fields:          ['a']
  validation properties: ['a']  additionalProperties=None
  serialization props:   ['a']  additionalProperties=None
  model_dump keys:       ['a']
## 13a. class keyword extra='allow'
  model_fields:          ['a']
  validation properties: ['a']  additionalProperties=True
  serialization props:   ['a']  additionalProperties=True
  model_dump keys:       ['a', 'z']
## 13b. inherited class keyword extra='allow'
  model_fields:          ['a', 'b']
  validation properties: ['a', 'b']  additionalProperties=True
  serialization props:   ['a', 'b']  additionalProperties=True
  model_dump keys:       ['a', 'b']
## 13c. keyword extra='allow' beside model_config extra='forbid'
  model_fields:          ['a']
  validation properties: ['a']  additionalProperties=True
  serialization props:   ['a']  additionalProperties=True
  model_dump keys:       ['a']
## 13d. class keyword alias_generator
  model_fields:          ['a_b']
  validation properties: ['aB']  additionalProperties=None
  serialization props:   ['aB']  additionalProperties=None
  model_dump keys:       ['a_b']
## 13e. child model_config extra='ignore' over a parent's keyword
  model_fields:          ['a']
  validation properties: ['a']  additionalProperties=None
  serialization props:   ['a']  additionalProperties=None
  model_dump keys:       ['a']
## 14. Field(exclude_if=...)
  model_fields:          ['a', 'b']
  validation properties: ['a', 'b']  additionalProperties=None
  serialization props:   ['a', 'b']  additionalProperties=None
  model_dump keys:       ['a', 'b']
  serialization required: None; validation required: ['b']
## 15. annotations under TYPE_CHECKING / if False
  model_fields:          ['a']
  validation properties: ['a']  additionalProperties=None
  serialization props:   ['a']  additionalProperties=None
  model_dump keys:       ['a']
## 16. BaseModel.model_fields through deprecated_instance_property
  class attribute is a descriptor: deprecated_instance_property
  defines __get__: True
  Plain.model_fields read gives: dict
  Plain().model_fields read gives: dict
## Observations column
| `pydantic.VERSION` | 2.14.3 |
| `BaseModel` names neither `ClassVar` nor `_`-prefixed | none |
| base with fields, child: serialization | created, id, name |
| `extra='allow'`: additionalProperties | True |
| inherited `extra='allow'`: additionalProperties | True |
| dict `{'extra': 'allow'}`: additionalProperties | True |
| child `extra='ignore'` over `allow`: additionalProperties | None |
| `@computed_field`: validation | a |
| `@computed_field`: serialization | Tripled, a, bare, doubled |
| `exclude_if` computed field required (serialization) | False |
| generator with computed fields: serialization | Fixed, someField, someTotal |
| `RootModel[list[str]]`: serialization | <no properties: type='array'> |
| `@model_serializer`: serialization | <no properties: type='object'> |
| `__get_pydantic_core_schema__` keeping `handler(source)`: serialization | a |
| `@field_serializer` field type (serialization) | string |
| keyword `extra='allow'`: additionalProperties | True |
| keyword `extra='allow'` beside `model_config` `forbid`: additionalProperties | True |
| keyword `alias_generator`: serialization | aB |
| child `model_config` `ignore` over a parent's keyword: additionalProperties | None |
| `Field(exclude_if=...)`: serialization required | None |
| `TYPE_CHECKING` / `if False` annotations: fields | ['a'] |
| `BaseModel.model_fields` read gives | dict (a `deprecated_instance_property`) |
```
