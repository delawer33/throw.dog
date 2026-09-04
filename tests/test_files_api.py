"""The file path over HTTP: a code buys a ticket, the ticket buys the bytes."""

import pytest
from fastapi.testclient import TestClient

from app.closedaddress import is_closed_address
from app.filestore import FileStore
from app.main import Settings, content_disposition, create_app, parse_range

TEST_SETTINGS = Settings(miss_delay_ms=0, gate_tarpit_delay_ms=0)


class FakeClock:
    """A clock the test moves by hand, so nothing ever sleeps."""

    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture()
def client(tmp_path):
    with TestClient(create_app(TEST_SETTINGS)) as test_client:
        yield test_client


def put_file(client, payload: bytes, *, chunk_size: int = 8, **kwargs) -> str:
    """Land a file in the store directly and return the code addressing it.

    The upload endpoints are a separate slice; what is under test here is what
    happens once a file has arrived.
    """
    store = client.app.state.files
    chunks = [payload[i : i + chunk_size] for i in range(0, len(payload), chunk_size)]
    upload = store.begin(size=len(payload), chunks=len(chunks), **kwargs)
    for index, chunk in enumerate(chunks):
        store.write_chunk(upload, index, chunk)
    return store.finish(upload)


def take(client, code: str):
    return client.post(f"/api/throws/{code}")


# --- the ticket -------------------------------------------------------------


def test_a_code_buys_a_ticket_and_the_ticket_buys_the_bytes(client):
    code = put_file(client, b"holiday photo", name="photo.jpg", mime="image/jpeg")

    grant = take(client, code)
    assert grant.status_code == 200
    body = grant.json()
    assert body["kind"] == "file"
    assert body["size"] == len(b"holiday photo")
    assert body["name"] == "photo.jpg"
    assert body["mime"] == "image/jpeg"
    assert is_closed_address(body["ticket"])

    download = client.get(body["url"])
    assert download.status_code == 200
    assert download.content == b"holiday photo"


def test_the_code_is_dead_the_moment_the_ticket_is_handed_out(client):
    code = put_file(client, b"one receiver")
    assert take(client, code).status_code == 200

    second = take(client, code)
    assert second.status_code == 404
    assert second.json() == {"detail": "no such throw"}


def test_a_file_code_is_forgiving_like_any_other_code(client):
    code = put_file(client, b"typed by hand")
    assert take(client, code.upper().replace("-", " ")).status_code == 200


def test_a_closed_file_carries_its_scheme_and_no_name(client):
    code = put_file(client, b"ciphertext", encrypted=True, enc="aes-gcm-v1")
    assert is_closed_address(code)

    body = take(client, code).json()
    assert body["enc"] == "aes-gcm-v1"
    assert "name" not in body, "a closed file's name is inside the ciphertext"
    assert "mime" not in body


def test_a_miss_on_a_code_is_unchanged_by_the_existence_of_files(client):
    text = client.post("/api/throws", json={"text": "a text throw"}).json()["code"]
    missed = take(client, "red-fox")
    read_text = take(client, text)

    assert missed.status_code == 404
    assert missed.json() == {"detail": "no such throw"}
    assert read_text.json() == {"text": "a text throw"}, "text answers as before"


# --- the download ------------------------------------------------------------


def test_the_bytes_always_arrive_as_a_download_never_as_a_page(client):
    url = take(client, put_file(client, b"<script>alert(1)</script>", name="x.html")).json()["url"]

    response = client.get(url)
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["cache-control"] == "no-store"


def test_a_finished_download_takes_the_file_with_it(client):
    url = take(client, put_file(client, b"delivered")).json()["url"]
    store = client.app.state.files

    assert client.get(url).content == b"delivered"
    assert client.get(url).status_code == 404, "the ticket died with the delivery"
    assert list(store.root.iterdir()) == []


def test_a_dropped_download_can_be_resumed_and_arrives_whole(client):
    payload = bytes(range(256)) * 4
    url = take(client, put_file(client, payload, chunk_size=64)).json()["url"]

    head = client.get(url, headers={"Range": "bytes=0-99"})
    assert head.status_code == 206
    assert head.headers["content-range"] == f"bytes 0-99/{len(payload)}"
    assert head.content == payload[:100]

    tail = client.get(url, headers={"Range": f"bytes=100-{len(payload) - 1}"})
    assert tail.status_code == 206
    assert head.content + tail.content == payload


