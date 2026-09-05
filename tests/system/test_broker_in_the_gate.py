"""A missing broker reddens the gate rather than emptying it (#423).

The `broker` fixture is the one place the decision is made, and every suite
that comes up against a real bus takes it. Skipping there on a machine with
no `mosquitto` is what lets the rest of the suite run; skipping there in CI
would delete the bus from the gate and still report green, so under CI the
absence is a failure instead — a broker is software and belongs in the gate
where hardware does not (#372).
"""

import pytest

from tests.brokers import no_broker


def test_no_broker_skips_off_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CI", raising=False)
    with pytest.raises(BaseException) as raised:
        no_broker("no mosquitto installed")
    assert raised.type is pytest.skip.Exception


@pytest.mark.parametrize("says_ci", ["true", "1", "TRUE"])
def test_no_broker_fails_under_ci(
    monkeypatch: pytest.MonkeyPatch, says_ci: str
) -> None:
    monkeypatch.setenv("CI", says_ci)
    with pytest.raises(BaseException) as raised:
        no_broker("no mosquitto installed")
    assert raised.type is pytest.fail.Exception
    assert "mosquitto" in str(raised.value)


@pytest.mark.parametrize("not_ci", ["", "0", "false"])
def test_an_unset_looking_ci_still_skips(
    monkeypatch: pytest.MonkeyPatch, not_ci: str
) -> None:
    monkeypatch.setenv("CI", not_ci)
    with pytest.raises(BaseException) as raised:
        no_broker("mosquitto would not start")
    assert raised.type is pytest.skip.Exception
