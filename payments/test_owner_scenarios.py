import json
import uuid
from unittest.mock import MagicMock, patch
from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from portal.testing import owner_fixture
from .models import OwnerSandboxRun, TestAgreement, TestInvoice


@override_settings(INTAKE_ENABLED=False,PLAN_PUBLICATION_ENABLED=False)
class OwnerScenarioTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_superuser('operator','operator@example.invalid','Test-password-123!')
        owner_fixture(self.client,self.owner)
        self.api=MagicMock()
        self.api.v1.test_helpers.test_clocks.create.return_value={'object':'test_helpers.test_clock','id':'clock_synthetic','livemode':False}
        self.api.v1.customers.create.return_value={'object':'customer','id':'cus_synthetic','livemode':False,'test_clock':'clock_synthetic'}
        self.api.v1.customers.retrieve.return_value=self.api.v1.customers.create.return_value
        self.api.v1.events.list.return_value={'data':[],'has_more':False}
        self.api.v1.invoices.list.return_value={'data':[]}
        patcher=patch('payments.gateway.client',return_value=self.api);patcher.start();self.addCleanup(patcher.stop)

    def post(self,path,data,client=None):return (client or self.client).post('/api/owner/'+path,json.dumps(data),content_type='application/json')

    def start(self,scenario='renewal',key=None):
        key=key or str(uuid.uuid4())
        r=self.post('sandbox-runs',{'scenario':scenario,'submission_key':key,'confirm_test_only':True})
        self.assertEqual(r.status_code,200,r.content)
        return OwnerSandboxRun.objects.get(pk=r.json()['id'])

    def test_requires_mfa_csrf_consent_and_closed_sales(self):
        self.assertEqual(Client().get('/api/owner/sandbox-runs').status_code,403)
        self.assertEqual(self.post('sandbox-runs',{'scenario':'renewal'}).status_code,400)
        with override_settings(INTAKE_ENABLED=True):
            self.assertEqual(self.post('sandbox-runs',{'scenario':'renewal','confirm_test_only':True}).status_code,503)
        c=Client(enforce_csrf_checks=True);owner_fixture(c,self.owner)
        self.assertEqual(self.post('sandbox-runs',{'confirm_test_only':True},c).status_code,403)
        self.api.v1.customers.create.assert_not_called()

    def test_new_isolated_fixture_idempotence_and_no_real_customer_email(self):
        key=str(uuid.uuid4());run=self.start(key=key);again=self.start(key=key)
        self.assertEqual(run.pk,again.pk);self.assertEqual(OwnerSandboxRun.objects.count(),1)
        self.assertEqual(run.agreement.monthly_cents,100);self.assertEqual(run.agreement.setup_cents,0)
        self.api.v1.test_helpers.test_clocks.create.assert_called_once()
        self.api.v1.customers.create.assert_called_once()
        self.assertNotIn('email',self.api.v1.customers.create.call_args.args[0])
        self.assertEqual(self.api.v1.customers.create.call_args.args[0]['test_clock'],run.clock_id)
        self.assertEqual(self.post('sandbox-runs',{'scenario':'decline-3ds','submission_key':key,'confirm_test_only':True}).status_code,400)

    def test_unverified_provider_object_does_not_bind_customer(self):
        self.api.v1.customers.create.return_value.update(livemode=True)
        r=self.post('sandbox-runs',{'scenario':'renewal','submission_key':str(uuid.uuid4()),'confirm_test_only':True})
        self.assertEqual(r.status_code,409)
        self.assertEqual(OwnerSandboxRun.objects.get().customer_id,'')

    def subscription(self,run):
        a=run.agreement;a.subscription_id='sub_synthetic';a.customer_id=run.customer_id;a.status='active';a.save()
        self.api.v1.subscriptions.retrieve.return_value={'object':'subscription','id':a.subscription_id,'livemode':False,
            'customer':run.customer_id,'metadata':{'kiwikind_test_agreement':str(a.pk)},'items':{'data':[{'current_period_end':2000000000}]}}
        return a

    def test_clock_advance_is_bound_and_idempotent(self):
        run=self.start();self.subscription(run)
        clock={'object':'test_helpers.test_clock','id':run.clock_id,'livemode':False,'status':'ready','frozen_time':1900000000}
        self.api.v1.test_helpers.test_clocks.retrieve.return_value=clock
        self.api.v1.test_helpers.test_clocks.advance.return_value={**clock,'status':'advancing'}
        r=self.post(f'sandbox-runs/{run.pk}/advance',{'confirm_advance':True});self.assertEqual(r.status_code,200,r.content)
        clock['frozen_time']=2000007200
        self.assertEqual(self.post(f'sandbox-runs/{run.pk}/advance',{'confirm_advance':True}).status_code,200)
        self.api.v1.test_helpers.test_clocks.advance.assert_called_once()
        self.api.v1.customers.retrieve.return_value={**self.api.v1.customers.create.return_value,'test_clock':'clock_wrong'}
        self.assertEqual(self.post(f'sandbox-runs/{run.pk}/advance',{'confirm_advance':True}).status_code,409)

    def test_provider_evidence_is_customer_bound_and_requires_app_ledger(self):
        run=self.start('decline-3ds');a=self.subscription(run)
        def event(kind,customer,extra):return {'object':'event','livemode':False,'type':kind,'data':{'object':{'livemode':False,'customer':customer,**extra}}}
        self.api.v1.events.list.return_value={'data':[
            event('payment_intent.payment_failed',run.customer_id,{'last_payment_error':{'code':'card_declined'}}),
            event('payment_intent.requires_action',run.customer_id,{}),
            event('payment_intent.payment_failed','cus_other',{'last_payment_error':{'code':'card_declined'}})],'has_more':False}
        invoice={'object':'invoice','id':'in_synthetic','livemode':False,'customer':run.customer_id,
            'currency':'nzd','subscription':a.subscription_id,'total':100,'amount_paid':100,'status':'paid','billing_reason':'subscription_cycle'}
        self.api.v1.invoices.list.return_value={'data':[invoice]}
        r=self.post(f'sandbox-runs/{run.pk}/evidence',{}).json()['flags']
        self.assertTrue(r['decline_seen']);self.assertTrue(r['authentication_requested']);self.assertFalse(r['renewal_paid'])
        TestInvoice.objects.create(agreement=a,provider_id='in_synthetic',status='paid',amount_cents=100,payment_intent='pi_synthetic')
        self.api.v1.payment_intents.retrieve.return_value={'object':'payment_intent','id':'pi_synthetic','livemode':False,'customer':run.customer_id,'latest_charge':'ch_synthetic','amount':100,'currency':'nzd','status':'succeeded'}
        self.api.v1.charges.retrieve.return_value={'object':'charge','id':'ch_synthetic','livemode':False,'customer':run.customer_id,
            'payment_intent':'pi_synthetic','amount':100,'currency':'nzd','paid':True,'payment_method_details':{'card':{'three_d_secure':{'result':'authenticated'}}}}
        r=self.post(f'sandbox-runs/{run.pk}/evidence',{}).json()['flags']
        self.assertTrue(r['renewal_paid']);self.assertTrue(r['authentication_completed']);self.assertTrue(r['ledger_synced'])

        run.refresh_from_db();self.assertEqual(run.evidence,r);self.assertIsNotNone(run.checked_at)
        self.api.v1.charges.retrieve.return_value['payment_intent']='pi_other'
        self.assertFalse(self.post(f'sandbox-runs/{run.pk}/evidence',{}).json()['flags']['authentication_completed'])
