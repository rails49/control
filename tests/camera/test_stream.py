"""The camera side read alone: the parts of an MJPEG body, and the login a
camera is asked with (#851)."""

import io

from tc49.camera.stream import credentials, frames, stream_url


def body(*parts: bytes) -> io.BytesIO:
    return io.BytesIO(b"".join(parts))


def part(frame: bytes, length: int | None = None) -> bytes:
    said = len(frame) if length is None else length
    return (
        b"--myboundary\r\nContent-Type: image/jpeg\r\n"
        + f"Content-Length: {said}\r\n\r\n".encode()
        + frame
        + b"\r\n"
    )


def test_each_part_is_its_jpeg_unchanged() -> None:
    one, two = b"\xff\xd8one\r\n--myboundary\xff\xd9", b"\xff\xd8two\xff\xd9"
    assert list(frames(body(part(one), part(two)))) == [one, two]


def test_a_part_with_no_length_ends_the_stream() -> None:
    no_length = b"--myboundary\r\nContent-Type: image/jpeg\r\n\r\n\xff\xd8\xff\xd9\r\n"
    assert list(frames(body(part(b"a"), no_length, part(b"b")))) == [b"a"]


def test_a_part_shorter_than_it_says_ends_the_stream() -> None:
    assert list(frames(body(part(b"a"), part(b"bb", length=10)))) == [b"a"]


def test_the_closing_boundary_ends_the_stream() -> None:
    assert list(frames(body(part(b"a"), b"--myboundary--\r\n"))) == [b"a"]


def test_the_login_is_admin_with_no_password_unless_set() -> None:
    assert credentials({}) == "Basic YWRtaW46"  # admin:
    assert credentials({"TC49_CAMERA_USER": ""}) == "Basic YWRtaW46"
    assert (
        credentials({"TC49_CAMERA_USER": "viewer", "TC49_CAMERA_PASSWORD": "pw"})
        == "Basic dmlld2VyOnB3"
    )  # viewer:pw


def test_a_camera_is_asked_at_its_stream() -> None:
    assert stream_url("192.168.178.58") == "http://192.168.178.58/media/?action=stream"
