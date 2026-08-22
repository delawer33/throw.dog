import threading

import pytest

from app.throwstore import OutOfCodes, StoreFull, ThrowStore


class FakeClock:
    """A clock the test moves by hand, so nothing ever sleeps."""

    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def sequence(*codes: str):
    """A code generator that hands out the given codes in order."""
    remaining = list(codes)

    def generate() -> str:
        return remaining.pop(0)

    return generate


def test_a_thrown_text_comes_back_under_its_code():
    store = ThrowStore(clock=FakeClock())
    code = store.put("hello from the laptop")
    assert store.take(code) == "hello from the laptop"


def test_a_throw_can_only_be_read_once():
    store = ThrowStore(clock=FakeClock())
    code = store.put("secret")
    assert store.take(code) == "secret"
    assert store.take(code) is None


def test_unknown_code_reads_as_nothing():
    store = ThrowStore(clock=FakeClock())
    assert store.take("red-fox") is None


def test_a_throw_dies_when_its_ttl_runs_out():
    clock = FakeClock()
    store = ThrowStore(ttl_seconds=600, clock=clock)
    code = store.put("slow reader")

    clock.advance(599)
    assert store.size() == 1, "still alive one second before the deadline"

    clock.advance(2)
    assert store.take(code) is None


def test_expired_throws_are_swept_not_just_hidden():
    clock = FakeClock()
    store = ThrowStore(ttl_seconds=10, clock=clock)
    store.put("one")
    store.put("two")
    store.put("three")
    assert store.size() == 3

    clock.advance(11)
    store.put("fresh")
    assert store.size() == 1


def test_ttl_is_measured_from_the_throw_not_from_the_first_read():
    clock = FakeClock()
    store = ThrowStore(ttl_seconds=100, clock=clock)
    first = store.put("early")
    clock.advance(60)
    second = store.put("late")

    clock.advance(50)  # 110s for the first, 50s for the second
    assert store.take(first) is None
    assert store.take(second) == "late"


def test_a_taken_code_is_skipped_when_it_comes_up_again():
    store = ThrowStore(clock=FakeClock(), code_generator=sequence("red-fox", "red-fox", "big-owl"))
    first = store.put("first")
    second = store.put("second")

    assert first == "red-fox"
    assert second == "big-owl", "the busy code was skipped, not overwritten"
    assert store.take("red-fox") == "first"
    assert store.take("big-owl") == "second"


def test_a_freed_code_can_be_handed_out_again():
    store = ThrowStore(clock=FakeClock(), code_generator=sequence("red-fox", "red-fox"))
    code = store.put("first")
    assert store.take(code) == "first"
    assert store.put("second") == "red-fox"


def test_giving_up_rather_than_overwriting_a_live_throw():
    store = ThrowStore(
        clock=FakeClock(),
        code_generator=sequence("red-fox", "red-fox", "red-fox"),
        code_attempts=2,
    )
    store.put("precious")
    with pytest.raises(OutOfCodes):
        store.put("intruder")
    assert store.take("red-fox") == "precious"


def test_only_one_of_many_concurrent_readers_gets_the_text():
    store = ThrowStore(clock=FakeClock())
    code = store.put("exactly once")

    start = threading.Barrier(16)
    results: list[str | None] = []
    guard = threading.Lock()

    def reader() -> None:
        start.wait()
        value = store.take(code)
        with guard:
            results.append(value)

    threads = [threading.Thread(target=reader) for _ in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results.count("exactly once") == 1
    assert results.count(None) == 15


def test_rejects_nonsense_configuration():
    with pytest.raises(ValueError):
        ThrowStore(ttl_seconds=0)
    with pytest.raises(ValueError):
        ThrowStore(code_attempts=0)


def test_store_refuses_new_throws_past_the_entry_ceiling():
    store = ThrowStore(ttl_seconds=600, clock=FakeClock(), max_entries=2)

    store.put("one")
    store.put("two")

    with pytest.raises(StoreFull):
        store.put("three")


def test_store_refuses_new_throws_past_the_memory_ceiling():
    store = ThrowStore(ttl_seconds=600, clock=FakeClock(), max_total_bytes=10)

    store.put("x" * 8)

    with pytest.raises(StoreFull):
        store.put("x" * 8)


def test_reading_a_throw_frees_its_room():
    store = ThrowStore(ttl_seconds=600, clock=FakeClock(), max_total_bytes=10)
    code = store.put("x" * 8)

    assert store.total_bytes() == 8
    store.take(code)

    assert store.total_bytes() == 0
    store.put("x" * 8)  # room is back


def test_expired_throws_are_swept_without_anyone_asking_for_them():
    clock = FakeClock()
    store = ThrowStore(ttl_seconds=60, clock=clock)
    for _ in range(5):
        store.put("secret")

    clock.advance(600)
    swept = store.purge_expired()

    assert swept == 5
    assert store.size() == 0
    assert store.total_bytes() == 0
