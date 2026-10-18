"""Decisiones que se toman sin llamar al modelo.

Un modelo de 3B no respeta de forma fiable un "no contestes a esto" en el
prompt: si se le pide un artículo o una receta, lo escribe y se inventa citas
de Pablo. Por eso estos casos se resuelven aquí, sin gastar una plaza de la IA.
"""
import re

from ..models import Article
from ..utils import normalizar
from . import mensajes

# --------------------------------------------------- preguntas sobre Pablo --

_IDENTIDAD = (
    'quien es pablo', 'sobre pablo', 'hablame de pablo', 'a que se dedica pablo', 'que hace pablo',
    'de quien es la wiki', 'de quien es esta wiki', 'quien hizo la wiki', 'quien hizo esta wiki',
    'quien es el autor', 'quien esta detras de la wiki', 'a que te dedicas', 'presentate',
    'hablame de ti', 'sobre ti', 'que sabes de pablo', 'que sabes sobre pablo', 'conoces a pablo',
    'informacion de pablo', 'informacion sobre pablo', 'cuentame de pablo', 'cuentame sobre pablo',
    'quien es el creador',
)


def es_pregunta_de_identidad(pregunta):
    q = normalizar(pregunta)
    return any(k in q for k in _IDENTIDAD)


# -------------------------------------------------------- respuestas fijas --

_ULTIMO = ('ultim', 'reciente', 'last', 'latest', 'nuevo')
_ARTICULO = ('articulo', 'post', 'entrada', 'publicad', 'subi')
_COMO_FUNCIONA = (
    'como funcionas', 'como trabajas', 'como estas hecha', 'como estas programad', 'como estas construid',
    'como estas basad', 'estas configurad', 'te configuraron', 'fuiste configurad', 'te programaron',
    'te han programado', 'te hicieron', 'te crearon', 'te construyeron', 'te desarrollaron', 'te montaron',
    'que modelo eres', 'que modelo usas', 'que ia eres', 'con que estas hecha', 'en que estas basad',
)
_COSENO = ('coseno', 'embedding', 'como funciona el rag', 'que es el rag', 'como encuentras los articulos',
           'como buscas los articulos', 'como recuperas')


def respuesta_fija(pregunta):
    """Respuesta sin modelo para preguntas sobre datos o sobre la propia IA, o None."""
    q = normalizar(pregunta)
    if any(k in q for k in _ULTIMO) and any(k in q for k in _ARTICULO):
        ultimo = Article.objects.publicados().order_by('-created_at').first()
        if ultimo:
            return mensajes.ultimo_articulo(ultimo)
    if any(k in q for k in _COMO_FUNCIONA):
        return mensajes.COMO_FUNCIONA
    if any(k in q for k in _COSENO):
        return mensajes.COSENO
    return None


# ------------------------------------------------------------ fuera de tema --

_FOLCLORE = ('sr ter', 'senor ter', 'termista', 'entendidur', 'noloser')

# Palabras que hacen técnica una pregunta aunque contenga otra cosa ("receta
# para desplegar con docker" sí es de la wiki). Se comparan como inicio de
# palabra, para que "digital" no cuente como "git".
_RE_TECNICA = re.compile(r'\b(' + '|'.join(re.escape(k) for k in (
    'linux', 'debian', 'ubuntu', 'windows', 'servidor', 'server', 'docker', 'contenedor', 'kubernetes', 'k8s',
    'proxmox', 'lxc', 'vm', 'maquina virtual', 'virtualiz', 'red', 'redes', 'vlan', 'dns', 'dhcp', 'ip',
    'firewall', 'vpn', 'wireguard', 'nginx', 'apache', 'ssh', 'ssl', 'tls', 'certificado', 'backup',
    'rclone', 'script', 'bash', 'python', 'powershell', 'ansible', 'terraform', 'git', 'django', 'postgres',
    'mysql', 'base de datos', 'redis', 'celery', 'cloudflare', 'despleg', 'deploy', 'devops', 'monitoriz',
    'grafana', 'zabbix', 'active directory', 'cron', 'systemd', 'raid', 'zfs', 'ollama', 'kernel', 'cluster',
)) + ')')

_CREATIVOS = (r'historia|historieta|cuento|relato|poema|poesia|cancion|receta|carta|ensayo|chiste|'
              r'novela|guion|rap|verso|redaccion|discurso|biografia')
_DET = r'(un|una|el|la|otro|otra|algun|alguna|nuevo|nueva)?\s*'

# Encargos creativos: el asistente responde preguntas, no escribe contenido.
# "dame un articulo de rclone" es legítimo (recomendar uno que existe);
# "escribe un articulo" no. Por eso articulo/post solo cuentan con verbos de escribir.
_RE_CREATIVO = re.compile(
    r'\b(escribe\w*|escribir|redacta\w*|crea|creame|genera\w*|hazme|haz|elabora\w*|'
    r'prepara\w*|inventa\w*|compon\w*)\s+(me\s+)?' + _DET + r'(articulo|post|' + _CREATIVOS + r')s?\b'
    r'|\b(dame|quiero|cuentame|dime|recitame|cantame)\s+(me\s+)?' + _DET + r'(' + _CREATIVOS + r')s?\b')
# Inventar siempre se rechaza; "imagina"/"finge" solo si no hay nada técnico
# ("imagina que se cae el servidor..." es una pregunta válida).
_RE_INVENTAR = re.compile(r'\b(inventa\w*|invent(a|e|ar)\s|haz como si|ponte en el papel)')
_RE_FICCION = re.compile(r'\b(imagina\w*|finge|fingir|supon que eres)\b')
# Temas que nunca son de la wiki.
_RE_AJENO = re.compile(
    r'\b(recetas?|cocina|cocinar|cocino|guisos?|guisar|ingredientes?|hornear|postres?|gastronom\w*|'
    r'gachas|paella|tortilla|cocido|lentejas|migas|pisto|croquetas?|gazpacho|salmorejo|'
    r'horoscopo|futbol|pelicula|famos[oa]s?)\b')


def esta_fuera_de_tema(pregunta):
    """True si la pregunta debe rechazarse sin consultar al modelo."""
    q = ' ' + ' '.join(normalizar(pregunta).split()) + ' '
    if any(k in q for k in _FOLCLORE):
        return False                    # el Sr. Ter sí puede improvisar (broma de la casa)
    if _RE_CREATIVO.search(q) or _RE_INVENTAR.search(q):
        return True
    tecnica = bool(_RE_TECNICA.search(q))
    return bool((_RE_FICCION.search(q) or _RE_AJENO.search(q)) and not tecnica)


# --------------------------------------------- respuestas del modelo inválidas --

# Si la presentación generada contiene algo de esto, no vale: se niega, habla en
# primera persona o copia las etiquetas internas del prompt.
_NEGATIVAS = ('lo siento', 'no puedo', 'no tengo informacion', 'no tengo datos', 'no conozco',
              'sin conocerla', 'informacion personal', 'perfil:', 'en perfil', 'datos:',
              'soy pablo', 'mi wiki', 'como modelo', 'como ia')


def presentacion_valida(texto):
    return len(texto) >= 40 and not any(k in normalizar(texto) for k in _NEGATIVAS)


def quitar_enlaces(texto):
    """El sistema añade su propio enlace al final: se borran los que invente el modelo."""
    lineas = [re.sub(r'/article/\S*', '', ln) for ln in texto.split('\n')
              if not re.match(r'(?i)^\s*leer\s*:?\s*(/article/\S*)?\s*$', ln)]
    return '\n'.join(lineas).strip()
