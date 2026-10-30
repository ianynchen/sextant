"""`YamlCatalogSource` and the bean models (D02 §1c): a catalog names one with
`bean_model: <id>` and the loader hands the model's mapping through as
`Catalog.bean_model`, exactly as a `shape_model` is resolved (D02 §1b) — and
refuses an id no file in `bean-models/` carries, naming the catalog file. The
shape-model half of the same mechanism is pinned in
`tests/application/test_endpoints.py`.
"""

from pathlib import Path

import pytest

from sextant.application.ports.catalogs import CatalogError
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir

_HEADER = "id: invented\nstyle: annotation_driven\nprotocol: http\ndirection: inbound\n"
_TINY = (
    "id: tiny\ndeclaring_annotation: com.acme.di.Provides\nname_attrs: [named]\n"
    "qualifier_annotation: com.acme.di.Named\nchannel_types: [com.acme.di.Pipe]\n"
)


def _write_model(directory: Path) -> None:
    (directory / "bean-models").mkdir()
    (directory / "bean-models" / "tiny.yml").write_text(_TINY, encoding="utf-8")


def test_a_catalog_takes_the_bean_model_it_names(tmp_path: Path):
    """The mapping reaches `Catalog.bean_model` whole: the fold that reads it
    (`resolve/beans.py`) is the one place the keys are interpreted, so the
    loader carries them as data rather than learning their meaning."""
    _write_model(tmp_path)
    (tmp_path / "invented-di.yml").write_text(
        _HEADER + "bean_model: tiny\nmatches: {}\n", encoding="utf-8"
    )

    [catalog] = YamlCatalogSource(tmp_path).load()

    assert catalog.bean_model == {
        "id": "tiny",
        "declaring_annotation": "com.acme.di.Provides",
        "name_attrs": ["named"],
        "qualifier_annotation": "com.acme.di.Named",
        "channel_types": ["com.acme.di.Pipe"],
    }


def test_a_catalog_naming_a_bean_model_that_does_not_ship_is_refused_by_file(tmp_path: Path):
    """A typo would silently leave the catalog with no DI vocabulary at all —
    every `bean_via` capture unresolved, and nothing to say why. Refused at the
    edge, naming the file and the key, as an unknown `shape_model` is."""
    _write_model(tmp_path)
    (tmp_path / "invented-typo.yml").write_text(
        _HEADER + "bean_model: sprng\nmatches: {}\n", encoding="utf-8"
    )

    with pytest.raises(CatalogError) as raised:
        YamlCatalogSource(tmp_path).load()

    assert "bean_model" in str(raised.value)
    assert "invented-typo.yml" in str(raised.value)
    assert "tiny" in str(raised.value)


def test_a_catalog_naming_no_bean_model_carries_an_empty_one(tmp_path: Path):
    """Every catalog shipped before this key, and a repository's own set with no
    `bean-models/` directory at all (D02 §6): absence is an empty mapping, not
    an error, and no directory is needed to load."""
    (tmp_path / "invented-bare.yml").write_text(_HEADER + "matches: {}\n", encoding="utf-8")

    [catalog] = YamlCatalogSource(tmp_path).load()

    assert catalog.bean_model == {}


# --- step models (spec 2026-09-21 §5, §6) -----------------------------------------------
#
# The flow definition's members are the core library's, shared by every broker catalog
# that walks a flow; a catalog names the table with `step_model: <id>` and the loader
# merges the model's `steps` and `undeclared_steps` into `matches` — the union with the
# catalog's own steps, because a broker catalog also declares the steps on its own specs.

_STEPS = (
    "id: flows\n"
    "steps:\n"
    "  - { method: transform, owner: com.acme.Flow, captures: {} }\n"
    "  - { method: handle, owner: com.acme.Flow, descriptor: '(Lcom/acme/H;)V', captures: { handler: arg0 } }\n"
    "undeclared_steps: { owner: com.acme.Flow, poisons: [handler] }\n"
)


def _write_step_model(directory: Path) -> None:
    (directory / "step-models").mkdir()
    (directory / "step-models" / "flows.yml").write_text(_STEPS, encoding="utf-8")


