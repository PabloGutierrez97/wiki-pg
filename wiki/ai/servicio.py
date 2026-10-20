"""Flujo completo de una pregunta a la IA.

Puertas, de la más barata a la más cara:
  1. ritmo por visitante (5/min, 30/h), también para las respuestas fijas;
  2. respuestas fijas, preguntas fuera de tema y respuestas ya cacheadas
     (no tocan Ollama);
  3. una sola pregunta en curso por visitante, aunque abra muchas pestañas;
  4. una de las AI_MAX_CONCURRENT plazas globales: si están llenas se avisa al
     momento en vez de hacer cola, así la IA nunca deja sin workers al resto
     de la web.

`preguntar()` devuelve un texto (respuesta inmediata) o una RespuestaLiberable
que va generando la respuesta y libera las plazas al terminar o al cerrarse.
"""
import hashlib
import logging
import re
import time

from ..models import Profile
from ..security import RespuestaLiberable, excede_limite, reservar_plaza_ia, reservar_turno_ip
from ..utils import cache_get, cache_set, normalizar
from . import filtros, mensajes, ollama, prompts

ASK_POR_MINUTO = 5
ASK_POR_HORA = 30
MAX_PREGUNTA = 300
# Respuestas idénticas se sirven desde caché durante este tiempo.
CACHE_RESPUESTA = 15 * 60
# Cambiar la versión invalida todas las respuestas guardadas (p. ej. al cambiar el prompt).
VERSION_CACHE = 'v5'

# Registro de preguntas (sin IP) para poder revisar qué contesta la IA: journalctl -u wiki_pg | grep ' ia '
log = logging.getLogger('wiki.ia')


def clave_respuesta(pregunta):
    norm = ' '.join(normalizar(pregunta).split())
    return 'ai:resp:%s:%s' % (VERSION_CACHE, hashlib.sha256(norm.encode('utf-8')).hexdigest())


def trozos_con_pausa(texto):
    """Escribe un texto ya hecho poco a poco (efecto terminal), en ~1 s como máximo."""
    trozos = re.findall(r'\S+\s*', texto)
    pausa = min(0.03, 1.0 / max(1, len(trozos)))
    for trozo in trozos:
        yield trozo
        time.sleep(pausa)


def preguntar(pregunta, ip):
    pregunta = (pregunta or '').strip()
    if not pregunta:
        return mensajes.USO
    if len(pregunta) > MAX_PREGUNTA:
        return mensajes.DEMASIADO_LARGA

    if (excede_limite('ask:min:' + ip, ASK_POR_MINUTO, 60)
            or excede_limite('ask:hora:' + ip, ASK_POR_HORA, 3600)):
        return mensajes.RAPIDO
    no_permitida = filtros.peticion_no_permitida(pregunta)
    if no_permitida:
        log.info('ia %s %r', no_permitida, pregunta[:200])
        return mensajes.ATAQUE if no_permitida == 'ataque' else mensajes.MANIPULACION
    fija = filtros.respuesta_fija(pregunta)
    if fija:
        return fija
    if filtros.esta_fuera_de_tema(pregunta):
        log.info('ia fuera_de_tema %r', pregunta[:200])
        return mensajes.FUERA_DE_TEMA
    clave = clave_respuesta(pregunta)
    guardada = cache_get(clave)
    if guardada:
        return guardada

    turno = reservar_turno_ip(ip)
    if not turno:
        return mensajes.EN_CURSO
    plaza = reservar_plaza_ia()
    if not plaza:
        turno.liberar()
        return mensajes.OCUPADA
    return RespuestaLiberable(_generar(pregunta, clave, plaza, turno), plaza, turno)


def _presentacion(pregunta):
    """Presentación de Pablo: la redacta el modelo y, si no vale, se usa la fija."""
    perfil = Profile.get()
    try:
        texto = ollama.generar(pregunta, prompts.presentacion(perfil))
    except Exception:
        texto = ''
    if filtros.presentacion_valida(texto):
        return mensajes.PREFIJO + filtros.quitar_enlaces(texto) + mensajes.PISTA_PERFIL
    return mensajes.presentacion_fija(perfil)


def _generar(pregunta, clave, plaza, turno):
    enviado = []
    completa = False
    try:
        if filtros.es_pregunta_de_identidad(pregunta):
            texto = _presentacion(pregunta)
            cache_set(clave, texto, CACHE_RESPUESTA)
            yield from trozos_con_pausa(texto)
            return

        system, enlazado = prompts.contexto_general(pregunta)
        if not filtros.es_de_la_wiki(pregunta, enlazado):
            log.info('ia fuera_de_tema %r', pregunta[:200])
            cache_set(clave, mensajes.FUERA_DE_TEMA, CACHE_RESPUESTA)
            yield mensajes.FUERA_DE_TEMA
            return
        log.info('ia modelo %r', pregunta[:200])
        tokens = ollama.generar_stream(pregunta, system)
        while True:
            try:
                token = next(tokens)
            except StopIteration as fin:
                completa = bool(fin.value)
                break
            if not enviado:
                token = mensajes.PREFIJO + token
            enviado.append(token)
            yield token

        if not enviado:
            completa = False
            yield mensajes.PREFIJO + mensajes.SIN_RESPUESTA
        elif enlazado:
            enlace = mensajes.leer(enlazado.slug)
            enviado.append(enlace)
            yield enlace
    except Exception:
        completa = False
        yield "\n" + mensajes.NO_DISPONIBLE
    finally:
        plaza.liberar()
        turno.liberar()
    if completa:
        cache_set(clave, ''.join(enviado), CACHE_RESPUESTA)
