const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('site/dist/app.js','utf8');
function boot(hash='',fail=false){
 const elements=new Map();
 function el(id){if(elements.has(id))return elements.get(id);const classes=new Set(['dashboard','signed-in-bar','retry-connection','back-to-login'].includes(id)?['hidden']:[]);
 const listeners={}; const e={textContent:'',disabled:false,classList:{add:x=>classes.add(x),remove:x=>classes.delete(x),contains:x=>classes.has(x),toggle(x,v){v??=!classes.has(x);v?classes.add(x):classes.delete(x);}},addEventListener(name,fn){listeners[name]=fn;},click(){listeners.click?.({preventDefault(){}});},replaceChildren(){},scrollIntoView(){},append(){},elements:{password:{},email:{value:''}}};elements.set(id,e);return e;}
 const state={fail};
 const ctx={document:{getElementById:el,body:el('body'),head:el('head'),hidden:false,addEventListener(){},querySelector(){return null;},createElement(){return el('new');}},location:{hash,pathname:'/',search:'',origin:'https://example.invalid'},history:{replaceState(){}},window:{addEventListener(){},scrollTo(){}},console,URL,Blob,Date,FormData,
 fetch:async url=>{if(state.fail)throw Error('offline');const path=url.slice(5);const unauthorized=path==='me';return {ok:!unauthorized,status:unauthorized?401:200,json:async()=>unauthorized?{error:'Sign in first'}:path==='status'?{intake_enabled:false}:path==='csrf'?{csrfToken:'token'}:{}};}};
 vm.createContext(ctx);vm.runInContext(source,ctx);
 return {ctx,el,state,run:s=>vm.runInContext(s,ctx)};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
test('closed intake keeps signup disabled after async initialization',async()=>{const a=boot('#signup');await settle();assert.equal(a.el('auth-submit').disabled,true);});
test('expired session clears identity and account details',async()=>{const a=boot();await settle();a.el('signed-in-email').textContent='old@example.invalid';a.el('dashboard').classList.remove('hidden');await assert.rejects(a.run("api('me')"));assert.equal(a.el('signed-in-email').textContent,'');assert.equal(a.el('dashboard').classList.contains('hidden'),true);assert.equal(a.ctx.location.hash,'#signin');});
test('failed startup offers retry and successful retry restores login controls',async()=>{const a=boot('#signin',true);await settle();assert.equal(a.el('retry-connection').classList.contains('hidden'),false);assert.equal(a.el('auth-submit').disabled,true);a.state.fail=false;await a.run('init()');assert.equal(a.el('retry-connection').classList.contains('hidden'),true);assert.equal(a.el('auth-submit').disabled,false);});
test('anonymous portal route opens account form',async()=>{const a=boot('#portal');await settle();assert.equal(a.ctx.location.hash,'#signin');});
test('feedback is outside sections hidden by account routes',()=>{const html=fs.readFileSync('site/dist/index.html','utf8');assert.ok(html.indexOf('id="notice"')<html.indexOf('<section class="top-account"'));assert.equal((html.match(/id="notice"/g)||[]).length,1);});
