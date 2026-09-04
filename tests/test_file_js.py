"""The open sender's file path, executed.

Reading the page cannot tell you whether a 12 MB file goes up as three chunks
in order, or whether an oversized one is refused before a byte moves — both are
properties of what runs, not of what is written. So the script is run in node
against a stub File and a fetch that records every request, and the assertions
are made against the sequence of requests that actually happened.
"""

import json
import re
import shutil
import subprocess

import pytest

from app.filestore import CHUNK_BYTES, OPEN_MAX_BYTES
from app.pages import SENDER_PAGE

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is a development dependency")

HARNESS = """
globalThis.window = globalThis;
window.isSecureContext = true;
window.location = { origin: 'https://throw.dog', href: 'https://throw.dog/' };
window.crypto = { subtle: {} };

const store = {};
globalThis.localStorage = globalThis.sessionStorage = {
  getItem: function (k) { return k in store ? store[k] : null; },
  setItem: function (k, v) { store[k] = String(v); },
  removeItem: function (k) { delete store[k]; }
};
globalThis.navigator = {};
// The analytics shim lives in its own <script> on the page; here it is a no-op,
// exactly as it is for a visitor whose tracker never loaded.
globalThis.tdTrack = function () {};

const requests = [];
const els = {};
const handlers = {};
const card = {
  addEventListener: function (event, fn) { handlers['card:' + event] = fn; }
};

function element(id) {
  return {
    id: id, textContent: '', value: '', innerHTML: '', hidden: false,
    disabled: false, offsetWidth: 1, files: null,
    style: {},
    classList: { add: function () {}, remove: function () {} },
    addEventListener: function (event, fn) { handlers[id + ':' + event] = fn; },
    closest: function () { return card; },
    setAttribute: function () {},
    focus: function () {}
  };
}
globalThis.document = {
  getElementById: function (id) {
    if (!els[id]) { els[id] = element(id); }
    return els[id];
  }
};

const FAIL_AT = process.env.FAIL_AT || '';

globalThis.fetch = function (url, options) {
  const method = (options && options.method) || 'GET';
  const record = { url: url, method: method };
  if (method === 'PUT') { record.bytes = options.body.size; }
  else if (options && options.body) { record.body = JSON.parse(options.body); }
  requests.push(record);
  if (FAIL_AT && url.indexOf(FAIL_AT) === 0 && method === 'POST') {
    return Promise.resolve({ status: Number(process.env.FAIL_CODE || 413), ok: false });
  }
  if (method === 'PUT') { return Promise.resolve({ status: 204, ok: true }); }
  if (url === '/api/files') {
    return Promise.resolve({
      status: 201, ok: true,
      json: function () { return Promise.resolve({ upload: 'u', chunk: TD_CHUNK }); }
    });
  }
  return Promise.resolve({
    status: 201, ok: true,
    json: function () { return Promise.resolve({ code: 'basted-lily' }); }
  });
};

// A stand-in File: only the four things the page touches.
function fakeFile(size, name, type) {
  return {
    size: size, name: name, type: type,
    slice: function (from, to) { return { size: to - from, from: from }; }
  };
}

function settle() { return new Promise(function (r) { setTimeout(r, 250); }); }

async function main() {
  PAGE_SCRIPT();

  const size = Number(process.env.SIZE);
  const file = fakeFile(size, process.env.NAME || 'holiday.mp4', 'video/mp4');

  if (process.env.SCENARIO === 'drop') {
    handlers['card:drop']({
      preventDefault: function () {},
      dataTransfer: { files: [file] }
    });
  } else if (process.env.SCENARIO === 'drop_two') {
    handlers['card:drop']({
      preventDefault: function () {},
      dataTransfer: { files: [file, fakeFile(10, 'second.txt', 'text/plain')] }
    });
  } else if (process.env.SCENARIO === 'pick') {
    els.file.files = [file];
    handlers['file:change']();
  }

  await settle();

  const at = document.getElementById;
  process.stdout.write(JSON.stringify({
    requests: requests,
    code: at('codebig').textContent,
    composeHidden: at('compose').hidden,
    doneHidden: at('done').hidden,
    progHidden: at('prog').hidden,
    progName: at('progname').textContent,
    error: at('error').textContent,
    errorHidden: at('error').hidden
  }));
}

main().catch(function (e) {
  process.stderr.write(String(e && e.stack));
  process.exit(1);
});
"""


