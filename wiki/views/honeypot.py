from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from ..models import HoneypotAttempt
from ..security import client_ip, excede_limite, ip_cuota

# Topes de registro: sin ellos, un bot podría llenar la base de datos.
REGISTROS_POR_IP_HORA = 20
REGISTROS_TOTALES_HORA = 1000


@csrf_exempt
def honeypot_admin(request):
    """Falso login de /admin/: siempre falla y apunta quién lo intenta."""
    ip = client_ip(request)
    if (request.method == 'POST'
            and not excede_limite('hp:ip:' + ip_cuota(ip), REGISTROS_POR_IP_HORA, 3600)
            and not excede_limite('hp:total', REGISTROS_TOTALES_HORA, 3600)):
        HoneypotAttempt.objects.create(
            ip=ip,
            username=request.POST.get('username', '')[:200],
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:1000],
            path=request.path,
        )
    return render(request, 'wiki/honeypot_login.html', {'error': request.method == 'POST'})
