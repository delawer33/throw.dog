"""The HTML pages, inlined.

No framework, no build step, no external requests — the whole point is that a
phone on a bad connection gets one small document and can act on it. The design
is "sticker-punk" (see ``model/08-design.md``): cream paper, ink borders, hard
offset shadows, a dog at the transfer card, and a bone that arcs on throw. Fonts
are system-ui (0 font bytes) and every asset — CSS, JS, SVG, the QR generator —
is inline, so a page is one self-contained document well under 100 KB.

The receiver page is identical for every code: it carries no throw content and
fetches it with a POST. Link previews and prefetchers issue GETs, and a GET
must never burn a one-shot throw.

Three pages, not two, and the split is a promise rather than a layout choice
(ADR 0003). A closed throw is encrypted in the sender's browser and decrypted in
the receiver's, so on those two pages a key exists in the tab, alongside the
plaintext it protects. Nothing loaded over the network runs there: not because a
loaded script is known to misbehave, but because "the server never sees your
text" cannot be true of a page whose code the server ships on demand. Hence the
closed sender lives at its own address instead of being a redraw of the
homepage — a script already fetched into a tab cannot be unfetched.

Browser analytics therefore survives only on the open sender page, where no key
is ever born.
"""

from __future__ import annotations

import json
import os
from typing import Final

from app.closedaddress import JS_PATTERN as CLOSED_ADDRESS_PATTERN

# Sticker-punk palette and building blocks. No `%` in the template that wraps
# this (only in _STYLE's own values, which are the format *argument*), so CSS
# percentages are safe here.
_STYLE: Final = """
  :root {
    --cream: #FFF3DC; --ink: #181207; --mustard: #FFB302; --red: #FF5B4A;
    --dot: #E8D9B8; color-scheme: light;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    background: var(--cream); color: var(--ink); min-height: 100vh;
    background-image: radial-gradient(var(--dot) 1.2px, transparent 1.2px);
    background-size: 26px 26px;
    padding: 32px 20px 72px; line-height: 1.5;
  }
  .wrap { max-width: 660px; margin: 0 auto; }
  .top { display: flex; align-items: center; margin-bottom: 30px; }
  .top b { font-size: 24px; font-weight: 900; letter-spacing: -.5px; }
  /* The logo is a home link but reads as a mark, not a hyperlink: no
     underline, not selectable, not draggable. */
  .toplink {
    display: flex; align-items: center; gap: 12px; color: inherit;
    text-decoration: none; cursor: pointer;
    user-select: none; -webkit-user-select: none; -webkit-tap-highlight-color: transparent;
  }
  .toplink svg { -webkit-user-drag: none; }
  .paw { transform: rotate(-8deg); flex: none; }
  h1 {
    font-size: clamp(30px, 6vw, 46px); font-weight: 900; line-height: 1.06;
    letter-spacing: -1.5px; text-transform: uppercase; margin-bottom: 14px;
  }
  h1 .hl {
    background: var(--mustard); padding: 0 10px; border: 3px solid var(--ink);
    display: inline-block; transform: rotate(-1.5deg); box-shadow: 5px 5px 0 var(--ink);
  }
  .sub { font-weight: 700; font-size: 15px; line-height: 1.45; margin-bottom: 40px; max-width: 480px; }

  .stage { position: relative; }
  .dog {
    position: absolute; right: 26px; top: -58px; z-index: 2; cursor: default;
    transform-origin: 50% 100%; transition: transform .25s cubic-bezier(.4,1.6,.6,1);
  }
  .stage:hover .dog { transform: rotate(-7deg) translateY(-3px); }
  .dog .tongue { opacity: 0; transition: opacity .2s; }
  .stage.thrown .dog .tongue { opacity: 1; }
  .stage.thrown .dog { animation: excited .5s ease .2s; }
  @keyframes excited {
    30% { transform: translateY(-10px) rotate(4deg); }
    60% { transform: translateY(0) rotate(-4deg); }
  }

  .card {
    position: relative; z-index: 3; background: #fff; border: 3px solid var(--ink);
    border-radius: 16px; box-shadow: 9px 9px 0 var(--ink); padding: 20px;
  }
  textarea {
    width: 100%; min-height: 200px; border: 2px dashed #18120744; border-radius: 10px;
    font: 600 15px/1.45 system-ui, sans-serif; padding: 14px; resize: vertical;
    background: #FFFDF6; outline: none; color: var(--ink);
  }
  textarea:focus { border-color: var(--ink); background: #fff; }

  .btn {
    font: 900 18px system-ui, sans-serif; text-transform: uppercase; letter-spacing: 1.5px;
    background: var(--red); color: #fff; border: 3px solid var(--ink); border-radius: 12px;
    box-shadow: 6px 6px 0 var(--ink); cursor: pointer;
    transition: transform .08s, box-shadow .08s; padding: 16px;
  }
  .btn.wide { width: 100%; margin-top: 14px; }
  .btn:hover { background: #ff6c5d; }
  .btn:active { transform: translate(5px, 5px); box-shadow: 1px 1px 0 var(--ink); }
  .btn.ghost {
    background: #fff; color: var(--ink); font-size: 14px; letter-spacing: .5px;
    box-shadow: 4px 4px 0 var(--ink);
  }
  .btn.ghost:hover { background: var(--cream); }

  /* flying bone */
  .bone { position: absolute; left: 44%; top: 34%; opacity: 0; pointer-events: none; z-index: 6; }
  .stage.thrown .bone { animation: arc .55s ease-in forwards; }
  @keyframes arc {
    0%   { opacity: 1; transform: translate(0,0) rotate(0); }
    50%  { opacity: 1; transform: translate(160px,-130px) rotate(380deg); }
    100% { opacity: 0; transform: translate(310px,-30px) rotate(720deg); }
  }

  /* result */
  .donelabel { font-weight: 800; font-size: 14px; margin-bottom: 10px; }
  .codebig {
    font: 900 clamp(30px, 8vw, 48px)/1.05 system-ui, sans-serif; letter-spacing: -1px;
    text-transform: uppercase; background: var(--mustard); color: var(--ink);
    border: 3px solid var(--ink); border-radius: 12px; box-shadow: 6px 6px 0 var(--ink);
    padding: 14px 16px; word-break: break-word; margin-bottom: 16px;
    transform: rotate(-1deg);
  }
  .result { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
  .qr {
    width: 116px; height: 116px; flex: none; border: 3px solid var(--ink);
    border-radius: 10px; box-shadow: 4px 4px 0 var(--ink); background: #fff; padding: 6px;
  }
  .qr svg { width: 100%; height: 100%; display: block; }
  .resmeta { flex: 1 1 180px; min-width: 0; }
  .url { font: 700 15px ui-monospace, SFMono-Regular, Menlo, monospace; word-break: break-all; margin-bottom: 10px; }
  /* The result pops in IMMEDIATELY — the bone flight is decoration that plays
     alongside it, never a gate the user waits behind (soft-launch feedback). */
  .stage.thrown #done { animation: pop .25s cubic-bezier(.5,1.8,.6,1); }
  @keyframes pop { from { transform: scale(.6); opacity: 0; } to { transform: scale(1); opacity: 1; } }

  /* receiver output */
  pre {
    white-space: pre-wrap; word-break: break-word; font: 600 15px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
    background: #FFFDF6; border: 2px solid var(--ink); border-radius: 10px; padding: 14px; margin-bottom: 14px;
    max-height: 55vh; overflow: auto;
  }
  #status { font-weight: 800; font-size: 16px; }

  .chip {
    display: inline-block; font-weight: 700; font-size: 13px; background: #fff;
    border: 2px solid var(--ink); border-radius: 999px; padding: 6px 14px;
    transform: rotate(1deg); margin-top: 22px;
  }
  .hint { opacity: .7; font-size: 13px; font-weight: 600; margin-top: 12px; }

  /* Pro fake-door */
  .prochip {
    font: 900 14px system-ui, sans-serif; text-transform: uppercase; letter-spacing: 1px;
    background: var(--mustard); color: var(--ink); border: 3px solid var(--ink);
    border-radius: 999px; box-shadow: 4px 4px 0 var(--ink); cursor: pointer;
    padding: 8px 18px; margin-top: 22px; margin-right: 10px; transform: rotate(-2deg);
    transition: transform .08s, box-shadow .08s;
  }
  .prochip:hover { background: #ffc233; }
  .prochip:active { transform: translate(4px, 4px) rotate(-2deg); box-shadow: 1px 1px 0 var(--ink); }
  .prodoor { margin-top: 22px; }
  .proinput {
    width: 100%; border: 2px dashed #18120744; border-radius: 10px;
    font: 600 15px system-ui, sans-serif; padding: 14px; background: #FFFDF6;
    outline: none; color: var(--ink); margin-top: 12px;
  }
  .proinput:focus { border-color: var(--ink); background: #fff; }
  textarea.proinput { min-height: 74px; resize: vertical; font: 600 15px/1.45 system-ui, sans-serif; }

  /* "Got a code?" fetch-by-code form on the sender page. Soft-launch showed
     that editing the URL by hand is not obvious to everyone, so the homepage
     itself must accept the two words. */
  .getcard { margin-top: 22px; padding: 16px 20px; }
  .getrow { display: flex; gap: 10px; flex-wrap: wrap; }
  .getrow .proinput { flex: 1 1 180px; min-width: 0; margin-top: 0; }
  .getrow .btn { flex: none; padding: 10px 18px; }
  .error {
    color: var(--red); font-weight: 800; font-size: 14px; margin-top: 12px;
    background: #fff; border: 2px solid var(--red); border-radius: 10px; padding: 10px 12px;
  }
  [hidden] { display: none !important; }

  /* footer on the main pages — links to the EN-only legal pages */
  .foot {
    margin-top: 34px; font-weight: 700; font-size: 13px; display: flex;
    gap: 10px; align-items: center; flex-wrap: wrap; opacity: .8;
  }
  .foot a { color: var(--ink); text-decoration: underline; text-underline-offset: 3px; }
  .foot a:hover { color: var(--red); }

  /* legal (Terms / Privacy) prose, reusing the .card shell */
  .prose { font-weight: 600; font-size: 15px; }
  .prose h2 {
    font-size: 18px; font-weight: 900; text-transform: uppercase;
    letter-spacing: -.3px; margin: 20px 0 8px;
  }
  .prose h2:first-child { margin-top: 0; }
  .prose p { margin-bottom: 12px; }
  .prose p:last-child { margin-bottom: 0; }
  .prose a { color: var(--ink); font-weight: 800; }
  .abuse {
    display: inline-block; font-weight: 800; background: var(--mustard);
    border: 2px solid var(--ink); border-radius: 8px; padding: 1px 8px;
    text-decoration: none; transform: rotate(-1deg);
  }

  /* Mode of the throw: two halves, the current one filled in. Both carry
     their own line, so the choice is made on what each mode actually does. */
  .modes { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 44px; }
  .mode {
    flex: 1 1 200px; text-align: left; font-family: inherit; cursor: pointer;
    background: #fff; color: var(--ink); border: 3px solid var(--ink);
    border-radius: 12px; box-shadow: 4px 4px 0 var(--ink); padding: 10px 14px;
  }
  .mode.on { background: var(--mustard); cursor: default; }
  .mode[disabled] { opacity: .55; cursor: not-allowed; box-shadow: none; }
  .modename { display: block; font-weight: 900; font-size: 15px; }
  .modenote { display: block; font-weight: 600; font-size: 12.5px; opacity: .75; margin-top: 3px; }

  /* Closed mode delivers by QR or not at all, so the QR is the result rather
     than a garnish beside a code that does not exist: it is centred, and the
     card centres on it. The two actions share one row and one flex basis, so
     they cannot end up different widths; below ~270px the row wraps and they
     stack, still equal. */
  .qr.big { width: min(230px, 62vw); height: min(230px, 62vw); margin: 0 auto 14px; }
  .doneclosed { text-align: center; }
  .doneclosed .url { font-size: 13px; }
  .donerow { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }
  .donerow .btn {
    flex: 1 1 130px; margin-top: 0; padding: 14px 10px;
    font-size: 15px; letter-spacing: .5px; box-shadow: 4px 4px 0 var(--ink);
  }

  @media (prefers-reduced-motion: reduce) {
    .bone, .dog, .stage.thrown #done, .btn { animation: none !important; transition: none !important; }
    .stage.thrown .bone { opacity: 0; }
  }
"""