@pytest.fixture(scope="module")
def script(tmp_path_factory):
    blocks = re.findall(r"<script>(.*?)</script>", SENDER_PAGE, re.S)
    # The homepage carries the remembered-mode redirect, the analytics shim and
    # the main script; the last is the one with the page's logic.
    body = blocks[-1]
    # Its main IIFE starts at column zero — the only thing on the page that
    # does, which is what makes it findable now that the shared file code has
    # callbacks of its own.
    opener = re.search(r"^\(function \(\) \{", body, re.M)
    assert opener, "unexpected shape for the page's IIFE"
    wrapped = (
        body[: opener.start()]
        + "function PAGE_SCRIPT() {"
        + body[opener.start() :]
    )
    wrapped = wrapped.rstrip().rstrip(";")
    assert wrapped.endswith("})()"), "unexpected shape for the page's IIFE"
    path = tmp_path_factory.mktemp("filejs") / "sender.js"
    path.write_text(wrapped + ";}\n" + HARNESS, encoding="utf-8")
    return path


def run(script, scenario, size, **extra):
    env = {"SCENARIO": scenario, "SIZE": str(size), "PATH": "/usr/bin:/bin"}
    env.update(extra)
    result = subprocess.run(
        [NODE, str(script)], capture_output=True, text=True, timeout=120, env=env
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_a_dropped_file_is_thrown_without_anyone_pressing_anything(script):
    # Dropping a file is the same gesture as pasting a text: the throw happens,
    # there is no second step to find.
    out = run(script, "drop", 1000)

    assert [r["method"] for r in out["requests"]] == ["POST", "PUT", "POST"]
    assert out["requests"][0]["url"] == "/api/files"
    assert out["requests"][0]["body"]["size"] == 1000
    assert out["requests"][0]["body"]["name"] == "holiday.mp4"
    assert out["code"] == "basted-lily"
    assert out["doneHidden"] is False


def test_picking_a_file_from_the_dialog_throws_it_the_same_way(script):
    out = run(script, "pick", 1000)
    assert [r["method"] for r in out["requests"]] == ["POST", "PUT", "POST"]


def test_a_big_file_goes_up_in_chunks_in_order_and_whole(script):
    size = CHUNK_BYTES * 2 + 1234
    out = run(script, "drop", size)

    puts = [r for r in out["requests"] if r["method"] == "PUT"]
    assert [r["url"] for r in puts] == [
        "/api/files/u/0",
        "/api/files/u/1",
        "/api/files/u/2",
    ]
    assert [r["bytes"] for r in puts] == [CHUNK_BYTES, CHUNK_BYTES, 1234]
    assert sum(r["bytes"] for r in puts) == size
    assert out["requests"][0]["body"]["chunks"] == 3


def test_an_oversized_file_is_refused_before_a_byte_of_it_moves(script):
    out = run(script, "drop", OPEN_MAX_BYTES + 1)

    assert out["requests"] == [], "nothing was sent"
    assert "25 MB" in out["error"]
    assert out["errorHidden"] is False


def test_an_empty_file_is_refused_with_its_own_reason(script):
    out = run(script, "drop", 0)
    assert out["requests"] == []
    assert out["error"] and "25 MB" not in out["error"]


def test_dropping_two_files_throws_neither(script):
    # Silently taking the first would be worse than refusing: the sender walks
    # away believing both went.
    out = run(script, "drop_two", 1000)
    assert out["requests"] == []


def test_the_progress_card_replaces_the_form_and_names_the_file(script):
    out = run(script, "drop", 1000)
    # It is hidden again by the end — the result card has taken its place — but
    # it was the file's own name that was on it.
    assert out["progName"] == "holiday.mp4"
    assert out["progHidden"] is True
    assert out["composeHidden"] is True


def test_a_refusal_from_the_server_puts_the_form_back_with_a_reason(script):
    out = run(script, "drop", 1000, FAIL_AT="/api/files", FAIL_CODE="413")

    assert out["progHidden"] is True
    assert out["composeHidden"] is False, "the sender can try again"
    assert "25 MB" in out["error"]


def test_an_upload_flood_from_this_address_is_said_in_our_own_words(script):
    out = run(script, "drop", 1000, FAIL_AT="/api/files", FAIL_CODE="429")
    assert out["error"] and "25 MB" not in out["error"]
    assert out["composeHidden"] is False
