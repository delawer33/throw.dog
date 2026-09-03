"""The SEO landings are the homepage wearing a query-shaped headline.

What matters: each is a real working sender page (not a doorway), each is
uniquely titled and described (not a synonym rewrite), the secret cluster keeps
every promise of ADR 0003 (a key can be born there), and the crawl plumbing —
sitemap, robots, indexability headers — names exactly the pages we mean.
"""

import pytest
from fastapi.testclient import TestClient

from app.landings import (
    CLOSED_LANDING_PAGES,
    INDEXABLE_PATHS,
    LANDING_PAGES,
    LANDINGS,
    SITEMAP_XML,
)
from app.main import create_app
from app.pages import ANALYTICS_HOST, ROBOTS_TXT

PAGE_BUDGET = 100 * 1024

_OPEN_SLUGS = tuple(l.slug for l in LANDINGS if not l.closed)
_CLOSED_SLUGS = tuple(l.slug for l in LANDINGS if l.closed)


@pytest.fixture()
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


# --- the sprint's shape -------------------------------------------------------


def test_eight_landings_in_two_clusters():
    # The sprint scope, pinned: four landings per cluster, one page per query,
    # no file-transfer pages before files exist.
    assert len(LANDINGS) == 8
    assert len(_OPEN_SLUGS) == 4
    assert len(_CLOSED_SLUGS) == 4
    for landing in LANDINGS:
        assert "file" not in landing.slug


def test_titles_descriptions_and_headlines_are_unique():
    # One query = one page, and no page is a copy of a sibling with synonyms
    # swapped in. Uniqueness here is the cheap tripwire for that rule.
    for field in ("title", "description", "sub"):
        values = [getattr(landing, field) for landing in LANDINGS]
        assert len(set(values)) == len(values), f"duplicate {field}"
    h1s = [(landing.tagline_a, landing.tagline_b) for landing in LANDINGS]
    assert len(set(h1s)) == len(h1s)


def test_every_landing_stays_under_the_page_budget():
    for slug, html in LANDING_PAGES.items():
        size = len(html.encode("utf-8"))
        assert size < PAGE_BUDGET, f"{slug} is {size} bytes, budget {PAGE_BUDGET}"


def test_every_landing_carries_the_working_form():
    # A landing without the form is an article, and articles are out of scope.
    for slug, html in LANDING_PAGES.items():
        assert 'id="text"' in html, slug
        assert 'id="throw"' in html, slug
        assert 'class="modes"' in html, slug
        assert "@@" not in html, f"{slug}: unfilled token"


def test_clusters_render_the_mode_their_queries_ask_for():
    # Device queries land on the open sender; secret queries land on the closed
    # one — with encryption machinery actually present, not just promised.
    for slug in _OPEN_SLUGS:
        html = LANDING_PAGES[slug]
        assert "crypto.subtle.encrypt" not in html, slug
    for slug in _CLOSED_SLUGS:
        html = LANDING_PAGES[slug]
        assert "crypto.subtle" in html, slug
        assert "enc: TD_ENC" in html, slug


def test_a_landing_is_a_document_not_an_entry_point():
    # A landing must serve the page its URL promised, to everyone: no
    # remembered-mode redirect away from it, and no rewriting the visitor's
    # remembered mode just because the page was read. The homepage keeps both
    # behaviours — that's the pair being pinned here.
    from app.pages import render_sender

    for slug, html in LANDING_PAGES.items():
        assert "location.replace('/closed')" not in html, slug
        assert "TD_IS_LANDING = true" in html, slug
    home = render_sender()
    assert "location.replace('/closed')" in home
    assert "TD_IS_LANDING = false" in home


def test_seo_meta_is_complete_and_self_canonical():
    for landing in LANDINGS:
        html = LANDING_PAGES[landing.slug]
        assert f"<title>{landing.title}</title>" in html
        assert f'rel="canonical" href="https://throw.dog/{landing.slug}"' in html
        assert 'name="description"' in html
        assert 'property="og:title"' in html
        assert "noindex" not in html


def test_cross_links_stay_inside_a_cluster():
    # The two intents are different people on different errands; the clusters
    # meet through the homepage, never through each other — anywhere on the
    # page, footer included. And no page links to itself.
    for slug in _OPEN_SLUGS:
        html = LANDING_PAGES[slug]
        for foreign in _CLOSED_SLUGS:
            assert f'href="/{foreign}"' not in html, (slug, foreign)
        for sibling in (s for s in _OPEN_SLUGS if s != slug):
            assert f'href="/{sibling}"' in html, (slug, sibling)
        assert f'href="/{slug}"' not in html, slug
    for slug in _CLOSED_SLUGS:
        html = LANDING_PAGES[slug]
        for foreign in _OPEN_SLUGS:
            assert f'href="/{foreign}"' not in html, (slug, foreign)
        for sibling in (s for s in _CLOSED_SLUGS if s != slug):
            assert f'href="/{sibling}"' in html, (slug, sibling)
        assert f'href="/{slug}"' not in html, slug


# --- ADR 0003 holds on the secret cluster ------------------------------------


def test_no_network_loaded_code_runs_on_a_secret_landing():
    # A key is born on these pages, so they are held to the same line as
    # /closed and the receiver: no loaded script, no analytics, no funnel
    # calls, no URL that fetches anything. Same assertions as
    # test_pages.test_no_network_loaded_code_runs_where_a_key_lives.
    assert len(CLOSED_LANDING_PAGES) == 4
    for html in CLOSED_LANDING_PAGES:
        assert "src=" not in html.lower()
        assert ANALYTICS_HOST not in html
        assert "tdTrack" not in html
        body = html.replace('xmlns="http://www.w3.org/2000/svg"', "")
        body = body.replace("xmlns='http://www.w3.org/2000/svg'", "")
        body = body.replace("https://throw.dog", "")
        assert "http://" not in body
        assert "https://" not in body


