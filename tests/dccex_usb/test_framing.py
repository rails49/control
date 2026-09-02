"""Tests at the framing seam: bytes in, whole `<…>` messages out."""

from tc49.dccex_usb.framing import MAX_MESSAGE, frame


def test_a_whole_message_arrives_whole() -> None:
    assert frame(b"", b"<t 3 50 1>") == (b"", [b"<t 3 50 1>"])


def test_a_message_split_across_chunks_is_held_until_it_closes() -> None:
    partial, messages = frame(b"", b"<t 3 ")
    assert messages == []

    assert frame(partial, b"50 1>") == (b"", [b"<t 3 50 1>"])


def test_several_messages_in_one_chunk_come_out_in_order() -> None:
    assert frame(b"", b"<t 3 50 1><a 12 1>") == (b"", [b"<t 3 50 1>", b"<a 12 1>"])


def test_bytes_before_a_message_are_dropped() -> None:
    assert frame(b"", b"noise<p1>") == (b"", [b"<p1>"])


def test_bytes_after_a_message_are_dropped() -> None:
    assert frame(b"", b"<p1>noise") == (b"", [b"<p1>"])


def test_a_second_start_restarts_the_message() -> None:
    """`<<t 3 0 1>` is one command: what preceded the `<` was never one."""
    assert frame(b"", b"<<t 3 0 1>") == (b"", [b"<t 3 0 1>"])


def test_a_start_abandons_a_partial_message() -> None:
    assert frame(b"<t 3 5", b"<p1>") == (b"", [b"<p1>"])


def test_an_overlong_message_is_discarded() -> None:
    partial, messages = frame(b"", b"<" + b"x" * MAX_MESSAGE)

    assert (partial, messages) == (b"", [])


def test_the_bytes_after_an_overlong_message_are_dropped_too() -> None:
    partial, messages = frame(b"", b"<" + b"x" * MAX_MESSAGE + b"y>")

    assert (partial, messages) == (b"", [])


def test_a_message_at_the_limit_still_closes() -> None:
    message = b"<" + b"x" * (MAX_MESSAGE - 1) + b">"

    assert frame(b"", message) == (b"", [message])
