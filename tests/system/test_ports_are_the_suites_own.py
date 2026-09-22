"""The number a test's server listens on is the suite's own (#560).

Picked by binding `:0` and closing the socket, it was nobody's: the kernel
draws outbound connections from the same ephemeral range, and the run that
failed had an MQTT client reconnecting in a loop while a store waited to be
started on the number it had been promised.

No fixture here can close that window by binding first. A store's port is
read before its server binds, because the app is started against its URL and
the store second — that order is what those suites are for (ADR-0059,
decision 5) — and mosquitto's goes into a config file written before the
process starts. So the picking has to be what is right instead: below the
range the kernel hands out by itself, and never the same number twice in one
run.
"""

import socket

import pytest

from tests.ports import EPHEMERAL_FIRST, Ports, free_port


def test_no_number_is_handed_out_twice_in_a_run() -> None:
    """Two fixtures asking one after the other, which is what a suite does:
    the second cannot be given what the first is about to bind."""
    picked = [free_port() for _ in range(200)]
    assert len(set(picked)) == len(picked)


def test_the_numbers_are_below_the_range_the_kernel_hands_out() -> None:
    """Nothing takes one of these by accident: an outbound connection is
    given an ephemeral port, and these are not ephemeral ports."""
    assert 1024 < EPHEMERAL_FIRST
    assert all(1024 < free_port() < EPHEMERAL_FIRST for _ in range(50))


def test_a_number_something_is_listening_on_is_stepped_over() -> None:
    """The one caller this cannot speak for is a program outside the run. It
    is holding its port, so the kernel refuses ours and the next is offered
    instead."""
    port = free_port()
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", port))
        taken.listen()
        assert Ports(port, port + 2, start=port).take() != port


def test_a_band_with_nothing_left_in_it_says_so() -> None:
    """Rather than handing out a number that is already taken and leaving the
    failure to whoever binds it."""
    port = free_port()
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", port))
        taken.listen()
        with pytest.raises(RuntimeError, match="no free port"):
            Ports(port, port, start=port).take()
