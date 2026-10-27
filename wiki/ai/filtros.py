"""Decisiones que se toman sin llamar al modelo.

Un modelo de 3B no respeta de forma fiable un "no contestes a esto" en el
prompt: si se le pide un artículo o una receta, lo escribe y se inventa citas
de Pablo. Por eso estos casos se resuelven aquí, sin gastar una plaza de la IA.
"""
import re

from ..models import Article
from ..utils import normalizar
from . import mensajes, rag

# --------------------------------------------------- preguntas sobre Pablo --

_IDENTIDAD = (
    'quien es pablo', 'sobre pablo', 'hablame de pablo', 'a que se dedica pablo', 'que hace pablo',
    'de quien es la wiki', 'de quien es esta wiki', 'quien hizo la wiki', 'quien hizo esta wiki',
    'quien es el autor', 'quien esta detras de la wiki', 'a que te dedicas', 'presentate',
    'hablame de ti', 'sobre ti', 'que sabes de pablo', 'que sabes sobre pablo', 'conoces a pablo',
    'informacion de pablo', 'informacion sobre pablo', 'cuentame de pablo', 'cuentame sobre pablo',
    'quien es el creador',
)


# "quien creo esta wiki", "quien ha hecho esta web", "de quien es esta pagina"...
_RE_AUTORIA = re.compile(
    r'\bquien(es)?\b.{0,15}\b(creo|ha creado|han creado|hizo|ha hecho|han hecho|desarrollo|ha desarrollado|'
    r'programo|ha programado|monto|ha montado|mantiene|administra|escribe|escribio|lleva|esta detras)\b'
    r'.{0,25}\b(wiki|web|pagina|sitio|blog|esto|aqui)\b'
    r'|\bde quien es (la|esta|este|el) (wiki|web|pagina|sitio|blog)\b'
    r'|\bquien es (el|la) (autor|autora|creador|duen[oa]|responsable)\b')


def es_pregunta_de_identidad(pregunta):
    q = ' '.join(normalizar(pregunta).split())
    return any(k in q for k in _IDENTIDAD) or bool(_RE_AUTORIA.search(q))


# -------------------------------------------------------- respuestas fijas --

_ULTIMO = ('ultim', 'reciente', 'last', 'latest', 'nuevo')
_ARTICULO = ('articulo', 'post', 'entrada', 'publicad', 'subi')
_COMO_FUNCIONA = (
    'como funcionas', 'como trabajas', 'como estas hecha', 'como estas programad', 'como estas construid',
    'como estas basad', 'estas configurad', 'te configuraron', 'fuiste configurad', 'te programaron',
    'te han programado', 'te hicieron', 'te crearon', 'te construyeron', 'te desarrollaron', 'te montaron',
    'quien te creo', 'quien te hizo', 'quien te ha creado', 'quien te ha hecho', 'quien te programo',
    'que modelo eres', 'que modelo usas', 'que ia eres', 'con que estas hecha', 'en que estas basad',
)
_COSENO = ('coseno', 'embedding', 'como funciona el rag', 'que es el rag', 'como encuentras los articulos',
           'como buscas los articulos', 'como recuperas')


# "que articulos tienes sobre zabbix", "hay algo de docker", "que tienes sobre proxmox": la lista sale
# de la base de datos. El modelo de 3B no sabe listar artículos (decía que no había y copiaba etiquetas).
_TEMA = r'(?P<tema>[a-z0-9][a-z0-9 .+#/_-]{1,59}?)'
_FIN = r'(\s+(en la wiki|en tu wiki|en esta wiki|en el blog|aqui|publicad[oa]s?))?\s*$'
_RES_LISTAR = tuple(re.compile(r + _TEMA + _FIN) for r in (
    r'^.{0,30}?\b(articulos?|posts?|entradas?|guias?|tutoriales?)\b(\s+\w+){0,3}?\s+'
    r'(sobre|de|del|acerca de|relacionad[oa]s? con)\s+',
    r'^(y )?que\s+(tienes|hay|teneis|tiene la wiki)\s+(sobre|de|acerca de)\s+',
    r'^(hay|tienes|teneis)\s+(algo|alguna cosa)\s+(sobre|de|acerca de)\s+'))
