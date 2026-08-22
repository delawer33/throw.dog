import pytest
from fastapi.testclient import TestClient

from app.main import Settings, create_app

# Zero delay on misses: the production one-second pause is an anti-guessing
# measure, not behaviour worth waiting for in tests.
TEST_SETTINGS = Settings(miss_delay_ms=0)


@pytest.fixture()
def client():
    with TestClient(create_app(TEST_SETTINGS)) as test_client:
        yield test_client


def throw(client, text: str) -> str:
    response = client.post("/api/throws", json={"text": text})
    assert response.status_code == 201, response.text
    return response.json()["code"]


def test_text_crosses_over_and_the_throw_dies_after_one_read(client):
    code = throw(client, "wifi password: hunter2")

    first = client.post(f"/api/throws/{code}")
    assert first.status_code == 200
    assert first.json() == {"text": "wifi password: hunter2"}

    second = client.post(f"/api/throws/{code}")
    assert second.status_code == 404


def test_every_kind_of_miss_looks_the_same(client):
    code = throw(client, "already gone")
    client.post(f"/api/throws/{code}")

    already_read = client.post(f"/api/throws/{code}")
    never_existed = client.post("/api/throws/zesty-walrus")
    not_even_a_code = client.post("/api/throws/wibble-wobble")

    responses = [already_read, never_existed, not_even_a_code]
    assert {r.status_code for r in responses} == {404}
    assert len({r.text for r in responses}) == 1, "one body for every kind of miss"


def test_the_code_in_the_url_is_forgiving(client):
    code = throw(client, "typed by hand")
    adjective, noun = code.split("-")

    response = client.post(f"/api/throws/{adjective.upper()}{noun.upper()}")
    assert response.status_code == 200
    assert response.json() == {"text": "typed by hand"}


def test_a_space_separated_code_works_too(client):
    code = throw(client, "read from a screen")
    adjective, noun = code.split("-")

    response = client.post(f"/api/throws/{adjective} {noun}")
    assert response.status_code == 200
    assert response.json() == {"text": "read from a screen"}


def test_text_over_the_size_limit_is_refused(client):
    oversized = "x" * (65536 + 1)
    response = client.post("/api/throws", json={"text": oversized})
    assert response.status_code == 413
    assert "65536" in response.json()["detail"], "the message names the limit"

    at_the_limit = client.post("/api/throws", json={"text": "x" * 65536})
    assert at_the_limit.status_code == 201


def test_the_limit_counts_utf8_bytes_not_characters(client):
    # 2-byte characters: 33_000 of them are under the character count but over
    # the byte limit.
    response = client.post("/api/throws", json={"text": "é" * 33_000})
    assert response.status_code == 413

    ok = client.post("/api/throws", json={"text": "é" * 30_000})
    assert ok.status_code == 201


def test_empty_text_is_not_a_throw(client):
    assert client.post("/api/throws", json={"text": ""}).status_code == 400
    assert client.post("/api/throws", json={"text": "   \n "}).status_code == 400


def test_loading_the_receiver_page_does_not_burn_the_throw(client):
    code = throw(client, "survives a prefetcher")

    page = client.get(f"/{code}")
    assert page.status_code == 200
    assert "survives a prefetcher" not in page.text

    assert client.post(f"/api/throws/{code}").json() == {"text": "survives a prefetcher"}


def test_the_receiver_page_is_the_same_for_any_code(client):
    known = client.get("/red-fox").text
    unknown = client.get("/zesty-walrus").text
    garbage = client.get("/wibble-wobble").text
    assert known == unknown == garbage


def test_noindex_header_is_on_every_response(client):
    code = throw(client, "private")
    responses = [
        client.get("/"),
        client.get(f"/{code}"),
        client.get("/healthz"),
        client.get("/robots.txt"),
        client.post(f"/api/throws/{code}"),
        client.post("/api/throws/never-existed"),
    ]
    for response in responses:
        assert response.headers["X-Robots-Tag"] == "noindex, nofollow"


def test_robots_txt_bans_everything(client):
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert "Disallow: /" in response.text


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_events_are_logged_without_the_throw_content(client, capsys):
    code = throw(client, "top secret payload")
    client.post(f"/api/throws/{code}")

    out = capsys.readouterr().out
    assert f"event=created code={code}" in out
    assert f"event=read code={code}" in out
    assert "ts=" in out
    assert "top secret payload" not in out


def test_default_settings_work_without_env(monkeypatch):
    for name in ("THROW_TTL_SECONDS", "THROW_MAX_BYTES", "THROW_MISS_DELAY_MS"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings.from_env()
    assert settings.ttl_seconds == 600
    assert settings.max_bytes == 65536
    assert settings.miss_delay_ms == 1000


def test_settings_come_from_env_when_present():
    settings = Settings.from_env(
        {"THROW_TTL_SECONDS": "30", "THROW_MAX_BYTES": "1024", "THROW_MISS_DELAY_MS": "0"}
    )
    assert (settings.ttl_seconds, settings.max_bytes, settings.miss_delay_ms) == (30.0, 1024, 0)
