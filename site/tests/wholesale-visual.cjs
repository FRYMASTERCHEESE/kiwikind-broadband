// Local synthetic fixture only; never point this review at customer infrastructure.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const base='http://127.0.0.1:8765';
(async()=>{
 const browser=await chromium.launch(process.env.PLAYWRIGHT_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH}:{});
 fs.mkdirSync('test-results/wholesale-visual',{recursive:true});
 try {
  for(const [name,width,height] of [['phone',360,800],['desktop',1280,900]]){
   const context=await browser.newContext({viewport:{width,height}});
   const page=await context.newPage();const errors=[];page.on('pageerror',error=>errors.push(error.message));
   await page.route('https://accounts.google.com/**',route=>route.abort());
   await page.route('**/api/**',route=>{
    const path=new URL(route.request().url()).pathname;
    const data=path==='/api/bootstrap'?{intake_enabled:false,registration_enabled:true,csrfToken:'fixture',account:{email:'synthetic@example.invalid'}}:path==='/api/csrf'?{csrfToken:'fixture'}:
      path==='/api/me'?{email:'synthetic@example.invalid'}:path==='/api/connection-progress'?
      {message:'Pre-launch only. Orders and payments are disabled.',orders:[{request_id:'synthetic-request',stage:'ready',updated_at:'2026-10-19T00:00:00Z'}],faults:[]}:{};
    return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)});
   });
   await page.goto(base+'/#portal');
   await page.locator('#dashboard').waitFor({state:'visible'});
   await page.locator('#load-connection-progress').click();
   await page.getByText('Prepared — awaiting launch approval',{exact:true}).waitFor();
   assert.equal(await page.locator('#order-submit').isDisabled(),true);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Customer page overflow');
   await page.screenshot({path:`test-results/wholesale-visual/${name}-customer.png`});
   await context.setOffline(true);
   await page.locator('#load-connection-progress').click();
   // Route fulfilment remains available offline, so explicitly fail the data read.
   await page.route('**/api/connection-progress',route=>route.abort());
   await page.locator('#load-connection-progress').click();
   await page.getByText('Updates could not load. Your account is preserved. Reconnect and tap Refresh preparation.').waitFor();
   assert.equal(await page.locator('#signed-in-email').textContent(),'synthetic@example.invalid');
   await context.setOffline(false);
   if(process.env.KIWIKIND_LOCAL_SESSION_FILE){
    const session=JSON.parse(fs.readFileSync(process.env.KIWIKIND_LOCAL_SESSION_FILE,'utf8'));
    await context.addCookies([{name:'sessionid',value:session.sessionid,url:base,httpOnly:true,sameSite:'Lax'}]);
    await page.goto(base+'/admin/wholesale/');
    await page.getByRole('heading',{name:'Pre-launch: prepare and practise'}).waitFor();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Admin dashboard overflow');
    await page.screenshot({path:`test-results/wholesale-visual/${name}-admin.png`,fullPage:true});
    await page.goto(base+'/admin/portal/wholesaleorder/add/');
    await page.locator('#id_address').waitFor({state:'visible'});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Order form overflow');
    await page.screenshot({path:`test-results/wholesale-visual/${name}-order-form.png`,fullPage:true});
   }
   assert.deepEqual(errors,[]);await context.close();
  }
 } finally {await browser.close();}
 console.log('Wholesale phone/desktop, closed intake, account retention and owner forms verified.');
})().catch(error=>{console.error(error);process.exitCode=1;});
