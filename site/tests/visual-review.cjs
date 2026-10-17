// Disconnected browser fixtures: no credentials, customers, or production writes.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 fs.mkdirSync('web-visual-evidence',{recursive:true});
 const browser=await chromium.launch();
 try {
  for(const [name,width,height] of [['desktop',1280,900],['phone',390,844]]){
   const page=await browser.newPage({viewport:{width,height}});
   await page.route('**/api/**',route=>{
    const path=new URL(route.request().url()).pathname;
    return route.fulfill({status:path==='/api/me'?401:200,contentType:'application/json',body:JSON.stringify(path==='/api/status'?{intake_enabled:false}:path==='/api/csrf'?{csrfToken:'fixture'}:{error:'Sign in first'})});
   });
   await page.route('https://accounts.google.com/**',route=>route.abort());
   for(const hash of ['home','why','mykiwikind','questions','signin','signup']){
    await page.goto('http://127.0.0.1:8765/#'+hash);
    await page.waitForFunction(()=>document.getElementById('auth-submit').disabled===false || document.getElementById('notice').textContent.includes('registration is closed'));
    if(hash==='questions')await page.getByText('Can I sign up for broadband today?',{exact:true}).click();
    if(hash==='signin')await page.locator('#auth-form').waitFor({state:'visible'});
    if(hash==='signup')assert.equal(await page.locator('#auth-submit').isDisabled(),true);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Horizontal overflow: '+name+' '+hash);
    await page.screenshot({path:`web-visual-evidence/${name}-${hash}.png`});
   }
   await page.close();
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
