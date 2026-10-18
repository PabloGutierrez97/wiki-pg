from django.shortcuts import get_object_or_404, render

from ..models import Article, Category, Profile
from ..rendering import articulo_html, resumen
from ..templatetags.wiki_tags import get_categories

MAX_TAG = 50


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

    return render(request, 'wiki/article_detail.html', {
        'article': article,
        'content_html': content_html,
        'toc': toc,
        'reading_time': article.minutos_lectura,
        'tags': article.tag_list,
        'featured_image_url': featured_image_url,
    })


def tag_detail(request, tag):
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
