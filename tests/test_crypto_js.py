"""The closed mode's crypto, actually executed.

Everything else about the closed mode can be checked by reading the page. This
cannot: "encrypted on the device" is a claim about what the code *does*, and the
only honest way to check it is to run it. The block is deliberately standalone
(no DOM, no page state) so node — which exposes the same WebCrypto, btoa/atob
and TextEncoder as a browser — can run it unchanged.

What is worth asserting here is not "AES was called". It is the three things a
user's outcome depends on: that what the sender writes the receiver reads back,
that a wrong or tampered payload *fails* rather than yielding rubbish (which is
what lets the receiver say "this key did not fit"), and that the size of what
goes over the wire is exactly what the server's limit was computed from.
"""

import json
import shutil
import subprocess

import pytest

from app.closedaddress import LENGTH as ADDRESS_LENGTH
from app.main import encrypted_ceiling
from app.pages import _CRYPTO_JS, _QR_JS

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    NODE is None,
    reason="node is a development dependency; without it the browser crypto is unproven",
)

DRIVER = """
async function main() {
  const out = {};
  const text = 'wifi: hunter2 — Ünïcode, \\n newlines, and \\t tabs';

  const key = await tdNewKey();
  const payload = await tdEncrypt(key, text);
  const exported = await tdExportKey(key);

  out.exportedKey = exported;
  out.payload = payload;
  out.payloadHasPlaintext = payload.indexOf('hunter2') >= 0;

  // The receiver's path: it only ever has the encoded key from the fragment.
  const imported = await tdImportKey(exported);
  out.roundTrip = await tdDecrypt(imported, payload);

  // A different key must fail, not decode to something.
  const other = await tdExportKey(await tdNewKey());
  try {
    await tdDecrypt(await tdImportKey(other), payload);
    out.wrongKey = 'decrypted';
  } catch (e) { out.wrongKey = 'rejected'; }

  // A tampered ciphertext must fail too: GCM authenticates it.
  const bytes = tdUnB64(payload);
  bytes[bytes.length - 1] ^= 1;
  try {
    await tdDecrypt(await tdImportKey(exported), tdB64(bytes));
    out.tampered = 'decrypted';
  } catch (e) { out.tampered = 'rejected'; }

  // Junk where a key should be must be rejected, not crash the page.
  for (const junk of ['', 'not-a-key', exported.slice(0, 10)]) {
    try { await tdImportKey(junk); out.junkKey = 'accepted'; }
    catch (e) { out.junkKey = out.junkKey || 'rejected'; }
  }

  // What a full-size throw actually weighs on the wire, measured not derived.
  const sizes = {};
  for (const n of [0, 1, 100, 65536]) {
    sizes[n] = (await tdEncrypt(key, 'x'.repeat(n))).length;
  }
  out.sizes = sizes;

  process.stdout.write(JSON.stringify(out));
}
main().catch(function (e) { process.stderr.write(String(e && e.stack)); process.exit(1); });
"""


