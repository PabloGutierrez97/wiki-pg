from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
import json
import re

from .models import Article, Category, Profile
import os
import urllib.request
from django.core.cache import cache


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


def _embed(texto):
    url = os.getenv('OLLAMA_URL', 'http://192.168.0.183:11434').rstrip('/') + '/api/embeddings'
    modelo = os.getenv('OLLAMA_EMBED_MODEL', 'bge-m3')
    payload = json.dumps({"model": modelo, "prompt": (texto or '')[:3000], "keep_alive": "5m"}).encode('utf-8')
    import time as _time
    for _i in range(2):
        try:
            req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            emb = data.get('embedding')
            if emb:
                return emb
        except Exception:
            pass
        _time.sleep(0.8)
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


def _buscar_semantico(pregunta, k=4):
    qemb = _embed(pregunta)
    if not qemb:
        return []
    import json as _json
    from .models import ArticleChunk
    res = []
    for c in ArticleChunk.objects.exclude(embedding='').select_related('article', 'article__category'):
        if not c.article.is_published:
            continue
        try:
            emb = _json.loads(c.embedding)
        except Exception:
            continue
        res.append((c, _coseno(qemb, emb)))
    res.sort(key=lambda t: t[1], reverse=True)
    return res[:k]


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


def _cmd_ask(arg, request):
    pregunta = (arg or '').strip()
    if not pregunta:
        return "Uso: [[amarillo]]ask <pregunta>[[/]]  (ej: ask que es rclone?)"
    if len(pregunta) > 300:
        return "[[rojo]]La pregunta es demasiado larga[[/]] (maximo 300 caracteres)."

    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    ip = (request.META.get('HTTP_CF_CONNECTING_IP')
          or (xff.split(',')[0].strip() if xff else '')
          or request.META.get('REMOTE_ADDR', 'anon'))
    rl_key = 'ask_rl_' + ip
    try:
        usos = cache.get(rl_key, 0)
        if usos >= 6:
            return "[[amarillo]]Vas muy rapido.[[/]] Espera un minuto antes de volver a preguntar."
        cache.set(rl_key, usos + 1, 60)
    except Exception:
        pass

    p = Profile.get()
    perfil = ""
    if p:
        perfil = "%s - %s en %s. %s" % (p.nombre or '', p.cargo or '', p.empresa or '', p.descripcion or '')
        perfil = perfil.strip()
    arts = Article.objects.filter(is_published=True).select_related('category').order_by('-created_at')[:25]
    listado = "\n".join("- [%s] %s (slug: %s)" % (a.category.name, a.title, a.slug) for a in arts)
    contacto_items = []
    if p and getattr(p, 'email', ''):
        contacto_items.append('Email: ' + p.email)
    if p and getattr(p, 'linkedin', ''):
        contacto_items.append('LinkedIn: ' + p.linkedin)
    contacto_items.append('GitHub: https://github.com/PabloGutierrez97')
    contacto_items.append('Wiki: https://wiki.pablogg.dev')
    contacto = ' | '.join(contacto_items)
    relevantes = _buscar_semantico(pregunta, 4)
    _bloques = []
    for _c, _sc in relevantes[:3]:
        _bloques.append("### %s\n%s" % (_c.article.title, _c.text))
    contexto_rag = "\n\n".join(_bloques) if _bloques else "(sin resultados relevantes)"

    system = (
        "Eres el asistente del wiki tecnico de Pablo Gutierrez Gracia (administrador de sistemas). "
        "Respondes SIEMPRE en espanol, de forma breve y clara (maximo 5 frases). "
        "Solo hablas sobre Pablo, su wiki y temas de administracion de sistemas / DevOps. "
        "Si la pregunta no tiene relacion, dilo amablemente y sugiere escribir 'help'. "
        "Si recomiendas un articulo, di su titulo y en una linea aparte escribe 'Leer: /article/<slug>/' usando el slug EXACTO de la lista, para que el enlace sea clicable. "
        "No inventes articulos ni datos que no esten en el contexto; si no lo sabes, dilo claramente. "
        "Responde basandote sobre todo en el CONTENIDO RELEVANTE que te paso; si la respuesta no esta ahi, dilo. "
        "Si preguntan por contacto (LinkedIn, email, GitHub, wiki), usa los datos de la seccion CONTACTO.\n\n"
        "EJEMPLOS:\n"
        "P: tienes algo sobre zabbix? R: Si. Por ejemplo 'Zabbix con proxies: monitorizar sedes remotas sin abrir 20 puertos'.\nLeer: /article/zabbix-proxies-sedes-remotas/\n"
        "P: receta de tortilla? R: Solo ayudo con la wiki de Pablo y temas de administracion de sistemas. Escribe help para ver que puedo hacer.\n\n"
        "PERFIL: " + perfil + "\n\n"
        "CONTACTO: " + contacto + "\n\n"
        "CONTENIDO RELEVANTE:\n" + contexto_rag + "\n\n"
        "ARTICULOS PUBLICADOS:\n" + listado
    )

    url = os.getenv('OLLAMA_URL', 'http://192.168.0.183:11434').rstrip('/') + '/api/generate'
    modelo = os.getenv('OLLAMA_MODEL', 'llama3.2:3b')
    payload = json.dumps({
        "model": modelo,
        "prompt": pregunta,
        "system": system,
        "stream": False,
        "keep_alive": "30m",
        "options": {"temperature": 0.3, "top_p": 0.9, "repeat_penalty": 1.1, "num_predict": 450}
    }).encode('utf-8')

    try:
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        respuesta = (data.get('response') or '').strip()
    except Exception:
        return "[[rojo]]La IA no esta disponible ahora mismo.[[/]] Intentalo de nuevo en un momento."

    if not respuesta:
        return "No he podido generar una respuesta. Prueba a reformular la pregunta."
    import re as _re
    _resp = []
    for _ln in respuesta.split("\n"):
        if _re.match(r'(?i)^\s*leer\s*:?\s*(/article/\S*)?\s*$', _ln):
            continue
        _resp.append(_re.sub(r'/article/\S*', '', _ln))
    respuesta = "\n".join(_resp).strip()
    if not respuesta:
        respuesta = "Te recomiendo este articulo:"
    salida = "[[verde]]IA[[/]] [[gris]].[[/]] " + respuesta
    art_rel = None
    if relevantes and relevantes[0][1] >= 0.45:
        art_rel = relevantes[0][0].article
    if art_rel is None:
        art_rel = _articulo_relevante(pregunta)
    if art_rel:
        salida += "\n\n[[gris]]Leer:[[/]] /article/" + art_rel.slug + "/"
    return salida


