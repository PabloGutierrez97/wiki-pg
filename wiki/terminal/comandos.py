"""Comandos del terminal de la wiki.

Para añadir uno basta con escribir una función que reciba el argumento (texto)
y devuelva la salida, y decorarla con @comando. La ayuda se genera sola a
partir del registro, en el orden en que se declaran.

La salida usa el marcado de colores del widget: [[verde]]texto[[/]].
"""
import re
from dataclasses import dataclass, field

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from ..models import Article, Category, Profile


@dataclass(frozen=True)
class Comando:
    nombre: str
    funcion: object
    uso: str = ''
    ayuda: str = ''
    alias: tuple = field(default_factory=tuple)


REGISTRO = {}
_ORDEN = []


def comando(nombre, uso='', ayuda='', alias=()):
    """Registra un comando. Sin `ayuda` no aparece en `help` (comandos ocultos)."""
    def registrar(funcion):
        cmd = Comando(nombre, funcion, uso, ayuda, tuple(alias))
        for n in (nombre, *alias):
            REGISTRO[n] = cmd
        _ORDEN.append(cmd)
        return funcion
    return registrar


def ejecutar(nombre, arg):
    """Salida del comando, o None si no existe."""
    cmd = REGISTRO.get(nombre)
    return cmd.funcion(arg) if cmd else None


def _publicados():
    return Article.objects.publicados()


def _fecha(dt):
    return dt.strftime('%d/%m/%Y')


# ------------------------------------------------------------------ comandos --

@comando('help', ayuda='Muestra esta ayuda')
def help_(arg):
    lineas = ["[[verde]]Comandos disponibles:[[/]]", ""]
    for cmd in _ORDEN:
        if not cmd.ayuda:
            continue
        uso = " [[gris]]%s[[/]]" % cmd.uso if cmd.uso else ""
        relleno = " " * max(1, 18 - len(cmd.nombre) - (len(cmd.uso) + 1 if cmd.uso else 0))
        lineas.append("  [[amarillo]]%s[[/]]%s%s%s" % (cmd.nombre, uso, relleno, cmd.ayuda))
        for variante, texto in getattr(cmd.funcion, 'variantes', ()):
            relleno = " " * max(1, 18 - len(cmd.nombre) - len(variante) - 1)
            lineas.append("  [[amarillo]]%s[[/]] [[gris]]%s[[/]]%s%s" % (cmd.nombre, variante, relleno, texto))
    return "\n".join(lineas)


@comando('whoami', ayuda='Informacion sobre Pablo', alias=('about',))
def whoami(arg):
    p = Profile.get()
    lineas = [
        f"[[verde]]{p.nombre or ''}[[/]]",
        f"[[azul]]{p.cargo or ''}[[/]] en [[azul]]{p.empresa or ''}[[/]]",
        f"[[gris]]{p.ubicacion or ''}[[/]]",
    ]
    if p.descripcion:
        lineas += ["", p.descripcion]
    return "\n".join(l for l in lineas if l)


@comando('ls', ayuda='Lista las categorias')
def ls(arg):
    if not arg:
        cats = Category.objects.annotate(n=Count('articles', filter=Q(articles__is_published=True))).order_by('name')
        if not cats:
            return "No hay categorias."
        lineas = ["[[gris]]Categorias disponibles:[[/]]", ""]
        lineas += [f"  [[verde]]{c.slug}/[[/]]   {c.name} [[gris]]({c.n} articulos)[[/]]" for c in cats]
        return "\n".join(lineas)
    q = arg.strip().rstrip('/')
    cat = (Category.objects.filter(slug__iexact=q).first()
           or Category.objects.filter(name__iexact=q).first()
           or Category.objects.filter(name__icontains=q).first()
           or Category.objects.filter(slug__icontains=q).first())
    if not cat:
        return f"Categoria '[[amarillo]]{arg}[[/]]' no encontrada. Usa [[amarillo]]ls[[/]] para verlas."
    arts = _publicados().filter(category=cat).order_by('-created_at')
    if not arts:
        return f"No hay articulos en '{cat.name}'."
    lineas = [f"[[gris]]Articulos en[[/]] [[verde]]{cat.name}[[/]][[gris]]:[[/]]", ""]
    for a in arts:
        lineas += [f"  [[azul]]{a.slug}[[/]]", f"    {a.title} [[gris]]· {_fecha(a.created_at)}[[/]]"]
    return "\n".join(lineas)


