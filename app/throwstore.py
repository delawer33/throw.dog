"""In-memory store of throws: write once, read once, then gone.

Pure module: no framework, no logging of throw content.

Everything that makes a throw a throw lives here — the time-to-live, the
single-read guarantee, sweeping the dead, and picking a code nobody is
currently using. The clock is injected so tests never sleep.

Thread safety matters: uvicorn runs sync handlers in a threadpool, so two
readers of the same code can land at the same instant. "Read exactly once"
is the whole product, so the take is done under a lock.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, NamedTuple

from app.closedaddress import generate as generate_address
from app.codewords import generate as generate_code

DEFAULT_TTL_SECONDS: float = 600.0
_DEFAULT_CODE_ATTEMPTS = 50

#: Ceilings so a flood of throws cannot eat the box. The code space alone is
#: no ceiling: every code filled with a max-size throw would be gigabytes.
DEFAULT_MAX_ENTRIES = 10_000
DEFAULT_MAX_TOTAL_BYTES = 256 * 1024 * 1024


class OutOfCodes(RuntimeError):
    """Raised when no unused code could be found for a new throw."""


class StoreFull(RuntimeError):
    """Raised when the store is at its entry or memory ceiling."""


class Throw(NamedTuple):
    """What a reader gets back: the text, and whether it is ciphertext.

    The store never encrypts or decrypts anything and holds no key — it cannot,
    the key never leaves the two browsers. ``encrypted`` is carried, not
    interpreted: it is the receiving page's cue to reach for a key.
    """

    text: str
    encrypted: bool


@dataclass(frozen=True, slots=True)
class _Entry:
    text: str
    expires_at: float
    size_bytes: int
    encrypted: bool


class ThrowStore:
    """Holds throws until someone reads them, or until they rot.

    Args:
        ttl_seconds: how long an unread throw survives.
        clock: callable returning seconds as a float; monotonic by default so
            that wall-clock jumps cannot resurrect or kill throws early.
        code_generator: callable returning a candidate two-word code, used to
            address open throws.
        address_generator: callable returning a candidate closed address, used
            to address closed throws. A closed throw has no two-word code —
            see :mod:`app.closedaddress` for why the two spaces must not meet.
        code_attempts: how many candidates to try before giving up.
        max_entries: how many throws may be alive at once.
        max_total_bytes: how much throw text may be resident at once.
    """

    def __init__(
        self,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        code_generator: Callable[[], str] = generate_code,
        address_generator: Callable[[], str] = generate_address,
        code_attempts: int = _DEFAULT_CODE_ATTEMPTS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if code_attempts < 1:
            raise ValueError("code_attempts must be at least 1")
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        if max_total_bytes < 1:
            raise ValueError("max_total_bytes must be at least 1")
        self._ttl_seconds = float(ttl_seconds)
        self._clock = clock
        self._generate_code = code_generator
        self._generate_address = address_generator
        self._code_attempts = code_attempts
        self._max_entries = max_entries
        self._max_total_bytes = max_total_bytes
        self._lock = threading.Lock()
        self._entries: dict[str, _Entry] = {}
        self._total_bytes = 0

    @property
    def ttl_seconds(self) -> float:
        return self._ttl_seconds

    def put(self, text: str, *, encrypted: bool = False) -> str:
        """Store ``text`` and return the address that will fetch it back once.

        ``encrypted`` says the text is ciphertext the sender's browser produced;
        it is stored alongside and handed back untouched. It also decides the
        shape of the returned address: two words for an open throw, a closed
        address for a closed one — a closed throw has no words to dictate.

        The ceilings and the lifetime do not care about the mode: both kinds of
        throw share one space of live throws, and size is counted by what
        actually landed here (ciphertext, base64 and all).
        """
        now = self._clock()
        expires_at = now + self._ttl_seconds
        size_bytes = len(text.encode("utf-8"))
        pick = self._generate_address if encrypted else self._generate_code
        with self._lock:
            self._purge_expired(now)
            if len(self._entries) >= self._max_entries:
                raise StoreFull("too many live throws")
            if self._total_bytes + size_bytes > self._max_total_bytes:
                raise StoreFull("live throws would exceed the memory ceiling")
            for _ in range(self._code_attempts):
                code = pick()
                if code in self._entries:
                    continue
                self._entries[code] = _Entry(
                    text=text,
                    expires_at=expires_at,
                    size_bytes=size_bytes,
                    encrypted=encrypted,
                )
                self._total_bytes += size_bytes
                return code
        raise OutOfCodes("could not find an unused code")

    def take(self, code: str) -> Throw | None:
        """Remove and return the throw for ``code``, text and mode together.

        ``None`` for every kind of miss: never existed, expired, or already
        read. Callers must not be able to tell those apart.

        Handing the throw out *is* the read, in both modes. For a closed throw
        we cannot know whether the receiver's key worked — we never see the
        key — and waiting to be told would be a way to have a throw served
        twice by lying about the first attempt.
        """
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            entry = self._entries.pop(code, None)
            if entry is not None:
                self._total_bytes -= entry.size_bytes
        if entry is None:
            return None
        return Throw(text=entry.text, encrypted=entry.encrypted)

    def size(self) -> int:
        """Number of throws still alive (sweeps the dead on the way)."""
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            return len(self._entries)

    def total_bytes(self) -> int:
        """Bytes of throw text currently resident (sweeps the dead first)."""
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            return self._total_bytes

    def purge_expired(self) -> int:
        """Drop everything past its deadline; return how many died.

        Public because nobody may ever come back for an expired throw, and
        its plaintext must not sit in memory waiting for the next request.
        A caller (the app's lifespan) sweeps on a timer.
        """
        now = self._clock()
        with self._lock:
            before = len(self._entries)
            self._purge_expired(now)
            return before - len(self._entries)

    def _purge_expired(self, now: float) -> None:
        """Drop everything past its deadline. Caller holds the lock."""
        dead = [code for code, entry in self._entries.items() if entry.expires_at <= now]
        for code in dead:
            self._total_bytes -= self._entries[code].size_bytes
            del self._entries[code]