_DOG: Final = """<svg class="dog" width="150" height="96" viewBox="0 0 150 96" aria-hidden="true">
  <path d="M46 26 Q28 18 24 42 Q23 62 42 56 Z" fill="#FFB302" stroke="#181207" stroke-width="4" stroke-linejoin="round"/>
  <path d="M104 26 Q122 18 126 42 Q127 62 108 56 Z" fill="#FFB302" stroke="#181207" stroke-width="4" stroke-linejoin="round"/>
  <circle cx="75" cy="52" r="32" fill="#fff" stroke="#181207" stroke-width="4"/>
  <circle cx="63" cy="48" r="3.6" fill="#181207"/>
  <circle cx="87" cy="48" r="3.6" fill="#181207"/>
  <path d="M75 57 q-5 0 -5 -3.5 q0 -3 5 -3 q5 0 5 3 q0 3.5 -5 3.5 Z" fill="#181207"/>
  <path d="M75 58 q0 5 -6 5 M75 58 q0 5 6 5" fill="none" stroke="#181207" stroke-width="3" stroke-linecap="round"/>
  <path class="tongue" d="M70 63 q5 10 10 0 Z" fill="#FF5B4A" stroke="#181207" stroke-width="3" stroke-linejoin="round"/>
  <g fill="#fff" stroke="#181207" stroke-width="4">
    <rect x="40" y="76" width="22" height="18" rx="9"/>
    <rect x="88" y="76" width="22" height="18" rx="9"/>
  </g>
  <path d="M48 80 v8 M54 80 v8 M96 80 v8 M102 80 v8" stroke="#181207" stroke-width="2.6" stroke-linecap="round"/>
</svg>"""

_PAW: Final = """<svg class="paw" width="30" height="30" viewBox="0 0 34 34" aria-hidden="true"><g fill="#181207">
  <ellipse cx="10" cy="9" rx="4" ry="5"/><ellipse cx="24" cy="9" rx="4" ry="5"/>
  <ellipse cx="4" cy="17" rx="3.4" ry="4.4"/><ellipse cx="30" cy="17" rx="3.4" ry="4.4"/>
  <path d="M17 14c6 0 10 4.5 10 9.5 0 4-3 6.5-10 6.5S7 27.5 7 23.5C7 18.5 11 14 17 14z"/></g></svg>"""

_BONE: Final = """<svg class="bone" width="48" height="21" viewBox="0 0 46 20" aria-hidden="true">
  <path d="M8 4a5 5 0 0 1 5 5h20a5 5 0 1 1 8-4 5 5 0 1 1-4 8H17a5 5 0 1 1-8-4 5 5 0 0 1-1-5z"
    fill="#fff" stroke="#181207" stroke-width="3"/></svg>"""

# --- Analytics (self-hosted Umami, cookieless) ------------------------------
#
# The one deliberate exception to "everything is inline": a single <script src>
# to our OWN analytics subdomain (never a third-party CDN). Umami is cookieless
# by default — it sets no cookie and needs no consent banner, which is the whole
# reason it was chosen over Google Analytics (see model/10-metrics.md). Both the
# host and the website id come from the environment so the operator can point the
# page at the running instance without touching code; an empty ANALYTICS_HOST
# disables analytics entirely (the snippet collapses to nothing). Defaults are
# safe placeholders so the module-level pages still render in tests/dev.
ANALYTICS_HOST: Final = os.environ.get("ANALYTICS_HOST", "analytics.throw.dog").strip()
ANALYTICS_WEBSITE_ID: Final = os.environ.get(
    "ANALYTICS_WEBSITE_ID", "00000000-0000-0000-0000-000000000000"
).strip()

# The funnel events fired via umami.track (model/10-metrics.md): page_view is
# automatic (the tracker fires it on load); the rest are wired to UI actions.
_ANALYTICS_SNIPPET: Final = (
    (
        '<script defer src="https://%s/script.js" data-website-id="%s"></script>\n'
        # tdTrack is a safe no-op when the tracker is blocked or still loading,
        # so the funnel calls below never throw.
        "<script>function tdTrack(n){try{if(window.umami&&window.umami.track)"
        "window.umami.track(n);}catch(e){}}</script>\n"
    )
    % (ANALYTICS_HOST, ANALYTICS_WEBSITE_ID)
    if ANALYTICS_HOST
    else "<script>function tdTrack(n){}</script>\n"
)

#: Inline favicon (a bone), so the /{code} catch-all never sees /favicon.ico
#: noise and the tab still gets an icon at zero extra requests.
_FAVICON: Final = (
    '<link rel="icon" href="data:image/svg+xml,'
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
    "<text y='.9em' font-size='90'>🦴</text></svg>\">"
)

_HEAD_TMPL: Final = """<!doctype html>
<html lang="@@lang@@">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
@@headMeta@@
<title>throw.dog</title>
%s
<style>%s</style>
%s</head>
"""


def _head(*, analytics: bool) -> str:
    """The shared shell, with or without the tracker.

    ``analytics=False`` is not a configuration switch — it is the trust
    boundary of ADR 0003 expressed in code. A page that holds a key holds it
    next to whatever else runs in that tab, and stripping the fragment out of
    the URL would not help: the decrypted text sits in the DOM either way. So
    the key-bearing pages get a shell with no network-loaded script at all, and
    with no ``tdTrack`` defined — which is deliberate, so a funnel call added
    there by habit fails loudly in review instead of quietly shipping.
    """
    return _HEAD_TMPL % (
        _FAVICON,
        _STYLE,
        _ANALYTICS_SNIPPET if analytics else "",
    )


#: For the open sender and the legal pages: no key is ever born on these.
_HEAD: Final = _head(analytics=True)

#: For the closed sender and every receiver page.
_HEAD_NO_SCRIPT: Final = _head(analytics=False)

#: Head block for the indexable sender page: description + canonical + link
#: previews (OG/Twitter). The @@metaDescription@@ token is localised via
#: STRINGS like every other string.
_SENDER_HEAD_META: Final = """<meta name="description" content="@@metaDescription@@">
<link rel="canonical" href="https://throw.dog/">
<meta property="og:type" content="website">
<meta property="og:url" content="https://throw.dog/">
<meta property="og:title" content="throw.dog — @@taglineA@@ @@taglineB@@">
<meta property="og:description" content="@@metaDescription@@">
<meta name="twitter:card" content="summary">"""

#: Receiver pages stay out of every index: the URL is a one-time secret and the
#: page is meaningless to a crawler.
_NOINDEX_META: Final = '<meta name="robots" content="noindex, nofollow">'

