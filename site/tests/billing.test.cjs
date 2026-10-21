const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {safeCheckout,money,invoiceLabel} = require('../../payments/static/payments/billing.js');
test('billing only opens exact Stripe test checkouts',()=>{
 assert.equal(safeCheckout('https://checkout.stripe.com/c/pay/cs_test_synthetic#test'),true);
 for(const url of [null,'','http://checkout.stripe.com/c/pay/cs_test_a','https://checkout.stripe.com/c/pay/cs_live_a',
 'https://checkout.stripe.com.evil.invalid/c/pay/cs_test_a','https://name@checkout.stripe.com/c/pay/cs_test_a',
 'https://checkout.stripe.com:444/c/pay/cs_test_a','javascript:alert(1)','https://checkout.stripe.com\n/c/pay/cs_test_a'])assert.equal(safeCheckout(url),false,String(url));
});
test('billing currency uses cents',()=>{assert.equal(money(8500),'$85.00');assert.equal(money(4025),'$40.25');});
test('billing renders text only and does not trust return parameters',()=>{
 const source=fs.readFileSync('payments/static/payments/billing.js','utf8');
 assert.equal(source.includes('innerHTML'),false);assert.equal(source.includes('location.search'),false);
 assert.ok(source.includes('terms_version:a.terms_version'));assert.ok(source.includes('pagehide'));
 assert.ok(source.includes('current!==generation'));assert.ok(source.includes("credentials:'same-origin'"));
});

test('a paid test invoice that was fully refunded is clearly labelled',()=>{
 const full=invoiceLabel({status:'paid',amount_cents:100,refunded_cents:100,dispute_status:''});
 assert.equal(full,'TEST invoice $1.00 · paid · fully refunded $1.00');
 const awaiting=invoiceLabel({status:'paid',amount_cents:100,refunded_cents:0,dispute_status:''});
 assert.equal(awaiting,'TEST invoice $1.00 · paid · refunded $0.00');
 const partial=invoiceLabel({status:'paid',amount_cents:1000,refunded_cents:200,dispute_status:''});
 assert.equal(partial,'TEST invoice $10.00 · paid · refunded $2.00');
 const challenged=invoiceLabel({status:'open',amount_cents:100,refunded_cents:0,dispute_status:''});
 assert.ok(challenged.includes('open'));
 assert.ok(!challenged.includes('fully refunded'));
});
