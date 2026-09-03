# throw.dog

Move a piece of text between devices in seconds. Paste it, get two words —
say them out loud or type them on the other device. Or use an encrypted
link when you can deliver one.

**https://throw.dog**

- No accounts, no database, nothing on disk: throws live in process memory,
  are read **once**, and vanish after 10 minutes untouched.
- **Open throw** — the server holds your plaintext; in exchange you get a
  two-word code (`basted lily`) you can dictate across a room or type on a
  keyboard you don't trust with your logins.
- **Closed throw** — encrypted in your browser (AES-256-GCM, WebCrypto);
  the key rides in the URL fragment, which browsers never send to servers.
  We only ever hold ciphertext. The cost: no two-word code — you can't say
  a key out loud — so it's link and QR only.

Why both modes exist, and why a closed throw can't have a spoken code, is
written down in [docs/adr/](docs/adr/) (Russian) — short answer: a key
derived from two words would be ~20 bits, and that's theater, not E2E.

## How it works

```
browser ── HTTPS ──> Caddy ──> FastAPI app
                                 └── ThrowStore: dict in RAM, TTL, one-shot take
```

- `app/throwstore.py` — put/take with atomic one-time read and TTL sweep.
- `app/codewords.py` — ~1M two-word codes, prefix-free, dictated-friendly.
- `app/closedaddress.py` — closed-throw addresses; start with a digit, so
  they can never collide with word codes and a receiver without a key never
  even asks the server (asking is what spends a throw).
- `app/gatekeeper.py` — per-IP miss budget + global tarpit against code
  enumeration; hits bypass the gate, misses are byte-identical and slow.
- `app/pages.py` — every page inline (CSS/JS/SVG/QR), no build step, no
  third-party code on any page where a key is born or lives.
- `app/csp.py` — the Content-Security-Policy is computed from the bytes of
  the page being sent, so the inline-script hashes can never go stale.
- `app/landings.py` — the search landings: one page per query, each a
  working copy of the homepage rather than a doorway. English at the root,
  Russian under `/ru/`, paired with `hreflang`.
- Codes never reach logs in the clear (keyed HMAC pseudonyms).

## Two languages, two sets of addresses

`/` is always English, `/ru/` is always Russian, and neither reads
`Accept-Language` — a page that picks its language from a request header can
only be indexed in the language the crawler asked for, and the other version
exists unseen ([ADR 0004](docs/adr/0004-yazyk-eto-adres.md)). The noindex
working pages (`/closed`, `/{code}`) still follow the browser, and say so
with `Vary`.

The link preview image at `/og.png` is served from memory; redraw it by
rendering `app/assets/og.source.html` at 1200×630 with headless Chrome.

## Run it locally

```
python -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/pytest                       # test suite (needs node for the JS tests)
.venv/bin/uvicorn app.main:app --reload
```

## Self-host

`docker compose up -d` with a `.env` from `.env.example` and a domain
pointed at the box — Caddy fetches certificates itself (`Caddyfile.acme`).
Operational notes: [DEPLOY.md](DEPLOY.md) (Russian). Optional self-hosted
Umami analytics lives behind the `analytics` compose profile.

## Contributing

Issues and PRs welcome. `pre-commit install` sets up the gitleaks hook —
this is a public repo, secrets must never touch the history. Run
`.venv/bin/pytest` before pushing; CI runs the suite plus a full-history
secret scan.

## License

[MIT](LICENSE)
