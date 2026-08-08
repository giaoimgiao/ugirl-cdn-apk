#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UGIRL 免费CDN - 本地文件管理 APP v2.0 (PIXEL)
==============================================
零依赖(纯标准库)。启动后自动打开浏览器, 本地管理 prod.ugirl.ai CDN 文件。
上传: 浏览器 XHR 直传 R2 (真实进度条)
功能: 一键开容器 / token直连 / 拖拽上传(进度) / 网页资源提取转存 / 强制下载 / 多容器隔离
用法:
    python3 ugirl_cdn_app.py            # 默认端口 8866
    UG_APP_PORT=9000 python3 ugirl_cdn_app.py
"""
import json, os, sys, time, re, uuid, threading, webbrowser, urllib.request, urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

BASE = "https://backend.ugirl.vip/api/v1"
if getattr(sys, "frozen", False):
    DATA_DIR = os.path.dirname(sys.executable)
else:
    DATA_DIR = os.path.dirname(os.path.abspath(__file__))
ACC_FILE = os.path.join(DATA_DIR, "ugirl_app_accounts.json")
PORT = int(os.environ.get("UG_APP_PORT", "8866"))
UA = "ugirl-cdn-app/2.0"

def load_accounts():
    try: return json.load(open(ACC_FILE))
    except Exception: return {}
def save_accounts(a): json.dump(a, open(ACC_FILE, "w"), ensure_ascii=False, indent=1)
def load_idx(uid):
    try: return json.load(open(os.path.join(DATA_DIR, f"ugirl_idx_{uid}.json")))
    except Exception: return {}
def save_idx(uid, idx): json.dump(idx, open(os.path.join(DATA_DIR, f"ugirl_idx_{uid}.json"), "w"), ensure_ascii=False, indent=1)

def api_json(path, method="GET", token=None, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", UA)
    if isinstance(token, dict):
        token = token.get("accessToken") or token.get("token") or ""
    if token: req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}

def register_account():
    email = f"cdn{uuid.uuid4().hex[:10]}@outlook.com"
    pw = "Cdnu@" + uuid.uuid4().hex[:10]
    st, d = api_json("/auth/register", "POST", body={"email": email, "password": pw, "nickname": "cdn_user"})
    if st not in (200, 201): return None, f"注册失败 {st} {json.dumps(d)[:100]}"
    token = d.get("token", "")
    if isinstance(token, dict): token = token.get("accessToken", "")
    prof = d.get("profile", {})
    uid = str(prof.get("id") or int(time.time()))
    if not token: return None, "注册响应无 token"
    acc = {"id": uid, "email": email, "password": pw, "token": token, "created": int(time.time())}
    accs = load_accounts(); accs[uid] = acc; save_accounts(accs)
    return acc, None

def presign_only(token, fname, size):
    st, d = api_json("/storage/presigned-url", "POST", token,
                     body={"fileType": "s3", "fileName": fname, "fileSize": size,
                           "contentType": "application/octet-stream", "accessLevel": "PUBLIC"}, timeout=20)
    if st not in (200, 201): return None, f"presign {st} {json.dumps(d)[:150]}"
    dd = d.get("data", {})
    return {"presignedUrl": dd.get("presignedUrl"), "filePath": dd.get("filePath")}, None

def get_url(token, fp):
    st, d = api_json("/storage/file-url", "POST", token, body={"filePath": fp}, timeout=20)
    return d.get("data", {}).get("url", "") if st == 200 else ""

def fetch_and_store(token, src, name):
    try:
        req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            content = r.read()
    except Exception as e:
        return None, str(e)[:100]
    p, err = presign_only(token, name or "file.bin", len(content))
    if not p: return None, err
    req = urllib.request.Request(p["presignedUrl"], data=content, method="PUT")
    req.add_header("Content-Length", str(len(content)))
    with urllib.request.urlopen(req, timeout=120) as r:
        if r.status not in (200, 201): return None, f"PUT {r.status}"
    url = get_url(token, p["filePath"])
    return {"filePath": p["filePath"], "url": url, "size": len(content)}, None

def parse_assets(src):
    try:
        req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        return None, str(e)[:100]
    out = set()
    for m in re.finditer(r'(?:src|href|poster)\s*=\s*["\']([^"\']+)["\']', html, re.I):
        u = m.group(1)
        if u.startswith(("data:", "javascript:", "#")): continue
        try:
            absu = urllib.parse.urljoin(src, u)
            if absu.startswith("http"): out.add(absu)
        except Exception: pass
    for m in re.finditer(r'url\(\s*["\']?([^"\')]+)["\']?\s*\)', html, re.I):
        try:
            absu = urllib.parse.urljoin(src, m.group(1))
            if absu.startswith("http"): out.add(absu)
        except Exception: pass
    return list(out)[:40], None

UI = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>UGIRL 免费CDN · 本地版</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0f0e17;color:#e0e0e0;font-family:'Courier New',monospace;min-height:100vh;
 background-image:linear-gradient(rgba(0,229,255,.04) 1px,transparent 1px),linear-gradient(90deg,rgba(0,229,255,.04) 1px,transparent 1px);
 background-size:32px 32px}
header{display:flex;align-items:center;justify-content:space-between;padding:12px 20px;background:#15162b;border-bottom:2px solid #00e5ff;position:sticky;top:0;z-index:9}
header .lg{font-size:16px;color:#00e5ff;letter-spacing:2px;font-weight:bold}
header .lg span{color:#ff2d95}
header .st{font-size:12px;color:#8b8fa8;letter-spacing:1px}
header .st b{color:#00e676}
.wrap{max-width:900px;margin:0 auto;padding:24px 16px 60px;width:100%}
.card{background:#15162b;border:2px solid #2d2f45;padding:18px;margin-bottom:18px;position:relative}
.card::before{content:'';position:absolute;top:-2px;left:-2px;width:14px;height:14px;background:#ff2d95}
.card h3{font-size:14px;color:#00e5ff;letter-spacing:2px;margin-bottom:14px}
.card h3::after{content:'▓▓▓';color:#2d2f45;margin-left:8px}
.hint{font-size:11px;color:#8b8fa8;margin-top:10px;line-height:1.8}
input[type=text],input[type=password]{width:100%;padding:10px 12px;background:#0f0e17;border:2px solid #2d2f45;color:#e0e0e0;font-family:'Courier New',monospace;font-size:13px;margin-bottom:10px;outline:none}
input:focus{border-color:#00e5ff}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.pixel-btn{font-family:'Courier New',monospace;font-size:13px;letter-spacing:1px;padding:8px 16px;
 background:#00e5ff;color:#0f0e17;border:2px solid #0f0e17;box-shadow:4px 4px 0 #0f0e17;cursor:pointer;transition:.12s}
.pixel-btn:hover{background:#7af2ff;transform:translate(2px,2px);box-shadow:2px 2px 0 #0f0e17}
.pixel-btn:active{transform:translate(4px,4px);box-shadow:0 0 0 #0f0e17}
.pixel-btn.green{background:#00e676;box-shadow:4px 4px 0 #0f0e17,4px 4px 0 2px #ffd500}
.pixel-btn.yellow{background:#ffd500;box-shadow:4px 4px 0 #0f0e17}
.pixel-btn.dark{background:#2d2f45;color:#00e5ff;box-shadow:4px 4px 0 #0f0e17}
.pixel-btn:disabled{opacity:.4;cursor:not-allowed}
.drop{border:3px dashed #2d2f45;padding:36px 20px;text-align:center;color:#8b8fa8;cursor:pointer;transition:.15s;background:#0f0e17}
.drop:hover,.drop.over{border-color:#00e5ff;color:#00e5ff;background:rgba(0,229,255,.05)}
.drop .big{font-size:20px;letter-spacing:3px;margin-bottom:8px}
.drop .small{font-size:11px}
#qwrap{display:none;margin-top:14px}
.qitem{background:#0f0e17;border:2px solid #2d2f45;padding:10px 12px;margin-bottom:8px}
.qitem .qn{font-size:12px;color:#e0e0e0;margin-bottom:6px;display:flex;justify-content:space-between}
.qitem .qn .pc{color:#ffd500}
.pbar{height:16px;background:#0f0e17;border:1px solid #2d2f45;overflow:hidden}
.pbar .fill{height:100%;width:0%;background:repeating-linear-gradient(90deg,#00e5ff 0 10px,#00b8d4 10px 20px);transition:width .15s}
.folder{background:#0f0e17;border:2px solid #2d2f45;margin-bottom:10px}
.folder .fh{display:flex;align-items:center;gap:10px;padding:10px 12px;cursor:pointer;user-select:none}
.folder .fh:hover{background:rgba(0,229,255,.04)}
.folder .fh .arr{color:#ffd500;font-size:12px;width:16px}
.folder .fh .nm{color:#e0e0e0;font-size:13px;flex:1}
.folder .fh .meta{color:#565a75;font-size:11px}
.folder .fb{display:none;border-top:2px solid #2d2f45;padding:6px 12px}
.folder.open .fb{display:block}
.folder.open .fh .arr{transform:rotate(90deg)}
.frow{display:flex;align-items:center;gap:10px;padding:8px 4px;border-bottom:1px dashed #23243a;font-size:12px;flex-wrap:wrap}
.frow:last-child{border-bottom:none}
.frow .fl{color:#00e5ff;font-size:11px;max-width:300px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer;flex:1;min-width:120px}
.mbtn{font-family:'Courier New',monospace;font-size:11px;padding:4px 10px;border:1px solid #2d2f45;cursor:pointer;color:#0f0e17;background:#00e5ff;letter-spacing:1px}
.mbtn:hover{filter:brightness(1.2)}
.mbtn.dl{background:#ffd500}.mbtn.del{background:#ff2d95}.mbtn.cp{background:#00e676}
#reslist{margin-top:12px}
.res{display:flex;align-items:center;gap:10px;padding:7px 4px;border-bottom:1px dashed #23243a;font-size:11px}
.res .rt{color:#00e5ff;font-size:10px;background:#1a1b33;padding:2px 6px;border:1px solid #2d2f45;white-space:nowrap}
.res .ru{flex:1;color:#8b8fa8;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.toast{position:fixed;bottom:30px;left:50%;transform:translateX(-50%);background:#00e676;color:#0f0e17;padding:10px 26px;font-size:13px;letter-spacing:1px;display:none;z-index:99;border:2px solid #0f0e17;box-shadow:4px 4px 0 #0f0e17;font-family:'Courier New',monospace}
.toast.err{background:#ff2d95;color:#fff}
.empty{color:#565a75;font-size:12px;text-align:center;padding:20px}
.accitem{display:flex;align-items:center;justify-content:space-between;background:#0f0e17;border:2px solid #2d2f45;padding:10px 12px;margin-bottom:8px;font-size:12px}
.accitem .em{color:#8b8fa8}.accitem .cur{color:#7ee787}
</style></head><body>
<header><div class="lg">UGIRL<span>CDN</span> ▸ 本地版</div><div class="st">容器: <b id="curSt">未连接</b></div></header>
<div class="wrap">
  <div class="card" id="connCard">
    <h3>连接容器</h3>
    <div class="row">
      <button class="pixel-btn green" id="regBtn">🆕 一键开新容器</button>
      <input type="text" id="tok" placeholder="或粘贴 ugirl token" style="flex:1;min-width:200px;margin-bottom:0">
      <button class="pixel-btn" id="connBtn">连接</button>
      <button class="pixel-btn dark" id="accBtn">👤 容器</button>
    </div>
    <div class="hint">每个账号 = 独立容器：文件互不可见、互不可删。Token 仅存于本机。</div>
  </div>
  <div class="card" id="accCard" style="display:none">
    <h3>容器列表</h3>
    <div id="acclist"></div>
  </div>
  <div class="card">
    <h3>上传文件</h3>
    <div class="drop" id="drop"><div class="big">⬇ 拖拽文件到此处</div><div class="small">或点击选择 · 浏览器直传 R2 · 支持任意类型</div></div>
    <input type="file" id="fileIn" multiple hidden>
    <div id="qwrap"></div>
  </div>
  <div class="card">
    <h3>网页资源提取</h3>
    <div class="row">
      <input type="text" id="furl" placeholder="输入网页 URL，提取其静态资源（图片/CSS/JS）" style="flex:1;min-width:200px">
      <button class="pixel-btn yellow" id="parseBtn">解析</button>
      <button class="pixel-btn dark" id="allBtn" style="display:none">全部转存</button>
    </div>
    <div id="reslist"></div>
  </div>
  <div class="card">
    <h3>我的文件 (<span id="fcount">0</span>)</h3>
    <div id="flist"><div class="empty">▮ 暂无文件，上传或转存后显示 ▯</div></div>
  </div>
</div>
<div class="toast" id="toast"></div>
<script>
let TOK=localStorage.getItem('ug_tok')||'', IDX=idxLoad(), PARSED=[];
const $=id=>document.getElementById(id);
function toast(m,e){const t=$('toast');t.textContent=m;t.className='toast'+(e?' err':'');t.style.display='block';clearTimeout(t._t);t._t=setTimeout(()=>t.style.display='none',2800)}
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'"')}
function fmtSize(b){if(b==null)return'';if(b<1024)return b+'B';if(b<1048576)return(b/1024).toFixed(1)+'KB';return(b/1048576).toFixed(2)+'MB'}
async function j(path,opt={}){opt.headers=Object.assign({'Content-Type':'application/json'},opt.headers||{});const r=await fetch(path,opt);const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||('HTTP '+r.status));return d}
function idxLoad(){try{return JSON.parse(localStorage.getItem('ug_idx')||'{}')}catch(e){return{}}}
function idxSave(){localStorage.setItem('ug_idx',JSON.stringify(IDX))}
function hasTok(){return !!TOK}
function connected(){$('curSt').textContent=($('tok').value.trim()||'已连接');$('connCard').style.display='none';render()}
function render(){const arr=Object.entries(IDX).map(([fp,v])=>({fp,...v})).sort((a,b)=>b.time-a.time);$('fcount').textContent=arr.length;
$('flist').innerHTML=arr.length?'':'<div class="empty">▮ 暂无文件，上传或转存后显示 ▯</div>';
arr.forEach(f=>{const el=document.createElement('div');el.className='folder';
el.innerHTML='<div class="fh"><span class="arr">▶</span><span class="nm">📁 '+esc(f.file||f.fp)+'</span><span class="meta">'+fmtSize(f.size)+' · '+new Date(f.time*1000).toLocaleString()+'</span></div><div class="fb"><div class="frow"><span class="fl" title="'+f.url+'">'+f.url+'</span><button class="mbtn cp" onclick="copyU(\\''+f.fp+'\\')">复制</button><button class="mbtn dl" onclick="dlF(\\''+f.fp+'\\')">下载</button><button class="mbtn del" onclick="delF(\\''+f.fp+'\\')">删除</button></div></div>';
el.querySelector('.fh').onclick=()=>el.classList.toggle('open');$('flist').appendChild(el)})}
async function copyU(fp){const d=await j('/api/url?filePath='+encodeURIComponent(fp));await navigator.clipboard.writeText(d.url);toast('✅ 已复制')}
async function dlF(fp){const r=await fetch('/api/raw?dl=1&filePath='+encodeURIComponent(fp));if(!r.ok)return toast('下载失败',1);const b=await r.blob();const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=(IDX[fp]&&IDX[fp].file)||fp.split('/').pop();a.click();URL.revokeObjectURL(a.href)}
async function delF(fp){if(!confirm('删除 '+fp+' ?'))return;await j('/api/delete',{method:'POST',body:JSON.stringify({filePath:fp})});delete IDX[fp];idxSave();toast('🗑 已删除');render()}
$('regBtn').onclick=async()=>{$('regBtn').disabled=true;toast('注册中...');try{const d=await j('/api/register',{method:'POST'});TOK=d.token;localStorage.setItem('ug_tok',TOK);connected();toast('✅ 新容器: '+d.email)}catch(e){toast(e.message,1)}finally{$('regBtn').disabled=false}};
$('connBtn').onclick=()=>{const t=$('tok').value.trim();if(!t)return toast('先粘贴 token',1);TOK=t;localStorage.setItem('ug_tok',TOK);connected();toast('✅ 已连接')};
$('accBtn').onclick=async()=>{const c=$('accCard');c.style.display=c.style.display==='none'?'block':'none';if(c.style.display==='block'){try{const d=await j('/api/accounts');$('acclist').innerHTML='';d.accounts.forEach(a=>{const el=document.createElement('div');el.className='accitem';el.innerHTML='<div><span class="em">'+esc(a.email)+'</span> <span class="cur">'+(a.cur?'·当前':'')+'</span></div><button class="mbtn cp" onclick="switchAcc(\\''+a.id+'\\')">切换</button>';$('acclist').appendChild(el)})}catch(e){toast(e.message,1)}}};
async function switchAcc(id){await j('/api/switch',{method:'POST',body:JSON.stringify({id})});location.reload()}
const drop=$('drop');drop.onclick=()=>{if(!hasTok())return toast('请先连接容器',1);$('fileIn').click()};
drop.ondragover=e=>{e.preventDefault();drop.classList.add('over')};drop.ondragleave=()=>drop.classList.remove('over');
drop.ondrop=e=>{e.preventDefault();drop.classList.remove('over');if(!hasTok())return toast('请先连接容器',1);if(e.dataTransfer.files.length)up(e.dataTransfer.files)};
$('fileIn').onchange=()=>{if($('fileIn').files.length)up($('fileIn').files)};
async function up(files){$('qwrap').style.display='block';$('qwrap').innerHTML='';for(const f of files){const el=document.createElement('div');el.className='qitem';
el.innerHTML='<div class="qn"><span>⬆ '+esc(f.name)+'</span><span class="pc">0%</span></div><div class="pbar"><div class="fill"></div></div>';$('qwrap').appendChild(el);
const fill=el.querySelector('.fill'),pc=el.querySelector('.pc');
try{
  const p=await j('/api/presign',{method:'POST',body:JSON.stringify({fileName:f.name,fileSize:f.size})});
  const x=new XMLHttpRequest();x.open('PUT',p.presignedUrl);
  x.upload.onprogress=e=>{if(e.lengthComputable){const pcnt=Math.round(e.loaded/e.total*100);fill.style.width=pcnt+'%';pc.textContent=pcnt+'%'}};
  await new Promise((res,rej)=>{x.onload=()=>x.status>=200&&x.status<300?res():rej(new Error('R2 '+x.status));x.onerror=()=>rej(new Error('网络错误'));x.send(f)});
  const u=await j('/api/url?filePath='+encodeURIComponent(p.filePath));
  const rec=await j('/api/record',{method:'POST',body:JSON.stringify({filePath:p.filePath,file:f.name,url:u.url,size:f.size})});
  IDX[rec.filePath]={file:f.name,url:u.url,size:f.size,time:Date.now()/1000};idxSave();
  fill.style.width='100%';pc.textContent='✓ 完成';
}catch(e){fill.style.background='#ff2d95';pc.textContent='✗ '+e.message.slice(0,18)}}
setTimeout(()=>{$('qwrap').style.display='none'},1600);render()}
$('parseBtn').onclick=async()=>{const u=$('furl').value.trim();if(!u)return toast('输入 URL',1);if(!hasTok())return toast('请先连接容器',1);$('parseBtn').disabled=true;toast('解析中...');try{const d=await j('/api/parse',{method:'POST',body:JSON.stringify({url:u})});PARSED=d.assets||[];$('reslist').innerHTML='';if(!PARSED.length){$('reslist').innerHTML='<div class="empty">未提取到资源</div>';$('allBtn').style.display='none';return}PARSED.forEach((a,i)=>{const ext=(a.split('?')[0].split('.').pop()||'?').slice(0,4).toUpperCase();const el=document.createElement('div');el.className='res';el.innerHTML='<span class="rt">'+ext+'</span><span class="ru">'+esc(a)+'</span><button class="mbtn cp" onclick="storeOne('+i+')">转存</button>';$('reslist').appendChild(el)});$('allBtn').style.display='inline-block';toast('✅ 提取到 '+PARSED.length+' 个资源')}catch(e){toast(e.message,1)}finally{$('parseBtn').disabled=false}};
async function storeOne(i){const a=PARSED[i];toast('转存中...');try{const d=await j('/api/fetch',{method:'POST',body:JSON.stringify({url:a,name:(a.split('/').pop().split('?')[0]||'file.bin').slice(0,60)})});IDX[d.filePath]={file:d.name,url:d.url,size:d.size,time:Date.now()/1000};idxSave();toast('✅ '+d.url);render()}catch(e){toast(e.message,1)}}
$('allBtn').onclick=async()=>{const L=PARSED.slice();$('allBtn').disabled=true;for(let i=0;i<L.length;i++){toast('转存 '+i+'/'+L.length);try{const d=await j('/api/fetch',{method:'POST',body:JSON.stringify({url:L[i],name:(L[i].split('/').pop().split('?')[0]||'file.bin').slice(0,60)})});IDX[d.filePath]={file:d.name,url:d.url,size:d.size,time:Date.now()/1000};idxSave()}catch(e){toast(e.message,1)}}$('allBtn').disabled=false;toast('✅ 全部完成');render()};
if(hasTok())connected();else render();
</script></body></html>"""

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass
    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def _html(self, s):
        b = s.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)
    def _body(self): return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/": return self._html(UI)
        q = parse_qs(u.query)
        accs = load_accounts(); cur = accs.get("__cur__")
        if u.path == "/api/me":
            return self._json(200, {"email": accs[cur]["email"] if cur else None})
        if u.path == "/api/list":
            return self._json(200, {"files": load_idx(cur) if cur else {}})
        if u.path == "/api/accounts":
            lst = [{"id": k, "email": v["email"], "cur": k == cur} for k, v in accs.items() if k != "__cur__"]
            return self._json(200, {"accounts": lst})
        if u.path == "/api/url":
            fp = q.get("filePath", [""])[0]
            if not cur or not fp: return self._json(400, {"error": "bad request"})
            url = get_url(accs[cur]["token"], fp)
            return self._json(200, {"filePath": fp, "url": url} if url else {"error": "not found"})
        if u.path == "/api/raw":
            fp = q.get("filePath", [""])[0]
            dl = q.get("dl", ["0"])[0] == "1"
            if not cur or not fp: return self._json(400, {"error": "bad request"})
            url = get_url(accs[cur]["token"], fp)
            if not url: return self._json(404, {"error": "not found"})
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = r.read()
                self.send_response(200)
                if dl:
                    name = fp.split("/")[-1]
                    self.send_header("Content-Disposition", 'attachment; filename="' + name + '"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                return self._json(502, {"error": str(e)[:80]})
            return
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        accs = load_accounts(); cur = accs.get("__cur__")
        if u.path == "/api/register":
            acc, err = register_account()
            if not acc: return self._json(400, {"error": err})
            accs = load_accounts(); accs["__cur__"] = acc["id"]; save_accounts(accs)
            return self._json(201, {"email": acc["email"], "id": acc["id"], "token": acc["token"]})
        if u.path == "/api/switch":
            try: d = json.loads(self._body() or b"{}")
            except Exception: return self._json(400, {"error": "bad json"})
            uid = d.get("id", "")
            accs = load_accounts()
            if uid not in accs: return self._json(404, {"error": "no such account"})
            accs["__cur__"] = uid; save_accounts(accs)
            return self._json(200, {"email": accs[uid]["email"]})
        if u.path == "/api/token":
            try: d = json.loads(self._body() or b"{}")
            except Exception: return self._json(400, {"error": "bad json"})
            tok = d.get("token", "").strip()
            if not tok: return self._json(400, {"error": "token required"})
            st, d2 = api_json("/users/me", "GET", tok)
            if st != 200: st, d2 = api_json("/user/me", "GET", tok)
            uid = str(d2.get("data", {}).get("id") or d2.get("data", {}).get("userId") or d2.get("id") or "tok_" + uuid.uuid4().hex[:6])
            email = d2.get("data", {}).get("email") or d2.get("email") or f"token-{uid}"
            accs = load_accounts()
            accs[uid] = {"id": uid, "email": email, "password": "", "token": tok, "created": int(time.time())}
            accs["__cur__"] = uid; save_accounts(accs)
            return self._json(200, {"email": email, "id": uid})
        if not cur: return self._json(401, {"error": "no active account"})
        tok = accs[cur]["token"]
        try: d = json.loads(self._body() or b"{}")
        except Exception: return self._json(400, {"error": "bad json"})
        if u.path == "/api/presign":
            p, err = presign_only(tok, d.get("fileName", "file.bin"), int(d.get("fileSize", 0)))
            if not p: return self._json(502, {"error": err})
            return self._json(200, p)
        if u.path == "/api/record":
            fp = d.get("filePath", "")
            if not fp: return self._json(400, {"error": "filePath required"})
            idx = load_idx(cur)
            idx[fp] = {"file": d.get("file", "file.bin"), "url": d.get("url", ""), "size": d.get("size", 0), "time": time.time()}
            save_idx(cur, idx)
            return self._json(201, {"filePath": fp})
        if u.path == "/api/delete":
            fp = d.get("filePath", "")
            if not fp: return self._json(400, {"error": "filePath required"})
            st = api_json("/storage/file", "DELETE", tok, body={"filePath": fp})[0]
            idx = load_idx(cur)
            if fp in idx: del idx[fp]; save_idx(cur, idx)
            return self._json(200, {"deleted": fp, "status": st})
        if u.path == "/api/fetch":
            src = d.get("url", "")
            if not src.startswith(("http://", "https://")): return self._json(400, {"error": "bad url"})
            res, err = fetch_and_store(tok, src, d.get("name"))
            if not res: return self._json(502, {"error": err})
            idx = load_idx(cur)
            idx[res["filePath"]] = {"file": d.get("name") or src.split("/")[-1][:60], "url": res["url"], "size": res["size"], "time": time.time()}
            save_idx(cur, idx)
            return self._json(201, res)
        if u.path == "/api/parse":
            src = d.get("url", "")
            if not src.startswith(("http://", "https://")): return self._json(400, {"error": "bad url"})
            assets, err = parse_assets(src)
            if assets is None: return self._json(502, {"error": err})
            return self._json(200, {"page": src, "count": len(assets), "assets": assets})
        return self._json(404, {"error": "not found"})

if __name__ == "__main__":
    print(f"[*] UGIRL 免费CDN 本地版启动: http://127.0.0.1:{PORT}")
    print(f"[*] 账号数据: {ACC_FILE}")
    threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()