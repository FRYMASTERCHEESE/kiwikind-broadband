"""Estimate merchant collection costs for all-in NZD advertised prices.

Standard NZ domestic card 2.65% + 30c, Stripe Billing 0.7%.
Prices must be displayed in full before customer consent.
"""
CARD_BPS = 265
BILLING_BPS = 70
FIXED_CENTS = 30

def estimated_fees(amount):
    return FIXED_CENTS + (amount * CARD_BPS + 9999) // 10000 + (amount * BILLING_BPS + 9999) // 10000

def all_in_amount(net_target):
    if type(net_target) is not int or net_target < 0:
        raise ValueError("Invalid price")
    lo = net_target
    hi = (net_target + FIXED_CENTS) * 10000 // 9665 + 8
    while lo < hi:
        mid = (lo + hi) // 2
        if mid - estimated_fees(mid) >= net_target:
            hi = mid
        else:
            lo = mid + 1
    return lo
