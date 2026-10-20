/* No secrets, arbitrary redirects, or success-by-query-string. */
(function () {
  'use strict';
  function safeCheckout(value) {
    if (typeof value !== 'string' || value.length > 4096 || /[\s\\]/.test(value)) return false;
    try { const u = new URL(value); return u.protocol === 'https:' && u.hostname === 'checkout.stripe.com' &&
      !u.username && !u.password && (!u.port || u.port === '443') && u.pathname.startsWith('/c/pay/cs_test_'); }
    catch (_) { return false; }
  }
  function money(cents) { return new Intl.NumberFormat('en-NZ', {style:'currency', currency:'NZD'}).format(cents / 100); }
  if (typeof module !== 'undefined') module.exports = {safeCheckout, money};
  if (typeof document === 'undefined') return;
  const list = document.getElementById('agreements'), feedback = document.getElementById('feedback');
  const refresh = document.getElementById('refresh');
  let generation = 0, busy = false;
  function element(tag, text, parent) { const node=document.createElement(tag); node.textContent=text; if(parent)parent.append(node); return node; }
  function clear() { generation++; list.replaceChildren(); }
  async function api(path, data) {
    const token = document.querySelector('[name=csrfmiddlewaretoken]').value;
    const response = await fetch('/api/billing/'+path, {method:data?'POST':'GET', credentials:'same-origin', cache:'no-store',
      headers:data?{'Content-Type':'application/json','X-CSRFToken':token}:{}, body:data?JSON.stringify(data):undefined,
      signal:AbortSignal.timeout(75000)});
    if(response.status===401 || response.status===403) { clear(); throw new Error('Sign in again from My KiwiKind before continuing.'); }
    const result=await response.json();
    if(!response.ok)throw new Error(result.error || 'Billing is unavailable. Refresh before retrying.');
    return result;
  }
  function confirmButton(article, wording, label, action) {
    const row=element('label','',article), box=document.createElement('input'); box.type='checkbox';row.append(box);element('span',wording,row);
    const button=element('button',label,article);button.type='button';button.disabled=true;
    box.addEventListener('change',()=>{button.disabled=!box.checked||busy;});
    button.addEventListener('click',async()=>{
      if(!box.checked||busy)return;busy=true;button.disabled=true;refresh.disabled=true;
      const current=generation;feedback.textContent='Sending test request securely…';
      try { const result=await action(); if(current!==generation)return;
        if(result.url) {if(!result.test_only||!safeCheckout(result.url))throw new Error('Unrecognised test checkout address.');window.location.assign(result.url);}
        else {feedback.textContent=result.message;await load(true);}
      } catch(error) {if(current===generation)feedback.textContent=error.message||'Request interrupted. Refresh status before retrying; do not create a replacement.';}
      finally {busy=false;refresh.disabled=false;box.checked=false;button.disabled=true;}
    });
  }
  async function load(preserveMessage) {
    const current=++generation;list.replaceChildren();refresh.disabled=true;
    if(!preserveMessage)feedback.textContent='Checking server-confirmed test billing…';
    try {const result=await api('summary');if(current!==generation)return;
      if(result.mode!=='sandbox_only'||result.live_payments_enabled!==false)throw new Error('Unexpected billing mode. Nothing was submitted.');
      if(!preserveMessage)feedback.textContent=result.test_enabled?'Test billing is available for reviewed test agreements.':'Live payments are disabled. No payment is due here.';
      if(!result.agreements.length)element('p','No reviewed test agreements are assigned to your account.',list);
      for(const a of result.agreements){
        const card=element('article','',list);element('h2',a.label,card);
        element('p',money(a.monthly_cents)+' per month · '+money(a.setup_cents)+' one-off setup · '+money(a.monthly_cents+a.setup_cents)+' initial test total.',card);
        element('p','Test status: '+a.status+(a.cancel_at_period_end?' · cancellation at period end requested':''),card);
        if(result.test_enabled&&a.status==='pending') confirmButton(card,
          'I agree to test '+money(a.monthly_cents)+' monthly recurring billing and '+money(a.setup_cents)+' once, using test payment details only. This does not order broadband.',
          'Open Stripe test checkout',()=>api('checkout',{agreement_id:a.id,terms_version:a.terms_version,accept_test_recurring:true}));
        if(result.test_enabled&&!['pending','canceled','incomplete_expired'].includes(a.status)&&!a.cancel_at_period_end)confirmButton(card,
          'Cancel this test subscription at the end of its current period. This does not cancel an actual broadband service.',
          'Cancel test subscription',()=>api('cancel',{agreement_id:a.id,accept_test_cancel:true}));
        if(a.invoices.length){const invoices=element('ul','',card);for(const inv of a.invoices)element('li',
          'TEST invoice '+money(inv.amount_cents)+' · '+inv.status+' · refunded '+money(inv.refunded_cents)+(inv.dispute_status?' · dispute '+inv.dispute_status:''),invoices);}
      }
    } catch(error){if(current===generation){list.replaceChildren();feedback.textContent=error.message||'Billing could not be loaded. Try refresh.';}}
    finally {if(current===generation)refresh.disabled=busy;}
  }
  refresh.addEventListener('click',()=>{if(!busy)load(false);});
  window.addEventListener('pagehide',clear);
  window.addEventListener('pageshow',event=>{if(event.persisted)load(false);});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)clear();else if(!busy)load(false);});
  load(false);
})();
