"""Credentialed CORS for one exact frontend origin, with Django CSRF intact."""
from django.conf import settings
from django.http import JsonResponse, HttpResponseRedirect
from django.utils.cache import patch_vary_headers


class PagesMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        api = request.path.startswith('/api/')
        origin = request.headers.get('Origin')
        allowed = settings.PAGES_ENABLED and origin == settings.PAGES_ORIGIN
        if api and origin and not allowed and origin != settings.PUBLIC_ORIGIN:
            return JsonResponse({'error': 'Origin not allowed'}, status=403)
        if api and request.method == 'OPTIONS' and origin:
            headers = {h.strip().lower() for h in request.headers.get('Access-Control-Request-Headers', '').split(',') if h.strip()}
            if not allowed or request.headers.get('Access-Control-Request-Method') not in ('GET', 'POST') or not headers <= {'content-type', 'x-csrftoken'}:
                return JsonResponse({'error': 'Preflight denied'}, status=403)
            response = JsonResponse({})
            response['Access-Control-Allow-Methods'] = 'GET, POST'
            response['Access-Control-Allow-Headers'] = 'Content-Type, X-CSRFToken'
            response['Access-Control-Max-Age'] = '300'
        elif settings.PAGES_API_ONLY and not api and request.path != '/healthz':
            if request.method in ('GET', 'HEAD'):
                target = 'owner.html' if request.path.startswith('/admin') else 'account.html'
                response = HttpResponseRedirect(settings.PAGES_URL + target)
            else:
                response = JsonResponse({'error': 'Use the GitHub Pages application'}, status=404)
        else:
            response = self.get_response(request)
        if api:
            patch_vary_headers(response, ['Origin'])
            response['Cache-Control'] = 'no-store'
            # Override any public endpoint wildcard before credentials are enabled.
            if 'Access-Control-Allow-Origin' in response:
                del response['Access-Control-Allow-Origin']
            if allowed:
                response['Access-Control-Allow-Origin'] = settings.PAGES_ORIGIN
                response['Access-Control-Allow-Credentials'] = 'true'
        return response
