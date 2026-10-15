"""Utilidades de seguridad compartidas por toda la wiki.

- client_ip(): la IP real del visitante detrás de Cloudflare + nginx.
- excede_limite(): contador atómico en Redis (compartido entre workers).
- Plazas de la IA: limitan cuántas respuestas genera Ollama a la vez, en
  total y por visitante, para que la IA nunca pueda tumbar el resto del sitio.
- staff_verificado: protege vistas internas (LinkedIn, subidas del editor).
"""
import functools
import ipaddress
import uuid

from django.conf import settings
from django.core.cache import cache
from django.http import Http404


def _ip_valida(valor):
    try:
        return str(ipaddress.ip_address((valor or '').strip()))
    except ValueError:
        return None


def client_ip(request):
    """IP real del visitante.

    nginx resuelve la IP de Cloudflare (real_ip_header CF-Connecting-IP, solo
    confiando en 127.0.0.1) y la pasa en X-Real-IP, sobrescribiendo cualquier
    X-Real-IP que envíe el cliente. Es la única cabecera fiable; X-Forwarded-For
    y CF-Connecting-IP se pueden falsificar si alguien llega sin pasar por nginx.
    """
    for clave in ('HTTP_X_REAL_IP', 'REMOTE_ADDR'):
        ip = _ip_valida(request.META.get(clave))
        if ip:
            return ip
    return '0.0.0.0'


def excede_limite(clave, limite, ventana):
    """Suma un uso a `clave` y dice si se ha pasado de `limite` en `ventana` segundos.

    Atómico con Redis (add + incr). Si la caché falla no bloquea a nadie: el
    límite de concurrencia de la IA sí falla cerrado, ver reservar_plaza_ia().
    """
    clave = 'rl:' + clave
    try:
        cache.add(clave, 0, ventana)
        usos = cache.incr(clave)
    except ValueError:
        # La clave caducó entre add() e incr(): empieza una ventana nueva.
        cache.set(clave, 1, ventana)
        usos = 1
    except Exception:
        return False
    return usos > limite


# ---------------------------------------------------------------- IA ----

# Si un worker muriera sin liberar su plaza, caduca sola tras este tiempo.
# Es igual al --timeout de gunicorn: ninguna respuesta puede durar más.
PLAZA_TTL = 120


class Plaza:
    """Una reserva en Redis que se libera una sola vez, pase lo que pase."""

    def __init__(self, clave, token):
        self.clave = clave
        self.token = token
        self.liberada = False

    def liberar(self):
        if self.liberada:
            return
        self.liberada = True
        try:
            if cache.get(self.clave) == self.token:
                cache.delete(self.clave)
        except Exception:
            pass


def _reservar(clave):
    token = uuid.uuid4().hex
    try:
        if cache.add(clave, token, PLAZA_TTL):
            return Plaza(clave, token)
    except Exception:
        pass
    return None


def reservar_plaza_ia():
    """Reserva una de las AI_MAX_CONCURRENT plazas globales, o None si están todas ocupadas.

    Falla cerrado: si Redis no responde, no hay plaza y la IA contesta que está
    ocupada en vez de quedarse sin límite.
    """
    total = max(1, int(getattr(settings, 'AI_MAX_CONCURRENT', 2)))
    for i in range(total):
        plaza = _reservar('ai:plaza:%d' % i)
        if plaza:
            return plaza
    return None


def reservar_turno_ip(ip):
    """Una sola pregunta a la vez por visitante (aunque abra muchas pestañas)."""
    return _reservar('ai:ip:' + ip)


class RespuestaLiberable:
    """Envuelve el generador del streaming para liberar las plazas al terminar.

    Django llama a close() siempre, también si el visitante cierra la pestaña
    antes de recibir el primer byte; un generador que no ha empezado no
    ejecutaría su `finally`, por eso la liberación va aquí.
    """

    def __init__(self, generador, *plazas):
        self._generador = generador
        self._plazas = [p for p in plazas if p]

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return next(self._generador)
        except BaseException:
            self.close()
            raise

    def close(self):
        try:
            self._generador.close()
        finally:
            for plaza in self._plazas:
                plaza.liberar()


# ------------------------------------------------------------- vistas ----

def staff_verificado(vista):
    """Solo staff con la sesión verificada por 2FA. Al resto se le responde 404.

    El 404 (en vez de redirigir al login) no revela que la ruta existe.
    """
    @functools.wraps(vista)
    def envoltura(request, *args, **kwargs):
        usuario = request.user
        verificado = getattr(usuario, 'is_verified', lambda: False)()
        if not (usuario.is_authenticated and usuario.is_active and usuario.is_staff and verificado):
            raise Http404()
        return vista(request, *args, **kwargs)
    return envoltura
