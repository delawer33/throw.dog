import pytest
from fastapi.testclient import TestClient

from app.gatekeeper import Gatekeeper
from app.main import Settings, code_pseudonym, create_app, sanitize_log_path

# Zero delay on misses: the production one-second pause (and the longer tarpit
# pause) is an anti-guessing measure, not behaviour worth waiting for in tests.
TEST_SETTINGS = Settings(miss_delay_ms=0, gate_tarpit_delay_ms=0)


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


def test_noindex_header_is_on_private_responses_only(client):
    # Receiver pages are one-time secrets and the API is machinery: both stay
    # out of every index. The homepage and legal pages are public (launch).
    code = throw(client, "private")
    private = [
        client.get(f"/{code}"),
        client.get("/healthz"),
        client.post(f"/api/throws/{code}"),
        client.post("/api/throws/never-existed"),
    ]
    for response in private:
        assert response.headers["X-Robots-Tag"] == "noindex, nofollow"
    for response in (client.get("/"), client.get("/robots.txt")):
        assert "X-Robots-Tag" not in response.headers


def test_robots_txt_bans_only_the_api(client):
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert "Disallow: /api/" in response.text
    assert "Disallow: /\n" not in response.text


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_events_are_logged_without_the_throw_content(client, capsys):
    code = throw(client, "top secret payload")
    client.post(f"/api/throws/{code}")

    out = capsys.readouterr().out
    pseudonym = code_pseudonym(code)
    # The pair is still correlatable: created and read carry the same pseudonym.
    assert f"event=created code={pseudonym}" in out
    assert f"event=read code={pseudonym}" in out
    assert "ts=" in out
    assert "top secret payload" not in out


def test_the_raw_code_never_reaches_the_event_log(client, capsys):
    code = throw(client, "another secret")
    client.post(f"/api/throws/{code}")

    out = capsys.readouterr().out
    # The shared secret must never appear verbatim; only its hash prefix does.
    assert code not in out
    assert code_pseudonym(code) in out


def test_the_pseudonym_is_a_short_stable_hash_prefix():
    # Deterministic and short: same code -> same pseudonym, within a process.
    once = code_pseudonym("red-fox")
    again = code_pseudonym("red-fox")
    assert once == again
    assert once != code_pseudonym("blue-jay")
    assert len(once) == 12
    assert "red-fox" not in once


def test_the_pseudonym_is_keyed_so_it_cannot_be_precomputed_from_logs():
    # The code space is tiny (~1.09M), so a *plain* SHA-256 prefix is reversible
    # from the logs alone. The pseudonym must be keyed: the same code under two
    # different secrets yields two different pseudonyms.
    import hashlib

    under_one = code_pseudonym("red-fox", secret=b"secret-one")
    under_two = code_pseudonym("red-fox", secret=b"secret-two")
    assert under_one != under_two

    # Stable under a fixed key — an operator who pins the secret gets stable
    # cross-restart correlation.
    assert code_pseudonym("red-fox", secret=b"secret-one") == under_one

    # And it is genuinely keyed, not the old unsalted hash prefix an attacker
    # could tabulate offline.
    assert under_one != hashlib.sha256(b"red-fox").hexdigest()[:12]


def test_a_fixed_env_secret_flows_through_create_app_to_the_event_log(capsys):
    # THROW_LOG_HMAC_SECRET pins the key; the logged pseudonym must be the one
    # produced under that key (proving create_app wires the secret through).
    settings = Settings.from_env({"THROW_LOG_HMAC_SECRET": "operator-pinned", "THROW_MISS_DELAY_MS": "0"})
    with TestClient(create_app(settings)) as c:
        code = throw(c, "keyed by env")
        c.post(f"/api/throws/{code}")
    out = capsys.readouterr().out
    expected = code_pseudonym(code, secret=b"operator-pinned")
    assert f"event=created code={expected}" in out
    assert f"event=read code={expected}" in out


