"""The closed sender's logic, executed.

The whole closed mode rests on one claim about this page: the text is encrypted
before it leaves, so the server is never handed the plaintext, not even for the
length of one request. Reading the source cannot establish that — the order of
`tdEncrypt` and `fetch` in the file says nothing about the order they run in,
and the two senders now share their surroundings, so a shared block wired the
wrong way would look right on the page. So the script is run, in node, against
a stub DOM and a `fetch` that keeps what it was given, and the assertions are
made against the actual request body.

The strongest of them closes the loop: the key that ends up in the fragment is
used, by the page's own crypto, to decrypt the body the page just posted. If
that yields the text the user typed, the pair really does work together.
"""

import json
import re
import shutil
import subprocess

import pytest

from app.pages import CLOSED_SENDER_PAGE

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is a development dependency")

SECRET = "wifi: hunter2 — и пароль от почты"

HARNESS = """
globalThis.window = globalThis;
window.isSecureContext = true;
window.location = { origin: 'https://throw.dog', href: 'https://throw.dog/closed' };

const store = {};
globalThis.localStorage = globalThis.sessionStorage = {
  getItem: function (k) { return k in store ? store[k] : null; },
  setItem: function (k, v) { store[k] = String(v); },
  removeItem: function (k) { delete store[k]; }
};
globalThis.navigator = {};

const posted = [];
const els = {};
const handlers = {};
globalThis.document = {
  getElementById: function (id) {
    if (!els[id]) {
      els[id] = {
        id: id, textContent: '', value: '', innerHTML: '', hidden: false,
        disabled: false, offsetWidth: 1,
        classList: { add: function () {}, remove: function () {} },
        addEventListener: function (event, fn) { handlers[id + ':' + event] = fn; },
        focus: function () {}
      };
    }
    return els[id];
  }
};

globalThis.fetch = function (url, options) {
  posted.push({ url: url, body: JSON.parse(options.body) });
  return Promise.resolve({
    status: 201, ok: true,
    json: function () { return Promise.resolve({ code: '9r6er8ieht7srq' }); }
  });
};

const SCENARIO = process.env.SCENARIO;
const SECRET = process.env.SECRET;

function settle() { return new Promise(function (r) { setTimeout(r, 200); }); }

async function main() {
  PAGE_SCRIPT();

  if (SCENARIO === 'throw') {
    els.text.value = SECRET;
    handlers['throw:click']();
  } else if (SCENARIO === 'paste_secret') {
    handlers['text:paste']({
      preventDefault: function () {},
      clipboardData: { getData: function () { return SECRET; } }
    });
  } else if (SCENARIO === 'paste_closed_link') {
    handlers['text:paste']({
      preventDefault: function () {},
      clipboardData: {
        getData: function () { return 'https://throw.dog/9r6er8ieht7srq#' + process.env.KEYISH; }
      }
    });
  }

  await settle();

  // Close the loop: take the key out of the URL the page produced and use it,
  // with the page's own crypto, on the body the page actually sent.
  let decrypted = null;
  const url = els.url.textContent;
  const at = url.indexOf('#');
  if (at >= 0 && posted.length === 1) {
    try {
      const key = await tdImportKey(url.slice(at + 1));
      decrypted = await tdDecrypt(key, posted[0].body.text);
    } catch (e) { decrypted = 'DECRYPT FAILED: ' + e; }
  }

  process.stdout.write(JSON.stringify({
    posts: posted.length,
    url: posted.length ? posted[0].url : null,
    body: posted.length ? posted[0].body : null,
    shownUrl: url,
    navigated: window.location.href,
    decrypted: decrypted,
    composeHidden: els.compose.hidden,
    doneHidden: els.done.hidden,
    error: els.error.textContent
  }));
}

main().catch(function (e) {
  process.stderr.write(String(e && e.stack));
  process.exit(1);
});
"""


@pytest.fixture(scope="module")
def script(tmp_path_factory):
    blocks = re.findall(r"<script>(.*?)</script>", CLOSED_SENDER_PAGE, re.S)
    assert len(blocks) == 1, "the closed sender must carry exactly one script"
    body = blocks[0]
    # Its main IIFE runs on load; wrap it so the harness installs its stubs first.
    wrapped = body.replace("(function () {", "function PAGE_SCRIPT() {(function () {", 1)
    wrapped = wrapped.rstrip().rstrip(";")
    assert wrapped.endswith("})()"), "unexpected shape for the page's IIFE"
    path = tmp_path_factory.mktemp("senderjs") / "sender.js"
    path.write_text(wrapped + ";}\n" + HARNESS, encoding="utf-8")
    return path


def run(script, scenario, **extra):
    env = {"SCENARIO": scenario, "SECRET": SECRET, "PATH": "/usr/bin:/bin"}
    env.update(extra)
    result = subprocess.run(
        [NODE, str(script)], capture_output=True, text=True, timeout=120, env=env
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("scenario", ["throw", "paste_secret"])
def test_the_server_is_never_handed_the_plaintext(script, scenario):
    # Both ways a throw is made — pressing the button and pasting — go through
    # the same send(), and neither may put the typed text on the wire.
    out = run(script, scenario)
    assert out["posts"] == 1
    assert out["url"] == "/api/throws"
    assert SECRET not in json.dumps(out["body"], ensure_ascii=False)
    assert out["body"]["text"] != SECRET


def test_the_request_says_which_format_it_is_in(script):
    # The server refuses an unknown scheme, so a sender that omitted or
    # misspelled this would produce an open throw holding ciphertext.
    assert run(script, "throw")["body"]["enc"] == "aes-gcm-v1"


def test_the_key_in_the_fragment_decrypts_what_was_posted(script):
    # The claim in full: this key and that body belong together, and together
    # they are the text the user typed.
    out = run(script, "throw")
    assert out["decrypted"] == SECRET


def test_the_key_rides_in_the_fragment_of_the_link_and_nowhere_else(script):
    out = run(script, "throw")
    shown = out["shownUrl"]
    assert shown.count("#") == 1
    address, key = shown.split("#")
    assert address.endswith("/9r6er8ieht7srq")
    # 32 bytes as unpadded base64url: no padding, and nothing needing escaping.
    assert len(key) == 43
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", key), key
    # And no part of it appears in what was sent.
    assert key not in json.dumps(out["body"])


def test_a_finished_throw_shows_the_link_instead_of_the_form(script):
    out = run(script, "throw")
    assert out["composeHidden"] is True
    assert out["doneHidden"] is False
    assert out["error"] == ""


def test_pasting_one_of_our_own_closed_links_opens_it_instead_of_sending_it(script):
    # The accident this prevents is the worst one available: a reader pastes the
    # link they were given into the compose box, and the key — the one thing we
    # promise never to receive — is uploaded as the body of a new throw.
    out = run(script, "paste_closed_link", KEYISH="A" * 43)
    assert out["posts"] == 0, "the key was sent to the server"
    assert out["navigated"] == "/9r6er8ieht7srq#" + "A" * 43