def test_only_the_range_carrying_the_last_byte_ends_the_ticket(client):
    payload = b"0123456789"
    url = take(client, put_file(client, payload)).json()["url"]

    assert client.get(url, headers={"Range": "bytes=0-4"}).status_code == 206
    assert client.get(url, headers={"Range": "bytes=0-4"}).status_code == 206
    assert client.get(url).content == payload
    assert client.get(url).status_code == 404


def test_a_range_past_the_end_is_refused_without_killing_the_ticket(client):
    url = take(client, put_file(client, b"0123456789")).json()["url"]

    refused = client.get(url, headers={"Range": "bytes=100-200"})
    assert refused.status_code == 416
    assert refused.headers["content-range"] == "bytes */10"
    assert client.get(url).content == b"0123456789", "the file is still there"


def test_someone_elses_ticket_opens_nothing(client):
    mine = take(client, put_file(client, b"mine")).json()
    yours = take(client, put_file(client, b"yours")).json()

    assert client.get(yours["url"]).content == b"yours"
    assert client.get(mine["url"]).content == b"mine"
    assert client.get("/api/files/t/2abcdefghijkmn").status_code == 404


def test_an_expired_file_is_gone_before_anyone_asks(tmp_path):
    clock = FakeClock()
    store = FileStore(tmp_path / "throws", ttl_seconds=600, clock=clock)
    with TestClient(create_app(TEST_SETTINGS, files=store)) as client:
        code = put_file(client, b"nobody came")

        clock.advance(601)
        assert take(client, code).status_code == 404
        assert list(store.root.iterdir()) == []


def test_a_download_is_never_indexed(client):
    url = take(client, put_file(client, b"private")).json()["url"]
    assert "noindex" in client.get(url).headers["x-robots-tag"]


# --- headers and ranges, on their own ---------------------------------------


def test_a_sender_chosen_filename_cannot_forge_a_header():
    header = content_disposition("evil\r\nX-Injected: yes.txt")
    assert "\r" not in header and "\n" not in header
    assert header.startswith('attachment; filename="throw.bin"')


def test_a_unicode_filename_survives_as_an_encoded_parameter():
    header = content_disposition("отчёт.pdf")
    assert "filename*=UTF-8''" in header
    assert "%D0%BE" in header


def test_a_nameless_file_still_downloads_under_some_name():
    assert content_disposition(None) == 'attachment; filename="throw.bin"'


@pytest.mark.parametrize(
    "header,expected",
    [
        (None, None),
        ("", None),
        ("bytes=0-4", (0, 4)),
        ("bytes=5-", (5, 9)),
        ("bytes=-3", (7, 9)),
        ("bytes=0-99", (0, 9)),  # clamped to what we have
        ("items=0-4", None),  # a unit we do not speak: serve the whole file
        ("bytes=0-4, 6-8", None),  # multipart is a document-viewer feature
        ("bytes=nonsense", None),
    ],
)
def test_range_headers_we_understand_and_the_ones_we_ignore(header, expected):
    assert parse_range(header, 10) == expected


@pytest.mark.parametrize("header", ["bytes=10-12", "bytes=5-1", "bytes=-0"])
def test_ranges_the_file_cannot_satisfy(header):
    from app.main import UNSATISFIABLE

    assert parse_range(header, 10) is UNSATISFIABLE


# --- what the log is allowed to say -----------------------------------------


def test_a_file_read_is_logged_by_shape_and_bucket_never_by_name(client, capsys):
    code = put_file(client, b"x" * 100, name="salaries-2026.xlsx", mime="text/csv")
    capsys.readouterr()

    take(client, code)

    line = capsys.readouterr().out.strip()
    assert "kind=file" in line
    assert "size=<=64K" in line, "an order of magnitude, not a fingerprint"
    assert "salaries" not in line
    assert code not in line


def test_a_ticket_never_reaches_the_access_log():
    from app.main import sanitize_log_path

    ticket = "2abcdefghijkmn"
    redacted = sanitize_log_path(f"/api/files/t/{ticket}")
    assert ticket not in redacted
    assert redacted.startswith("/api/files/t/")


def test_an_upload_id_never_reaches_the_access_log_but_the_chunk_number_does():
    from app.main import sanitize_log_path

    upload = "2abcdefghijkmn"
    redacted = sanitize_log_path(f"/api/files/{upload}/7")
    assert upload not in redacted
    assert redacted.endswith("/7")
