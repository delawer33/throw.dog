"""HTTP surface for throw.dog — thin on purpose.

All the rules live in :mod:`app.codewords` and :mod:`app.throwstore`; this
module only translates them into requests, responses and one-line events.

Served by uvicorn as ``app.main:app`` (the actual command lives in the
container image, not here).
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel

from app.codewords import normalize
from app.pages import RECEIVER_PAGE, ROBOTS_TXT, SENDER_PAGE
from app.throwstore import ThrowStore

DEFAULT_TTL_SECONDS = 600
DEFAULT_MAX_BYTES = 65536
DEFAULT_MISS_DELAY_MS = 1000

#: One body for every kind of miss — never existed, expired, already read.
#: Telling them apart would turn code-guessing into a search with feedback.
MISS_BODY = {"detail": "no such throw"}


@dataclass(frozen=True, slots=True)
class Settings:
    ttl_seconds: float = DEFAULT_TTL_SECONDS
    max_bytes: int = DEFAULT_MAX_BYTES
    miss_delay_ms: int = DEFAULT_MISS_DELAY_MS

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        source = os.environ if env is None else env
        return cls(
            ttl_seconds=float(source.get("THROW_TTL_SECONDS", DEFAULT_TTL_SECONDS)),
            max_bytes=int(source.get("THROW_MAX_BYTES", DEFAULT_MAX_BYTES)),
            miss_delay_ms=int(source.get("THROW_MISS_DELAY_MS", DEFAULT_MISS_DELAY_MS)),
        )


class ThrowRequest(BaseModel):
    text: str


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

    app = FastAPI(title="throw.dog", docs_url=None, redoc_url=None, openapi_url=None)
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

    @app.post("/api/throws")
    async def create_throw(payload: ThrowRequest) -> JSONResponse:
        text = payload.text
        if not text.strip():
            return JSONResponse({"detail": "nothing to throw"}, status_code=400)
        size = len(text.encode("utf-8"))
        if size > config.max_bytes:
            return JSONResponse(
                {"detail": f"text is too big: {size} bytes, limit is {config.max_bytes}"},
                status_code=413,
            )
        code = throws.put(text)
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