@pytest.fixture(scope="module")
def crypto(tmp_path_factory):
    script = tmp_path_factory.mktemp("cryptojs") / "roundtrip.js"
    script.write_text(_CRYPTO_JS + DRIVER, encoding="utf-8")
    result = subprocess.run(
        [NODE, str(script)], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_what_the_sender_encrypts_the_receiver_reads_back(crypto):
    assert crypto["roundTrip"] == "wifi: hunter2 — Ünïcode, \n newlines, and \t tabs"


def test_the_server_never_sees_the_plaintext(crypto):
    assert crypto["payloadHasPlaintext"] is False


def test_the_key_is_url_fragment_safe_and_unpadded(crypto):
    # It rides in the fragment of a link, so it must survive being copied,
    # pasted and put in a QR without escaping. 32 bytes as base64url is 43
    # characters; padding would only add a character that needs escaping.
    key = crypto["exportedKey"]
    assert len(key) == 43
    assert "=" not in key and "+" not in key and "/" not in key
    assert all(char.isalnum() or char in "-_" for char in key)


def test_a_wrong_key_fails_instead_of_producing_rubbish(crypto):
    # This is what lets the receiver distinguish "this key did not fit" from
    # "nothing here" — three different situations need three different messages.
    assert crypto["wrongKey"] == "rejected"


def test_a_tampered_payload_fails(crypto):
    # We hold the ciphertext, so we could alter it. GCM makes that detectable
    # rather than silent, which is the reason for choosing it over plain CTR.
    assert crypto["tampered"] == "rejected"


def test_junk_in_place_of_a_key_is_rejected_not_crashed_on(crypto):
    assert crypto["junkKey"] == "rejected"


def test_the_wire_size_is_what_the_servers_limit_was_computed_from(crypto):
    # The server allows a closed throw to be bigger by exactly the base64 and
    # GCM overhead, so that the *visible* limit is the same in both modes. If
    # the browser's output ever grew past that arithmetic, a text well inside
    # the stated limit would start being refused — so the two are pinned here.
    for plaintext_bytes, measured in crypto["sizes"].items():
        assert measured == encrypted_ceiling(int(plaintext_bytes))


# --- both halves, end to end ------------------------------------------------


ENCRYPT_DRIVER = """
async function main() {
  const key = await tdNewKey();
  const payload = await tdEncrypt(key, process.argv[2]);
  process.stdout.write(JSON.stringify({
    payload: payload, key: await tdExportKey(key), enc: TD_ENC
  }));
}
main().catch(function (e) { process.stderr.write(String(e)); process.exit(1); });
"""

DECRYPT_DRIVER = """
async function main() {
  const key = await tdImportKey(process.argv[2]);
  process.stdout.write(await tdDecrypt(key, process.argv[3]));
}
main().catch(function (e) { process.stderr.write(String(e)); process.exit(1); });
"""


def _run(script, *args):
    result = subprocess.run(
        [NODE, str(script), *args], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_a_closed_throw_survives_the_whole_trip(tmp_path):
    """The one test that crosses every seam at once.

    A real browser-side encryption, through the real HTTP surface, back out and
    decrypted again — and with it, the two claims that only hold if all the
    pieces agree: that the sender's ``enc`` value is the one the server accepts,
    and that what the server hands the receiver is still decryptable.

    It also pins the thing that matters most and is easiest to lose in a
    refactor: at no point does the server hold the plaintext.
    """
    from fastapi.testclient import TestClient

    from app.main import Settings, create_app

    encrypt = tmp_path / "encrypt.js"
    decrypt = tmp_path / "decrypt.js"
    encrypt.write_text(_CRYPTO_JS + ENCRYPT_DRIVER, encoding="utf-8")
    decrypt.write_text(_CRYPTO_JS + DECRYPT_DRIVER, encoding="utf-8")

    secret = "postgres://user:hunter2@db.internal:5432/prod"
    sent = json.loads(_run(encrypt, secret))

    client = TestClient(create_app(Settings(miss_delay_ms=0)))
    created = client.post(
        "/api/throws", json={"text": sent["payload"], "enc": sent["enc"]}
    )
    assert created.status_code == 201, created.text
    address = created.json()["code"]

    fetched = client.post(f"/api/throws/{address}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["enc"] == sent["enc"]
    assert secret not in body["text"], "the server never held the plaintext"

    # The receiver's half: the key came from the fragment, which we never sent.
    assert _run(decrypt, sent["key"], body["text"]) == secret

    # And it is gone.
    assert client.post(f"/api/throws/{address}").status_code == 404


# --- the QR has to hold the whole thing -------------------------------------


QR_DRIVER = """
const url = process.argv[2];
const svg = qrSVG(url);
process.stdout.write(JSON.stringify({ length: url.length, empty: svg === '' }));
"""


def test_a_closed_link_fits_in_the_qr(tmp_path):
    """The closed mode leads with the QR, and the QR generator fails quietly.

    It supports versions 1-4 only and returns nothing at all when the payload
    is too long — so a link one character over the limit would not raise, it
    would render an empty box on the one screen that has no other way to deliver
    the throw. The address length was chosen against this budget; this is the
    test that keeps it honest, including the ``#`` and the 43-character key.
    """
    script = tmp_path / "qr.js"
    script.write_text(_QR_JS + QR_DRIVER, encoding="utf-8")

    url = "https://throw.dog/" + "x" * ADDRESS_LENGTH + "#" + "k" * 43
    result = json.loads(_run(script, url))
    assert result["empty"] is False, f"a {result['length']}-char closed link has no QR"

    # And it is genuinely near the edge, so the margin is a decision rather
    # than luck: one more character than version 4 can hold produces nothing.
    over = json.loads(_run(script, "https://throw.dog/" + "x" * 61))
    assert over["length"] == 79
    assert over["empty"] is True
