"""Cliente mínimo de la API de Ollama (sin dependencias externas)."""
import json
import time
import urllib.request

from django.conf import settings

TIMEOUT_RESPUESTA = 60
OPCIONES = {"temperature": 0.2, "top_p": 0.9, "repeat_penalty": 1.1, "num_predict": 450}


def _url(ruta):
    return settings.OLLAMA_URL.rstrip('/') + ruta


def _peticion(ruta, cuerpo):
    return urllib.request.Request(_url(ruta), data=json.dumps(cuerpo).encode('utf-8'),
                                  headers={'Content-Type': 'application/json'})


def _cuerpo_generar(pregunta, system, stream):
    return {
        "model": settings.OLLAMA_MODEL,
        "prompt": pregunta,
        "system": system,
        "stream": stream,
        "keep_alive": "30m",
        "options": OPCIONES,
    }


def generar(pregunta, system, timeout=TIMEOUT_RESPUESTA):
    """Respuesta completa del modelo. Lanza excepción si Ollama falla."""
    req = _peticion('/api/generate', _cuerpo_generar(pregunta, system, False))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return (json.loads(resp.read().decode('utf-8')).get('response') or '').strip()


def generar_stream(pregunta, system, timeout=TIMEOUT_RESPUESTA):
    """Genera los trozos de texto según llegan. Devuelve True al terminar si el modelo acabó."""
    req = _peticion('/api/generate', _cuerpo_generar(pregunta, system, True))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for linea in resp:
            linea = linea.strip()
            if not linea:
                continue
            try:
                obj = json.loads(linea.decode('utf-8'))
            except ValueError:
                continue
            if obj.get('response'):
                yield obj['response']
            if obj.get('done'):
                return True
    return False


def embedding(texto, timeout=30, intentos=2):
    """Vector del texto con el modelo de embeddings, o None si Ollama no responde.

    Para preguntas en vivo se llama con timeout corto y un solo intento.
    """
    cuerpo = {"model": settings.OLLAMA_EMBED_MODEL, "prompt": (texto or '')[:3000], "keep_alive": "5m"}
    for intento in range(intentos):
        try:
            with urllib.request.urlopen(_peticion('/api/embeddings', cuerpo), timeout=timeout) as resp:
                emb = json.loads(resp.read().decode('utf-8')).get('embedding')
            if emb:
                return emb
        except Exception:
            pass
        if intento + 1 < intentos:
            time.sleep(0.8)
    return None
