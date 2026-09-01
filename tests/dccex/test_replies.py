"""What the station says, framed and read: the two facts, and everything else.

The port carries the whole conversation — this app's replies, and every
broadcast meant for JMRI, a hand-held throttle or a browser — so most of what
is read here is somebody else's and reads as nothing at all (#289).
"""

from tc49.dccex import replies


def test_bytes_become_whole_messages() -> None:
    assert replies.messages(b"", b"<p1><p0 A>") == (b"", [b"<p1>", b"<p0 A>"])


def test_a_partial_message_is_carried_to_the_next_read() -> None:
    partial, whole = replies.messages(b"", b"<p1 ")
    assert whole == []
    assert replies.messages(partial, b"A>") == (b"", [b"<p1 A>"])


def test_bytes_outside_a_message_are_dropped() -> None:
    assert replies.messages(b"", b"junk<p1>more") == (b"", [b"<p1>"])


def test_a_second_start_begins_the_message_again() -> None:
    assert replies.messages(b"", b"<p1<p0>") == (b"", [b"<p0>"])


def test_a_message_that_never_ends_is_discarded() -> None:
    partial, whole = replies.messages(b"", b"<" + b"x" * (replies.MAX_MESSAGE + 1))
    assert (partial, whole) == (b"", [])


def test_the_line_naming_a_track_says_which() -> None:
    assert replies.reply(b"<p1 A>") == replies.Power(track="A", on=True)
    assert replies.reply(b"<p0 B>") == replies.Power(track="B", on=False)


def test_the_line_naming_no_track_says_it_of_every_one() -> None:
    assert replies.reply(b"<p1>") == replies.Power(track="", on=True)
    assert replies.reply(b"<p0>") == replies.Power(track="", on=False)


def test_a_power_line_naming_a_mode_names_no_track() -> None:
    """`MAIN`, `PROG` and `JOIN` are what a track is *for*, not a district:
    reading one as a track would put a district on the railroad the hardware
    does not have."""
    assert replies.reply(b"<p1 MAIN>") is None
    assert replies.reply(b"<p1 JOIN>") is None


def test_the_lock_is_read_off_what_the_station_broadcasts() -> None:
    assert replies.reply(b"<!PAUSED>") == replies.Lock(locked=True)
    assert replies.reply(b"<!RESUMED>") == replies.Lock(locked=False)


def test_everything_else_on_the_port_reads_as_nothing() -> None:
    for other in (
        b"<iDCC-EX V-5.6.3 / ESP32 / EXCSB1_WITH_EX8874 G-0ad3080>",
        b"<l 3 0 128 0>",
        b"<H 1 1>",
        b"<Q 7>",
        b"<jI 250 0>",
        b"<>",
    ):
        assert replies.reply(other) is None
