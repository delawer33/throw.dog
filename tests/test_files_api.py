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


@pytest.fixture()
def limited():
    """A client whose upload limiter is tighter than production's."""
    from contextlib import ExitStack

    from app.gatekeeper import UploadLimiter

    with ExitStack() as stack:

        def build(**kwargs):
            app = create_app(TEST_SETTINGS, upload_limiter=UploadLimiter(**kwargs))
            return stack.enter_context(TestClient(app))

        yield build


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
    return store.finish(upload).code


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


# --- the upload -------------------------------------------------------------


def send(client, payload: bytes, *, pieces: list[bytes] | None = None, **fields):
    """Push ``payload`` through the three upload handles. Returns the code.

    ``pieces`` spells the chunking out where it is not the plain open-mode one
    — a closed upload leads with its sealed header, so its pieces are not just
    the file cut into equal parts.
    """
    from app.filestore import CHUNK_BYTES

    if pieces is None:
        pieces = [
            payload[i : i + CHUNK_BYTES] for i in range(0, max(1, len(payload)), CHUNK_BYTES)
        ]
    fields.setdefault("size", len(payload))
    fields.setdefault("chunks", len(pieces))
    started = client.post("/api/files", json=fields)
    assert started.status_code == 201, started.text
    upload = started.json()["upload"]
    for index, piece in enumerate(pieces):
        assert client.put(f"/api/files/{upload}/{index}", content=piece).status_code == 204
    done = client.post(f"/api/files/{upload}/done")
    assert done.status_code == 201, done.text
    return done.json()["code"]


def test_a_file_uploaded_in_chunks_comes_back_whole(client):
    payload = bytes(range(256)) * 40
    code = send(client, payload, name="dump.bin", mime="application/octet-stream")

    body = take(client, code).json()
    assert body["size"] == len(payload)
    assert client.get(body["url"]).content == payload


def test_no_address_exists_until_the_file_has_fully_arrived(client):
    started = client.post("/api/files", json={"size": 8, "chunks": 1})
    upload = started.json()["upload"]

    assert take(client, upload).status_code == 404
    assert client.post(f"/api/files/{upload}/done").status_code == 400, "nothing arrived"


def test_an_oversized_open_file_is_refused_before_a_byte_of_it_arrives(client):
    from app.main import DEFAULT_OPEN_FILE_MAX_BYTES

    over = DEFAULT_OPEN_FILE_MAX_BYTES + 1
    refused = client.post("/api/files", json={"size": over, "chunks": 7})

    assert refused.status_code == 413
    assert str(DEFAULT_OPEN_FILE_MAX_BYTES) in refused.json()["detail"]
    assert client.app.state.files.total_bytes() == 0, "nothing was reserved"


def test_the_closed_mode_is_allowed_more_because_we_cannot_read_it(client):
    from app.main import (
        DEFAULT_CLOSED_FILE_MAX_BYTES,
        DEFAULT_OPEN_FILE_MAX_BYTES,
        chunks_for,
        closed_file_ceiling,
    )

    plain = DEFAULT_OPEN_FILE_MAX_BYTES + 1
    data_chunks = chunks_for(plain)
    accepted = client.post(
        "/api/files",
        json={
            "enc": "aes-gcm-file-v1",
            "plain": plain,
            "size": closed_file_ceiling(plain, data_chunks),
            "chunks": data_chunks + 1,
        },
    )
    assert accepted.status_code == 201, "over the open plank, under the closed one"

    over = DEFAULT_CLOSED_FILE_MAX_BYTES + 1
    refused = client.post(
        "/api/files",
        json={
            "enc": "aes-gcm-file-v1",
            "plain": over,
            "size": over,
            "chunks": chunks_for(over) + 1,
        },
    )
    assert refused.status_code == 413
    assert str(DEFAULT_CLOSED_FILE_MAX_BYTES) in refused.json()["detail"]


