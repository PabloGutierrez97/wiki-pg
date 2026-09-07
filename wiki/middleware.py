from django.shortcuts import redirect
from django.urls import reverse

class TwoFactorRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.user.is_staff:
            setup_url = reverse('two_factor:setup')
            allowed_urls = [
                setup_url,
                '/account/',
                '/static/',
                '/media/',
                '/linkedin/',
            ]
            
            is_verified = request.user.is_verified() if hasattr(request.user, 'is_verified') else False
            
            # Solo forzar 2FA si intenta acceder al admin
            if not is_verified and request.path.startswith('/termistawk/'):
                return redirect(setup_url)
        
        return self.get_response(request)
