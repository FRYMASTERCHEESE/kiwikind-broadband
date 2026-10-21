/* Account-specific content uses text nodes. Never infer payment from redirects. */
'use strict';
(() => {
  const notice = document.getElementById('payment-notice');
  const records = document.getElementById('payment-records');
  const signin = document.getElementById('payment-signin');
  const refresh = document.getElementById('payment-refresh');
  let busy = false, generation = 0;
  const money = cents => new Intl.NumberFormat('en-NZ', {style:'currency', currency:'NZD'}).format(cents/100);
  function text(tag, value, parent, cls) {
    const e=document.createElement(tag); e.textContent=value; if(cls)e.className=cls; parent.append(e); return e;
  }
  function allowed(url, portal) {
    if(typeof url!=='string'||/[\s\\]/.test(url))return false;
    try { const u=new URL(url);return u.protocol==='https:'&&!u.username&&!u.password&&(!u.port||u.port==='443')&&
      (portal ? u.hostname==='billing.stripe.com'&&u.pathname.startsWith('/p/session/')&&!u.pathname.startsWith('/p/session/test_') : u.hostname==='checkout.stripe.com'&&u.pathname.startsWith('/c/pay/cs_live_'));
    } catch { return false; }
  }
  async function request(path, body) {
    const options={credentials:'same-origin',cache:'no-store',headers:{'Accept':'application/json'}};
    if(body) {
      const csrf=await fetch('/api/csrf',{credentials:'same-origin',cache:'no-store'});
      if(!csrf.ok)throw new Error('Could not verify your session. Refresh before continuing.');
      const token=(await csrf.json()).csrfToken;
      options.method='POST'; options.headers['Content-Type']='application/json';options.headers['X-CSRFToken']=token;options.body=JSON.stringify(body);
    }
    const r=await fetch('/api/billing/live/'+path,options);
    if(r.status===401){const e=new Error('Please sign in again.');e.expired=true;throw e;}
    const data=await r.json();if(!r.ok)throw new Error(data.error||'Request unavailable. Refresh before retrying.');return data;
  }
  function controls(disabled) {document.querySelectorAll('button').forEach(b=>{b.disabled=disabled;});}
  function action(parent, label, fn) {const b=text('button',label,parent);b.type='button';b.addEventListener('click',async()=>{
    if(busy)return;busy=true;controls(true);try{await fn();}catch(e){notice.textContent=e.message||'Connection interrupted. The payment may have completed; refresh before retrying.';if(e.expired){generation++;records.replaceChildren();signin.hidden=false;}}finally{busy=false;controls(false);}
  });}
  async function load() {
    if(busy)return;busy=true;controls(true);const current=++generation;records.replaceChildren();signin.hidden=true;
    notice.textContent='Checking your account…';
    try {
      const data=await request('summary');if(current!==generation)return;
      if(data.mode!=='live'||!Array.isArray(data.agreements))throw new Error('Unexpected billing response. No checkout opened.');
      notice.textContent=data.live_payments_enabled ? 'Review the amounts and service terms before choosing Pay with Stripe.' : 'Online payments are not yet activated. No new checkout can be started. Existing invoice obligations are unchanged.';
      if(!data.agreements.length)text('p','No owner-approved payment agreement is assigned to your account.',records);
      for(const a of data.agreements) {
        const card=document.createElement('article');records.append(card);text('h2',a.label,card);
        if(!Number.isSafeInteger(a.monthly_cents)||!Number.isSafeInteger(a.setup_cents)||a.monthly_cents<50||a.setup_cents<0||a.currency!=='NZD') {text('p','Offer requires review. No payment can be started.',card);continue;}
        const monthly=money(a.monthly_cents), setup=money(a.setup_cents), total=money(a.monthly_cents+a.setup_cents);
        text('p',monthly+' each month + '+setup+' once. First payment: '+total+'. '+a.tax_treatment+'.',card);
        text('p','Payment status: '+a.status+(a.cancel_at_period_end?' — cancellation at period end requested.':''),card);
        const terms=document.createElement('details');card.append(terms);text('summary','Read service and cancellation terms',terms);text('p',a.service_terms,terms,'terms');
        if(data.live_payments_enabled&&a.ready_to_pay&&a.status==='pending')action(card,'Pay with Stripe',async()=>{
          if(!window.confirm('REAL PAYMENT: '+total+' now, then '+monthly+' every month until cancellation under the displayed terms. '+a.tax_treatment+'.\n\n'+a.service_terms+'\n\nDo you agree to these recurring charges and terms?'))return;
          const reply=await request('checkout',{agreement_id:a.id,terms_version:a.terms_version,accept_live_recurring:true});
          if(reply.livemode!==true||!allowed(reply.url,false))throw new Error('Unrecognised checkout address. Nothing opened.');window.location.assign(reply.url);
        });
        if(a.can_manage&&!a.cancel_at_period_end&&!['pending','canceled','incomplete_expired'].includes(a.status))action(card,'Stop future subscription billing',async()=>{
          if(!window.confirm('Stop future Stripe subscription billing at the end of the current period? Contact KiwiKind separately to confirm broadband cancellation and any contractual charges.'))return;
          const reply=await request('cancel',{agreement_id:a.id,accept_live_cancel:true});notice.textContent=reply.message;card.querySelectorAll('button').forEach(b=>b.remove());
        });
        if(a.can_manage&&data.portal_available)action(card,'Manage card / Stripe invoices',async()=>{
          const reply=await request('portal',{agreement_id:a.id});if(reply.livemode!==true||!allowed(reply.url,true))throw new Error('Unrecognised account portal address. Nothing opened.');window.location.assign(reply.url);
        });
        if(a.invoices&&a.invoices.length){text('h3','Confirmed invoice history',card);const list=document.createElement('ul');card.append(list);for(const i of a.invoices)text('li',money(i.amount_cents)+' — '+i.status+'; refunded '+money(i.refunded_cents)+(i.dispute_status?'; dispute '+i.dispute_status:''),list);}
      }
    } catch(e){notice.textContent=e.message||'Could not load payments. Your saved login has not been changed.';if(e.expired){records.replaceChildren();signin.hidden=false;}}
    finally {busy=false;controls(false);}
  }
  refresh.addEventListener('click',load);
  window.addEventListener('pageshow',e=>{if(e.persisted)load();});
  load();
})();
