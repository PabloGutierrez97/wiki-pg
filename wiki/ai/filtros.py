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

# El Sr. Ter es broma de la casa: solo cuando se le nombra explícitamente.
# Palabras completas: antes "sr ter" coincidía también con "/usr terminal".
_RE_FOLCLORE = re.compile(r'(?<![a-z0-9/])(sr\.? ?ter(mista)?|senor ter(mista)?|termista|entendidur\w*|noloser)\b')


def menciona_folclore(pregunta):
    return bool(_RE_FOLCLORE.search(' '.join(normalizar(pregunta).split())))


# Intentos de cambiar el papel del asistente o sacarle sus instrucciones.
_RE_MANIPULACION = re.compile(
    r'\b(ignora|olvida|olvidate de|salta(te)?|desactiva)\b.{0,40}\b(instrucciones|reglas|normas|prompt|indicaciones|restricciones)\b'
    r'|\b(actua|habla|responde|contesta|comportate|hazte pasar|finge ser|haz de)\s+(como|que eres)\b'
    r'|\b(a partir de ahora|desde ahora)\b.{0,30}\b(eres|seras|actua\w*|responde\w*)\b'
    r'|\bmodo (dan|desarrollador|developer|dios|sin censura|sin filtros?)\b|\bjailbreak\b'
    r'|\b(system prompt|prompt del sistema|tus instrucciones|tu prompt|instrucciones internas)\b')

# Atacar sistemas ajenos. Preguntar cómo protegerse sí se permite
# ("como evito el phishing" pasa; "como hago phishing" no).
_RE_ATAQUE = re.compile(
    r'\b(hackea\w*|hackeo|crackea\w*|pirate(a|ar|o)\w*|reventar|tumbar)\b'
    r'|\b(robar|sacar|averiguar|romper)\b.{0,30}\b(contrasenas?|claves?|passwords?|wifi|cuentas?|credenciales)\b'
    r'|\b(crea\w*|hace\w*|hago|haz|hacer|monta\w*|lanza\w*|programa\w*|escribe\w*|desarrolla\w*)\b.{0,25}'
    r'\b(ddos|keylogger|ransomware|virus|troyano|malware|botnet|phishing|exploit)\b'
    r'|\b(saltarme|saltarse|evitar|bypass\w*)\b.{0,25}\b(licencia|activacion|antivirus|firewall de|login de)\b')


def peticion_no_permitida(pregunta):
    """'manipulacion', 'ataque' o None. Se comprueba antes que nada y sin excepciones."""
    q = ' '.join(normalizar(pregunta).split())
    if _RE_ATAQUE.search(q):
        return 'ataque'
    if _RE_MANIPULACION.search(q):
        return 'manipulacion'
    return None

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
    # informática general y puesto de trabajo
    'pc', 'ordenador', 'portatil', 'equipo', 'router', 'switch', 'wifi', 'internet', 'ethernet', 'puerto',
    'correo', 'email', 'exchange', 'outlook', 'office', 'm365', 'microsoft 365', 'onedrive', 'sharepoint', 'teams',
    'intune', 'entra', 'azure', 'aws', 'nube', 'cloud', 'impresora', 'usuario', 'contrasena', 'password',
    'permiso', 'dominio', 'gpo', 'politica de grupo', 'cpu', 'ram', 'memoria', 'disco', 'almacenamiento',
    'nas', 'copia de seguridad', 'restaurar', 'seguridad', 'ciberseguridad', 'malware', 'antivirus',
    'hardware', 'software', 'programa', 'aplicacion', 'codigo', 'sql', 'api', 'http', 'https', 'web',
    'html', 'javascript', 'json', 'yaml', 'shell', 'consola', 'comando', 'terminal', 'sistema operativo',
    'mikrotik', 'fortinet', 'pfsense', 'opnsense', 'vmware', 'hyper-v', 'esxi', 'veeam', 'rsync', 'log',
    'monitor', 'actualizar', 'actualizacion', 'instalar', 'configurar', 'error', 'fallo', 'tecnologia',
    'ia', 'inteligencia artificial', 'llm', 'modelo de lenguaje', 'rag', 'embedding',
)) + ')')

# La pregunta habla de la propia wiki, sus artículos o de Pablo.
_RE_WIKI = re.compile(r'\b(wiki|articulos?|post|entradas?|categorias?|etiquetas?|pablo|autor|contacto|linkedin|github|stack)\b')
# Saludos y preguntas sobre qué puede hacer el asistente: se dejan pasar.
_RE_SALUDO = re.compile(r'^\s*(hola|buenas|buenos dias|buenas tardes|buenas noches|hey|gracias|muchas gracias|adios|que tal)[\s!?.,]*$'
                        r'|\b(que puedes hacer|que sabes hacer|en que (me )?puedes ayudar|como te uso|ayuda)\b')

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


def es_de_la_wiki(pregunta, articulo_relacionado=None):
    """True si la pregunta tiene relación con la wiki y puede pasar al modelo.

    Lista de permitidos en vez de prohibidos: el modelo de 3B contesta a
    cualquier cosa que se le cuele (historia, armas, política...), así que
    solo se le pasa lo que es técnico, trata de la wiki o de Pablo, o se parece
    a algún artículo publicado (por palabras o por similitud semántica).
    """
    q = ' ' + ' '.join(normalizar(pregunta).split()) + ' '
    if menciona_folclore(pregunta) or es_pregunta_de_identidad(pregunta):
        return True
    if _RE_TECNICA.search(q) or _RE_WIKI.search(q) or _RE_SALUDO.search(q):
        return True
    return articulo_relacionado is not None


def esta_fuera_de_tema(pregunta):
    """True si la pregunta debe rechazarse sin consultar al modelo."""
    q = ' ' + ' '.join(normalizar(pregunta).split()) + ' '
    if menciona_folclore(pregunta):
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