# Minimal QR generator (byte mode, EC level L, versions 1-4, best mask). Output
# is verified module-for-module against the reference `qrcode` encoder. Only the
# sender's result card needs it, so it lives here and not on the receiver page.
_QR_JS: Final = """
function makeQR(text){
  var EXP=new Array(256),LOG=new Array(256);
  (function(){var x=1;for(var i=0;i<255;i++){EXP[i]=x;LOG[x]=i;x<<=1;if(x&0x100)x^=0x11d;}})();
  function gmul(a,b){return (a===0||b===0)?0:EXP[(LOG[a]+LOG[b])%255];}
  function genPoly(n){var g=[1];for(var i=0;i<n;i++){var ng=new Array(g.length+1);for(var k=0;k<ng.length;k++)ng[k]=0;for(var j=0;j<g.length;j++){ng[j]^=g[j];ng[j+1]^=gmul(g[j],EXP[i]);}g=ng;}return g;}
  function rsEncode(data,n){var g=genPoly(n);var res=data.slice();for(var i=0;i<n;i++)res.push(0);for(i=0;i<data.length;i++){var c=res[i];if(c!==0)for(var j=0;j<g.length;j++)res[i+j]^=gmul(g[j],c);}return res.slice(data.length);}
  var utf=unescape(encodeURIComponent(text)),data=[];
  for(var i=0;i<utf.length;i++)data.push(utf.charCodeAt(i));
  var caps=[19,34,55,80],ecLens=[7,10,15,20],ver=-1;
  for(var v=0;v<4;v++){if(4+8+8*data.length<=caps[v]*8){ver=v;break;}}
  if(ver<0)return null;
  var bits=[];
  function push(val,len){for(var b=len-1;b>=0;b--)bits.push((val>>b)&1);}
  push(4,4);push(data.length,8);
  for(i=0;i<data.length;i++)push(data[i],8);
  var cap=caps[ver]*8;
  push(0,Math.min(4,cap-bits.length));
  while(bits.length%8)bits.push(0);
  var pad=[0xEC,0x11],pi=0;
  while(bits.length<cap){push(pad[pi],8);pi^=1;}
  var dcw=[];
  for(i=0;i<bits.length;i+=8){var byte=0;for(var j=0;j<8;j++)byte=(byte<<1)|bits[i+j];dcw.push(byte);}
  var ecw=rsEncode(dcw,ecLens[ver]),all=dcw.concat(ecw),mbits=[];
  for(i=0;i<all.length;i++)for(j=7;j>=0;j--)mbits.push((all[i]>>j)&1);
  var V=ver+1,size=4*V+17,m=[],res=[];
  for(i=0;i<size;i++){m.push(new Array(size).fill(0));res.push(new Array(size).fill(false));}
  function put(r,c,val){m[r][c]=val;res[r][c]=true;}
  function finder(r,c){for(var di=-1;di<=7;di++)for(var dj=-1;dj<=7;dj++){var rr=r+di,cc=c+dj;if(rr<0||rr>=size||cc<0||cc>=size)continue;var val=0;if(di>=0&&di<=6&&dj>=0&&dj<=6)val=(di===0||di===6||dj===0||dj===6||(di>=2&&di<=4&&dj>=2&&dj<=4))?1:0;put(rr,cc,val);}}
  finder(0,0);finder(0,size-7);finder(size-7,0);
  for(i=8;i<=size-9;i++){put(6,i,(i%2===0)?1:0);put(i,6,(i%2===0)?1:0);}
  if(V>=2){var a=size-7;for(var di=-2;di<=2;di++)for(var dj=-2;dj<=2;dj++)put(a+di,a+dj,(Math.max(Math.abs(di),Math.abs(dj))!==1)?1:0);}
  put(size-8,8,1);
  for(i=0;i<=8;i++){res[8][i]=true;res[i][8]=true;}
  for(i=0;i<8;i++){res[8][size-1-i]=true;res[size-1-i][8]=true;}
  var idx=0,up=true;
  for(var col=size-1;col>0;col-=2){
    if(col===6)col--;
    for(var k=0;k<size;k++){var row=up?size-1-k:k;for(var t=0;t<2;t++){var cc=col-t;if(!res[row][cc]){m[row][cc]=idx<mbits.length?mbits[idx]:0;idx++;}}}
    up=!up;
  }
  function maskFn(mask,r,c){switch(mask){case 0:return (r+c)%2===0;case 1:return r%2===0;case 2:return c%3===0;case 3:return (r+c)%3===0;case 4:return (Math.floor(r/2)+Math.floor(c/3))%2===0;case 5:return (r*c)%2+(r*c)%3===0;case 6:return ((r*c)%2+(r*c)%3)%2===0;case 7:return ((r+c)%2+(r*c)%3)%2===0;}}
  function fmtBits(mask){var d=(1<<3)|mask,rem=d;for(var i=0;i<10;i++)rem=(rem<<1)^(((rem>>9)&1)*0x537);return ((d<<10)|rem)^0x5412;}
  function drawFmt(mtx,mask){var f=fmtBits(mask);function gb(i){return (f>>i)&1;}for(var i=0;i<=5;i++)mtx[i][8]=gb(i);mtx[7][8]=gb(6);mtx[8][8]=gb(7);mtx[8][7]=gb(8);for(i=9;i<15;i++)mtx[8][14-i]=gb(i);for(i=0;i<8;i++)mtx[8][size-1-i]=gb(i);for(i=8;i<15;i++)mtx[size-15+i][8]=gb(i);mtx[size-8][8]=1;}
  function penalty(mtx){var n=size,p=0,i,j;
    for(i=0;i<n;i++){var rc=1,cc=1;for(j=1;j<n;j++){if(mtx[i][j]===mtx[i][j-1])rc++;else{if(rc>=5)p+=3+(rc-5);rc=1;}if(mtx[j][i]===mtx[j-1][i])cc++;else{if(cc>=5)p+=3+(cc-5);cc=1;}}if(rc>=5)p+=3+(rc-5);if(cc>=5)p+=3+(cc-5);}
    for(i=0;i<n-1;i++)for(j=0;j<n-1;j++){var val=mtx[i][j];if(val===mtx[i][j+1]&&val===mtx[i+1][j]&&val===mtx[i+1][j+1])p+=3;}
    var A=[1,0,1,1,1,0,1,0,0,0,0],B=[0,0,0,0,1,0,1,1,1,0,1];
    function line(arr){var c=0;for(var s=0;s+11<=arr.length;s++){var ma=true,mb=true;for(var k=0;k<11;k++){if(arr[s+k]!==A[k])ma=false;if(arr[s+k]!==B[k])mb=false;}if(ma)c++;if(mb)c++;}return c;}
    for(i=0;i<n;i++){p+=40*line(mtx[i]);var col=[];for(j=0;j<n;j++)col.push(mtx[j][i]);p+=40*line(col);}
    var dark=0;for(i=0;i<n;i++)for(j=0;j<n;j++)dark+=mtx[i][j];p+=Math.floor(Math.abs(dark*100/(n*n)-50)/5)*10;
    return p;}
  var bestPen=Infinity,bestM=null,bestMask=0;
  for(var mask=0;mask<8;mask++){
    var cand=m.map(function(row){return row.slice();});
    for(i=0;i<size;i++)for(j=0;j<size;j++)if(!res[i][j]&&maskFn(mask,i,j))cand[i][j]^=1;
    drawFmt(cand,mask);
    var pen=penalty(cand);
    if(pen<bestPen){bestPen=pen;bestM=cand;bestMask=mask;}
  }
  return {size:size,modules:bestM};
}
function qrSVG(text){
  var q=makeQR(text);if(!q)return '';
  var s=q.size,d='';
  for(var r=0;r<s;r++)for(var c=0;c<s;c++)if(q.modules[r][c])d+='M'+c+' '+r+'h1v1h-1z';
  var vb=s+8;
  return '<svg viewBox="-4 -4 '+vb+' '+vb+'" shape-rendering="crispEdges" xmlns="http://www.w3.org/2000/svg">'
    +'<rect x="-4" y="-4" width="'+vb+'" height="'+vb+'" fill="#fff"/>'
    +'<path d="'+d+'" fill="#181207"/></svg>';
}
"""

# The closed mode's crypto, kept as one block on purpose. Everything here is
# standalone — no DOM, no page state, no strings — so the round-trip can be run
# outside a browser (node exposes the same WebCrypto, btoa/atob, TextEncoder)
# and a test can prove that what tdEncrypt writes, tdDecrypt reads back.
#
# AES-256-GCM. The key is 32 random bytes, the IV 12, and what goes to the
# server is base64 of ``iv || ciphertext || tag``. The key is base64url without
# padding, because its only home is the fragment of a URL.
#
# GCM is authenticated: a wrong key does not produce garbage, it fails. That is
# what lets the receiver say "this key did not fit" instead of showing rubbish.
_CRYPTO_CHECK_JS: Final = """
function tdCryptoReady(){
  try { return !!(window.crypto && window.crypto.subtle && window.crypto.getRandomValues
    && window.isSecureContext); } catch (e) { return false; }
}
"""

