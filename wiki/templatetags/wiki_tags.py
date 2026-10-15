from django import template
from django.db.models import Count, Prefetch, Q
from wiki.models import Category

register = template.Library()

_published = Count('articles', filter=Q(articles__is_published=True))


@register.simple_tag
def get_categories():
    """Categorías raíz con sus subcategorías y el número de artículos publicados.

    Cada categoría lleva `n_articles` (los suyos) y `total_articles`
    (los suyos más los de sus subcategorías).
    """
    subs = Category.objects.annotate(n_articles=_published)
    cats = list(
        Category.objects.filter(parent=None)
        .annotate(n_articles=_published)
        .prefetch_related(Prefetch('subcategories', queryset=subs, to_attr='subs'))
    )
    for cat in cats:
        cat.total_articles = cat.n_articles + sum(s.n_articles for s in cat.subs)
    return cats


@register.filter
def split(value, delimiter=','):
    return value.split(delimiter)


@register.filter
def trim(value):
    return value.strip()