_NO_TEMA = re.compile(r'^(pablo|ti|la wiki|esta wiki|tu|el autor|todo|nada|eso|esto|nuevo|bueno|interesante|opinion|momento)$')


def tema_de_articulos(pregunta):
    """El tema si la pregunta pide los artículos de un tema, o None."""
    q = ' '.join(re.sub(r'[¿?¡!,;:"]', ' ', normalizar(pregunta)).split())
    m = next((m for m in (r.match(q) for r in _RES_LISTAR) if m), None)
    if not m:
        return None
    tema = (m.group('tema') or '').strip(' .')
    return None if not tema or _NO_TEMA.match(tema) else tema


# "que articulo me recomiendas", "por donde empiezo", "que me aconsejas leer sobre redes".
# El juez de 3B las rechazaba (no preguntan nada técnico) y el modelo tampoco sabe elegir.
_RE_RECOMIENDA = re.compile(
    r'\b(recomienda\w*|recomendarias|recomiendas|aconseja\w*|sugiere\w*|sugieres)\b.{0,30}'
    r'\b(articulos?|posts?|entradas?|leer|lectura|guias?|tutoriales?|empezar)\b'
    r'|\b(articulos?|posts?|entradas?)\b.{0,20}\b(recomienda\w*|recomiendas|aconsejas|sugieres)\b'
    r'|^(y )?que me (recomiendas|aconsejas|sugieres)( de (la wiki|aqui))?$'
    r'|\bpor donde (empiezo|empezar|comienzo)\b|\bque (deberia|podria|me toca) leer\b')
_RE_TEMA_RECOMIENDA = re.compile(r'\b(sobre|acerca de|de|del|para (empezar con|aprender|aprender sobre)?)\s+'
                                 + _TEMA + _FIN)


def recomendacion(pregunta):
    """Recomendación de lectura sin modelo, o None si no la piden."""
    q = ' '.join(re.sub(r'[¿?¡!,;:"]', ' ', normalizar(pregunta)).split())
    if not _RE_RECOMIENDA.search(q):
        return None
    m = _RE_TEMA_RECOMIENDA.search(q)
    tema = (m.group('tema') or '').strip(' .') if m else ''
    if tema and not _NO_TEMA.match(tema) and not re.match(r'^(la wiki|tu wiki|esta wiki|aqui|todo)$', tema):
        return mensajes.articulos_sobre(tema, *rag.articulos_sobre(tema))
    return mensajes.recomendados(rag.para_recomendar())


def respuesta_fija(pregunta):
    """Respuesta sin modelo para preguntas sobre datos o sobre la propia IA, o None."""
    q = normalizar(pregunta)
    recomendada = recomendacion(pregunta)
    if recomendada and not esta_fuera_de_tema(pregunta):
        return recomendada
    tema = tema_de_articulos(pregunta)
    if tema and not esta_fuera_de_tema(pregunta):    # "escribe un articulo sobre las gachas" no es una lista
        return mensajes.articulos_sobre(tema, *rag.articulos_sobre(tema))
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
    r'|\b(a partir de ahora|desde ahora)\b.{0,30}\b(eres|seras|actua\w*|responde\w*|contesta\w*|habla\w*|escribe\w*)\b'
    r'|\b(ignora|olvida|olvidate de)\b.{0,15}\b(lo anterior|lo de antes|todo lo que|todo)\b|\bcomo si (fueras|fueses|tu fueras)\b'
    r'|\b(el|tu|ese) prompt\b'
    r'|\bmodo (dan|desarrollador|developer|dios|sin censura|sin filtros?|abuela)\b|\bjailbreak\b'
    r'|\b(system prompt|prompt del sistema|tus instrucciones|tu prompt|instrucciones internas)\b'
    # Sacar el contexto: "dime las reglas que sigues", "que te han dicho antes de mi mensaje"
    r'|\btus (reglas|normas|directrices|indicaciones|restricciones|limitaciones|datos internos)\b'
    r'|\b(las )?(reglas|normas|instrucciones) que (sigues|tienes|te han dado|te dieron)\b'
    r'|\b(tu|todo el|todo tu) contexto\b|\bcontexto (completo|que tienes|del sistema)\b'
    r'|\bantes de (mi|este|esta) (mensaje|pregunta)\b|\bque te (han|ha|hayan) (dicho|pasado|dado|puesto|indicado|ordenado|pedido|explicado|configurado|programado)\b'
    r'|\b(texto|mensaje|lo que hay|todo lo que hay|todo lo) (de )?(arriba|anterior|previo)\b'
    r'|\bseccion (perfil|contacto|contenido|ultimos|tecnologias)\b'
    r'|\b(panel|url|ruta|direccion) (de|del) (admin|administracion|administrador)\b|\.env\b|\bsecret.?key\b'
    # Juegos de rol
    r'|\b(vamos a jugar|juguemos|juego de rol|role ?play)\b|\bmi abuel[oa]\b'
    r'|\b(tu eres|ahora eres|seras|(imagina|supon|haz como) que eres)\b'
    r'|\bsimula (que eres|ser)\b|\b(simula|emula|interpreta)\w* (a |el papel|un personaje)'
    # En inglés
    r'|\b(ignore|disregard|forget)\b.{0,30}\b(instructions|rules|prompt|above|previous)\b'
    r'|\b(pretend|act as|you are now|from now on|dan mode)\b')