def test_the_access_log_path_is_pseudonymised_for_a_receiver_request():
    # uvicorn logs the request line verbatim; a receiver GET is `/{code}` and a
    # read POST is `/api/throws/{code}`. Neither may leak the code.
    receiver = sanitize_log_path("/red-fox")
    assert "red-fox" not in receiver
    assert receiver == "/" + code_pseudonym("red-fox")

    read = sanitize_log_path("/api/throws/red-fox?x=1")
    assert "red-fox" not in read
    assert read == "/api/throws/" + code_pseudonym("red-fox")

    # Code-free routes are logged untouched.
    for safe in ("/", "/healthz", "/robots.txt", "/api/throws"):
        assert sanitize_log_path(safe) == safe


def test_a_noncanonical_alias_pseudonymises_like_its_canonical_read():
    # The read path logs the *normalised* code, so the access-log path must
    # normalise before hashing too — otherwise `/api/throws/RED_FOX` would carry
    # a different pseudonym than its `event=read` line and the two streams could
    # not be correlated. The raw code still never appears either way.
    canonical = code_pseudonym("red-fox")

    read = sanitize_log_path("/api/throws/RED_FOX")
    assert "RED_FOX" not in read and "red-fox" not in read
    assert read == "/api/throws/" + canonical

    receiver = sanitize_log_path("/RED_FOX")
    assert "RED_FOX" not in receiver and "red-fox" not in receiver
    assert receiver == "/" + canonical


def test_an_aliased_read_correlates_with_its_create_across_the_two_log_streams(client, capsys):
    code = throw(client, "correlate me")
    adjective, noun = code.split("-")
    # Read via a non-canonical alias (uppercase + underscore).
    alias = f"{adjective.upper()}_{noun.upper()}"
    assert client.post(f"/api/throws/{alias}").status_code == 200

    out = capsys.readouterr().out
    pseudonym = code_pseudonym(code)
    # Event log: created and read of the same throw share one pseudonym...
    assert f"event=created code={pseudonym}" in out
    assert f"event=read code={pseudonym}" in out
    # ...and the access-log path for the aliased read agrees with it.
    assert sanitize_log_path(f"/api/throws/{alias}") == "/api/throws/" + pseudonym


def test_the_access_log_filter_redacts_the_code_in_the_request_line():
    # Exercise the real filter on a record shaped exactly as uvicorn builds it.
    import logging

    from app.main import _AccessLogRedactor

    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("1.2.3.4:5", "GET", "/red-fox", "1.1", 405),
        exc_info=None,
    )
    assert _AccessLogRedactor().filter(record) is True
    rendered = record.getMessage()
    assert "red-fox" not in rendered
    assert code_pseudonym("red-fox") in rendered


def test_the_redactor_is_installed_on_the_uvicorn_access_logger():
    import logging

    from app.main import _AccessLogRedactor

    access_logger = logging.getLogger("uvicorn.access")
    assert any(isinstance(f, _AccessLogRedactor) for f in access_logger.filters)


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


