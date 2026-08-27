"""HTTP surface for throw.dog — thin on purpose.

All the rules live in :mod:`app.codewords` and :mod:`app.throwstore`; this
module only translates them into requests, responses and one-line events.

Served by uvicorn as ``app.main:app`` (the actual command lives in the
container image, not here).
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import hmac
import json
import logging
import os
import secrets
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from app.closedaddress import is_closed_address
from app.codewords import normalize
from app.csp import FLOOR_POLICY
from app.gatekeeper import (
    DEFAULT_GLOBAL_MISS_THRESHOLD,
    DEFAULT_GLOBAL_WINDOW_SECONDS,
    DEFAULT_MAX_TRACKED_IPS,
    DEFAULT_MISS_BUDGET,
    DEFAULT_WINDOW_SECONDS,
    Gatekeeper,
    ReadOutcome,
)
from app.pages import (
    PRIVACY_PAGE,
    ROBOTS_TXT,
    TERMS_PAGE,
    closed_sender_page,
    csp_for,
    receiver_page,
    sender_page,
)
from app.throwstore import OutOfCodes, StoreFull, ThrowStore

DEFAULT_TTL_SECONDS = 600
DEFAULT_MAX_BYTES = 65536

DEFAULT_MISS_DELAY_MS = 1000
#: Extra delay added on TOP of the base miss delay when the gatekeeper says this
#: IP is over its miss-budget, or the global tarpit is engaged. Deliberately much
#: larger than the base miss delay so enumeration from abusive sources is slow,
#: while an honest reader (who holds a valid code, and so gets a HIT, never a
#: gated miss) is never affected.
DEFAULT_GATE_TARPIT_DELAY_MS = 4000
DEFAULT_SWEEP_INTERVAL_SECONDS = 60.0

#: Where Pro fake-door email captures are appended. Defaults to a file on the
#: docker-volume-mounted ``/data`` dir so the list survives container restarts;
#: override with ``THROW_PRO_EMAILS_PATH`` (tests point it at a tmp file).
DEFAULT_PRO_EMAILS_PATH = "/data/pro-emails.txt"

#: The most we will accept for a Pro-interest email. RFC 5321 caps an address at
#: 254 chars; anything longer is junk and never touches the file.
_MAX_EMAIL_LEN = 254

#: A Pro-interest request body is tiny — a single email in a JSON object. Cap the
#: bytes we read so the endpoint can't be used to buffer a flood.
_PRO_BODY_MAX_BYTES = 4096

#: Where free-form user feedback (the wish box in the Pro panel) is appended.
#: Same posture as the emails: docker-volume file, one line per record.
DEFAULT_FEEDBACK_PATH = "/data/feedback.txt"

#: The most feedback text we keep, in characters (the page enforces the same
#: cap via ``maxlength``), and the raw-body ceiling around it (UTF-8 + JSON
#: escaping can inflate 2000 chars several-fold).
_FEEDBACK_MAX_CHARS = 2000
_FEEDBACK_BODY_MAX_BYTES = 32768

#: Default header carrying the real client IP when we sit behind a trusted
#: proxy. Cloudflare's ``CF-Connecting-IP`` is always consulted first.
DEFAULT_FORWARDED_HEADER = "X-Forwarded-For"

#: How much raw body we tolerate around a max-size text. JSON escaping can
#: inflate the payload well past the text it carries, so the body ceiling is
#: generous — its job is to stop a 100 MB flood, not to police the text size.
_BODY_SLACK_FACTOR = 8
_BODY_SLACK_BYTES = 1024

# --- closed throws: the format, and what it costs in bytes ------------------

#: The one encryption format we carry. A version, not a free-form label: the
#: sender's browser and this server have to agree on the layout of the bytes
#: (12-byte IV, then AES-256-GCM ciphertext with its 16-byte tag, all base64),
#: and an unrecognised version means they do not. We never decrypt any of it —
#: this string is passed from one browser to the other, nothing more.
ENC_SCHEME = "aes-gcm-v1"

#: AES-GCM's authentication tag, and the IV that precedes the ciphertext. Used
#: only to convert between what the sender typed and what arrived here; the
#: server never touches either field.
_GCM_TAG_BYTES = 16
_GCM_IV_BYTES = 12


def encrypted_ceiling(plaintext_max_bytes: int) -> int:
    """How many bytes of payload a ``plaintext_max_bytes`` text turns into.

    A closed throw arrives as base64 of ``IV || ciphertext || tag``, a third
    larger than what the sender actually typed. That expansion is our
    arithmetic, not theirs: the visible limit has to be identical in both modes,
    or a closed sender would learn about base64 from an error message about a
    text that looked well inside it.
    """
    binary = _GCM_IV_BYTES + plaintext_max_bytes + _GCM_TAG_BYTES
    return 4 * ((binary + 2) // 3)


def encrypted_plaintext_bytes(text: str) -> int | None:
    """How much plaintext a closed payload accounts for; ``None`` if it is not one.

    The mirror of :func:`encrypted_ceiling`, and the reason it exists is not
    tidiness. ``enc`` arrives on the client's word, so measuring a closed throw
    by its own length would quietly turn one limit into two: anyone could claim
    the flag and store a third more raw text than the stated limit allows. Going
    back through the base64 measures every throw in the same units — the bytes
    the human actually typed — so the limit is one limit.

    This is arithmetic about size, not inspection of content: we decode the
    base64 and count, and we could not do more if we wanted to. No key is here,
    and none ever will be.
    """
    try:
        raw = base64.b64decode(text, validate=True)
    except (ValueError, binascii.Error):
        return None
    return max(0, len(raw) - _GCM_IV_BYTES - _GCM_TAG_BYTES)


#: One body for every kind of miss — never existed, expired, already read.
#: Telling them apart would turn code-guessing into a search with feedback.
MISS_BODY = {"detail": "no such throw"}

#: Per-process random key for the log pseudonym HMAC, generated fresh on every
#: start. It is the *default* keying: with it, a plain SHA-256 prefix table is
#: useless to an attacker who only has the logs (the code space is a tiny ~1.09M
#: values, trivially precomputed against an unkeyed hash), because they never
#: see this key — it lives only in RAM and is never logged. The tradeoff of the
#: random default is that pseudonyms differ across restarts, so you cannot
#: correlate a throw's events across a process boundary. An operator who *wants*
#: that stable cross-restart correlation sets ``THROW_LOG_HMAC_SECRET`` to a
#: fixed value — but must then keep that secret off the logs and out of the
#: image, since anyone who learns it regains the precompute attack.
_DEFAULT_LOG_HMAC_SECRET = secrets.token_bytes(32)


@dataclass(frozen=True, slots=True)
class Settings:
    ttl_seconds: float = DEFAULT_TTL_SECONDS
    max_bytes: int = DEFAULT_MAX_BYTES
    miss_delay_ms: int = DEFAULT_MISS_DELAY_MS
    #: Extra delay on a tarpitted miss, added on top of ``miss_delay_ms``. Only
    #: ever applies to misses from an over-budget IP (or under the global
    #: tarpit); hits never touch the gate, so honest readers never see it.
    gate_tarpit_delay_ms: int = DEFAULT_GATE_TARPIT_DELAY_MS
    sweep_interval_seconds: float = DEFAULT_SWEEP_INTERVAL_SECONDS
    gate_window_seconds: float = DEFAULT_WINDOW_SECONDS
    gate_miss_budget: int = DEFAULT_MISS_BUDGET
    gate_global_window_seconds: float = DEFAULT_GLOBAL_WINDOW_SECONDS
    gate_global_miss_threshold: int = DEFAULT_GLOBAL_MISS_THRESHOLD
    gate_max_tracked_ips: int = DEFAULT_MAX_TRACKED_IPS
    #: Only trust a forwarding header when we know a proxy sets it. Left False,
    #: the limiter uses the socket peer — trusting the header on a directly
    #: exposed app would let anyone spoof their IP and dodge the per-IP budget.
    trusted_proxy: bool = False
    forwarded_header: str = DEFAULT_FORWARDED_HEADER
    #: File the Pro fake-door appends interested emails to (one per line).
    pro_emails_path: str = DEFAULT_PRO_EMAILS_PATH
    #: File the feedback wish-box appends to (one line per record).
    feedback_path: str = DEFAULT_FEEDBACK_PATH
    #: Key for the log-pseudonym HMAC. Defaults to a per-process random value
    #: (see ``_DEFAULT_LOG_HMAC_SECRET``); set ``THROW_LOG_HMAC_SECRET`` to pin
    #: it for stable cross-restart correlation.
    log_hmac_secret: bytes = _DEFAULT_LOG_HMAC_SECRET

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        source = os.environ if env is None else env
        secret = source.get("THROW_LOG_HMAC_SECRET")
        return cls(
            ttl_seconds=float(source.get("THROW_TTL_SECONDS", DEFAULT_TTL_SECONDS)),
            max_bytes=int(source.get("THROW_MAX_BYTES", DEFAULT_MAX_BYTES)),
            miss_delay_ms=int(source.get("THROW_MISS_DELAY_MS", DEFAULT_MISS_DELAY_MS)),
            gate_tarpit_delay_ms=int(
                source.get("THROW_GATE_TARPIT_DELAY_MS", DEFAULT_GATE_TARPIT_DELAY_MS)
            ),
            sweep_interval_seconds=float(
                source.get("THROW_SWEEP_INTERVAL_SECONDS", DEFAULT_SWEEP_INTERVAL_SECONDS)
            ),
            gate_window_seconds=float(
                source.get("THROW_GATE_WINDOW_SECONDS", DEFAULT_WINDOW_SECONDS)
            ),
            gate_miss_budget=int(source.get("THROW_GATE_MISS_BUDGET", DEFAULT_MISS_BUDGET)),
            gate_global_window_seconds=float(
                source.get("THROW_GATE_GLOBAL_WINDOW_SECONDS", DEFAULT_GLOBAL_WINDOW_SECONDS)
            ),
            gate_global_miss_threshold=int(
                source.get("THROW_GATE_GLOBAL_MISS_THRESHOLD", DEFAULT_GLOBAL_MISS_THRESHOLD)
            ),
            gate_max_tracked_ips=int(
                source.get("THROW_GATE_MAX_TRACKED_IPS", DEFAULT_MAX_TRACKED_IPS)
            ),
            trusted_proxy=_env_bool(source.get("THROW_TRUSTED_PROXY"), default=False),
            forwarded_header=source.get("THROW_FORWARDED_HEADER", DEFAULT_FORWARDED_HEADER),
            pro_emails_path=source.get("THROW_PRO_EMAILS_PATH", DEFAULT_PRO_EMAILS_PATH),
            feedback_path=source.get("THROW_FEEDBACK_PATH", DEFAULT_FEEDBACK_PATH),
            log_hmac_secret=(
                secret.encode("utf-8") if secret else _DEFAULT_LOG_HMAC_SECRET
            ),
        )


def normalize_pro_email(raw: object) -> str | None:
    """Minimal validation for a Pro fake-door email; returns it trimmed or None.

    This is a fake-door signup, not an auth flow — we only need enough to reject
    obvious junk before appending. The rule: a string with a single-line ``@``
    that has something on both sides, no whitespace, and within the RFC length
    cap. We deliberately do not verify deliverability.
    """
    if not isinstance(raw, str):
        return None
    email = raw.strip()
    if not email or len(email) > _MAX_EMAIL_LEN:
        return None
    if any(c.isspace() for c in email):
        return None
    local, sep, domain = email.partition("@")
    if not sep or not local or not domain or "@" in domain:
        return None
    return email


def append_pro_email(path: str, email: str) -> None:
    """Append one interested email to ``path``, creating the dir if needed.

    One record per line: an ISO timestamp and the email, tab-separated. The file
    lives on a docker-volume so the list survives restarts. The email is written
    here and nowhere else — never to stdout or the access log — so it stays out
    of anything we ship or keep as operational logs.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with target.open("a", encoding="utf-8") as handle:
        handle.write(f"{ts}\t{email}\n")