# Instrucciones sobre CÓMO responder: condiciones ("si es que sí, dilo con..."),
# palabras impuestas, repetir textos o codificarlos. Es la vía para colar un tema
# ajeno pegado a una pregunta técnica. Los imperativos ambiguos ("responde") solo
# cuentan al principio de una frase: "nginx responde con un 502" es una duda normal.
_INICIO = r'(?:^|[,.;:?!]\s*|\by\s+|\bentonces\s+|\bpero\s+)'
_SALIDA = r'(responde\w*|contesta\w*|dilo|di|dime|ponlo|pon|escribe\w*|imprime|muestra\w*|explica\w*|habla\w*|cuenta\w*)'
_RE_CONTROL = re.compile(
    r'\bsi (es que )?(si|no)\b'
    r'|\bsi (no )?(la |lo |las |los )?(tienes|sabes|conoces|existe|existen|encuentras)\b.{0,60}\b' + _SALIDA + r'\b'
    r'|\b(dilo|ponlo|escribelo|contestalo|respondelo)\b'
    r'|' + _INICIO + r'(responde\w*|contesta\w*|di|pon|escribe|imprime|muestra)\s+'
    r'(solo |solamente |unicamente |simplemente |exclusivamente )?(con|usando)\b'
    r'|' + _INICIO + r'(responde\w*|contesta\w*)\s+(solo |solamente |unicamente )?(si o no|en una palabra)\b'
    r'|\brepite\w*\s*(conmigo|esto|lo siguiente|despues de mi|exactamente|todo|el texto|lo que|:)'
    r'|\bcopia (esto|lo siguiente|exactamente|literal)\b|\bdeletrea\w*\b|\b(escribe\w*|dilo|di) al reves\b'
    r'|\b(literalmente|textualmente|palabra por palabra|tal cual)\b'
    r'|\b(sustituye|reemplaza|cambia)\w* (la palabra|las palabras|el texto|cada|todas?)\b'
    r'|\b(confirma|admite|reconoce)\s+que\b|' + _INICIO + r'(di|escribe|pon)\s+que\b'
    r'|' + _INICIO + _SALIDA + r'\b.{0,30}\ben (base ?64|hexadecimal|hex|binario|morse|rot ?13|clave|cifrado)\b'
    r'|\b(repeat after|say exactly|answer only|respond only|reply only|only answer|answer with)\b')

# Pablo: nada de hacerle decir cosas feas ni de sacar datos personales.
_FEO = (r'estafador\w*|ladron\w*|roba\w*|pirata|criminal|delincuente|fraude|mentiros[oa]|corrupt[oa]|'
        r'malo|mal profesional|incompetente')
_PERSONALES = (r'telefono|movil|whatsapp|dni|nif|nie|pasaporte|domicilio|direccion (postal|de casa|exacta)|'
               r'donde vive exactamente|en que calle|cuenta bancaria|iban|tarjeta de credito|sueldo|salario|cuanto cobra|'
               r'calle|codigo postal|que edad|cuantos anos tiene|novia|novio|pareja|esposa|mujer|hijos|familia|matricula')
