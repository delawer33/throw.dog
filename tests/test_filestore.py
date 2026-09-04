import threading

import pytest

from app.closedaddress import is_closed_address
from app.codewords import normalize
from app.filestore import (
    BadChunk,
    FileStore,
    NoSuchUpload,
    OutOfCodes,
    StoreFull,
    UploadIncomplete,
)


class FakeClock:
    """A clock the test moves by hand, so nothing ever sleeps."""

    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def sequence(*codes: str):
    """A generator that hands out the given addresses in order."""
    remaining = list(codes)

    def generate() -> str:
        return remaining.pop(0)

    return generate


def make_store(tmp_path, **kwargs) -> FileStore:
    kwargs.setdefault("clock", FakeClock())
    return FileStore(tmp_path / "throws", **kwargs)


def upload(store: FileStore, payload: bytes, chunk_size: int = 8, **kwargs) -> str:
    """Push ``payload`` through the three steps and return the address."""
    chunks = [payload[i : i + chunk_size] for i in range(0, len(payload), chunk_size)]
    upload_id = store.begin(size=len(payload), chunks=len(chunks), **kwargs)
    for index, chunk in enumerate(chunks):
        store.write_chunk(upload_id, index, chunk)
    return store.finish(upload_id)


# --- the round trip ---------------------------------------------------------


def test_a_thrown_file_comes_back_under_its_code(tmp_path):
    store = make_store(tmp_path)
    code = upload(store, b"a file from the laptop", name="notes.txt", mime="text/plain")

    grant = store.take(code)
    assert grant is not None
    assert grant.size == len(b"a file from the laptop")
    assert grant.name == "notes.txt"
    assert grant.mime == "text/plain"

    held = store.checkout(grant.ticket)
    assert held.path.read_bytes() == b"a file from the laptop"


def test_an_open_throw_is_addressed_by_words_a_closed_one_by_an_address(tmp_path):
    store = make_store(tmp_path)
    assert normalize(upload(store, b"open bytes")) is not None
    assert is_closed_address(upload(store, b"closed bytes", encrypted=True))


def test_the_code_dies_the_moment_the_ticket_is_handed_out(tmp_path):
    store = make_store(tmp_path)
    code = upload(store, b"one receiver only")

    assert store.take(code) is not None
    assert store.take(code) is None


def test_a_ticket_outlives_the_code_that_bought_it(tmp_path):
    store = make_store(tmp_path)
    grant = store.take(upload(store, b"still downloading"))

    assert store.take("red-fox") is None, "the code is gone"
    assert store.checkout(grant.ticket) is not None, "the bytes are not"


def test_unknown_code_and_unknown_ticket_read_as_nothing(tmp_path):
    store = make_store(tmp_path)
    assert store.take("red-fox") is None
    assert store.checkout("2abcdefghijkmn") is None


def test_someone_elses_ticket_does_not_open_this_file(tmp_path):
    store = make_store(tmp_path)
    mine = store.take(upload(store, b"mine"))
    yours = store.take(upload(store, b"yours"))

    assert store.checkout(mine.ticket).path.read_bytes() == b"mine"
    assert store.checkout(yours.ticket).path.read_bytes() == b"yours"
    store.complete(mine.ticket)
    assert store.checkout(mine.ticket) is None
    assert store.checkout(yours.ticket) is not None


# --- the upload -------------------------------------------------------------


def test_an_upload_is_not_addressable_before_it_is_finished(tmp_path):
    store = make_store(tmp_path)
    upload_id = store.begin(size=4, chunks=1)

    assert store.take(upload_id) is None, "the upload id is not an address"
    assert store.size() == 0


def test_chunks_must_arrive_in_order(tmp_path):
    store = make_store(tmp_path)
    upload_id = store.begin(size=4, chunks=2)
    store.write_chunk(upload_id, 0, b"ab")

    with pytest.raises(BadChunk):
        store.write_chunk(upload_id, 0, b"cd")
    with pytest.raises(BadChunk):
        store.write_chunk(upload_id, 5, b"cd")