def normalize_feedback(raw: object) -> str | None:
    """Trim a feedback text; None when it is not a usable string.

    Free-form by design — the only rules are "non-empty after trimming" and the
    character cap, which mirrors the page's ``maxlength``.
    """
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text or len(text) > _FEEDBACK_MAX_CHARS:
        return None
    return text


def append_feedback(path: str, text: str) -> None:
    """Append one feedback record to ``path`` as a single escaped line.

    Newlines/tabs/backslashes in the text are escaped so every record stays one
    ``ts<TAB>text`` line and the file remains trivially greppable. Like the Pro
    emails, the text goes to this file and nowhere else — never to stdout or
    the access log.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    flat = text.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t")
    with target.open("a", encoding="utf-8") as handle:
        handle.write(f"{ts}\t{flat}\n")


def _env_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def client_ip(request: Request, settings: Settings) -> str:
    """The IP the per-IP budget is charged to.

    Behind Caddy/Cloudflare the socket peer is always the proxy, so the real
    client must come from a forwarding header — but only when we *know* a proxy
    sets it (``trusted_proxy``). On a directly exposed app the header is
    attacker-controlled, so we ignore it and charge the socket peer.

    When trusted, Cloudflare's ``CF-Connecting-IP`` (a single, proxy-set
    address) wins. Otherwise we take the *leftmost* entry of the forwarded
    header — the original client as recorded by our own proxy, which we trust
    to have written it honestly.
    """
    if settings.trusted_proxy:
        cf = request.headers.get("CF-Connecting-IP")
        if cf and cf.strip():
            return cf.strip()
        forwarded = request.headers.get(settings.forwarded_header)
        if forwarded:
            first = forwarded.split(",")[0].strip()
            if first:
                return first
    return request.client.host if request.client else "unknown"


#: How many hex chars of the keyed HMAC to keep as a code's log pseudonym.
#: 12 hex = 48 bits — collision-safe for any realistic log volume, yet short
#: enough to eyeball. Once the digest is *keyed*, 12 hex is plenty: the point is
#: no longer "can't brute-force the prefix" but "can't invert without the key".
#: Stable within a process: the same code maps to the same pseudonym, so the
#: created/read pair of one throw stays correlatable across log lines.
_CODE_PSEUDONYM_LEN = 12

#: The key code_pseudonym uses when no explicit secret is passed. Starts at the
#: per-process random default and is overwritten by ``create_app`` with the
#: active ``Settings.log_hmac_secret`` — this is what lets the uvicorn access-log
#: filter (which sees no Settings) key its pseudonyms the same way log_event does.
_active_log_hmac_secret = _DEFAULT_LOG_HMAC_SECRET

#: Paths uvicorn may log verbatim: they carry no throw code. Everything else
#: is a receiver code (``/red-fox``) or a read (``/api/throws/red-fox``) and
#: must be pseudonymised before it reaches the access log.
_SAFE_LOG_PATHS = frozenset(
    {
        "/",
        "/closed",
        "/terms",
        "/privacy",
        "/healthz",
        "/robots.txt",
        "/api/throws",
        "/api/pro-interest",
        "/api/feedback",
    }
)


def code_pseudonym(code: str, secret: bytes | None = None) -> str:
    """A short, keyed, one-way stand-in for a throw code.

    The raw code is a shared secret between the two humans of a throw; it must
    never land in a log we keep. But the code space is tiny (~1.09M values), so a
    *plain* SHA-256 prefix is reversible by anyone with the logs: precompute the
    pseudonym→code table once, look up any live throw's code, steal its secret.

    We defeat that by keying the digest with HMAC-SHA256 under a secret the
    attacker never sees (``secret``, defaulting to the active per-process key).
    Without the key the pseudonym cannot be inverted from log access alone. The
    keyed prefix is still stable — same code, same key → same pseudonym — so
    created/read events of one throw still pair up.
    """
    key = _active_log_hmac_secret if secret is None else secret
    digest = hmac.new(key, code.encode("utf-8"), "sha256").hexdigest()
    return digest[:_CODE_PSEUDONYM_LEN]


def log_event(event: str, code: str, *, encrypted: bool | None = None) -> None:
    """One machine-readable line per interesting moment, on stdout.

    Throw content never appears here — nor does the raw code: only its stable
    pseudonym, so created and read of the same throw still line up.

    ``encrypted`` adds the throw's mode when there is one. It is a fact about
    the throw, not about what was in it, and it is the whole of what the funnel
    needs now that the key-bearing pages carry no browser analytics. The key
    itself cannot appear here even by accident: it travels in the fragment of
    the link, which no browser sends to us.
    """
    timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    mode = "" if encrypted is None else f" mode={'closed' if encrypted else 'open'}"
    print(
        f"event={event} code={code_pseudonym(code)}{mode} ts={timestamp}",
        file=sys.stdout,
        flush=True,
    )


def sanitize_log_path(raw_path: str) -> str:
    """Strip any throw code out of a request path before it is logged.

    uvicorn's access log writes the request line verbatim, and for a receiver
    GET (``/{code}``) or a read POST (``/api/throws/{code}``) that path *is*
    the code. We replace the code segment with its pseudonym so the access log
    stays useful (routes, status codes) without ever recording the secret.

    The read path pseudonymises the *normalised* code (``red-fox``), so we must
    normalise the raw segment here too before hashing — otherwise a non-canonical
    alias (``/api/throws/RED_FOX``) would pseudonymise to a different value than
    its ``event=read`` line and the two streams would fail to correlate. When the
    segment does not normalise to a real code we fall back to hashing it raw:
    still never the plaintext, just an uncorrelatable stand-in for a probe.

    A closed address falls into that same raw branch, which is exactly right:
    it has no canonical form to normalise to (it is matched exactly), so hashing
    it verbatim is what makes its create and read lines pair up. Either way the
    address never appears in a log we keep.
    """
    path = raw_path.split("?", 1)[0]
    if path in _SAFE_LOG_PATHS:
        return path
    if path.startswith("/api/throws/"):
        code = path[len("/api/throws/") :]
        return "/api/throws/" + code_pseudonym(normalize(code) or code)
    # Anything else is a bare receiver code (or an unknown probe): redact the
    # whole thing rather than risk leaking a code we failed to anticipate.
    segment = path.lstrip("/")
    return "/" + code_pseudonym(normalize(segment) or segment)


class _AccessLogRedactor(logging.Filter):
    """Rewrites the path in every uvicorn access-log record.

    uvicorn builds each access record with ``record.args`` set to
    ``(client_addr, method, full_path, http_version, status_code)``; the path
    sits at index 2. We pseudonymise it in place so no formatter — default or
    custom — can ever emit the raw code. A filter (not a disabled logger) keeps
    the operationally useful access log alive, just code-free.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            redacted = list(args)
            redacted[2] = sanitize_log_path(args[2])
            record.args = tuple(redacted)
        return True