_CRYPTO_JS: Final = _CRYPTO_CHECK_JS + """
var TD_ENC = 'aes-gcm-v1';
var TD_IV_BYTES = 12, TD_KEY_BYTES = 32;

function tdB64(bytes){
  var s = '';
  for (var i = 0; i < bytes.length; i++) { s += String.fromCharCode(bytes[i]); }
  return btoa(s);
}
function tdUnB64(str){
  var s = atob(str), bytes = new Uint8Array(s.length);
  for (var i = 0; i < s.length; i++) { bytes[i] = s.charCodeAt(i); }
  return bytes;
}
function tdB64Url(bytes){
  return tdB64(bytes).replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=+$/, '');
}
function tdUnB64Url(str){
  return tdUnB64(str.replace(/-/g, '+').replace(/_/g, '/'));
}
function tdNewKey(){
  return crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, true,
    ['encrypt', 'decrypt']);
}
function tdExportKey(key){
  return crypto.subtle.exportKey('raw', key).then(function (raw) {
    return tdB64Url(new Uint8Array(raw));
  });
}
function tdImportKey(str){
  try {
    var raw = tdUnB64Url(str);
    if (raw.length !== TD_KEY_BYTES) { return Promise.reject(new Error('key length')); }
    return crypto.subtle.importKey('raw', raw, { name: 'AES-GCM' }, false, ['decrypt']);
  } catch (e) { return Promise.reject(e); }
}
function tdEncrypt(key, text){
  var iv = crypto.getRandomValues(new Uint8Array(TD_IV_BYTES));
  var data = new TextEncoder().encode(text);
  return crypto.subtle.encrypt({ name: 'AES-GCM', iv: iv }, key, data)
    .then(function (buffer) {
      var body = new Uint8Array(buffer), out = new Uint8Array(iv.length + body.length);
      out.set(iv, 0);
      out.set(body, iv.length);
      return tdB64(out);
    });
}
function tdDecrypt(key, payload){
  try {
    var all = tdUnB64(payload);
    if (all.length <= TD_IV_BYTES) { return Promise.reject(new Error('too short')); }
    return crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: all.slice(0, TD_IV_BYTES) }, key, all.slice(TD_IV_BYTES)
    ).then(function (buffer) { return new TextDecoder().decode(buffer); });
  } catch (e) { return Promise.reject(e); }
}
"""



_TOP: Final = (
    '<div class="top"><a class="toplink" href="/" aria-label="throw.dog home">'
    + _PAW
    + "<b>throw.dog</b></a></div>"
)

_FOOTER: Final = """  <footer class="foot">
    <a href="/terms">@@footerTerms@@</a>
    <span aria-hidden="true">·</span>
    <a href="/privacy">@@footerPrivacy@@</a>
  </footer>"""


def _mode_row(*, closed: bool) -> str:
    """The mode of the throw: two halves, the current one filled in.

    Both halves always carry their own line, so the choice is made on what each
    mode actually does — "the server sees your text and a code works" against
    "the server sees only ciphertext and only a link or QR works" — rather than
    on which name sounds safer. The current mode stays on screen afterwards
    too: the choice is remembered per device, and a remembered choice that
    acted silently would be worst exactly where it matters, on a shared
    machine.
    """

    def half(name: str, note: str, *, current: bool) -> str:
        if current:
            return (
                '  <div class="mode on">\n'
                f'    <span class="modename">{name}</span>\n'
                f'    <span class="modenote">{note}</span>\n'
                "  </div>"
            )
        return (
            '  <button class="mode" id="switchmode" type="button">\n'
            f'    <span class="modename">{name}</span>\n'
            f'    <span class="modenote" id="othernote">{note}</span>\n'
            "  </button>"
        )

    return (
        '<div class="modes" role="group" aria-label="@@modeLabel@@">\n'
        + half("@@modeOpenName@@", "@@modeOpenNote@@", current=not closed)
        + "\n"
        + half("@@modeClosedName@@", "@@modeClosedNote@@", current=closed)
        + "\n</div>"
    )


#: "Got a code?" — on both sender pages, because a person who prefers the closed
#: mode still receives throws, and the page they land on first is whichever one
#: their remembered choice sends them to.
_GET_CARD: Final = """  <div class="card getcard">
    <p class="donelabel">@@getLabel@@</p>
    <div class="getrow">
      <input class="proinput" id="getcode" type="text" autocapitalize="none"
             autocomplete="off" spellcheck="false" placeholder="@@getPlaceholder@@">
      <button class="btn ghost" id="getgo" type="button">@@getBtn@@</button>
    </div>
  </div>"""


def _get_card_js(*, track: bool) -> str:
    """Wiring for the "Got a code?" field.

    It accepts three things a person plausibly puts there: two words, a link to
    an open throw, and a whole closed link. The last one is why this is not a
    one-line normaliser any more — a closed link's key lives in the fragment,
    and the old "everything that is not a latin letter becomes a hyphen" rule
    quietly ground it, plus the address, into a code that could not exist. The
    reader then saw "nothing here" over a throw that was alive and well.

    ``track`` is False on the closed sender page, which defines no tdTrack at
    all (ADR 0003).
    """
    fetch_link = "    tdTrack('fetch_link');\n" if track else ""
    fetch_code = "    tdTrack('fetch_code');\n" if track else ""
    return (
        r"""
  var getcode = document.getElementById('getcode');
  function goGet() {
    var target = tdClosedTarget(getcode.value);
    if (target) {
"""
        + fetch_link
        + """      window.location.href = target;
      return;
    }
    var typed = (getcode.value || '').trim().replace(/[?#].*$/, '');
    var code = typed.split('/').pop().toLowerCase()
      .replace(/[^a-z]+/g, '-').replace(/^-+|-+$/g, '');
    if (!code) { getcode.focus(); return; }
"""
        + fetch_code
        + """    window.location.href = '/' + code;
  }
  document.getElementById('getgo').addEventListener('click', goGet);
  getcode.addEventListener('keydown', function (event) {
    if (event.key === 'Enter') { event.preventDefault(); goGet(); }
  });
  // A pasted closed link is acted on at once, so the key never rests in this
  // field. On the open sender that field lives on a page that loads a script
  // over the network, and a key must not sit there waiting to be submitted.
  getcode.addEventListener('paste', function (event) {
    var clipboard = event.clipboardData || window.clipboardData;
    if (!clipboard) { return; }
    var target = tdClosedTarget(clipboard.getData('text'));
    if (!target) { return; }
    event.preventDefault();
    window.location.href = target;
  });
"""
    )


#: The one rule that decides whether an address needs a key, injected from the
#: module that owns it so the browser and the server cannot drift apart on it.
_CLOSED_RE_JS: Final = """
var CLOSED_RE = /@@__CLOSED_RE__@@/;
"""

#: Recognising one of our own closed links wherever a person might put it.
#:
#: This is a safety net, not a convenience. A closed link carries the key, and
#: the key is the one thing that must never reach us — so a link pasted where a
#: text was expected must be opened, never thrown. Whitespace anywhere means the
#: value is prose that happens to contain a link, and prose is left alone.
#:
#: Only the address is lowercased. The key is base64url and case-carrying;
#: folding it would destroy it.
_OWN_LINK_JS: Final = r"""
function tdClosedTarget(value){
  var raw = (value || '').trim();
  if (!raw || /\s/.test(raw)) { return null; }
  var hash = '', at = raw.indexOf('#');
  if (at >= 0) { hash = raw.slice(at); raw = raw.slice(0, at); }
  var last = raw.replace(/[?].*$/, '').replace(/\/+$/, '').split('/').pop().toLowerCase();
  if (!CLOSED_RE.test(last)) { return null; }
  return '/' + last + hash;
}
"""

#: Where the remembered mode and the carried-over draft live. The draft rides in
#: sessionStorage, never in the URL and never through us: switching mode must
#: not be a way to hand the server a text the sender meant to encrypt.
_STORAGE_JS: Final = """
var TD_MODE_KEY = 'td_mode', TD_DRAFT_KEY = 'td_draft';
function tdRemember(mode){ try { localStorage.setItem(TD_MODE_KEY, mode); } catch (e) {} }
function tdKeepDraft(value){ try { sessionStorage.setItem(TD_DRAFT_KEY, value || ''); } catch (e) {} }
function tdTakeDraft(){
  try {
    var draft = sessionStorage.getItem(TD_DRAFT_KEY);
    if (draft) { sessionStorage.removeItem(TD_DRAFT_KEY); return draft; }
  } catch (e) {}
  return '';
}
"""

# Both senders compose a throw and then show a card with a link and a QR. What
# differs between them is one function — how the text becomes a throw — so only
# that function lives in the templates; the surroundings are shared, which is
# also what keeps the two from drifting apart on the parts that matter (the
# closed-link guard below, and reporting a network failure in our own words).
_COMPOSE_JS: Final = """
  var text = document.getElementById('text');
  var error = document.getElementById('error');
  var compose = document.getElementById('compose');
  var done = document.getElementById('done');
  var stage = document.getElementById('stage');
  var urlEl = document.getElementById('url');
  var qrEl = document.getElementById('qr');
  var currentUrl = '';
  var busy = false;

  function fail(message) {
    error.textContent = message;
    error.hidden = false;
  }

  function throwAnim() {
    stage.classList.remove('thrown');
    void stage.offsetWidth;
    stage.classList.add('thrown');
  }
"""


