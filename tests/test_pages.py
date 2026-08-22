"""The pages are the product on a bad connection: keep them small and inline.

Speed is a design rule (``model/08-design.md``): each document must weigh under
100 KB on its own, with no external CSS/JS/font/image/CDN request to make it
whole.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.pages import (
    ANALYTICS_HOST,
    ANALYTICS_WEBSITE_ID,
    PRIVACY_PAGE,
    RECEIVER_PAGE,
    SENDER_PAGE,
    STRINGS,
    TERMS_PAGE,
    pick_locale,
    render_receiver,
    render_sender,
)

PAGE_BUDGET = 100 * 1024


@pytest.fixture()
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def test_sender_page_is_under_the_budget():
    size = len(SENDER_PAGE.encode("utf-8"))
    assert size < PAGE_BUDGET, f"sender page is {size} bytes, budget is {PAGE_BUDGET}"


def test_receiver_page_is_under_the_budget():
    size = len(RECEIVER_PAGE.encode("utf-8"))
    assert size < PAGE_BUDGET, f"receiver page is {size} bytes, budget is {PAGE_BUDGET}"


def test_legal_pages_are_under_the_budget():
    for name, page in (("terms", TERMS_PAGE), ("privacy", PRIVACY_PAGE)):
        size = len(page.encode("utf-8"))
        assert size < PAGE_BUDGET, f"{name} page is {size} bytes, budget is {PAGE_BUDGET}"


def test_pages_make_no_external_requests_except_own_analytics():
    # Everything is inline, with ONE deliberate exception: the cookieless Umami
    # tracker served from our OWN analytics subdomain (slice 7). That is not a
    # third-party CDN — it is self-hosted on the same VPS — so we relax the
    # slice-8 "zero external requests" rule to permit that one script src and
    # nothing else. The SVG xmlns is a namespace identifier, not a fetched URL.
    allowed_src = "https://" + ANALYTICS_HOST + "/script.js"
    for page in (SENDER_PAGE, RECEIVER_PAGE):
        body = page.replace('xmlns="http://www.w3.org/2000/svg"', "")
        # Strip the single permitted analytics script URL before auditing.
        body = body.replace(allowed_src, "")
        assert "http://" not in body
        assert "https://" not in body
        # Third-party CDNs / font hosts / stylesheets stay forbidden outright.
        for needle in ("@import", "cdn", "googleapis", "<link"):
            assert needle not in page.lower()
        # The only external script is the analytics one: exactly one src=.
        assert page.lower().count("src=") == 1


def test_analytics_snippet_points_at_own_host():
    # The tracker loads from the configured analytics host, never a third party.
    expected = f'<script defer src="https://{ANALYTICS_HOST}/script.js"'
    for page in (SENDER_PAGE, RECEIVER_PAGE):
        assert expected in page
        assert f'data-website-id="{ANALYTICS_WEBSITE_ID}"' in page
        # No third-party analytics ever.
        assert "google-analytics" not in page.lower()
        assert "googletagmanager" not in page.lower()
        assert "plausible" not in page.lower()


def test_pages_set_no_cookies():
    # Umami is cookieless and our own JS never touches cookies, so no consent
    # banner is needed. Assert our code writes nothing to document.cookie.
    for page in (SENDER_PAGE, RECEIVER_PAGE):
        assert "document.cookie" not in page


def test_funnel_events_are_wired():
    # The funnel events from model/10-metrics.md fire via umami.track (tdTrack).
    assert "tdTrack('paste')" in SENDER_PAGE
    assert "tdTrack('code_created')" in SENDER_PAGE
    assert "tdTrack('received')" in RECEIVER_PAGE
    # Pro hooks exist but are guarded (Pro UI ships in another slice).
    assert "tdTrack('pro_click')" in SENDER_PAGE
    assert "tdTrack('pro_email')" in SENDER_PAGE


def test_reduced_motion_is_honoured():
    assert "prefers-reduced-motion" in SENDER_PAGE


# --- i18n -------------------------------------------------------------------


def test_both_locales_carry_the_same_keys():
    # No missing translations, no fallback gaps: EN and RU are key-for-key equal.
    assert set(STRINGS) == {"en", "ru"}
    assert STRINGS["en"].keys() == STRINGS["ru"].keys()
    for locale, strings in STRINGS.items():
        for key, value in strings.items():
            assert value.strip(), f"{locale}/{key} is empty"


def test_localised_pages_leave_no_untranslated_tokens():
    # Every @@token@@ and the @@__T__@@ blob must be filled for both locales.
    for lang in STRINGS:
        for page in (render_sender(lang), render_receiver(lang)):
            assert "@@" not in page, f"{lang}: unfilled token in page"
            assert f'<html lang="{lang}">' in page


def test_pick_locale_defaults_to_english():
    assert pick_locale(None) == "en"
    assert pick_locale("") == "en"
    assert pick_locale("fr-FR,fr;q=0.9,de;q=0.5") == "en"
    assert pick_locale("*") == "en"


def test_pick_locale_selects_russian_when_preferred():
    assert pick_locale("ru") == "ru"
    assert pick_locale("ru-RU,ru;q=0.9,en;q=0.5") == "ru"
    # Highest q-value wins even when it is not the first entry.
    assert pick_locale("en;q=0.5, ru;q=0.9") == "ru"
    # A lower-weighted Russian must not override a preferred English.
    assert pick_locale("en-US,en;q=0.9,ru;q=0.3") == "en"


def test_render_carries_the_right_copy():
    ru = render_sender("ru")
    en = render_sender("en")
    assert STRINGS["ru"]["taglineA"] in ru
    assert STRINGS["en"]["taglineA"] in en
    assert STRINGS["ru"]["chip"] in render_receiver("ru")


def test_server_serves_russian_only_when_the_browser_prefers_it():
    client = TestClient(create_app())

    ru = client.get("/", headers={"Accept-Language": "ru-RU,ru;q=0.9"})
    assert STRINGS["ru"]["taglineB"] in ru.text
    assert STRINGS["en"]["taglineB"] not in ru.text

    en = client.get("/", headers={"Accept-Language": "en-US,en;q=0.9"})
    assert STRINGS["en"]["taglineB"] in en.text
    assert STRINGS["ru"]["taglineB"] not in en.text

    # No Accept-Language header at all falls back to the English default.
    default = client.get("/", headers={"Accept-Language": ""})
    assert STRINGS["en"]["taglineB"] in default.text

    # The receiver page is localised the same way.
    recv = client.get("/abc-def", headers={"Accept-Language": "ru"})
    assert STRINGS["ru"]["fetching"] in recv.text


# --- legal pages (Terms / Privacy) ------------------------------------------


def test_terms_page_serves_and_mentions_ephemerality_and_abuse(client):
    response = client.get("/terms")
    assert response.status_code == 200
    body = response.text
    assert "Terms of" in body
    # ephemerality: one-time read + ~10 minute lifetime.
    assert "10 minutes" in body
    assert "deleted the instant" in body  # one-time read
    # visible abuse contact.
    assert "abuse@throw.dog" in body


def test_privacy_page_serves_and_mentions_ephemerality_and_abuse(client):
    response = client.get("/privacy")
    assert response.status_code == 200
    body = response.text
    assert "Privacy" in body
    assert "10 minutes" in body
    assert "never logged" in body
    assert "abuse@throw.dog" in body


def test_legal_pages_carry_noindex(client):
    # Same noindex handling as every page: meta tag in the shell + response header.
    for path in ("/terms", "/privacy"):
        response = client.get(path)
        assert 'name="robots" content="noindex, nofollow"' in response.text
        assert response.headers["X-Robots-Tag"] == "noindex, nofollow"


def test_legal_pages_are_english_only(client):
    # RU is out of scope for the legal copy: the pages stay English regardless
    # of Accept-Language, and declare lang="en".
    for path in ("/terms", "/privacy"):
        response = client.get(path, headers={"Accept-Language": "ru-RU,ru;q=0.9"})
        assert '<html lang="en">' in response.text
        assert "@@" not in response.text  # no unfilled tokens


def test_main_pages_footer_links_to_legal_pages(client):
    # Footer link labels are localised; the destinations are the EN-only pages.
    en = client.get("/", headers={"Accept-Language": "en-US,en;q=0.9"}).text
    assert 'href="/terms"' in en
    assert 'href="/privacy"' in en
    assert STRINGS["en"]["footerTerms"] in en
    assert STRINGS["en"]["footerPrivacy"] in en

    ru = client.get("/", headers={"Accept-Language": "ru-RU,ru;q=0.9"}).text
    assert STRINGS["ru"]["footerTerms"] in ru
    assert STRINGS["ru"]["footerPrivacy"] in ru

    # The receiver page carries the same footer.
    recv = client.get("/abc-def")
    assert 'href="/terms"' in recv.text
    assert 'href="/privacy"' in recv.text
