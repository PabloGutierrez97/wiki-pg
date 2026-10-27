"""Datos derivados del perfil para la página «Sobre mí».

Los campos de experiencia y formación son texto libre. Si cada línea empieza
por un año o un periodo («2021 – hoy  Responsable de Sistemas | Texco»), se
muestran como línea de tiempo; si no, se respeta el texto tal cual.
"""
import re

from django.utils import timezone

_FIN_ABIERTO = ('hoy', 'actualidad', 'presente', 'ahora', 'actual')
_RE_LINEA = re.compile(
    r'^\s*(?P<ini>(?:19|20)\d{2})'
    r'(?:\s*[-–—/]\s*(?P<fin>(?:19|20)\d{2}|' + '|'.join(_FIN_ABIERTO) + r'))?'
    r'\s*[:|,.\-–—]?\s+(?P<resto>\S.*)$', re.I)
_RE_ANIO = re.compile(r'\b(19[89]\d|20\d{2})\b')


def linea_de_tiempo(texto):
    """[{periodo, actual, titulo, detalle}] o None si el texto no tiene ese formato."""
    lineas = [l.strip() for l in (texto or '').splitlines() if l.strip()]
    if not lineas:
        return None
    entradas = []
    for linea in lineas:
        m = _RE_LINEA.match(linea)
        if not m:
            return None
        fin = (m.group('fin') or '').lower()
        actual = fin in _FIN_ABIERTO
        if not fin:
            periodo = m.group('ini')
        else:
            periodo = '%s – %s' % (m.group('ini'), 'hoy' if actual else fin)
        resto = m.group('resto').strip()
        if '|' in resto:
            titulo, detalle = [p.strip() for p in resto.split('|', 1)]
        elif ', ' in resto:
            titulo, detalle = [p.strip() for p in resto.split(', ', 1)]
        else:
            titulo, detalle = resto, ''
        entradas.append({'periodo': periodo, 'actual': actual, 'titulo': titulo, 'detalle': detalle})
    return entradas


def en_sistemas_desde(experiencia):
    """(año, años de experiencia) a partir del año más antiguo citado, o (None, None)."""
    anios = [int(a) for a in _RE_ANIO.findall(experiencia or '')]
    hoy = timezone.localdate().year
    anios = [a for a in anios if a <= hoy]
    if not anios:
        return None, None
    desde = min(anios)
    return desde, max(0, hoy - desde)


def stack_en_listas(stack):
    """{'sistemas': 'Windows, Linux'} -> [('Sistemas', ['Windows', 'Linux'])]."""
    resultado = []
    for area, valor in (stack or {}).items():
        if isinstance(valor, (list, tuple)):
            items = [str(v).strip() for v in valor if str(v).strip()]
        else:
            items = [v.strip() for v in str(valor).split(',') if v.strip()]
        if items:
            nombre = str(area).strip()
            resultado.append((nombre[:1].upper() + nombre[1:], items))
    return resultado


def certificaciones(texto):
    return [c.strip() for c in re.split(r'[,\n]', texto or '') if c.strip()]
