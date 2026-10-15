import hashlib
import logging
import secrets

from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.html import strip_tags
from .models import Category, Article
from .security import client_ip, excede_limite, staff_verificado
import markdown

log = logging.getLogger(__name__)

# Lo que cuesta CPU (convertir Markdown) se guarda en Redis y se invalida solo:
# la clave incluye updated_at, así que editar un artículo genera otra clave.
CACHE_RENDER = 24 * 3600
CACHE_BUSQUEDA = 5 * 60
MAX_Q = 100
MAX_RESULTADOS = 30
BUSQUEDAS_POR_MINUTO = 30
SUGERENCIAS_POR_MINUTO = 60


def _cacheado(clave, calcular, segundos):
    try:
        valor = cache.get(clave)
    except Exception:
        return calcular()
    if valor is None:
        valor = calcular()
        try:
            cache.set(clave, valor, segundos)
        except Exception:
            pass
    return valor


def _version(article):
    return '%s:%s' % (article.pk, article.updated_at.timestamp() if article.updated_at else 0)


def _resumen(article):
    return _cacheado('md:resumen:' + _version(article),
                     lambda: strip_tags(markdown.markdown(article.content))[:200],
                     CACHE_RENDER)


def _ids_busqueda(query, limite):
    """Ids de artículos que coinciden con la búsqueda, cacheados unos minutos."""
    clave = 'busq:%d:%s' % (limite, hashlib.sha256(query.lower().encode('utf-8')).hexdigest())
    return _cacheado(clave, lambda: list(
        Article.objects.filter(is_published=True).filter(
            models.Q(title__icontains=query) |
            models.Q(content__icontains=query) |
            models.Q(tags__icontains=query) |
            models.Q(category__name__icontains=query)
        ).distinct().values_list('id', flat=True)[:limite]
    ), CACHE_BUSQUEDA)


def _articulos_por_ids(ids):
    por_id = {a.id: a for a in Article.objects.filter(id__in=ids, is_published=True).select_related('category')}
    return [por_id[i] for i in ids if i in por_id]
from markdown.extensions.codehilite import CodeHiliteExtension
from pygments.formatters import HtmlFormatter


class LangHtmlFormatter(HtmlFormatter):
    """Añade class="language-xxx" al <code> para que la interfaz muestre el lenguaje."""

    def __init__(self, lang_str='', **options):
        super().__init__(**options)
        self.lang_str = lang_str

    def _wrap_code(self, source):
        yield 0, f'<code class="{self.lang_str}">' if self.lang_str else '<code>'
        yield from source
        yield 0, '</code>'
from django.db import models

def home(request):
    from django.utils import timezone
    from .templatetags.wiki_tags import get_categories
    categories = get_categories()
    recent_articles = Article.objects.filter(is_published=True).select_related('category')[:6]
    
    # Stats
    total_articles = Article.objects.filter(is_published=True).count()
    total_categories = Category.objects.count()
    last_updated = Article.objects.filter(is_published=True).order_by('-updated_at').first()
    
    return render(request, 'wiki/home.html', {
        'categories': categories,
        'recent_articles': recent_articles,
        'total_articles': total_articles,
        'total_categories': total_categories,
        'last_updated': last_updated,
    })

def category_detail(request, slug):
    category = get_object_or_404(Category, slug=slug)
    articles = list(Article.objects.filter(category=category, is_published=True))
    for article in articles:
        article.summary = _resumen(article)
    return render(request, 'wiki/category_detail.html', {
        'category': category,
        'articles': articles
    })

def article_detail(request, slug):
    article = get_object_or_404(Article, slug=slug, is_published=True)
    def _render():
        md = markdown.Markdown(extensions=[
            'fenced_code',
            'tables',
            'toc',
            CodeHiliteExtension(linenums=False, guess_lang=False, css_class='highlight', pygments_formatter=LangHtmlFormatter)
        ])
        html = md.convert(article.content)
        return (html, md.toc)
    content_html, toc = _cacheado('md:articulo:' + _version(article), _render, CACHE_RENDER)

    # Tiempo de lectura (200 palabras por minuto)
    word_count = len(article.content.split())
    reading_time = max(1, round(word_count / 200))

    # Justo antes del return render en article_detail
    tags = [t.strip() for t in article.tags.split(',') if t.strip()] if article.tags else []

    featured_image_url = None
    if article.featured_image and article.featured_image.name:
        try:
            featured_image_url = article.featured_image.url
        except ValueError:
            pass

    return render(request, 'wiki/article_detail.html', {
        'article': article,
        'content_html': content_html,
        'toc': toc,
        'reading_time': reading_time,
        'tags': tags,
        'featured_image_url': featured_image_url,
    })

def search(request):
    query = request.GET.get('q', '').strip()[:MAX_Q]
    results = []
    if len(query) >= 2:
        if excede_limite('busq:min:' + client_ip(request), BUSQUEDAS_POR_MINUTO, 60):
            return HttpResponse('Demasiadas busquedas seguidas. Espera un minuto y vuelve a intentarlo.',
                                status=429, content_type='text/plain; charset=utf-8')
        results = _articulos_por_ids(_ids_busqueda(query, MAX_RESULTADOS))
        for article in results:
            article.summary = _resumen(article)
    return render(request, 'wiki/search.html', {
        'query': query,
        'results': results
    })

