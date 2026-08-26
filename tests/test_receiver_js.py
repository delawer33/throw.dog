"""The receiver page's logic, executed.

The guarantee this file exists for cannot be read off the page: *asking the
server for a throw is what consumes it*, so a reader who cannot possibly decrypt
must not ask. Checking that by looking at where `fetch` appears in the source is
worthless — the call sits inside a function defined above the branch that
decides whether to call it. So the script is run instead, in node, against a
counted `fetch` and a stub DOM, and the assertion is the one that matters: how
many times the server was contacted.

The scenarios are the accidents that actually happen to people: a link with the
fragment stripped by a chat client, a link wrapped mid-key by a mail client, a
key that is intact but from a different throw, and the ordinary happy path.
"""

import json
import re
import shutil
import subprocess

import pytest

from app.closedaddress import generate as generate_address
from app.pages import RECEIVER_PAGE

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is a development dependency")

CLOSED = generate_address()

HARNESS = """
globalThis.window = globalThis;
window.isSecureContext = true;

const calls = { fetch: 0, strip: 0 };
const els = {};
globalThis.document = {
  getElementById: function (id) {
    if (!els[id]) {
      els[id] = { textContent: '', className: '', hidden: false,
                  addEventListener: function () {} };
    }
    return els[id];
  }
};
globalThis.history = { replaceState: function () { calls.strip++; } };

const SCENARIO = process.env.SCENARIO;
const PATHNAME = process.env.PATHNAME;

async function setup() {
  // Build a real ciphertext with the page's own crypto, so the happy path is
  // exercised against genuine output rather than a fixture.
  const key = await tdNewKey();
  const payload = await tdEncrypt(key, 'wifi: hunter2');
  const encoded = await tdExportKey(key);
  const otherKey = await tdExportKey(await tdNewKey());

  let hash = '';
  let respond = () => ({ status: 200, ok: true, enc: 'aes-gcm-v1', text: payload });

  if (SCENARIO === 'no_key') { hash = ''; }
  else if (SCENARIO === 'bare_hash') { hash = '#'; }
  else if (SCENARIO === 'truncated_key') { hash = '#' + encoded.slice(0, 25); }
  else if (SCENARIO === 'junk_key') { hash = '#not a key at all'; }
  else if (SCENARIO === 'wrong_key') { hash = '#' + otherKey; }
  else if (SCENARIO === 'good_key') { hash = '#' + encoded; }
  else if (SCENARIO === 'gone') {
    hash = '#' + encoded;
    respond = () => ({ status: 404, ok: false });
  } else if (SCENARIO === 'network_down') {
    hash = '#' + encoded;
    respond = null;
  } else if (SCENARIO === 'open_code') {
    hash = '';
    respond = () => ({ status: 200, ok: true, text: 'plain as day' });
  }

  window.location = { hash: hash, pathname: PATHNAME, search: '' };
  globalThis.fetch = function () {
    calls.fetch++;
    if (respond === null) { return Promise.reject(new Error('offline')); }
    const r = respond();
    return Promise.resolve({
      status: r.status, ok: r.ok,
      json: function () {
        const body = { text: r.text };
        if (r.enc) { body.enc = r.enc; }
        return Promise.resolve(body);
      }
    });
  };
}

setup().then(function () {
  PAGE_SCRIPT();
  // Let every queued promise settle before reporting.
  return new Promise(function (resolve) { setTimeout(resolve, 150); });
}).then(function () {
  process.stdout.write(JSON.stringify({
    fetches: calls.fetch,
    strips: calls.strip,
    status: els.status ? els.status.textContent : null,
    statusClass: els.status ? els.status.className : null,
    shown: els.text ? els.text.textContent : null,
    resultHidden: els.result ? els.result.hidden : null,
    chip: els.chip ? els.chip.textContent : null
  }));
}).catch(function (e) {
  process.stderr.write(String(e && e.stack));
  process.exit(1);
});
"""


def _page_script() -> str:
    """The receiver page's inline script, lifted out of the served document."""
    blocks = re.findall(r"<script>(.*?)</script>", RECEIVER_PAGE, re.S)
    assert len(blocks) == 1, "the receiver page must carry exactly one script"
    return blocks[0]