@csrf_exempt
@require_POST
def terminal_command(request):
    try:
        data = json.loads(request.body)
        raw = (data.get('command') or '').strip()
    except Exception:
        return JsonResponse({'output': 'Error en la peticion.'})

    if not raw:
        return JsonResponse({'output': ''})

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


@csrf_exempt
@require_POST
def terminal_ask(request):
    from django.http import StreamingHttpResponse, HttpResponse
    try:
        data = json.loads(request.body)
        pregunta = (data.get('command') or '').strip()
    except Exception:
        pregunta = ''
    if pregunta.lower().startswith('ask'):
        pregunta = pregunta[3:].strip()
    if not pregunta:
        return HttpResponse("Uso: [[amarillo]]ask <pregunta>[[/]]", content_type='text/plain; charset=utf-8')
    if len(pregunta) > 300:
        return HttpResponse("[[rojo]]La pregunta es demasiado larga[[/]] (maximo 300 caracteres).", content_type='text/plain; charset=utf-8')

    import unicodedata as _ud
    _pl = ''.join(ch for ch in _ud.normalize('NFD', pregunta.lower()) if _ud.category(ch) != 'Mn')
    if (any(k in _pl for k in ['ultim', 'reciente', 'last', 'latest', 'nuevo']) and
            any(k in _pl for k in ['articulo', 'post', 'entrada', 'publicad', 'subi'])):
        _u = Article.objects.filter(is_published=True).order_by('-created_at').first()
        if _u:
            _t = ("[[verde]]IA[[/]] [[gris]].[[/]] El ultimo articulo publicado es [[azul]]" + _u.title +
                  "[[/]], del " + _u.created_at.strftime('%d/%m/%Y') + ".\n\n[[gris]]Leer:[[/]] /article/" + _u.slug + "/")
            return HttpResponse(_t, content_type='text/plain; charset=utf-8')

    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    ip = (request.META.get('HTTP_CF_CONNECTING_IP')
          or (xff.split(',')[0].strip() if xff else '')
          or request.META.get('REMOTE_ADDR', 'anon'))
    try:
        usos = cache.get('ask_rl_' + ip, 0)
        if usos >= 6:
            return HttpResponse("[[amarillo]]Vas muy rapido.[[/]] Espera un minuto antes de volver a preguntar.", content_type='text/plain; charset=utf-8')
        cache.set('ask_rl_' + ip, usos + 1, 60)
    except Exception:
        pass

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
    recientes = Article.objects.filter(is_published=True).order_by('-created_at')[:15]
    listado_rec = "\n".join("- %s - %s (slug: %s)" % (r.created_at.strftime('%d/%m/%Y'), r.title, r.slug) for r in recientes)
    system = (
        "Eres el asistente del wiki tecnico de Pablo Gutierrez Gracia (administrador de sistemas). "
        "Respondes SIEMPRE en espanol, de forma breve y clara (maximo 5 frases). "
        "Para procedimientos o temas tecnicos usa el CONTENIDO RELEVANTE. "
        "Para que articulos hay, cual es el mas reciente o el ultimo, o fechas de publicacion, usa la lista ULTIMOS ARTICULOS (ya esta ordenada del mas nuevo al mas antiguo, con su fecha). "
        "Para contacto (LinkedIn, email, GitHub) usa CONTACTO. No inventes datos que no esten aqui. "
        "No escribas enlaces ni 'Leer:'; el sistema anade el enlace al final.\n\n"
        "PERFIL: " + perfil + "\n\n"
        "CONTACTO: " + contacto + "\n\n"
        "ULTIMOS ARTICULOS (mas reciente primero):\n" + listado_rec + "\n\n"
        "CONTENIDO RELEVANTE:\n" + contexto_rag
    )
    art_rel = None
    if relevantes and relevantes[0][1] >= 0.45:
        art_rel = relevantes[0][0].article
    if art_rel is None:
        art_rel = _articulo_relevante(pregunta)
    link = ("\n\n[[gris]]Leer:[[/]] /article/" + art_rel.slug + "/") if art_rel else ""

    url = os.getenv('OLLAMA_URL', 'http://192.168.0.183:11434').rstrip('/') + '/api/generate'
    modelo = os.getenv('OLLAMA_MODEL', 'llama3.2:3b')
    payload = json.dumps({
        "model": modelo, "prompt": pregunta, "system": system, "stream": True,
        "keep_alive": "30m",
        "options": {"temperature": 0.3, "top_p": 0.9, "repeat_penalty": 1.1, "num_predict": 450}
    }).encode('utf-8')

    def generar():
        primero = True
        try:
            req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
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
                        if primero:
                            yield "[[verde]]IA[[/]] [[gris]].[[/]] " + tok
                            primero = False
                        else:
                            yield tok
                    if obj.get('done'):
                        break
        except Exception:
            yield "\n[[rojo]]La IA no esta disponible ahora mismo.[[/]]"
        if link:
            yield link

    resp = StreamingHttpResponse(generar(), content_type='text/plain; charset=utf-8')
    resp['X-Accel-Buffering'] = 'no'
    resp['Cache-Control'] = 'no-cache'
    return resp
