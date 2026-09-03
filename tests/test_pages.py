"""The pages are the product on a bad connection: keep them small and inline.

Speed is a design rule (``model/08-design.md``): each document must weigh under
100 KB on its own, with no external CSS/JS/font/image/CDN request to make it
whole.
"""

import re

import pytest
from fastapi.testclient import TestClient

from app.closedaddress import generate as generate_address
from app.main import create_app
from app.pages import (
    ANALYTICS_HOST,
    ANALYTICS_WEBSITE_ID,
    CLOSED_SENDER_PAGE,
    KEY_BEARING_PAGES,
    PRIVACY_PAGE,
    RECEIVER_PAGE,
    SENDER_PAGE,
    STRINGS,
    TERMS_PAGE,
    pick_locale,
    render_closed_sender,
    render_receiver,
    render_sender,
)

PAGE_BUDGET = 100 * 1024

#: Substrings that mean "this page fetches something from a third party". Kept
#: narrow enough that legal copy *about* CDNs and font hosts does not match.
_FETCH_NEEDLES = ("@import", "cdn.", "//cdn", "googleapis", "unpkg.com", "jsdelivr")


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


def test_closed_sender_page_is_under_the_budget():
    size = len(CLOSED_SENDER_PAGE.encode("utf-8"))
    assert size < PAGE_BUDGET, f"closed sender is {size} bytes, budget is {PAGE_BUDGET}"


def test_legal_pages_are_under_the_budget():
    for name, page in (("terms", TERMS_PAGE), ("privacy", PRIVACY_PAGE)):
        size = len(page.encode("utf-8"))
        assert size < PAGE_BUDGET, f"{name} page is {size} bytes, budget is {PAGE_BUDGET}"


def test_no_network_loaded_code_runs_where_a_key_lives():
    # The most important test in this file, and it is a test about a promise
    # rather than about markup (ADR 0003). On the closed sender a key is
    # generated; on a receiver page a key is used and the decrypted text ends up
    # in the DOM. "The server only ever sees ciphertext" cannot survive a script
    # that page fetches from anywhere — including from us — so those two pages
    # must load nothing at all.
    #
    # Stripping the key out of the URL is NOT a substitute and must not be
    # mistaken for one: the plaintext sits in the same tab either way. Today's
    # safety would in any case be accidental — the tracker is `defer` and the
    # inline script happens to run first — and accidental is not a property.
    for page in KEY_BEARING_PAGES:
        assert "src=" not in page.lower(), "no loaded script on a key-bearing page"
        assert ANALYTICS_HOST not in page
        assert "tdTrack" not in page, "no funnel calls where a key exists"
        body = page.replace('xmlns="http://www.w3.org/2000/svg"', "")
        body = body.replace("xmlns='http://www.w3.org/2000/svg'", "")
        body = body.replace("https://throw.dog", "")
        assert "http://" not in body
        assert "https://" not in body


def test_analytics_survives_only_on_the_open_sender_page():
    # The one exception, and it is affordable precisely because it is confined:
    # a click that never becomes a request (pro_click / feedback_open) is the
    # only funnel fact a server log cannot produce, and it happens here, where
    # no key is ever born. Everything else was already derivable server-side.
    assert ANALYTICS_HOST in SENDER_PAGE
    assert SENDER_PAGE.lower().count("src=") == 1
    assert "tdTrack('pro_click')" in SENDER_PAGE
    assert "tdTrack('feedback_open')" in SENDER_PAGE


def test_the_open_sender_loads_nothing_but_its_own_analytics():
    # Everything else is inline, with ONE deliberate exception: the cookieless
    # Umami tracker served from our OWN analytics subdomain — self-hosted on the
    # same VPS, not a third-party CDN. The SVG xmlns is a namespace identifier,
    # not a fetched URL; so are the data-URI favicon, the self-canonical, and
    # the JSON-LD @context — schema.org names the vocabulary, browsers never
    # fetch it (and the block is a data script, not an executed one).
    allowed_src = "https://" + ANALYTICS_HOST + "/script.js"
    body = SENDER_PAGE.replace('xmlns="http://www.w3.org/2000/svg"', "")
    body = body.replace("xmlns='http://www.w3.org/2000/svg'", "")
    body = body.replace(allowed_src, "")
    body = body.replace('"@context":"https://schema.org"', "")
    body = body.replace("https://throw.dog", "")
    assert "http://" not in body
    assert "https://" not in body
    for needle in _FETCH_NEEDLES:
        assert needle not in SENDER_PAGE.lower()
    for match in re.findall(r"<link[^>]*>", SENDER_PAGE, flags=re.IGNORECASE):
        assert 'href="data:' in match or 'href="https://throw.dog' in match


