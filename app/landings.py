"""The SEO landings: query-shaped front doors to the same product.

A landing is a variant of the homepage under one search query (CONTEXT.md), not
an article: the headline and a short prose card answer the query's intent, and
the working throw form sits right there. Two clusters, one per mode. The device
cluster ("send text from pc to phone") renders the open sender; the secret
cluster ("one time secret") renders the closed sender — which means the secret
landings inherit the no-network-code shell of ADR 0003 by construction: a key
can be born on them, so they load no analytics and no script from anywhere.
That is the deliberate price of putting the real form on the page instead of a
button to it, and the CSP is computed from each rendered page's bytes like
everywhere else.

Landings are written only for what the product already does today — a lied-to
search intent costs more than early indexation buys — so file-transfer queries
wait for the file release.

Two languages, on separate URLs: English at the root, Russian under ``/ru/``.
Separate URLs and not one address that guesses, because a page that changes
language by request header can only ever be indexed in the language the
crawler happens to ask for — the other one exists and is invisible. Where a
page has a counterpart in the other language the two name each other with
``hreflang``, and the Russian set is smaller on purpose: it covers the queries
Russian searchers actually type, not a translation of the English list.

Each page's copy answers its own intent in its own words — the shared skeleton
is the form and the shell, never the prose. The Russian pages are written, not
translated, for the same reason. Cross-links stay inside a cluster and inside a
language; the clusters meet only through the homepage footer.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Final

from app.pages import JSON_LD, OG_CARD, lang_switch, render_landing


@dataclass(frozen=True, slots=True)
class Landing:
    slug: str
    #: <title> and og:title — the query, answered, with the brand at the end.
    title: str
    #: meta/og description: what a searcher sees under the blue link.
    description: str
    #: H1 halves: ``tagline_a`` plain, ``tagline_b`` in the mustard sticker.
    tagline_a: str
    tagline_b: str
    #: The one-liner under the H1, replacing the homepage's.
    sub: str
    #: True → the closed sender renders (secret cluster, ADR 0003 shell).
    closed: bool
    #: The prose card, ``<h2>/<p>`` sections. No scheme'd URLs on closed pages.
    body: str
    #: UI language of the whole page. Russian pages live under ``/ru/``.
    lang: str = "en"
    #: The slug of this page's counterpart in the other language, when one
    #: exists. Only a genuine counterpart may be named: hreflang is a claim
    #: that these two pages are the same page for a different reader, and a
    #: false pair teaches the crawler to distrust the true ones.
    alternate: str | None = None
    #: The day this page's copy or links last really changed — its sitemap
    #: ``lastmod``. Per page, because a blanket bump claims every URL moved.
    updated: str = "2026-09-21"

    @property
    def path(self) -> str:
        return f"/ru/{self.slug}" if self.lang == "ru" else f"/{self.slug}"

    @property
    def url(self) -> str:
        return f"https://throw.dog{self.path}"


LANDINGS: Final[tuple[Landing, ...]] = (
    # --- device cluster (open mode) ------------------------------------------
    Landing(
        slug="send-text-from-pc-to-phone",
        alternate="perekinut-tekst-s-kompa-na-telefon",
        title="Send Text from PC to Phone — No Login, No App | throw.dog",
        description=(
            "Paste text on your PC, get a two-word code and a QR, open it on "
            "your phone. No account, no app, no cable — and the text deletes "
            "itself after one read."
        ),
        tagline_a="Send text from",
        tagline_b="PC to phone",
        sub=(
            "Paste your text below — you get a two-word code and a QR. "
            "Type the code on your phone, and the text is there."
        ),
        closed=False,
        body="""    <h2>How it works</h2>
    <p>Paste the text into the box above — pasting throws it right away (typed
    it by hand? press throw). You get two short words — like
    <code>red-fox</code> — and a QR. On your phone, either scan the QR with
    the camera, or open throw.dog in any browser and type the two words.
    That's it: the text appears on the phone, usually in under ten seconds
    including the typing. A note, an address, a whole message — if it's text,
    it throws.</p>

    <h2>No login, no app, no cable</h2>
    <p>The usual ways to send copied text from a PC to a phone all want
    something first: emailing yourself wants your inbox open on both ends,
    messengers want you signed in on the second device, cables want to be
    found. This is just a website on both devices. Nothing to install, no
    account to create, nothing to pair.</p>

    <h2>It cleans up after itself</h2>
    <p>A throw is read once and then it's gone — the moment your phone fetches
    the text, the code stops working, and an unread throw evaporates on its own
    after 10 minutes. Nothing is stored, so there is nothing to go back and
    delete.</p>

    <h2>Works the other way too</h2>
    <p>The same trick moves text from the phone back to the PC: throw on the
    phone, type the two words on the computer. Text up to 64&nbsp;KB — notes,
    addresses, snippets of code, whole paragraphs.</p>""",
    ),
    Landing(
        slug="copy-paste-between-devices",
        title="Copy and Paste Between Devices — Any Browser, No Setup | throw.dog",
        description=(
            "A cross-device clipboard that works between Windows, Mac, Linux, "
            "Android and iPhone: paste on one device, read on the other. No "
            "shared account, no pairing, nothing to install."
        ),
        tagline_a="Copy &amp; paste",
        tagline_b="between devices",
        sub=(
            "Paste on this device — get a two-word code and a QR — open it on "
            "the other one. Works across any mix of systems."
        ),
        closed=False,
        body="""    <h2>The clipboard that ignores ecosystems</h2>
    <p>Copying and pasting between devices works beautifully — as long as both
    devices belong to the same company and the same account. Apple's clipboard
    reaches other Apple devices on your Apple ID; Windows syncs to Android
    through apps that both want you signed in. The moment your mix is a work
    Windows machine and a personal iPhone, or a Mac and an Android, or a Linux
    box and anything at all, the built-in ways stop copying.</p>

    <h2>This one is just a website</h2>
    <p>Paste into the box above — the paste itself throws it — and on the
    other device open throw.dog and type the two words (or scan the QR). Copy
    and paste from computer to phone, phone to computer, computer to
    computer: it works across devices, entirely online, browser to browser —
    which is why the mix of systems doesn't matter, and why it works on a
    machine where you can't install anything.</p>

    <h2>Not a clipboard manager</h2>
    <p>Nothing is synced and nothing is kept. One throw carries one piece of
    text, up to 64&nbsp;KB, is read exactly once, and expires in 10 minutes if
    nobody picks it up. It's the paste-it-across move, without the history a
    synced clipboard quietly accumulates.</p>""",
    ),
    Landing(
        slug="send-link-from-pc-to-phone",
        alternate="otpravit-ssylku-s-kompyutera-na-telefon",
        title="Send a Link from PC to Phone — Scan a QR, It Opens | throw.dog",
        description=(
            "Move a URL from your computer to your phone in seconds: paste the "
            "link, scan the QR with the phone camera, tap. No login, no "
            "messaging yourself."
        ),
        tagline_a="Send a link from",
        tagline_b="PC to phone",
        sub=(
            "Paste the URL below — scan the QR with your phone's camera — the "
            "link is on the phone, ready to open."
        ),
        closed=False,
        body="""    <h2>The two-second version</h2>
    <p>Paste the URL into the box above — pasting throws it right away. Point
    your phone's camera at the QR that appears: the phone opens the throw,
    and the link is there to tap or copy. No typing at all on the phone — the
    camera does the reading, on iPhone and Android alike.</p>

    <h2>Instead of messaging yourself</h2>
    <p>The usual way to send a URL from a PC to a phone is to email it to
    yourself or drop it into a chat with yourself — which means logging into
    your mail or messenger on whatever machine you're at, and leaving the link
    sitting in that history forever. Here there's no account on either end,
    and the throw erases itself after one read or 10 minutes, whichever comes
    first.</p>

    <h2>No camera handy?</h2>
    <p>The two-word code works too: open throw.dog in the phone's browser and
    type the words. Same throw, same result — and it goes in the other
    direction just as well, phone to PC.</p>""",
    ),
    Landing(
        slug="send-text-from-phone-to-computer",
        alternate="skinut-tekst-s-telefona-na-kompyuter",
        title="Send Text from Phone to Computer — No Cable, No Login | throw.dog",
        description=(
            "Type or paste text on your phone, get a two-word code, and enter "
            "it on the computer at throw.dog. Works on locked-down work "
            "machines — it's just a website, nothing to install."
        ),
        tagline_a="Send text from",
        tagline_b="phone to computer",
        sub=(
            "Paste your text below on the phone — then on the computer, open "
            "throw.dog and type the two-word code into the fetch box."
        ),
        closed=False,
        body="""    <h2>How it works, in this direction</h2>
    <p>On the phone: type the text above and press throw — or just paste it,
    pasting throws right away. You get two short words. On the computer: open
    throw.dog and type those two words into the <i>Got a code?</i> box. The
    message appears on the big screen, ready to copy. Ten seconds, give or
    take your typing.</p>

    <h2>Made for the locked-down work computer</h2>
    <p>The classic version of this problem is a corporate machine where you
    can't install anything, can't plug in a personal phone, and don't want to
    log into your personal mail or messengers just to move one address or one
    snippet. A website you can type two words into is the whole requirement
    here — and that's all this is.</p>

    <h2>Nothing left behind</h2>
    <p>That matters double on a shared or monitored machine: a throw is read
    once and gone, an unread one dies in 10 minutes, and there's no account
    involved — so there's no history to sign out of and nothing to clean up
    afterwards.</p>""",
    ),
    # --- secret cluster (closed mode, ADR 0003 shell) -------------------------
    Landing(
        slug="send-password-securely-one-time",
        alternate="odnorazovaya-ssylka-s-parolem",
        title="Send a Password Securely — One-Time Link, Encrypted in Your Browser | throw.dog",
        description=(
            "Share a password over a link that works once and dies in 10 "
            "minutes. Encrypted on your device with AES-256-GCM — the key "
            "stays in the link, the server only ever holds ciphertext."
        ),
        tagline_a="Send a password",
        tagline_b="securely",
        sub=(
            "Paste the password below — it is encrypted right here in your "
            "browser, and you get a one-time link and QR to hand over."
        ),
        closed=True,
        body="""    <h2>Why not just text it?</h2>
    <p>A password dropped into chat or email stays there: in both histories,
    in both backups, on however many devices those accounts are signed into,
    for years. The link this page gives you works exactly once and stops
    existing after 10 minutes either way — so what's left in the chat
    afterwards is a dead link, not the password. Free, online, no account on
    either end.</p>

    <h2>Encrypted before it leaves your device</h2>
    <p>Your browser encrypts the password on this page with AES-256-GCM before
    anything is sent. The decryption key travels only in the part of the link
    after the <code>#</code>, which browsers never send to any server — so the
    server holds ciphertext it cannot read, and neither can we. This page also
    loads no script from the network, not even our own analytics, so every
    line of code that touches your secret arrived in this one document.</p>

    <h2>One read, and honesty about it</h2>
    <p>The first time the link is opened, the throw is handed out and
    destroyed — even if the opener's key turns out wrong. We can't tell
    whether decryption succeeded on their side, and waiting to be told would
    be a way to make one secret readable twice. If the link is lost, nothing
    is recoverable, by anyone, including us. That's the deal, stated up
    front.</p>

    <h2>Handing it over in person?</h2>
    <p>Use the QR instead of the link: the other person scans it from your
    screen, and the key never enters any chat at all.</p>""",
    ),
    Landing(
        slug="one-time-secret",
        title="One-Time Secret Link — Read Once, Then Gone | throw.dog",
        description=(
            "Create a one-time secret link: encrypted in your browser, opens "
            "exactly once, self-destructs after 10 minutes either way. No "
            "account, no ads, no trace."
        ),
        tagline_a="One-time secret:",
        tagline_b="reads once",
        sub=(
            "Paste the secret below — it is encrypted in this tab, and the "
            "link you get opens exactly once."
        ),
        closed=True,
        body="""    <h2>What one-time actually means here</h2>
    <p>The link works on its first opening and never again — and «opening»
    is counted strictly. The instant the server hands the ciphertext out, it
    deletes it; we don't wait to hear whether the reader decrypted it
    successfully, because a service that waits can be lied to and made to
    serve the secret twice. One-time means one time even when that's
    inconvenient.</p>

    <h2>Ten minutes, on purpose</h2>
    <p>An unopened secret self-destructs after 10 minutes. That's short by the
    standards of secret-sharing sites — deliberately. A secret link that stays
    live for days is a secret sitting in someone's inbox, waiting. Ten minutes
    covers «I'm sending it to you right now», which is what a one-time secret
    is actually for, and leaves nothing lying around for later.</p>

    <h2>What the server sees</h2>
    <p>Ciphertext, and only ciphertext. The secret is encrypted in your browser
    on this page (AES-256-GCM), and the key rides in the fragment of the link —
    after the <code>#</code> — which no browser sends to any server. This page
    loads no network scripts at all, so the code doing the encrypting is all in
    the document you already received.</p>

    <h2>No account, no ads, no trail</h2>
    <p>Nothing to sign up for on either end, no ads, no third-party trackers,
    and no archive of your secrets anywhere — there is nothing to archive.
    The fastest way to share a secret message is also the shortest: paste,
    throw, hand over the link.</p>""",
    ),
    Landing(
        slug="self-destructing-note",
        alternate="odnorazovaya-zapiska",
        title="Self-Destructing Note or Message — Gone After One Read | throw.dog",
        description=(
            "Write a self-destructing note or message online: one read or "
            "10 minutes, whichever comes first. Encrypted on your device — "
            "nobody, including us, can read it or bring it back."
        ),
        tagline_a="Notes that",
        tagline_b="self-destruct",
        sub=(
            "Type the note below — it is encrypted in this tab, and the link "
            "you get survives exactly one reading."
        ),
        closed=True,
        body="""    <h2>Actually destroyed, not marked as deleted</h2>
    <p>A note here lives only in the server's memory — it is never written to
    disk in the first place. It is erased the instant it is read, and an
    unread note erases itself after 10 minutes. There's no trash folder, no
    soft delete, no backup where a copy lingers: destruction is the storage
    model, not a cleanup job.</p>

    <h2>And unreadable even while it exists</h2>
    <p>Before the note leaves this page, your browser encrypts it, and the key
    exists only in the link you get — in the fragment after the
    <code>#</code>, which browsers keep to themselves. For its whole short
    life on the server the note is ciphertext without a key. We couldn't read
    it if we were asked to.</p>

    <h2>A page you can take at its word</h2>
    <p>«Encrypted in your browser» is only as good as the page doing it, so
    this page plays by a strict rule: no script loaded from the network runs
    here — no analytics, no fonts, no third-party anything. Everything that
    touches your note is in the document your browser already fetched, and
    the page's security policy makes the browser enforce that rule rather
    than trust our manners.</p>

    <h2>Note, message, text — one tool</h2>
    <p>Call it a self-destructing message, a disappearing note, a self-deleting
    note or a one-time note — people search for all of them, and they all
    mean this: text that exists for one reader and then doesn't. Unlike the
    timed messages inside Telegram, WhatsApp or iMessage, this one needs no
    app on either side and no shared contact: it's a website, the link or QR
    opens in any browser, and the other person never learns your number.</p>

    <h2>When it's the right tool</h2>
    <p>A door code for the guest, a Wi-Fi password for the visitor, the thing
    you'd rather say once and have disappear. Self-destructing note or
    self-destructing message — either way it works online, in any browser,
    with nothing to install. Write it, hand over the link or the QR, done — the
    note does its own shredding.</p>""",
    ),
    Landing(
        slug="privnote-alternative",
        alternate="analog-privnote",
        updated="2026-10-04",
        title="Privnote Alternative — No Ads, No Loaded Scripts, Open Source | throw.dog",
        description=(
            "A Privnote alternative that shows its work: one-time encrypted "
            "notes with zero ads and zero loaded scripts on the note pages, a "
            "QR for handing secrets over in person — and public source code."
        ),
        tagline_a="The Privnote",
        tagline_b="alternative",
        sub=(
            "Paste the note below — encrypted in this tab, delivered by a "
            "one-time link or QR, gone in 10 minutes."
        ),
        closed=True,
        body="""    <h2>What to demand from any private-note site</h2>
    <p>Whichever service you pick — this one included — hold it to four
    things. The note should be encrypted <i>in your browser</i>, with the key
    in the part of the link after the <code>#</code>, so the server only ever
    stores ciphertext. The pages where the note is written and read should
    load no outside scripts — no ads, no analytics, no CDN code — because any
    loaded script runs right next to your secret. «Deleted after reading»
    should mean deleted, not archived. And you should be able to read the
    source code rather than take anyone's word for all of the above. The best
    Privnote alternative is whichever service passes all four — hold this one
    to them too.</p>

    <h2>How throw.dog answers those</h2>
    <p>Notes are encrypted on this page with AES-256-GCM and the server holds
    ciphertext only; the key never reaches us. The compose and read pages load
    zero network scripts — not even our own visit counter — and the page's
    security policy has the browser enforce that, rather than politely
    promising it. Notes live in memory only, die on first read or after 10
    minutes, and are never written to disk. The full source is public, at
    github.com/delawer33/throw.dog.</p>

    <h2>Privnote vs throw.dog, point by point</h2>
    <p>As of September 2026, going by what each site itself says. Privnote
    has done one thing well for years — this is not a takedown, it's the
    list of where the two actually differ, so you can pick the one that fits
    the note in your hand.</p>
    <table>
      <tr><th></th><th>Privnote</th><th>throw.dog</th></tr>
      <tr><td>Encrypted in the browser, key after the <code>#</code></td><td>yes</td><td>yes</td></tr>
      <tr><td>Ads on the note pages</td><td>yes</td><td>none</td></tr>
      <tr><td>Scripts loaded from outside</td><td>ads, analytics</td><td>zero — the browser enforces it</td></tr>
      <tr><td>Source code</td><td>closed</td><td>public, on GitHub</td></tr>
      <tr><td>An unread note waits</td><td>up to 30 days</td><td>10 minutes</td></tr>
      <tr><td>Gone on first read</td><td>by default</td><td>always</td></tr>
      <tr><td>Hand over by QR, no link sent</td><td>no</td><td>yes</td></tr>
      <tr><td>Extra password on the note</td><td>optional</td><td>no</td></tr>
      <tr><td>Read receipt by email</td><td>optional</td><td>no — no email, no account, no log</td></tr>
      <tr><td>Files</td><td>no</td><td>yes, one file up to 100 MB</td></tr>
      <tr><td>Sign-up</td><td>none</td><td>none</td></tr>
    </table>
    <p>If you need a note to wait a week for its reader, or a password on top
    of the link, Privnote has that and this site doesn't — on purpose. Most
    other Privnote alternatives (onetimesecret, yopass and the rest) are
    worth putting through the same four checks above; the open-source ones
    let you.</p>

    <h2>What's genuinely different</h2>
    <p>Two things you won't find in most Privnote-style services. The QR: the
    result card leads with one, so you can hand a secret to the person next to
    you without the link — and its key — ever entering a chat history. And the
    10-minute lifetime: most services keep an unread note for days or weeks;
    here it's gone in 10 minutes, because a live secret link with a long shelf
    life is mostly a liability with a countdown nobody is watching.</p>

    <h2>Honest limits</h2>
    <p>In-browser encryption — anyone's — can't protect you from the site
    that serves the encrypting page itself; we say so in our Privacy note
    rather than hide behind the word «encrypted». Notes are text up to
    64&nbsp;KB; a file goes the same way, sealed in the browser chunk by
    chunk and stored as ciphertext for the same 10 minutes — one file, up to
    100&nbsp;MB.</p>""",
    ),
    # --- русский кластер: устройства (открытый режим) -------------------------
    Landing(
        lang="ru",
        slug="perekinut-tekst-s-kompa-na-telefon",
        alternate="send-text-from-pc-to-phone",
        title="Как перекинуть текст с компа на телефон — без регистрации | throw.dog",
        description=(
            "Вставь текст на компьютере, получи два слова и QR, открой на "
            "телефоне. Без аккаунта, приложений и провода — текст стирается "
            "после первого прочтения."
        ),
        tagline_a="Перекинуть текст",
        tagline_b="с компа на телефон",
        sub=(
            "Вставь текст ниже — получишь два слова и QR. Набери эти два "
            "слова на телефоне, и текст там."
        ),
        closed=False,
        body="""    <h2>Как это работает</h2>
    <p>Вставь текст в поле выше — вставка сразу бросает его (набрал руками —
    нажми кнопку). В ответ придут два коротких слова, вроде
    <code>red-fox</code>, и QR-код. На телефоне либо наведи камеру на QR,
    либо открой throw.dog в любом браузере и набери эти два слова. Всё:
    текст на телефоне, обычно быстрее чем за десять секунд вместе с
    набором.</p>

    <h2>Без регистрации, приложений и провода</h2>
    <p>Обычные способы перекинуть текст требуют чего-то заранее: письмо себе
    — открытой почты на обоих концах, мессенджер — залогиненного аккаунта на
    втором устройстве, провод — чтобы он нашёлся. Здесь на обоих устройствах
    просто сайт. Ставить нечего, регистрироваться негде, сопрягать нечего.</p>

    <h2>Убирает за собой сам</h2>
    <p>Бросок читается один раз и исчезает: как только телефон забрал текст,
    код перестаёт работать. Непрочитанный бросок сам испаряется через 10
    минут. Ничего не хранится — значит, нечего потом идти удалять.</p>

    <h2>Работает и в обратную сторону</h2>
    <p>Тем же приёмом текст едет с телефона на компьютер: бросаешь на
    телефоне, набираешь два слова на компе. Текст до 64&nbsp;КБ — заметки,
    адреса, куски кода, целые абзацы.</p>""",
    ),
    Landing(
        lang="ru",
        slug="skinut-tekst-s-telefona-na-kompyuter",
        alternate="send-text-from-phone-to-computer",
        updated="2026-10-04",
        title="Как скинуть текст с телефона на компьютер — без проводов | throw.dog",
        description=(
            "Набери или вставь текст на телефоне, получи два слова и введи их "
            "на компьютере на throw.dog. Работает на рабочем компе, где ничего "
            "нельзя ставить — это просто сайт."
        ),
        tagline_a="Скинуть текст с",
        tagline_b="телефона на компьютер",
        sub=(
            "Вставь текст ниже на телефоне — потом на компьютере открой "
            "throw.dog и набери два слова в поле «Есть код?»."
        ),
        closed=False,
        body="""    <h2>Как это работает в эту сторону</h2>
    <p>На телефоне: набери текст выше и нажми «бросить» — или просто вставь,
    вставка бросает сразу. Получишь два коротких слова. На компьютере: открой
    throw.dog и набери эти два слова в поле <i>Есть код?</i>. Сообщение
    появится на большом экране, готовое к копированию. Десять секунд плюс
    скорость твоего набора.</p>

    <h2>Сделано для запертого рабочего компа</h2>
    <p>Классическая версия задачи — рабочая машина, куда нельзя ничего
    поставить, нельзя воткнуть личный телефон и не хочется логиниться в
    личную почту или мессенджеры ради одного адреса. Сайт, куда можно
    набрать два слова, — это всё, что здесь требуется.</p>

    <h2>Ничего не остаётся</h2>
    <p>На общей или просматриваемой машине это важно вдвойне: бросок
    прочитан — и его нет, непрочитанный умирает через 10 минут, аккаунта
    нигде не заводится. Выходить не из чего и подчищать нечего.</p>""",
    ),
    Landing(
        lang="ru",
        slug="otpravit-ssylku-s-kompyutera-na-telefon",
        alternate="send-link-from-pc-to-phone",
        title="Как отправить ссылку с компьютера на телефон — наведи камеру | throw.dog",
        description=(
            "Перенеси ссылку с компьютера на телефон за секунды: вставь URL, "
            "наведи камеру телефона на QR, нажми. Без регистрации и без писем "
            "самому себе."
        ),
        tagline_a="Отправить ссылку с",
        tagline_b="компьютера на телефон",
        sub=(
            "Вставь ссылку ниже — наведи камеру телефона на QR — ссылка на "
            "телефоне, можно открывать."
        ),
        closed=False,
        body="""    <h2>Версия на две секунды</h2>
    <p>Вставь ссылку в поле выше — вставка сразу её бросает. Наведи камеру
    телефона на появившийся QR: телефон откроет бросок, ссылка внутри — жми
    или копируй. На телефоне вообще ничего набирать не надо, читает
    камера. Одинаково на iPhone и на Android.</p>

    <h2>Вместо письма самому себе</h2>
    <p>Обычно ссылку с компьютера на телефон отправляют письмом себе или
    сообщением в чат с самим собой — то есть логинятся в почту или мессенджер
    на той машине, за которой сидят, и оставляют ссылку в истории навсегда.
    Здесь аккаунта нет ни с одной стороны, а бросок стирается после первого
    прочтения или через 10 минут — что раньше.</p>

    <h2>Камеры под рукой нет?</h2>
    <p>Тогда работают два слова: открой throw.dog в браузере телефона и
    набери их. Тот же бросок, тот же результат — и точно так же в обратную
    сторону, с телефона на компьютер.</p>""",
    ),
    # --- русский кластер: секреты (закрытый режим, оболочка ADR 0003) ---------
    Landing(
        lang="ru",
        slug="odnorazovaya-ssylka-s-parolem",
        alternate="send-password-securely-one-time",
        updated="2026-10-04",
        title="Одноразовая ссылка с паролем — открывается один раз | throw.dog",
        description=(
            "Передай пароль ссылкой, которая работает один раз и умирает "
            "через 10 минут. Шифруется у тебя в браузере — ключ остаётся в "
            "ссылке, сервер видит только шифр."
        ),
        tagline_a="Одноразовая ссылка",
        tagline_b="с паролем",
        sub=(
            "Вставь пароль ниже — он шифруется прямо здесь, в браузере, а ты "
            "получаешь одноразовую ссылку и QR."
        ),
        closed=True,
        body="""    <h2>Почему не просто сообщением</h2>
    <p>Пароль, брошенный в чат или почту, там и остаётся: в двух историях, в
    двух резервных копиях, на всех устройствах, где эти аккаунты залогинены,
    годами. Ссылка с этой страницы срабатывает ровно один раз и перестаёт
    существовать через 10 минут в любом случае — так что в переписке потом
    останется мёртвая ссылка, а не пароль. Бесплатно, онлайн, без аккаунта с
    обеих сторон.</p>

    <h2>Шифруется до отправки</h2>
    <p>Браузер шифрует пароль прямо на этой странице (AES-256-GCM) ещё до
    того, как что-то уйдёт на сервер. Ключ едет только в той части ссылки,
    которая идёт после <code>#</code>, — её браузеры не отправляют никакому
    серверу. Значит, у нас лежит шифр, который мы не можем прочитать. И эта
    страница не грузит ни одного скрипта из сети, даже нашей аналитики: весь
    код, который трогает твой секрет, приехал в этом одном документе.</p>

    <h2>Один раз — и честно про это</h2>
    <p>При первом открытии ссылки бросок выдаётся и уничтожается — даже если
    у открывшего оказался неверный ключ. Мы не знаем, удалась ли расшифровка
    на той стороне, а ждать подтверждения означало бы дать способ выдать один
    секрет дважды. Потерянную ссылку не восстановит никто, включая нас. Это
    честная цена, названная заранее.</p>

    <h2>Передаёшь из рук в руки?</h2>
    <p>Тогда QR вместо ссылки: человек сканирует его прямо с твоего экрана, и
    ключ не попадает ни в какую переписку вообще.</p>""",
    ),
    Landing(
        lang="ru",
        slug="odnorazovaya-zapiska",
        alternate="self-destructing-note",
        updated="2026-10-04",
        title="Одноразовая записка онлайн — самоуничтожается после прочтения | throw.dog",
        description=(
            "Одноразовая записка онлайн, бесплатно и без регистрации: одно "
            "прочтение или 10 минут — и её нет. Шифруется у тебя на "
            "устройстве, прочитать или вернуть не может никто, включая нас."
        ),
        tagline_a="Одноразовая",
        tagline_b="записка",
        sub=(
            "Напиши записку ниже — она шифруется прямо здесь, а ссылка "
            "переживёт ровно одно прочтение."
        ),
        closed=True,
        body="""    <h2>Уничтожена, а не «помечена удалённой»</h2>
    <p>Записка живёт только в памяти сервера — на диск она не попадает
    вообще. Стирается в тот момент, когда её прочитали; непрочитанная стирает
    себя через 10 минут. Здесь нет корзины, отложенного удаления и резервной
    копии, где что-то задержалось: уничтожение — это и есть способ хранения,
    а не уборка по расписанию.</p>

    <h2>И нечитаема, пока существует</h2>
    <p>Ещё до того, как записка уйдёт с этой страницы, браузер её шифрует, а
    ключ остаётся только в ссылке — в части после <code>#</code>, которую
    браузеры оставляют себе. Всю свою короткую жизнь на сервере записка
    лежит шифром без ключа.</p>

    <h2>Странице можно верить на слово</h2>
    <p>«Шифруется в браузере» стоит ровно столько, сколько стоит страница,
    которая это делает. Поэтому здесь жёсткое правило: ни один скрипт,
    загруженный из сети, тут не выполняется — ни аналитика, ни шрифты, ни
    что-либо стороннее. Всё, что трогает записку, лежит в уже полученном
    документе, а политика безопасности страницы заставляет браузер это
    соблюдать, вместо того чтобы полагаться на наши хорошие манеры.</p>

    <h2>Как отправить одноразовую записку</h2>
    <p>Напиши текст в поле выше и нажми «бросить» — или просто вставь его,
    вставка бросает сразу. Получишь ссылку и QR. Ссылку отправь в любой чат
    или письмом, QR покажи человеку рядом — он наведёт камеру. Первое же
    открытие покажет записку и сотрёт её; если никто не открыл за 10 минут,
    она исчезнет сама. Регистрации нет ни у тебя, ни у получателя.</p>

    <h2>Секретная, зашифрованная, одноразовая — это одно и то же</h2>
    <p>Секретная записка онлайн, зашифрованная записка, одноразовые заметки
    онлайн — ищут по-разному, а нужно одно и то же. Здесь это одна вещь:
    записка зашифрована ещё до отправки, прочитать её можно один раз, а заметкой, которую хранят, она не
    станет никогда — ей просто негде храниться. Если нужна заметка «для
    себя на потом», это не тот инструмент; если нужно сказать что-то одному
    человеку и не оставить следа — тот.</p>

    <h2>Когда это то, что нужно</h2>
    <p>Код от подъезда гостю, пароль от вайфая, то, что хочется сказать один
    раз и чтобы оно исчезло. Самоудаляющаяся или самоуничтожающаяся — как ни
    называй, работает онлайн, в любом браузере, ставить ничего не надо.
    Написал, отдал ссылку или QR — записка сама себя уничтожит.</p>

    <h2>Если искали что-то вроде Privnote</h2>
    <p>Это оно — самоуничтожающаяся записка по одноразовой ссылке, — только
    без рекламы на страницах записки, без единого скрипта со стороны и с
    открытым исходным кодом. Плюс QR, чтобы отдать секрет из рук в руки, не
    отправляя ссылку вообще. Бесплатно, без регистрации, без приложения.
    Подробное сравнение по пунктам — на странице
    <a href="/ru/analog-privnote">аналог Privnote</a>.</p>""",
    ),
    Landing(
        lang="ru",
        slug="analog-privnote",
        alternate="privnote-alternative",
        updated="2026-10-04",
        title="Аналог Privnote — записки без рекламы, с открытым кодом | throw.dog",
        description=(
            "Чем заменить Privnote: одноразовая зашифрованная записка без "
            "рекламы и сторонних скриптов, с QR для передачи из рук в руки и "
            "открытым исходным кодом. Бесплатно, без регистрации."
        ),
        tagline_a="Аналог",
        tagline_b="Privnote",
        sub=(
            "Напиши записку ниже — она шифруется в этой вкладке, уходит "
            "одноразовой ссылкой или QR и исчезает через 10 минут."
        ),
        closed=True,
        body="""    <h2>Что такое Privnote и почему ищут замену</h2>
    <p>Privnote — один из старейших сервисов одноразовых записок: пишешь
    текст, получаешь ссылку, после прочтения записка удаляется. Идея хорошая
    и работает годами. Замену обычно ищут не потому, что идея плохая, а из-за
    того, что вокруг неё: рекламы и сторонних скриптов на тех самых
    страницах, где пишется и читается секрет, и закрытого кода, из-за
    которого обещания сервиса приходится принимать на веру.</p>

    <h2>По-русски и без чужого кода</h2>
    <p>Если искали Privnote на русском — здесь весь интерфейс русский, от
    поля ввода до страницы, где записку читают, включая короткое «Ничего
    нет» для уже прочитанной ссылки. А главное отличие не в языке: на
    страницах, где пишется и читается записка, нет ни рекламы, ни счётчиков,
    ни одного скрипта со стороны — и это не обещание, а правило, которое
    браузер соблюдает за нас.</p>

    <h2>Что спросить у любого сервиса записок</h2>
    <p>У этого тоже. Шифруется ли записка у тебя в браузере, а ключ лежит в
    ссылке после <code>#</code> — так, что сервер хранит только шифр? Грузят
    ли страницы записки чужие скрипты — рекламу, счётчики, библиотеки с
    CDN? Любой такой скрипт выполняется рядом с твоим секретом. Удаляется ли
    прочитанная записка по-настоящему, а не уходит в архив? И можно ли
    прочитать исходный код, вместо того чтобы верить на слово? Хороший
    аналог Privnote — тот, что честно отвечает «да» на все четыре.</p>

    <h2>Privnote и throw.dog: сравнение по пунктам</h2>
    <p>По состоянию на сентябрь 2026 года, по тому, что пишут о себе сами
    сервисы. Это не разгром Privnote, а список мест, где они реально
    расходятся, — чтобы выбрать под свою записку.</p>
    <table>
      <tr><th></th><th>Privnote</th><th>throw.dog</th></tr>
      <tr><td>Шифрование в браузере, ключ после <code>#</code></td><td>да</td><td>да</td></tr>
      <tr><td>Реклама на страницах записки</td><td>есть</td><td>нет</td></tr>
      <tr><td>Скрипты со стороны</td><td>реклама, аналитика</td><td>ноль — это соблюдает браузер</td></tr>
      <tr><td>Исходный код</td><td>закрыт</td><td>открыт, на GitHub</td></tr>
      <tr><td>Сколько ждёт непрочитанная записка</td><td>до 30 дней</td><td>10 минут</td></tr>
      <tr><td>Исчезает после первого прочтения</td><td>по умолчанию</td><td>всегда</td></tr>
      <tr><td>Передать по QR, без ссылки в чате</td><td>нет</td><td>да</td></tr>
      <tr><td>Дополнительный пароль на записку</td><td>по желанию</td><td>нет</td></tr>
      <tr><td>Уведомление о прочтении на почту</td><td>по желанию</td><td>нет — ни почты, ни аккаунта, ни журнала</td></tr>
      <tr><td>Файлы</td><td>нет</td><td>да, один файл до 100 МБ</td></tr>
      <tr><td>Регистрация</td><td>не нужна</td><td>не нужна</td></tr>
    </table>
    <p>Если записка должна неделю ждать адресата или нужен пароль поверх
    ссылки — это есть у Privnote и сознательно нет здесь. Остальные аналоги
    (onetimesecret, yopass и другие) стоит прогнать через те же четыре
    вопроса; у тех, что с открытым кодом, это можно сделать самому.</p>

    <h2>Чем throw.dog отличается по-настоящему</h2>
    <p>QR первым делом: карточка результата начинается с него, так что секрет
    можно отдать человеку рядом, а ссылка с ключом вообще не попадёт ни в
    одну переписку. И 10 минут жизни: живая ссылка на секрет, которая неделями
    лежит в чужом почтовом ящике, — это риск с таймером, за которым никто не
    следит. Исходный код открыт: github.com/delawer33/throw.dog.</p>

    <h2>Честно о пределах</h2>
    <p>Шифрование в браузере — любое, не только наше — не защитит от сайта,
    который сам отдаёт шифрующую страницу; мы пишем об этом в политике
    конфиденциальности, а не прячемся за словом «зашифровано». Записка — до
    64&nbsp;КБ текста; файл идёт тем же путём, шифруется в браузере кусками
    и хранится шифром те же 10 минут — один файл, до 100&nbsp;МБ.</p>""",
    ),
    Landing(
        lang="ru",
        slug="odnorazovoe-soobshchenie",
        updated="2026-10-04",
        title="Одноразовое сообщение онлайн — по ссылке, в любой мессенджер | throw.dog",
        description=(
            "Отправь одноразовое сообщение через сайт: текст открывается по "
            "ссылке один раз и исчезает. Работает поверх Telegram, WhatsApp, "
            "почты и рабочих чатов — без приложения и без номера телефона."
        ),
        tagline_a="Одноразовое сообщение",
        tagline_b="по ссылке",
        sub=(
            "Напиши сообщение ниже — получишь ссылку, которая откроется один "
            "раз. Отправь её куда угодно."
        ),
        closed=True,
        body="""    <h2>В мессенджерах такое уже есть — зачем ещё</h2>
    <p>Есть, и если вы с собеседником в одном мессенджере, пользуйся им:
    в Telegram есть секретные чаты с таймером и автоудаление сообщений, в
    WhatsApp — исчезающие сообщения и фото «на один просмотр». Эта страница —
    для остальных случаев. Собеседник в другом мессенджере или пишете друг
    другу по почте. Рабочий чат, где таймеров нет, а история хранится годами.
    Человек, которому не хочется давать свой номер. Тогда одноразовое
    сообщение отправляется ссылкой — а ссылку можно положить куда угодно.</p>

    <h2>Ссылка вместо текста</h2>
    <p>Разница с обычным сообщением одна: в чат уходит не сам текст, а
    ссылка на него. Получатель открывает её в браузере — прямо из Telegram,
    WhatsApp, письма или Slack, — читает, и на этом всё: второй раз ссылка
    покажет «ничего нет». Не открыл за 10 минут — текст исчезает сам, даже
    если ссылка так и висит в переписке. Рядом с собеседником? Покажи QR с
    экрана, и ссылка не попадёт ни в какой чат вообще.</p>

    <h2>Что останется в переписке</h2>
    <p>Мёртвая ссылка. Само сообщение в чат не попадает: оно шифруется прямо
    в этой вкладке, ключ едет в части ссылки после <code>#</code>, которую
    браузеры не отправляют на сервер, а у нас лежит только шифр — и то не
    дольше 10 минут. Страница не грузит ни одного стороннего скрипта, так что
    рядом с твоим текстом не работает ничей чужой код.</p>

    <h2>Чего одноразовость не обещает</h2>
    <p>Она защищает от повторного прочтения и от истории переписки, но не от
    самого читателя: открыв сообщение, он может его скопировать или сделать
    скриншот — как и в любом мессенджере. И если ссылку первым откроет не
    тот, кому она предназначалась, адресат вместо сообщения увидит «ничего
    нет» — так перехват хотя бы не останется незамеченным.</p>""",
    ),
)

#: Labels for the in-cluster link block, per language and cluster. Pages
#: cross-link inside their own cluster and their own language only (the
#: clusters meet through the homepage, the languages through hreflang); the
#: blocks are generated so the set stays consistent when a page is added.
_CLUSTER_LINKS: Final[dict[tuple[str, bool], dict[str, str]]] = {
    ("en", False): {
        "send-text-from-pc-to-phone": "Send text from PC to phone",
        "copy-paste-between-devices": "Copy &amp; paste between devices",
        "send-link-from-pc-to-phone": "Send a link from PC to phone",
        "send-text-from-phone-to-computer": "Send text from phone to computer",
    },
    ("en", True): {
        "send-password-securely-one-time": "Send a password securely",
        "one-time-secret": "One-time secret link",
        "self-destructing-note": "Self-destructing note",
        "privnote-alternative": "Privnote alternative",
    },
    ("ru", False): {
        "perekinut-tekst-s-kompa-na-telefon": "Перекинуть текст с компа на телефон",
        "skinut-tekst-s-telefona-na-kompyuter": "Скинуть текст с телефона на компьютер",
        "otpravit-ssylku-s-kompyutera-na-telefon": "Отправить ссылку с компьютера на телефон",
    },
    ("ru", True): {
        "odnorazovaya-ssylka-s-parolem": "Одноразовая ссылка с паролем",
        "odnorazovaya-zapiska": "Одноразовая записка",
        "odnorazovoe-soobshchenie": "Одноразовое сообщение",
        "analog-privnote": "Аналог Privnote",
    },
}

_RELATED_HEADING: Final = {"en": "Related", "ru": "Ещё по теме"}


def _related(landing: Landing) -> str:
    prefix = "/ru/" if landing.lang == "ru" else "/"
    links = " ·\n    ".join(
        f'<a href="{prefix}{slug}">{label}</a>'
        for slug, label in _CLUSTER_LINKS[(landing.lang, landing.closed)].items()
        if slug != landing.slug
    )
    if not links:
        return ""
    return f"""

    <h2>{_RELATED_HEADING[landing.lang]}</h2>
    <p class="related">{links}</p>"""


#: Where each language's set is rooted, for the hreflang pair on the homepages.
HOME_URLS: Final[dict[str, str]] = {
    "en": "https://throw.dog/",
    "ru": "https://throw.dog/ru/",
}


def hreflang_links(en_url: str | None, ru_url: str | None) -> str:
    """The ``hreflang`` block naming both versions of one page, plus x-default.

    Both sides must list both URLs — an annotation only counts when it is
    returned. ``x-default`` points at English: it is what a reader we have no
    better guess for gets, and the honest default for the launch surface.
    """
    out = []
    if en_url:
        out.append(f'<link rel="alternate" hreflang="en" href="{en_url}">')
    if ru_url:
        out.append(f'<link rel="alternate" hreflang="ru" href="{ru_url}">')
    if en_url:
        out.append(f'<link rel="alternate" hreflang="x-default" href="{en_url}">')
    return "\n".join(out)


_BY_SLUG: Final[dict[str, Landing]] = {}


def _alternate_urls(landing: Landing) -> tuple[str | None, str | None]:
    other = _BY_SLUG.get(landing.alternate) if landing.alternate else None
    if other is None:
        return (landing.url, None) if landing.lang == "en" else (None, landing.url)
    return (
        (landing.url, other.url) if landing.lang == "en" else (other.url, landing.url)
    )


def _head_meta(landing: Landing) -> str:
    # The fields land inside double-quoted attributes: a title with a quote in
    # it must break here loudly as an entity, not silently as stray markup.
    title = escape(landing.title, quote=True)
    description = escape(landing.description, quote=True)
    en_url, ru_url = _alternate_urls(landing)
    locale = "ru_RU" if landing.lang == "ru" else "en_US"
    head = (
        f'<meta name="description" content="{description}">\n'
        f'<link rel="canonical" href="{landing.url}">\n'
        + hreflang_links(en_url, ru_url)
        + "\n"
        + '<meta property="og:type" content="website">\n'
        f'<meta property="og:url" content="{landing.url}">\n'
        f'<meta property="og:title" content="{title}">\n'
        f'<meta property="og:description" content="{description}">\n'
        f'<meta property="og:locale" content="{locale}">\n' + OG_CARD
    )
    # Structured data only where no key is born: on a secret landing the block
    # would be an outside reference on a page that is held to none (ADR 0003).
    return head if landing.closed else head + "\n" + JSON_LD


_SWITCH_LABEL: Final = {"en": "Русский", "ru": "English"}


def _lang_switch(landing: Landing) -> str:
    """Where the other language's reader is sent from this page.

    A page with a counterpart points straight at it; one without points at the
    other language's homepage. The link is UI, not a claim — only a real
    counterpart is ever named in ``hreflang``.
    """
    other = _BY_SLUG.get(landing.alternate) if landing.alternate else None
    href = other.path if other else ("/" if landing.lang == "ru" else "/ru/")
    return lang_switch(href, _SWITCH_LABEL[landing.lang])


def _render_one(landing: Landing) -> str:
    body = landing.body + _related(landing)
    overrides = {
        "title": landing.title,
        "taglineA": landing.tagline_a,
        "taglineB": landing.tagline_b,
        # The closed sender template reads @@subClosed@@, the open one @@sub@@.
        ("subClosed" if landing.closed else "sub"): landing.sub,
    }
    return render_landing(
        closed=landing.closed,
        lang=landing.lang,
        head_meta=_head_meta(landing),
        strings=overrides,
        body=f'\n  <div class="card prose seo">\n{body}\n  </div>\n',
        lang_switch_html=_lang_switch(landing),
    )


_BY_SLUG.update({landing.slug: landing for landing in LANDINGS})

#: path → rendered page, in sprint order. Rendered once at import, like every
#: other page constant: the landings are static documents.
LANDING_PAGES: Final[dict[str, str]] = {
    landing.path: _render_one(landing) for landing in LANDINGS
}

#: The secret-cluster pages, both languages: a key can be born on these, so the
#: ADR 0003 test holds them to the same line as /closed and the receiver page.
CLOSED_LANDING_PAGES: Final[tuple[str, ...]] = tuple(
    LANDING_PAGES[landing.path] for landing in LANDINGS if landing.closed
)

#: Everything we want indexed, for the sitemap and for main.py's header logic.
INDEXABLE_PATHS: Final[tuple[str, ...]] = (
    "/",
    "/ru/",
    "/terms",
    "/privacy",
    *(landing.path for landing in LANDINGS),
)

#: path → when that page last really changed, for the sitemap. Hand-kept,
#: because a build timestamp would tell crawlers every deploy rewrote every
#: page — a lie that costs crawl budget. Landings carry their own ``updated``;
#: the non-landing pages are dated here. Bump a date when that page's copy or
#: links actually change.
LASTMOD: Final[dict[str, str]] = {
    "/": "2026-09-21",
    "/ru/": "2026-10-04",
    "/terms": "2026-09-21",
    "/privacy": "2026-09-21",
    **{landing.path: landing.updated for landing in LANDINGS},
}

SITEMAP_XML: Final = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    + "".join(
        f"  <url><loc>https://throw.dog{path}</loc>"
        f"<lastmod>{LASTMOD[path]}</lastmod></url>\n"
        for path in INDEXABLE_PATHS
    )
    + "</urlset>\n"
)
