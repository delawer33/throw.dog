"""The headers that make the E2E promise checkable from outside.

A product whose whole claim is "we cannot read it" has to be provably unable to
load someone else's code into the page that holds the key. That proof is a
Content-Security-Policy strict enough to name every script by hash, and it is
worthless if it drifts from the pages by one byte — so these tests recompute the
hashes from the served HTML rather than trusting a list.

The rest of the standard headers live in Caddy (they are identical for every
response and must not depend on application code); the last tests here read the
Caddyfiles to keep both deployment modes honest.
"""

import base64
import hashlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.closedaddress import generate as generate_address
from app.csp import inline_script_hashes
from app.main import create_app
from app.pages import ANALYTICS_HOST

ROOT = Path(__file__).resolve().parent.parent

#: (path, headers, is a key ever born or shown on this page?)
HTML_PAGES = (
    ("/", {}, False),
    ("/", {"accept-language": "ru"}, False),
    ("/closed", {}, True),
    ("/closed", {"accept-language": "ru"}, True),
    ("/terms", {}, False),
    ("/privacy", {}, False),
)


@pytest.fixture()
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def _pages(client):
    """Every HTML surface, including a receiver page (needs a real address)."""
    for path, headers, key_bearing in HTML_PAGES:
        yield path, client.get(path, headers=headers), key_bearing
    address = generate_address()
    yield f"/{address}", client.get(f"/{address}"), True


def _directive(policy: str, name: str) -> list[str]:
    for chunk in policy.split(";"):
        parts = chunk.strip().split()
        if parts and parts[0] == name:
            return parts[1:]
    return []


