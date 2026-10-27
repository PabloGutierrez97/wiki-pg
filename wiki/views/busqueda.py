import hashlib

from django.db.models import Case, IntegerField, Q, Value, When
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render

from ..models import Article
from ..rendering import resumen
from ..security import client_ip_cuota, excede_limite
from ..utils import cacheado

CACHE_BUSQUEDA = 5 * 60
MIN_Q = 2
MAX_Q = 100
MAX_RESULTADOS = 30
MAX_SUGERENCIAS = 6
# La página de búsqueda se actualiza mientras se escribe (wiki.js), con 300 ms de espera.
BUSQUEDAS_POR_MINUTO = 60
SUGERENCIAS_POR_MINUTO = 60


def _consulta(request):
    return request.GET.get('q', '').strip()[:MAX_Q]


def _ids_busqueda(query, limite):
    """Ids de artículos que coinciden con la búsqueda, cacheados unos minutos."""
    clave = 'busq:%d:%s' % (limite, hashlib.sha256(query.lower().encode('utf-8')).hexdigest())
    return cacheado(clave, lambda: list(
        Article.objects.publicados().filter(
            Q(title__icontains=query) |
            Q(content__icontains=query) |
            Q(tags__icontains=query) |
            Q(category__name__icontains=query)
        ).annotate(
            # Primero los que lo llevan en el título, luego en etiquetas o categoría, luego solo en el texto.
            relevancia=Case(When(title__icontains=query, then=Value(0)),
                            When(Q(tags__icontains=query) | Q(category__name__icontains=query), then=Value(1)),
                            default=Value(2), output_field=IntegerField()),
        ).order_by('relevancia', '-created_at').distinct().values_list('id', flat=True)[:limite]
    ), CACHE_BUSQUEDA)


def _articulos(query, limite):
    """Artículos de la búsqueda, en el orden de los ids cacheados."""
    ids = _ids_busqueda(query, limite)
    por_id = Article.objects.publicados().select_related('category').in_bulk(ids)
    return [por_id[i] for i in ids if i in por_id]


def search(request):
    query = _consulta(request)
    results = []
    if len(query) >= MIN_Q:
        if excede_limite('busq:min:' + client_ip_cuota(request), BUSQUEDAS_POR_MINUTO, 60):
            return HttpResponse('Demasiadas busquedas seguidas. Espera un minuto y vuelve a intentarlo.',
                                status=429, content_type='text/plain; charset=utf-8')
        results = _articulos(query, MAX_RESULTADOS)
        for article in results:
            article.summary = resumen(article)
    return render(request, 'wiki/search.html', {'query': query, 'results': results,
                                                'query_corta': 0 < len(query) < MIN_Q})


def search_api(request):
    query = _consulta(request)
    resultados = []
    if len(query) >= MIN_Q:
        if excede_limite('sugg:min:' + client_ip_cuota(request), SUGERENCIAS_POR_MINUTO, 60):
            return JsonResponse({'results': []}, status=429)
        resultados = [{
            'title': a.title,
            'url': a.get_absolute_url(),
            'category': a.category.name if a.category else '',
        } for a in _articulos(query, MAX_SUGERENCIAS)]
    return JsonResponse({'results': resultados})
