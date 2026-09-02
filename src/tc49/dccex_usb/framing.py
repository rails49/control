"""The framing rule: a client's bytes become whole `<…>` messages.

The command station delimits a message with `<` and `>`, and this app reads
nothing else of the protocol (ADR-0043). Several clients share one device, so
a message reaches it whole or not at all: bytes arrive from a client in
whatever chunks TCP hands over and are held here until the `>` that ends the
message.

Bytes outside a message are dropped. Before a `<` there is nothing for them
to belong to, and after a `>` the same. A `<` inside a message starts the
message over rather than joining it, because what came before was never a
message — `<<t 3 0 1>` is one command.

A message that passes `MAX_MESSAGE` without its `>` is discarded rather than
grown: nothing the station answers to is that long, so a client sending it is
a broken one, and the bytes after it are dropped until the next `<`.

Pure, so the rule is read and tested on its own, with no socket and no device.
"""

MAX_MESSAGE = 1024

START = ord("<")
END = ord(">")


def frame(buffered: bytes, arrived: bytes) -> tuple[bytes, list[bytes]]:
    """Fold `arrived` into `buffered`.

    Returns what is still a partial message, to be passed back as `buffered`
    next time, and the messages that completed — delimiters included, in the
    order they closed.
    """
    partial = buffered
    messages: list[bytes] = []
    for byte in arrived:
        if byte == START:
            partial = b"<"
        elif not partial:
            continue
        elif byte == END:
            messages.append(partial + b">")
            partial = b""
        else:
            partial += bytes((byte,))
            if len(partial) > MAX_MESSAGE:
                partial = b""
    return partial, messages
