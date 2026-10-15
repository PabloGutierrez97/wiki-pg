from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
import json
import re

from .models import Article, Category, Profile
import hashlib
import math
import os
import time
import unicodedata
import urllib.request
from array import array
from django.core.cache import cache

from .security import (
    RespuestaLiberable, client_ip, excede_limite,
    reservar_plaza_ia, reservar_turno_ip,
)

# Límites de la IA (por visitante). La concurrencia global va en settings.AI_MAX_CONCURRENT.
ASK_POR_MINUTO = 5
ASK_POR_HORA = 30
# Comandos normales del terminal (ls, cat, tree...): baratos, pero sin límite se pueden encadenar.
CMD_POR_MINUTO = 60
# Peticiones del terminal: una pregunta de 300 caracteres cabe de sobra en 4 KB.
MAX_BODY = 4096
# Respuestas idénticas se sirven desde caché durante este tiempo.
ASK_CACHE_SEG = 15 * 60

MSG_RAPIDO = "[[amarillo]]Vas muy rapido.[[/]] Espera un poco antes de volver a preguntar."
MSG_EN_CURSO = "[[amarillo]]Ya tienes una pregunta en curso.[[/]] Espera a que termine la respuesta."
MSG_OCUPADA = ("[[amarillo]]La IA esta atendiendo a otras personas ahora mismo.[[/]] "
               "Vuelve a preguntar en unos segundos.")
MSG_NO_DISPONIBLE = "[[rojo]]La IA no esta disponible ahora mismo.[[/]] Intentalo de nuevo en un momento."
MSG_FUERA_DE_TEMA = ("[[verde]]IA[[/]] [[gris]].[[/]] Solo puedo ayudarte con la wiki de Pablo y con temas de "
                     "sistemas, redes, virtualizacion y DevOps. No escribo articulos, historias ni recetas, "
                     "y no invento nada sobre Pablo.\n\n"
                     "[[gris]]Prueba con[[/]] [[amarillo]]ls[[/]][[gris]],[[/]] [[amarillo]]buscar <tema>[[/]] "
                     "[[gris]]o[[/]] [[amarillo]]help[[/]][[gris]].[[/]]")


def _cmd_help():
    lineas = [
        "[[verde]]Comandos disponibles:[[/]]",
        "",
        "  [[amarillo]]help[[/]]              Muestra esta ayuda",
        "  [[amarillo]]whoami[[/]]            Informacion sobre Pablo",
        "  [[amarillo]]ls[[/]]                Lista las categorias",
        "  [[amarillo]]ls[[/]] [[gris]]<categoria>[[/]]    Lista articulos de una categoria",
        "  [[amarillo]]cat[[/]] [[gris]]<slug>[[/]]        Muestra el resumen de un articulo",
        "  [[amarillo]]buscar[[/]] [[gris]]<texto>[[/]]    Busca articulos por palabra",
        "  [[amarillo]]tree[[/]]              Estructura completa de la wiki",
        "  [[amarillo]]stack[[/]]             Muestra el stack tecnologico",
        "  [[amarillo]]stats[[/]]             Estadisticas de la wiki",
        "  [[amarillo]]neofetch[[/]]          Resumen del sistema",
        "  [[amarillo]]contact[[/]]           Enlaces de contacto",
        "  [[amarillo]]date[[/]]              Fecha y hora actual",
        "  [[amarillo]]ask[[/]] [[gris]]<pregunta>[[/]]    Pregunta libre a la IA (local)",
        "  [[amarillo]]wikis[[/]]             Otras wikis recomendadas",
        "  [[amarillo]]clear[[/]]             Limpia la pantalla",
    ]
    return "\n".join(lineas)


def _cmd_whoami():
    p = Profile.get()
    if not p:
        return "Perfil no configurado."
    lineas = [
        f"[[verde]]{p.nombre or ''}[[/]]",
        f"[[azul]]{p.cargo or ''}[[/]] en [[azul]]{p.empresa or ''}[[/]]",
        f"[[gris]]{p.ubicacion or ''}[[/]]",
    ]
    if p.descripcion:
        lineas.append("")
        lineas.append(p.descripcion)
    return "\n".join([l for l in lineas if l])


def _cmd_stack():
    p = Profile.get()
    if not p or not p.stack:
        return "Stack no configurado."
    try:
        data = json.loads(p.stack)
        return "\n".join(f"  [[amarillo]]{k}:[[/]] {v}" for k, v in data.items())
    except Exception:
        return p.stack


def _cmd_ls(arg):
    if not arg:
        cats = Category.objects.all().order_by('name')
        if not cats:
            return "No hay categorias."
        lineas = ["[[gris]]Categorias disponibles:[[/]]", ""]
        for c in cats:
            n = Article.objects.filter(category=c, is_published=True).count()
            lineas.append(f"  [[verde]]{c.slug}/[[/]]   {c.name} [[gris]]({n} articulos)[[/]]")
        return "\n".join(lineas)
    q = arg.strip().rstrip('/')
    cat = (Category.objects.filter(slug__iexact=q).first()
           or Category.objects.filter(name__iexact=q).first()
           or Category.objects.filter(name__icontains=q).first()
           or Category.objects.filter(slug__icontains=q).first())
    if not cat:
        return f"Categoria '[[amarillo]]{arg}[[/]]' no encontrada. Usa [[amarillo]]ls[[/]] para verlas."
    arts = Article.objects.filter(category=cat, is_published=True).order_by('-created_at')
    if not arts:
        return f"No hay articulos en '{cat.name}'."
    lineas = [f"[[gris]]Articulos en[[/]] [[verde]]{cat.name}[[/]][[gris]]:[[/]]", ""]
    for a in arts:
        fecha = a.created_at.strftime('%d/%m/%Y')
        lineas.append(f"  [[azul]]{a.slug}[[/]]")
        lineas.append(f"    {a.title} [[gris]]· {fecha}[[/]]")
    return "\n".join(lineas)


