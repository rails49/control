"""The mapping, a row at a time: a desired value in, the exact bytes out.

Every row of the table in docs/dccex/README.md is here, asserted on the byte
string and not on a shape, because the byte string is the whole of what this
app promises the command station. Pure functions, so none of it needs a
socket, a bus or hardware (#289).
"""

from tc49.dccex import commands


def test_a_speed_is_scaled_and_its_sign_is_the_direction() -> None:
    assert commands.traction("3", 1.0) == b"<t 3 126 1>"
    assert commands.traction("3", -1.0) == b"<t 3 126 0>"
    assert commands.traction("3", 0.5) == b"<t 3 63 1>"
    assert commands.traction("460", -0.25) == b"<t 460 32 0>"


def test_full_speed_either_way_is_one_step_and_two_directions() -> None:
    """The acceptance criterion, stated as the two commands differing in one
    field: the magnitude is the fraction of the locomotive's maximum and the
    sign is which way it runs along the track."""
    forward = commands.traction("3", 1.0)
    backward = commands.traction("3", -1.0)
    assert forward == b"<t 3 126 1>"
    assert backward == b"<t 3 126 0>"
    assert forward[:-2] == backward[:-2]


def test_a_speed_of_zero_is_step_zero() -> None:
    assert commands.traction("3", 0.0) == b"<t 3 0 1>"


def test_a_fraction_past_the_maximum_is_the_maximum() -> None:
    """There is nothing above a locomotive's maximum to ask for, so a
    fraction past the range is full speed and never more."""
    assert commands.traction("3", 4.0) == b"<t 3 126 1>"
    assert commands.traction("3", -4.0) == b"<t 3 126 0>"


def test_a_function_is_the_switch_the_station_has() -> None:
    assert commands.function("3", "2", "on") == b"<F 3 2 1>"
    assert commands.function("3", "2", "off") == b"<F 3 2 0>"


def test_a_function_value_this_hardware_cannot_express_sends_nothing() -> None:
    """A model's functions are fully configurable and the station's are
    switches, so a three-position vacuum names a state there is no packet
    for and nothing is sent rather than something near it."""
    assert commands.function("3", "5", "high") is None


def test_a_point_is_a_stateless_accessory_packet() -> None:
    """The drawing types the accessory number a throttle shows, and the
    packet wants a decoder address and a sub-address: four to a decoder."""
    assert commands.point("1", "closed") == b"<a 1 0 0>"
    assert commands.point("4", "thrown") == b"<a 1 3 1>"
    assert commands.point("5", "closed") == b"<a 2 0 0>"
    assert commands.point("2044", "thrown") == b"<a 511 3 1>"


def test_a_point_position_the_contract_does_not_name_sends_nothing() -> None:
    assert commands.point("5", "middle") is None


def test_an_address_that_is_no_accessory_number_sends_nothing() -> None:
    assert commands.point("LT3", "closed") is None
    assert commands.point("0", "closed") is None
    assert commands.point("2045", "closed") is None


def test_a_signal_is_an_extended_accessory_packet() -> None:
    assert commands.signal("40", "stop") == b"<A 40 0>"
    assert commands.signal("40", "caution") == b"<A 40 1>"
    assert commands.signal("40", "clear") == b"<A 40 2>"


def test_an_aspect_no_head_here_is_wired_for_sends_nothing() -> None:
    """An aspect is a name and not an enum, so what a head shows is wiring:
    one this translator has no packet for is silence rather than a guess."""
    assert commands.signal("40", "approach medium") is None


def test_the_track_takes_the_word_the_whole_railroad_shares() -> None:
    assert commands.track("on") == b"<1>"
    assert commands.track("off") == b"<0>"


def test_a_stop_is_the_lock_and_not_the_one_shot() -> None:
    """`<!P>` latches until it is released; `<!>` would be a one-shot any
    throttle on the same port could drive away from."""
    assert commands.track("stopped") == b"<!P>"
    assert commands.RELEASE == b"<!R>"


def test_a_poll_asks_for_the_status_and_for_the_lock() -> None:
    assert commands.STATUS == b"<s>"
    assert commands.LOCK_QUERY == b"<!Q>"


def test_a_startup_file_is_handed_over_line_by_line() -> None:
    """The file is not parsed beyond blank and comment: a line is a string
    the station is handed, so that a person can write anything their station
    understands without this app growing a vocabulary for it."""
    assert commands.startup(
        "<= A LIMIT 3000>\n<= B LIMIT 3000>\n<= C LIMIT 1500>\n"
    ) == [b"<= A LIMIT 3000>", b"<= B LIMIT 3000>", b"<= C LIMIT 1500>"]


def test_comments_and_blank_lines_are_not_sent() -> None:
    """The line naming which district a value is for has to be one the
    station never sees."""
    assert commands.startup(
        "# trip currents for the four districts\n"
        "\n"
        "  <= A LIMIT 3000>  \n"
        "   # D is the yard\n"
        "<= D LIMIT 1500>\n"
    ) == [b"<= A LIMIT 3000>", b"<= D LIMIT 1500>"]


def test_a_file_with_nothing_in_it_sends_nothing() -> None:
    assert commands.startup("") == []
    assert commands.startup("\n\n# only a note\n") == []
