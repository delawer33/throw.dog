"""Files thrown through the relay: metadata in memory, bytes on the volume.

Pure module in the same sense as :mod:`app.throwstore` — no framework, no
logging, an injected clock — except that it owns a directory. It is deliberately
*not* an extension of ``ThrowStore``: a text throw is a string that arrives in
one request, a file is a multi-request upload with a physical duration, and
folding the second into the first would make both harder to read.

Three lifetimes live here, and they are three because a file takes minutes:

* **The upload.** Chunks arrive in order and are appended. Nothing is
  addressable yet — handing out a code before the bytes landed would send the
  receiver to a half-empty throw. An upload that stalls is swept.
* **The throw.** Created by :meth:`finish`; this is where the TTL starts, not
  at the first byte. Addressed by a code (open) or a closed address (closed),
  exactly like a text throw, and taken exactly once.
* **The ticket.** What :meth:`take` hands back in place of the bytes. The code
  dies at that moment — one throw, one receiver — while the ticket survives a
  dropped connection and a resumed download for a short idle window. See
  ``docs/adr/0005-fayly-cherez-relei.md``: dying on the first byte loses
  50 MB files on mobile networks, dying only after full delivery lets a bot
  hold an open file alive for the whole TTL by never finishing.

Nothing secret is written to disk. The on-disk name of a file is a digest of
its upload id, so neither the code, nor the closed address, nor the ticket can
be read out of a directory listing. The directory is wiped on startup: a
restart kills every throw, and that is the feature.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, NamedTuple

from app.closedaddress import generate as generate_address
from app.codewords import generate as generate_code

DEFAULT_TTL_SECONDS: float = 600.0

#: How long a ticket survives with nothing happening on it. Long enough to
#: outlive a lift, a tunnel or a handover between networks; short enough that a
#: bot which opens the connection and goes quiet cannot park on a file.
DEFAULT_TICKET_IDLE_SECONDS: float = 120.0

#: How long a half-finished upload is kept before it is swept. The sender's tab
#: is gone or the network died; either way nobody will ever finish it.
DEFAULT_UPLOAD_IDLE_SECONDS: float = 120.0

#: Chunk size the client uploads in. Fixed because Cloudflare's free plan cuts a
#: request body at 100 MB — chunking is what makes the largest allowed file
#: possible at all, not a nicety.
CHUNK_BYTES: int = 4 * 1024 * 1024

#: The most one chunk may weigh on the wire. A closed chunk is its plaintext
#: plus a GCM tag, and the closed header chunk is small but not empty, so the
#: ceiling is the chunk size plus room for that overhead — not an exact equality.
MAX_CHUNK_BYTES: int = CHUNK_BYTES + 64 * 1024

#: Ceilings so a flood of uploads cannot eat the box. Bytes are counted as
#: *declared* size and reserved when the upload starts: a thousand uploads that
#: each announce 100 MB must be refused before they write, not after.
DEFAULT_MAX_ENTRIES = 200
DEFAULT_MAX_TOTAL_BYTES = 4 * 1024 * 1024 * 1024

_DEFAULT_CODE_ATTEMPTS = 50
_DEFAULT_TICKET_ATTEMPTS = 50


class OutOfCodes(RuntimeError):
    """Raised when no unused code could be found for a finished upload."""


class StoreFull(RuntimeError):
    """Raised when the store is at its entry or disk ceiling."""


class NoSuchUpload(KeyError):
    """Raised when an upload id is unknown, finished, or already swept."""


class BadChunk(ValueError):
    """Raised when a chunk arrives out of order, too big, or past the size."""


class UploadIncomplete(ValueError):
    """Raised when ``done`` arrives before all the declared bytes did."""


class Grant(NamedTuple):
    """What a receiver gets in exchange for a code: a ticket, not the bytes.

    ``name`` and ``mime`` are present only for an open throw. In the closed
    mode they are inside the ciphertext, because a file's name is content too
    and we do not get to know it.
    """

    ticket: str
    size: int
    encrypted: bool
    name: str | None
    mime: str | None
    enc: str | None


class Checkout(NamedTuple):
    """An open ticket: where the bytes are and how many of them there are."""

    path: Path
    size: int
    encrypted: bool
    name: str | None
    mime: str | None


@dataclass(slots=True)
class _Upload:
    upload_id: str
    path: Path
    encrypted: bool
    declared_size: int
    chunks: int
    name: str | None
    mime: str | None
    enc: str | None
    touched_at: float
    received_bytes: int = 0
    next_chunk: int = 0
    #: Serialises writes to this one file. Per-upload, so two senders never
    #: wait on each other — only a client racing itself does.
    writing: threading.Lock = field(default_factory=threading.Lock)


@dataclass(slots=True)
class _File:
    path: Path
    size: int
    encrypted: bool
    name: str | None
    mime: str | None
    enc: str | None
    expires_at: float


@dataclass(slots=True)
class _Ticket:
    path: Path
    size: int
    encrypted: bool
    name: str | None
    mime: str | None
    #: A taken ticket ignores the throw's TTL: a download that started before
    #: the deadline is allowed to finish after it. What kills it is silence.
    idle_until: float


class FileStore:
    """Holds uploads, live file throws and open tickets.

    Args:
        root: directory the bytes live in. Wiped on construction — a restart
            is meant to lose everything.
        ttl_seconds: how long a finished throw survives unread.
        ticket_idle_seconds: how long a ticket survives without activity.
        upload_idle_seconds: how long a stalled upload is kept.
        clock: seconds as a float; monotonic by default so a wall-clock jump
            cannot resurrect a throw or kill one early.
        code_generator: candidate two-word codes for open throws.
        address_generator: candidate closed addresses, and tickets — the same
            space by construction, never typed by hand either way.
        is_reserved: asks the *other* store whether a candidate code is already
            in use. Text throws and file throws share one address space (a
            receiver types two words and does not know which kind is behind
            them), so each store has to be able to see the other's live codes.
        max_entries: how many uploads and throws may be alive at once.
        max_total_bytes: how many declared bytes may be reserved at once.
    """

    def __init__(
        self,
        root: str | os.PathLike[str],
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        ticket_idle_seconds: float = DEFAULT_TICKET_IDLE_SECONDS,
        upload_idle_seconds: float = DEFAULT_UPLOAD_IDLE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        code_generator: Callable[[], str] = generate_code,
        address_generator: Callable[[], str] = generate_address,
        is_reserved: Callable[[str], bool] | None = None,
        code_attempts: int = _DEFAULT_CODE_ATTEMPTS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if ticket_idle_seconds <= 0:
            raise ValueError("ticket_idle_seconds must be positive")
        if upload_idle_seconds <= 0:
            raise ValueError("upload_idle_seconds must be positive")
        if code_attempts < 1:
            raise ValueError("code_attempts must be at least 1")
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        if max_total_bytes < 1:
            raise ValueError("max_total_bytes must be at least 1")
        self._root = Path(root)
        self._ttl_seconds = float(ttl_seconds)
        self._ticket_idle_seconds = float(ticket_idle_seconds)
        self._upload_idle_seconds = float(upload_idle_seconds)
        self._clock = clock
        self._generate_code = code_generator
        self._generate_address = address_generator
        self._is_reserved = is_reserved or (lambda _code: False)
        self._code_attempts = code_attempts
        self._max_entries = max_entries
        self._max_total_bytes = max_total_bytes
        self._lock = threading.Lock()
        self._uploads: dict[str, _Upload] = {}
        self._entries: dict[str, _File] = {}
        self._tickets: dict[str, _Ticket] = {}
        self._reserved_bytes = 0
        #: Paths whose entry is already forgotten but whose bytes are still
        #: there. Filled under the lock, emptied outside it: a slow filesystem
        #: must never stall a request that only wanted to read a dict.
        self._doomed: list[Path] = []
        self._prepare_root()

    # -- properties ---------------------------------------------------------

    @property
    def ttl_seconds(self) -> float:
        return self._ttl_seconds

    @property
    def root(self) -> Path:
        return self._root

    # -- upload -------------------------------------------------------------

    def begin(
        self,
        *,
        size: int,
        chunks: int,
        encrypted: bool = False,
        name: str | None = None,
        mime: str | None = None,
        enc: str | None = None,
    ) -> str:
        """Reserve room for ``size`` bytes and return the upload id.

        ``size`` is what will actually travel the wire, ciphertext expansion
        and all; the mode's human-visible limit is checked a layer up, in the
        same units the sender sees. Nothing here is addressable yet.
        """
        if size < 1:
            raise ValueError("size must be positive")
        if chunks < 1:
            raise ValueError("chunks must be positive")
        if chunks > size:
            raise ValueError("chunks cannot exceed size")
        if chunks * MAX_CHUNK_BYTES < size:
            raise ValueError("chunks too few for the declared size")
        now = self._clock()
        upload_id = self._generate_address()
        path = self._path_for(upload_id)
        with self._lock:
            self._purge_expired(now)
            if len(self._uploads) + len(self._entries) >= self._max_entries:
                raise StoreFull("too many live throws")
            if self._reserved_bytes + size > self._max_total_bytes:
                raise StoreFull("live throws would exceed the disk ceiling")
            self._uploads[upload_id] = _Upload(
                upload_id=upload_id,
                path=path,
                encrypted=encrypted,
                declared_size=size,
                chunks=chunks,
                name=name,
                mime=mime,
                enc=enc,
                touched_at=now,
            )
            self._reserved_bytes += size
        self._drain()
        # Create the file empty and outside the lock: from here on this path
        # belongs to this upload and to nothing else.
        path.touch()
        return upload_id

    def write_chunk(self, upload_id: str, index: int, data: bytes) -> int:
        """Append chunk ``index`` and return how many bytes have landed.

        Strictly in order. Out of order means the client and the file on disk
        disagree about what is in it, and there is no repair worth writing:
        the upload is not addressable, so the honest answer is to fail and let
        the sender start again.
        """
        now = self._clock()
        with self._lock:
            upload = self._uploads.get(upload_id)
            if upload is None:
                raise NoSuchUpload(upload_id)
            if index != upload.next_chunk:
                raise BadChunk(f"expected chunk {upload.next_chunk}, got {index}")
            if index >= upload.chunks:
                raise BadChunk("more chunks than were declared")
            if len(data) > MAX_CHUNK_BYTES:
                raise BadChunk("chunk is too big")
            if upload.received_bytes + len(data) > upload.declared_size:
                raise BadChunk("more bytes than were declared")
            writing = upload.writing
            upload.touched_at = now
        with writing:
            with open(upload.path, "ab") as sink:
                sink.write(data)
            with self._lock:
                # Re-check: the sweeper may have dropped the upload (and its
                # file) while this chunk was in flight.
                if self._uploads.get(upload_id) is not upload:
                    raise NoSuchUpload(upload_id)
                upload.received_bytes += len(data)
                upload.next_chunk += 1
                upload.touched_at = self._clock()
                return upload.received_bytes

    def finish(self, upload_id: str) -> str:
        """Turn a completed upload into a live throw and return its address.

        This is where the throw is born and where the TTL starts — measured
        from the moment the file is fully here, never from the first byte, or
        a 100 MB upload would arrive already half-dead.
        """
        now = self._clock()
        expires_at = now + self._ttl_seconds
        with self._lock:
            upload = self._uploads.get(upload_id)
            if upload is None:
                raise NoSuchUpload(upload_id)
            if upload.received_bytes != upload.declared_size:
                raise UploadIncomplete("not all declared bytes arrived")
            if upload.next_chunk != upload.chunks:
                raise UploadIncomplete("not all declared chunks arrived")
            pick = self._generate_address if upload.encrypted else self._generate_code
            for _ in range(self._code_attempts):
                code = pick()
                if code in self._entries or self._is_reserved(code):
                    continue
                del self._uploads[upload_id]
                self._entries[code] = _File(
                    path=upload.path,
                    size=upload.declared_size,
                    encrypted=upload.encrypted,
                    name=upload.name,
                    mime=upload.mime,
                    enc=upload.enc,
                    expires_at=expires_at,
                )
                return code
        raise OutOfCodes("could not find an unused code")

    def abandon(self, upload_id: str) -> bool:
        """Drop an unfinished upload and its bytes. True if there was one."""
        with self._lock:
            upload = self._uploads.pop(upload_id, None)
            if upload is None:
                return False
            self._reserved_bytes -= upload.declared_size
        _unlink(upload.path)
        return True

    # -- take ---------------------------------------------------------------

    def take(self, code: str) -> Grant | None:
        """Kill the code and hand back a ticket for the bytes.

        ``None`` for every kind of miss — never existed, expired, already
        taken — so a caller cannot tell them apart. The code dies here, at the
        same instant it would for a text throw; what the receiver gets is a
        pass to the bytes, and the bytes then survive a dropped connection.
        """
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            # Popping the entry and minting the ticket happen under one lock:
            # in between, the file is in neither map, and a sweep that landed
            # there would find nothing to keep it alive.
            entry = self._entries.pop(code, None)
            if entry is not None:
                for _ in range(_DEFAULT_TICKET_ATTEMPTS):
                    ticket = self._generate_address()
                    if ticket not in self._tickets:
                        break
                else:  # pragma: no cover - 68 bits of space, 50 tries
                    # Put it back rather than lose the file: the code is still
                    # the only way to it, and nobody has been handed anything.
                    self._entries[code] = entry
                    raise OutOfCodes("could not find an unused ticket")
                self._tickets[ticket] = _Ticket(
                    path=entry.path,
                    size=entry.size,
                    encrypted=entry.encrypted,
                    name=entry.name,
                    mime=entry.mime,
                    idle_until=now + self._ticket_idle_seconds,
                )
        self._drain()
        if entry is None:
            return None
        return Grant(
            ticket=ticket,
            size=entry.size,
            encrypted=entry.encrypted,
            name=entry.name,
            mime=entry.mime,
            enc=entry.enc,
        )

    def checkout(self, ticket: str) -> Checkout | None:
        """Look up an open ticket and push its idle deadline back.

        Called at the start of every download and resume. ``None`` means the
        ticket never existed or went quiet long enough to be swept.
        """
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            held = self._tickets.get(ticket)
            if held is not None:
                held.idle_until = now + self._ticket_idle_seconds
        self._drain()
        if held is None:
            return None
        return Checkout(
            path=held.path,
            size=held.size,
            encrypted=held.encrypted,
            name=held.name,
            mime=held.mime,
        )

    def touch(self, ticket: str) -> bool:
        """Push a ticket's idle deadline back mid-transfer. False if gone.

        A 100 MB download over a slow link outlives the idle window on its own,
        so the streaming response says "still moving" as it goes.
        """
        now = self._clock()
        with self._lock:
            held = self._tickets.get(ticket)
            if held is None:
                return False
            held.idle_until = now + self._ticket_idle_seconds
            return True

    def complete(self, ticket: str) -> bool:
        """The receiver has the whole file: forget the ticket, unlink the bytes."""
        with self._lock:
            held = self._tickets.pop(ticket, None)
            if held is None:
                return False
            self._reserved_bytes -= held.size
        _unlink(held.path)
        return True

    # -- housekeeping -------------------------------------------------------

    def holds(self, code: str) -> bool:
        """Whether ``code`` addresses a live file throw.

        Read without the lock on purpose. Its only caller is the *other*
        store's code picker, which holds its own lock at the time; taking ours
        underneath it would give two locks two acquisition orders and, one day,
        a deadlock. A dict lookup is atomic here, and a candidate code that
        goes stale between this answer and its use is no worse than the race
        the picker already tolerates.
        """
        return code in self._entries

    def size(self) -> int:
        """Live throws (not uploads, not tickets); sweeps the dead first."""
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            counted = len(self._entries)
        self._drain()
        return counted

    def uploads_in_flight(self) -> int:
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            counted = len(self._uploads)
        self._drain()
        return counted

    def tickets_open(self) -> int:
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            counted = len(self._tickets)
        self._drain()
        return counted

    def total_bytes(self) -> int:
        """Declared bytes currently reserved on disk (sweeps the dead first)."""
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            counted = self._reserved_bytes
        self._drain()
        return counted

    def purge_expired(self) -> int:
        """Unlink everything past its deadline; return how many died.

        Public because nobody is coming back for an expired throw and its bytes
        must not sit on the volume waiting for the next request. The app's
        lifespan sweeps on a timer.
        """
        now = self._clock()
        with self._lock:
            died = self._purge_expired(now)
        self._drain()
        return died

    def _drain(self) -> None:
        """Unlink what the last sweep forgot. Caller must NOT hold the lock."""
        with self._lock:
            doomed, self._doomed = self._doomed, []
        for path in doomed:
            _unlink(path)

    def _purge_expired(self, now: float) -> int:
        """Forget everything past its deadline; return how many. Lock held.

        The bytes are queued for :meth:`_drain` rather than unlinked here, so
        every sweep — including the ones that happen on the way into an
        ordinary lookup — is a handful of dict operations and no disk.
        """
        doomed = self._doomed
        died = 0
        for code, entry in [
            item for item in self._entries.items() if item[1].expires_at <= now
        ]:
            del self._entries[code]
            self._reserved_bytes -= entry.size
            doomed.append(entry.path)
            died += 1
        for ticket, held in [
            item for item in self._tickets.items() if item[1].idle_until <= now
        ]:
            del self._tickets[ticket]
            self._reserved_bytes -= held.size
            doomed.append(held.path)
            died += 1
        stale_uploads = now - self._upload_idle_seconds
        for upload_id, upload in [
            item for item in self._uploads.items() if item[1].touched_at <= stale_uploads
        ]:
            del self._uploads[upload_id]
            self._reserved_bytes -= upload.declared_size
            doomed.append(upload.path)
            died += 1
        return died

    def _path_for(self, upload_id: str) -> Path:
        """Where an upload's bytes live: a digest, never the address itself.

        A directory listing is not a place to publish live addresses — not the
        upload id, and by extension not the code or ticket that will stand for
        it later. The digest is one-way and that is all it has to be; the
        address space is 68 random bits, so there is nothing here to guess.
        """
        digest = hashlib.sha256(upload_id.encode("utf-8")).hexdigest()
        return self._root / digest

    def _prepare_root(self) -> None:
        """Make the directory, and empty it if anything survived a restart.

        Restart-is-amnesia is the design, not an accident: the metadata that
        made those bytes reachable lived in RAM, so whatever is on disk now is
        unreachable by anyone, including us.
        """
        if self._root.exists():
            shutil.rmtree(self._root, ignore_errors=True)
        self._root.mkdir(parents=True, exist_ok=True)


def _unlink(path: Path) -> None:
    """Remove a file, tolerating its absence — the goal is that it is gone."""
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        # Nothing useful to do and nothing to log: the sweeper will pass again,
        # and a path we cannot delete is not a reason to fail a request.
        pass
