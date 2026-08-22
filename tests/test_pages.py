"""The pages are the product on a bad connection: keep them small and inline.

Speed is a design rule (``model/08-design.md``): each document must weigh under
100 KB on its own, with no external CSS/JS/font/image/CDN request to make it
whole.
"""

from fastapi.testclient import TestClient

from app.main import create_app
from app.pages import (
    RECEIVER_PAGE,
    SENDER_PAGE,
    STRINGS,
    pick_locale,
    render_receiver,
    render_sender,
)

PAGE_BUDGET = 100 * 1024


def test_sender_page_is_under_the_budget():
    size = len(SENDER_PAGE.encode("utf-8"))
    assert size < PAGE_BUDGET, f"sender page is {size} bytes, budget is {PAGE_BUDGET}"


def test_receiver_page_is_under_the_budget():
    size = len(RECEIVER_PAGE.encode("utf-8"))
    assert size < PAGE_BUDGET, f"receiver page is {size} bytes, budget is {PAGE_BUDGET}"


def test_pages_make_no_external_requests():
    # Everything is inline; nothing reaches out to a CDN, font host, or image.
    # The SVG xmlns is a namespace identifier, not a fetched URL.
    for page in (SENDER_PAGE, RECEIVER_PAGE):
        body = page.replace('xmlns="http://www.w3.org/2000/svg"', "")
        assert "http://" not in body
        assert "https://" not in body
        for needle in ("src=", "@import", "cdn", "googleapis", "<link"):
            assert needle not in page.lower()


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
