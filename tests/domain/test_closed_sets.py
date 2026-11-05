from sextant.domain.closed_sets import Evidence, Protocol, precedence_of


def test_precedence_ranks_human_above_code_when_evidence_is_curated():
    assert precedence_of(Evidence.HUMAN) == 90


def test_precedence_ranks_model_below_code_when_evidence_is_llm():
    assert precedence_of(Evidence.LLM) == 10


def test_precedence_is_fifty_when_evidence_is_any_code_derived_value():
    for evidence in (Evidence.COMPILER, Evidence.SYNTAX, Evidence.NAME_MATCH, Evidence.DECLARED):
        assert precedence_of(evidence) == 50


def test_amqp_and_pulsar_are_protocols():
    assert Protocol.AMQP == "amqp"
    assert Protocol.PULSAR == "pulsar"


def test_the_broker_families_are_distinct_protocols():
    # D00 §4's reason: linking gates on protocol equality (DR-5), and an AMQP
    # exchange can never be answered by a Pulsar topic.
    assert len({Protocol.AMQP, Protocol.PULSAR, Protocol.JMS, Protocol.KAFKA}) == 4


def test_the_two_group_d_protocols_are_members():
    assert Protocol.TEMPORAL.value == "temporal"
    assert Protocol.EVENTBUS.value == "eventbus"


def test_actor_is_a_protocol():
    assert Protocol.ACTOR.value == "actor"


def test_in_process_is_a_protocol():
    """Spec 2026-11-05 §3: a dispatch catalog with no wire (Spring application events) writes
    its hops under `in_process`, named for the kind of hand-over, never a framework."""
    assert Protocol.IN_PROCESS.value == "in_process"