def test_a_closed_sender_cannot_smuggle_extra_bytes_past_the_limit(client):
    from app.main import chunks_for, closed_file_ceiling

    plain = 1024
    data_chunks = chunks_for(plain)
    inflated = closed_file_ceiling(plain, data_chunks) + 1

    refused = client.post(
        "/api/files",
        json={
            "enc": "aes-gcm-file-v1",
            "plain": plain,
            "size": inflated,
            "chunks": data_chunks + 1,
        },
    )
    assert refused.status_code == 400


def test_an_unknown_file_encryption_scheme_is_refused(client):
    refused = client.post(
        "/api/files", json={"enc": "rot13", "size": 8, "chunks": 1, "plain": 8}
    )
    assert refused.status_code == 400
    assert refused.json()["detail"] == "unknown encryption scheme"


def test_a_closed_file_keeps_no_name_even_when_one_is_offered(client):
    """A file's name is content; in the closed mode we do not get to have it."""
    from app.main import chunks_for, closed_file_ceiling

    plain = 16
    size = closed_file_ceiling(plain, chunks_for(plain))
    header, sealed = b"h" * (size - plain - 16), b"c" * (plain + 16)
    code = send(
        client,
        b"",
        pieces=[header, sealed],
        enc="aes-gcm-file-v1",
        plain=plain,
        size=size,
        chunks=chunks_for(plain) + 1,
        name="leaked.txt",
        mime="text/plain",
    )

    body = take(client, code).json()
    assert body["enc"] == "aes-gcm-file-v1"
    assert "name" not in body
    assert "mime" not in body


@pytest.mark.parametrize(
    "payload",
    [
        {"size": 0, "chunks": 1},
        {"size": -5, "chunks": 1},
        {"size": "8", "chunks": 1},
        {"size": 8, "chunks": 0},
        {"size": 8, "chunks": 4},  # not the fixed chunking
        {"size": True, "chunks": 1},
    ],
)
def test_absurd_upload_metadata_is_refused(client, payload):
    assert client.post("/api/files", json=payload).status_code == 400


def test_chunks_must_arrive_in_order(client):
    started = client.post("/api/files", json={"size": 8, "chunks": 1}).json()
    upload = started["upload"]

    assert client.put(f"/api/files/{upload}/1", content=b"abcdefgh").status_code == 400
    assert client.put(f"/api/files/{upload}/0", content=b"abcdefgh").status_code == 204


def test_a_chunk_for_an_unknown_upload_looks_like_any_other_miss(client):
    response = client.put("/api/files/2abcdefghijkmn/0", content=b"x")
    assert response.status_code == 404
    assert response.json() == {"detail": "no such throw"}


def test_more_bytes_than_declared_are_refused(client):
    upload = client.post("/api/files", json={"size": 4, "chunks": 1}).json()["upload"]
    assert client.put(f"/api/files/{upload}/0", content=b"far too long").status_code == 400


def test_a_filename_is_reduced_to_a_bare_name(client):
    code = send(client, b"payload", name="../../etc/passwd")
    assert take(client, code).json()["name"] == "passwd"


def test_a_junk_mime_is_dropped_rather_than_echoed(client):
    code = send(client, b"payload", name="x.bin", mime="not a mime type")
    assert "mime" not in take(client, code).json()


def test_the_upload_limit_holds_the_disk_without_touching_the_read_path(limited):
    client = limited(max_concurrent=2, max_bytes_per_window=10**9)
    first = client.post("/api/files", json={"size": 1024, "chunks": 1})
    second = client.post("/api/files", json={"size": 1024, "chunks": 1})
    third = client.post("/api/files", json={"size": 1024, "chunks": 1})

    assert first.status_code == 201
    assert second.status_code == 201
    assert third.status_code == 429
    assert client.app.state.files.total_bytes() == 2048, "the refused one reserved nothing"

    # The read path is untouched: an honest receiver behind the same NAT still
    # reads their throw, and a miss is still a miss.
    text = client.post("/api/throws", json={"text": "unaffected"}).json()["code"]
    assert take(client, text).json() == {"text": "unaffected"}
    assert take(client, "red-fox").status_code == 404


