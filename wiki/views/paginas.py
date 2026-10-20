import json

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.safestring import mark_safe

from ..models import Article, Category, Profile
from ..rendering import articulo_html, descripcion, resumen
from ..security import client_ip_cuota, excede_limite
from ..templatetags.wiki_tags import get_categories

MAX_TAG = 50
ETIQUETAS_POR_MINUTO = 30


def home(request):
    publicados = Article.objects.publicados()
    return render(request, 'wiki/home.html', {
        'categories': get_categories(),
        'recent_articles': publicados.select_related('category')[:6],
        'total_articles': publicados.count(),
        'total_categories': Category.objects.count(),
        'last_updated': publicados.order_by('-updated_at').first(),
    })


def category_detail(request, slug):
    category = get_object_or_404(Category, slug=slug)
    articles = list(Article.objects.publicados().filter(category=category))
    for article in articles:
        article.summary = resumen(article)
    return render(request, 'wiki/category_detail.html', {
        'category': category,
        'articles': articles,
    })


def article_detail(request, slug):
    article = get_object_or_404(Article.objects.publicados(), slug=slug)
    content_html, toc = articulo_html(article)

    featured_image_url = None
    if article.featured_image and article.featured_image.name:
        try:
            featured_image_url = article.featured_image.url
        except ValueError:
            pass

    desc = descripcion(article)
    return render(request, 'wiki/article_detail.html', {
        'article': article,
        'descripcion': desc,
        'datos_estructurados': _datos_estructurados(article, desc, featured_image_url),
        'content_html': content_html,
        'toc': toc,
        'reading_time': article.minutos_lectura,
        'tags': article.tag_list,
        'featured_image_url': featured_image_url,
    })


def _datos_estructurados(article, desc, imagen):
    """JSON-LD (schema.org) para que Google entienda el artículo y su ruta.

    Se escapa '<' para que ningún texto pueda cerrar la etiqueta script.
    """
    base = settings.SITE_URL
    cat = article.category
    migas = [('Inicio', base + '/')]
    if cat.parent:
        migas.append((cat.parent.name, base + reverse('wiki:category_detail', args=[cat.parent.slug])))
    migas.append((cat.name, base + reverse('wiki:category_detail', args=[cat.slug])))
    migas.append((article.title, article.url_publica))
    articulo = {
        '@context': 'https://schema.org',
        '@type': 'TechArticle',
        'headline': article.title[:110],
        'description': desc,
        'datePublished': article.created_at.isoformat(),
        'dateModified': article.updated_at.isoformat(),
        'inLanguage': 'es',
        'articleSection': cat.name,
        'keywords': ', '.join(article.tag_list),
        'mainEntityOfPage': article.url_publica,
        'author': {'@type': 'Person', 'name': 'Pablo Gutiérrez Gracia',
                   'url': base + reverse('wiki:about')},
    }
    if imagen:
        articulo['image'] = base + imagen
    migas_ld = {
        '@context': 'https://schema.org',
        '@type': 'BreadcrumbList',
        'itemListElement': [{'@type': 'ListItem', 'position': i, 'name': n, 'item': u}
                            for i, (n, u) in enumerate(migas, 1)],
    }
    texto = json.dumps([articulo, migas_ld], ensure_ascii=False).replace('<', '\\u003c')
    return mark_safe(texto)


def tag_detail(request, tag):
    if excede_limite('tag:min:' + client_ip_cuota(request), ETIQUETAS_POR_MINUTO, 60):
        return HttpResponse('Demasiadas peticiones seguidas. Espera un minuto.',
                            status=429, content_type='text/plain; charset=utf-8')
    tag = tag[:MAX_TAG]
    return render(request, 'wiki/tag_detail.html', {
        'tag': tag,
        'articles': Article.objects.publicados().filter(tags__icontains=tag),
    })


def about(request):
    profile = Profile.get()
    return render(request, 'wiki/about.html', {
        'profile': profile,
        'stack': profile.stack_dict(),
    })
