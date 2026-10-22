"""Customer-facing Android screens must show real accounts and approved offers, not QA purchase controls."""
from pathlib import Path
from django.test import SimpleTestCase


class CustomerAppReleaseTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.main = Path("android/app/src/main/java/nz/kiwikind/broadband/MainActivity.java").read_text()
        cls.strings = Path("android/app/src/main/res/values/strings.xml").read_text()

    def test_real_account_replaces_marketing_demo(self):
        self.assertIn('if("mykiwikind".equals(id)){if(signedIn)home();else auth(false);return;}',self.main)
        self.assertNotIn('Dashboard design preview only',self.main)

    def test_customer_payments_do_not_offer_private_test_checkout(self):
        self.assertNotIn('button("Private sandbox testing"',self.main)
        self.assertIn('button("Refresh payments",this::liveBillingScreen)',self.main)
        self.assertIn('isLiveCheckout(url)',self.main)
        self.assertIn('accept_live_recurring',self.main)
        self.assertIn('this::broadbandPlans',self.main)
        self.assertIn('this::orders',self.main)
        self.assertIn('this::tickets',self.main)

    def test_no_false_no_service_or_prelaunch_copy_on_customer_login(self):
        self.assertNotIn("Pre-launch terms",self.main)
        self.assertNotIn("PRE-LAUNCH · No live service",self.strings)
        self.assertIn("availability confirmation required",self.strings)
        self.assertIn("broadband and account terms",self.strings)
