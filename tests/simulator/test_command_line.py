"""The simulator's command line: the two delays it carries a train on (#1229).

A deployed box runs moves at the defaults unless its env file sets others,
and a delay that is not a positive number of seconds is refused before the
app starts.
"""

import sys

import pytest

import tc49.simulator.__main__ as simulator
from tc49.simulator.__main__ import simulator_command_line

REQUIRED = ["--broker", "broker:1883", "--store", "http://store:8765"]
"""The two flags every deployed simulator is passed, beside the delays."""


def test_the_delays_are_five_seconds_each_unless_set() -> None:
    args = simulator_command_line().parse_args(REQUIRED)

    assert (args.transit, args.clear) == (5.0, 5.0)


def test_a_set_delay_is_taken_in_seconds() -> None:
    args = simulator_command_line().parse_args(
        [*REQUIRED, "--transit", "2", "--clear", "0.5"]
    )

    assert (args.transit, args.clear) == (2.0, 0.5)


@pytest.mark.parametrize("value", ["0", "-1", "soon", "nan", "inf"])
def test_a_delay_that_is_not_a_positive_number_is_refused(
    value: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        simulator_command_line().parse_args([*REQUIRED, "--transit", value])
    assert "is not" in capsys.readouterr().err


def test_main_runs_the_simulator_on_the_delays_it_was_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    given: dict[str, object] = {}

    class Bus:
        def __init__(self, *_: object, **__: object) -> None: ...

        def close(self) -> None: ...

    def serve(*_: object, **kwargs: object) -> None:
        given.update(kwargs)

    monkeypatch.setattr(simulator, "MqttBus", Bus)
    monkeypatch.setattr(simulator, "serve", serve)
    monkeypatch.setattr(
        sys, "argv", ["simulator", *REQUIRED, "--transit", "2", "--clear", "0.5"]
    )

    simulator.main()

    assert (given["transit_s"], given["clear_s"]) == (2.0, 0.5)
