"""Contenido derivado para la portada: el «comando del día» y las etiquetas más usadas.

Todo sale de los artículos publicados y se cachea por versión del conjunto
(número de artículos + última edición), así que publicar o editar algo lo
actualiza solo.
"""
import random
import re
from collections import Counter

from django.db.models import Count, Max
from django.utils import timezone

from .models import Article
from .utils import cacheado

CACHE_PORTADA = 3600
MAX_COMANDOS = 20
LONGITUD_MIN, LONGITUD_MAX = 6, 90

_RE_BLOQUE = re.compile(r'^[ \t]*```[ \t]*([\w+#.-]*)[^\n]*\n(.*?)^[ \t]*```', re.M | re.S)

# Lenguaje del bloque -> (prompt que se muestra, lenguajes equivalentes)
PROMPTS = {
    'bash': '$', 'sh': '$', 'shell': '$', 'console': '$', 'zsh': '$', '': '$',
    'powershell': r'PS C:\>', 'ps1': r'PS C:\>', 'pwsh': r'PS C:\>',
    'cmd': r'C:\>', 'bat': r'C:\>', 'batch': r'C:\>',
    'routeros': '[admin@MikroTik] >', 'mikrotik': '[admin@MikroTik] >',
}
_COMENTARIO = ('#', '//', 'REM ', 'rem ', '::', ';')
# Comandos demasiado triviales para destacarlos.
_TRIVIALES = {'echo', 'cd', 'ls', 'clear', 'exit', 'pwd', 'cls', 'su', 'whoami'}
# Nunca se destaca una línea que pueda contener credenciales.
_SENSIBLE = re.compile(r'pass(word)?\s*[=:]|token|secret|api[_-]?key|BEGIN [A-Z ]*PRIVATE', re.I)


def version_publicados():
    """Cambia cada vez que se publica, despublica o edita un artículo (una sola consulta)."""
    datos = Article.objects.publicados().aggregate(n=Count('id'), ultima=Max('updated_at'))
    return '%s:%s' % (datos['n'], datos['ultima'].timestamp() if datos['ultima'] else 0)


def _primer_comando(texto):
    for linea in texto.splitlines():
        linea = linea.strip()
        for prompt in ('$ ', 'PS> '):   # '# ' no: en bash es un comentario
            if linea.startswith(prompt) and len(linea) > len(prompt) + 2:
                linea = linea[len(prompt):].strip()
                break
        if not linea or linea.startswith(_COMENTARIO) or linea.endswith(('\\', '`', '^')):
            continue
        if not (LONGITUD_MIN <= len(linea) <= LONGITUD_MAX) or _SENSIBLE.search(linea):
            continue
        if not re.match(r'^[\w./~\[-]', linea) or linea.split()[0].lower() in _TRIVIALES:
            continue
        return linea
    return None


def _comandos():
    lista = []
    for art in Article.objects.publicados().only('title', 'slug', 'content').order_by('-created_at'):
        for bloque in _RE_BLOQUE.finditer(art.content or ''):
            lenguaje = bloque.group(1).lower()
            if lenguaje not in PROMPTS:
                continue
            cmd = _primer_comando(bloque.group(2))
            if cmd:
                lista.append({'cmd': cmd, 'prompt': PROMPTS[lenguaje],
                              'lang': lenguaje or 'shell', 'titulo': art.title,
                              'url': art.get_absolute_url()})
                break   # uno por artículo, para que salgan temas variados
    return lista


def comandos_del_dia(version, hoy=None):
    """Lista de comandos con el del día primero. Vacía si ningún artículo tiene código."""
    todos = cacheado('portada:comandos:' + version, _comandos, CACHE_PORTADA)
    if not todos:
        return []
    hoy = hoy or timezone.localdate()
    orden = list(todos)
    random.Random(hoy.toordinal()).shuffle(orden)
    return orden[:MAX_COMANDOS]


def etiquetas_frecuentes(version, limite=14):
    """[(etiqueta, nº de artículos)] ordenadas por uso; solo las que aparecen en 2 o más."""
    def _calcular():
        cuenta = Counter()
        for tags in Article.objects.publicados().values_list('tags', flat=True):
            vistas = {t.strip().lower() for t in (tags or '').split(',') if t.strip()}
            cuenta.update(vistas)
        return [(t, n) for t, n in cuenta.most_common(limite) if n >= 2]
    return cacheado('portada:etiquetas:%s:%d' % (version, limite), _calcular, CACHE_PORTADA)
