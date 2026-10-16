import hashlib
import hmac
import time
from django.conf import settings
from django.db import transaction
from .models import RateBucket

def limited(request, scope, limit=10, seconds=900):
    # Use immediate peer only. Deployment proxy must enforce its own client-IP limit.
    identity = request.META.get('REMOTE_ADDR', '')
    key = hmac.new(settings.SECRET_KEY.encode(), f'{scope}:{identity}'.encode(), hashlib.sha256).hexdigest()
    window = int(time.time()) // seconds
    with transaction.atomic():
        bucket, _ = RateBucket.objects.get_or_create(key=key, defaults={'window':window})
        if bucket.window != window:
            bucket.window, bucket.count = window, 0
        bucket.count += 1
        bucket.save()
        return bucket.count > limit