@pytest.fixture(scope="module")
def script(tmp_path_factory):
    body = _page_script()
    # The page's script ends in an IIFE that runs on load; wrap it so the
    # harness can install its stubs first and then run it.
    wrapped = body.replace("(function () {", "function PAGE_SCRIPT() {(function () {", 1)
    wrapped = wrapped.rstrip().rstrip(";")
    assert wrapped.endswith("})()"), "unexpected shape for the page's IIFE"
    wrapped += ";}\n"
    path = tmp_path_factory.mktemp("receiverjs") / "receiver.js"
    path.write_text(wrapped + HARNESS, encoding="utf-8")
    return path


def run(script, scenario, pathname="/" + CLOSED):
    result = subprocess.run(
        [NODE, str(script)],
        capture_output=True,
        text=True,
        timeout=120,
        env={"SCENARIO": scenario, "PATHNAME": pathname, "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


T = None


@pytest.fixture(scope="module", autouse=True)
def strings():
    global T
    T = json.loads(re.search(r"var T = (\{.*?\});", RECEIVER_PAGE, re.S).group(1))


@pytest.mark.parametrize("scenario", ["no_key", "bare_hash", "truncated_key", "junk_key"])
def test_a_reader_who_cannot_decrypt_never_touches_the_throw(script, scenario):
    # Every way a key goes missing: never sent, an empty fragment, wrapped
    # mid-key by a mail client, or replaced by junk. All of them are locally
    # detectable, so all of them must cost nothing — the sender's correct link
    # has to still work afterwards.
    out = run(script, scenario)
    assert out["fetches"] == 0, f"{scenario} asked the server and spent the throw"
    assert out["status"] == T["keyMissing"]
    assert "still waiting" in out["status"], "and it must say the throw survived"


@pytest.mark.parametrize("scenario", ["no_key", "truncated_key"])
def test_an_unusable_key_leaves_the_url_intact_so_a_reload_can_work(script, scenario):
    # Nothing was consumed, so the reader may still open the whole link. Wiping
    # the fragment here would make that impossible in this tab.
    assert run(script, scenario)["strips"] == 0


def test_a_wrong_but_well_formed_key_spends_the_throw_and_says_so(script):
    # This one genuinely cannot be caught without asking: the key is the right
    # shape, just from another throw. So the throw IS spent, and the message
    # says that rather than inviting a pointless reload.
    out = run(script, "wrong_key")
    assert out["fetches"] == 1
    assert out["status"] == T["keyBad"]
    assert "used up" in out["status"]
    assert out["shown"] in (None, "")


def test_the_happy_path_shows_the_decrypted_text_and_wipes_the_key(script):
    out = run(script, "good_key")
    assert out["fetches"] == 1
    assert out["shown"] == "wifi: hunter2"
    assert out["resultHidden"] is False
    assert out["strips"] == 1, "the key must leave the address bar once it is spent"
    assert out["chip"] == T["chipClosed"]


def test_a_closed_throw_that_is_already_gone_says_nothing_here(script):
    out = run(script, "gone")
    assert out["fetches"] == 1
    assert out["status"] == T["notFound"]


def test_a_network_failure_keeps_the_key_so_refreshing_is_honest(script):
    # The message tells the reader to refresh. That advice is only true if the
    # key is still in the URL to refresh with.
    out = run(script, "network_down")
    assert out["fetches"] == 1
    assert out["strips"] == 0
    assert out["status"] == T["netRecv"]


def test_an_open_code_is_fetched_and_shown_without_any_key(script):
    out = run(script, "open_code", pathname="/basted-lily")
    assert out["fetches"] == 1
    assert out["shown"] == "plain as day"
    assert out["strips"] == 0


def test_the_three_outcomes_are_three_different_messages(script):
    missing = run(script, "no_key")["status"]
    bad = run(script, "wrong_key")["status"]
    gone = run(script, "gone")["status"]
    assert len({missing, bad, gone}) == 3
