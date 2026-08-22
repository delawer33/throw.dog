"""The pages are the product on a bad connection: keep them small and inline.

Speed is a design rule (``model/08-design.md``): each document must weigh under
100 KB on its own, with no external CSS/JS/font/image/CDN request to make it
whole.
"""

from app.pages import RECEIVER_PAGE, SENDER_PAGE

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