def test_a_catalog_takes_the_step_models_steps_beside_its_own(tmp_path: Path):
    """The union, in one `matches.steps` list — the model's after the catalog's — and the
    model's `undeclared_steps` block, so the engine reads one table and learns nothing
    about where each entry came from."""
    _write_step_model(tmp_path)
    (tmp_path / "invented-flows.yml").write_text(
        _HEADER + "step_model: flows\nmatches:\n  steps:\n"
        "    - { method: topic, owner: com.acme.Sink, captures: { channel: arg0 } }\n",
        encoding="utf-8",
    )

    [catalog] = YamlCatalogSource(tmp_path).load()

    assert catalog.matches == {
        "steps": [
            {"method": "topic", "owner": "com.acme.Sink", "captures": {"channel": "arg0"}},
            {"method": "transform", "owner": "com.acme.Flow", "captures": {}},
            {
                "method": "handle",
                "owner": "com.acme.Flow",
                "descriptor": "(Lcom/acme/H;)V",
                "captures": {"handler": "arg0"},
            },
        ],
        "undeclared_steps": {"owner": "com.acme.Flow", "poisons": ["handler"]},
    }


def test_a_catalog_naming_a_step_model_that_does_not_ship_is_refused_by_file(tmp_path: Path):
    _write_step_model(tmp_path)
    (tmp_path / "invented-typo.yml").write_text(
        _HEADER + "step_model: flow\nmatches: {}\n", encoding="utf-8"
    )

    with pytest.raises(CatalogError) as raised:
        YamlCatalogSource(tmp_path).load()

    assert "step_model" in str(raised.value)
    assert "invented-typo.yml" in str(raised.value)
    assert "flows" in str(raised.value)


def test_a_step_the_catalog_and_its_model_both_declare_is_refused(tmp_path: Path):
    """One `(owner, method, descriptor)` from both sides is two entries for one overload
    — the silent last-wins the engine's own step check refuses, caught here by file
    before the union hides which side wrote it."""
    _write_step_model(tmp_path)
    (tmp_path / "invented-twice.yml").write_text(
        _HEADER + "step_model: flows\nmatches:\n  steps:\n"
        "    - { method: transform, owner: com.acme.Flow, captures: {} }\n",
        encoding="utf-8",
    )

    with pytest.raises(CatalogError) as raised:
        YamlCatalogSource(tmp_path).load()

    assert "invented-twice.yml" in str(raised.value)
    assert "transform" in str(raised.value)


def test_a_catalog_may_not_declare_undeclared_steps_beside_a_model_that_does(tmp_path: Path):
    """`undeclared_steps` is one block, not a list: a catalog takes the model's or writes
    its own, never both — the `shape_model` rule for the same reason."""
    _write_step_model(tmp_path)
    (tmp_path / "invented-both.yml").write_text(
        _HEADER + "step_model: flows\nmatches:\n"
        "  undeclared_steps: { owner: com.acme.Other, poisons: [handler] }\n",
        encoding="utf-8",
    )

    with pytest.raises(CatalogError) as raised:
        YamlCatalogSource(tmp_path).load()

    assert "undeclared_steps" in str(raised.value)
    assert "invented-both.yml" in str(raised.value)


def test_a_catalog_naming_no_step_model_keeps_its_matches_as_written(tmp_path: Path):
    (tmp_path / "invented-bare.yml").write_text(
        _HEADER + "matches: { steps: [] }\n", encoding="utf-8"
    )

    [catalog] = YamlCatalogSource(tmp_path).load()

    assert catalog.matches == {"steps": []}


# --- the value model (spec 2026-09-22 §2a, §5a, §7b; D02 §1f) ---------------------------
#
# The identity of a PRODUCING call — which of its arguments carries the value its result
# stands for — declared once per producer in `value-models/`, and HOISTED out of every
# `channel_via` / `url_via` / `call_wrappers` / `record_wrappers` entry the catalogs already
# carry. The two forms are the same three fields; only the declaration site differs, which
# is what makes the hoist cost no catalog edit and change no behaviour.