def _compose_wiring_js(*, track: bool) -> str:
    """Wire the compose card up to ``send``, which each sender defines itself.

    ``track`` is false on the closed sender: ADR 0003 keeps analytics off every
    page where a key exists, so there is nothing there to report a paste to.
    """
    paste = "    tdTrack('paste');\n" if track else ""
    return """
  text.addEventListener('paste', function (event) {
    var clipboard = event.clipboardData || window.clipboardData;
    if (!clipboard) { return; }
    var pasted = clipboard.getData('text');
    if (!pasted || !pasted.trim()) { return; }
    // A closed link of ours is opened, not thrown — see tdClosedTarget. This
    // has to happen before anything is sent, or the key goes up with the text.
    var target = tdClosedTarget(pasted);
    if (target) { event.preventDefault(); window.location.href = target; return; }
""" + paste + """    event.preventDefault();
    text.value = pasted;
    send(pasted);
  });

  document.getElementById('throw').addEventListener('click', function () {
    send(text.value);
  });

  document.getElementById('copyurl').addEventListener('click', function () {
    var button = document.getElementById('copyurl');
    function ok() { button.textContent = T.copied; setTimeout(function () { button.textContent = T.copyLink; }, 1500); }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(currentUrl).then(ok, function () {});
    }
  });

  document.getElementById('again').addEventListener('click', function () {
    text.value = '';
    done.hidden = true;
    compose.hidden = false;
    error.hidden = true;
    stage.classList.remove('thrown');
    text.focus();
  });
"""


_SENDER_TMPL: Final = _HEAD + """<body>
<script>
// The remembered mode, applied before anything is drawn. Pasting throws the
// text immediately, so the mode cannot be a decision made in the moment — it
// has to be already settled by the time the textarea exists.
(function () {
  try {
    if (localStorage.getItem('td_mode') === 'closed'
        && window.crypto && window.crypto.subtle && window.isSecureContext) {
      // The navigation is queued, not immediate: this document keeps parsing
      // and its main script would otherwise run and overwrite the very mode we
      // are honouring. The flag stops it.
      window.tdLeaving = true;
      window.location.replace('/closed');
    }
  } catch (e) {}
})();
</script>
<div class="wrap">
  """ + _TOP + """

  <h1><span>@@taglineA@@</span> <span class="hl">@@taglineB@@</span></h1>
  <p class="sub">@@sub@@</p>

  """ + _mode_row(closed=False) + """

  <div class="stage" id="stage">
    """ + _DOG + _BONE + """

    <div class="card">
      <div id="compose">
        <textarea id="text" autofocus placeholder="@@placeholder@@"></textarea>
        <button class="btn wide" id="throw" type="button">@@throwBtn@@</button>
        <p id="error" class="error" hidden></p>
      </div>

      <div id="done" hidden>
        <p class="donelabel">@@doneLabel@@</p>
        <div class="codebig" id="codebig"></div>
        <div class="result">
          <div class="qr" id="qr"></div>
          <div class="resmeta">
            <div class="url" id="url"></div>
            <button class="btn ghost" id="copyurl" type="button">@@copyLink@@</button>
          </div>
        </div>
        <p class="hint">@@hint@@</p>
        <button class="btn wide" id="again" type="button">@@againBtn@@</button>
      </div>
    </div>
  </div>

""" + _GET_CARD + """

  <button class="prochip" id="prochip" type="button" data-ev="pro_click">@@proChip@@</button>
  <button class="prochip" id="fbchip" type="button">@@fbChip@@</button>
  <span class="chip">@@chipOpen@@</span>

  <div class="card prodoor" id="prodoor" hidden>
    <p class="donelabel">@@proTitle@@</p>
    <p class="hint">@@proPerks@@</p>
    <div id="proform">
      <input class="proinput" id="proemail" type="email" inputmode="email"
             autocomplete="email" placeholder="@@proEmailPlaceholder@@">
      <button class="btn wide" id="prosubmit" type="button" data-ev="pro_email">@@proSubmit@@</button>
      <p id="proerror" class="error" hidden></p>
    </div>
    <p id="prothanks" class="donelabel" hidden></p>
  </div>

  <div class="card prodoor" id="fbdoor" hidden>
    <p class="donelabel">@@fbTitle@@</p>
    <p class="hint">@@fbIntro@@</p>
    <div id="fbform">
      <textarea class="proinput" id="fbtext" maxlength="2000"
                placeholder="@@fbPlaceholder@@"></textarea>
      <button class="btn wide ghost" id="fbsubmit" type="button">@@fbSubmit@@</button>
      <p id="fberror" class="error" hidden></p>
    </div>
    <p id="fbthanks" class="donelabel" hidden></p>
  </div>

""" + _FOOTER + """
</div>

<script>
var T = @@__T__@@;
""" + _QR_JS + _CRYPTO_CHECK_JS + _CLOSED_RE_JS + _OWN_LINK_JS + _STORAGE_JS + """
(function () {""" + _COMPOSE_JS + """
  var codebig = document.getElementById('codebig');

  // Leaving for /closed: touch nothing. Writing the remembered mode here would
  // flip it back to open, and taking the draft would consume it before the
  // page that needs it has loaded.
  if (window.tdLeaving) { return; }

  tdRemember('open');
  text.value = tdTakeDraft();
  text.focus();

  // Closed mode needs WebCrypto over https. Where it is missing, the half is
  // shown disabled WITH the reason: a mode that simply vanished would read as
  // us having lied on the homepage.
  var switchmode = document.getElementById('switchmode');
  if (!tdCryptoReady()) {
    switchmode.disabled = true;
    document.getElementById('othernote').textContent = T.modeClosedUnavailable;
  } else {
    switchmode.addEventListener('click', function () {
      tdRemember('closed');
      tdKeepDraft(text.value);
      window.location.href = '/closed';
    });
  }

  function send(value) {
    if (busy) { return; }
    // One of our own closed links, wherever it came from: it carries a key, so
    // it is opened rather than thrown. Sending it would hand us the one thing
    // the closed mode promises we never receive.
    var opening = tdClosedTarget(value);
    if (opening) { window.location.href = opening; return; }
    if (!value || !value.trim()) { fail(T.nothing); return; }
    busy = true;
    error.hidden = true;
    fetch('/api/throws', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: value })
    }).then(null, function () {
      // The browser's own failure wording is untranslated; ours is not.
      throw new Error(T.netSend);
    }).then(function (response) {
      if (response.status === 413) { throw new Error(T.tooBig); }
      if (response.status === 400) { throw new Error(T.nothing); }
      if (!response.ok) { throw new Error(T.throwFailed); }
      return response.json();
    }).then(function (data) {
      tdTrack('code_created');
      currentUrl = window.location.origin + '/' + data.code;
      codebig.textContent = data.code;
      urlEl.textContent = currentUrl.replace(/^https?:\\/\\//, '');
      qrEl.innerHTML = qrSVG(currentUrl);
      compose.hidden = true;
      done.hidden = false;
      throwAnim();
    }).catch(function (err) {
      fail(err && err.message ? err.message : T.netSend);
    }).then(function () {
      busy = false;
    });
  }

""" + _compose_wiring_js(track=True) + _get_card_js(track=True) + """
  // Pro fake-door: chip reveals the "coming soon" panel; the email is POSTed to
  // /api/pro-interest (a POST body, never the URL, so it stays out of any log).
  // This page — the open sender — is the only one left with browser analytics,
  // and pro_click / feedback_open are the only funnel facts a server log cannot
  // produce on its own: a click that never becomes a request. They live here,
  // where no key is ever born, which is what makes ADR 0003 affordable.
  var prochip = document.getElementById('prochip');
  var prodoor = document.getElementById('prodoor');
  var proemail = document.getElementById('proemail');
  var proerror = document.getElementById('proerror');
  var prothanks = document.getElementById('prothanks');
  var proform = document.getElementById('proform');
  var probusy = false;

  prochip.addEventListener('click', function () {
    prodoor.hidden = !prodoor.hidden;
    if (!prodoor.hidden) { tdTrack('pro_click'); proemail.focus(); }
  });

  document.getElementById('prosubmit').addEventListener('click', function () {
    if (probusy) { return; }
    var value = (proemail.value || '').trim();
    if (value.indexOf('@') < 1 || value.length > 254) {
      proerror.textContent = T.proBadEmail; proerror.hidden = false; return;
    }
    probusy = true; proerror.hidden = true;
    fetch('/api/pro-interest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: value })
    }).then(function (response) {
      if (response.status === 400) { throw new Error(T.proBadEmail); }
      if (!response.ok) { throw new Error(T.proNet); }
      proform.hidden = true;
      prothanks.textContent = T.proThanks;
      prothanks.hidden = false;
      tdTrack('pro_email');
    }).catch(function (err) {
      proerror.textContent = err && err.message ? err.message : T.proNet;
      proerror.hidden = false;
    }).then(function () {
      probusy = false;
    });
  });

  // Feedback: its own chip and panel, deliberately separate from the Pro
  // fake-door — this is us asking users for help, not selling. Same privacy
  // posture as the email: POST body only, file-only storage.
  var fbchip = document.getElementById('fbchip');
  var fbdoor = document.getElementById('fbdoor');
  var fbtext = document.getElementById('fbtext');
  var fbform = document.getElementById('fbform');
  var fberror = document.getElementById('fberror');
  var fbthanks = document.getElementById('fbthanks');
  var fbbusy = false;

  fbchip.addEventListener('click', function () {
    fbdoor.hidden = !fbdoor.hidden;
    if (!fbdoor.hidden) { tdTrack('feedback_open'); fbtext.focus(); }
  });

  document.getElementById('fbsubmit').addEventListener('click', function () {
    if (fbbusy) { return; }
    var value = (fbtext.value || '').trim();
    if (!value) { fberror.textContent = T.fbEmpty; fberror.hidden = false; return; }
    fbbusy = true; fberror.hidden = true;
    fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: value })
    }).then(function (response) {
      if (!response.ok) { throw new Error(T.proNet); }
      fbform.hidden = true;
      fbthanks.textContent = T.fbThanks;
      fbthanks.hidden = false;
      tdTrack('feedback');
    }).catch(function (err) {
      fberror.textContent = err && err.message ? err.message : T.proNet;
      fberror.hidden = false;
    }).then(function () {
      fbbusy = false;
    });
  });
})();
</script>
</body>
</html>
"""

