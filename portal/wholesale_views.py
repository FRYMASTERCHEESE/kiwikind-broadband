from django.http import JsonResponse
from .models import WholesaleOrder, WholesaleFault
from .views import endpoint


@endpoint(['GET'], authenticated=True)
def connection_progress(request):
    """The same private, read-only projection for website and Android.

    Never expose draft pricing, supplier references, addresses or internal notes.
    Practice cases are excluded even when the caller is an operator.
    """
    orders = WholesaleOrder.objects.filter(rehearsal=False, customer_request__user=request.user).select_related('customer_request').order_by('-updated_at')[:100]
    faults = WholesaleFault.objects.filter(rehearsal=False, ticket__user=request.user).order_by('-updated_at')[:100]
    return JsonResponse({
        'mode': 'prelaunch', 'live_orders_enabled': False, 'payments_enabled': False,
        'availability': 'unverified',
        'message': 'KiwiKind is preparing for launch. No broadband service, confirmed price or installation date is offered.',
        'orders': [{'request_id': str(case.customer_request_id),
                    'stage': 'cancelled' if case.customer_request.status == 'cancelled' else case.state,
                    'updated_at': case.updated_at.isoformat()} for case in orders],
        'faults': [{'ticket_id': str(case.ticket_id), 'stage': case.state, 'updated_at': case.updated_at.isoformat()} for case in faults],
    })