def _inline_scripts(html: str) -> list[str]:
    return [
        m.group(1)
        for m in re.finditer(r"<script\b(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)
    ]


def test_every_html_page_carries_a_csp(client):
    for path, response, _ in _pages(client):
        assert response.status_code == 200, path
        assert response.headers.get("content-security-policy"), path


def test_every_inline_script_is_named_by_its_own_hash(client):
    """The hash list is derived from the bytes we actually serve, per locale."""
    for path, response, _ in _pages(client):
        script_src = _directive(response.headers["content-security-policy"], "script-src")
        scripts = _inline_scripts(response.text)
        assert scripts, f"{path} has no inline script — did the page change?"
        for body in scripts:
            digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
            assert f"'sha256-{digest}'" in script_src, path


def test_inline_script_hashes_match_the_helper(client):
    for path, response, _ in _pages(client):
        script_src = _directive(response.headers["content-security-policy"], "script-src")
        for source in inline_script_hashes(response.text):
            assert source in script_src, path


def test_no_page_ever_allows_inline_or_eval_scripts(client):
    for path, response, _ in _pages(client):
        script_src = _directive(response.headers["content-security-policy"], "script-src")
        assert "'unsafe-inline'" not in script_src, path
        assert "'unsafe-eval'" not in script_src, path
        assert "*" not in script_src, path


def test_the_policy_locks_down_everything_it_does_not_need(client):
    for path, response, _ in _pages(client):
        policy = response.headers["content-security-policy"]
        assert _directive(policy, "default-src") == ["'none'"], path
        assert _directive(policy, "base-uri") == ["'none'"], path
        assert _directive(policy, "frame-ancestors") == ["'none'"], path
        assert _directive(policy, "form-action") == ["'self'"], path
        # A single inline <style> block, and the data: favicon.
        assert _directive(policy, "style-src") == ["'unsafe-inline'"], path
        assert _directive(policy, "img-src") == ["'self'", "data:"], path


def test_a_page_that_holds_a_key_admits_no_analytics_host(client):
    """ADR 0003 in header form: no network-loaded code where a key lives."""
    for path, response, key_bearing in _pages(client):
        if not key_bearing:
            continue
        policy = response.headers["content-security-policy"]
        assert ANALYTICS_HOST not in policy, path
        assert _directive(policy, "connect-src") == ["'self'"], path
        # Hashes and nothing else: no origin, not even ours, may serve code
        # into a tab that holds a key.
        assert all(
            source.startswith("'sha256-")
            for source in _directive(policy, "script-src")
        ), path


def test_the_analytics_pages_may_reach_exactly_their_own_host(client):
    expected = f"https://{ANALYTICS_HOST}"
    for path, response, key_bearing in _pages(client):
        if key_bearing:
            continue
        policy = response.headers["content-security-policy"]
        script_src = _directive(policy, "script-src")
        assert expected in script_src, path
        # Cloudflare's email-obfuscation script lands on a same-origin
        # /cdn-cgi/ path; without 'self' the legal pages render a mangled
        # abuse address and nobody notices until a user reports it.
        assert "'self'" in script_src, path
        # Umami posts the event back to the same host; without this, page_view
        # is silently dropped.
        assert _directive(policy, "connect-src") == ["'self'", expected], path


def test_non_html_responses_still_get_a_floor_policy(client):
    for path in ("/robots.txt", "/healthz"):
        policy = client.get(path).headers.get("content-security-policy", "")
        assert _directive(policy, "default-src") == ["'none'"], path
        assert _directive(policy, "frame-ancestors") == ["'none'"], path


# --- the static half, which belongs to the proxy -----------------------------

CADDYFILES = ("Caddyfile", "Caddyfile.acme")

REQUIRED_SITE_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    # Critical: a closed-throw link must not leak out of the tab in a Referer.
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


def _uncommented(block: str) -> str:
    """The block with ``#`` comment lines dropped — prose about a header is not
    the header."""
    return "\n".join(
        line for line in block.splitlines() if not line.strip().startswith("#")
    )


def _site_block(caddyfile: str, marker: str) -> str:
    """The braces-balanced body of the block introduced by ``marker``."""
    # Start at the marker's trailing brace: the ``{$SITE_DOMAIN}`` placeholder
    # in front of it has braces of its own that would balance out immediately.
    start = caddyfile.index(marker) + len(marker) - 1
    depth = 0
    for i in range(start, len(caddyfile)):
        if caddyfile[i] == "{":
            depth += 1
        elif caddyfile[i] == "}":
            depth -= 1
            if depth == 0:
                return caddyfile[start : i + 1]
    raise AssertionError(f"unbalanced block for {marker}")


@pytest.mark.parametrize("name", CADDYFILES)
def test_the_site_block_sets_the_standard_headers(name):
    block = _site_block((ROOT / name).read_text(), "{$SITE_DOMAIN} {")
    for header, value in REQUIRED_SITE_HEADERS.items():
        assert f"{header} \"{value}\"" in block, f"{name}: {header}"
    assert "Permissions-Policy" in block, name
    for feature in ("camera=()", "microphone=()", "geolocation=()"):
        assert feature in block, f"{name}: {feature}"
    # Neither Caddy nor its proxy hop should name the stack.
    assert "-Server" in block, name
    assert "-Via" in block, name


@pytest.mark.parametrize("name", CADDYFILES)
def test_the_proxy_never_sets_a_csp_of_its_own(name):
    """Two CSP headers intersect, and the intersection breaks the pages.

    The app owns the policy because only the app knows the hashes.
    """
    text = (ROOT / name).read_text()
    site = _uncommented(_site_block(text, "{$SITE_DOMAIN} {"))
    assert "Content-Security-Policy" not in site, name


@pytest.mark.parametrize("name", CADDYFILES)
def test_the_analytics_block_is_hardened_but_not_broken(name):
    """Umami's own dashboard is a third-party app: harden, do not police it."""
    block = _uncommented(
        _site_block((ROOT / name).read_text(), "{$ANALYTICS_DOMAIN} {")
    )
    assert 'Strict-Transport-Security "max-age=31536000; includeSubDomains"' in block, name
    assert 'X-Content-Type-Options "nosniff"' in block, name
    assert "-Server" in block, name
    assert "-Via" in block, name
    # A strict CSP here would blank the dashboard; frame protection is enough.
    assert "Content-Security-Policy" not in block, name
