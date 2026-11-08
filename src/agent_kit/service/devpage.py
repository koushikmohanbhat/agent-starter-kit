"""A single static page for trying the agent locally (served only with KIT_AUTH=dev). Not a product UI."""

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>agent-starter-kit · dev</title>
<style>
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1b;--mut:#6b6b66;--line:#e4e3de;--acc:#2b59c3;--ok:#1f7a4d;--warn:#9a6700}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;background:var(--bg);color:var(--ink)}
header{padding:14px 20px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:center;flex-wrap:wrap;background:var(--card)}
header b{font-size:16px}header .mut{color:var(--mut);font-size:13px}
main{display:grid;grid-template-columns:minmax(0,2fr) minmax(280px,1fr);gap:16px;padding:16px;max-width:1200px;margin:0 auto}
@media(max-width:820px){main{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
#log{height:56vh;overflow:auto;display:flex;flex-direction:column;gap:8px}
.msg{max-width:85%;padding:8px 12px;border-radius:10px;white-space:pre-wrap}
.user{align-self:flex-end;background:#e8eefb}.assistant{align-self:flex-start;background:#f1f0ec}
.ev{align-self:flex-start;font:12px/1.4 ui-monospace,Menlo,monospace;color:var(--mut)}
form{display:flex;gap:8px;margin-top:10px}input,select,button{font:inherit}
input[type=text]{flex:1;padding:9px 11px;border:1px solid var(--line);border-radius:8px}
button{padding:8px 14px;border:0;border-radius:8px;background:var(--acc);color:#fff;cursor:pointer}
button.ghost{background:transparent;color:var(--acc);border:1px solid var(--line)}button.ok{background:var(--ok)}button.no{background:#a33}
.ap{border-top:1px solid var(--line);padding:10px 0}.ap:first-child{border-top:0}.ap code{font-size:12px}
.hint{color:var(--mut);font-size:13px;margin:6px 0 0}.chips{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.chips button{background:#eef1f8;color:var(--ink);font-size:13px;padding:5px 9px}
</style></head><body>
<header><b>agent-starter-kit</b><span class="mut" id="meta">loading…</span>
<label class="mut">Customer <select id="who"><option>cust-001</option><option>cust-002</option></select></label>
<button class="ghost" onclick="newSession()">New conversation</button></header>
<main>
<section class="card"><div id="log"></div>
<form onsubmit="send(event)"><input id="msg" type="text" placeholder="Ask about an order, e.g. Where is ORD-10003?" autocomplete="off"><button>Send</button></form>
<div class="chips" id="chips"></div>
<p class="hint">Dev mode: identity comes from the selector, not a login. Tool calls and approvals are shown as they happen.</p></section>
<aside class="card"><b>Approvals</b> <span class="mut">(acting as support lead)</span><div id="aps"><p class="hint">None pending.</p></div>
<button class="ghost" style="margin-top:8px" onclick="loadAps()">Refresh</button></aside>
</main>
<script>
let sid=null;const log=document.getElementById('log');
const examples=["Where is my order ORD-10003?","I want a refund for ORD-10001, it arrived damaged","Please refund my headphones, order ORD-10004",
"Change the delivery address for ORD-10002 to 12 MG Road, Bengaluru 560001","I want to speak to a human"];
for(const e of examples){const b=document.createElement('button');b.type='button';b.textContent=e;b.onclick=()=>{document.getElementById('msg').value=e};document.getElementById('chips').append(b)}
function hdr(lead){return {'Content-Type':'application/json','X-User-Id':lead?'lead-1':document.getElementById('who').value,'X-User-Roles':lead?'support_lead':''}}
function add(cls,text){const d=document.createElement('div');d.className=cls;d.textContent=text;log.append(d);log.scrollTop=log.scrollHeight;return d}
function newSession(){sid=null;log.innerHTML=''}
document.getElementById('who').onchange=newSession;
async function send(ev){ev.preventDefault();const i=document.getElementById('msg');const m=i.value.trim();if(!m)return;i.value='';add('msg user',m);
 const r=await fetch('/v1/chat',{method:'POST',headers:hdr(),body:JSON.stringify({message:m,session_id:sid,stream:true})});
 const rd=r.body.getReader();const dec=new TextDecoder();let buf='';
 while(true){const {value,done}=await rd.read();if(done)break;buf+=dec.decode(value,{stream:true});let k;
  while((k=buf.indexOf('\\n\\n'))>=0){const chunk=buf.slice(0,k);buf=buf.slice(k+2);const line=chunk.split('\\n').find(l=>l.startsWith('data: '));if(!line)continue;
   const e=JSON.parse(line.slice(6));
   if(e.type==='tool_call')add('ev','→ '+e.name+' '+JSON.stringify(e.args));
   else if(e.type==='tool_result')add('ev','← '+e.name+' '+JSON.stringify(e.result));
   else if(e.type==='approval_required'){add('ev','⏸ approval required: '+e.approval.reason);loadAps()}
   else if(e.type==='final'){sid=e.session_id;add('msg assistant',e.message)}
   else if(e.type==='error')add('ev','error: '+e.message)}}}
async function loadAps(){const r=await fetch('/v1/approvals',{headers:hdr(true)});const j=await r.json();const el=document.getElementById('aps');el.innerHTML='';
 if(!j.approvals||!j.approvals.length){el.innerHTML='<p class="hint">None pending.</p>';return}
 for(const a of j.approvals){const d=document.createElement('div');d.className='ap';
  d.innerHTML='<div><b>'+a.tool+'</b> for '+a.user.id+'</div><code></code><div style="margin-top:6px;display:flex;gap:6px"></div>';
  d.querySelector('code').textContent=JSON.stringify(a.args);
  for(const [lbl,ok,cls] of [['Approve',true,'ok'],['Reject',false,'no']]){const b=document.createElement('button');b.textContent=lbl;b.className=cls;
   b.onclick=async()=>{const r=await fetch('/v1/approvals/'+a.id,{method:'POST',headers:hdr(true),body:JSON.stringify({approve:ok,reason:ok?'':'Outside policy'})});
    const j=await r.json();if(j.message&&a.session_id===sid)add('msg assistant',j.message);loadAps()};d.querySelector('div:last-child').append(b)}
  el.append(d)}}
fetch('/v1/agent',{headers:hdr()}).then(r=>r.json()).then(j=>{document.getElementById('meta').textContent=j.name+' · '+j.framework+' · '+j.model.provider+' '+(j.model.name||'')+' · prompt '+j.prompt.id+'@'+j.prompt.version});
loadAps();
</script></body></html>"""
