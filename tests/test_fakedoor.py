"""The Pro fake-door: a chip reveals a "coming soon" panel that captures emails.

The endpoint appends interested emails to a volume-backed file. It validates
minimally (a fake-door signup is not an auth flow) and never puts the email in a
URL or a log — it goes only to the configured file.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import Settings, create_app
from app.pages import STRINGS, render_sender


@pytest.fixture()
def emails_file(tmp_path):
    return tmp_path / "sub" / "pro-emails.txt"


@pytest.fixture()
def client(emails_file):
    settings = Settings(miss_delay_ms=0, pro_emails_path=str(emails_file))
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_a_valid_email_is_appended_to_the_configured_file(client, emails_file):
    response = client.post("/api/pro-interest", json={"email": "dog@throw.dog"})
    assert response.status_code == 201, response.text
    assert response.json() == {"ok": True}

    # The parent dir is created on demand and the email lands in the file.
    contents = emails_file.read_text(encoding="utf-8")
    assert "dog@throw.dog" in contents


def test_multiple_signups_each_get_their_own_line(client, emails_file):
    client.post("/api/pro-interest", json={"email": "a@example.com"})
    client.post("/api/pro-interest", json={"email": "b@example.com"})

    lines = emails_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert any("a@example.com" in line for line in lines)
    assert any("b@example.com" in line for line in lines)


@pytest.mark.parametrize(
    "bad",
    ["", "not-an-email", "@nolocal.com", "nodomain@", "has space@x.com", "a@b@c.com"],
)
def test_an_invalid_email_is_rejected_and_never_written(client, emails_file, bad):
    response = client.post("/api/pro-interest", json={"email": bad})
    assert response.status_code == 400
    assert not emails_file.exists(), "nothing is written for a bad email"


def test_an_over_long_email_is_rejected(client, emails_file):
    oversized = "x" * 250 + "@e.com"  # > 254 chars
    response = client.post("/api/pro-interest", json={"email": oversized})
    assert response.status_code == 400
    assert not emails_file.exists()


def test_a_missing_email_field_is_a_clean_error(client, emails_file):
    response = client.post("/api/pro-interest", json={"nope": 1})
    assert response.status_code == 400
    assert not emails_file.exists()


def test_the_pro_strings_exist_in_both_locales():
    pro_keys = {
        "proChip",
        "proTitle",
        "proPerks",
        "proEmailPlaceholder",
        "proSubmit",
        "proThanks",
        "proBadEmail",
        "proNet",
    }
    for locale in ("en", "ru"):
        assert pro_keys <= set(STRINGS[locale]), f"{locale} is missing Pro strings"
        for key in pro_keys:
            assert STRINGS[locale][key].strip()


def test_the_price_line_is_localised():
    assert "$4/mo" in render_sender("en")
    assert "$4/мес" in render_sender("ru")


def test_the_chip_and_form_are_on_the_sender_page():
    page = render_sender("en")
    assert 'id="prochip"' in page
    assert 'id="proemail"' in page
    assert '/api/pro-interest' in page
    # Funnel hooks exist for slice 7's Umami wiring, without the snippet itself.
    assert 'data-ev="pro_click"' in page
    assert 'data-ev="pro_email"' in page