def test_oversized_body_is_rejected_without_buffering_it_all(client):
    # Ten megabytes of JSON: the limit must bite on the way in, not after
    # the whole flood is resident in memory.
    huge = '{"text":"' + "z" * (10 * 1024 * 1024) + '"}'

    response = client.post(
        "/api/throws", content=huge, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 413
    assert "too big" in response.json()["detail"]


def test_oversized_body_is_refused_on_its_declared_length_alone(client):
    # Content-Length is the cheapest possible check: no body read at all.
    response = client.post(
        "/api/throws",
        content=b"",
        headers={"Content-Type": "application/json", "Content-Length": str(50 * 1024 * 1024)},
    )

    assert response.status_code == 413


def test_malformed_body_is_a_plain_bad_request(client):
    assert client.post("/api/throws", content=b"not json").status_code == 400
    assert client.post("/api/throws", json={"txet": "typo"}).status_code == 400
    assert client.post("/api/throws", json={"text": 42}).status_code == 400


def test_a_read_under_tarpit_is_byte_identical_to_an_ordinary_miss():
    # A global threshold of one means a single recorded miss shuts the gate on
    # everyone. The tarpitted reply must be indistinguishable from a plain
    # miss, or the tarpit itself would leak "this code exists".
    gate = Gatekeeper(global_miss_threshold=1)
    app = create_app(TEST_SETTINGS, gatekeeper=gate)
    with TestClient(app) as c:
        code = throw(c, "still reachable while the gate is open")

        # A hit does not count against anyone: the read path still works.
        opened = c.post(f"/api/throws/{code}")
        assert opened.status_code == 200
        assert opened.json() == {"text": "still reachable while the gate is open"}

        ordinary_miss = c.post("/api/throws/never-existed")  # trips the global flood
        tarpitted = c.post("/api/throws/also-never-existed")  # served under tarpit

        assert ordinary_miss.status_code == tarpitted.status_code == 404
        assert ordinary_miss.text == tarpitted.text


def test_a_hammering_ip_gets_tarpitted_but_a_valid_read_still_lands_first():
    gate = Gatekeeper(miss_budget=3)
    app = create_app(TEST_SETTINGS, gatekeeper=gate)
    with TestClient(app) as c:
        code = throw(c, "beat the budget")
        assert c.post(f"/api/throws/{code}").json() == {"text": "beat the budget"}

        for _ in range(3):
            assert c.post("/api/throws/never-existed").status_code == 404
        # Budget spent: still a 404, but now from the tarpit, not the store.
        assert c.post("/api/throws/never-existed").status_code == 404


def test_a_valid_code_reads_even_when_the_ip_is_over_its_miss_budget():
    # The core use case: an abuser and an honest reader share one NAT'd IP. The
    # abuser burns the per-IP miss budget; the honest reader still holds a VALID
    # code and MUST get their throw. Gating a hit would deny honest readers —
    # exactly the defect this fix removes.
    gate = Gatekeeper(miss_budget=3)
    app = create_app(TEST_SETTINGS, gatekeeper=gate)
    with TestClient(app) as c:
        code = throw(c, "reach me from a burnt IP")

        # Burn the budget past its ceiling from this IP.
        for _ in range(5):
            assert c.post("/api/throws/never-existed").status_code == 404
        assert gate.allow("testclient") is False  # confirm the IP is over budget

        # The valid code still reads — the hit bypasses the gate entirely.
        landed = c.post(f"/api/throws/{code}")
        assert landed.status_code == 200
        assert landed.json() == {"text": "reach me from a burnt IP"}


def test_a_valid_code_reads_even_while_the_global_tarpit_is_engaged():
    # A global threshold of one means a single recorded miss shuts the door on
    # everyone. A holder of a valid code must still be served — hits never gate.
    gate = Gatekeeper(global_miss_threshold=1)
    app = create_app(TEST_SETTINGS, gatekeeper=gate)
    with TestClient(app) as c:
        code = throw(c, "reach me under the flood")

        assert c.post("/api/throws/never-existed").status_code == 404  # trip global
        assert gate.allow("anyone") is False  # confirm the global tarpit is on

        landed = c.post(f"/api/throws/{code}")
        assert landed.status_code == 200
        assert landed.json() == {"text": "reach me under the flood"}


def test_an_over_budget_miss_is_byte_identical_to_an_ordinary_miss():
    # The tarpit only lengthens the delay; the body must not change, or an
    # over-budget IP could tell a real code from a fake one by its reply bytes.
    gate = Gatekeeper(miss_budget=3)
    app = create_app(TEST_SETTINGS, gatekeeper=gate)
    with TestClient(app) as c:
        ordinary = c.post("/api/throws/never-existed")  # within budget
        for _ in range(4):
            c.post("/api/throws/never-existed")  # spend the budget
        assert gate.allow("testclient") is False
        tarpitted = c.post("/api/throws/still-never-existed")  # over budget

        assert ordinary.status_code == tarpitted.status_code == 404
        assert ordinary.text == tarpitted.text


def test_a_tarpitted_miss_sleeps_longer_than_an_ordinary_miss(monkeypatch):
    # Observe the delay via the injected sleep, not the wall clock: a tarpitted
    # miss must add the configured tarpit delay on top of the base miss delay.
    # The TestClient is used WITHOUT its context manager so the lifespan sweeper
    # (which also awaits asyncio.sleep) never starts and spins on the fake sleep.
    import app.main as main

    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(main.asyncio, "sleep", fake_sleep)

    gate = Gatekeeper(miss_budget=3)
    settings = Settings(miss_delay_ms=1000, gate_tarpit_delay_ms=4000)
    app = create_app(settings, gatekeeper=gate)
    c = TestClient(app)
    c.post("/api/throws/never-existed")
    assert slept[-1] == pytest.approx(1.0)  # base miss delay only

    for _ in range(4):
        c.post("/api/throws/never-existed")  # push over budget
    assert slept[-1] == pytest.approx(5.0)  # base + tarpit extra


def test_the_tarpit_delay_comes_from_env():
    settings = Settings.from_env({"THROW_GATE_TARPIT_DELAY_MS": "2500"})
    assert settings.gate_tarpit_delay_ms == 2500

    default = Settings.from_env({})
    assert default.gate_tarpit_delay_ms == 4000


def test_trusted_proxy_gives_each_forwarded_ip_its_own_budget():
    # Behind a proxy every request shares one socket peer; the limiter must
    # instead charge the forwarded client, so two forwarded IPs are independent.
    gate = Gatekeeper(miss_budget=3)
    settings = Settings(miss_delay_ms=0, trusted_proxy=True)
    app = create_app(settings, gatekeeper=gate)
    with TestClient(app) as c:
        for _ in range(4):
            c.post("/api/throws/never-existed", headers={"X-Forwarded-For": "203.0.113.7"})
        c.post("/api/throws/never-existed", headers={"X-Forwarded-For": "198.51.100.9"})

    # State is keyed by the forwarded IPs, not the shared socket peer.
    assert "203.0.113.7" in gate._ip_misses
    assert "198.51.100.9" in gate._ip_misses


def test_cf_connecting_ip_wins_when_behind_a_trusted_proxy():
    gate = Gatekeeper()
    app = create_app(Settings(miss_delay_ms=0, trusted_proxy=True), gatekeeper=gate)
    with TestClient(app) as c:
        c.post(
            "/api/throws/never-existed",
            headers={"CF-Connecting-IP": "203.0.113.50", "X-Forwarded-For": "10.9.9.9"},
        )
    assert "203.0.113.50" in gate._ip_misses
    assert "10.9.9.9" not in gate._ip_misses


def test_forwarded_header_is_ignored_when_not_behind_a_proxy():
    # trusted_proxy defaults to False: the header is attacker-controlled and
    # must never move the budget off the real socket peer.
    gate = Gatekeeper()
    app = create_app(Settings(miss_delay_ms=0), gatekeeper=gate)
    with TestClient(app) as c:
        c.post("/api/throws/never-existed", headers={"X-Forwarded-For": "203.0.113.7"})
    assert "203.0.113.7" not in gate._ip_misses
    assert "testclient" in gate._ip_misses  # the TestClient socket peer


def test_proxy_settings_come_from_env():
    settings = Settings.from_env(
        {"THROW_TRUSTED_PROXY": "true", "THROW_FORWARDED_HEADER": "X-Real-IP"}
    )
    assert settings.trusted_proxy is True
    assert settings.forwarded_header == "X-Real-IP"

    off = Settings.from_env({})
    assert off.trusted_proxy is False
    assert off.forwarded_header == "X-Forwarded-For"


def test_a_full_store_answers_busy_rather_than_failing(client):
    from app.throwstore import ThrowStore

    full = create_app(TEST_SETTINGS, store=ThrowStore(ttl_seconds=600, max_entries=1))
    with TestClient(full) as busy_client:
        assert busy_client.post("/api/throws", json={"text": "first"}).status_code == 201

        response = busy_client.post("/api/throws", json={"text": "second"})

    assert response.status_code == 503
    assert "busy" in response.json()["detail"]