_IDENTITIES = (
    "id: invented\n"
    "identified_by:\n"
    "  - { owner: com.acme.Session, method: queue, arg: 0, by: scripts/probes/cp1_spring_paths.md }\n"
)


def _write_value_model(directory: Path, text: str) -> None:
    (directory / "value-models").mkdir()
    (directory / "value-models" / "invented.yml").write_text(text, encoding="utf-8")


def test_an_existing_channel_via_is_read_as_an_identity_entry():
    """Spec §2a step 1. The two forms are the same three fields; only the declaration site
    differs. Hoisting costs no catalog edit and changes no behaviour."""
    model = YamlCatalogSource(catalogs_dir()).value_model()

    assert {"owner": "jakarta/jms/Session#", "method": "createQueue", "arg": 0} in model


def test_an_identity_entry_without_an_owner_loads(tmp_path: Path):
    """§5a: a free function is an answer, not an error. Requiring `owner` would bake OO into
    a model the fact grammar does not."""
    _write_value_model(
        tmp_path,
        "id: invented\nidentified_by:\n"
        "  - { method: connect, arg: 0, by: scripts/probes/cp1_spring_paths.md }\n",
    )

    model = YamlCatalogSource(tmp_path).value_model()

    assert model == [{"method": "connect", "arg": 0, "by": "scripts/probes/cp1_spring_paths.md"}]


def test_an_identity_entry_without_a_probe_row_is_refused(tmp_path: Path):
    """§7b: `value-models/` becomes a dumping ground otherwise. The same rule the architecture
    suite already applies to `measured:` blocks."""
    _write_value_model(
        tmp_path,
        "id: invented\nidentified_by:\n  - { owner: com.acme.Session, method: queue, arg: 0 }\n",
    )

    with pytest.raises(CatalogError) as raised:
        YamlCatalogSource(tmp_path).value_model()

    assert "identified_by" in str(raised.value)
    assert "invented.yml" in str(raised.value)
    assert "by" in str(raised.value)


def test_a_declared_identity_is_read_beside_the_hoisted_ones(tmp_path: Path):
    """A `value-models/` entry and a hoisted one land in one table, the declared entries
    first: a producer whose measured form disagrees with a catalog's older spelling is then
    answered by the measured one under any first-match read."""
    _write_value_model(tmp_path, _IDENTITIES)
    (tmp_path / "invented-jms.yml").write_text(
        _HEADER + "matches:\n  methods:\n"
        "    - { name: send, channel_arg: 0,\n"
        "        channel_via: [{ owner: com.acme.Session, method: topic, arg: 0 }] }\n",
        encoding="utf-8",
    )

    model = YamlCatalogSource(tmp_path).value_model()

    assert model == [
        {
            "owner": "com/acme/Session#",
            "method": "queue",
            "arg": 0,
            "by": "scripts/probes/cp1_spring_paths.md",
        },
        {"owner": "com/acme/Session#", "method": "topic", "arg": 0},
    ]


def test_a_declared_entry_and_its_hoisted_twin_are_one_entry(tmp_path: Path):
    """`by` is provenance, not part of the claim. The producer a `value-models/` file
    declares and the catalog spelling the hoist finds are the same identity, so the table
    holds it once — the declared one, with its probe. Deduplicating on the whole mapping
    instead would list `java.net.URI#create` twice in the shipped table, once measured and
    once not."""
    _write_value_model(tmp_path, _IDENTITIES)
    (tmp_path / "invented-jms.yml").write_text(
        _HEADER + "matches:\n  methods:\n"
        "    - { name: send, channel_arg: 0,\n"
        "        channel_via: [{ owner: com.acme.Session, method: queue, arg: 0 }] }\n",
        encoding="utf-8",
    )

    assert YamlCatalogSource(tmp_path).value_model() == [
        {
            "owner": "com/acme/Session#",
            "method": "queue",
            "arg": 0,
            "by": "scripts/probes/cp1_spring_paths.md",
        }
    ]


