"""`chain_text`: a builder chain written as text, constants only (Quartz spec §3b, ruling 4).

Pure function over effective call-site rows, so the rows here carry only the columns it
reads (`owner`, `name`, `result`, `arguments`). Class names are invented; the shapes (a
fluent schedule chain, a nested builder argument, a boxed varargs) are the ones measured
on the Quartz builders."""

from typing import Any

import pytest

from sextant.application.resolve.shapes.chain_text import chain_text

SCHEDULE = "org/acme/Schedules#"
TIME_OF_DAY = "org/acme/TimeOfDay#"
BUILDER = "org/acme/Builder#"


def _site(
    owner: str, name: str, *arguments: dict[str, Any], result: int | None = None
) -> dict[str, Any]:
    return {"owner": owner, "name": name, "result": result, "arguments": list(arguments)}


def _int(value: int) -> dict[str, Any]:
    return {"kind": "int", "value": value}


def test_a_simple_schedule_chain_reads_as_written() -> None:
    sites = [
        _site(SCHEDULE, "simpleSchedule", result=1),
        _site(BUILDER, "withIntervalInSeconds", _int(30), result=2),
        _site(BUILDER, "repeatForever", result=3),
    ]

    assert chain_text(sites, {}) == "simpleSchedule().withIntervalInSeconds(30).repeatForever()"


def test_a_nested_builder_argument_is_written_as_its_call() -> None:
    nested = _site(TIME_OF_DAY, "hourAndMinuteOfDay", _int(9), _int(0), result=7)
    sites = [
        _site(SCHEDULE, "dailyTimeIntervalSchedule", result=1),
        _site(BUILDER, "startingDailyAt", {"kind": "unresolved", "source": 7}, result=2),
    ]

    assert (
        chain_text(sites, {7: nested})
        == "dailyTimeIntervalSchedule().startingDailyAt(TimeOfDay.hourAndMinuteOfDay(9, 0))"
    )


def test_a_boxed_varargs_reads_as_ints() -> None:
    # The projection (`effective_call_sites`) has already turned each boxed element into
    # its constant, so the array arrives holding ints.
    days = {"kind": "array", "elements": [_int(3), _int(5)]}
    sites = [
        _site(SCHEDULE, "dailyTimeIntervalSchedule", result=1),
        _site(BUILDER, "onDaysOfTheWeek", days, result=2),
    ]

    assert chain_text(sites, {}) == "dailyTimeIntervalSchedule().onDaysOfTheWeek(3, 5)"


@pytest.mark.pins("schedules.an-enum-constant-is-written-as-its-type-and-name")
def test_an_enum_constant_reads_as_its_type_and_name() -> None:
    hour = {"kind": "enum", "symbol": "org/acme/IntervalUnit#HOUR."}
    sites = [
        _site(SCHEDULE, "dailyTimeIntervalSchedule", result=1),
        _site(BUILDER, "withInterval", _int(1), hour, result=2),
    ]

    assert chain_text(sites, {}) == (
        "dailyTimeIntervalSchedule().withInterval(1, IntervalUnit.HOUR)"
    )


def test_a_string_argument_is_quoted() -> None:
    sites = [_site(SCHEDULE, "named", {"kind": "string", "value": "nightly"}, result=1)]

    assert chain_text(sites, {}) == 'named("nightly")'


def test_a_class_a_boolean_and_a_long_read_as_written() -> None:
    sites = [
        _site(
            SCHEDULE,
            "of",
            {"kind": "class", "symbol": "org/acme/Job#"},
            {"kind": "boolean", "value": True},
            {"kind": "long", "value": 5000},
        )
    ]

    assert chain_text(sites, {}) == "of(Job, true, 5000)"


@pytest.mark.pins("schedules.a-chain-with-a-non-constant-argument-has-no-text")
@pytest.mark.parametrize(
    "argument",
    [
        {"kind": "unresolved"},
        {"kind": "unresolved", "source": 9},
        {"kind": "parameter", "value": 0},
        {"kind": "field", "symbol": "org/acme/Config#unit."},
        {"kind": "array", "elements": [_int(1), {"kind": "unresolved"}]},
    ],
)
def test_a_non_constant_argument_gives_none(argument: dict[str, Any]) -> None:
    sites = [
        _site(SCHEDULE, "simpleSchedule", result=1),
        _site(BUILDER, "withIntervalInSeconds", argument, result=2),
    ]

    assert chain_text(sites, {}) is None


@pytest.mark.pins("schedules.a-chain-with-a-non-constant-argument-has-no-text")
def test_a_nested_call_with_a_non_constant_argument_gives_none() -> None:
    nested = _site(TIME_OF_DAY, "hourAndMinuteOfDay", {"kind": "unresolved"}, result=7)
    sites = [_site(BUILDER, "startingDailyAt", {"kind": "unresolved", "source": 7})]

    assert chain_text(sites, {7: nested}) is None