# The closed sender. Its own page, with a shell that loads nothing: the key is
# generated in this tab and never leaves it except in the fragment of the link
# the sender copies. There is no code to dictate, so the QR is the result rather
# than a garnish — and a QR is also the only delivery channel that does not put
# the key into somebody's chat history.
_CLOSED_SENDER_TMPL: Final = _HEAD_NO_SCRIPT + """<body>
<div class="wrap">
  """ + _TOP + """

  <h1><span>@@taglineA@@</span> <span class="hl">@@taglineB@@</span></h1>
  <p class="sub">@@subClosed@@</p>

  """ + _mode_row(closed=True) + """

  <div class="stage" id="stage">
    """ + _DOG + _BONE + """

    <div class="card">
      <div id="compose">
        <textarea id="text" autofocus placeholder="@@placeholder@@"></textarea>
        <button class="btn wide" id="throw" type="button">@@throwBtn@@</button>
        <p id="error" class="error" hidden></p>
      </div>

      <div id="done" class="doneclosed" hidden>
        <p class="donelabel">@@doneClosedLabel@@</p>
        <div class="qr big" id="qr"></div>
        <div class="url" id="url"></div>
        <p class="hint">@@keyOnce@@</p>
        <div class="donerow">
          <button class="btn ghost" id="copyurl" type="button">@@copyLink@@</button>
          <button class="btn" id="again" type="button">@@againBtn@@</button>
        </div>
      </div>
    </div>
  </div>

""" + _GET_CARD + """

  <span class="chip">@@chipClosed@@</span>

""" + _FOOTER + """
</div>

<script>
var T = @@__T__@@;
""" + _QR_JS + _CRYPTO_JS + _CLOSED_RE_JS + _OWN_LINK_JS + _STORAGE_JS + """
(function () {""" + _COMPOSE_JS + """
  tdRemember('closed');
  text.value = tdTakeDraft();
  text.focus();

  // This page can be arrived at directly — a bookmark, or the mode we
  // remembered — so the check the homepage does cannot be relied on. A browser
  // that cannot encrypt says so before anything is typed, not after: finding
  // out at the moment you press throw means having already written the secret.
  if (!tdCryptoReady()) {
    fail(T.noCrypto);
    text.disabled = true;
    document.getElementById('throw').disabled = true;
  }

  document.getElementById('switchmode').addEventListener('click', function () {
    tdRemember('open');
    tdKeepDraft(text.value);
    window.location.href = '/';
  });

  function send(value) {
    if (busy) { return; }
    // One of our own closed links, wherever it came from: it carries a key, so
    // it is opened rather than thrown. Sending it would hand us the one thing
    // the closed mode promises we never receive.
    var opening = tdClosedTarget(value);
    if (opening) { window.location.href = opening; return; }
    if (!value || !value.trim()) { fail(T.nothing); return; }
    if (!tdCryptoReady()) { fail(T.noCrypto); return; }
    busy = true;
    error.hidden = true;
    var key;
    // Encrypt first, then send. The server is never given a chance to hold the
    // text, not even for the length of one request.
    tdNewKey().then(function (fresh) {
      key = fresh;
      return tdEncrypt(fresh, value);
    }).then(function (payload) {
      return fetch('/api/throws', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: payload, enc: TD_ENC })
      }).then(null, function () { throw new Error(T.netSend); });
    }).then(function (response) {
      if (response.status === 413) { throw new Error(T.tooBig); }
      if (response.status === 400) { throw new Error(T.nothing); }
      if (!response.ok) { throw new Error(T.throwFailed); }
      return response.json();
    }).then(function (data) {
      return tdExportKey(key).then(function (encoded) {
        // The key goes in the fragment and nowhere else. Fragments are not sent
        // with any request, so this URL is the only copy in existence.
        currentUrl = window.location.origin + '/' + data.code + '#' + encoded;
        var svg = qrSVG(currentUrl);
        qrEl.innerHTML = svg;
        qrEl.hidden = !svg;
        urlEl.textContent = currentUrl.replace(/^https?:\\/\\//, '');
        compose.hidden = true;
        done.hidden = false;
        throwAnim();
      });
    }).catch(function (err) {
      fail(err && err.message ? err.message : T.netSend);
    }).then(function () {
      busy = false;
    });
  }

""" + _compose_wiring_js(track=False) + _get_card_js(track=False) + """})();
</script>
</body>
</html>
"""

# The receiver. Same shell for every address, and the same shell whether or not
# a key is involved — the page reveals nothing about the throw before it asks.
# Nothing loaded over the network runs here: the decrypted text ends up in this
# tab's DOM, where stripping the key out of the URL would not protect it.
_RECEIVER_TMPL: Final = _HEAD_NO_SCRIPT + """<body>
<div class="wrap">
  """ + _TOP + """

  <div class="stage">
    """ + _DOG + """
    <div class="card">
      <p id="status">@@fetching@@</p>

      <div id="result" hidden>
        <pre id="text"></pre>
        <button class="btn ghost" id="copy" type="button">@@copyBtn@@</button>
      </div>
    </div>
  </div>

  <span class="chip" id="chip">@@chipEphemeral@@</span>

""" + _FOOTER + """
</div>

<script>
var T = @@__T__@@;
""" + _CRYPTO_JS + _CLOSED_RE_JS + """
(function () {
  var status = document.getElementById('status');
  var result = document.getElementById('result');
  var target = document.getElementById('text');
  var chip = document.getElementById('chip');

  var hash = window.location.hash || '';
  var key = hash.charAt(0) === '#' ? hash.slice(1) : '';
  var address = window.location.pathname.replace(/^\\/+/, '').replace(/\\/+$/, '');
  // Closed addresses and two-word codes are disjoint by construction (see
  // app.closedaddress), so this page knows a key is needed from the address
  // alone, before asking the server anything.
  var closed = CLOSED_RE.test(address);

  function fail(message) {
    status.className = 'error';
    status.textContent = message;
  }

  function show(value) {
    target.textContent = value;
    status.hidden = true;
    result.hidden = false;
  }

  // The key leaves the address bar the moment its fate is settled, and not
  // before. Every outcome that leaves the throw alive keeps the URL whole, so
  // reloading remains the honest advice; once the server has answered, the
  // throw is spent either way and the key has nothing left to do here.
  function stripKey() {
    if (!key) { return; }
    try {
      history.replaceState(null, '', window.location.pathname + window.location.search);
    } catch (e) {}
  }

  function read(imported) {
    return fetch('/api/throws/' + encodeURIComponent(address), { method: 'POST' })
      // A rejected fetch carries the browser's own wording ("Failed to fetch"),
      // untranslated and meaningless to the reader. Only messages we chose are
      // ever put on screen.
      .then(null, function () { throw new Error(T.netRecv); })
      .then(function (response) {
        stripKey();
        if (response.status === 404) { throw new Error(T.notFound); }
        if (!response.ok) { throw new Error(T.wrong); }
        return response.json();
      })
      .then(function (data) {
        if (!data.enc) { show(data.text); return; }
        if (!imported) { fail(T.keyBad); return; }
        chip.textContent = T.chipClosed;
        // Past this point the throw is spent whatever happens: we asked, and we
        // were given it. A key that does not fit says so plainly, because the
        // reader's next move is to ask for a new throw, not to reload.
        return tdDecrypt(imported, data.text).then(show, function () { fail(T.keyBad); });
      });
  }

  function netFail(err) {
    fail(err && err.message ? err.message : T.netRecv);
  }

  if (!closed) {
    read(null).catch(netFail);
  } else if (!tdCryptoReady()) {
    fail(T.noCrypto);
  } else if (!key) {
    fail(T.keyMissing);
  } else {
    // The key is checked HERE, before a single byte is asked of the server,
    // because asking is what consumes the throw. A link truncated mid-key is
    // the ordinary accident — mail clients wrap long URLs — and it is locally
    // detectable, so it must not cost the reader the throw. Only a key that is
    // well-formed but wrong gets that far, and that one we cannot know about
    // without trying.
    tdImportKey(key).then(read, function () { fail(T.keyMissing); }).catch(netFail);
  }

  document.getElementById('copy').addEventListener('click', function () {
    var button = document.getElementById('copy');
    var value = target.textContent;
    function ok() { button.textContent = T.copied; setTimeout(function () { button.textContent = T.copyBtn; }, 1500); }
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
      button.textContent = T.selectFallback;
    }
  });
})();
</script>
</body>
</html>
"""


