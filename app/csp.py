"""The Content-Security-Policy that throw.dog serves with every page.

Why this lives in the application and not in Caddy, unlike every other security
header: the policy names each inline ``<script>`` by its sha256 hash, and the
pages are rendered per locale, so the hashes are a property of the response
body. A hand-copied list in a Caddyfile would be one JS edit away from a blank
page. Here it cannot drift — the hashes are taken from the bytes being sent.

Everything that *is* the same for every response (HSTS, nosniff,
Referrer-Policy, Permissions-Policy, X-Frame-Options) stays in Caddy.
"""

from __future__ import annotations

import base64
import hashlib
import re
from functools import lru_cache
from typing import Final

#: Inline scripts only — a ``<script src>`` is covered by its host, not a hash.
_INLINE_SCRIPT: Final = re.compile(
    r"<script\b(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S
)

#: Applied to responses that are not pages (JSON, robots.txt). They cannot
#: execute anything anyway; this says so out loud, for free.
FLOOR_POLICY: Final = "default-src 'none'; base-uri 'none'; frame-ancestors 'none'"


def inline_script_hashes(html: str) -> list[str]:
    """``'sha256-…'`` sources for every inline script in ``html``, in order.

    The hash covers the exact bytes between the tags — the same span the browser
    hashes — so any change to the JS changes the source here in lockstep.
    """
    return [
        "'sha256-%s'"
        % base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
        for body in _INLINE_SCRIPT.findall(html)
    ]


@lru_cache(maxsize=32)
def policy_for(html: str, analytics_origin: str = "") -> str:
    """The policy for one rendered page.

    ``analytics_origin`` is empty for every page where a key is born or shown:
    those load no network code at all (ADR 0003), and the header is where that
    promise becomes enforceable by the browser rather than by our good manners.

    Cached because there are only a handful of distinct pages (three templates
    times two locales, plus the legal pages), and they are module constants or
    memoised renders — the same string object comes back on every request.
    """
    script_src = " ".join(inline_script_hashes(html))
    connect_src = "'self'"
    if analytics_origin:
        # 'self' rides along on exactly the pages that already load code over
        # the network, and never on the ones that hold a key. We serve no
        # script file of our own, so it buys an attacker nothing (every
        # same-origin path answers with HTML or JSON, under nosniff) — but
        # Cloudflare injects one at /cdn-cgi/ on any page carrying a mailto:,
        # and without 'self' the legal pages would show a mangled address.
        script_src = f"{script_src} 'self' {analytics_origin}"
        # Umami POSTs the event to its own host; without this the tracker loads
        # and then every page_view is silently blocked.
        connect_src = f"{connect_src} {analytics_origin}"
    return "; ".join(
        (
            "default-src 'none'",
            f"script-src {script_src}",
            # One inline <style> block per page. A hash would work equally well
            # and buys nothing: there is no attacker-reachable style sink here.
            "style-src 'unsafe-inline'",
            # data: is the inline favicon; nothing else is an image.
            "img-src 'self' data:",
            f"connect-src {connect_src}",
            "base-uri 'none'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        )
    )