def _cmd_cat(arg):
    if not arg:
        return "Uso: [[amarillo]]cat <slug-del-articulo>[[/]]"
    art = Article.objects.filter(slug__iexact=arg, is_published=True).first()
    if not art:
        return f"Articulo '[[amarillo]]{arg}[[/]]' no encontrado. Usa [[amarillo]]ls[[/]] para ver los disponibles."
    texto = re.sub(r'[#*`>_\[\]()]', '', art.content)
    palabras = len(art.content.split())
    lectura = max(1, round(palabras / 200))
    fecha = art.created_at.strftime('%d/%m/%Y')
    resumen = texto.strip()[:400]
    lineas = [
        f"[[verde]]{art.title}[[/]]",
        f"[[gris]]Categoria:[[/]] {art.category.name}  [[gris]]·[[/]]  [[gris]]{fecha}[[/]]  [[gris]]·[[/]]  [[gris]]{lectura} min de lectura[[/]]",
    ]
    if art.tags:
        tags = " ".join(f"[[amarillo]]#{t.strip()}[[/]]" for t in art.tags.split(',') if t.strip())
        lineas.append(f"[[gris]]Tags:[[/]] {tags}")
    lineas.append("")
    lineas.append(f"{resumen}...")
    lineas.append("")
    lineas.append(f"[[gris]]Leer completo:[[/]] /article/{art.slug}/")
    return "\n".join(lineas)


def _cmd_buscar(arg):
    if not arg:
        return "Uso: [[amarillo]]buscar <texto>[[/]]"
    from django.db.models import Q
    arts = Article.objects.filter(is_published=True).filter(
        Q(title__icontains=arg) | Q(content__icontains=arg) |
        Q(tags__icontains=arg) | Q(category__name__icontains=arg)
    ).distinct()[:8]
    if not arts:
        return f"Sin resultados para '[[amarillo]]{arg}[[/]]'."
    lineas = [f"[[verde]]{len(arts)}[[/]] [[gris]]resultado(s) para[[/]] '[[amarillo]]{arg}[[/]]':", ""]
    for a in arts:
        lineas.append(f"  [[gris]][{a.category.name}][[/]] [[azul]]{a.slug}[[/]]")
        lineas.append(f"    {a.title}")
    return "\n".join(lineas)


def _cmd_tree():
    cats = Category.objects.all().order_by('name')
    if not cats:
        return "No hay categorias."
    lineas = ["[[verde]]wiki.pablogg.dev[[/]]"]
    cats = list(cats)
    for i, c in enumerate(cats):
        ultima_cat = (i == len(cats) - 1)
        rama_cat = "└──" if ultima_cat else "├──"
        lineas.append(f"[[gris]]{rama_cat}[[/]] [[amarillo]]{c.name}/[[/]]")
        arts = list(Article.objects.filter(category=c, is_published=True).order_by('-created_at'))
        prefijo = "    " if ultima_cat else "[[gris]]│[[/]]   "
        for j, a in enumerate(arts):
            ultima_art = (j == len(arts) - 1)
            rama_art = "└──" if ultima_art else "├──"
            lineas.append(f"{prefijo}[[gris]]{rama_art}[[/]] [[azul]]{a.slug}[[/]]")
    return "\n".join(lineas)


def _cmd_stats():
    total_art = Article.objects.filter(is_published=True).count()
    total_cat = Category.objects.count()
    ultimo = Article.objects.filter(is_published=True).order_by('-created_at').first()
    total_palabras = sum(len(a.content.split()) for a in Article.objects.filter(is_published=True))
    lineas = [
        "[[verde]]Estadisticas de la wiki[[/]]",
        "",
        f"  [[amarillo]]Articulos publicados:[[/]] {total_art}",
        f"  [[amarillo]]Categorias:[[/]] {total_cat}",
        f"  [[amarillo]]Palabras totales:[[/]] {total_palabras:,}".replace(",", "."),
    ]
    if ultimo:
        fecha = ultimo.created_at.strftime('%d/%m/%Y')
        lineas.append(f"  [[amarillo]]Ultimo articulo:[[/]] {ultimo.title} [[gris]]({fecha})[[/]]")
    return "\n".join(lineas)


def _cmd_neofetch():
    p = Profile.get()
    nombre = p.nombre if p else "Pablo Gutierrez Gracia"
    cargo = p.cargo if p else "Administrador de Sistemas"
    total_art = Article.objects.filter(is_published=True).count()
    total_cat = Category.objects.count()
    logo = [
        "[[verde]]    ____  ______[[/]]",
        "[[verde]]   / __ \\/ ____/[[/]]",
        "[[verde]]  / /_/ / / __[[/]]  ",
        "[[verde]] / ____/ /_/ /[[/]]  ",
        "[[verde]]/_/    \\____/[[/]]   ",
    ]
    info = [
        f"[[amarillo]]{nombre}[[/]]",
        "[[gris]]-------------------[[/]]",
        f"[[amarillo]]Cargo:[[/]] {cargo}",
        f"[[amarillo]]Host:[[/]] wiki.pablogg.dev",
        f"[[amarillo]]OS:[[/]] Django 6 + PostgreSQL",
        f"[[amarillo]]Infra:[[/]] Proxmox LXC + Cloudflare",
        f"[[amarillo]]Articulos:[[/]] {total_art}",
        f"[[amarillo]]Categorias:[[/]] {total_cat}",
    ]
    lineas = []
    maxlen = max(len(logo), len(info))
    for i in range(maxlen):
        izq = logo[i] if i < len(logo) else "               "
        der = info[i] if i < len(info) else ""
        lineas.append(f"{izq}   {der}")
    return "\n".join(lineas)


