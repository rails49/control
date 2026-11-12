"""The simulator's command line: the two delays it carries a train on (#1229).

A deployed box runs moves at the defaults unless its env file sets others,
and a delay that is not a positive number of seconds is refused before the
app starts.
"""

import pytest

from tc49.simulator.__main__ import parser

REQUIRED = ["--broker", "broker:1883", "--store", "http://store:8765"]
"""The two flags every deployed simulator is passed, beside the delays."""


def test_the_delays_are_five_seconds_each_unless_set() -> None:
    args = parser().parse_args(REQUIRED)

    assert (args.transit, args.clear) == (5.0, 5.0)


def test_a_set_delay_is_taken_in_seconds() -> None:
    args = parser().parse_args([*REQUIRED, "--transit", "2", "--clear", "0.5"])

    assert (args.transit, args.clear) == (2.0, 0.5)


@pytest.mark.parametrize("value", ["0", "-1", "soon", "nan", "inf"])
def test_a_delay_that_is_not_a_positive_number_is_refused(
    value: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        parser().parse_args([*REQUIRED, "--transit", value])
    assert "is not" in capsys.readouterr().err
