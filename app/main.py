"""HTTP surface for throw.dog — thin on purpose.

All the rules live in :mod:`app.codewords` and :mod:`app.throwstore`; this
module only translates them into requests, responses and one-line events.

Served by uvicorn as ``app.main:app`` (the actual command lives in the
container image, not here).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from app.codewords import normalize
from app.pages import RECEIVER_PAGE, ROBOTS_TXT, SENDER_PAGE
from app.throwstore import OutOfCodes, StoreFull, ThrowStore

DEFAULT_TTL_SECONDS = 600
DEFAULT_MAX_BYTES = 65536
DEFAULT_MISS_DELAY_MS = 1000
DEFAULT_SWEEP_INTERVAL_SECONDS = 60.0

#: How much raw body we tolerate around a max-size text. JSON escaping can
#: inflate the payload well past the text it carries, so the body ceiling is
#: generous — its job is to stop a 100 MB flood, not to police the text size.
_BODY_SLACK_FACTOR = 8
_BODY_SLACK_BYTES = 1024

#: One body for every kind of miss — never existed, expired, already read.
#: Telling them apart would turn code-guessing into a search with feedback.
MISS_BODY = {"detail": "no such throw"}


@dataclass(frozen=True, slots=True)
class Settings:
    ttl_seconds: float = DEFAULT_TTL_SECONDS
    max_bytes: int = DEFAULT_MAX_BYTES
    miss_delay_ms: int = DEFAULT_MISS_DELAY_MS
    sweep_interval_seconds: float = DEFAULT_SWEEP_INTERVAL_SECONDS

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        source = os.environ if env is None else env
        return cls(
            ttl_seconds=float(source.get("THROW_TTL_SECONDS", DEFAULT_TTL_SECONDS)),
            max_bytes=int(source.get("THROW_MAX_BYTES", DEFAULT_MAX_BYTES)),
            miss_delay_ms=int(source.get("THROW_MISS_DELAY_MS", DEFAULT_MISS_DELAY_MS)),
            sweep_interval_seconds=float(
                source.get("THROW_SWEEP_INTERVAL_SECONDS", DEFAULT_SWEEP_INTERVAL_SECONDS)
            ),
        )


def log_event(event: str, code: str) -> None:
    """One machine-readable line per interesting moment, on stdout.

    Throw content never appears here — not in events, not in errors.
    """
    timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    print(f"event={event} code={code} ts={timestamp}", file=sys.stdout, flush=True)


def create_app(settings: Settings | None = None, store: ThrowStore | None = None) -> FastAPI:
    config = settings or Settings.from_env()
    throws = store or ThrowStore(ttl_seconds=config.ttl_seconds)
    miss_delay_seconds = config.miss_delay_ms / 1000.0
    max_body_bytes = config.max_bytes * _BODY_SLACK_FACTOR + _BODY_SLACK_BYTES

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

    @app.middleware("http")
    async def no_index(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    async def miss() -> JSONResponse:
        # Constant delay so that a guesser learns nothing from timing.
        if miss_delay_seconds > 0:
            await asyncio.sleep(miss_delay_seconds)
        return JSONResponse(MISS_BODY, status_code=404)

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.get("/robots.txt", response_class=PlainTextResponse)
    async def robots() -> PlainTextResponse:
        return PlainTextResponse(ROBOTS_TXT)

    def too_big(size: int | None = None) -> JSONResponse:
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

        text = payload["text"]
        if not text.strip():
            return JSONResponse({"detail": "nothing to throw"}, status_code=400)
        size = len(text.encode("utf-8"))
        if size > config.max_bytes:
            return too_big(size)
        try:
            code = throws.put(text)
        except (StoreFull, OutOfCodes):
            return JSONResponse(
                {"detail": "service is busy, try again in a minute"}, status_code=503
            )
        log_event("created", code)
        return JSONResponse({"code": code}, status_code=201)

    @app.post("/api/throws/{code}")
    async def take_throw(code: str) -> Response:
        canonical = normalize(code)
        if canonical is None:
            return await miss()
        text = throws.take(canonical)
        if text is None:
            return await miss()
        log_event("read", canonical)
        return JSONResponse({"text": text})

    @app.get("/", response_class=HTMLResponse)
    async def sender_page() -> HTMLResponse:
        return HTMLResponse(SENDER_PAGE)

    @app.get("/{code}", response_class=HTMLResponse)
    async def receiver_page(code: str) -> HTMLResponse:
        # Same shell for every code, valid or not: the page reveals nothing,
        # and only its POST can consume a throw.
        return HTMLResponse(RECEIVER_PAGE)

    return app


app = create_app()