def test_analytics_snippet_points_at_own_host():
    # The identity of the tracker matters as much as its confinement: a stray
    # third-party snippet would defeat the whole cookieless story, and the only
    # site id we ever hand out is our own.
    assert f'data-website-id="{ANALYTICS_WEBSITE_ID}"' in SENDER_PAGE
    for foreign in ("google-analytics", "googletagmanager", "plausible", "hotjar"):
        assert foreign not in SENDER_PAGE.lower()


def test_no_page_loads_a_third_party_anything():
    # Needles that indicate a *fetch*, not a mention: the Privacy copy now
    # discusses CDNs and font hosts in prose, and saying so must not trip a test
    # about loading from them.
    for page in (SENDER_PAGE, CLOSED_SENDER_PAGE, RECEIVER_PAGE, TERMS_PAGE, PRIVACY_PAGE):
        for needle in _FETCH_NEEDLES:
            assert needle not in page.lower()


def test_pages_set_no_cookies():
    # Umami is cookieless and our own JS never touches cookies, so no consent
    # banner is needed. Assert our code writes nothing to document.cookie.
    for page in (SENDER_PAGE, CLOSED_SENDER_PAGE, RECEIVER_PAGE):
        assert "document.cookie" not in page


def test_funnel_events_are_wired():
    # The funnel events from model/10-metrics.md that still belong in the
    # browser. The rest moved to the server log, which sees creates and reads
    # with their mode, GETs of a page that never became a read, and referrers
    # (in the proxy log) — everything except a click that stayed a click.
    assert "tdTrack('paste')" in SENDER_PAGE
    assert "tdTrack('code_created')" in SENDER_PAGE
    assert "tdTrack('pro_click')" in SENDER_PAGE
    assert "tdTrack('pro_email')" in SENDER_PAGE
    assert "tdTrack('feedback_open')" in SENDER_PAGE


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
        for page in (render_sender(lang), render_closed_sender(lang), render_receiver(lang)):
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
    assert STRINGS["ru"]["chipEphemeral"] in render_receiver("ru")
    assert STRINGS["ru"]["modeClosedName"] in render_closed_sender("ru")


def test_each_homepage_language_has_its_own_address():
    # The indexable homepages do not read Accept-Language: one URL, one
    # language, always. A homepage that answered in whatever language was
    # asked for could only ever be indexed in one of them, and the other would
    # exist unseen — search is the main channel, so the URLs are the split.
    client = TestClient(create_app())

    for header in ("ru-RU,ru;q=0.9", "en-US,en;q=0.9", ""):
        en = client.get("/", headers={"Accept-Language": header})
        assert STRINGS["en"]["taglineB"] in en.text, header
        assert STRINGS["ru"]["taglineB"] not in en.text, header

        ru = client.get("/ru/", headers={"Accept-Language": header})
        assert STRINGS["ru"]["taglineB"] in ru.text, header
        assert STRINGS["en"]["taglineB"] not in ru.text, header

    # Each names the other, so a reader who landed on the wrong one is one
    # click away and a crawler finds the pair without guessing.
    assert 'href="/ru/"' in client.get("/").text
    assert 'href="/"' in client.get("/ru/").text


def test_pages_that_never_reach_an_index_still_follow_the_browser():
    # /closed and the receiver pages are noindex working surfaces: no crawler
    # forms an opinion about them, so answering in the reader's own language
    # costs nothing and helps.
    client = TestClient(create_app())
    recv = client.get("/abc-def", headers={"Accept-Language": "ru"})
    assert STRINGS["ru"]["fetching"] in recv.text
    closed = client.get("/closed", headers={"Accept-Language": "ru"})
    assert STRINGS["ru"]["taglineB"] in closed.text


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


