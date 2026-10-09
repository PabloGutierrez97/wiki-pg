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

    system = (
        "Eres el asistente del wiki tecnico de Pablo Gutierrez Gracia (administrador de sistemas). "
        "Respondes SIEMPRE en espanol, de forma breve y clara (maximo 5 frases). "
        "Solo hablas sobre Pablo, su wiki y temas de administracion de sistemas / DevOps. "
        "Si la pregunta no tiene relacion, dilo amablemente y sugiere escribir 'help'. "
        "Si procede, menciona el articulo relevante por su titulo. No inventes articulos que no esten en la lista.\n\n"
        "PERFIL: " + perfil + "\n\n"
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
        "options": {"temperature": 0.3, "num_predict": 256}
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
    return "[[verde]]IA[[/]] [[gris]].[[/]] " + respuesta


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