def _cmd_contact():
    p = Profile.get()
    lineas = ["[[verde]]Contacto[[/]]", ""]
    if p and p.email:
        lineas.append(f"  [[amarillo]]Email:[[/]]    {p.email}")
    if p and p.linkedin:
        lineas.append(f"  [[amarillo]]LinkedIn:[[/]] {p.linkedin}")
    lineas.append(f"  [[amarillo]]GitHub:[[/]]   https://github.com/PabloGutierrez97")
    lineas.append(f"  [[amarillo]]Wiki:[[/]]     https://wiki.pablogg.dev")
    return "\n".join(lineas)


def _cmd_date():
    ahora = timezone.localtime()
    dias = ['Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado', 'Domingo']
    meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
             'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
    dia = dias[ahora.weekday()]
    mes = meses[ahora.month - 1]
    return f"[[verde]]{dia} {ahora.day} de {mes} de {ahora.year}[[/]] - [[amarillo]]{ahora.strftime('%H:%M:%S')}[[/]]"


def _cmd_wikis():
    wikis = [
        ("Juan Francisco Trapero", "https://wiki.jtrapero.eu.org/", "Memoria de un homelab: infraestructura autohospedada, Linux, redes, seguridad y automatizacion"),
    ]
    lineas = ["[[verde]]Otras wikis recomendadas[[/]]", ""]
    for nombre, url, desc in wikis:
        lineas.append("  [[amarillo]]%s[[/]]" % nombre)
        lineas.append("  %s" % url)
        lineas.append("  [[gris]]%s[[/]]" % desc)
        lineas.append("")
    return "\n".join(lineas).rstrip()


def _embed(texto, timeout=30, intentos=2):
    """Embedding con bge-m3. Para preguntas en vivo se llama con timeout corto y sin reintentos."""
    url = os.getenv('OLLAMA_URL', 'http://192.168.0.183:11434').rstrip('/') + '/api/embeddings'
    modelo = os.getenv('OLLAMA_EMBED_MODEL', 'bge-m3')
    payload = json.dumps({"model": modelo, "prompt": (texto or '')[:3000], "keep_alive": "5m"}).encode('utf-8')
    for _i in range(intentos):
        try:
            req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            emb = data.get('embedding')
            if emb:
                return emb
        except Exception:
            pass
        if _i + 1 < intentos:
            time.sleep(0.8)
    return None


def _trocear(texto, maximo=900):
    import re as _re
    texto = (texto or '').strip()
    if not texto:
        return []
    parrafos = _re.split(r'\n\s*\n', texto)
    chunks = []
    actual = ''
    for p in parrafos:
        p = p.strip()
        if not p:
            continue
        if actual and len(actual) + len(p) + 2 <= maximo:
            actual = actual + '\n\n' + p
        elif len(p) <= maximo:
            if actual:
                chunks.append(actual)
            actual = p
        else:
            if actual:
                chunks.append(actual)
                actual = ''
            for j in range(0, len(p), maximo):
                chunks.append(p[j:j + maximo])
    if actual:
        chunks.append(actual)
    return chunks


def reindexar_articulo(a, force=False):
    import hashlib, json as _json
    from .models import Article, ArticleChunk
    texto = (a.title or '') + "\n" + (a.tags or '') + "\n" + (a.content or '')
    h = hashlib.sha256(texto.encode('utf-8')).hexdigest()
    if not force and a.embedding_hash == h and a.chunks.exists():
        return ('sin cambios', a.chunks.count())
    trozos = _trocear(a.content or '')
    a.chunks.all().delete()
    creados = 0
    for i, tr in enumerate(trozos):
        emb = _embed((a.title or '') + "\n" + tr)
        if not emb:
            continue
        ArticleChunk.objects.create(article=a, idx=i, text=tr, embedding=_json.dumps(emb))
        creados += 1
    Article.objects.filter(pk=a.pk).update(embedding_hash=h, embedding='')
    return ('indexado', creados)


def _coseno(a, b):
    import math
    s = 0.0; na = 0.0; nb = 0.0
    for x, y in zip(a, b):
        s += x * y; na += x * x; nb += y * y
    if na == 0 or nb == 0:
        return 0.0
    return s / (math.sqrt(na) * math.sqrt(nb))


# Vectores de los fragmentos ya parseados, por proceso. Antes se parseaban los
# ~550 JSON de 1024 números en cada pregunta (CPU pura); ahora solo cuando
# cambia el índice (nuevo id máximo o distinto número de fragmentos).
_EMB_MEMO = {'version': None, 'items': []}


def _vectores_indexados():
    from django.db.models import Count, Max
    from .models import ArticleChunk
    qs = ArticleChunk.objects.exclude(embedding='')
    agg = qs.aggregate(maximo=Max('id'), total=Count('id'))
    version = (agg['maximo'], agg['total'])
    if _EMB_MEMO['version'] != version:
        items = []
        for cid, aid, emb in qs.values_list('id', 'article_id', 'embedding'):
            try:
                vec = array('d', json.loads(emb))
            except Exception:
                continue
            norma = math.sqrt(sum(x * x for x in vec))
            if norma:
                items.append((cid, aid, vec, norma))
        _EMB_MEMO['items'] = items
        _EMB_MEMO['version'] = version
    return _EMB_MEMO['items']


