'use strict';
const $ = id => document.getElementById(id);
const consentVersion = 'prelaunch-2026-10-16';
let csrfToken = '', registration = false, backend = false, intake = false;
let orderKey = null;
let lastAccountSync = 0;
let accountSyncInFlight = false;
function notice(message, error = false) { $('notice').textContent = message; $('notice').classList.toggle('error', error); }
async function api(path, data) {
  const response = await fetch('/api/' + path, {method: data === undefined ? 'GET' : 'POST', credentials: 'same-origin', headers: {'Content-Type':'application/json', 'X-CSRFToken':csrfToken}, ...(data === undefined ? {} : {body:JSON.stringify(data)})});
  let result; try { result = await response.json(); } catch { throw new Error('The customer backend is unavailable. Nothing has been submitted.'); }
  if (!response.ok) {
    if (response.status === 401 && path !== 'login' && path !== 'google-login' && !$('dashboard').classList.contains('hidden')) showSignedOut();
    const error = new Error(result.error || 'The request could not be completed.');
    error.status = response.status;
    throw error;
  }
  if (result.csrfToken) csrfToken = result.csrfToken;
  return result;
}
function showSignedOut() {
  updateAccountNavigation(false);
  $('dashboard').classList.add('hidden');
  $('auth-area').classList.remove('hidden');
  $('signed-in-bar').classList.add('hidden');
  $('signed-in-email').textContent='';
  $('account-email').textContent='';
  for (const id of ['orders','tickets','invoices']) $(id).replaceChildren();
  location.hash='#signin';
}
function formData(form) { return Object.fromEntries(new FormData(form)); }
function safeAction(fn) { return async event => { event?.preventDefault(); try { await fn(event); } catch (error) { notice(error.message, true); } }; }
function node(tag, value) { const el = document.createElement(tag); el.textContent = value; return el; }
function empty(id, message) { $(id).replaceChildren(node('p',message)); }
function record(parent, title, subtitle) { const el=node('div',''); el.className='record'; el.append(node('strong',title),node('small',subtitle)); parent.append(el); return el; }
function button(label, action) { const b=node('button',label); b.className='textbutton'; b.type='button'; b.addEventListener('click',safeAction(action)); return b; }
function date(value) { return new Date(value).toLocaleDateString('en-NZ'); }
async function refresh() {
  const me=await api('me');
  lastAccountSync = Date.now();
  updateAccountNavigation(true); document.body.classList.remove('account-open','signup-view'); if(location.hash==='#signin'||location.hash==='#signup'){history.replaceState(null,'',location.pathname+location.search);} $('auth-area').classList.add('hidden'); $('dashboard').classList.remove('hidden'); $('account-email').textContent=me.email; $('signed-in-email').textContent=me.email; $('signed-in-bar').classList.remove('hidden');
  const results=await Promise.allSettled([api('orders'),api('tickets'),api('invoices')]);
  const [orders,tickets,invoices]=results.map(r=>r.status==='fulfilled'?r.value:null);
  if(results.some(r=>r.status==='rejected')) notice('You are still signed in, but some account details could not load. Use Refresh account to retry.',true);
  empty('orders',orders?'No requests yet.':'Requests temporarily unavailable.'); if(orders?.orders?.length) $('orders').replaceChildren();
  for(const order of orders?.orders || []) {
    const el=record($('orders'),order.address, `${order.status} · ${date(order.created_at)} · ${order.id}`);
    if(order.status!=='cancelled') el.append(button('Cancel request',async()=>{await api(`orders/${order.id}/cancel`,{}); await refresh(); notice('Request cancelled.');}));
  }
  empty('tickets',tickets?'No conversations yet.':'Conversations temporarily unavailable.'); if(tickets?.tickets?.length) $('tickets').replaceChildren();
  for(const ticket of tickets?.tickets || []) {
    const el=record($('tickets'),ticket.subject,`${ticket.category} · ${ticket.status}`);
    el.append(button('Read & reply',async()=>{
      const data=await api(`tickets/${ticket.id}/messages`);
      const conversation=node('div','');
      for(const m of data.messages) conversation.append(node('small',`${m.from_support?'Support':'You'} · ${date(m.created_at)}`),node('p',m.body));
      const form=node('form',''), label=node('label','Your reply'), input=document.createElement('textarea'); input.required=true; input.maxLength=4000; label.append(input);form.append(label);
      const submit=node('button','Send reply');submit.className='button';submit.type='submit';form.append(submit);
      form.addEventListener('submit',safeAction(async()=>{await api(`tickets/${ticket.id}/messages`,{body:input.value});await refresh();notice('Reply recorded.');}));
      conversation.append(form);el.replaceChildren(node('strong',ticket.subject),conversation);
    }));
  }
  empty('invoices',invoices?'No invoices.':'Billing information temporarily unavailable.');
  for(const i of invoices?.invoices || []) record($('invoices'),new Intl.NumberFormat('en-NZ',{style:'currency',currency:i.currency}).format(i.amount_cents/100),`${i.status} · Due ${i.due_date}`);
  $('order-submit').disabled=!intake;
  $('refresh-account')?.classList.remove('hidden');
}
$('toggle-auth').addEventListener('click',()=>{registration=!registration;$('auth-title').textContent=registration?'Create your account':'Welcome back';$('auth-submit').textContent=registration?'Create account ↗':'Sign in ↗';$('register-consent').classList.toggle('hidden',!registration);$('auth-form').elements.password.autocomplete=registration?'new-password':'current-password';$('auth-submit').disabled=!backend || (registration&&!intake);});
$('auth-form').addEventListener('submit',safeAction(async e=>{const d=formData(e.target);if(registration){if(!d.consent)throw new Error('Please accept the pre-launch terms.');const r=await api('register',{...d,consent_version:consentVersion});notice(r.message);location.hash='#signin';}else{await api('login',d);await refresh();notice('You’re signed in.');}}));
$('forgot').addEventListener('click',safeAction(async()=>{if(!backend)throw new Error('Password reset is available when the customer backend is connected.');const email=$('auth-form').elements.email.value;if(!email)throw new Error('Enter your email above first.');notice((await api('password-reset',{email})).message);}));
$('logout').addEventListener('click',safeAction(async()=>{await api('logout',{});updateAccountNavigation(false);$('dashboard').classList.add('hidden');$('auth-area').classList.remove('hidden');$('signed-in-bar').classList.add('hidden');$('signed-in-email').textContent='';for(const id of ['orders','tickets','invoices'])$(id).replaceChildren();$('auth-form').reset();notice('Signed out.');csrfToken=(await api('csrf')).csrfToken;}));
$('order-form').addEventListener('submit',safeAction(async e=>{const d=formData(e.target);orderKey ||= crypto.randomUUID();const r=await api('orders',{...d,idempotency_key:orderKey,consent_version:consentVersion});orderKey=null;e.target.reset();await refresh();notice(r.message);}));
$('order-form').addEventListener('input',()=>{orderKey=null;});
$('ticket-form').addEventListener('submit',safeAction(async e=>{const r=await api('tickets',formData(e.target));e.target.reset();await refresh();notice(r.message);}));
$('deletion-form').addEventListener('submit',safeAction(async e=>{notice((await api('privacy/deletion',formData(e.target))).message);e.target.reset();}));
$('refresh-account')?.addEventListener('click',safeAction(async()=>{await refresh();notice('Account details refreshed.');}));
$('top-logout').addEventListener('click',()=> $('logout').click());
$('top-refresh').addEventListener('click',()=> $('refresh-account').click());
$('export').addEventListener('click',safeAction(async()=>{const data=await api('privacy/export');const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='kiwikind-data.json';a.click();URL.revokeObjectURL(url);notice('Your data export is ready.');}));
async function init(){
  try{
    const s=await api('status');backend=true;intake=s.intake_enabled;
    $('connection-status').textContent=intake?'Pre-launch portal connected · no active broadband sales':'Portal connected · customer intake is closed';
    if(s.legal_entity && s.business_contact && s.privacy_contact)$('legal-identity').textContent=`Operator: ${s.legal_entity}. Business contact: ${s.business_contact}. Privacy contact: ${s.privacy_contact}. Pre-launch only.`;
    await api('csrf');$('auth-submit').disabled=registration&&!intake;
    $('toggle-auth').disabled=false;$('forgot').disabled=false;
    $('retry-connection').classList.add('hidden');
    setupGoogleSignIn();
    const hash=location.hash;
    if(hash.startsWith('#verify=')){const token=decodeURIComponent(hash.slice(8));history.replaceState(null,'','#portal');notice((await api('verify',{token})).message);}
    if(hash.startsWith('#reset=')){
      const token=decodeURIComponent(hash.slice(7));history.replaceState(null,'','#portal');
      const form=$('auth-form');form.replaceChildren(node('h3','Set a new password'));
      const label=node('label','New password (at least 12 characters)'),input=document.createElement('input');input.type='password';input.autocomplete='new-password';input.required=true;input.minLength=12;input.maxLength=128;label.append(input);form.append(label);
      const submit=node('button','Update password');submit.type='submit';submit.className='button';form.append(submit);
      const copy=form.cloneNode(true);form.replaceWith(copy);
      copy.addEventListener('submit',safeAction(async()=>{notice((await api('password-reset/confirm',{token,password:copy.querySelector('input').value})).message);location.reload();}));return;
    }
    try{await refresh();if(location.hash==='#portal'){history.replaceState(null,'',location.pathname+location.search);} if(!location.hash){window.scrollTo(0,0);}}catch{/* Anonymous visitors see sign-in. */updateAccountNavigation(false);$('dashboard').classList.add('hidden');$('auth-area').classList.remove('hidden');$('signed-in-bar').classList.add('hidden');}
  }catch{ backend=false;$('retry-connection').classList.remove('hidden'); notice('KiwiKind could not connect. The server may be waking up. Retry the connection shortly.',true);$('connection-status').textContent='Customer backend temporarily unavailable';$('auth-submit').disabled=true;$('toggle-auth').disabled=true;$('forgot').disabled=true; }
}
$('retry-connection').addEventListener('click',safeAction(init));
init();