def test_a_call_wrapper_is_hoisted_as_a_constructor_identity(tmp_path: Path):
    """`call_wrappers` names a TYPE and a constructor argument, so the producer is that
    type's `<init>` — the same three fields the other two keys spell directly."""
    (tmp_path / "invented-rest.yml").write_text(
        _HEADER + "matches:\n  call_wrappers:\n"
        "    - { type: com.acme.Entity, payload_ctor_arg: 0 }\n",
        encoding="utf-8",
    )

    model = YamlCatalogSource(tmp_path).value_model()

    assert model == [{"owner": "com/acme/Entity#", "method": "<init>", "role": "payload", "arg": 0}]


def test_two_value_models_declaring_one_producer_are_refused_by_file(tmp_path: Path):
    """One producer is declared once. Deduplication would otherwise keep whichever file
    `sorted(glob)` reaches first and drop the other's `by` with it — the citation is the
    whole justification for the entry (§7b), so losing one silently is the dumping ground
    arriving through a duplicate rather than through an omission."""
    _write_value_model(tmp_path, _IDENTITIES)
    (tmp_path / "value-models" / "second.yml").write_text(
        "id: second\nidentified_by:\n"
        "  - { owner: com.acme.Session, method: queue, arg: 0, by: scripts/probes/cp2_data_rest.md }\n",
        encoding="utf-8",
    )

    with pytest.raises(CatalogError) as raised:
        YamlCatalogSource(tmp_path).value_model()

    assert "second.yml" in str(raised.value)
    assert "invented" in str(raised.value)


def test_a_record_wrapper_hoists_one_entry_per_declared_position(tmp_path: Path):
    """`record_wrappers` is the fourth hop key — the same `{type, <name>_ctor_arg}` shape
    `call_wrappers` has, and the spec's §2a enumeration omitted it (ruled 2026-09-23). Its
    three shipped occurrences are byte-identical entries for one producer, which is the
    duplication "declared once per producer" exists to end.

    TWO entries from one wrapper, because the block declares two positions of the same
    constructor: two claims about two arguments, not one. `last` is carried verbatim — a
    rule resolved per site, never an index this layer could evaluate."""
    (tmp_path / "invented-kafka.yml").write_text(
        _HEADER + "matches:\n  record_wrappers:\n"
        "    - { type: com.acme.Record, channel_ctor_arg: 0, payload_ctor_arg: last }\n",
        encoding="utf-8",
    )

    assert YamlCatalogSource(tmp_path).value_model() == [
        {"owner": "com/acme/Record#", "method": "<init>", "role": "channel", "arg": 0},
        {"owner": "com/acme/Record#", "method": "<init>", "role": "payload", "arg": "last"},
    ]


def test_the_shipped_record_wrappers_collapse_to_one_producer():
    """The three shipped `record_wrappers` blocks say the same thing about the same
    constructor, in three files. Hoisted, they are two entries — one per position — and
    not six."""
    model = YamlCatalogSource(catalogs_dir()).value_model()
    record = [
        entry
        for entry in model
        if entry.get("owner") == "org/apache/kafka/clients/producer/ProducerRecord#"
    ]

    undiscriminated = [entry for entry in record if "descriptor" not in entry]

    assert undiscriminated == [
        {
            "owner": "org/apache/kafka/clients/producer/ProducerRecord#",
            "method": "<init>",
            "role": "channel",
            "arg": 0,
        },
        {
            "owner": "org/apache/kafka/clients/producer/ProducerRecord#",
            "method": "<init>",
            "role": "payload",
            "arg": "last",
        },
    ]


def test_a_directory_with_no_value_models_and_no_hop_keys_has_an_empty_model(tmp_path: Path):
    """A repository's own catalog set (D02 §6) declaring neither is an empty table, not an
    error — the `bean-models/` rule, for the same reason."""
    (tmp_path / "invented-bare.yml").write_text(_HEADER + "matches: {}\n", encoding="utf-8")

    assert YamlCatalogSource(tmp_path).value_model() == []


# --- the condition vocabulary a bean model carries (spec 2026-10-22 conditional-beans) -----