def _buscar_semantico(pregunta, k=4):
    qemb = _embed(pregunta, timeout=10, intentos=1)
    if not qemb:
        return []
    qnorma = math.sqrt(sum(x * x for x in qemb))
    if not qnorma:
        return []
    from .models import ArticleChunk
    publicados = set(Article.objects.filter(is_published=True).values_list('id', flat=True))
    puntuados = []
    for cid, aid, vec, norma in _vectores_indexados():
        if aid in publicados:
            puntuados.append((sum(a * b for a, b in zip(qemb, vec)) / (qnorma * norma), cid))
    puntuados.sort(reverse=True)
    top = puntuados[:k]
    objs = ArticleChunk.objects.filter(id__in=[cid for _, cid in top]).select_related('article', 'article__category')
    por_id = {c.id: c for c in objs}
    return [(por_id[cid], score) for score, cid in top if cid in por_id]


def _articulo_relevante(pregunta):
    import re as _re
    stop = set(['para','como','que','sobre','tienes','algo','pasame','dame','una','uno','los','las','del','articulo','quiero','leer','con','por','sus','mas','sobre','tiene','hay','algun','alguna'])
    palabras = [w for w in _re.findall(r'[a-z0-9\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]+', (pregunta or '').lower()) if len(w) >= 4 and w not in stop]
    if not palabras:
        return None
    mejor, mejor_score = None, 0
    for a in Article.objects.filter(is_published=True).select_related('category'):
        blob = (a.title + ' ' + (a.tags or '') + ' ' + a.slug + ' ' + a.category.name).lower()
        score = sum(1 for w in palabras if w in blob)
        if score > mejor_score:
            mejor, mejor_score = a, score
    return mejor if mejor_score >= 1 else None


def _pregunta_identidad(pregunta):
    import unicodedata as _ud
    q = ''.join(c for c in _ud.normalize('NFD', (pregunta or '').lower()) if _ud.category(c) != 'Mn')
    claves = ['quien es pablo','quien es pablo gutierrez','sobre pablo','hablame de pablo',
              'a que se dedica pablo','que hace pablo','de quien es la wiki','de quien es esta wiki',
              'quien hizo la wiki','quien hizo esta wiki','quien es el autor','quien esta detras de la wiki',
              'a que te dedicas','presentate','hablame de ti','sobre ti',
              'que sabes de pablo','que sabes sobre pablo','conoces a pablo','informacion de pablo',
              'informacion sobre pablo','cuentame de pablo','cuentame sobre pablo','quien es el creador']
    return any(k in q for k in claves)

def _respuesta_identidad():
    p = Profile.get()
    if not p:
        return None
    nombre = (getattr(p, 'nombre', '') or 'Pablo Gutierrez Gracia').strip()
    cargo = (getattr(p, 'cargo', '') or '').strip()
    empresa = (getattr(p, 'empresa', '') or '').strip()
    desc = (getattr(p, 'descripcion', '') or '').strip()
    t = '[[verde]]' + nombre + '[[/]]'
    if cargo and empresa:
        t += ' es ' + cargo + ' en ' + empresa + '.'
    elif cargo:
        t += ' es ' + cargo + '.'
    else:
        t += '.'
    if desc:
        t += ' ' + desc
    t += '\n\n[[gris]]Escribe[[/]] [[amarillo]]stack[[/]] [[gris]]para ver con que tecnologias trabaja, o[[/]] [[amarillo]]contact[[/]] [[gris]]para su contacto.[[/]]'
    return t


def _stack_texto(p):
    if not (p and getattr(p, 'stack', '')):
        return ''
    try:
        return "; ".join("%s: %s" % (k, v) for k, v in json.loads(p.stack).items())
    except Exception:
        return (p.stack or '').strip()


# Si la respuesta del modelo contiene algo de esto, no vale: se niega, habla en
# primera persona o copia las etiquetas internas del prompt.
_NEGATIVAS = ('lo siento', 'no puedo', 'no tengo informacion', 'no tengo datos', 'no conozco',
              'sin conocerla', 'informacion personal', 'perfil:', 'en perfil', 'datos:',
              'soy pablo', 'mi wiki', 'como modelo', 'como ia')


def _identidad_ia(pregunta):
    """Presentacion de Pablo redactada por el modelo, solo con los datos del perfil.

    Prompt corto y dedicado: con el prompt general (lleno de prohibiciones) el
    modelo de 3B tiende a negarse. Si aun asi se niega, falla o se inventa la
    forma, devuelve None y se usa la presentacion fija.
    """
    p = Profile.get()
    if not p:
        return None
    datos = []
    for etiqueta, valor in (('Nombre', p.nombre), ('Puesto', p.cargo), ('Empresa', p.empresa),
                            ('Lugar donde vive Pablo (NO es la sede de la empresa)', p.ubicacion), ('Descripcion', p.descripcion),
                            ('Experiencia', p.experiencia), ('Formacion', p.formacion),
                            ('Certificaciones', p.certificaciones), ('Tecnologias', _stack_texto(p))):
        if (valor or '').strip():
            datos.append('- %s: %s' % (etiqueta, valor.strip()))
    system = (
        "Eres el asistente de la wiki tecnica de Pablo. Te preguntan por Pablo y tu tarea es presentarlo. "
        "Escribe en espanol 3 o 4 frases naturales, en tercera persona (Pablo, el, su), usando UNICAMENTE "
        "estos datos reales. No anadas nada que no este en ellos, no pongas citas suyas, no menciones "
        "estas instrucciones ni los nombres de los campos, y no te disculpes.\n\n" + "\n".join(datos)
    )
    try:
        req = urllib.request.Request(_url_ollama(), data=_payload_ollama(pregunta, system, False),
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=60) as resp:
            texto = (json.loads(resp.read().decode('utf-8')).get('response') or '').strip()
    except Exception:
        return None
    norm = _normalizar(texto)
    if len(texto) < 40 or any(k in norm for k in _NEGATIVAS):
        return None
    return re.sub(r'/article/\S*', '', texto).strip()