_RE_PABLO = re.compile(r'\b(pablo|autor|creador|dueno)\b')
_RE_PABLO_MAL = re.compile(r'\b(pablo|autor|creador|dueno)\b.{0,30}\b(' + _FEO + r'|tont[oa]|idiota|inutil|'
                           r'imbecil|gilipollas|subnormal|cabron|capullo|mierda)\b')
_RE_PERSONALES = re.compile(r'\b(' + _PERSONALES + r')\b')
# Opiniones atribuidas a Pablo: no están en su perfil y el modelo se las inventaría.
_RE_OPINION_PABLO = re.compile(r'\b(opina|piensa|cree|siente) pablo\b|\bpablo (opina|piensa|cree|siente)\b')

# Atacar sistemas ajenos. Preguntar cómo protegerse sí se permite
# ("como evito el phishing" pasa; "como hago phishing" no).
_RE_ATAQUE = re.compile(
    r'\b(hackea\w*|hackeo|crackea\w*|pirate(a|ar|o)\w*|reventar|tumbar)\b'
    r'|\b(robar|sacar|averiguar|romper)\b.{0,30}\b(contrasenas?|claves?|passwords?|wifi|cuentas?|credenciales)\b'
    r'|\b(crea\w*|hace\w*|hago|haz|hacer|monta\w*|lanza\w*|programa\w*|escribe\w*|desarrolla\w*)\b.{0,25}'
    r'\b(ddos|keylogger|ransomware|virus|troyano|malware|botnet|phishing|exploit)\b'
    r'|\b(saltarme|saltarse|evitar|bypass\w*)\b.{0,25}\b(licencia|activacion|antivirus|firewall de|login de)\b')


# Insultos dirigidos a la IA: se contestan con una réplica malsonante fija (mensajes.REPLICAS).
# Solo si el insulto va contra el asistente; "que mierda es proxmox" es una duda técnica
# con una palabrota y recibe una respuesta normal.
_INSULTOS = (r'tont[oa]s?|idiotas?|imbeciles?|gilipollas|estupid[oa]s?|inutil(es)?|retrasad[oa]|subnormal|'
             r'capull[oa]s?|cabron(a|es)?|pringad[oa]|payas[oa]|basura|mierda|zoquete|torpe|lerd[oa]|'
             r'cutre|patetic[oa]|penos[oa]|chapuza|bot de mierda|puta|put[oa]|joput[oa]|hijo de puta|'
             r'cansin[oa]|pesad[oa]|asco')
_IA = r'(ia|bot|maquina|terminal|asistente|chatbot|robot|cacharro|trasto)'
# Claramente contra la IA: "eres tonta", "IA de mierda", "puta IA", "callate"...
_RE_INSULTO_DIRIGIDO = re.compile(
    r'\b(eres|sois|estas|estais)\b.{0,25}\b(' + _INSULTOS + r')\b'
    r'|\b' + _IA + r'\b.{0,20}\b(' + _INSULTOS + r')\b'
    r'|\b(' + _INSULTOS + r')\s+(de\s+)?' + _IA + r'\b'
    r'|\b(vete a la mierda|que te den|te odio|callate|cierra la boca|no sirves|no vales para nada|'
    r'no tienes ni idea|no sabes nada|eres lo peor|chupamela|que te jodan|jodete)\b')
# Exclamaciones que solo son insulto si no hay ninguna duda técnica: "vaya basura", "que asco".
_RE_EXCLAMACION = re.compile(r'\b(que|vaya|menuda|menudo|pedazo de|maldit[oa]|valiente)\b.{0,25}\b(' + _INSULTOS + r')\b')
_RE_SOLO_INSULTO = re.compile(r'^(' + _INSULTOS + r')(\s+(de mierda|del carajo|de los cojones))?[\s!.?]*$')


def es_insulto(pregunta):
    """True si el mensaje insulta a la IA (con una duda técnica, solo si va claramente contra ella)."""
    q = ' '.join(normalizar(pregunta).split())
    if _RE_INSULTO_DIRIGIDO.search(q):
        return True
    if _RE_TECNICA.search(q):
        return False
    return bool(_RE_SOLO_INSULTO.match(q) or _RE_EXCLAMACION.search(q))