def test_more_bytes_than_declared_are_refused(tmp_path):
    store = make_store(tmp_path)
    upload_id = store.begin(size=4, chunks=1)

    with pytest.raises(BadChunk):
        store.write_chunk(upload_id, 0, b"abcde")


def test_a_short_upload_cannot_be_finished(tmp_path):
    store = make_store(tmp_path)
    upload_id = store.begin(size=8, chunks=2)
    store.write_chunk(upload_id, 0, b"abcd")

    with pytest.raises(UploadIncomplete):
        store.finish(upload_id)


def test_writing_to_an_unknown_upload_fails(tmp_path):
    store = make_store(tmp_path)
    with pytest.raises(NoSuchUpload):
        store.write_chunk("2abcdefghijkmn", 0, b"x")


def test_an_abandoned_upload_takes_its_bytes_with_it(tmp_path):
    store = make_store(tmp_path)
    upload_id = store.begin(size=4, chunks=1)
    store.write_chunk(upload_id, 0, b"abcd")

    assert store.abandon(upload_id) is True
    assert store.total_bytes() == 0
    assert list(store.root.iterdir()) == []
    assert store.abandon(upload_id) is False


def test_a_stalled_upload_is_swept(tmp_path):
    clock = FakeClock()
    store = make_store(tmp_path, clock=clock, upload_idle_seconds=120)
    upload_id = store.begin(size=8, chunks=2)
    store.write_chunk(upload_id, 0, b"abcd")

    clock.advance(119)
    assert store.uploads_in_flight() == 1

    clock.advance(2)
    assert store.purge_expired() == 1
    assert store.total_bytes() == 0
    assert list(store.root.iterdir()) == []
    with pytest.raises(NoSuchUpload):
        store.finish(upload_id)


# --- lifetimes --------------------------------------------------------------


def test_the_ttl_starts_when_the_file_has_fully_arrived(tmp_path):
    clock = FakeClock()
    store = make_store(tmp_path, clock=clock, ttl_seconds=600)
    upload_id = store.begin(size=8, chunks=2)
    store.write_chunk(upload_id, 0, b"abcd")
    clock.advance(300)  # a big file takes minutes to arrive
    store.write_chunk(upload_id, 1, b"efgh")
    code = store.finish(upload_id)

    clock.advance(599)
    assert store.size() == 1, "still alive, counted from the moment it landed"

    clock.advance(2)
    assert store.take(code) is None


def test_an_expired_throw_loses_its_bytes(tmp_path):
    clock = FakeClock()
    store = make_store(tmp_path, clock=clock, ttl_seconds=600)
    upload(store, b"nobody came")

    clock.advance(601)
    assert store.purge_expired() == 1
    assert store.total_bytes() == 0
    assert list(store.root.iterdir()) == []


def test_a_quiet_ticket_dies_and_a_busy_one_does_not(tmp_path):
    clock = FakeClock()
    store = make_store(tmp_path, clock=clock, ticket_idle_seconds=120)
    grant = store.take(upload(store, b"slow link"))

    clock.advance(100)
    assert store.touch(grant.ticket) is True
    clock.advance(100)
    assert store.checkout(grant.ticket) is not None, "activity keeps it alive"

    clock.advance(121)
    assert store.checkout(grant.ticket) is None
    assert list(store.root.iterdir()) == []


def test_a_ticket_survives_the_throws_own_ttl(tmp_path):
    clock = FakeClock()
    store = make_store(tmp_path, clock=clock, ttl_seconds=600, ticket_idle_seconds=120)
    grant = store.take(upload(store, b"started in time"))

    clock.advance(700)  # past the TTL, but the download is still moving
    assert store.touch(grant.ticket) is True
    assert store.checkout(grant.ticket).path.read_bytes() == b"started in time"


