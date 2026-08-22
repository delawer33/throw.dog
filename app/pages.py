"""The two HTML pages, inlined.

No framework, no build step, no external requests — the whole point is that a
phone on a bad connection gets one small document and can act on it.

The receiver page is identical for every code: it carries no throw content and
fetches it with a POST. Link previews and prefetchers issue GETs, and a GET
must never burn a one-shot throw.
"""

from __future__ import annotations

from typing import Final

_STYLE: Final = """
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 1.25rem;
    font: 1.15rem/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    max-width: 44rem; margin-inline: auto;
  }
  h1 { font-size: 1.25rem; font-weight: 600; margin: 0 0 .75rem; }
  h1 span { opacity: .55; font-weight: 400; }
  textarea {
    width: 100%; min-height: 45vh; padding: .75rem;
    font: inherit; font-size: 1.1rem;
    border: 2px solid currentColor; border-radius: .5rem;
    background: transparent; color: inherit;
  }
  button {
    font: inherit; font-size: 1.1rem; padding: .6rem 1.4rem; margin-top: .75rem;
    border: 2px solid currentColor; border-radius: .5rem;
    background: transparent; color: inherit; cursor: pointer;
  }
  .code {
    font-size: clamp(1.8rem, 9vw, 3.2rem); font-weight: 700;
    word-break: break-all; line-height: 1.15; margin: 1rem 0;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  }
  .hint { opacity: .7; font-size: .95rem; }
  .error { color: #c22; font-weight: 600; }
  pre {
    white-space: pre-wrap; word-break: break-word;
    padding: .75rem; border: 2px solid currentColor; border-radius: .5rem;
    font-size: 1.05rem; margin: 0;
  }
  [hidden] { display: none !important; }
"""

_HEAD: Final = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>throw.dog</title>
<style>%s</style>
</head>
""" % _STYLE

SENDER_PAGE: Final = _HEAD + """<body>
<h1>throw.dog <span>&mdash; paste text, get a code</span></h1>

<div id="compose">
  <textarea id="text" autofocus placeholder="Paste or type text here. Pasting throws it right away."></textarea>
  <div><button id="throw" type="button">throw</button></div>
  <p class="hint">Lives 10 minutes. Dies the moment it is read once.</p>
  <p id="error" class="error" hidden></p>
</div>

<div id="done" hidden>
  <p>Type this on the other device:</p>
  <p class="code" id="url"></p>
  <p class="hint">The text is deleted as soon as that page loads it.</p>
  <div><button id="again" type="button">throw something else</button></div>
</div>

<script>
(function () {
  var text = document.getElementById('text');
  var error = document.getElementById('error');
  var compose = document.getElementById('compose');
  var done = document.getElementById('done');
  var url = document.getElementById('url');
  var busy = false;

  function fail(message) {
    error.textContent = message;
    error.hidden = false;
  }

  function send(value) {
    if (busy) { return; }
    if (!value || !value.trim()) { fail('Nothing to throw yet.'); return; }
    busy = true;
    error.hidden = true;
    fetch('/api/throws', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: value })
    }).then(function (response) {
      if (response.status === 413) { throw new Error('That text is too big — 64 KB is the limit.'); }
      if (response.status === 400) { throw new Error('Nothing to throw yet.'); }
      if (!response.ok) { throw new Error('Could not throw that. Try again.'); }
      return response.json();
    }).then(function (data) {
      url.textContent = window.location.origin.replace(/^https?:\\/\\//, '') + '/' + data.code;
      compose.hidden = true;
      done.hidden = false;
    }).catch(function (err) {
      fail(err && err.message ? err.message : 'Network problem. Try again.');
    }).then(function () {
      busy = false;
    });
  }

  text.addEventListener('paste', function (event) {
    var clipboard = event.clipboardData || window.clipboardData;
    if (!clipboard) { return; }
    var pasted = clipboard.getData('text');
    if (!pasted || !pasted.trim()) { return; }
    event.preventDefault();
    text.value = pasted;
    send(pasted);
  });

  document.getElementById('throw').addEventListener('click', function () {
    send(text.value);
  });

  document.getElementById('again').addEventListener('click', function () {
    text.value = '';
    done.hidden = true;
    compose.hidden = false;
    error.hidden = true;
    text.focus();
  });
})();
</script>
</body>
</html>
"""

RECEIVER_PAGE: Final = _HEAD + """<body>
<h1>throw.dog</h1>

<p id="status">Fetching&hellip;</p>

<div id="result" hidden>
  <pre id="text"></pre>
  <div><button id="copy" type="button">Copy</button></div>
  <p class="hint">This throw is gone now — it existed for one read.</p>
</div>

<script>
(function () {
  var status = document.getElementById('status');
  var result = document.getElementById('result');
  var target = document.getElementById('text');
  var code = window.location.pathname.replace(/^\\/+/, '').replace(/\\/+$/, '');

  fetch('/api/throws/' + encodeURIComponent(code), { method: 'POST' })
    .then(function (response) {
      if (response.status === 404) { throw new Error('no such throw — expired, already read, or never existed'); }
      if (!response.ok) { throw new Error('Something went wrong. Reload to try again.'); }
      return response.json();
    })
    .then(function (data) {
      target.textContent = data.text;
      status.hidden = true;
      result.hidden = false;
    })
    .catch(function (err) {
      status.textContent = err && err.message ? err.message : 'Network problem. Reload to try again.';
    });

  document.getElementById('copy').addEventListener('click', function () {
    var button = document.getElementById('copy');
    var value = target.textContent;
    function ok() { button.textContent = 'Copied'; setTimeout(function () { button.textContent = 'Copy'; }, 1500); }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(value).then(ok, select);
    } else {
      select();
    }
    function select() {
      var range = document.createRange();
      range.selectNodeContents(target);
      var selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      button.textContent = 'Press Ctrl+C / long-press to copy';
    }
  });
})();
</script>
</body>
</html>
"""

ROBOTS_TXT: Final = "User-agent: *\nDisallow: /\n"