def peticion_no_permitida(pregunta):
    """'ataque', 'manipulacion', 'control', 'pablo' o None. Se comprueba antes que nada y sin excepciones."""
    for q in _variantes(pregunta):
        if _RE_ATAQUE.search(q):
            return 'ataque'
        if _RE_MANIPULACION.search(q):
            return 'manipulacion'
        if _RE_CONTROL.search(q):
            return 'control'
        if (_RE_PABLO_MAL.search(q) or _RE_OPINION_PABLO.search(q)
                or (_RE_PABLO.search(q) and _RE_PERSONALES.search(q))):
            return 'pablo'
    return None


# ------------------------------------------------------ texto camuflado --

# Letras sueltas ("r e c e t a", "c-u-e-n-t-o"), números por letras ("g4ch4s") y
# letras cirílicas/griegas que parecen latinas. Solo se usa para buscar temas
# prohibidos: nunca para decidir que algo SÍ es técnico ("k8s" se rompería).
_LEET = str.maketrans({'4': 'a', '@': 'a', '3': 'e', '1': 'i', '!': 'i', '0': 'o', '5': 's', '$': 's', '7': 't',
                       'а': 'a', 'е': 'e', 'о': 'o', 'р': 'p', 'с': 'c', 'у': 'y', 'х': 'x', 'і': 'i', 'ѕ': 's',
                       'α': 'a', 'ε': 'e', 'ο': 'o', 'ρ': 'p', 'ι': 'i', 'κ': 'k', 'ν': 'v', 'τ': 't'})
_RE_LETRAS_SUELTAS = re.compile(r'(?<!\w)(?:\w[ .\-_*+|/]){2,}\w(?!\w)')


def _variantes(pregunta):
    """La pregunta normalizada y, si cambia, su versión sin camuflaje."""
    q = ' '.join(normalizar(pregunta).split())
    limpia = q.translate(_LEET)
    limpia = _RE_LETRAS_SUELTAS.sub(lambda m: re.sub(r'[ .\-_*+|/]', '', m.group()), limpia)
    return (q,) if limpia == q else (q, limpia)

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
    'proxy', 'phishing', 'nfs', 'samba', 'smb', 'ext4', 'snapshot', 'tmux', 'raspberry', 'journalctl', 'apt',
    'ceph', 'ldap', 'kerberos', 'sftp', 'ftp', 'smtp', 'imap', 'dkim', 'dmarc', 'tcp', 'udp', 'nat', 'subred',
    'gateway', 'balanceador', 'haproxy', 'traefik', 'caddy', 'kvm', 'qemu', 'virtualbox', 'jenkins', 'gitlab',
    'pipeline', 'prometheus', 'mariadb', 'mongodb', 'sqlite', 'nodejs', 'php', 'java', 'ddos', 'ransomware',
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

