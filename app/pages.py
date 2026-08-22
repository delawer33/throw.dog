"""The two HTML pages, inlined.

No framework, no build step, no external requests — the whole point is that a
phone on a bad connection gets one small document and can act on it. The design
is "sticker-punk" (see ``model/08-design.md``): cream paper, ink borders, hard
offset shadows, a dog at the transfer card, and a bone that arcs on throw. Fonts
are system-ui (0 font bytes) and every asset — CSS, JS, SVG, the QR generator —
is inline, so a page is one self-contained document well under 100 KB.

The receiver page is identical for every code: it carries no throw content and
fetches it with a POST. Link previews and prefetchers issue GETs, and a GET
must never burn a one-shot throw.
"""

from __future__ import annotations

import json
from typing import Final

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
  .top { display: flex; align-items: center; gap: 12px; margin-bottom: 30px; }
  .top b { font-size: 24px; font-weight: 900; letter-spacing: -.5px; }
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
  .stage.thrown .dog { animation: excited .5s ease .45s; }
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
  .stage.thrown .bone { animation: arc 1s ease-in forwards; }
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
  .stage.thrown #done { animation: pop .35s cubic-bezier(.5,1.8,.6,1) .5s backwards; }
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
  .error {
    color: var(--red); font-weight: 800; font-size: 14px; margin-top: 12px;
    background: #fff; border: 2px solid var(--red); border-radius: 10px; padding: 10px 12px;
  }
  [hidden] { display: none !important; }

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

_HEAD: Final = """<!doctype html>
<html lang="@@lang@@">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>throw.dog</title>
<style>%s</style>
</head>
""" % _STYLE

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

_SENDER_TMPL: Final = _HEAD + """<body>
<div class="wrap">
  <div class="top">""" + _PAW + """<b>throw.dog</b></div>

  <h1><span>@@taglineA@@</span> <span class="hl">@@taglineB@@</span></h1>
  <p class="sub">@@sub@@</p>

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

  <span class="chip">@@chip@@</span>
</div>

<script>
var T = @@__T__@@;
""" + _QR_JS + """
(function () {
  var text = document.getElementById('text');
  var error = document.getElementById('error');
  var compose = document.getElementById('compose');
  var done = document.getElementById('done');
  var stage = document.getElementById('stage');
  var codebig = document.getElementById('codebig');
  var urlEl = document.getElementById('url');
  var qrEl = document.getElementById('qr');
  var currentUrl = '';
  var busy = false;

  text.focus();

  function fail(message) {
    error.textContent = message;
    error.hidden = false;
  }

  function throwAnim() {
    stage.classList.remove('thrown');
    void stage.offsetWidth;
    stage.classList.add('thrown');
  }

  function send(value) {
    if (busy) { return; }
    if (!value || !value.trim()) { fail(T.nothing); return; }
    busy = true;
    error.hidden = true;
    fetch('/api/throws', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: value })
    }).then(function (response) {
      if (response.status === 413) { throw new Error(T.tooBig); }
      if (response.status === 400) { throw new Error(T.nothing); }
      if (!response.ok) { throw new Error(T.throwFailed); }
      return response.json();
    }).then(function (data) {
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
})();
</script>
</body>
</html>
"""

_RECEIVER_TMPL: Final = _HEAD + """<body>
<div class="wrap">
  <div class="top">""" + _PAW + """<b>throw.dog</b></div>

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

  <span class="chip">@@chip@@</span>
</div>

<script>
var T = @@__T__@@;
(function () {
  var status = document.getElementById('status');
  var result = document.getElementById('result');
  var target = document.getElementById('text');
  var code = window.location.pathname.replace(/^\\/+/, '').replace(/\\/+$/, '');

  fetch('/api/throws/' + encodeURIComponent(code), { method: 'POST' })
    .then(function (response) {
      if (response.status === 404) { throw new Error(T.notFound); }
      if (!response.ok) { throw new Error(T.wrong); }
      return response.json();
    })
    .then(function (data) {
      target.textContent = data.text;
      status.hidden = true;
      result.hidden = false;
    })
    .catch(function (err) {
      status.className = 'error';
      status.textContent = err && err.message ? err.message : T.netRecv;
    });

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
        "placeholder": "Paste or type text. Pasting throws it right away.",
        "throwBtn": "throw 🦴",
        "doneLabel": "Type the code on the other device, or scan the QR:",
        "copyLink": "copy link",
        "hint": "The text is deleted the moment this link is opened.",
        "againBtn": "throw again",
        "chip": "🔒 nothing is stored — gone in 10 minutes",
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
    },
    "ru": {
        "taglineA": "Кинь.",
        "taglineB": "Пёс принесёт.",
        "sub": "Вставь текст — получи короткий код и QR. Открой их на другом устройстве.",
        "placeholder": "Вставь или набери текст. Вставка бросает сразу.",
        "throwBtn": "бросить 🦴",
        "doneLabel": "Набери код на другом устройстве или отсканируй QR:",
        "copyLink": "копировать ссылку",
        "hint": "Текст удалится, как только эту ссылку откроют.",
        "againBtn": "бросить ещё",
        "chip": "🔒 ничего не хранится — исчезает через 10 минут",
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


def _render(template: str, lang: str) -> str:
    """Fill a page template's ``@@key@@`` tokens and ``var T`` blob for ``lang``."""
    strings = STRINGS[lang]
    out = template.replace("@@__T__@@", json.dumps(strings, ensure_ascii=False))
    out = out.replace("@@lang@@", lang)
    for key, value in strings.items():
        out = out.replace(f"@@{key}@@", value)
    return out


def render_sender(lang: str = DEFAULT_LOCALE) -> str:
    return _render(_SENDER_TMPL, lang)


def render_receiver(lang: str = DEFAULT_LOCALE) -> str:
    return _render(_RECEIVER_TMPL, lang)


def sender_page(accept_language: str | None = None) -> str:
    return render_sender(pick_locale(accept_language))


def receiver_page(accept_language: str | None = None) -> str:
    return render_receiver(pick_locale(accept_language))


#: EN-rendered pages, kept as module constants so callers and the slice-8
#: page-size test can import a ready string. Locale-aware serving uses the
#: ``*_page(accept_language)`` helpers above.
SENDER_PAGE: Final = render_sender(DEFAULT_LOCALE)
RECEIVER_PAGE: Final = render_receiver(DEFAULT_LOCALE)

ROBOTS_TXT: Final = "User-agent: *\nDisallow: /\n"
