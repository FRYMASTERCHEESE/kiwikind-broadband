from django.conf import settings
from django.http import JsonResponse
from .security import limited

class SafetyMiddleware:
    def __init__(self, get_response): self.get_response = get_response
    def __call__(self, request):
        if request.path.startswith('/admin/'):
            if not settings.ADMIN_ENABLED:
                return JsonResponse({'error':'Administration disabled'}, status=404)
            if request.method == 'POST' and request.path == '/admin/login/' and limited(request,'admin'):
                return JsonResponse({'error':'Try again later'},status=429)
        response = self.get_response(request)
        response['Content-Security-Policy'] = ("default-src 'self'; script-src 'self' https://accounts.google.com; "
            "style-src 'self' https://accounts.google.com; img-src 'self' data: https://*.googleusercontent.com https://accounts.google.com; "
            "connect-src 'self' https://accounts.google.com; frame-src https://accounts.google.com; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        response['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        if request.path.startswith('/api/'):
            response['Cache-Control'] = 'no-store'
        return response