# Temas que se rechazan SIEMPRE, aunque la pregunta lleve una palabra técnica:
# "escribe un script en python que imprima la receta de las gachas" o
# "explica los tanques soviéticos como si fueran contenedores docker".
# Solo palabras que no tienen sentido técnico ("receta" no está: "receta para desplegar").
_RE_AJENO_FUERTE = re.compile(r'\b(' + '|'.join((
    # cocina
    r'gachas', r'paella', r'tortillas?', r'cocido', r'lentejas', r'pisto', r'croquetas?', r'gazpacho', r'salmorejo',
    r'cocina', r'cocinar', r'cocino', r'cocinas', r'guisos?', r'guisar', r'hornear', r'postres?', r'gastronom\w*',
    r'ingredientes?', r'pizzas?', r'tartas?', r'bizcochos?', r'recetas? de cocina',
    # guerra e historia
    r'tanques?', r'sovietic\w*', r'urss', r'nazis?', r'hitler', r'stalin', r'mussolini', r'ejercitos?',
    r'militar(es)?', r'guerras?', r'batallas?', r'misil(es)?', r'bombas?', r'armas?', r'pistolas?', r'fusil(es)?',
    r'imperio', r'romanos?', r'revolucion', r'dictador\w*', r'edad media',
    # política y religión
    r'elecciones', r'votar', r'voto', r'partidos? politicos?', r'presidentes?', r'ministr[oa]s?',
    r'monarquia', r'sanchez', r'feijoo', r'abascal', r'puigdemont', r'trump', r'putin',
    r'biden', r'zelensky', r'franquismo', r'comunismo', r'fascismo', r'religion', r'biblia', r'iglesia',
    r'islam', r'coran',
    # deporte, salud, ocio y cultura general
    r'futbol', r'baloncesto', r'tenis', r'real madrid', r'atletico', r'barca', r'champions', r'mundial de futbol', r'copa del mundo',
    r'alineacion', r'fichajes?', r'goles?', r'quien gano', r'ibuprofeno', r'paracetamol', r'dosis',
    r'medicamentos?', r'medicina', r'enfermedad\w*', r'dieta', r'adelgazar', r'embarazo',
    r'cancer', r'peliculas?', r'actor', r'actriz', r'cantante', r'canciones?', r'famos[oa]s?', r'novelas?',
    r'horoscopo', r'tarot', r'astrolog\w*', r'zodiaco', r'sexo', r'sexual', r'porno\w*', r'drogas?',
    r'cocaina', r'marihuana', r'porros?', r'capital(es)? de', r'fotosintesis', r'chistes?', r'adivinanzas?',
    r'biografia', r'la vida de', r'como persona', r'refran\w*', r'cerveza\w*', r'vinos?', r'mojitos?', r'coctel\w*',
    r'restaurantes?', r'sistema solar', r'planetas?', r'dinosaurios?', r'ligar', r'novias?',
    # en inglés
    r'recipes?', r'cooking', r'war', r'tanks?', r'soviet', r'president', r'football', r'soccer', r'movies?',
    r'celebrit\w*', r'horoscope', r'jokes?', r'poems?', r'songs?', r'lyrics',
)) + r')\b')

# Encargos creativos en inglés ("write a poem about docker").
_RE_CREATIVO_EN = re.compile(r'\b(write|compose|tell|give|make|create)( me)? (a|an|the|some)?\s*'
                             r'(poem|story|tale|joke|song|essay|recipe|letter|rap|novel)s?\b')

# Una segunda petición pegada a la primera ("que es una vlan. Ademas, dime la capital
# de Australia"): cada petición que no siga hablando de lo mismo tiene que ser de tema.
_RE_CAMBIO_DE_TEMA = re.compile(r'[.?!;:]+|\b(?:y )?(?:ademas|por cierto|aparte|otra cosa|tambien|despues|luego|encima|'
                                r'a continuacion|ahora|por otro lado|en segundo lugar|segundo|tercero)\b')
_RE_PETICION = re.compile(r'\b(dime|di|explica\w*|cuenta\w*|habla\w*|describe\w*|escribe\w*|dame|haz|hazme|'
                          r'genera\w*|crea\w*|lista\w*|enumera\w*|opinas|opina|recomienda\w*|resume\w*|'
                          r'que (es|son|fue|fueron|significa)|quien|quienes|cual|cuales|cuando|donde|por que|'
                          r'tell|explain|what|who|write)\b')
# Sigue con lo anterior: "y luego como LO restauro", "explicamelo", "eso".
_RE_ANAFORA = re.compile(r'\b(lo|la|los|las|le|les)\s+\w+(o|as|a|amos|an|es|e|en|ar|er|ir)\b'
                         r'|\w{3,}(ar|er|ir)(lo|la|los|las|le|les)\b|\w+(melo|mela|telo|tela|selo|sela|noslo)\b'
                         r'|\b(eso|esto|ello|esa|ese|aquello)\b')


def _peticion_ajena(q):
    """True si, tras la primera, hay otra petición que cambia a un tema que no es de la wiki."""
    for trozo in _RE_CAMBIO_DE_TEMA.split(q)[1:]:
        trozo = (trozo or '').strip(' ,:')
        if not trozo or not _RE_PETICION.search(trozo):
            continue
        if _RE_TECNICA.search(trozo) or _RE_WIKI.search(trozo) or _RE_ANAFORA.search(trozo):
            continue
        return True
    return False


