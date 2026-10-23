"""Utilidades pequeñas compartidas por toda la app."""
import unicodedata

from django.core.cache import cache


def normalizar(texto):
    """Minúsculas y sin tildes: 'Cómo' -> 'como'. Para comparar texto libre.

    NFKD convierte también letras de ancho completo ('ｒｅｃｅｔａ') y se quitan
    los caracteres invisibles (Cf, p. ej. espacios de ancho cero) que se usan
    para colar palabras partidas por los filtros.
    """
    return ''.join(ch for ch in unicodedata.normalize('NFKD', (texto or '').lower())
                   if unicodedata.category(ch) not in ('Mn', 'Cf'))


def cache_get(clave):
    """Lee de la caché sin romper la petición si Redis no responde."""
    try:
        return cache.get(clave)
    except Exception:
        return None


def cache_set(clave, valor, segundos):
    try:
        cache.set(clave, valor, segundos)
    except Exception:
        pass


def cacheado(clave, calcular, segundos):
    """Devuelve el valor cacheado o lo calcula y lo guarda.

    Si Redis falla se calcula igualmente: la caché nunca tumba una página.
    """
    try:
        valor = cache.get(clave)
    except Exception:
        return calcular()
    if valor is None:
        valor = calcular()
        cache_set(clave, valor, segundos)
    return valor
