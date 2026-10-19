const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('site/dist/app.js','utf8');
function boot(hash='',fail=false){
 const elements=new Map();
 function el(id){if(elements.has(id))return elements.get(id);const classes=new Set(['dashboard','signed-in-bar','retry-connection','back-to-login'].includes(id)?['hidden']:[]);
 const listeners={}; const e={textContent:'',disabled:false,classList:{add:x=>classes.add(x),remove:x=>classes.delete(x),contains:x=>classes.has(x),toggle(x,v){v??=!classes.has(x);v?classes.add(x):classes.delete(x);}},listeners,addEventListener(name,fn){listeners[name]=fn;},click(){listeners.click?.({preventDefault(){}});},remove(){elements.delete(id);},replaceChildren(){},scrollIntoView(){},append(){},elements:{password:{},email:{value:''}}};elements.set(id,e);return e;}
 el('google-signin').parentElement=el('google-shell');
 const state={fail,authenticated:false,expiredDetails:false};
 const ctx={document:{getElementById:el,body:el('body'),head:el('head'),hidden:false,addEventListener(){},querySelector(){return null;},createElement(){return el('new');}},location:{hash,pathname:'/',search:'',origin:'https://example.invalid'},history:{replaceState(){}},window:{addEventListener(){},scrollTo(){}},console,URL,Blob,Date,FormData,
 fetch:async url=>{if(state.fail)throw Error('offline');const path=url.slice(5);if(state.respond)return state.respond(path);const unauthorized=(path==='me'&&!state.authenticated)||(state.expiredDetails&&path==='tickets');return {ok:!unauthorized,status:unauthorized?401:200,json:async()=>unauthorized?{error:'Sign in first'}:path==='bootstrap'?{intake_enabled:false,registration_enabled:false,csrfToken:'token',account:state.authenticated?{email:'synthetic@example.invalid'}:null}:path==='csrf'?{csrfToken:'token'}:path==='me'?{email:'synthetic@example.invalid'}:{}};}};
 vm.createContext(ctx);vm.runInContext(source,ctx);
 return {ctx,el,state,run:s=>vm.runInContext(s,ctx)};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));

function reply(data,status=200){return {ok:status===200,status,json:async()=>data};}
function deferred(){let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};}
test('startup waits for saved identity before enabling another sign-in',async()=>{
 const a=boot('#signin');await settle();const pending=deferred();let scripts=0;
 a.ctx.document.head.append=()=>scripts++;
 a.state.respond=path=>path==='bootstrap'?pending.promise:reply(path==='bootstrap'?{intake_enabled:false,registration_enabled:false,csrfToken:'token',account:state.authenticated?{email:'synthetic@example.invalid'}:null}:{});
 const init=a.run('init()');await settle();
 assert.equal(a.el('auth-submit').disabled,true);assert.equal(a.el('forgot').disabled,true);
 assert.equal(a.el('google-shell').classList.contains('hidden'),true);assert.equal(scripts,0);
 pending.resolve(reply({account:{email:'synthetic@example.invalid'}}));await init;
 assert.equal(a.el('dashboard').classList.contains('hidden'),false);
 assert.equal(a.el('notice').textContent,'Your saved account is signed in.');
});
test('startup session network error keeps sign-in paused and offers retry',async()=>{
 const a=boot('#signin');await settle();
 a.state.respond=path=>path==='bootstrap'?Promise.reject(Error('offline')):reply({});
 await a.run('init()');assert.equal(a.el('auth-submit').disabled,true);
 assert.equal(a.el('retry-connection').classList.contains('hidden'),false);
 assert.equal(a.el('google-shell').classList.contains('hidden'),true);
 assert.match(a.el('notice').textContent,/could not connect/);
 a.state.respond=path=>reply(path==='me'?{error:'Sign in first'}:{},path==='me'?401:200);
 await a.run('init()');assert.equal(a.el('auth-submit').disabled,false);
 assert.equal(a.el('google-shell').classList.contains('hidden'),false);
 assert.equal(a.el('notice').textContent,'Ready to sign in.');
});
test('startup closed registration remains disabled and explained',async()=>{
 const a=boot('#signup');await settle();assert.equal(a.el('auth-submit').disabled,true);
 assert.match(a.el('notice').textContent,/Email registration is closed/);
});

