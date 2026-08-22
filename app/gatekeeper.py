"""Admission control for the read path — pure logic, no I/O.

The code space is a lottery a bot can brute-force: without a gate, a scraper
walks the whole space inside one TTL and passively collects other people's
secrets (see model/11-security-abuse.md, threat #1). This module is the gate.

It answers one question — *may this IP read right now?* — and remembers the
outcome of each read so the answer tightens under abuse. Two brakes:

* **Per-IP miss budget.** A sliding window of *misses* per IP. Guessing burns
  the budget; over budget the caller is told to tarpit. Successful takes are
  never counted — a legitimate miss is a rare typo, not an attack.
* **Global miss flood.** A botnet spreads guesses over hundreds of IPs so no
  single IP ever trips its budget. When misses across *all* IPs flood a short
  window, a global tarpit engages and every read is stalled until the flood
  drains — insurance, not a scalpel.

Pure by design: the clock is injected and nothing here sleeps. The HTTP layer
executes the delay; this module only decides. State is in-process memory — a
single instance is the accepted stage architecture.
"""

from __future__ import annotations

import time
from collections import deque
from enum import Enum
from typing import Callable, Deque

DEFAULT_WINDOW_SECONDS: float = 60.0
DEFAULT_MISS_BUDGET: int = 10
DEFAULT_GLOBAL_WINDOW_SECONDS: float = 60.0
DEFAULT_GLOBAL_MISS_THRESHOLD: int = 100
DEFAULT_MAX_TRACKED_IPS: int = 4096


class ReadOutcome(Enum):
    """What a read actually did, once the store has spoken."""

    HIT = "hit"
    MISS = "miss"


class Gatekeeper:
    """Decides whether a read is allowed, and learns from what happens.

    Args:
        window_seconds: length of the per-IP sliding window of misses.
        miss_budget: how many misses one IP may accumulate in that window
            before it is told to tarpit.
        global_window_seconds: length of the global sliding window of misses.
        global_miss_threshold: how many misses across all IPs, inside the
            global window, engage the global tarpit.
        max_tracked_ips: soft ceiling on distinct IPs held in per-IP state.
            Once the map grows past this, a sweep reclaims every bucket whose
            window has fully drained — so a spray botnet of one-shot IPs cannot
            grow the map without bound and turn the gate into a memory-DoS.
        clock: callable returning seconds as a float; monotonic by default so
            wall-clock jumps cannot forgive or condemn an IP early.
    """

    def __init__(
        self,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        miss_budget: int = DEFAULT_MISS_BUDGET,
        global_window_seconds: float = DEFAULT_GLOBAL_WINDOW_SECONDS,
        global_miss_threshold: int = DEFAULT_GLOBAL_MISS_THRESHOLD,
        max_tracked_ips: int = DEFAULT_MAX_TRACKED_IPS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        if miss_budget < 1:
            raise ValueError("miss_budget must be at least 1")
        if global_window_seconds <= 0:
            raise ValueError("global_window_seconds must be positive")
        if global_miss_threshold < 1:
            raise ValueError("global_miss_threshold must be at least 1")
        if max_tracked_ips < 1:
            raise ValueError("max_tracked_ips must be at least 1")
        self._window_seconds = float(window_seconds)
        self._miss_budget = miss_budget
        self._global_window_seconds = float(global_window_seconds)
        self._global_miss_threshold = global_miss_threshold
        self._max_tracked_ips = max_tracked_ips
        self._clock = clock
        self._ip_misses: dict[str, Deque[float]] = {}
        self._global_misses: Deque[float] = deque()

    def allow(self, ip: str) -> bool:
        """True if ``ip`` may read now; False means the caller should tarpit.

        A global miss flood shuts the door on everyone; otherwise an IP is
        turned away only once its own misses fill the budget for the window.
        """
        now = self._clock()
        self._prune_global(now)
        self._sweep_ips_if_crowded(now)
        if len(self._global_misses) >= self._global_miss_threshold:
            return False
        recent = self._ip_misses.get(ip)
        if recent is None:
            return True
        self._prune_ip(ip, recent, now)
        return len(recent) < self._miss_budget

    def record(self, ip: str, outcome: ReadOutcome) -> None:
        """Remember what a completed read did. Hits are free; misses count."""
        if outcome is ReadOutcome.HIT:
            return
        now = self._clock()
        recent = self._ip_misses.get(ip)
        if recent is None:
            recent = deque()
            self._ip_misses[ip] = recent
        recent.append(now)
        self._prune_ip(ip, recent, now)
        self._global_misses.append(now)
        self._prune_global(now)
        self._sweep_ips_if_crowded(now)

    def _prune_ip(self, ip: str, recent: Deque[float], now: float) -> None:
        """Drop this IP's misses that have aged out of the window."""
        cutoff = now - self._window_seconds
        while recent and recent[0] <= cutoff:
            recent.popleft()
        if not recent:
            # No stale one-entry deques left lying around per IP forever.
            del self._ip_misses[ip]

    def _sweep_ips_if_crowded(self, now: float) -> None:
        """Reclaim fully-drained per-IP buckets once the map is crowded.

        A spray botnet leaves a one-shot bucket per source IP that ``record``
        alone never revisits, so those buckets would pile up forever. This
        sweep — O(tracked IPs), and only when the map exceeds its ceiling —
        drops every bucket whose newest miss has already aged out of the
        window, bounding memory to genuinely active IPs.
        """
        if len(self._ip_misses) <= self._max_tracked_ips:
            return
        cutoff = now - self._window_seconds
        stale = [
            ip
            for ip, recent in self._ip_misses.items()
            if not recent or recent[-1] <= cutoff
        ]
        for ip in stale:
            del self._ip_misses[ip]

    def _prune_global(self, now: float) -> None:
        """Drop global misses that have aged out of the global window."""
        cutoff = now - self._global_window_seconds
        misses = self._global_misses
        while misses and misses[0] <= cutoff:
            misses.popleft()