ls.variantes = (('<categoria>', 'Lista articulos de una categoria'),)


@comando('cat', uso='<slug>', ayuda='Muestra el resumen de un articulo')
def cat(arg):
    if not arg:
        return "Uso: [[amarillo]]cat <slug-del-articulo>[[/]]"
    art = _publicados().filter(slug__iexact=arg).select_related('category').first()
    if not art:
        return f"Articulo '[[amarillo]]{arg}[[/]]' no encontrado. Usa [[amarillo]]ls[[/]] para ver los disponibles."
    resumen = re.sub(r'[#*`>_\[\]()]', '', art.content).strip()[:400]
    lineas = [
        f"[[verde]]{art.title}[[/]]",
        f"[[gris]]Categoria:[[/]] {art.category.name}  [[gris]]·[[/]]  [[gris]]{_fecha(art.created_at)}[[/]]  "
        f"[[gris]]·[[/]]  [[gris]]{art.minutos_lectura} min de lectura[[/]]",
    ]
    if art.tag_list:
        lineas.append("[[gris]]Tags:[[/]] " + " ".join(f"[[amarillo]]#{t}[[/]]" for t in art.tag_list))
    lineas += ["", f"{resumen}...", "", f"[[gris]]Leer completo:[[/]] {art.get_absolute_url()}"]
    return "\n".join(lineas)


@comando('buscar', uso='<texto>', ayuda='Busca articulos por palabra')
def buscar(arg):
    if not arg:
        return "Uso: [[amarillo]]buscar <texto>[[/]]"
    arts = _publicados().filter(
        Q(title__icontains=arg) | Q(content__icontains=arg) |
        Q(tags__icontains=arg) | Q(category__name__icontains=arg)
    ).select_related('category').distinct()[:8]
    if not arts:
        return f"Sin resultados para '[[amarillo]]{arg}[[/]]'."
    lineas = [f"[[verde]]{len(arts)}[[/]] [[gris]]resultado(s) para[[/]] '[[amarillo]]{arg}[[/]]':", ""]
    for a in arts:
        lineas += [f"  [[gris]][{a.category.name}][[/]] [[azul]]{a.slug}[[/]]", f"    {a.title}"]
    return "\n".join(lineas)


@comando('tree', ayuda='Estructura completa de la wiki')
def tree(arg):
    cats = list(Category.objects.order_by('name'))
    if not cats:
        return "No hay categorias."
    por_cat = {}
    for a in _publicados().order_by('-created_at').only('slug', 'category_id'):
        por_cat.setdefault(a.category_id, []).append(a.slug)
    lineas = ["[[verde]]" + settings.SITE_URL.split('://')[-1] + "[[/]]"]
    for i, c in enumerate(cats):
        ultima_cat = i == len(cats) - 1
        lineas.append(f"[[gris]]{'└──' if ultima_cat else '├──'}[[/]] [[amarillo]]{c.name}/[[/]]")
        prefijo = "    " if ultima_cat else "[[gris]]│[[/]]   "
        slugs = por_cat.get(c.id, [])
        for j, slug in enumerate(slugs):
            lineas.append(f"{prefijo}[[gris]]{'└──' if j == len(slugs) - 1 else '├──'}[[/]] [[azul]]{slug}[[/]]")
    return "\n".join(lineas)


@comando('stack', ayuda='Muestra el stack tecnologico')
def stack(arg):
    p = Profile.get()
    if not p.stack:
        return "Stack no configurado."
    data = p.stack_dict()
    if not data:
        return p.stack
    return "\n".join(f"  [[amarillo]]{k}:[[/]] {v}" for k, v in data.items())


@comando('stats', ayuda='Estadisticas de la wiki')
def stats(arg):
    publicados = _publicados()
    ultimo = publicados.order_by('-created_at').first()
    palabras = sum(len(c.split()) for c in publicados.values_list('content', flat=True))
    lineas = [
        "[[verde]]Estadisticas de la wiki[[/]]",
        "",
        f"  [[amarillo]]Articulos publicados:[[/]] {publicados.count()}",
        f"  [[amarillo]]Categorias:[[/]] {Category.objects.count()}",
        f"  [[amarillo]]Palabras totales:[[/]] {palabras:,}".replace(",", "."),
    ]
    if ultimo:
        lineas.append(f"  [[amarillo]]Ultimo articulo:[[/]] {ultimo.title} [[gris]]({_fecha(ultimo.created_at)})[[/]]")
    return "\n".join(lineas)


