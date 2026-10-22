import json
import uuid
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from .models import Ticket, Message, PrivacyRequest, AuditEvent, DraftPlan, Provider, AvailabilityEvidence, WholesaleOrder
from .testing import owner_fixture


class OwnerOperationsTests(TestCase):
    def setUp(self):
        User=get_user_model()
        self.owner=User.objects.create_superuser('operator','operator@example.invalid','Test-password-123!')
        owner_fixture(self.client,self.owner)
        self.customer=User.objects.create_user('customer',email='customer@example.invalid',password='Test-password-123!')
        self.ticket=Ticket.objects.create(user=self.customer,subject='Synthetic question',category='support')

    def post(self,path,data,client=None):
        return (client or self.client).post('/api/owner/'+path,json.dumps(data),content_type='application/json')

    def get(self,kind,pk):return self.client.get(f'/api/owner/operations/{kind}/{pk}')

    def save(self,kind,pk,values,**extra):
        token=self.get(kind,pk).json()['version']
        return self.post(f'operations/{kind}/{pk}',{'version':token,'values':values,**extra})

    def test_anonymous_customer_and_staff_cannot_use_operations(self):
        c=Client()
        for path in ['operations','operations/customers','operations/tickets/'+str(self.ticket.pk)]:
            self.assertEqual(c.get('/api/owner/'+path).status_code,403)
        c.force_login(self.customer)
        self.assertEqual(c.get('/api/owner/operations').status_code,403)
        self.customer.is_staff=True;self.customer.is_superuser=True;self.customer.save()
        c.force_login(self.customer)
        self.assertEqual(c.get('/api/owner/operations').status_code,403)

    def test_customer_projection_excludes_credentials_and_operators(self):
        result=self.client.get('/api/owner/operations/customers').json()
        self.assertEqual([row['id'] for row in result['rows']],[str(self.customer.pk)])
        self.assertNotIn('password',json.dumps(result));self.assertNotIn('owneridentity',json.dumps(result))
        self.assertEqual(self.get('customers',self.owner.pk).status_code,404)
        self.assertEqual(self.save('customers',self.customer.pk,{'first_name':'Test','last_name':'Person','is_active':True}).status_code,200)
        r=self.save('customers',self.customer.pk,{'is_superuser':True})
        self.assertEqual(r.status_code,400);self.customer.refresh_from_db();self.assertFalse(self.customer.is_superuser)

    def test_stale_or_tampered_versions_cannot_overwrite(self):
        token=self.get('tickets',self.ticket.pk).json()['version']
        self.assertEqual(self.save('tickets',self.ticket.pk,{'status':'resolved'}).status_code,200)
        for value in [token,token+'tampered','']:
            r=self.post(f'operations/tickets/{self.ticket.pk}',{'version':value,'values':{'status':'open'}})
            self.assertEqual(r.status_code,409)
        self.ticket.refresh_from_db();self.assertEqual(self.ticket.status,'resolved')

    def test_replies_are_audited_idempotent_and_conflict_checked(self):
        key=str(uuid.uuid4());data={'body':'Synthetic support reply','submission_key':key}
        for _ in range(2):self.assertEqual(self.post(f'tickets/{self.ticket.pk}/reply',data).status_code,200)
        self.assertEqual(Message.objects.filter(submission_key=key).count(),1)
        self.assertEqual(AuditEvent.objects.filter(action='support_reply').count(),1)
        self.assertEqual(self.post(f'tickets/{self.ticket.pk}/reply',{**data,'body':'Different'}).status_code,409)
        self.assertEqual(self.get('tickets',self.ticket.pk).json()['messages'][0]['body'],data['body'])

    def test_privacy_completion_requires_explicit_manual_fulfilment_confirmation(self):
        request=PrivacyRequest.objects.create(user=self.customer)
        self.assertEqual(self.save('privacy',request.pk,{'status':'completed'}).status_code,400)
        self.assertEqual(self.save('privacy',request.pk,{'status':'completed'},confirm_completed=True).status_code,200)
        self.assertTrue(get_user_model().objects.filter(pk=self.customer.pk).exists())

    def test_private_catalogue_server_gst_and_stale_protection(self):
        plan=DraftPlan.objects.create(name='Ops test quote',wholesale_ex_gst='40.00',address_specific=True)
        values={f['name']:f['value'] for f in self.get('catalogue',plan.pk).json()['fields'] if not f['disabled']}
        values.update({'wholesale_ex_gst':'50.00','review_status':'draft','confirm_current_approval':False})
        r=self.save('catalogue',plan.pk,values)
        self.assertEqual(r.status_code,200,r.content)
        plan.refresh_from_db();self.assertEqual(str(plan.wholesale_inc_gst),'57.50');self.assertIsNone(plan.approved_at)
        values['review_status']='approved'
        self.assertEqual(self.save('catalogue',plan.pk,values).status_code,400)
        self.assertEqual(self.client.get('/api/plans').json()['plans'],[])

    def test_availability_append_only_and_cases_cannot_go_live(self):
        evidence=AvailabilityEvidence.objects.create(address='12 Test Street',postcode='6011',result='unknown',checked_by=self.owner)
        self.assertFalse(self.get('availability',evidence.pk).json()['editable'])
        self.assertEqual(self.save('availability',evidence.pk,{'result':'available'}).status_code,409)
        case=WholesaleOrder.objects.create(address='12 Test Street',postcode='6011',created_by=self.owner,rehearsal=True)
        result=self.get('preparation',case.pk).json()
        self.assertEqual(self.post(f'cases/preparation/{case.pk}/transition',{'target':'availability_review',
            'revision':result['revision'],'submission_key':str(uuid.uuid4()),'note':'Synthetic review','reference':''}).status_code,200)
        self.assertEqual(self.save('preparation',case.pk,{}).status_code,409)

    def test_private_server_previews_current_retail_totals_without_creating_offers(self):
        from django.test import override_settings
        from payments.live_models import LiveAgreement
        values = {'source_monthly_cents': 6992, 'source_setup_cents': 3500, 'agreement_id': 'new'}
        with override_settings(KIWIKIND_ALL_IN_RETAIL_ENABLED=True):
            response = self.post('retail-price-preview', values)
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual((data['monthly_cents'], data['setup_cents'],
            data['first_invoice_cents']), (9062, 5200, 14262))
        self.assertEqual(data['pricing_policy'], 'all_in_v3')
        self.assertTrue(data['gst_included'])
        self.assertFalse(data['saved'])
        self.assertFalse(data['approved'])
        self.assertFalse(data['checkout_created'])
        self.assertFalse(data['supplier_order_created'])
        self.assertFalse(LiveAgreement.objects.exists())
        for invalid in (None, -1, '6992', 1000001, True):
            bad = {**values, 'source_monthly_cents': invalid}
            self.assertEqual(self.post('retail-price-preview', bad).status_code, 400)

    def test_preview_respects_legacy_agreements_and_is_owner_only(self):
        from django.test import override_settings
        from payments.live_models import LiveAgreement
        old = LiveAgreement.objects.create(
            user=self.customer, created_by=self.owner, label='Past synthetic',
            service_reference='synthetic-legacy-preview',
            pricing_policy='all_in_v2', source_monthly_cents=6992,
            source_setup_cents=3500, service_terms='Synthetic only')
        payload = {'agreement_id': str(old.pk), 'source_monthly_cents': 6992,
                   'source_setup_cents': 3500}
        with override_settings(KIWIKIND_ALL_IN_RETAIL_ENABLED=True):
            res = self.post('retail-price-preview', payload)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['pricing_policy'], 'all_in_v2')
        self.assertEqual(res.json()['monthly_cents'], 8662)
        self.assertEqual(self.post('retail-price-preview',
            {**payload, 'agreement_id': 'invalid'}).status_code, 400)
        visitor = Client()
        self.assertEqual(self.post('retail-price-preview', payload, visitor).status_code, 403)
        visitor.force_login(self.customer)
        self.assertEqual(self.post('retail-price-preview', payload, visitor).status_code, 403)
        self.assertEqual(LiveAgreement.objects.count(), 1)

    def test_readonly_ledgers_unknown_models_and_csrf(self):
        self.assertEqual(self.client.get('/api/owner/operations/auth.User').status_code,404)
        self.assertEqual(self.post('operations/audit/new',{'values':{}}).status_code,405)
        c=Client(enforce_csrf_checks=True);owner_fixture(c,self.owner)
        self.assertEqual(self.post(f'tickets/{self.ticket.pk}/reply',{'body':'x','submission_key':str(uuid.uuid4())},c).status_code,403)