# --- i18n -------------------------------------------------------------------
#
# Every user-facing string lives here, EN first, RU second. Both locales carry
# the *same* keys — no fallback gaps — so a page is fully translated or the test
# suite fails. Detection is server-side from the ``Accept-Language`` header
# (:func:`pick_locale`): EN is the default for any locale that isn't Russian,
# RU only when the browser actually prefers Russian. The strings are injected
# two ways — ``@@key@@`` tokens in the HTML, and a single ``var T = {...}`` JSON
# blob the inline JS reads — both rendered from the one dict below.
STRINGS: Final[dict[str, dict[str, str]]] = {
    "en": {
        "taglineA": "Throw it.",
        "taglineB": "The dog fetches.",
        "sub": "Paste text — get a short code and a QR. Open them on another device.",
        "subClosed": "Paste text — it is encrypted here, then you get a QR and a link. There is no code to type.",
        "placeholder": "Paste or type text. Pasting throws it right away.",
        "throwBtn": "throw 🦴",
        "doneLabel": "Type the code on the other device, or scan the QR:",
        "copyLink": "copy link",
        "hint": "The text is deleted the moment this link is opened.",
        "againBtn": "throw again",
        # No unconditional padlock anywhere near a throw: in the open mode there
        # is nothing for it to promise, and a lock icon reads as a promise.
        "chipOpen": "gone in 10 minutes — read once, then deleted",
        "chipClosed": "encrypted on your device — the server only ever holds ciphertext",
        "chipEphemeral": "read once — gone in 10 minutes",
        # Mode of the throw. Both halves describe what actually happens, in the
        # same breath and at the same length, so neither reads as the safe one.
        "modeLabel": "Mode of the throw",
        "modeOpenName": "Open",
        "modeOpenNote": "The server sees your text. A two-word code works — type it on the other device.",
        "modeClosedName": "Closed",
        "modeClosedNote": "Encrypted on this device; the server sees only ciphertext. Link or QR only, no code.",
        "modeClosedUnavailable": "Needs a modern browser over https — this one cannot encrypt.",
        "doneClosedLabel": "Scan this on the other device:",
        "keyOnce": "The key exists only in this link — we never receive it and cannot bring it back.",
        "noCrypto": "This browser cannot encrypt here. It needs a modern browser over https.",
        "keyMissing": "This link has no usable key — the part after # is missing or damaged. The throw is still waiting: ask for the whole link and open it again.",
        "keyBad": "This key does not fit — wrong or damaged link. The throw has been used up, so ask for a new one.",
        "nothing": "Nothing to throw yet.",
        "tooBig": "Text is too big — 64 KB limit.",
        "throwFailed": "Couldn't throw. Try again.",
        "netSend": "Network problem. Try again.",
        "copied": "copied",
        "fetching": "Fetching…",
        "copyBtn": "copy",
        "notFound": "Nothing here — expired, already read, or never existed.",
        "wrong": "Something went wrong. Refresh the page.",
        "netRecv": "Network problem. Refresh the page.",
        "selectFallback": "press Ctrl+C / long-press to copy",
        # Footer link labels appear on the main pages, so they ARE localised.
        # The pages they point to (/terms, /privacy) are EN-only (launch audience).
        "footerTerms": "Terms",
        "footerPrivacy": "Privacy",
        "proChip": "✨ Pro",
        "proTitle": "Pro coming soon, $4/mo",
        "proPerks": "Bigger files, longer TTL, custom codes. Want it? Leave your email.",
        "proEmailPlaceholder": "you@example.com",
        "proSubmit": "notify me",
        "proThanks": "thanks, you'll be first to know",
        "proBadEmail": "That doesn't look like an email.",
        "proNet": "Network problem. Try again.",
        "metaDescription": "Move text between devices in seconds: paste it, get two words and a QR, open on the other device. No accounts, no cookies, nothing stored — gone in 10 minutes.",
        "getLabel": "Got a code? Fetch it here:",
        "getPlaceholder": "two words: basted lily — or paste a whole link",
        "getBtn": "fetch",
        "fbChip": "💬 feedback",
        "fbTitle": "Help us make this better",
        "fbIntro": "We've just launched. If anything felt confusing, or you wished it worked differently — a couple of words here would really help us.",
        "fbPlaceholder": "What felt off? What's missing?",
        "fbSubmit": "send",
        "fbThanks": "thank you — this genuinely helps.",
        "fbEmpty": "Write something first.",
    },
    "ru": {
        "taglineA": "Кинь.",
        "taglineB": "Пёс принесёт.",
        "sub": "Вставь текст — получи короткий код и QR. Открой их на другом устройстве.",
        "subClosed": "Вставь текст — он шифруется здесь, ты получишь QR и ссылку. Код набирать не нужно.",
        "placeholder": "Вставь или набери текст. Вставка бросает сразу.",
        "throwBtn": "бросить 🦴",
        "doneLabel": "Набери код на другом устройстве или отсканируй QR:",
        "copyLink": "копировать ссылку",
        "hint": "Текст удалится, как только эту ссылку откроют.",
        "againBtn": "бросить ещё",
        "chipOpen": "исчезает через 10 минут — читается один раз",
        "chipClosed": "зашифровано на твоём устройстве — у сервера только шифр",
        "chipEphemeral": "читается один раз — исчезает через 10 минут",
        "modeLabel": "Режим броска",
        "modeOpenName": "Открытый",
        "modeOpenNote": "Сервер видит текст. Работает код из двух слов — набери его на другом устройстве.",
        "modeClosedName": "Закрытый",
        "modeClosedNote": "Шифруется на этом устройстве, сервер видит только шифр. Только ссылка или QR, кода нет.",
        "modeClosedUnavailable": "Нужен современный браузер и https — здесь шифровать нечем.",
        "doneClosedLabel": "Отсканируй на другом устройстве:",
        "keyOnce": "Ключ есть только в этой ссылке — мы его не получаем и вернуть не сможем.",
        "noCrypto": "Этот браузер здесь не умеет шифровать. Нужен современный браузер и https.",
        "keyMissing": "В ссылке нет годного ключа — часть после # потерялась или побилась. Бросок на месте: попроси прислать ссылку целиком и открой заново.",
        "keyBad": "Ключ не подошёл — ссылка не та или повреждена. Бросок уже потрачен, попроси бросить заново.",
        "nothing": "Пока нечего бросать.",
        "tooBig": "Слишком большой текст — лимит 64 КБ.",
        "throwFailed": "Не удалось бросить. Попробуй ещё раз.",
        "netSend": "Проблема сети. Попробуй ещё раз.",
        "copied": "скопировано",
        "fetching": "Приношу…",
        "copyBtn": "копировать",
        "notFound": "Ничего нет — истекло, уже прочитано или не существовало.",
        "wrong": "Что-то пошло не так. Обнови страницу.",
        "netRecv": "Проблема сети. Обнови страницу.",
        "selectFallback": "нажми Ctrl+C / удерживай, чтобы скопировать",
        "footerTerms": "Условия",
        "footerPrivacy": "Приватность",
        "proChip": "✨ Pro",
        "proTitle": "Pro скоро, $4/мес",
        "proPerks": "Больше размер, дольше хранение, свои коды. Нужно? Оставь имейл.",
        "proEmailPlaceholder": "you@example.com",
        "proSubmit": "сообщить мне",
        "proThanks": "спасибо, сообщим первыми",
        "proBadEmail": "Это не похоже на имейл.",
        "proNet": "Проблема сети. Попробуй ещё раз.",
        "metaDescription": "Перекинь текст между устройствами за секунды: вставь, получи два слова и QR, открой на другом устройстве. Без аккаунтов и куки, ничего не хранится — исчезает через 10 минут.",
        "getLabel": "Есть код? Забери здесь:",
        "getPlaceholder": "два слова: basted lily — или вставь ссылку целиком",
        "getBtn": "принести",
        "fbChip": "💬 отзыв",
        "fbTitle": "Помоги сделать лучше",
        "fbIntro": "Мы только запустились. Если что-то было непонятно или хотелось, чтобы работало иначе — пара слов здесь нам очень поможет.",
        "fbPlaceholder": "Что смутило? Чего не хватило?",
        "fbSubmit": "отправить",
        "fbThanks": "спасибо — это правда помогает.",
        "fbEmpty": "Сначала напиши что-нибудь.",
    },
}

DEFAULT_LOCALE: Final = "en"


def pick_locale(accept_language: str | None) -> str:
    """Pick ``"ru"`` or ``"en"`` from an ``Accept-Language`` header.

    RU only when the browser's most-preferred language (highest q-value) is
    Russian; EN is the default for everything else, including a missing or
    unparseable header. We compare against the whole ranked list rather than
    just the first entry so ``en;q=0.5, ru;q=0.9`` correctly resolves to RU.
    """
    if not accept_language:
        return DEFAULT_LOCALE
    best_lang = DEFAULT_LOCALE
    best_q = -1.0
    for part in accept_language.split(","):
        token = part.strip()
        if not token:
            continue
        tag, _, params = token.partition(";")
        tag = tag.strip().lower()
        if not tag or tag == "*":
            continue
        q = 1.0
        params = params.strip()
        if params.lower().startswith("q="):
            try:
                q = float(params[2:])
            except ValueError:
                q = 1.0
        if q > best_q:
            best_q = q
            best_lang = "ru" if tag.split("-")[0] == "ru" else "en"
    return best_lang


def _render(template: str, lang: str, head_meta: str = "") -> str:
    """Fill a page template's ``@@key@@`` tokens and ``var T`` blob for ``lang``.

    ``head_meta`` fills the shell's ``@@headMeta@@`` slot — SEO/preview tags on
    the indexable sender page, ``noindex`` on receiver pages — and may itself
    carry ``@@key@@`` tokens (it is substituted before the string pass).
    """
    strings = STRINGS[lang]
    out = template.replace("@@headMeta@@", head_meta)
    # The browser needs the same "is this a closed address?" rule the server
    # uses, and one drifting copy of it would silently break the guarantee that
    # a keyless arrival never consumes a throw. So it is injected from the
    # module that owns it, never written out here a second time.
    out = out.replace("@@__CLOSED_RE__@@", CLOSED_ADDRESS_PATTERN)
    out = out.replace("@@__T__@@", json.dumps(strings, ensure_ascii=False))
    out = out.replace("@@lang@@", lang)
    for key, value in strings.items():
        out = out.replace(f"@@{key}@@", value)
    return out


