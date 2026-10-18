'use strict';
// Opt-in account screens; no ad tags, tracking pixels, or public design changes.
const pendingReferral=new URL(location.origin+location.pathname+location.search).searchParams.get('ref')||'';
if (/^[A-Za-z0-9_-]{24}$/.test(pendingReferral)) $('referral-code').value=pendingReferral;
$('referral-entry').classList.toggle('hidden',!registration);
$('toggle-auth').addEventListener('click',()=> $('referral-entry').classList.toggle('hidden',!registration));
async function loadReferrals(create=false){
  const generation=accountGeneration;
  const result=await api('referrals',create?{}:undefined,generation);
  if(generation!==accountGeneration)return;
  $('referral-result').replaceChildren(node('p',result.code?`Your code: ${result.code}`:'Create a code to prepare your invitation link.'));
  if(result.share_url){const link=node('a',result.share_url);link.href=result.share_url;$('referral-result').append(link);}
  for(const item of result.history)record($('referral-result'),'Referral',`${item.status} · ${date(item.created_at)}`);
  $('create-referral').disabled=Boolean(result.code);
}
$('load-referrals').addEventListener('click',safeAction(()=>loadReferrals()));
$('create-referral').addEventListener('click',safeAction(()=>loadReferrals(true)));
$('load-preferences').addEventListener('click',safeAction(async()=>{
  const generation=accountGeneration;const value=await api('preferences',undefined,generation);
  if(generation===accountGeneration)$('account-notifications').checked=value.account_notifications;
}));
$('preferences-form').addEventListener('submit',safeAction(async()=>{
  await api('preferences',{account_notifications:$('account-notifications').checked});
  notice('Preference saved. Notification delivery and marketing remain disabled.');
}));
$('google-deletion').addEventListener('click',safeAction(async()=>{
  if(!$('confirm-google-deletion').checked)throw Error('Confirm that you want account deletion review.');
  notice((await api('privacy/deletion',{confirm:true})).message);
}));