def test_legal_pages_are_indexable_with_seo_meta(client):
    # Public launch: legal pages carry description + canonical and no noindex.
    for path in ("/terms", "/privacy"):
        response = client.get(path)
        assert "noindex" not in response.text
        assert "X-Robots-Tag" not in response.headers
        assert 'name="description"' in response.text
        assert f'rel="canonical" href="https://throw.dog{path}"' in response.text


def test_sender_page_is_indexable_with_previews(client):
    response = client.get("/")
    assert "noindex" not in response.text
    assert "X-Robots-Tag" not in response.headers
    assert 'name="description"' in response.text
    assert 'property="og:title"' in response.text
    assert 'rel="canonical" href="https://throw.dog/"' in response.text


def test_receiver_page_stays_noindex(client):
    response = client.get("/some-code")
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

    ru = client.get("/ru/").text
    assert STRINGS["ru"]["footerTerms"] in ru
    assert STRINGS["ru"]["footerPrivacy"] in ru

    # The receiver page carries the same footer.
    recv = client.get("/abc-def")
    assert 'href="/terms"' in recv.text
    assert 'href="/privacy"' in recv.text


# --- mode of the throw ------------------------------------------------------


def test_both_sender_pages_show_both_modes_with_their_own_line():
    # The choice is only real if both halves say what they actually do. Neither
    # is allowed to be just a name, and neither may be missing — a mode you
    # cannot see is a mode chosen for you.
    for page in (SENDER_PAGE, CLOSED_SENDER_PAGE):
        for key in ("modeOpenName", "modeOpenNote", "modeClosedName", "modeClosedNote"):
            assert STRINGS["en"][key] in page, key
        assert 'class="modes"' in page
        # Exactly one half is the current one, and exactly one is a way out.
        assert page.count('class="mode on"') == 1
        assert page.count('id="switchmode"') == 1


def test_the_remembered_mode_is_applied_before_anything_is_drawn():
    # Pasting throws the text immediately, so the mode cannot be decided in the
    # moment — it has to already be settled when the textarea appears.
    assert "td_mode" in SENDER_PAGE
    assert "location.replace('/closed')" in SENDER_PAGE
    body = SENDER_PAGE.index("<body>")
    assert SENDER_PAGE.index("location.replace('/closed')") - body < 800


def test_a_draft_survives_a_mode_switch_without_touching_the_url_or_us():
    # Switching must not be a trap that eats what you typed — and must not be a
    # way for a text meant for the closed mode to reach us on the way there.
    for page in (SENDER_PAGE, CLOSED_SENDER_PAGE):
        assert "sessionStorage" in page
        assert "tdKeepDraft(text.value)" in page
        assert "tdTakeDraft()" in page
    # The draft never becomes part of an address or a request body.
    assert "td_draft=" not in SENDER_PAGE
    assert "td_draft" not in CLOSED_SENDER_PAGE.split("JSON.stringify")[1]
    assert "td_draft" not in RECEIVER_PAGE


def test_closed_mode_unavailable_is_shown_with_its_reason():
    # Disabled and explained, never absent: a mode that silently vanished would
    # read as us having lied on the homepage.
    assert "switchmode.disabled = true" in SENDER_PAGE
    assert "T.modeClosedUnavailable" in SENDER_PAGE
    assert STRINGS["en"]["modeClosedUnavailable"] in SENDER_PAGE


def test_no_unconditional_padlock_near_a_throw():
    # The padlock promised protection on a page where there was none. It is gone
    # from every page where a throw is made or read; the mode says what is true.
    for page in (SENDER_PAGE, CLOSED_SENDER_PAGE, RECEIVER_PAGE):
        assert "🔒" not in page
    assert STRINGS["en"]["chipOpen"] in SENDER_PAGE
    assert STRINGS["en"]["chipClosed"] in CLOSED_SENDER_PAGE
    assert STRINGS["en"]["chipEphemeral"] in RECEIVER_PAGE


