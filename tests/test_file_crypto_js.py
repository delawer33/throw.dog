"""The closed mode's file format, actually executed.

A file cannot be one encrypt call, so the closed mode's promise rests on a
layout — a preamble, a sealed header, and one sealed chunk per piece — that two
browsers have to agree on with nothing in between able to help them. Reading the
page proves none of it. So both ends are run in node: the file is assembled
exactly as the sender assembles it, then handed to the receiver's own
``tdFetchClosedFile`` through a ``fetch`` that serves byte ranges out of memory.

What is asserted is what a person's outcome depends on: that the file comes back
byte for byte with its name; that the name is nowhere in the bytes we would
hold; and that every way of mangling the file that a relay could perform —
flipping a byte, swapping two chunks, cutting the tail off — fails loudly
instead of saving something broken.
"""

import json
import shutil
import subprocess

import pytest

from app.main import ENC_FILE_SCHEME, closed_file_ceiling
from app.pages import (
    _CRYPTO_JS,
    _DOWNLOAD_JS,
    _FILE_CRYPTO_JS,
    _FILE_SIZE_JS,
    CLOSED_SENDER_PAGE,
)

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    NODE is None,
    reason="node is a development dependency; without it the file format is unproven",
)

DRIVER = """
// A chunk of sixteen bytes rather than four megabytes: the layout is what is
// under test, and a small chunk exercises more of it per second.
TD_CHUNK = 16;

const NAME = 'отчёт за квартал.pdf';
const MIME = 'application/pdf';
const PLAIN = new Uint8Array(16 * 3 + 5);
for (let i = 0; i < PLAIN.length; i++) { PLAIN[i] = (i * 7) % 256; }

function slices(bytes) {
  const out = [];
  for (let at = 0; at < bytes.length; at += TD_CHUNK) {
    out.push(bytes.slice(at, Math.min(at + TD_CHUNK, bytes.length)));
  }
  return out;
}

// The sender's side, assembled exactly as the page assembles it.
async function seal(key) {
  const prefix = tdNewPrefix();
  const pieces = slices(PLAIN);
  const head = await tdSealHeader(key, prefix, pieces.length, {
    name: NAME, mime: MIME, size: PLAIN.length
  });
  const sealed = [head];
  for (let i = 0; i < pieces.length; i++) {
    sealed.push(await tdSealChunk(key, prefix, i + 1, pieces.length, pieces[i]));
  }
  return { pieces: sealed, chunks: pieces.length };
}

function join(pieces) {
  const total = pieces.reduce((sum, piece) => sum + piece.length, 0);
  const out = new Uint8Array(total);
  let at = 0;
  for (const piece of pieces) { out.set(piece, at); at += piece.length; }
  return out;
}

// The relay, reduced to what the receiver actually uses of it: byte ranges.
function serve(wire) {
  globalThis.fetch = function (url, options) {
    const spec = options.headers['Range'].replace('bytes=', '').split('-');
    const from = Number(spec[0]), to = Number(spec[1]);
    if (from >= wire.length) {
      return Promise.resolve({ ok: false, status: 416 });
    }
    const slice = wire.slice(from, Math.min(to + 1, wire.length));
    return Promise.resolve({
      ok: true, status: 206,
      arrayBuffer: function () { return Promise.resolve(slice.buffer.slice(
        slice.byteOffset, slice.byteOffset + slice.byteLength)); }
    });
  };
}

async function fetched(key, wire) {
  serve(wire);
  const got = await tdFetchClosedFile(key, '/api/files/t/t', wire.length,
                                      function () {});
  const bytes = new Uint8Array(await got.blob.arrayBuffer());
  return { name: got.name, size: got.size, bytes: Array.from(bytes) };
}

async function rejects(key, wire) {
  try {
    await fetched(key, wire);
    return 'opened';
  } catch (e) { return 'rejected'; }
}

async function main() {
  const out = {};
  const key = await tdNewKey();
  const { pieces, chunks } = await seal(key);
  const wire = join(pieces);

  out.chunks = chunks;
  out.plainSize = PLAIN.length;
  out.wireSize = wire.length;
  out.chunkSize = TD_CHUNK;

  // Nothing of the file — not its bytes, not its name — is in what we hold.
  const asText = Buffer.from(wire).toString('latin1');
  out.nameInWire = asText.indexOf('otchyot') >= 0
    || asText.indexOf(Buffer.from(NAME, 'utf8').toString('latin1')) >= 0;
  out.plainInWire = asText.indexOf(
    Buffer.from(PLAIN).toString('latin1')) >= 0;

  const got = await fetched(key, wire);
  out.name = got.name;
  out.size = got.size;
  out.roundTrip = got.bytes.length === PLAIN.length
    && got.bytes.every((b, i) => b === PLAIN[i]);

  // A different key: rejected, never rubbish.
  out.wrongKey = await rejects(await tdNewKey(), wire);

  // One flipped byte in the middle chunk.
  const flipped = wire.slice();
  flipped[flipped.length - 20] ^= 1;
  out.tampered = await rejects(key, flipped);

  // Two chunks of equal size swapped: each still authenticates on its own, so
  // only the chunk number in the AAD can catch this.
  const swapped = pieces.slice();
  const a = swapped[1]; swapped[1] = swapped[2]; swapped[2] = a;
  out.reordered = await rejects(key, join(swapped));

  // The tail cut off, and the count in the preamble lowered to match — the
  // shape a relay quietly truncating a file would produce.
  const short = pieces.slice(0, pieces.length - 1);
  const shortWire = join(short);
  shortWire[8] = 0; shortWire[9] = 0; shortWire[10] = 0;
  shortWire[11] = chunks - 1;
  out.truncated = await rejects(key, shortWire);

  process.stdout.write(JSON.stringify(out));
}

main().catch(function (e) {
  process.stderr.write(String(e && e.stack));
  process.exit(1);
});
"""


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    path = tmp_path_factory.mktemp("filecryptojs") / "format.js"
    path.write_text(
        _CRYPTO_JS + _FILE_SIZE_JS + _FILE_CRYPTO_JS + _DOWNLOAD_JS + DRIVER,
        encoding="utf-8",
    )
    done = subprocess.run(
        [NODE, str(path)], capture_output=True, text=True, timeout=120
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_a_closed_file_comes_back_byte_for_byte_with_its_name(result):
    assert result["roundTrip"] is True
    assert result["name"] == "отчёт за квартал.pdf"
    assert result["size"] == result["plainSize"]


def test_neither_the_bytes_nor_the_name_are_in_what_we_hold(result):
    # The name is metadata to a server and content to a person, so in this mode
    # it lives inside the ciphertext with everything else.
    assert result["plainInWire"] is False
    assert result["nameInWire"] is False


def test_a_wrong_key_fails_instead_of_saving_rubbish(result):
    assert result["wrongKey"] == "rejected"


def test_one_flipped_byte_is_caught(result):
    assert result["tampered"] == "rejected"


def test_two_chunks_swapped_are_caught(result):
    # Each chunk authenticates perfectly on its own; only its number in the AAD
    # says where it belonged.
    assert result["reordered"] == "rejected"


def test_a_truncated_tail_is_caught(result):
    # And this is why the count is in the AAD as well as the number: with a
    # matching count in the preamble, every remaining chunk would otherwise
    # open, and the reader would save a file quietly missing its end.
    assert result["truncated"] == "rejected"


# --- the two ends agree about the numbers -----------------------------------


def test_the_page_and_the_server_name_the_same_format():
    assert f"var TD_FILE_ENC = '{ENC_FILE_SCHEME}';" in _FILE_CRYPTO_JS
    assert ENC_FILE_SCHEME in CLOSED_SENDER_PAGE


def test_the_declared_chunk_count_is_the_one_the_server_expects(result):
    # The page sends the header plus one chunk per piece; the server refuses
    # anything else, so a disagreement here is a closed mode that cannot throw.
    plain, chunk = result["plainSize"], result["chunkSize"]
    assert result["chunks"] == -(-plain // chunk)


def test_the_wire_size_stays_inside_the_ceiling_the_server_allows(result):
    # Same arithmetic on both sides, or a file the sender was told was fine is
    # refused after it has already been encrypted.
    plain, chunks = result["plainSize"], result["chunks"]
    assert result["wireSize"] <= closed_file_ceiling(plain, chunks)
