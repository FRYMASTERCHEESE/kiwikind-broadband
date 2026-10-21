"""One-shot, exact-source transformation on a private working branch only.
Generated files are committed for review; this helper is removed before release.
"""
from pathlib import Path
import subprocess

EXPECTED = 'ebbb26e811cfab953f4aa2d63332e3e9ed0183e2'
subprocess.run(['git', 'merge-base', '--is-ancestor', EXPECTED, 'HEAD'], check=True)

def replace(path, old, new, count=1):
    p = Path(path); text = p.read_text()
    if text.count(old) != count:
        raise RuntimeError(f'Unexpected source in {path}: expected {count} exact matches')
    p.write_text(text.replace(old, new))

# Keep sandbox models/tables and routes unchanged.
p = Path('payments/models.py'); p.write_text(p.read_text()+'\nfrom .live_models import LiveAgreement, LiveInvoice, LiveEvent  # noqa: E402,F401\n')
p = Path('payments/admin.py'); p.write_text(p.read_text()+'\nfrom . import live_admin  # noqa: E402,F401\n')
replace('payments/live_models.py', 'from portal.owner_admin import OWNER_EMAIL, OWNER_USERNAME\n', '')
replace('payments/live_models.py', 'def approved_agreements():\n', 'def approved_agreements():\n    from portal.owner_admin import OWNER_EMAIL, OWNER_USERNAME\n')
replace('payments/urls.py', 'from . import views\n', 'from . import views, live_views, setup_views\n')
replace('payments/urls.py', 'urlpatterns = [\n', '''urlpatterns = [
    path('payments/', live_views.page),
    path('api/billing/live/summary', live_views.summary),
    path('api/billing/live/checkout', live_views.checkout),
    path('api/billing/live/cancel', live_views.cancel),
    path('api/billing/live/portal', live_views.portal),
    path('api/billing/live/refund', live_views.refund),
    path('api/billing/live/webhook', live_views.webhook),
    path('admin/stripe-setup/', setup_views.setup, name='stripe-setup'),
''')

# Port the existing audited reconciliation implementation to isolated live
# records with mode/account/consent boundaries, not runtime monkey-patching.
s = Path('payments/service.py').read_text()
s = s.replace('Sandbox recurring Checkout', 'Live recurring Checkout')
s = s.replace('from .models import TestAgreement, TestInvoice', 'from .live_models import LiveAgreement, LiveInvoice')
s = s.replace('from .gateway import', 'from .live_gateway import')
s = s.replace('TestAgreement', 'LiveAgreement').replace('TestInvoice', 'LiveInvoice')
s = s.replace('test_object', 'live_object').replace('cs_test_', 'cs_live_')
s = s.replace('kiwikind_test_agreement', 'kiwikind_live_agreement')
s = s.replace('kiwikind-sandbox-', 'kiwikind-live-').replace('sandbox_recurring_consent', 'live_recurring_consent')
s = s.replace("'name': 'KiwiKind TEST ONLY monthly'", "'name': a.label")
s = s.replace("'name': 'KiwiKind TEST ONLY setup'", "'name': a.label + ' - setup'")
s = s.replace('TEST ONLY. No broadband service or real payment is supplied.', 'Recurring monthly payment under your accepted KiwiKind service terms. Broadband activation is confirmed separately.')
s = s.replace("origin()+'/billing/", "origin()+'/payments/")
old = "        if str(a.terms_version) != expected_version:"
assert s.count(old) == 1
s = s.replace(old, "        a.check_checkout_eligibility()\n"+old)
old = "or (obj.get('metadata') or {}).get('kiwikind_live_agreement') != str(a.pk)):"
assert s.count(old) == 1
s = s.replace(old, "or (obj.get('metadata') or {}).get('kiwikind_live_agreement') != str(a.pk)\n            or (obj.get('metadata') or {}).get('kiwikind_terms_version') != str(a.terms_version)):")
s = s.replace("metadata={'kiwikind_live_agreement': str(a.pk)},", "metadata={'kiwikind_live_agreement': str(a.pk), 'kiwikind_terms_version': str(a.terms_version)},")
s = s.replace("subscription_data={'metadata': {'kiwikind_live_agreement': str(a.pk)}},", "subscription_data={'metadata': {'kiwikind_live_agreement': str(a.pk), 'kiwikind_terms_version': str(a.terms_version)}},\n            automatic_tax={'enabled': False}, allow_promotion_codes=False,")
old = "if (sub.get('metadata') or {}).get('kiwikind_live_agreement') != str(a.pk):"
assert s.count(old) == 1
s = s.replace(old, "if ((sub.get('metadata') or {}).get('kiwikind_live_agreement') != str(a.pk)\n            or (sub.get('metadata') or {}).get('kiwikind_terms_version') != str(a.terms_version)):")
s = s.replace('reviewed test agreement', 'reviewed customer agreement').replace('test agreement', 'customer agreement').replace('Test checkout', 'Checkout')
assert 'cs_test_' not in s and 'TEST ONLY' not in s and 'kiwikind_test_agreement' not in s
Path('payments/live_service.py').write_text(s)