def about(request):
    from .models import Profile
    import json
    profile = Profile.get()
    stack = {}
    if profile.stack:
        try:
            stack = json.loads(profile.stack)
        except:
            stack = {}
    return render(request, 'wiki/about.html', {
        'profile': profile,
        'stack': stack,
    })

@staff_verificado
def linkedin_auth(request):
    from .linkedin import get_auth_url
    state = secrets.token_urlsafe(32)
    request.session['linkedin_oauth_state'] = state
    return redirect(get_auth_url(state))

@staff_verificado
def linkedin_callback(request):
    from .linkedin import get_access_token, get_profile
    from .models import LinkedInToken

    # El state impide que alguien te "conecte" su propia cuenta con un enlace preparado.
    esperado = request.session.pop('linkedin_oauth_state', None)
    recibido = request.GET.get('state', '')
    if not esperado or not secrets.compare_digest(esperado, recibido):
        return redirect(reverse('admin:index'))

    code = request.GET.get('code')
    if not code:
        return redirect(reverse('admin:index'))

    token_data = get_access_token(code)
    access_token = token_data.get('access_token')

    if not access_token:
        return redirect(reverse('admin:index'))
    
    profile = get_profile(access_token)
    author_id = profile.get('sub')
    
    token = LinkedInToken()
    token.access_token = access_token
    token.author_id = author_id
    token.save()

    return redirect(reverse('admin:index'))

@staff_verificado
@require_POST
def linkedin_post(request, article_id):
    from .linkedin import post_to_linkedin
    from .models import LinkedInToken

    token = LinkedInToken.get()
    if not token:
        return redirect(reverse('admin:wiki_linkedintoken_changelist'))
    
    article = get_object_or_404(Article, pk=article_id)
    text = request.POST.get('text', f'Nuevo artículo en mi wiki: {article.title}\n\nhttps://wiki.pablogg.dev/article/{article.slug}/')
    
    post_to_linkedin(token.access_token, token.author_id, text[:3000])

    return redirect(reverse('admin:wiki_article_change', args=[article_id]))

def tag_detail(request, tag):
    tag = tag[:50]
    articles = Article.objects.filter(
        is_published=True,
        tags__icontains=tag
    )
    return render(request, 'wiki/tag_detail.html', {
        'tag': tag,
        'articles': articles
    })

@staff_verificado
@require_POST
def generate_linkedin_text(request, article_id):
    from google import genai
    from django.conf import settings

    article = get_object_or_404(Article, pk=article_id)

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    prompt = f"""Eres un asistente que escribe publicaciones de LinkedIn para un administrador de sistemas que comparte artículos técnicos en su wiki personal.

Genera un texto de LinkedIn en español, profesional pero cercano, basado en este artículo:

Título: {article.title}
Contenido: {article.content[:2000]}

El texto debe:
- Tener entre 3 y 5 frases
- Sonar natural, no como un anuncio genérico
- Terminar con 3-4 hashtags relevantes en español
- NO incluir la URL del artículo (se añadirá después)

Devuelve solo el texto del post, sin comillas ni explicaciones adicionales."""

    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt
        )
        text = response.text.strip()
        text += f"\n\nLee el artículo completo aquí: https://wiki.pablogg.dev/article/{article.slug}/"
        return JsonResponse({'text': text})
    except Exception:
        log.exception('Error generando el texto de LinkedIn con Gemini')
        return JsonResponse({'error': 'Gemini no ha respondido; prueba de nuevo en un momento'}, status=502)

@csrf_exempt
def honeypot_admin(request):
    from .models import HoneypotAttempt
    from django.http import HttpResponse

    # Se registra cada intento, pero con tope: si no, un bot podría llenar la base de datos.
    ip = client_ip(request)
    if (request.method == 'POST'
            and not excede_limite('hp:ip:' + ip, 20, 3600)
            and not excede_limite('hp:total', 1000, 3600)):
        HoneypotAttempt.objects.create(
            ip=ip,
            username=request.POST.get('username', '')[:200],
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:1000],
            path=request.path,
        )

    return render(request, 'wiki/honeypot_login.html', {
        'error': request.method == 'POST',
    })


def search_api(request):
    query = request.GET.get('q', '').strip()[:MAX_Q]
    resultados = []
    if len(query) >= 2:
        if excede_limite('sugg:min:' + client_ip(request), SUGERENCIAS_POR_MINUTO, 60):
            return JsonResponse({'results': []}, status=429)
        for article in _articulos_por_ids(_ids_busqueda(query, 6)):
            resultados.append({
                'title': article.title,
                'url': f'/article/{article.slug}/',
                'category': article.category.name if article.category else '',
            })
    return JsonResponse({'results': resultados})