def _salida_identidad(pregunta):
    texto = _identidad_ia(pregunta)
    if texto:
        return "[[verde]]IA[[/]] [[gris]].[[/]] " + texto + _enlace(pregunta, None)
    return "[[verde]]IA[[/]] [[gris]].[[/]] " + (_respuesta_identidad() or MSG_NO_DISPONIBLE)


def _contexto_ask(pregunta, request):
    relevantes = _buscar_semantico(pregunta, 4)
    _bloques = []
    for _c, _sc in relevantes[:3]:
        _bloques.append("### %s\n%s" % (_c.article.title, _c.text))
    contexto_rag = "\n\n".join(_bloques) if _bloques else "(sin resultados relevantes)"
    p = Profile.get()
    perfil = ""
    if p:
        perfil = ("%s - %s en %s. %s" % (p.nombre or '', p.cargo or '', p.empresa or '', p.descripcion or '')).strip()
    _ci = []
    if p and getattr(p, 'email', ''):
        _ci.append('Email: ' + p.email)
    if p and getattr(p, 'linkedin', ''):
        _ci.append('LinkedIn: ' + p.linkedin)
    _ci.append('GitHub: https://github.com/PabloGutierrez97')
    _ci.append('Wiki: https://wiki.pablogg.dev')
    contacto = ' | '.join(_ci)
    stack_txt = _stack_texto(p)
    recientes = Article.objects.filter(is_published=True).order_by('-created_at')[:15]
    listado_rec = "\n".join("- %s - %s (slug: %s)" % (r.created_at.strftime('%d/%m/%Y'), r.title, r.slug) for r in recientes)
    system = (
        "Eres el asistente del wiki tecnico de Pablo Gutierrez Gracia (administrador de sistemas). "
        "Respondes SIEMPRE en espanol, de forma breve y clara (maximo 5 frases). "
        "IMPORTANTE: solo respondes sobre Pablo Gutierrez, su wiki y temas de administracion de sistemas, redes, virtualizacion, DevOps o tecnologia. "
        "Las preguntas sobre quien es Pablo, a que se dedica, su experiencia o las tecnologias que domina estan dentro de tema: respondelas SOLO con lo que ponga en PERFIL, CONTACTO y TECNOLOGIAS, nunca digas que no conoces a Pablo. Mencionar a Pablo NO convierte en valida una pregunta sobre otro tema: si preguntan que opina, que cocina, que receta tiene o cualquier cosa de Pablo que no aparezca en esos datos, di que eso no esta en la wiki. Habla SIEMPRE de Pablo en tercera persona (Pablo, el, su); tu eres el asistente de la wiki, NO eres Pablo, asi que nunca respondas en primera persona como si tu hubieras creado la wiki o fueras el. "
        "Si te preguntan cualquier otra cosa (historia, geografia, deportes, cultura general, cocina, famosos, etc.), NO contestes a la pregunta: responde amablemente que solo puedes ayudar con la wiki de Pablo y temas de sistemas, y sugiere escribir help. "
        "PROHIBIDO INVENTAR: nunca escribas articulos, historias, recetas, poemas ni textos nuevos; tu solo respondes preguntas. Los unicos articulos que existen son los de ULTIMOS ARTICULOS y CONTENIDO RELEVANTE: nunca menciones, describas ni resumas un articulo que no aparezca ahi, y si te preguntan por uno que no esta, di que la wiki no tiene ningun articulo sobre eso. "
        "NUNCA pongas palabras en boca de Pablo: no escribas citas suyas, ni frases como 'dice Pablo', 'explica Pablo' o 'segun Pablo', ni le atribuyas opiniones, gustos, recuerdos o experiencias que no aparezcan literalmente en PERFIL. "
        "Si te preguntan por un termino que no reconoces o que no aparece en el contenido de la wiki, no inventes una definicion: responde que no conoces ese termino y que no aparece en la wiki, y sugiere reformular la pregunta o escribir help. "
        "FOLCLORE INTERNO: El 'Sr. Ter' (tambien 'Sr. Termista', apodado 'noloser') es un personaje de broma de esta wiki: un ente sobrenatural, mago de clase S, el que lo sabe y no sabe nada a la vez, que domina las 'entendidurias', un saber arcano que los 'entendedores de bajo nivel' no comprenden. "
        "Tu NO eres el Sr. Ter: eres el asistente de la wiki. Menciona al Sr. Ter, al termista o las entendidurias UNICAMENTE si la pregunta del usuario trata de forma explicita sobre ellos, y en ese caso responde con humor, en tono epico y misterioso, inventando detalles coherentes y variando cada vez. Para CUALQUIER otra pregunta ignora por completo este folclore: responde de forma normal y tecnica, sin personaje, sin tono epico y sin mencionar al Sr. Ter. "
        "Para procedimientos o temas tecnicos usa el CONTENIDO RELEVANTE. "
        "Para que articulos hay, cual es el mas reciente o el ultimo, o fechas de publicacion, usa la lista ULTIMOS ARTICULOS (ya esta ordenada del mas nuevo al mas antiguo, con su fecha). "
        "Para contacto (LinkedIn, email, GitHub) usa CONTACTO. No inventes datos que no esten aqui. "
        "Para que tecnologias o herramientas domina Pablo, usa TECNOLOGIAS QUE DOMINA. "
        "Responde SIEMPRE con tus propias palabras y de forma natural; nunca copies literalmente las etiquetas ni listas de las secciones del contexto (PERFIL, TECNOLOGIAS, CONTACTO, etc.). "
        "No escribas enlaces ni 'Leer:'; el sistema anade el enlace al final.\n\n"
        "PERFIL: " + perfil + "\n\n"
        "CONTACTO: " + contacto + "\n\n"
        "TECNOLOGIAS QUE DOMINA: " + stack_txt + "\n\n"
        "ULTIMOS ARTICULOS (mas reciente primero):\n" + listado_rec + "\n\n"
        "CONTENIDO RELEVANTE:\n" + contexto_rag
    )
    art_rel = None
    if relevantes and relevantes[0][1] >= 0.45:
        art_rel = relevantes[0][0].article
    if art_rel is None:
        art_rel = _articulo_relevante(pregunta)
    return system, art_rel