test('startup keeps partial account loading warnings visible',async()=>{
 const a=boot();await settle();
 a.state.respond=path=>path==='tickets'?Promise.reject(Error('offline')):reply(path==='bootstrap'?{account:{email:'synthetic@example.invalid'}}:path==='me'?{email:'synthetic@example.invalid'}:{});
 await a.run('init()');assert.match(a.el('notice').textContent,/some account details could not load/);
 assert.equal(a.el('dashboard').classList.contains('hidden'),false);
});
test('reset startup preserves return-to-sign-in controls',async()=>{
 const a=boot('#reset=synthetic-token');await settle();
 assert.equal(a.run('resetToken'),'synthetic-token');assert.equal(a.el('forgot').disabled,false);
 assert.equal(a.el('google-shell').classList.contains('hidden'),false);
 assert.match(a.el('notice').textContent,/Choose a new password/);
});

test('parallel startup retry cannot duplicate identity requests',async()=>{
 const a=boot();await settle();const pending=deferred();let count=0;
 a.state.respond=path=>{count++;return path==='bootstrap'?pending.promise:reply({error:'Sign in first'},401);};
 const first=a.run('init()');await a.run('init()');assert.equal(count,1);
 pending.resolve(reply({intake_enabled:false}));await first;
});
test('interrupted writes never claim nothing was submitted',async()=>{
 const a=boot();await settle();a.state.respond=()=>Promise.reject(Error('connection reset'));
 await assert.rejects(a.run("api('login',{})"),/may have reached KiwiKind/);
});
test('duplicate password submits only send one login request',async()=>{
 const a=boot('#signin');await settle();const pending=deferred();let logins=0;
 a.ctx.FormData=class {constructor(){return [['email','synthetic@example.invalid'],['password','synthetic-only']];}};
 a.state.respond=path=>path==='login'?(logins++,pending.promise):reply(path==='bootstrap'?{account:{email:'synthetic@example.invalid'}}:path==='me'?{email:'synthetic@example.invalid'}:{});
 const submit=a.el('auth-form').listeners.submit;const event={preventDefault(){},target:{}};
 const first=submit(event);await submit(event);assert.equal(logins,1);assert.equal(a.el('auth-submit').disabled,true);
 pending.resolve(reply({csrfToken:'synthetic'}));await first;assert.equal(a.el('auth-submit').disabled,false);
});

test('account navigation explains closed registration and clears stale notice on return',async()=>{
 const a=boot('#signin');await settle();a.run('selectAccountForm(true)');
 assert.match(a.el('notice').textContent,/Email registration is closed/);
 assert.equal(a.el('auth-submit').disabled,true);
 a.run('selectAccountForm(false)');assert.equal(a.el('notice').textContent,'Ready to sign in.');
});

test('account-only launch enables signup while order submission stays disabled',async()=>{
 const a=boot('#signup');await settle();const paths=[];
 a.state.respond=path=>{paths.push(path);return reply({registration_enabled:true,intake_enabled:false,csrfToken:'fresh',account:null});};
 await a.run('init()');
 assert.equal(a.el('auth-submit').disabled,false);
 assert.equal(a.run('registrationEnabled'),true);
 assert.equal(a.run('intake'),false);
 assert.deepEqual(paths,['bootstrap']);
 assert.equal(a.run('csrfToken'),'fresh');
});

test('saved-account startup does not repeat identity or csrf requests',async()=>{
 const a=boot();await settle();const paths=[];
 a.state.respond=path=>{paths.push(path);return reply(path==='bootstrap'?{account:{email:'synthetic@example.invalid'},registration_enabled:true,intake_enabled:false,csrfToken:'fresh'}:{});};
 await a.run('init()');
 assert.deepEqual(paths,['bootstrap','orders','tickets','invoices']);
 assert.equal(a.el('order-submit').disabled,true);
 assert.equal(a.el('signed-in-email').textContent,'synthetic@example.invalid');
});

test('retry after server session expiry clears stale private account view',async()=>{
 const a=boot();await settle();a.state.authenticated=true;await a.run('refresh()');
 a.state.authenticated=false;await a.run('init()');
 assert.equal(a.el('dashboard').classList.contains('hidden'),true);
 assert.equal(a.el('account-email').textContent,'');
});