def render_sender(lang: str = DEFAULT_LOCALE) -> str:
    return _render(_SENDER_TMPL, lang, head_meta=_SENDER_HEAD_META)


def render_closed_sender(lang: str = DEFAULT_LOCALE) -> str:
    # Not indexable: the homepage is the one entry point, and this page is the
    # same product with a different mode selected.
    return _render(_CLOSED_SENDER_TMPL, lang, head_meta=_NOINDEX_META)


def render_receiver(lang: str = DEFAULT_LOCALE) -> str:
    return _render(_RECEIVER_TMPL, lang, head_meta=_NOINDEX_META)


def sender_page(accept_language: str | None = None) -> str:
    return render_sender(pick_locale(accept_language))


def closed_sender_page(accept_language: str | None = None) -> str:
    return render_closed_sender(pick_locale(accept_language))


def receiver_page(accept_language: str | None = None) -> str:
    return render_receiver(pick_locale(accept_language))


#: EN-rendered pages, kept as module constants so callers and the slice-8
#: page-size test can import a ready string. Locale-aware serving uses the
#: ``*_page(accept_language)`` helpers above.
SENDER_PAGE: Final = render_sender(DEFAULT_LOCALE)
CLOSED_SENDER_PAGE: Final = render_closed_sender(DEFAULT_LOCALE)
RECEIVER_PAGE: Final = render_receiver(DEFAULT_LOCALE)

#: The pages on which a key is born or lives. Nothing loaded over the network
#: may run here (ADR 0003); a test holds the line.
KEY_BEARING_PAGES: Final = (CLOSED_SENDER_PAGE, RECEIVER_PAGE)

# The API is banned outright; code pages carry their own noindex (crawlers
# only ever see one if a human published the link). The rest is public.
ROBOTS_TXT: Final = "User-agent: *\nDisallow: /api/\n"


# --- legal pages (Terms / Privacy) ------------------------------------------
#
# These two are deliberately English-only: the launch audience is EN, and RU
# versions of the legal copy are explicitly out of scope for now. So — unlike
# every other user-facing string — the body copy here does NOT go through the
# ``STRINGS`` i18n dict; it is hardcoded static English text. Only the footer
# *link labels* on the main pages are localised (``footerTerms``/``footerPrivacy``
# in ``STRINGS``); the destination pages themselves stay EN.
#
# They reuse the same sticker-punk shell (``_HEAD`` + ``_STYLE``) and the same
# ``noindex`` handling (the ``<meta robots>`` in ``_HEAD`` plus main.py's
# ``X-Robots-Tag`` middleware), so they cost no extra CSS and stay well under
# the 100 KB budget.
#
# The copy is intentionally short and truthful, matching the product's
# privacy-first model: ephemeral, one-time read, ~10 min TTL, RAM only, no
# accounts, no tracking cookies, content never logged, codes pseudonymized in
# logs. No boilerplate we can't stand behind.
#
# NOTE (HITL / founder step): the abuse@ mailbox below is only a UI address.
# Making abuse@throw.dog actually deliver mail is a manual one-time founder step
# in Cloudflare (Email Routing → route abuse@throw.dog to a real inbox). Nothing
# in this codebase provisions it.

_ABUSE_EMAIL: Final = "abuse@throw.dog"


def _legal_page(h1_html: str, body_html: str, slug: str, description: str) -> str:
    """Wrap static EN legal copy in the shared sticker-punk shell.

    ``_HEAD`` still carries the ``@@lang@@`` token (it is shared with the
    localised templates); legal pages are English, so we fill it with ``en``.
    Legal pages are indexable — a public product should show its terms.
    """
    meta = (
        f'<meta name="description" content="{description}">\n'
        f'<link rel="canonical" href="https://throw.dog/{slug}">'
    )
    head = _HEAD.replace("@@lang@@", DEFAULT_LOCALE).replace("@@headMeta@@", meta)
    return head + f"""<body>
<div class="wrap">
  <div class="top"><a class="toplink" href="/" aria-label="throw.dog home">{_PAW}<b>throw.dog</b></a></div>

  <h1>{h1_html}</h1>

  <div class="card prose">
{body_html}
  </div>

  <footer class="foot">
    <a href="/">home</a>
    <span aria-hidden="true">·</span>
    <a href="/terms">Terms</a>
    <span aria-hidden="true">·</span>
    <a href="/privacy">Privacy</a>
  </footer>
</div>
</body>
</html>
"""


_TERMS_BODY: Final = f"""    <h2>What this is</h2>
    <p>throw.dog moves a piece of text from one device to another. Paste text,
    get a short code and a QR, then open it on the other device. That is the
    whole service — no accounts, no sign-up.</p>

    <h2>Two modes, and what each one means</h2>
    <p>Before throwing, you choose the mode. In the <b>open</b> mode the throw is
    addressed by a two-word code you can type on the other device, and the text
    passes through our memory as you wrote it — we are able to read it. In the
    <b>closed</b> mode your browser encrypts the text before it leaves the
    device and we only ever hold ciphertext; the key travels in the part of the
    link after the <code>#</code>, which browsers never send to a server, so we
    never receive it. A closed throw has no two-word code and can only be opened
    from the whole link or its QR.</p>
    <p>Because we never have the key, we cannot recover a closed throw for you,
    and we cannot help if the link is lost or truncated. That is the price of the
    guarantee, not an oversight.</p>

    <h2>One throw, one read</h2>
    <p>Each throw is held for about 10 minutes and is deleted the instant it is
    handed out — whichever comes first. Opening the link consumes it: the text is
    gone and the link stops working. In the closed mode this is true even if the
    key turns out not to fit, because we cannot tell whether decryption
    succeeded — waiting to be told would be a way to have one throw handed out
    twice. Treat every throw as one-time and temporary, and do not rely on it to
    store anything.</p>

    <h2>Acceptable use</h2>
    <p>Do not use throw.dog to send illegal content, malware, or anything you
    have no right to share, and do not try to break, overload, or abuse the
    service. It is a pass-through pipe for moving your own text between devices.</p>

    <h2>No warranty</h2>
    <p>The service is provided as-is, on a best-effort basis, with no guarantee
    of availability or delivery. A throw can expire, fail, or be lost. Use it
    accordingly.</p>

    <h2>Abuse</h2>
    <p>Report abuse to <a class="abuse" href="mailto:{_ABUSE_EMAIL}">{_ABUSE_EMAIL}</a>.</p>"""


_PRIVACY_BODY: Final = f"""    <h2>The short version</h2>
    <p>throw.dog is built to know as little about you as possible: no accounts,
    no tracking cookies, no profiling analytics, no ads.</p>

    <h2>Your text</h2>
    <p>The text you throw lives only in the server's memory, for about 10 minutes
    at most, and is erased the moment it is handed out. Nothing is written to
    disk and nothing is kept long-term. The content of a throw is never logged.</p>
    <p>In the <b>closed</b> mode what reaches us is ciphertext your browser
    produced (AES-256-GCM), and the key never reaches us at all: it travels in
    the fragment of the link — the part after the <code>#</code> — which browsers
    do not send with any request. We could not read a closed throw if we wanted
    to, and we cannot recover one for you. In the <b>open</b> mode the text
    passes through our memory as you wrote it, and we are technically able to
    read it. The mode is your choice and it is shown on screen when you make
    it.</p>

    <h2>What the closed mode does not protect you from</h2>
    <p>It protects you from us as a place your text is stored. It does not
    protect you from us as the source of the page doing the encrypting: we serve
    that page, so anyone who can change what we serve could change it. No
    in-browser encryption anywhere can escape that, and we would rather name it
    than let the word "encrypted" imply otherwise. What we do about it is
    narrow and real: on the two pages where a key is created or used &mdash; the
    closed compose page, and any page that opens a link &mdash; every line of
    code that runs arrived inside that one document. No analytics, no fonts, no
    third-party code of any kind is loaded there. Those pages do make one
    request of their own, for the throw itself, and it never carries the key.
    Everything else is in the source you received, which is all there is to
    audit.</p>

    <h2>Logs</h2>
    <p>We keep minimal operational logs (for example, that a throw was created or
    read) to run the service and stop abuse. Throw codes are pseudonymized in
    logs with a keyed hash, so a log on its own cannot be turned back into a
    working code, and the text is never included.</p>

    <h2>Cookies &amp; tracking</h2>
    <p>No cookies, no profiling, no third-party trackers, no ads. The homepage
    and the legal pages load one script of our own — a cookieless visit counter
    self-hosted on our analytics subdomain, which records no identifiers and
    builds no profile. It is named here rather than tucked away because "no
    third-party scripts" and "no scripts at all" are different claims, and only
    the first is true of the homepage. The pages where a key exists &mdash; the
    closed sender and every page that opens a throw &mdash;
    load no script at all, by design. Nothing on any page is fetched from a
    CDN, a font host, or anyone else.</p>

    <h2>Contact</h2>
    <p>Questions or abuse reports:
    <a class="abuse" href="mailto:{_ABUSE_EMAIL}">{_ABUSE_EMAIL}</a>.</p>"""


TERMS_PAGE: Final = _legal_page(
    'Terms of <span class="hl">Service</span>',
    _TERMS_BODY,
    "terms",
    "Terms of service for throw.dog — ephemeral one-time text transfer.",
)
PRIVACY_PAGE: Final = _legal_page(
    'Privacy <span class="hl">Policy</span>',
    _PRIVACY_BODY,
    "privacy",
    "Privacy policy for throw.dog: no accounts, no cookies, nothing stored.",
)
