from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class TwoFactorRequiredMiddleware:
    """El staff sin 2FA verificado que intenta entrar al admin va a configurarlo."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if (user.is_authenticated and user.is_staff
                and request.path.startswith('/' + settings.ADMIN_URL)
                and not getattr(user, 'is_verified', lambda: False)()):
            return redirect(reverse('two_factor:setup'))
        return self.get_response(request)
