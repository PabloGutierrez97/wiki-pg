"""Búsqueda semántica sobre los artículos (RAG).

Cada artículo se trocea en fragmentos de ~900 caracteres; cada fragmento se
guarda con su embedding (bge-m3). Al preguntar se calcula el embedding de la
pregunta y se buscan los fragmentos con mayor similitud coseno.
"""
import hashlib
import json
import math
import re
from array import array

from django.db.models import Count, Max

from ..models import Article, ArticleChunk
from ..utils import normalizar
from . import ollama

TAMANO_FRAGMENTO = 900
# Por encima de esta similitud se enlaza el artículo al final de la respuesta.
UMBRAL_ENLACE = 0.45

_STOP = {'para', 'como', 'que', 'sobre', 'tienes', 'algo', 'pasame', 'dame', 'una', 'uno', 'los',
         'las', 'del', 'articulo', 'quiero', 'leer', 'con', 'por', 'sus', 'mas', 'tiene', 'hay',
         'algun', 'alguna', 'articulos', 'wiki', 'sabes', 'tienes', 'hablame', 'explica',
         'cuentame', 'dime', 'esta', 'este', 'tengo'}


def trocear(texto, maximo=TAMANO_FRAGMENTO):
    """Agrupa párrafos en fragmentos de hasta `maximo` caracteres."""
    texto = (texto or '').strip()
    if not texto:
        return []
    fragmentos, actual = [], ''
    for parrafo in re.split(r'\n\s*\n', texto):
        parrafo = parrafo.strip()
        if not parrafo:
            continue
        if actual and len(actual) + len(parrafo) + 2 <= maximo:
            actual += '\n\n' + parrafo
        elif len(parrafo) <= maximo:
            if actual:
                fragmentos.append(actual)
            actual = parrafo
        else:
            if actual:
                fragmentos.append(actual)
                actual = ''
            fragmentos.extend(parrafo[j:j + maximo] for j in range(0, len(parrafo), maximo))
    if actual:
        fragmentos.append(actual)
    return fragmentos


def reindexar_articulo(articulo, force=False):
    """Recalcula los fragmentos y embeddings de un artículo si su texto cambió.

    Devuelve ('indexado' | 'sin cambios', número de fragmentos).
    """
    texto = (articulo.title or '') + "\n" + (articulo.tags or '') + "\n" + (articulo.content or '')
    huella = hashlib.sha256(texto.encode('utf-8')).hexdigest()
    if not force and articulo.embedding_hash == huella and articulo.chunks.exists():
        return 'sin cambios', articulo.chunks.count()
    articulo.chunks.all().delete()
    creados = 0
    for i, fragmento in enumerate(trocear(articulo.content)):
        emb = ollama.embedding((articulo.title or '') + "\n" + fragmento)
        if emb:
            ArticleChunk.objects.create(article=articulo, idx=i, text=fragmento, embedding=json.dumps(emb))
            creados += 1
    Article.objects.filter(pk=articulo.pk).update(embedding_hash=huella)
    return 'indexado', creados


# Vectores ya parseados, por proceso: parsear ~550 JSON de 1024 números en cada
# pregunta es CPU pura. Se recargan solo cuando cambia el índice.
_MEMO = {'version': None, 'items': []}


def _vectores_indexados():
    qs = ArticleChunk.objects.exclude(embedding='')
    agg = qs.aggregate(maximo=Max('id'), total=Count('id'))
    version = (agg['maximo'], agg['total'])
    if _MEMO['version'] != version:
        items = []
        for cid, aid, emb in qs.values_list('id', 'article_id', 'embedding'):
            try:
                vec = array('d', json.loads(emb))
            except (ValueError, TypeError):
                continue
            norma = math.sqrt(sum(x * x for x in vec))
            if norma:
                items.append((cid, aid, vec, norma))
        _MEMO.update(items=items, version=version)
    return _MEMO['items']


def buscar(pregunta, k=4):
    """[(fragmento, similitud)] de los k fragmentos más parecidos a la pregunta."""
    qemb = ollama.embedding(pregunta, timeout=10, intentos=1)
    if not qemb:
        return []
    qnorma = math.sqrt(sum(x * x for x in qemb))
    if not qnorma:
        return []
    publicados = set(Article.objects.publicados().values_list('id', flat=True))
    puntuados = sorted(
        ((sum(a * b for a, b in zip(qemb, vec)) / (qnorma * norma), cid)
         for cid, aid, vec, norma in _vectores_indexados() if aid in publicados),
        reverse=True)[:k]
    por_id = ArticleChunk.objects.select_related('article', 'article__category').in_bulk(
        [cid for _, cid in puntuados])
    return [(por_id[cid], score) for score, cid in puntuados if cid in por_id]


def articulos_por_palabras(pregunta):
    """Artículos cuyo título, tags, slug o categoría comparten más palabras con la pregunta (empatados)."""
    palabras = [w for w in re.findall(r'[a-z0-9]+', normalizar(pregunta))
                if len(w) >= 4 and w not in _STOP]
    if not palabras:
        return []
    puntuados = []
    for a in Article.objects.publicados().select_related('category').order_by('-created_at'):
        blob = normalizar(' '.join((a.title, a.tags or '', a.slug, a.category.name)))
        score = sum(1 for w in palabras if w in blob)
        if score:
            puntuados.append((score, a))
    if not puntuados:
        return []
    mejor = max(s for s, _ in puntuados)
    return [a for s, a in puntuados if s == mejor]


def articulo_por_palabras(pregunta):
    """El artículo que más palabras comparte con la pregunta, o None."""
    encontrados = articulos_por_palabras(pregunta)
    return encontrados[0] if encontrados else None


def articulos_sobre(tema, maximo=8):
    """Artículos publicados sobre un tema: primero los que lo nombran, después los parecidos por significado."""
    encontrados = articulos_por_palabras(tema)
    for frag, score in buscar(tema, 8):
        if score >= UMBRAL_ENLACE and frag.article not in encontrados:
            encontrados.append(frag.article)
    return encontrados[:maximo]
