"""Soft-launch feedback fixes: the wish box and the fetch-by-code form.

The wish box (inside the Pro panel) POSTs free-form text to /api/feedback,
which appends it to a volume-backed file — same privacy posture as the Pro
emails: body-only transport, file-only storage, never a URL or a log.

The fetch-by-code form lives on the sender page because soft-launch showed
that editing the URL by hand is not obvious to everyone.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import Settings, append_feedback, create_app
from app.pages import STRINGS, render_sender


@pytest.fixture()
def feedback_file(tmp_path):
    return tmp_path / "sub" / "feedback.txt"


@pytest.fixture()
def client(feedback_file):
    settings = Settings(miss_delay_ms=0, feedback_path=str(feedback_file))
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_valid_feedback_is_appended_to_the_configured_file(client, feedback_file):
    response = client.post("/api/feedback", json={"text": "make it purple"})
    assert response.status_code == 201, response.text
    assert response.json() == {"ok": True}
    assert "make it purple" in feedback_file.read_text(encoding="utf-8")


def test_each_record_is_one_line_even_with_newlines_inside(client, feedback_file):
    client.post("/api/feedback", json={"text": "line one\nline two\ttabbed"})
    client.post("/api/feedback", json={"text": "second record"})

    lines = feedback_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert "line one\\nline two\\ttabbed" in lines[0]
    assert "second record" in lines[1]


@pytest.mark.parametrize("bad", ["", "   ", None, 42, "x" * 2001])
def test_junk_feedback_is_rejected_and_never_written(client, feedback_file, bad):
    response = client.post("/api/feedback", json={"text": bad})
    assert response.status_code == 400
    assert not feedback_file.exists()


def test_a_missing_text_field_is_a_clean_error(client, feedback_file):
    response = client.post("/api/feedback", json={"nope": 1})
    assert response.status_code == 400
    assert not feedback_file.exists()


def test_an_oversized_body_is_cut_off_early(client, feedback_file):
    response = client.post(
        "/api/feedback",
        content=b'{"text": "' + b"x" * 40000 + b'"}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert not feedback_file.exists()


def test_append_feedback_escapes_backslashes(tmp_path):
    target = tmp_path / "fb.txt"
    append_feedback(str(target), "a\\b\nc")
    line = target.read_text(encoding="utf-8").splitlines()[0]
    assert line.endswith("a\\\\b\\nc")


def test_the_feedback_panel_and_fetch_form_are_on_the_sender_page():
    page = render_sender("en")
    # Feedback panel: its own chip + card, separate from the Pro fake-door.
    assert 'id="fbchip"' in page
    assert 'id="fbdoor"' in page
    assert 'id="fbtext"' in page
    assert "/api/feedback" in page
    # Fetch-by-code form: input + button + JS normalisation to /two-words.
    assert 'id="getcode"' in page
    assert 'id="getgo"' in page


def test_the_new_strings_exist_in_both_locales():
    keys = {
        "getLabel",
        "getPlaceholder",
        "getBtn",
        "fbChip",
        "fbTitle",
        "fbIntro",
        "fbPlaceholder",
        "fbSubmit",
        "fbThanks",
        "fbEmpty",
    }
    for locale in ("en", "ru"):
        assert keys <= set(STRINGS[locale]), f"{locale} is missing new strings"
        for key in keys:
            assert STRINGS[locale][key].strip()