# --- closed sender ----------------------------------------------------------


def test_the_closed_sender_encrypts_before_it_ever_calls_us():
    # Ordering is the promise: the server must not be given a chance to hold the
    # text, not even for the length of one request.
    page = CLOSED_SENDER_PAGE
    assert "crypto.subtle" in page
    assert page.index("tdEncrypt(") < page.index("fetch('/api/throws'")
    assert "enc: TD_ENC" in page
    # The plaintext variable is never what gets posted.
    assert "JSON.stringify({ text: payload, enc: TD_ENC })" in page


def test_the_key_goes_in_the_fragment_and_only_there():
    page = CLOSED_SENDER_PAGE
    assert "'/' + data.code + '#' + encoded" in page
    # Never a query parameter, never a path segment, never a body field.
    assert "?key=" not in page
    assert "key: " not in page


def test_the_closed_sender_leads_with_the_qr_and_says_why():
    # The QR is the delivery channel that does not put the key into somebody's
    # chat history, so it is the result rather than a garnish beside it.
    page = CLOSED_SENDER_PAGE
    assert 'class="qr big"' in page
    # No code element at all: a closed throw has no two-word code to show.
    # (The .codebig style lives in the shared stylesheet; the markup is what
    # matters here.)
    assert 'id="codebig"' not in page
    assert page.index('class="qr big"') < page.index('id="url"')
    # One line under it, not three. The fact worth carrying is that the key is
    # only in this link; the rest answered questions nobody had asked.
    assert page.count('class="hint"') == 1
    assert STRINGS["en"]["keyOnce"] in page


def test_the_closed_result_centres_on_the_qr_and_its_buttons_match():
    # Both complaints from a real browser: the card hugged the left edge, and
    # the two buttons were different widths because one was .wide and one was
    # shrink-to-fit. They now share a row and a flex basis.
    page = CLOSED_SENDER_PAGE
    assert 'id="done" class="doneclosed"' in page
    assert ".doneclosed { text-align: center; }" in page
    assert "margin: 0 auto 14px" in page, "the QR must centre itself"
    # Scoped to the result card: the compose button above it is legitimately
    # full-width, being the only thing to press there.
    done = page[page.index('id="done"'):page.index('id="again"')]
    assert 'class="donerow"' in done, "both actions belong to the one row"
    assert 'id="copyurl"' in done
    assert "wide" not in done, "a full-width button beside a shrink-to-fit one"


def test_the_open_sender_still_leads_with_the_code():
    # Typing the two words on the other device is the main path in open mode.
    assert SENDER_PAGE.index('id="codebig"') < SENDER_PAGE.index('id="qr"')


def test_the_open_sender_carries_no_encryption_machinery():
    # It only needs to know whether the closed mode is offerable at all.
    assert "tdCryptoReady" in SENDER_PAGE
    assert "crypto.subtle.encrypt" not in SENDER_PAGE
    assert "tdNewKey" not in SENDER_PAGE


# --- receiver ---------------------------------------------------------------


def test_the_closed_sender_says_up_front_when_the_browser_cannot_encrypt():
    # /closed is reachable directly — a bookmark, or the mode we remembered — so
    # the homepage's check does not cover it. Finding out at the moment you
    # press throw means having already typed the secret into a page that cannot
    # protect it, so the page refuses input instead.
    page = CLOSED_SENDER_PAGE
    assert "T.noCrypto" in page
    assert "text.disabled = true" in page
    assert page.index("tdCryptoReady()") < page.index("function send(")


def test_the_receiver_reads_the_key_from_the_fragment_and_takes_it_back_out():
    # Two guarantees whose timing decides whether the reader loses the throw:
    # the key is stripped once the server has answered (not before, or a failed
    # read leaves a URL that can no longer be refreshed), and an unusable key
    # costs nothing because the page never asks. Both are timing, so both are
    # tested by running this script in tests/test_receiver_js.py, which counts
    # the fetches and the strips. Here we only pin that the parts are present.
    page = RECEIVER_PAGE
    assert "location.hash" in page
    assert "history.replaceState" in page
    assert "function stripKey()" in page