def test_a_finished_upload_gives_its_slot_back(limited):
    client = limited(max_concurrent=1, max_bytes_per_window=10**9)
    send(client, b"first")
    assert send(client, b"second"), "the slot came back with the finished upload"


def test_a_done_on_an_unknown_upload_hands_out_no_slot(limited):
    client = limited(max_concurrent=1, max_bytes_per_window=10**9)
    assert client.post("/api/files", json={"size": 8, "chunks": 1}).status_code == 201
    assert client.post("/api/files/2abcdefghijkmn/done").status_code == 404
    assert client.post("/api/files", json={"size": 8, "chunks": 1}).status_code == 429


def test_the_bytes_per_minute_limit_stops_a_flood_of_reservations(limited):
    client = limited(max_concurrent=100, max_bytes_per_window=4096)
    assert client.post("/api/files", json={"size": 4096, "chunks": 1}).status_code == 201
    assert client.post("/api/files", json={"size": 1, "chunks": 1}).status_code == 429


def test_a_full_disk_answers_busy_rather_than_failing(tmp_path):
    store = FileStore(tmp_path / "throws", max_total_bytes=1024)
    with TestClient(create_app(TEST_SETTINGS, files=store)) as client:
        assert client.post("/api/files", json={"size": 1024, "chunks": 1}).status_code == 201
        busy = client.post("/api/files", json={"size": 1024, "chunks": 1})

    assert busy.status_code == 503
    assert "busy" in busy.json()["detail"]


def test_a_file_creation_is_logged_by_shape_never_by_name(client, capsys):
    capsys.readouterr()
    send(client, b"x" * 50, name="passport-scan.pdf")

    line = capsys.readouterr().out.strip()
    assert "event=created" in line and "kind=file" in line and "mode=open" in line
    assert "passport" not in line


# --- the gates ---------------------------------------------------------------
#
# Two of stage two's four gates are things a test can hold shut for good; the
# other two (50 MB across real networks, and the demo) are watched with a
# stopwatch and cannot live here. These are the two that can.


def test_a_bot_walking_the_code_space_never_reaches_an_open_file(client):
    """Gate: an enumerator gets nothing, and the honest throw is untouched."""
    code = put_file(client, b"somebody's passport scan", name="scan.jpg")
    grant_url = None

    # Every code in the space is two words; the bot has the same handle the
    # receiver has and nothing else.
    for guess in ("red-fox", "blue-cat", "basted-lily", "salty-dog", "wild-boar"):
        if guess == code:
            continue
        response = take(client, guess)
        assert response.status_code == 404
        assert response.json() == {"detail": "no such throw"}

    # Nor can it skip the code and go for the bytes: the ticket space is not
    # reachable by hand, and a wrong one opens nothing.
    for ticket in ("2abcdefghijkmn", "3zzzzzzzzzzzzz"):
        assert client.get(f"/api/files/t/{ticket}").status_code == 404

    # And the file is still there for the person who has the code.
    grant_url = take(client, code).json()["url"]
    assert client.get(grant_url).content == b"somebody's passport scan"


def test_a_flood_of_uploads_hits_the_limit_before_it_hits_the_disk(limited, tmp_path):
    """Gate: the disk holds under a flood, and an honest throw still lands."""
    client = limited(max_concurrent=2, max_bytes_per_window=4 * 1024 * 1024)

    accepted = 0
    for _ in range(50):
        response = client.post("/api/files", json={"size": 1024 * 1024, "chunks": 1})
        if response.status_code == 201:
            accepted += 1
        else:
            assert response.status_code == 429

    assert accepted <= 4, "the flood was stopped by the limit, not by the disk"
    assert client.app.state.files.total_bytes() <= 4 * 1024 * 1024

    # The honest sender in the middle of all this: a text throw still crosses,
    # and so does a read. The upload brake never touches the read path.
    code = client.post("/api/throws", json={"text": "still working"}).json()["code"]
    assert take(client, code).json() == {"text": "still working"}
