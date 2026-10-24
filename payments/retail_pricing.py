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


def order_quote(monthly_ex_gst_cents, setup_ex_gst_cents, *, include_processing=False,
                monthly_price_increase_cents=0, source_prices_only=False):
    """GST first, then add the owner's already-GST-inclusive additions once.

    First invoice is the sum of the two displayed charge lines so rounding
    cannot make checkout differ by one cent from the approved quote.
    Missing setup information yields no payable quote.
    """
    if type(source_prices_only) is not bool:
        raise ValueError('Invalid supplier pricing option')
    if source_prices_only:
        monthly = _including_gst(monthly_ex_gst_cents)
        setup = None if setup_ex_gst_cents is None else _including_gst(setup_ex_gst_cents)
        return {'currency': 'NZD', 'gst_included': True,
            'monthly_cents': monthly, 'setup_cents': setup,
            'monthly_addition_cents': 0, 'setup_addition_cents': 0,
            'first_invoice_cents': None if setup is None else monthly + setup,
            'quote_complete': setup is not None}
    monthly = _including_gst(monthly_ex_gst_cents) + 300
    setup = (None if setup_ex_gst_cents is None
             else _including_gst(setup_ex_gst_cents) + 1000)
    if type(include_processing) is not bool:
        raise ValueError('Invalid retail pricing option')
    # Increase the complete advertised monthly retail amount by exactly $4,
    # never the supplier wholesale amount, and never the once-only setup.
    # Restrict to explicitly supported pricing-policy versions.
    if type(monthly_price_increase_cents) is not int or monthly_price_increase_cents not in (0, 400):
        raise ValueError('Invalid retail monthly price policy')
    if monthly_price_increase_cents and not include_processing:
        raise ValueError('Monthly increase requires an all-inclusive retail price')
    if include_processing:
        from .all_in_prices import all_in_amount
        initial_monthly = monthly
        monthly = all_in_amount(initial_monthly)
        if setup is not None:
            setup = all_in_amount(initial_monthly + setup) - monthly
    monthly += monthly_price_increase_cents
    if monthly > 1200000 or (setup is not None and not 0 <= setup <= 1200000):
        raise ValueError('Retail quote exceeds allowed limits')
    return {
        'currency': 'NZD', 'gst_included': True,
        'monthly_cents': monthly, 'setup_cents': setup,
        'monthly_addition_cents': 300, 'setup_addition_cents': 1000,
        'first_invoice_cents': None if setup is None else monthly + setup,
        'quote_complete': setup is not None,
    }
