'use strict';
const $ = id => document.getElementById(id);
const consentVersion = 'prelaunch-2026-10-16';
let csrfToken = '', registration = false, backend = false, intake = false;
let orderKey = null;
function notice(message, error = false) { $('notice').textContent = message; $('notice').classList.toggle('error', error); }
async function api(path, data) {
  const response = await fetch('/api/' + path, {method: data === undefined ? 'GET' : 'POST', credentials: 'same-origin', headers: {'Content-Type':'application/json', 'X-CSRFToken':csrfToken}, ...(data === undefined ? {} : {body:JSON.stringify(data)})});
  let result; try { result = await response.json(); } catch { throw new Error('The customer backend is unavailable. Nothing has been submitted.'); }
  if (!response.ok) throw new Error(result.error || 'The request could not be completed.');
  if (result.csrfToken) csrfToken = result.csrfToken;
  return result;
}
function formData(form) { return Object.fromEntries(new FormData(form)); }
function safeAction(fn) { return async event => { event?.preventDefault(); try { await fn(event); } catch (error) { notice(error.message, true); } }; }
function node(tag, value) { const el = document.createElement(tag); el.textContent = value; return el; }
function empty(id, message) { $(id).replaceChildren(node('p',message)); }
function record(parent, title, subtitle) { const el=node('div',''); el.className='record'; el.append(node('strong',title),node('small',subtitle)); parent.append(el); return el; }
function button(label, action) { const b=node('button',label); b.className='textbutton'; b.type='button'; b.addEventListener('click',safeAction(action)); return b; }
function date(value) { return new Date(value).toLocaleDateString('en-NZ'); }
async function refresh() {
  const me=await api('me'); $('auth-area').classList.add('hidden'); $('dashboard').classList.remove('hidden'); $('account-email').textContent=me.email;
  const [orders,tickets,invoices]=await Promise.all([api('orders'),api('tickets'),api('invoices')]);
  empty('orders','No requests yet.'); if(orders.orders.length) $('orders').replaceChildren();
  for(const order of orders.orders) {
    const el=record($('orders'),order.address, `${order.status} · ${date(order.created_at)} · ${order.id}`);
    if(order.status!=='cancelled') el.append(button('Cancel request',async()=>{await api(`orders/${order.id}/cancel`,{}); await refresh(); notice('Request cancelled.');}));
  }
  empty('tickets','No conversations yet.'); if(tickets.tickets.length) $('tickets').replaceChildren();
  for(const ticket of tickets.tickets) {
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
  empty('invoices','No invoices.');
  for(const i of invoices.invoices) { const el=record($('invoices'),new Intl.NumberFormat('en-NZ',{style:'currency',currency:i.currency}).format(i.amount_cents/100),`${i.sandbox?'TEST · ':''}${i.status} · Due ${i.due_date} · Refunded NZ$${((i.refunded_cents||0)/100).toFixed(2)}`); if(i.sandbox && i.status==='unpaid' && invoices.stripe_test_checkout_enabled) el.append(button('Test card checkout',async()=>{const result=await api('billing/stripe/test-checkout',{invoice_id:i.id}); if(!result.url.startsWith('https://checkout.stripe.com/')) throw new Error('Invalid checkout URL'); window.location.assign(result.url);})); }
  const billing=await api('billing/agreements');
  for(const a of billing.agreements){
    const el=record($('invoices'),'Synthetic recurring billing',`TEST · NZ$${(a.monthly_cents/100).toFixed(2)}/month · NZ$${(a.setup_cents/100).toFixed(2)} setup · ${a.status}`);
    if(billing.test_enabled && a.synthetic_reviewed && a.status==='pending') el.append(button('Start test subscription',async()=>{
      if(!window.confirm('Start synthetic monthly recurring card billing in Stripe test mode? No real funds or service activation.')) return;
      const result=await api('billing/stripe/test-subscribe',{agreement_id:a.id,accept_test_recurring:true});
      if(!result.url.startsWith('https://checkout.stripe.com/'))throw new Error('Invalid checkout URL');
      window.location.assign(result.url);
    }));
    if(billing.test_enabled && ['active','trialing','past_due'].includes(a.status)) el.append(button('Cancel test renewal',async()=>{
      if(window.confirm('Cancel this synthetic subscription at the end of its current test period?'))notice((await api('billing/stripe/test-cancel',{agreement_id:a.id})).message);
    }));
  }
  $('order-submit').disabled=!intake;
}
$('toggle-auth').addEventListener('click',()=>{registration=!registration;$('auth-title').textContent=registration?'Create your account':'Welcome back';$('auth-submit').textContent=registration?'Create account ↗':'Sign in ↗';$('register-consent').classList.toggle('hidden',!registration);$('auth-form').elements.password.autocomplete=registration?'new-password':'current-password';$('auth-submit').disabled=!backend || (registration&&!intake);});
$('auth-form').addEventListener('submit',safeAction(async e=>{const d=formData(e.target);if(registration){if(!d.consent)throw new Error('Please accept the pre-launch terms.');const r=await api('register',{...d,consent_version:consentVersion});notice(r.message);}else{await api('login',d);await refresh();notice('You’re signed in.');}}));
$('forgot').addEventListener('click',safeAction(async()=>{if(!backend)throw new Error('Password reset is available when the customer backend is connected.');const email=$('auth-form').elements.email.value;if(!email)throw new Error('Enter your email above first.');notice((await api('password-reset',{email})).message);}));
$('logout').addEventListener('click',safeAction(async()=>{await api('logout',{});$('dashboard').classList.add('hidden');$('auth-area').classList.remove('hidden');for(const id of ['orders','tickets','invoices'])$(id).replaceChildren();$('auth-form').reset();notice('Signed out.');csrfToken=(await api('csrf')).csrfToken;}));
$('order-form').addEventListener('submit',safeAction(async e=>{const d=formData(e.target);orderKey ||= crypto.randomUUID();const r=await api('orders',{...d,idempotency_key:orderKey,consent_version:consentVersion});orderKey=null;e.target.reset();await refresh();notice(r.message);}));
$('order-form').addEventListener('input',()=>{orderKey=null;});
$('ticket-form').addEventListener('submit',safeAction(async e=>{const r=await api('tickets',formData(e.target));e.target.reset();await refresh();notice(r.message);}));
$('deletion-form').addEventListener('submit',safeAction(async e=>{notice((await api('privacy/deletion',formData(e.target))).message);e.target.reset();}));
$('export').addEventListener('click',safeAction(async()=>{const data=await api('privacy/export');const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='kiwikind-data.json';a.click();URL.revokeObjectURL(url);notice('Your data export is ready.');}));
async function init(){
  try {
    const catalogue=await api('plans');
    if(catalogue.plans.length) $('public-plans').replaceChildren();
    for(const p of catalogue.plans) record($('public-plans'),p.name,`${p.download_mbps}/${p.upload_mbps} Mbps · NZ$${(p.retail_monthly_cents/100).toFixed(2)}/month · NZ$${(p.retail_setup_cents/100).toFixed(2)} setup incl GST · valid to ${p.valid_until} · availability unverified`);
  } catch { $('public-plans').textContent='Plans are temporarily unavailable. No price or availability is confirmed.'; }
  try{
    const s=await api('status');backend=true;intake=s.intake_enabled;
    $('connection-status').textContent=intake?'Pre-launch portal connected · no active broadband sales':'Portal connected · customer intake is closed';
    if(s.legal_entity && s.business_contact && s.privacy_contact)$('legal-identity').textContent=`Operator: ${s.legal_entity}. Business contact: ${s.business_contact}. Privacy contact: ${s.privacy_contact}. Pre-launch only.`;
    await api('csrf');$('auth-submit').disabled=false;
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
    try{await refresh();}catch{/* Anonymous visitors see sign-in. */}
  }catch{ $('connection-status').textContent='Design preview · customer backend is not connected';$('auth-submit').disabled=true;$('toggle-auth').disabled=true;$('forgot').disabled=true; }
}
init();