_LOGO = (
    "[[verde]]    ____  ______[[/]]",
    "[[verde]]   / __ \\/ ____/[[/]]",
    "[[verde]]  / /_/ / / __[[/]]  ",
    "[[verde]] / ____/ /_/ /[[/]]  ",
    "[[verde]]/_/    \\____/[[/]]   ",
)


@comando('neofetch', ayuda='Resumen del sistema')
def neofetch(arg):
    p = Profile.get()
    info = [
        f"[[amarillo]]{p.nombre}[[/]]",
        "[[gris]]-------------------[[/]]",
        f"[[amarillo]]Cargo:[[/]] {p.cargo}",
        f"[[amarillo]]Host:[[/]] {settings.SITE_URL.split('://')[-1]}",
        "[[amarillo]]OS:[[/]] Django 6 + PostgreSQL",
        "[[amarillo]]Infra:[[/]] Proxmox LXC + Cloudflare",
        f"[[amarillo]]Articulos:[[/]] {_publicados().count()}",
        f"[[amarillo]]Categorias:[[/]] {Category.objects.count()}",
    ]
    filas = max(len(_LOGO), len(info))
    return "\n".join(
        f"{_LOGO[i] if i < len(_LOGO) else ' ' * 15}   {info[i] if i < len(info) else ''}" for i in range(filas))


@comando('contact', ayuda='Enlaces de contacto')
def contact(arg):
    p = Profile.get()
    lineas = ["[[verde]]Contacto[[/]]", ""]
    if p.email:
        lineas.append(f"  [[amarillo]]Email:[[/]]    {p.email}")
    if p.linkedin:
        lineas.append(f"  [[amarillo]]LinkedIn:[[/]] {p.linkedin}")
    lineas.append(f"  [[amarillo]]GitHub:[[/]]   {settings.GITHUB_URL}")
    lineas.append(f"  [[amarillo]]Wiki:[[/]]     {settings.SITE_URL}")
    return "\n".join(lineas)


_DIAS = ('Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado', 'Domingo')
_MESES = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
          'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')


@comando('date', ayuda='Fecha y hora actual')
def date(arg):
    ahora = timezone.localtime()
    return (f"[[verde]]{_DIAS[ahora.weekday()]} {ahora.day} de {_MESES[ahora.month - 1]} de {ahora.year}[[/]]"
            f" - [[amarillo]]{ahora.strftime('%H:%M:%S')}[[/]]")


# `ask` se resuelve en views.py porque necesita la petición (IP del visitante);
# aquí solo se registra para que salga en la ayuda.
@comando('ask', uso='<pregunta>', ayuda='Pregunta libre a la IA (local)')
def ask(arg):
    raise RuntimeError('ask se atiende en terminal/views.py')


WIKIS_RECOMENDADAS = (
    ("Juan Francisco Trapero", "https://wiki.jtrapero.eu.org/",
     "Memoria de un homelab: infraestructura autohospedada, Linux, redes, seguridad y automatizacion"),
)


@comando('wikis', ayuda='Otras wikis recomendadas')
def wikis(arg):
    lineas = ["[[verde]]Otras wikis recomendadas[[/]]", ""]
    for nombre, url, desc in WIKIS_RECOMENDADAS:
        lineas += [f"  [[amarillo]]{nombre}[[/]]", f"  {url}", f"  [[gris]]{desc}[[/]]", ""]
    return "\n".join(lineas).rstrip()


# `clear` lo trata la vista (devuelve una señal al widget); se registra para la ayuda.
@comando('clear', ayuda='Limpia la pantalla')
def clear(arg):
    return ''


# Ocultos (sin ayuda)
@comando('sudo')
def sudo(arg):
    return "Nice try. Pero aqui no hay sudo que valga ;)"


@comando('exit', alias=('logout', 'quit'))
def exit_(arg):
    return "No puedes salir. Estas atrapado en la wiki para siempre."
