import pytest

from app.gatekeeper import Gatekeeper, ReadOutcome


class FakeClock:
    """A clock the test moves by hand, so nothing ever sleeps."""

    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def miss(gate: Gatekeeper, ip: str, times: int = 1) -> None:
    for _ in range(times):
        gate.record(ip, ReadOutcome.MISS)


def test_an_ip_within_its_miss_budget_is_allowed():
    gate = Gatekeeper(window_seconds=60, miss_budget=10, clock=FakeClock())
    miss(gate, "1.2.3.4", times=9)
    assert gate.allow("1.2.3.4") is True


def test_an_ip_over_its_miss_budget_is_tarpitted():
    gate = Gatekeeper(window_seconds=60, miss_budget=10, clock=FakeClock())
    miss(gate, "1.2.3.4", times=10)
    assert gate.allow("1.2.3.4") is False


def test_the_budget_is_per_ip():
    gate = Gatekeeper(window_seconds=60, miss_budget=10, clock=FakeClock())
    miss(gate, "1.2.3.4", times=10)
    assert gate.allow("1.2.3.4") is False
    assert gate.allow("5.6.7.8") is True


def test_an_ip_recovers_once_its_misses_age_out_of_the_window():
    clock = FakeClock()
    gate = Gatekeeper(window_seconds=60, miss_budget=10, clock=clock)
    miss(gate, "1.2.3.4", times=10)
    assert gate.allow("1.2.3.4") is False

    clock.advance(61)
    assert gate.allow("1.2.3.4") is True


def test_only_the_stale_part_of_the_window_ages_out():
    clock = FakeClock()
    gate = Gatekeeper(window_seconds=60, miss_budget=10, clock=clock)
    miss(gate, "1.2.3.4", times=6)
    clock.advance(40)
    miss(gate, "1.2.3.4", times=6)  # 12 total, but 6 are old
    assert gate.allow("1.2.3.4") is False

    clock.advance(21)  # the first six are now > 60s old; six recent remain
    assert gate.allow("1.2.3.4") is True


def test_hits_are_never_counted_against_the_budget():
    gate = Gatekeeper(window_seconds=60, miss_budget=10, clock=FakeClock())
    for _ in range(1000):
        gate.record("1.2.3.4", ReadOutcome.HIT)
    assert gate.allow("1.2.3.4") is True


def test_a_flood_of_misses_across_many_ips_engages_the_global_tarpit():
    gate = Gatekeeper(
        window_seconds=60,
        miss_budget=10,
        global_window_seconds=60,
        global_miss_threshold=100,
        clock=FakeClock(),
    )
    # 100 different IPs, one miss each: no IP trips its own budget...
    for n in range(100):
        miss(gate, f"10.0.0.{n}")
    # ...but a fresh, innocent IP is turned away all the same.
    assert gate.allow("192.168.0.1") is False


def test_the_global_tarpit_disengages_once_the_flood_drains():
    clock = FakeClock()
    gate = Gatekeeper(
        window_seconds=60,
        miss_budget=10,
        global_window_seconds=60,
        global_miss_threshold=100,
        clock=clock,
    )
    for n in range(100):
        miss(gate, f"10.0.0.{n}")
    assert gate.allow("192.168.0.1") is False

    clock.advance(61)
    assert gate.allow("192.168.0.1") is True


def test_below_the_global_threshold_leaves_innocent_ips_alone():
    gate = Gatekeeper(
        window_seconds=60,
        miss_budget=10,
        global_window_seconds=60,
        global_miss_threshold=100,
        clock=FakeClock(),
    )
    for n in range(99):
        miss(gate, f"10.0.0.{n}")
    assert gate.allow("192.168.0.1") is True


def test_idle_ip_buckets_are_reclaimed_once_their_windows_drain():
    # A spray botnet: many distinct IPs, one guess each, none ever returning.
    # Their buckets must not pile up in memory forever.
    clock = FakeClock()
    gate = Gatekeeper(window_seconds=60, max_tracked_ips=2, clock=clock)
    for n in range(50):
        miss(gate, f"10.0.0.{n}")
    assert len(gate._ip_misses) > gate._max_tracked_ips

    # Every window drains, then a single further operation sweeps the map.
    clock.advance(61)
    assert gate.allow("192.168.0.1") is True
    assert len(gate._ip_misses) == 0


def test_active_ip_buckets_survive_a_sweep():
    # The sweep must reclaim only fully-drained buckets, never an IP still
    # inside its window.
    clock = FakeClock()
    gate = Gatekeeper(window_seconds=60, max_tracked_ips=2, clock=clock)
    miss(gate, "1.2.3.4")  # goes stale before the sweep
    clock.advance(61)
    for n in range(50):  # a fresh spray that triggers the sweep
        miss(gate, f"10.0.0.{n}")

    assert "1.2.3.4" not in gate._ip_misses  # drained and reclaimed
    # ...but every IP still inside its window is left untouched.
    assert all(f"10.0.0.{n}" in gate._ip_misses for n in range(50))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"window_seconds": 0},
        {"miss_budget": 0},
        {"global_window_seconds": 0},
        {"global_miss_threshold": 0},
        {"max_tracked_ips": 0},
    ],
)
def test_nonsense_configuration_is_refused(kwargs):
    with pytest.raises(ValueError):
        Gatekeeper(**kwargs)