def _install_access_log_redactor() -> None:
    """Attach the path redactor to uvicorn's access logger, exactly once.

    Called at import time so it is in place however ``app.main:app`` is served
    (the container just runs ``uvicorn app.main:app`` with no logging config).
    """
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, _AccessLogRedactor) for f in access_logger.filters):
        access_logger.addFilter(_AccessLogRedactor())


_install_access_log_redactor()


def create_app(
    settings: Settings | None = None,
    store: ThrowStore | None = None,
    gatekeeper: Gatekeeper | None = None,
) -> FastAPI:
    config = settings or Settings.from_env()
    # Point the module-level pseudonym key (used by log_event and, crucially, the
    # uvicorn access-log filter, which never sees Settings) at this app's key.
    global _active_log_hmac_secret
    _active_log_hmac_secret = config.log_hmac_secret
    throws = store or ThrowStore(ttl_seconds=config.ttl_seconds)
    gate = gatekeeper or Gatekeeper(
        window_seconds=config.gate_window_seconds,
        miss_budget=config.gate_miss_budget,
        global_window_seconds=config.gate_global_window_seconds,
        global_miss_threshold=config.gate_global_miss_threshold,
        max_tracked_ips=config.gate_max_tracked_ips,
    )
    miss_delay_seconds = config.miss_delay_ms / 1000.0
    tarpit_delay_seconds = config.gate_tarpit_delay_ms / 1000.0
    # The ceiling the server actually enforces on arriving text. A closed throw
    # is base64 of the same text, so it is allowed to be correspondingly bigger
    # — the human-visible limit stays config.max_bytes in both modes.
    closed_max_bytes = encrypted_ceiling(config.max_bytes)
    max_body_bytes = closed_max_bytes * _BODY_SLACK_FACTOR + _BODY_SLACK_BYTES

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        # Expired throws must not linger in RAM on a quiet instance: nobody
        # is coming for them, and their plaintext would sit in any dump.
        async def sweep_forever() -> None:
            while True:
                await asyncio.sleep(config.sweep_interval_seconds)
                throws.purge_expired()

        sweeper = asyncio.create_task(sweep_forever())
        try:
            yield
        finally:
            sweeper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sweeper

    app = FastAPI(
        title="throw.dog",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = config
    app.state.store = throws
    app.state.gatekeeper = gate

    # Public launch: the homepage and legal pages ARE indexable; everything
    # else — receiver /{code} pages (one-time secrets) and the API — stays out
    # of every index via the header (code pages also carry a <meta robots>).
    indexable_paths = {"/", "/terms", "/privacy", "/robots.txt"}

    @app.middleware("http")
    async def no_index(request: Request, call_next):
        response = await call_next(request)
        if request.url.path not in indexable_paths:
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        # Pages set their own policy (it carries their script hashes); anything
        # else — JSON, robots.txt, errors — gets the floor. Never overwrite:
        # two policies would intersect and blank the page.
        response.headers.setdefault("Content-Security-Policy", FLOOR_POLICY)
        return response

    async def miss(*, tarpitted: bool = False) -> JSONResponse:
        # The body is byte-identical for every miss (see MISS_BODY); only the
        # delay varies, and it varies uniformly for ALL of an IP's misses — an
        # existing code and a non-existent one are indistinguishable, so timing
        # never leaks whether a code existed. A tarpitted miss (over-budget IP
        # or global tarpit) pays an extra delay on top of the base, making
        # enumeration from abusive sources slow.
        delay = miss_delay_seconds + (tarpit_delay_seconds if tarpitted else 0.0)
        if delay > 0:
            await asyncio.sleep(delay)
        return JSONResponse(MISS_BODY, status_code=404)

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.get("/robots.txt", response_class=PlainTextResponse)
    async def robots() -> PlainTextResponse:
        return PlainTextResponse(ROBOTS_TXT)

    def too_big(size: int | None = None) -> JSONResponse:
        # The limit named here is always the visible one. A closed sender is
        # over it by the same text that would be over it in the open mode, so
        # the number they see is the number they can act on.
        measured = "the request body" if size is None else f"{size} bytes"
        return JSONResponse(
            {"detail": f"text is too big: {measured}, limit is {config.max_bytes}"},
            status_code=413,
        )

    @app.post("/api/throws")
    async def create_throw(request: Request) -> JSONResponse:
        # Read the body ourselves: letting the framework parse it first would
        # buffer a 100 MB flood in full before we ever got to the 64 KB limit.
        declared = request.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > max_body_bytes:
            return too_big()
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > max_body_bytes:
                return too_big()

        try:
            payload = json.loads(body)
        except ValueError:
            return JSONResponse({"detail": "malformed request"}, status_code=400)
        if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
            return JSONResponse(
                {"detail": "expected a JSON object with a text field"}, status_code=400
            )

        # ``enc`` absent (or null, which is how a client says the same thing in
        # JSON) means an open throw. Anything else must be the one format we
        # carry: a version we do not know means the two ends disagree about the
        # bytes, and storing it anyway would produce a throw nobody can read.
        scheme = payload.get("enc")
        if scheme is not None and scheme != ENC_SCHEME:
            return JSONResponse(
                {"detail": "unknown encryption scheme"}, status_code=400
            )
        encrypted = scheme is not None

        text = payload["text"]
        if not text.strip():
            return JSONResponse({"detail": "nothing to throw"}, status_code=400)
        if encrypted:
            # Measured in the sender's units, not ours: the number in a 413 is
            # the size of the text they pasted, and the limit it is compared
            # against is the same one an open throw is held to.
            carried = encrypted_plaintext_bytes(text)
            if carried is None:
                return JSONResponse(
                    {"detail": "an enc payload must be base64"}, status_code=400
                )
            if carried > config.max_bytes:
                return too_big(carried)
        else:
            size = len(text.encode("utf-8"))
            if size > config.max_bytes:
                return too_big(size)
        try:
            code = throws.put(text, encrypted=encrypted)
        except (StoreFull, OutOfCodes):
            return JSONResponse(
                {"detail": "service is busy, try again in a minute"}, status_code=503
            )
        log_event("created", code, encrypted=encrypted)
        return JSONResponse({"code": code}, status_code=201)

    @app.post("/api/throws/{code}")
    async def take_throw(code: str, request: Request) -> Response:
        # The store is consulted FIRST, and a HIT is served unconditionally: a
        # reader who holds a valid code is never gated, so honest reads survive
        # even when this IP shares a NAT with an abuser (the core use case) or
        # the global tarpit is engaged. The gate only governs MISSES — it makes
        # enumeration slower, it does not lock out anyone holding a real code.
        ip = client_ip(request, config)

        # Two address spaces, deliberately disjoint (see app.closedaddress). A
        # code is retyped by hand, so it is normalised forgivingly; an address
        # is only ever pasted by a machine, so it is matched exactly.
        closed = is_closed_address(code)
        canonical = code if closed else normalize(code)
        taken = throws.take(canonical) if canonical is not None else None
        if taken is not None:
            # A hit is free: recorded as such (a no-op for counting) and never
            # rate-limited. One-time-take semantics are unchanged.
            gate.record(ip, ReadOutcome.HIT)
            log_event("read", canonical, encrypted=taken.encrypted)
            body = {"text": taken.text}
            if taken.encrypted:
                # The receiving browser needs to know to reach for the key in
                # the fragment. We hand back the format, never a key — we have
                # never had one.
                body["enc"] = ENC_SCHEME
            return JSONResponse(body)

        if closed:
            # A miss on a closed address is not evidence of code-guessing: the
            # space is ~68 bits and nobody types it, so it cannot be enumerated
            # in the first place. Charging it to the per-IP budget would let a
            # flood of nonsense addresses tarpit the honest reader sharing that
            # NAT — the very person the budget exists to protect. An IP already
            # over budget still pays the tarpit; it just does not sink deeper.
            return await miss(tarpitted=not gate.allow(ip))

        # A miss: count it, then let the (now-updated) gate decide whether this
        # IP is over budget or the global tarpit is engaged. Either way the body
        # is byte-identical; only the delay grows.
        gate.record(ip, ReadOutcome.MISS)
        tarpitted = not gate.allow(ip)
        return await miss(tarpitted=tarpitted)

    @app.post("/api/pro-interest")
    async def pro_interest(request: Request) -> JSONResponse:
        # The email arrives in a POST body — never the URL — so it never reaches
        # the access log. We also never print it: it is user data, appended only
        # to the volume-backed file.
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > _PRO_BODY_MAX_BYTES:
                return JSONResponse({"detail": "request too large"}, status_code=413)
        try:
            payload = json.loads(body)
        except ValueError:
            return JSONResponse({"detail": "malformed request"}, status_code=400)
        email = normalize_pro_email(
            payload.get("email") if isinstance(payload, dict) else None
        )
        if email is None:
            return JSONResponse({"detail": "invalid email"}, status_code=400)
        try:
            append_pro_email(config.pro_emails_path, email)
        except OSError:
            return JSONResponse(
                {"detail": "could not record interest, try again"}, status_code=503
            )
        log_event("pro_email", "-")
        return JSONResponse({"ok": True}, status_code=201)

    @app.post("/api/feedback")
    async def feedback(request: Request) -> JSONResponse:
        # Free-form wish box (Pro panel). Same privacy posture as the emails:
        # the text arrives in the POST body, is appended to the volume-backed
        # file, and never reaches stdout or the access log.
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > _FEEDBACK_BODY_MAX_BYTES:
                return JSONResponse({"detail": "request too large"}, status_code=413)
        try:
            payload = json.loads(body)
        except ValueError:
            return JSONResponse({"detail": "malformed request"}, status_code=400)
        text = normalize_feedback(
            payload.get("text") if isinstance(payload, dict) else None
        )
        if text is None:
            return JSONResponse({"detail": "invalid feedback"}, status_code=400)
        try:
            append_feedback(config.feedback_path, text)
        except OSError:
            return JSONResponse(
                {"detail": "could not record feedback, try again"}, status_code=503
            )
        log_event("feedback", "-")
        return JSONResponse({"ok": True}, status_code=201)

    def page(html: str) -> HTMLResponse:
        """Serve a page under a policy computed from that exact page.

        The hashes in the policy come from the bytes below it, so a change to
        the inline JS can never leave a stale allow-list behind (see app.csp).
        """
        return HTMLResponse(html, headers={"Content-Security-Policy": csp_for(html)})

    @app.get("/", response_class=HTMLResponse)
    async def get_sender_page(request: Request) -> HTMLResponse:
        # Locale (EN default, RU when the browser prefers it) is decided from
        # Accept-Language; the page is otherwise identical for everyone.
        return page(sender_page(request.headers.get("accept-language")))

    # Static legal pages, English-only (see app.pages). Registered before the
    # ``/{code}`` catch-all so those words never resolve as receiver codes.
    # noindex is covered the same way as every page: the <meta robots> in the
    # shell plus the X-Robots-Tag middleware above. The abuse@ address on these
    # pages needs a matching Cloudflare Email Routing rule — a manual founder
    # step, not provisioned here.
    @app.get("/terms", response_class=HTMLResponse)
    async def get_terms_page() -> HTMLResponse:
        return page(TERMS_PAGE)

    @app.get("/privacy", response_class=HTMLResponse)
    async def get_privacy_page() -> HTMLResponse:
        return page(PRIVACY_PAGE)

    # The closed sender lives on its own page rather than as a redraw of the
    # homepage: the homepage has already loaded a script from the network, and a
    # loaded script cannot be unloaded from a tab where a key is about to be
    # generated (ADR 0003). Registered before the ``/{code}`` catch-all, like
    # the legal pages, so the word never resolves as a throw address.
    @app.get("/closed", response_class=HTMLResponse)
    async def get_closed_sender_page(request: Request) -> HTMLResponse:
        return page(closed_sender_page(request.headers.get("accept-language")))

    @app.get("/{code}", response_class=HTMLResponse)
    async def get_receiver_page(code: str, request: Request) -> HTMLResponse:
        # Same shell for every code, valid or not: the page reveals nothing,
        # and only its POST can consume a throw.
        return page(receiver_page(request.headers.get("accept-language")))

    return app


app = create_app()
