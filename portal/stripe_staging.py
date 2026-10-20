"""Sandbox only. Live keys are rejected, regardless of deployment flags."""
import os
import stripe
from urllib.parse import urlsplit
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse
from .models import Invoice, StripePayment
from .views import endpoint

def configured():
    return (os.getenv('STRIPE_TEST_CHECKOUT_ENABLED') == '1'
        and os.getenv('STRIPE_TEST_PRICE_REVIEWED') == '1'
        and os.getenv('STRIPE_TEST_SECRET_KEY','').startswith('sk_test_')
        and os.getenv('STRIPE_TEST_WEBHOOK_SECRET','').startswith('whsec_'))

def gateway_options():
    return {'api_key':os.environ['STRIPE_TEST_SECRET_KEY']}

def plain(value):
    return value if isinstance(value,dict) else value.to_dict()

def safe_url(url):
    parsed=urlsplit(url or '')
    return parsed.scheme=='https' and parsed.netloc=='checkout.stripe.com' and not parsed.username

@endpoint(['POST'],True,throttle='checkout')
def checkout(request):
    if not configured(): return JsonResponse({'error':'Test checkout is disabled'},status=503)
    if not settings.PUBLIC_ORIGIN.startswith('https://') and not settings.DEBUG:
        return JsonResponse({'error':'HTTPS required'},status=503)
    initial=Invoice.objects.filter(pk=request.data.get('invoice_id'),user=request.user,status='unpaid',currency='NZD',sandbox=True).first()
    if initial is None:return JsonResponse({'error':'Synthetic unpaid invoice not found'},status=404)
    # Persist the attempt before any provider call, including a process crash. Stripe retry
    # keys have finite retention: uncertain attempts cannot be restarted after 23 hours.
    StripePayment.objects.get_or_create(invoice=initial,defaults={'amount_cents':initial.amount_cents})
    with transaction.atomic():
        invoice=Invoice.objects.select_for_update().filter(pk=request.data.get('invoice_id'),user=request.user,status='unpaid',currency='NZD',sandbox=True).first()
        if invoice is None: return JsonResponse({'error':'Synthetic unpaid invoice not found'},status=404)
        if not 50 <= invoice.amount_cents <= 1000000:
            return JsonResponse({'error':'Invoice requires review'},status=400)
        payment=StripePayment.objects.select_for_update().get(invoice=invoice)
        if not payment.session_id and timezone.now()-payment.created_at > timedelta(hours=23):
            return JsonResponse({'error':'Old attempt requires provider reconciliation'},status=409)
        if payment.amount_cents != invoice.amount_cents or payment.paid:
            return JsonResponse({'error':'Invoice changed or already paid'},status=409)
        # Never create a second session on expiry/retry. An operator must reconcile first.
        try:
            if payment.session_id:
                result=stripe.checkout.Session.retrieve(payment.session_id,**gateway_options())
                result=plain(result)
                if result.get('status') != 'open':
                    return JsonResponse({'error':'Checkout requires reconciliation'},status=409)
            else:
                result=stripe.checkout.Session.create(mode='payment',payment_method_types=['card'],
                    success_url=settings.PUBLIC_ORIGIN+'/?checkout=returned',cancel_url=settings.PUBLIC_ORIGIN+'/?checkout=cancelled',
                    client_reference_id=str(invoice.id),customer_email=request.user.email,
                    line_items=[{'price_data':{'currency':'nzd','unit_amount':payment.amount_cents,'product_data':{'name':'KiwiKind synthetic test invoice'}},'quantity':1}],
                    metadata={'invoice_id':str(invoice.id)},idempotency_key='kiwikind-test-invoice-'+str(invoice.id),**gateway_options())
            result=plain(result)
            if result.get('livemode') is not False or not safe_url(result.get('url')):
                return JsonResponse({'error':'Invalid test checkout response'},status=502)
            payment.session_id=result['id'];payment.save(update_fields=['session_id'])
            return JsonResponse({'url':result['url']})
        except stripe.StripeError:
            return JsonResponse({'error':'Stripe test checkout unavailable'},status=502)