def test_open_landings_carry_the_same_analytics_as_the_homepage():
    for slug in _OPEN_SLUGS:
        html = LANDING_PAGES[slug]
        assert ANALYTICS_HOST in html, slug
        assert html.lower().count("src=") == 1, slug


def test_secret_landing_csp_forbids_loading_code(client):
    for slug in _CLOSED_SLUGS:
        policy = client.get(f"/{slug}").headers["Content-Security-Policy"]
        directives = dict(
            part.strip().split(" ", 1) for part in policy.split(";") if part.strip()
        )
        # Only hashes in script-src: no 'self', no host — the browser enforces
        # ADR 0003 on these pages exactly as it does on /closed.
        assert "'self'" not in directives["script-src"], slug
        assert ANALYTICS_HOST not in policy, slug


# --- serving and crawl plumbing ----------------------------------------------


def test_landings_are_served_and_indexable(client):
    for slug in LANDING_PAGES:
        response = client.get(f"/{slug}")
        assert response.status_code == 200, slug
        assert "X-Robots-Tag" not in response.headers, slug
        assert "noindex" not in response.text, slug


def test_a_landing_slug_never_burns_a_throw(client):
    # The routes are registered before the /{code} catch-all; a GET of a
    # landing must render the landing, not a receiver page for a dead code.
    response = client.get("/one-time-secret")
    assert "One-Time Secret" in response.text
    assert 'id="status"' not in response.text


def test_sitemap_lists_exactly_the_indexable_pages(client):
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert "X-Robots-Tag" not in response.headers
    for path in INDEXABLE_PATHS:
        assert f"<loc>https://throw.dog{path}</loc>" in response.text
    assert response.text.count("<loc>") == len(INDEXABLE_PATHS) == 11


def test_every_indexable_page_carries_a_link_preview_card(client):
    # Search and shared links are the product's main channel: a bare link with
    # no image is a click not made. The card must be on every page a stranger
    # can arrive at or share — landings, homepage and the legal pages alike.
    for path in INDEXABLE_PATHS:
        body = client.get(path).text
        assert 'property="og:image" content="https://throw.dog/og.png"' in body, path
        assert 'name="twitter:card" content="summary_large_image"' in body, path
        assert 'property="og:site_name"' in body, path
        assert 'property="og:locale"' in body, path


def test_the_preview_image_is_served_and_cacheable(client):
    response = client.get("/og.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert "immutable" in response.headers["cache-control"]
    # A PNG magic number, so a truncated or swapped asset fails here and not
    # silently in someone's link preview.
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert "X-Robots-Tag" not in response.headers


def test_structured_data_everywhere_except_where_a_key_lives():
    # It tells a crawler what the product *is*. It carries a schema.org URL,
    # so it stays off the pages ADR 0003 holds to zero outside references.
    for slug in _OPEN_SLUGS:
        assert "application/ld+json" in LANDING_PAGES[slug], slug
        assert '"@type":"WebApplication"' in LANDING_PAGES[slug], slug
    for slug in _CLOSED_SLUGS:
        assert "application/ld+json" not in LANDING_PAGES[slug], slug
        assert "schema.org" not in LANDING_PAGES[slug], slug


def test_legal_pages_are_not_link_graph_dead_ends(client):
    # /terms and /privacy are indexable and in the sitemap; a crawler landing
    # there must find a way into the landings rather than a three-link cul-de-sac.
    for path in ("/terms", "/privacy"):
        body = client.get(path).text
        assert 'href="/send-text-from-pc-to-phone"' in body, path
        assert 'href="/one-time-secret"' in body, path


def test_sitemap_dates_every_url():
    assert SITEMAP_XML.count("<lastmod>") == len(INDEXABLE_PATHS)


def test_robots_names_the_sitemap():
    assert "Sitemap: https://throw.dog/sitemap.xml" in ROBOTS_TXT
    assert SITEMAP_XML.count("<url>") == len(INDEXABLE_PATHS)


def test_homepage_footer_links_into_both_clusters(client):
    body = client.get("/").text
    assert 'href="/send-text-from-pc-to-phone"' in body
    assert 'href="/one-time-secret"' in body


def test_cluster_links_live_on_the_homepage_alone(client):
    # The spec sanctions exactly one meeting point. /closed and receiver pages
    # are working surfaces, not entry points — no promo links there.
    for path in ("/closed", "/red-fox"):
        body = client.get(path).text
        assert 'href="/send-text-from-pc-to-phone"' not in body, path
        assert 'href="/one-time-secret"' not in body, path


# --- honesty ------------------------------------------------------------------


def test_secret_cluster_copy_stays_honest():
    # The boundary named out loud, per the PRD's content principles: no
    # military-grade puffery, and the alternative page admits what in-browser
    # encryption cannot protect against.
    for html in CLOSED_LANDING_PAGES:
        assert "military" not in html.lower()
        assert "unhackable" not in html.lower()
    comparison = LANDING_PAGES["privnote-alternative"]
    assert "can't protect you from the site" in comparison
    assert "github.com/delawer33/throw.dog" in comparison


def test_landing_copy_never_promises_files_yet():
    for slug, html in LANDING_PAGES.items():
        prose = html.split('class="card prose seo"')[1].split("<footer")[0]
        assert "upload" not in prose.lower(), slug
