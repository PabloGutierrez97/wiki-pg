"""Endpoints HTTP del terminal.

- /terminal/cmd/  comandos (JSON in / JSON out).
- /terminal/ask/  preguntas a la IA con la respuesta en streaming.

Los dos son POST sin CSRF (el widget no envía token y no modifican datos);
el abuso se frena con límites por IP y con las plazas de la IA.
"""
import json

from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from ..ai import mensajes, servicio
from ..security import client_ip_cuota, excede_limite
from . import comandos

# Comandos baratos (ls, cat, tree...), pero sin límite se pueden encadenar.
CMD_POR_MINUTO = 60
# Una pregunta de 300 caracteres cabe de sobra en 4 KB.
MAX_BODY = 4096
MAX_COMANDO = 400
RECHAZOS = {mensajes.RAPIDO, mensajes.EN_CURSO, mensajes.OCUPADA, mensajes.USO,
            mensajes.DEMASIADO_LARGA, mensajes.FUERA_DE_TEMA, mensajes.MANIPULACION, mensajes.ATAQUE,
            mensajes.CONTROL, mensajes.SOBRE_PABLO}


def _leer_json(request):
    """Cuerpo JSON acotado a MAX_BODY, o None si no es válido."""
    try:
        longitud = int(request.META.get('CONTENT_LENGTH') or 0)
    except ValueError:
        return None
    if longitud > MAX_BODY:
        return None
    try:
        data = json.loads(request.body or b'{}')
    except (ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def _streaming(contenido):
    resp = StreamingHttpResponse(contenido, content_type='text/plain; charset=utf-8')
    resp['X-Accel-Buffering'] = 'no'   # que nginx no acumule la respuesta
    resp['Cache-Control'] = 'no-cache'
    return resp


@csrf_exempt
@require_POST
def terminal_command(request):
    data = _leer_json(request)
    if data is None:
        return JsonResponse({'output': 'Error en la peticion.'}, status=400)
    raw = (data.get('command') or '').strip()[:MAX_COMANDO]
    if not raw:
        return JsonResponse({'output': ''})

    ip = client_ip_cuota(request)
    if excede_limite('cmd:min:' + ip, CMD_POR_MINUTO, 60):
        return JsonResponse({'output': mensajes.RAPIDO}, status=429)

    partes = raw.split(maxsplit=1)
    nombre = partes[0].lower()
    arg = partes[1].strip() if len(partes) > 1 else ''

    if nombre == 'clear':
        return JsonResponse({'output': '', 'clear': True})
    if nombre == 'ask':
        respuesta = servicio.preguntar(arg, ip)
        salida = respuesta if isinstance(respuesta, str) else ''.join(respuesta).strip()
        return JsonResponse({'output': salida})

    salida = comandos.ejecutar(nombre, arg)
    if salida is None:
        salida = f"comando no encontrado: [[amarillo]]{nombre}[[/]]. Escribe [[verde]]help[[/]]."
    return JsonResponse({'output': salida})


@csrf_exempt
@require_POST
def terminal_ask(request):
    data = _leer_json(request)
    if data is None:
        return _streaming(["[[rojo]]Peticion no valida.[[/]]"])
    pregunta = (data.get('command') or '').strip()
    if pregunta.lower().startswith('ask'):
        pregunta = pregunta[3:]
    respuesta = servicio.preguntar(pregunta, client_ip_cuota(request))
    if isinstance(respuesta, str):
        # Los avisos (límite, ocupada, fuera de tema...) salen de golpe para no
        # retener un hilo de gunicorn; las respuestas normales, con efecto de escritura.
        respuesta = [respuesta] if respuesta in RECHAZOS else servicio.trozos_con_pausa(respuesta)
    return _streaming(respuesta)