def test_the_receiver_recognises_a_closed_address_the_same_way_the_server_does():
    from app.closedaddress import JS_PATTERN

    assert JS_PATTERN in RECEIVER_PAGE
    # And the same rule is on the sender pages, so the "Got a code?" field can
    # tell a pasted closed link from two words.
    for page in (SENDER_PAGE, CLOSED_SENDER_PAGE):
        assert JS_PATTERN in page


def test_the_receiver_tells_three_situations_apart():
    # "Nothing here", "your link is incomplete" and "your key did not fit" call
    # for three different next moves from the reader, so they are three
    # different messages — and the incomplete-link one says the throw survives,
    # while the bad-key one says it does not.
    page = RECEIVER_PAGE
    for key in ("notFound", "keyMissing", "keyBad", "noCrypto"):
        assert f"T.{key}" in page, key
    en = STRINGS["en"]
    assert len({en["notFound"], en["keyMissing"], en["keyBad"]}) == 3
    assert "still waiting" in en["keyMissing"]
    assert "used up" in en["keyBad"]
    for locale in STRINGS.values():
        assert len({locale["notFound"], locale["keyMissing"], locale["keyBad"]}) == 3


def test_the_receiver_decrypts_locally_and_never_asks_us_to():
    page = RECEIVER_PAGE
    # The call site, not the definition: decryption happens only after the
    # ciphertext has arrived, and in this tab.
    assert "tdDecrypt(imported, data.text)" in page
    assert page.index("tdDecrypt(imported, data.text)") > page.index(
        "fetch('/api/throws/"
    )
    # No second request anywhere: the key is never sent to be checked.
    assert page.count("fetch(") == 1


# --- fetch-by-code accepts a whole closed link ------------------------------


def test_the_fetch_field_keeps_the_fragment_of_a_pasted_link():
    # A pasted link is the natural thing to put in that field, and the old
    # normaliser ground a closed link — key and all — into an address that could
    # not exist, so the reader saw "nothing here" over a live throw.
    for page in (SENDER_PAGE, CLOSED_SENDER_PAGE):
        assert "raw.indexOf('#')" in page
        assert "'/' + last + hash" in page


def test_the_fetch_field_still_forgives_typed_words():
    for page in (SENDER_PAGE, CLOSED_SENDER_PAGE):
        assert "replace(/[^a-z]+/g, '-')" in page


# --- serving ----------------------------------------------------------------


def test_the_closed_sender_is_served_and_stays_out_of_the_index(client):
    response = client.get("/closed")
    assert response.status_code == 200
    assert 'name="robots" content="noindex, nofollow"' in response.text
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow"


def test_the_closed_sender_is_localised_like_every_other_page(client):
    ru = client.get("/closed", headers={"Accept-Language": "ru-RU,ru;q=0.9"})
    assert STRINGS["ru"]["modeClosedName"] in ru.text
    assert "@@" not in ru.text


def test_a_receiver_page_for_a_closed_address_is_the_same_document(client):
    # The page must reveal nothing about the throw before it asks — including
    # whether the address is one we have ever heard of.
    known = client.get(f"/{generate_address()}").text
    words = client.get("/basted-lily").text
    assert known == words


# --- privacy copy tells the truth -------------------------------------------


def test_privacy_says_which_pages_load_a_script_and_which_load_none(client):
    # "No third-party scripts" and "no scripts at all" are different claims and
    # only the first holds everywhere, so the page names the one script it does
    # load rather than making the broader claim.
    body = client.get("/privacy").text
    assert "loads no third-party scripts" not in body
    assert "analytics subdomain" in body
    assert "load no script at all" in body


def test_privacy_names_the_boundary_of_the_closed_mode(client):
    body = client.get("/privacy").text
    assert "AES-256-GCM" in body
    assert "does not protect you from" in body.lower()
    assert "source of the page" in body


def test_terms_describes_both_modes_and_the_price_of_the_closed_one(client):
    body = client.get("/terms").text
    assert "two-word code" in body
    assert "cannot recover a closed throw" in body
    assert "handed out" in body