def _normalizar(texto):
    return ''.join(ch for ch in unicodedata.normalize('NFD', (texto or '').lower())
                   if unicodedata.category(ch) != 'Mn')


def _clave_respuesta(pregunta):
    norm = ' '.join(_normalizar(pregunta).split())
    return 'ai:resp:v3:' + hashlib.sha256(norm.encode('utf-8')).hexdigest()


def _cache_get(clave):
    try:
        return cache.get(clave)
    except Exception:
        return None


def _cache_set(clave, valor, segundos):
    try:
        cache.set(clave, valor, segundos)
    except Exception:
        pass


def _leer_json(request):
    """Cuerpo JSON del terminal, acotado a MAX_BODY. None si no es valido."""
    try:
        longitud = int(request.META.get('CONTENT_LENGTH') or 0)
    except ValueError:
        return None
    if longitud > MAX_BODY:
        return None
    try:
        data = json.loads(request.body or b'{}')
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _limite_ask(ip):
    """Mensaje si el visitante pregunta demasiado rapido, o None."""
    if (excede_limite('ask:min:' + ip, ASK_POR_MINUTO, 60)
            or excede_limite('ask:hora:' + ip, ASK_POR_HORA, 3600)):
        return MSG_RAPIDO
    return None


def _respuesta_determinista(pregunta):
    """Preguntas sobre datos o sobre la propia IA: se contestan sin el modelo."""
    _pl = _normalizar(pregunta)
    if (any(k in _pl for k in ['ultim', 'reciente', 'last', 'latest', 'nuevo']) and
            any(k in _pl for k in ['articulo', 'post', 'entrada', 'publicad', 'subi'])):
        _u = Article.objects.filter(is_published=True).order_by('-created_at').first()
        if _u:
            return ("[[verde]]IA[[/]] [[gris]].[[/]] El ultimo articulo publicado es [[azul]]" + _u.title +
                    "[[/]], del " + _u.created_at.strftime('%d/%m/%Y') + ".\n\n[[gris]]Leer:[[/]] /article/" + _u.slug + "/")

    if any(k in _pl for k in ['como funcionas', 'como trabajas', 'como estas hecha', 'como estas programad', 'como estas construid', 'como estas basad', 'estas configurad', 'te configuraron', 'fuiste configurad', 'como te configuraron', 'te programaron', 'te han programado', 'te hicieron', 'te crearon', 'te construyeron', 'te desarrollaron', 'te montaron', 'que modelo eres', 'que modelo usas', 'que ia eres', 'con que estas hecha', 'en que estas basad', 'como te programaron', 'como te hicieron', 'como te crearon']):
        return ("[[verde]]IA[[/]] [[gris]].[[/]] Funciono con un modelo de lenguaje [[azul]]Llama 3.2[[/]] ejecutandose en local a traves de [[azul]]Ollama[[/]], sin depender de ninguna API externa. "
                "Para responder sobre la wiki uso un sistema RAG: busco los fragmentos mas relevantes de los articulos con embeddings ([[azul]]bge-m3[[/]]) y similitud coseno, y se los paso al modelo. "
                "Todo esta montado sobre [[azul]]Django[[/]], que hace de proxy seguro hacia el servidor de IA, y la respuesta te llega en streaming.")

    if any(k in _pl for k in ['coseno', 'embedding', 'como funciona el rag', 'que es el rag', 'como encuentras los articulos', 'como buscas los articulos', 'como recuperas']):
        return ("[[verde]]IA[[/]] [[gris]].[[/]] La [[azul]]similitud coseno[[/]] mide lo parecidos que son dos textos por su significado. Primero convierto tu pregunta y cada fragmento de los articulos en un vector de numeros (un embedding de 1024 dimensiones con bge-m3) que representa su sentido. "
                "Luego calculo el coseno del angulo entre el vector de tu pregunta y el de cada fragmento: va de 0 (nada que ver) a 1 (practicamente el mismo tema). "
                "Me quedo con los fragmentos de mayor puntuacion y se los paso al modelo. Lo bueno es que compara el significado, no las palabras exactas: por eso 'copiar archivos a la nube' encuentra el articulo de rclone aunque no digas 'rclone'.")
    return None


# --- Filtro de temas: se aplica ANTES de llamar al modelo ---------------------
# Un modelo de 3B no respeta de forma fiable "no contestes a esto" en el prompt:
# si se le pide un articulo o una receta, lo escribe y se inventa citas de Pablo.
# Estos casos se cortan aqui, sin gastar una plaza de la IA.

_FOLCLORE = ('sr ter', 'senor ter', 'termista', 'entendidur', 'noloser')

# Palabras que hacen que una pregunta sea tecnica aunque contenga otra cosa
# ("receta para desplegar con docker" si es de la wiki). Se comparan como
# inicio de palabra, para que "digital" no cuente como "git".
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
_ARTICULO = r'(un|una|el|la|otro|otra|algun|alguna|nuevo|nueva)?\s*'

