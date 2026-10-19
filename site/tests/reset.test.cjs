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

test('reset link opens separate form and keeps existing sign-in controls',async()=>{
 const a=boot('#reset=synthetic-token');await settle();
 assert.equal(a.el('auth-form').classList.contains('hidden'),true);
 assert.equal(a.el('reset-form').classList.contains('hidden'),false);
 assert.equal(a.run('resetToken'),'synthetic-token');
 assert.equal(a.el('auth-submit').disabled,false);
});
test('return from reset clears token and restores sign-in form',async()=>{
 const a=boot('#reset=synthetic-token');a.el('reset-form').reset=()=>{};await settle();
 a.el('reset-back').click();
 assert.equal(a.run('resetToken'),'');
 assert.equal(a.el('reset-form').classList.contains('hidden'),true);
 assert.equal(a.el('auth-form').classList.contains('hidden'),false);
});

test('successful reset submits token, clears password and retains success message',async()=>{
 const a=boot('#reset=synthetic-token');await settle();let cleared=false;
 a.ctx.FormData=class {constructor(){return [['password','Synthetic-reset-pass-429!']];}};
 a.state.respond=path=>({ok:true,status:200,json:async()=>path==='csrf'?{csrfToken:'fresh'}:{message:'Password updated. Sign in again.'}});
 await a.el('reset-form').listeners.submit({preventDefault(){},target:{reset(){cleared=true;}}});
 assert.equal(cleared,true);assert.equal(a.run('resetToken'),'');
 assert.equal(a.el('reset-form').classList.contains('hidden'),true);
 assert.equal(a.el('auth-form').classList.contains('hidden'),false);
 assert.equal(a.el('notice').textContent,'Password updated. Sign in again.');
});
test('reset API errors keep the form and token for retry',async()=>{
 const a=boot('#reset=synthetic-token');await settle();
 a.ctx.FormData=class {constructor(){return [['password','Synthetic-reset-pass-429!']];}};
 a.state.respond=()=>({ok:false,status:400,json:async()=>({error:'Invalid or used reset link'})});
 await a.el('reset-form').listeners.submit({preventDefault(){},target:{reset(){throw Error('must not clear');}}});
 assert.equal(a.run('resetToken'),'synthetic-token');
 assert.equal(a.el('reset-form').classList.contains('hidden'),false);
 assert.equal(a.el('notice').textContent,'Invalid or used reset link');
});