def _model_with(directory: Path, body: str) -> None:
    (directory / "bean-models").mkdir(exist_ok=True)
    (directory / "bean-models" / "tiny.yml").write_text("id: tiny\n" + body, encoding="utf-8")


def test_a_bean_model_carrying_a_well_formed_condition_vocabulary_loads(tmp_path: Path):
    _model_with(
        tmp_path,
        "conditions:\n"
        "  profile: {annotation: com.acme.Profile, expressions: value, by: probe.md}\n"
        "  other: {annotations: [com.acme.Odd], by: probe.md}\n"
        "presence:\n"
        "  missing: com.acme.Missing\n"
        "  present: com.acme.Present\n"
        "  type_attrs: [value, type]\n"
        "  name_attrs: [name]\n"
        "  annotation_attrs: [annotation]\n"
        "  order_reason: the order is not in the code\n"
        "  present_cycle_reason: both fail\n"
        "  by: probe.md\n"
        "stereotypes: [com.acme.Component]\n"
        "configuration_annotation: com.acme.Config\n"
        "stereotype_name_attrs: {com.acme.Component: value}\n",
    )
    (tmp_path / "invented-di.yml").write_text(
        _HEADER + "bean_model: tiny\nmatches: {}\n", encoding="utf-8"
    )

    [catalog] = YamlCatalogSource(tmp_path).load()

    assert catalog.bean_model["conditions"]["profile"]["annotation"] == "com.acme.Profile"
    assert catalog.bean_model["stereotypes"] == ["com.acme.Component"]
    assert catalog.bean_model["presence"]["name_attrs"] == ["name"]
    assert catalog.bean_model["presence"]["annotation_attrs"] == ["annotation"]
    assert catalog.bean_model["stereotype_name_attrs"] == {"com.acme.Component": "value"}


@pytest.mark.parametrize(
    ("body", "complaint"),
    [
        ("conditions: [profile]\n", "`conditions` must be a mapping"),
        ("conditions:\n  regex: {annotation: com.acme.Re, by: p.md}\n", "the kinds are"),
        ("conditions:\n  profile: {expressions: value, by: p.md}\n", "needs `annotation`"),
        ("conditions:\n  profile: {annotation: com.acme.P}\n", "`by:` probe"),
        ("conditions:\n  other: {by: p.md}\n", "`conditions.other` needs `annotations`"),
        (
            (
                "conditions:\n  profile: {annotation: com.acme.P, by: p.md, "
                "set_by: deploymnet, set_by_probe: q.md}\n"
            ),
            "`conditions.profile.set_by` is `deployment` or absent",
        ),
        (
            "conditions:\n  property: {annotation: com.acme.P, by: p.md, set_by: deployment}\n",
            "`conditions.property.set_by` needs a `set_by_probe:` probe",
        ),
        ("presence: {missing: com.acme.M, present: com.acme.P, by: p.md}\n", "`presence` needs"),
        (
            (
                "presence: {missing: com.acme.M, present: com.acme.P, type_attrs: [value], "
                "name_attrs: [name]}\n"
            ),
            "`presence` needs",
        ),
        (
            (
                "presence: {missing: com.acme.M, present: com.acme.P, type_attrs: [value], "
                "name_attrs: [name], order_reason: x, present_cycle_reason: y, by: p.md}\n"
            ),
            "`annotation_attrs`",
        ),
        (
            (
                "presence: {missing: com.acme.M, present: com.acme.P, type_attrs: [value], "
                "name_attrs: [name], annotation_attrs: [annotation], by: p.md}\n"
            ),
            "`order_reason`",
        ),
        (
            (
                "presence: {missing: com.acme.M, present: com.acme.P, type_attrs: [value], "
                "name_attrs: [name], annotation_attrs: [annotation], order_reason: x, "
                "by: p.md}\n"
            ),
            "`present_cycle_reason`",
        ),
        ("stereotype_name_attrs: [value]\n", "`stereotype_name_attrs` must map"),
        ("stereotype_name_attrs: {com.acme.Component: 7}\n", "`stereotype_name_attrs` must map"),
        ("stereotypes: []\n", "`stereotypes` must be a non-empty list"),
        ("stereotypes: com.acme.Component\n", "`stereotypes` must be a non-empty list"),
        ("stereotypes: [com.acme.Component, 7]\n", "`stereotypes` must be a non-empty list"),
        ("configuration_annotation: [com.acme.Config]\n", "`configuration_annotation` must"),
        ("interface_registrations: []\n", "`interface_registrations` must"),
        ("interface_registrations: [{supertypes: [], by: p.md}]\n", "`interface_registrations`"),
        ("interface_registrations: [{supertypes: [com.acme.Repo]}]\n", "`interface_registrations`"),
        (
            "interface_registrations: [{supertypes: [com.acme.Repo], excluded_by: [x], by: p.md}]\n",
            "`interface_registrations`",
        ),
    ],
)
def test_a_malformed_condition_vocabulary_is_refused_naming_the_model_file(
    tmp_path: Path, body: str, complaint: str
):
    """A typo here would strip every bean of its condition without a word, so the loader
    refuses it where the file is known — the contract `_models` kept when the block lived in
    a catalog."""
    _model_with(tmp_path, body)
    (tmp_path / "invented-di.yml").write_text(
        _HEADER + "bean_model: tiny\nmatches: {}\n", encoding="utf-8"
    )

    with pytest.raises(CatalogError) as raised:
        YamlCatalogSource(tmp_path).load()

    assert "tiny.yml" in str(raised.value)
    assert complaint in str(raised.value)


