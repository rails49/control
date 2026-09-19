"""What the station says, framed and read: the three facts, and everything
else.

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


def test_the_banner_names_the_build_the_station_is_running() -> None:
    """The station answers `<s>` with a banner whose last field is the build
    it was made from, and this railroad's firmware puts the release tag
    there: the row then names exactly which build is on the box, which is
    what makes a flash verifiable (ADR-0065)."""
    assert replies.reply(
        b"<iDCC-EX V-5.6.4 / ESP32 / EXCSB1_WITH_EX8874 G-v5.6.4-rails49.1>"
    ) == replies.Build(build="v5.6.4-rails49.1")


def test_an_older_station_names_a_commit_and_that_is_a_build_too() -> None:
    """Firmware built from a checkout rather than a release reports the
    commit it came from. That is still a build identifier and goes out as it
    stands: the field is free text and this app does not interpret it."""
    assert replies.reply(
        b"<iDCC-EX V-5.4.16 / ESP32 / EXCSB1_WITH_EX8874 G-9db8d0e>"
    ) == replies.Build(build="9db8d0e")


def test_a_banner_with_no_build_in_it_names_none() -> None:
    """A banner this app cannot read a build out of says nothing about the
    build, and is not thereby a link failure: what the link is made of is the
    station having answered at all."""
    assert replies.reply(b"<iDCC-EX V-5.6.4 / ESP32>") is None
    assert replies.reply(b"<iDCC-EX>") is None
    assert replies.reply(b"<i>") is None


def test_everything_else_on_the_port_reads_as_nothing() -> None:
    for other in (
        b"<l 3 0 128 0>",
        b"<H 1 1>",
        b"<Q 7>",
        b"<jI 250 0>",
        b"<>",
    ):
        assert replies.reply(other) is None
