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
from typing import Callable

from app.codewords import generate as generate_code

DEFAULT_TTL_SECONDS: float = 600.0
_DEFAULT_CODE_ATTEMPTS = 50


class OutOfCodes(RuntimeError):
    """Raised when no unused code could be found for a new throw."""


@dataclass(frozen=True, slots=True)
class _Entry:
    text: str
    expires_at: float


class ThrowStore:
    """Holds throws until someone reads them, or until they rot.

    Args:
        ttl_seconds: how long an unread throw survives.
        clock: callable returning seconds as a float; monotonic by default so
            that wall-clock jumps cannot resurrect or kill throws early.
        code_generator: callable returning a candidate code.
        code_attempts: how many candidates to try before giving up.
    """

    def __init__(
        self,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        code_generator: Callable[[], str] = generate_code,
        code_attempts: int = _DEFAULT_CODE_ATTEMPTS,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if code_attempts < 1:
            raise ValueError("code_attempts must be at least 1")
        self._ttl_seconds = float(ttl_seconds)
        self._clock = clock
        self._generate_code = code_generator
        self._code_attempts = code_attempts
        self._lock = threading.Lock()
        self._entries: dict[str, _Entry] = {}

    @property
    def ttl_seconds(self) -> float:
        return self._ttl_seconds

    def put(self, text: str) -> str:
        """Store ``text`` and return the code that will fetch it back once."""
        now = self._clock()
        expires_at = now + self._ttl_seconds
        with self._lock:
            self._purge_expired(now)
            for _ in range(self._code_attempts):
                code = self._generate_code()
                if code in self._entries:
                    continue
                self._entries[code] = _Entry(text=text, expires_at=expires_at)
                return code
        raise OutOfCodes("could not find an unused code")

    def take(self, code: str) -> str | None:
        """Remove and return the throw for ``code``.

        ``None`` for every kind of miss: never existed, expired, or already
        read. Callers must not be able to tell those apart.
        """
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            entry = self._entries.pop(code, None)
        if entry is None:
            return None
        return entry.text

    def size(self) -> int:
        """Number of throws still alive (sweeps the dead on the way)."""
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            return len(self._entries)

    def _purge_expired(self, now: float) -> None:
        """Drop everything past its deadline. Caller holds the lock."""
        dead = [code for code, entry in self._entries.items() if entry.expires_at <= now]
        for code in dead:
            del self._entries[code]