def test_the_shipped_spring_model_reads_bean_presence_only_through_presence():
    """Spec 2026-10-22-conditional-beans §2c: `@ConditionalOnMissingBean` / `@ConditionalOnBean`
    are evaluated from the module's own beans, so they leave the unevaluated `other` list — a
    second listing there would write them `unresolved` beside their evaluated rows."""
    spring = next(
        c.bean_model
        for c in YamlCatalogSource(catalogs_dir()).load()
        if c.bean_model.get("id") == "spring"
    )
    presence = spring["presence"]
    other = spring["conditions"]["other"]["annotations"]

    assert presence["missing"].endswith(".ConditionalOnMissingBean")
    assert presence["present"].endswith(".ConditionalOnBean")
    assert {presence["missing"], presence["present"]}.isdisjoint(other)


def test_an_unknown_dispatcher_word_is_refused(tmp_path: Path):
    """Ruling 3 of the 2026-10-30 object-identity design. `dispatcher` is a closed set — the
    dispatchers the server model's keys apply to — and a word outside it is a typo, not an
    absence. Read as
    absent, `dispatcher: sping` would quietly take every configured prefix off the catalog's
    rows, which is exactly what a catalog with no dispatcher means."""
    (tmp_path / "invented-typo.yml").write_text(
        _HEADER + "dispatcher: dispatcherservlet\nmatches: {}\n", encoding="utf-8"
    )

    with pytest.raises(CatalogError) as raised:
        YamlCatalogSource(tmp_path).load()

    assert "dispatcherservlet" in str(raised.value)
    assert "invented-typo.yml" in str(raised.value)


def test_a_server_model_key_naming_an_unknown_dispatcher_is_refused(tmp_path: Path):
    """The same closed set, on the server model's side: a key that `applies_to` a dispatcher
    its file does not declare would apply to nothing, silently."""
    (tmp_path / "server-models").mkdir()
    (tmp_path / "server-models" / "invented.yml").write_text(
        "id: invented\ndispatchers: [spring]\n"
        "stacks: [{stack: servlet, coordinates: ['org.springframework:spring-webmvc']}]\n"
        "prefixes:\n"
        "  - framework: org.springframework.boot\n"
        "    versions: '>=2.0'\n"
        "    measured: ['3.5.14']\n"
        "    stack: servlet\n"
        "    keys: [{key: server.servlet.context-path, applies_to: [sping]}]\n"
        "    protocols: [http]\n",
        encoding="utf-8",
    )

    with pytest.raises(CatalogError) as raised:
        YamlCatalogSource(tmp_path).server_model()

    assert "sping" in str(raised.value)