function setupGoogleSignIn(){
  if(document.querySelector('script[src="https://accounts.google.com/gsi/client"]'))return;
  const clientId='956119315558-mgaqlpnfr9r0ic9n4jtb284gaa4n7i61.apps.googleusercontent.com';
  const script=document.createElement('script');
  script.src='https://accounts.google.com/gsi/client';script.async=true;
  script.onload=()=>{
    if(!window.google?.accounts?.id)return;
    google.accounts.id.initialize({client_id:clientId,ux_mode:'redirect',login_uri:location.origin+'/api/google-callback'});
    google.accounts.id.renderButton($('google-signin'),{theme:'filled_black',shape:'pill',size:'large',text:'signin_with',logo_alignment:'left',width:280});
  };
  script.onerror=()=>notice('Google sign-in is unavailable. You can still use email sign-in.',true);
  document.head.append(script);
}

// Top navigation switches directly to the requested account form.
function updateAccountNavigation(signedIn){$('nav-signin').classList.toggle('hidden',signedIn);$('nav-signup').classList.toggle('hidden',signedIn);$('nav-account').classList.toggle('hidden',!signedIn);}
function selectAccountForm(signUp){
  if(registration!==signUp)$('toggle-auth').click();
  document.body.classList.toggle('signup-view',signUp);
  $('back-to-login').classList.toggle('hidden',!signUp);
}
function routeAccount(){
  const hash=location.hash;
  if(hash==='#portal' && $('dashboard').classList.contains('hidden')){location.hash='#signin';return;}
  if(!$('dashboard').classList.contains('hidden') && (hash==='#signin'||hash==='#signup')){
    history.replaceState(null,'',location.pathname+location.search);
    document.body.classList.remove('account-open','signup-view');
    window.scrollTo(0,0);
    return;
  }
  document.body.classList.toggle('account-open',hash==='#signup'||hash==='#signin');
  if(hash==='#signup'||hash==='#signin'){
    selectAccountForm(hash==='#signup');
    $('auth-area').scrollIntoView({block:'start'});
  }else if(!registration){document.body.classList.remove('signup-view');$('back-to-login').classList.add('hidden');}
}
window.addEventListener('hashchange',routeAccount);
routeAccount();

// Refresh shared account data after returning from Android, another tab, or a network interruption.
// Keep the existing dashboard visible if a temporary request fails.
async function syncAccountOnReturn() {
  if (document.hidden || !backend || accountSyncInFlight || $('dashboard').classList.contains('hidden')) return;
  if (Date.now() - lastAccountSync < 15000) return;
  accountSyncInFlight = true;
  try { await refresh(); }
  catch (error) { notice('Account refresh is temporarily unavailable. Your existing account view is preserved.', true); }
  finally { accountSyncInFlight = false; }
}
document.addEventListener('visibilitychange', () => { if (!document.hidden) void syncAccountOnReturn(); });
window.addEventListener('focus', () => { void syncAccountOnReturn(); });
window.addEventListener('online', () => { void syncAccountOnReturn(); });
