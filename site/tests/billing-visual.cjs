// Synthetic local browser review; never use customer infrastructure or real Stripe.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const base='http://127.0.0.1:8765';
(async()=>{
 if(!process.env.KIWIKIND_LOCAL_SESSION_FILE)throw new Error('Disposable session fixture required');
 const session=JSON.parse(fs.readFileSync(process.env.KIWIKIND_LOCAL_SESSION_FILE,'utf8'));
 const browser=await chromium.launch(process.env.PLAYWRIGHT_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH}:{});
 try{
  for(const [name,width,height] of [['phone',360,800],['desktop',1280,900]]){
   const context=await browser.newContext({viewport:{width,height}});
   await context.addCookies([{name:'sessionid',value:session.sessionid,url:base,httpOnly:true,sameSite:'Lax'}]);
   const page=await context.newPage();const errors=[];page.on('pageerror',error=>errors.push(error.message));
   await page.route('https://**',route=>route.abort());
   const agreement={id:'00000000-0000-0000-0000-000000000001',terms_version:'00000000-0000-0000-0000-000000000002',label:'Synthetic monthly test',monthly_cents:1000,setup_cents:200,status:'pending',cancel_at_period_end:false,invoices:[]};
   await page.route('**/api/billing/summary',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({mode:'sandbox_only',live_payments_enabled:false,test_enabled:true,agreements:[agreement]})}));
   let posts=0;
   await page.route('**/api/billing/checkout',route=>{
    posts++;const data=route.request().postDataJSON();
    assert.equal(data.accept_test_recurring,true);assert.equal(data.terms_version,agreement.terms_version);
    assert.equal(data.monthly_cents,undefined);assert.equal(data.agreement_id,agreement.id);
    return route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({error:'Synthetic reconciliation warning; no provider call was made.'})});
   });
   await page.goto(base+'/billing/?returned=1');
   await page.getByRole('heading',{name:agreement.label}).waitFor();
   const checkout=page.getByRole('button',{name:'Open Stripe test checkout'});
   assert.equal(await checkout.isDisabled(),true);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Billing page overflow');
   await page.screenshot({path:`test-results/wholesale-visual/${name}-billing.png`,fullPage:true});
   await page.getByRole('checkbox').check();await checkout.click();
   await page.getByText('Synthetic reconciliation warning; no provider call was made.').waitFor();
   assert.equal(posts,1);assert.equal(await page.getByRole('checkbox').isChecked(),false);
   assert.equal(await checkout.isDisabled(),true);
   await page.route('**/api/billing/summary',route=>route.fulfill({status:401,contentType:'application/json',body:'{"error":"Sign in first"}'}));
   await page.getByRole('button',{name:'Refresh billing status'}).click();
   await page.getByText('Sign in again from My KiwiKind before continuing.').waitFor();
   assert.equal(await page.locator('#agreements').textContent(),'');assert.deepEqual(errors,[]);
   await context.close();
  }
 }finally{await browser.close();}
 console.log('Synthetic phone/desktop billing: consent, amounts, stale-session clearing and layout passed. No Stripe network request.');
})().catch(error=>{console.error(error);process.exitCode=1;});