def test_completing_a_download_unlinks_the_file(tmp_path):
    store = make_store(tmp_path)
    grant = store.take(upload(store, b"delivered"))

    assert store.complete(grant.ticket) is True
    assert store.complete(grant.ticket) is False
    assert store.total_bytes() == 0
    assert list(store.root.iterdir()) == []


# --- ceilings ---------------------------------------------------------------


def test_the_entry_ceiling_counts_uploads_and_throws_together(tmp_path):
    store = make_store(tmp_path, max_entries=2)
    upload(store, b"first")
    store.begin(size=4, chunks=1)

    with pytest.raises(StoreFull):
        store.begin(size=4, chunks=1)


def test_bytes_are_reserved_before_they_are_written(tmp_path):
    store = make_store(tmp_path, max_total_bytes=100)
    store.begin(size=100, chunks=1)  # nothing written yet

    with pytest.raises(StoreFull):
        store.begin(size=1, chunks=1)
    assert store.total_bytes() == 100


def test_an_expired_throw_frees_room_for_the_next(tmp_path):
    clock = FakeClock()
    store = make_store(tmp_path, clock=clock, max_total_bytes=8, ttl_seconds=600)
    upload(store, b"12345678")

    with pytest.raises(StoreFull):
        store.begin(size=8, chunks=1)

    clock.advance(601)
    assert store.begin(size=8, chunks=1)


def test_absurd_metadata_is_refused_before_any_file_is_made(tmp_path):
    store = make_store(tmp_path)
    for kwargs in (
        {"size": 0, "chunks": 1},
        {"size": 10, "chunks": 0},
        {"size": 10, "chunks": 11},  # chunks smaller than a byte
        {"size": 10**12, "chunks": 1},  # one chunk cannot hold it
    ):
        with pytest.raises(ValueError):
            store.begin(**kwargs)
    assert list(store.root.iterdir()) == []


# --- the disk ---------------------------------------------------------------


def test_no_address_is_readable_from_the_directory(tmp_path):
    store = make_store(tmp_path)
    code = upload(store, b"bytes")
    grant = store.take(code)

    names = [entry.name for entry in store.root.iterdir()]
    assert len(names) == 1
    assert code not in names[0]
    assert grant.ticket not in names[0]


def test_the_directory_is_emptied_on_startup(tmp_path):
    root = tmp_path / "throws"
    root.mkdir()
    (root / "left-over").write_bytes(b"from a previous life")

    store = FileStore(root, clock=FakeClock())

    assert list(store.root.iterdir()) == []
    assert store.size() == 0
    assert store.total_bytes() == 0


# --- addresses --------------------------------------------------------------


def test_a_code_already_live_elsewhere_is_skipped(tmp_path):
    """Text and file throws share one space of two-word codes."""
    taken = {"red-fox"}
    store = make_store(
        tmp_path,
        code_generator=sequence("red-fox", "blue-cat"),
        is_reserved=taken.__contains__,
    )
    assert upload(store, b"bytes") == "blue-cat"


def test_running_out_of_codes_is_an_error_not_a_collision(tmp_path):
    store = make_store(
        tmp_path,
        code_generator=sequence("red-fox", "red-fox", "red-fox"),
        code_attempts=2,
    )
    upload(store, b"first")
    upload_id = store.begin(size=5, chunks=1)
    store.write_chunk(upload_id, 0, b"again")

    with pytest.raises(OutOfCodes):
        store.finish(upload_id)


# --- concurrency ------------------------------------------------------------


def test_only_one_of_many_racing_receivers_gets_the_ticket(tmp_path):
    store = make_store(tmp_path)
    code = upload(store, b"contested")
    start = threading.Barrier(8)
    grants = []

    def race() -> None:
        start.wait()
        grant = store.take(code)
        if grant is not None:
            grants.append(grant)

    threads = [threading.Thread(target=race) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(grants) == 1