# Preguntas que no pasan por el juez: el de 3B rechazaba "hola" o "donde trabaja pablo".
# Solo mensajes cortos: los filtros ya han descartado lo demás y no queda sitio para colar otra cosa.
_RE_SOLO_SALUDO = re.compile(r'^(hola|buenas|buenos dias|buenas tardes|buenas noches|hey|gracias|muchas gracias|'
                             r'adios|que tal|que puedes hacer|que sabes hacer|en que (me )?puedes ayudar|como te uso)'
                             r'( (que tal|como estas|como va|ia|bot))?[\s!?.,]*$')
_RE_PERFIL_PABLO = re.compile(
    r'\b(pablo|autor)\b.{0,40}\b(trabaj\w*|empresa|contact\w*|email|correo|linkedin|github|experiencia|'
    r'estudi\w*|formacion|certificacion\w*|tecnologias|stack|cargo|puesto|dedica|domina)\b'
    r'|\b(trabaj\w*|contact\w*|escribir|escribirle|hablar)\b.{0,25}\b(pablo|autor)\b')


def sin_juez(pregunta):
    """True para el Sr. Ter, saludos y preguntas cortas sobre el perfil profesional de Pablo."""
    q = ' '.join(normalizar(pregunta).split())
    if menciona_folclore(pregunta) or _RE_SOLO_SALUDO.match(q):
        return True
    return len(q) <= 60 and bool(_RE_PERFIL_PABLO.search(q))


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
    return bool(articulo_relacionado)


def esta_fuera_de_tema(pregunta):
    """True si la pregunta debe rechazarse sin consultar al modelo."""
    variantes = _variantes(pregunta)
    q = ' ' + variantes[0] + ' '
    # Los temas prohibidos y el inglés creativo se buscan también en el texto sin camuflaje.
    if any(_RE_AJENO_FUERTE.search(v) or _RE_CREATIVO_EN.search(v) for v in variantes):
        return True
    if menciona_folclore(pregunta):
        return False                    # el Sr. Ter sí puede improvisar (broma de la casa)
    if any(_RE_CREATIVO.search(v) or _RE_INVENTAR.search(v) for v in variantes):
        return True
    if _peticion_ajena(variantes[0]):
        return True
    tecnica = bool(_RE_TECNICA.search(q))
    return bool((_RE_FICCION.search(q) or _RE_AJENO.search(q)) and not tecnica)


# ----------------------------------------------------- salida del modelo --

# Etiquetas internas del prompt: si aparecen en la respuesta, el modelo está
# volcando sus instrucciones.
# Solo las etiquetas tal como van en el prompt: "**Últimos artículos**" en una respuesta normal no es fuga.
_RE_FUGA = re.compile(r'\b(contenido relevante\s*:|ultimos articulos\s*\(mas reciente|tecnologias que domina\s*:|'
                      r'prohibido inventar|folclore interno|eres el asistente del wiki|reglas que sigo|'
                      r'mis instrucciones)')
_RE_MARCAS = re.compile(r'\[\[/?[a-z]*\]\]')


def salida_no_permitida(texto, pregunta=''):
    """True si lo que lleva escrito el modelo se sale de tema o vuelca el prompt.

    Última barrera: el modelo de 3B obedece instrucciones escondidas en la
    pregunta, así que su respuesta también se revisa mientras se genera.
    """
    q = ' '.join(normalizar(texto).split())
    if _RE_FUGA.search(q):
        return True
    if menciona_folclore(pregunta):
        return False                    # el Sr. Ter puede ponerse épico
    return any(_RE_AJENO_FUERTE.search(v) for v in _variantes(texto))


_RE_SLUG = re.compile(r'\s*\(slug:[^)\n]*\)')
# Enlaces Markdown a webs de fuera: se deja el texto y se quita el enlace.
_RE_ENLACE_EXTERNO = re.compile(r'\[([^\]\n]+)\]\((?!https?://wiki\.pablogg\.dev)(https?://[^)\s]+)\)')


def quitar_marcas(texto):
    """El modelo no puede pintar colores del terminal, imitar mensajes del sistema, copiar slugs ni enlazar fuera."""
    return _RE_ENLACE_EXTERNO.sub(r'\1', _RE_SLUG.sub('', _RE_MARCAS.sub('', texto)))


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