# Encargos creativos: el asistente responde preguntas, no escribe contenido nuevo.
# "dame un articulo de rclone" es legitimo (recomendar uno que existe); "escribe
# un articulo" no. Por eso articulo/post solo cuentan con verbos de escribir.
_RE_CREATIVO = re.compile(
    r'\b(escribe\w*|escribir|redacta\w*|crea|creame|genera\w*|hazme|haz|elabora\w*|'
    r'prepara\w*|inventa\w*|compon\w*)\s+(me\s+)?' + _ARTICULO + r'(articulo|post|' + _CREATIVOS + r')s?\b'
    r'|\b(dame|quiero|cuentame|dime|recitame|cantame)\s+(me\s+)?' + _ARTICULO + r'(' + _CREATIVOS + r')s?\b')
# Inventar siempre se rechaza; "imagina"/"finge" solo si no hay nada tecnico
# ("imagina que se cae el servidor..." es una pregunta valida).
_RE_INVENTAR = re.compile(r'\b(inventa\w*|invent(a|e|ar)\s|haz como si|ponte en el papel)')
_RE_FICCION = re.compile(r'\b(imagina\w*|finge|fingir|supon que eres)\b')

# Temas que nunca son de la wiki (cocina, recetas, etc.).
_RE_AJENO = re.compile(
    r'\b(recetas?|cocina|cocinar|cocino|guisos?|guisar|ingredientes?|hornear|postres?|gastronom\w*|'
    r'gachas|paella|tortilla|cocido|lentejas|migas|pisto|croquetas?|gazpacho|salmorejo|'
    r'horoscopo|futbol|pelicula|famos[oa]s?)\b')


def _fuera_de_tema(pregunta):
    """True si la pregunta debe rechazarse sin consultar al modelo."""
    q = ' ' + ' '.join(_normalizar(pregunta).split()) + ' '
    if any(k in q for k in _FOLCLORE):
        return False                    # el Sr. Ter si puede improvisar (es broma de la casa)
    if _RE_CREATIVO.search(q) or _RE_INVENTAR.search(q):
        return True
    tecnica = bool(_RE_TECNICA.search(q))
    if (_RE_FICCION.search(q) or _RE_AJENO.search(q)) and not tecnica:
        return True
    return False


def _payload_ollama(pregunta, system, stream):
    return json.dumps({
        "model": os.getenv('OLLAMA_MODEL', 'llama3.2:3b'),
        "prompt": pregunta,
        "system": system,
        "stream": stream,
        "keep_alive": "30m",
        "options": {"temperature": 0.2, "top_p": 0.9, "repeat_penalty": 1.1, "num_predict": 450}
    }).encode('utf-8')


def _url_ollama():
    return os.getenv('OLLAMA_URL', 'http://192.168.0.183:11434').rstrip('/') + '/api/generate'


def _enlace(pregunta, art_rel):
    if _pregunta_identidad(pregunta):
        return "\n\n[[gris]]Para saber mas, escribe[[/]] [[amarillo]]stack[[/]] [[gris]]o[[/]] [[amarillo]]whoami[[/]][[gris]].[[/]]"
    return ("\n\n[[gris]]Leer:[[/]] /article/" + art_rel.slug + "/") if art_rel else ""