# A visible portal entry without changing sign-in/session handling.
p=Path('site/dist/index.html'); html=p.read_text()
assert html.count('</header>') == 1
p.write_text(html.replace('</header>', '<a href="/payments/" class="button">Payments &amp; invoices</a></header>'))

# Native payment navigation uses the existing authenticated API and UI helpers.
main='android/app/src/main/java/nz/kiwikind/broadband/MainActivity.java'
replace(main, '"Our journey","FAQs",signedIn?', '"Our journey","FAQs","Payments",signedIn?')
replace(main, '"progress","questions","account","signup"', '"progress","questions","payments","account","signup"')
replace(main, 'if(page.equals("account")){', 'if(page.equals("payments")){if(signedIn)liveBillingScreen();else auth(false);}else if(page.equals("account")){')
old='accountCard("Billing","Payments disabled",()->run(()->api.call("invoices",null),r->{refreshScreen=null;content.removeAllViews();title("Billing");paragraph("Payments are disabled. No charges are being taken.");JSONArray a=r.optJSONArray("invoices");if(a==null||a.length()==0)paragraph("No invoices.");else for(int i=0;i<a.length();i++)paragraph(a.getJSONObject(i).toString());button("Billing status / private payment testing",this::billingScreen);nav();}));'
replace(main, old, 'accountCard("Payments & invoices","Review your agreed service and pay securely",this::liveBillingScreen);')
method=r'''
    private void liveBillingScreen(){run(()->api.call("billing/live/summary",null),r->{
        refreshScreen=this::liveBillingScreen;content.removeAllViews();title("Payments & invoices");
        if(!"live".equals(r.optString("mode"))){paragraph("Unexpected payment response. No checkout was opened.");nav();return;}
        boolean enabled=r.optBoolean("live_payments_enabled",false);
        paragraph(enabled?"Review your monthly service and terms before paying. Card details are entered securely on Stripe.":"Online payments are not yet activated. No new checkout can be started. Existing invoice obligations are unchanged.");
        JSONArray agreements=r.optJSONArray("agreements");
        if(agreements==null||agreements.length()==0)paragraph("No owner-approved payment agreement is assigned to this account.");
        else for(int i=0;i<agreements.length();i++){
            JSONObject a=agreements.getJSONObject(i);
            long monthlyCents=a.getLong("monthly_cents"),setupCents=a.getLong("setup_cents");
            if(monthlyCents<50||monthlyCents>1000000||setupCents<0||setupCents>1000000||!"NZD".equals(a.optString("currency"))){paragraph("Offer requires review. No payment can be started.");continue;}
            String id=a.getString("id"),version=a.getString("terms_version"),status=a.getString("status"),terms=a.getString("service_terms");
            String monthly=billingMoney(monthlyCents),setup=billingMoney(setupCents),total=billingMoney(monthlyCents+setupCents);
            paragraph(a.getString("label")+"\n"+monthly+" per month + "+setup+" once. First payment: "+total+". "+a.getString("tax_treatment")+".\nStatus: "+status+(a.optBoolean("cancel_at_period_end")?" — cancellation at period end requested":""));
            paragraph("Service and cancellation terms\n"+terms);
            if(enabled&&a.optBoolean("ready_to_pay")&&"pending".equals(status))button("Pay with Stripe",()->new AlertDialog.Builder(this)
                .setTitle("Confirm recurring payment")
                .setMessage("REAL PAYMENT: "+total+" now, then "+monthly+" each month until cancelled under the displayed terms. "+a.optString("tax_treatment")+".\n\n"+terms+"\n\nDo you agree to these charges and terms?")
                .setNegativeButton("Back",null).setPositiveButton("Agree and pay",(dialog,which)->run(
                    ()->api.call("billing/live/checkout",data("agreement_id",id,"terms_version",version,"accept_live_recurring",true)),reply->{
                        String url=reply.optString("url");if(!reply.optBoolean("livemode")||!BillingUrls.isLiveCheckout(url)){message("Unrecognised payment address. Nothing opened.");return;}
                        startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(url)));message("Stripe opened. Refresh after returning; returning alone does not confirm payment.");
                    })).show());
            if(a.optBoolean("can_manage")&&!a.optBoolean("cancel_at_period_end")&&!java.util.Arrays.asList("pending","canceled","incomplete_expired").contains(status))button("Stop future subscription billing",()->new AlertDialog.Builder(this)
                .setTitle("Stop future billing?").setMessage("Stop Stripe billing at the current period end. Contact KiwiKind separately to confirm broadband cancellation and any contractual charges.")
                .setNegativeButton("Keep billing",null).setPositiveButton("Stop billing",(dialog,which)->run(
                    ()->api.call("billing/live/cancel",data("agreement_id",id,"accept_live_cancel",true)),reply->{message(reply.optString("message"));liveBillingScreen();})).show());
            if(a.optBoolean("can_manage")&&r.optBoolean("portal_available"))button("Manage card / Stripe invoices",()->run(
                ()->api.call("billing/live/portal",data("agreement_id",id)),reply->{String url=reply.optString("url");if(!reply.optBoolean("livemode")||!BillingUrls.isLivePortal(url)){message("Unrecognised Stripe account address.");return;}startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(url)));}));
            JSONArray invoices=a.optJSONArray("invoices");if(invoices!=null)for(int j=0;j<invoices.length();j++){JSONObject inv=invoices.getJSONObject(j);paragraph("Invoice "+billingMoney(inv.getLong("amount_cents"))+" — "+inv.getString("status")+"\nRefunded: "+billingMoney(inv.getLong("refunded_cents"))+(inv.optString("dispute_status").isEmpty()?"":" · Dispute: "+inv.optString("dispute_status")));}
        }
        paragraph("A successful payment does not automatically activate broadband. Contact kiwikindbroadband@gmail.com for service or payment help.");
        button("Refresh payment status",this::liveBillingScreen);
        button("Private sandbox testing",this::billingScreen);
        button("Previous account invoices",()->run(()->api.call("invoices",null),reply->{content.removeAllViews();title("Previous invoices");JSONArray rows=reply.optJSONArray("invoices");if(rows==null||rows.length()==0)paragraph("No previous invoices.");else for(int j=0;j<rows.length();j++)paragraph(rows.getJSONObject(j).toString());button("Back to payments",this::liveBillingScreen);nav();}));
        nav();
    });}
'''
replace(main, '    private String billingMoney(long cents)', method+'\n    private String billingMoney(long cents)')
replace('android/app/build.gradle', 'versionCode 10', 'versionCode 11')
replace('android/app/build.gradle', "versionName '0.2.8-prelaunch'", "versionName '0.2.9-payments-prelaunch'")

# Add visible private setup navigation only in owner admin, never on public pages.
replace('payments/live_admin.py', 'from django.utils import timezone\n', 'from django.utils import timezone\nfrom django.utils.html import format_html\n')
replace('payments/live_admin.py', "readonly_fields = ['terms_version'", "readonly_fields = ['stripe_setup', 'terms_version'")
replace('payments/live_admin.py', '    def has_delete_permission(self, request, obj=None):\n        return False\n', '''    @admin.display(description='Stripe connection and release checklist')
    def stripe_setup(self, obj):
        return format_html('<a href="{}">Open private Stripe setup</a>', '/admin/stripe-setup/')

    def has_delete_permission(self, request, obj=None):
        return False
''')
# Log only booleans on deployment, never values or account/customer records.
p=Path('deploy/start.sh'); text=p.read_text(); marker='python manage.py collectstatic --noinput'
assert marker in text
p.write_text(text.replace(marker, marker+'\npython manage.py report_billing_config',1))
print('Prepared isolated live billing, owner setup and customer navigation. No external payment calls were made.')
