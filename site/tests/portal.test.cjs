const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('site/dist/app.js','utf8');
function boot(hash='',fail=false){
 const elements=new Map();
 function el(id){if(elements.has(id))return elements.get(id);const classes=new Set(['dashboard','signed-in-bar','retry-connection','back-to-login'].includes(id)?['hidden']:[]);
 const listeners={}; const e={textContent:'',disabled:false,classList:{add:x=>classes.add(x),remove:x=>classes.delete(x),contains:x=>classes.has(x),toggle(x,v){v??=!classes.has(x);v?classes.add(x):classes.delete(x);}},addEventListener(name,fn){listeners[name]=fn;},click(){listeners.click?.({preventDefault(){}});},replaceChildren(){},scrollIntoView(){},append(){},elements:{password:{},email:{value:''}}};elements.set(id,e);return e;}
 el('google-signin').parentElement=el('google-shell');
 const state={fail,authenticated:false,expiredDetails:false};
 const ctx={document:{getElementById:el,body:el('body'),head:el('head'),hidden:false,addEventListener(){},querySelector(){return null;},createElement(){return el('new');}},location:{hash,pathname:'/',search:'',origin:'https://example.invalid'},history:{replaceState(){}},window:{addEventListener(){},scrollTo(){}},console,URL,Blob,Date,FormData,
 fetch:async url=>{if(state.fail)throw Error('offline');const path=url.slice(5);if(state.respond)return state.respond(path);const unauthorized=(path==='me'&&!state.authenticated)||(state.expiredDetails&&path==='tickets');return {ok:!unauthorized,status:unauthorized?401:200,json:async()=>unauthorized?{error:'Sign in first'}:path==='status'?{intake_enabled:false}:path==='csrf'?{csrfToken:'token'}:path==='me'?{email:'synthetic@example.invalid'}:{}};}};
 vm.createContext(ctx);vm.runInContext(source,ctx);
 return {ctx,el,state,run:s=>vm.runInContext(s,ctx)};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
test('closed intake keeps signup disabled after async initialization',async()=>{const a=boot('#signup');await settle();assert.equal(a.el('auth-submit').disabled,true);});
test('expired session clears identity and account details',async()=>{const a=boot();await settle();a.el('signed-in-email').textContent='old@example.invalid';a.el('dashboard').classList.remove('hidden');await assert.rejects(a.run("api('me')"));assert.equal(a.el('signed-in-email').textContent,'');assert.equal(a.el('dashboard').classList.contains('hidden'),true);assert.equal(a.ctx.location.hash,'#signin');});
test('failed startup offers retry and successful retry restores login controls',async()=>{const a=boot('#signin',true);await settle();assert.equal(a.el('retry-connection').classList.contains('hidden'),false);assert.equal(a.el('auth-submit').disabled,true);a.state.fail=false;await a.run('init()');assert.equal(a.el('retry-connection').classList.contains('hidden'),true);assert.equal(a.el('auth-submit').disabled,false);});
test('anonymous portal route opens account form',async()=>{const a=boot('#portal');await settle();assert.equal(a.ctx.location.hash,'#signin');});
test('feedback is outside sections hidden by account routes',()=>{const html=fs.readFileSync('site/dist/index.html','utf8');assert.ok(html.indexOf('id="notice"')<html.indexOf('<section class="top-account"'));assert.equal((html.match(/id="notice"/g)||[]).length,1);});

test('detail request expiry cannot repopulate private dashboard after successful identity check',async()=>{
 const a=boot();await settle();a.state.authenticated=true;a.state.expiredDetails=true;
 await assert.rejects(a.run('refresh()'),/Please sign in again/);
 assert.equal(a.el('dashboard').classList.contains('hidden'),true);
 assert.equal(a.el('signed-in-email').textContent,'');
 assert.equal(a.el('account-email').textContent,'');
 assert.equal(a.ctx.location.hash,'#signin');
});

test('Google button fits a narrow viewport even when account form starts hidden',async()=>{
 const a=boot();await settle();const widths=[];let onResize;
 a.ctx.document.documentElement={clientWidth:322};
 a.ctx.window.addEventListener=(event,callback)=>{if(event==='resize')onResize=callback;};
 const google={accounts:{id:{initialize(){},renderButton(host,options){widths.push(options.width);}}}};
 a.ctx.google=google;a.ctx.window.google=google;
 a.el('new').onload();
 assert.equal(widths[0],238);
 a.ctx.document.documentElement.clientWidth=640;onResize();assert.equal(widths[1],280);
 a.ctx.document.documentElement.clientWidth=320;onResize();assert.equal(widths[2],236);
});

function deferred(){let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};}
function reply(data,status=200){return {ok:status===200,status,json:async()=>data};}
test('identity response arriving after sign-out cannot reopen dashboard',async()=>{
 const a=boot();await settle();const pending=deferred();
 a.state.respond=()=>pending.promise;
 const refresh=a.run('refresh()');a.run('showSignedOut()');
 pending.resolve(reply({email:'old@example.invalid'}));await refresh;
 assert.equal(a.el('dashboard').classList.contains('hidden'),true);
 assert.equal(a.el('account-email').textContent,'');
});
test('older refresh cannot replace a newer signed-in identity',async()=>{
 const a=boot();await settle();const pending=deferred();let identities=0;
 a.state.respond=path=>path==='me'?(++identities===1?pending.promise:reply({email:'new@example.invalid'})):reply({});
 const old=a.run('refresh()');await a.run('refresh()');
 pending.resolve(reply({email:'old@example.invalid'}));await old;
 assert.equal(a.el('account-email').textContent,'new@example.invalid');
 assert.equal(a.el('dashboard').classList.contains('hidden'),false);
});
test('stale unauthorized response cannot sign out a newer account',async()=>{
 const a=boot();await settle();const pending=deferred();
 a.state.respond=()=>pending.promise;const old=a.run("api('orders')");
 a.state.respond=path=>reply(path==='me'?{email:'new@example.invalid'}:{});
 await a.run('refresh()');pending.resolve(reply({error:'Sign in first'},401));
 await assert.rejects(old);assert.equal(a.el('account-email').textContent,'new@example.invalid');
 assert.equal(a.el('dashboard').classList.contains('hidden'),false);
});
test('detail response arriving after sign-out cannot restore private records',async()=>{
 const a=boot();await settle();const pending=deferred();
 a.state.respond=path=>path==='me'?reply({email:'old@example.invalid'}):pending.promise;
 const refresh=a.run('refresh()');await settle();a.run('showSignedOut()');
 pending.resolve(reply({orders:[{address:'Private old address',created_at:'2026-10-16'}]}));await refresh;
 assert.equal(a.el('dashboard').classList.contains('hidden'),true);
 assert.equal(a.el('account-email').textContent,'');
});