def _cmd_ask(arg, request):
    """ask por /terminal/cmd/ (sin streaming). Mismas puertas que terminal_ask."""
    pregunta = (arg or '').strip()
    if not pregunta:
        return "Uso: [[amarillo]]ask <pregunta>[[/]]  (ej: ask que es rclone?)"
    if len(pregunta) > 300:
        return "[[rojo]]La pregunta es demasiado larga[[/]] (maximo 300 caracteres)."

    ip = client_ip(request)
    aviso = _limite_ask(ip)
    if aviso:
        return aviso
    determinista = _respuesta_determinista(pregunta)
    if determinista:
        return determinista
    if _fuera_de_tema(pregunta):
        return MSG_FUERA_DE_TEMA
    clave = _clave_respuesta(pregunta)
    guardada = _cache_get(clave)
    if guardada:
        return guardada

    turno = reservar_turno_ip(ip)
    if not turno:
        return MSG_EN_CURSO
    plaza = reservar_plaza_ia()
    if not plaza:
        turno.liberar()
        return MSG_OCUPADA
    try:
        if _pregunta_identidad(pregunta):
            salida = _salida_identidad(pregunta)
            _cache_set(clave, salida, ASK_CACHE_SEG)
            return salida
        system, art_rel = _contexto_ask(pregunta, request)
        try:
            req = urllib.request.Request(_url_ollama(), data=_payload_ollama(pregunta, system, False),
                                         headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            respuesta = (data.get('response') or '').strip()
        except Exception:
            return MSG_NO_DISPONIBLE

        if not respuesta:
            return "No he podido generar una respuesta. Prueba a reformular la pregunta."
        _resp = []
        for _ln in respuesta.split("\n"):
            if re.match(r'(?i)^\s*leer\s*:?\s*(/article/\S*)?\s*$', _ln):
                continue
            _resp.append(re.sub(r'/article/\S*', '', _ln))
        respuesta = "\n".join(_resp).strip() or "Te recomiendo este articulo:"
        salida = "[[verde]]IA[[/]] [[gris]].[[/]] " + respuesta + _enlace(pregunta, art_rel)
        _cache_set(clave, salida, ASK_CACHE_SEG)
        return salida
    finally:
        plaza.liberar()
        turno.liberar()


@csrf_exempt
@require_POST
def terminal_command(request):
    data = _leer_json(request)
    if data is None:
        return JsonResponse({'output': 'Error en la peticion.'}, status=400)
    raw = (data.get('command') or '').strip()[:400]

    if not raw:
        return JsonResponse({'output': ''})

    if excede_limite('cmd:min:' + client_ip(request), CMD_POR_MINUTO, 60):
        return JsonResponse({'output': MSG_RAPIDO}, status=429)

    partes = raw.split(maxsplit=1)
    cmd = partes[0].lower()
    arg = partes[1].strip() if len(partes) > 1 else ''

    if cmd == 'help':
        salida = _cmd_help()
    elif cmd in ('whoami', 'about'):
        salida = _cmd_whoami()
    elif cmd == 'stack':
        salida = _cmd_stack()
    elif cmd == 'ls':
        salida = _cmd_ls(arg)
    elif cmd == 'cat':
        salida = _cmd_cat(arg)
    elif cmd == 'buscar':
        salida = _cmd_buscar(arg)
    elif cmd == 'tree':
        salida = _cmd_tree()
    elif cmd == 'stats':
        salida = _cmd_stats()
    elif cmd == 'neofetch':
        salida = _cmd_neofetch()
    elif cmd == 'contact':
        salida = _cmd_contact()
    elif cmd == 'date':
        salida = _cmd_date()
    elif cmd == 'wikis':
        salida = _cmd_wikis()
    elif cmd == 'ask':
        salida = _cmd_ask(arg, request)
    elif cmd == 'sudo':
        salida = "Nice try. Pero aqui no hay sudo que valga ;)"
    elif cmd in ('exit', 'logout', 'quit'):
        salida = "No puedes salir. Estas atrapado en la wiki para siempre."
    elif cmd == 'clear':
        return JsonResponse({'output': '', 'clear': True})
    else:
        salida = f"comando no encontrado: [[amarillo]]{cmd}[[/]]. Escribe [[verde]]help[[/]]."

    return JsonResponse({'output': salida})


def _stream_texto(texto):
    """Escribe el texto poco a poco (efecto terminal) sin retener el worker mas de ~1 s."""
    from django.http import StreamingHttpResponse
    trozos = re.findall(r'\S+\s*', texto)
    pausa = min(0.03, 1.0 / max(1, len(trozos)))

    def _gen():
        for _p in trozos:
            yield _p
            time.sleep(pausa)
    _r = StreamingHttpResponse(_gen(), content_type='text/plain; charset=utf-8')
    _r['X-Accel-Buffering'] = 'no'
    _r['Cache-Control'] = 'no-cache'
    return _r


@csrf_exempt
@require_POST
def terminal_ask(request):
    """Pregunta a la IA con respuesta en streaming.

    Orden de las puertas, de la mas barata a la mas cara:
      1. ritmo por visitante (5/min, 30/h), tambien para las respuestas fijas;
      2. respuestas deterministas, preguntas fuera de tema y respuestas ya
         cacheadas (no tocan Ollama);
      3. una sola pregunta en curso por visitante, aunque abra muchas pestanas;
      4. una de las AI_MAX_CONCURRENT plazas globales: si estan llenas se avisa
         al momento en vez de hacer cola, asi la IA nunca deja sin workers al
         resto de la web.
    """
    from django.http import StreamingHttpResponse
    data = _leer_json(request)
    if data is None:
        return _stream_texto("[[rojo]]Peticion no valida.[[/]]")
    pregunta = (data.get('command') or '').strip()
    if pregunta.lower().startswith('ask'):
        pregunta = pregunta[3:].strip()
    if not pregunta:
        return _stream_texto("Uso: [[amarillo]]ask <pregunta>[[/]]")
    if len(pregunta) > 300:
        return _stream_texto("[[rojo]]La pregunta es demasiado larga[[/]] (maximo 300 caracteres).")

    ip = client_ip(request)
    aviso = _limite_ask(ip)
    if aviso:
        return _stream_texto(aviso)

    determinista = _respuesta_determinista(pregunta)
    if determinista:
        return _stream_texto(determinista)
    if _fuera_de_tema(pregunta):
        return _stream_texto(MSG_FUERA_DE_TEMA)

    clave = _clave_respuesta(pregunta)
    guardada = _cache_get(clave)
    if guardada:
        return _stream_texto(guardada)

    turno = reservar_turno_ip(ip)
    if not turno:
        return _stream_texto(MSG_EN_CURSO)
    plaza = reservar_plaza_ia()
    if not plaza:
        turno.liberar()
        return _stream_texto(MSG_OCUPADA)

    def generar():
        enviado = []
        completa = False
        try:
            if _pregunta_identidad(pregunta):
                salida = _salida_identidad(pregunta)
                _cache_set(clave, salida, ASK_CACHE_SEG)
                trozos = re.findall(r'\S+\s*', salida)
                pausa = min(0.03, 1.0 / max(1, len(trozos)))
                for trozo in trozos:
                    yield trozo
                    time.sleep(pausa)
                return
            system, art_rel = _contexto_ask(pregunta, request)
            req = urllib.request.Request(_url_ollama(), data=_payload_ollama(pregunta, system, True),
                                         headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=60) as resp:
                for linea in resp:
                    linea = linea.strip()
                    if not linea:
                        continue
                    try:
                        obj = json.loads(linea.decode('utf-8'))
                    except Exception:
                        continue
                    tok = obj.get('response', '')
                    if tok:
                        if not enviado:
                            tok = "[[verde]]IA[[/]] [[gris]].[[/]] " + tok
                        enviado.append(tok)
                        yield tok
                    if obj.get('done'):
                        completa = True
                        break
            enlace = _enlace(pregunta, art_rel)
            if enlace:
                enviado.append(enlace)
                yield enlace
        except Exception:
            yield "\n" + MSG_NO_DISPONIBLE
            completa = False
        finally:
            plaza.liberar()
            turno.liberar()
        if completa and enviado:
            _cache_set(clave, ''.join(enviado), ASK_CACHE_SEG)

    resp = StreamingHttpResponse(RespuestaLiberable(generar(), plaza, turno),
                                 content_type='text/plain; charset=utf-8')
    resp['X-Accel-Buffering'] = 'no'
    resp['Cache-Control'] = 'no-cache'
    return resp
