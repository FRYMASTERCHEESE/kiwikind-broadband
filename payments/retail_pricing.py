"""Server-side preparation for GST-inclusive quotes; no payment execution.

Inputs are the combined selected supplier charges, excluding GST. Call once
per order, after summing eligible plan/data/IP and installation selections.
Never trust browser-supplied amounts or use an unverified setup cost as zero.
"""
from decimal import Decimal, ROUND_HALF_UP


def _cents(value):
    if type(value) is not int or not 0 <= value <= 1000000:
        raise ValueError('Expected non-negative integer cents within quote limits')
    return value


def _including_gst(value):
    return int((Decimal(_cents(value)) * Decimal('1.15')).quantize(
        Decimal('1'), rounding=ROUND_HALF_UP))


def order_quote(monthly_ex_gst_cents, setup_ex_gst_cents):
    """GST first, then add the owner's already-GST-inclusive additions once.

    First invoice is the sum of the two displayed charge lines so rounding
    cannot make checkout differ by one cent from the approved quote.
    Missing setup information yields no payable quote.
    """
    monthly = _including_gst(monthly_ex_gst_cents) + 300
    setup = (None if setup_ex_gst_cents is None
             else _including_gst(setup_ex_gst_cents) + 1000)
    return {
        'currency': 'NZD', 'gst_included': True,
        'monthly_cents': monthly, 'setup_cents': setup,
        'monthly_addition_cents': 300, 'setup_addition_cents': 1000,
        'first_invoice_cents': None if setup is None else monthly + setup,
        'quote_complete': setup is not None,
    }
