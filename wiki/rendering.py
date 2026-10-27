"""Conversión de Markdown a HTML, cacheada por versión del artículo.

Convertir Markdown es lo que más CPU cuesta de servir una página. La clave de
caché incluye updated_at, así que editar un artículo genera otra clave y la
versión vieja caduca sola.
"""
import re

import markdown
from django.utils.html import strip_tags
from markdown.extensions.codehilite import CodeHiliteExtension
from pygments.formatters import HtmlFormatter

from .utils import cacheado

CACHE_RENDER = 24 * 3600


class LangHtmlFormatter(HtmlFormatter):
    """Añade class="language-xxx" al <code> para que la interfaz muestre el lenguaje."""

    def __init__(self, lang_str='', **options):
        super().__init__(**options)
        self.lang_str = lang_str

    def _wrap_code(self, source):
        yield 0, f'<code class="{self.lang_str}">' if self.lang_str else '<code>'
        yield from source
        yield 0, '</code>'


_RE_CODIGO = re.compile(r'<pre[^>]*>.*?</pre>', re.S)
_RE_TITULOS = re.compile(r'<h[1-6][^>]*>.*?</h[1-6]>', re.S)


def texto_plano(article, titulos=True):
    """Texto del artículo sin Markdown ni bloques de código (y sin títulos si titulos=False)."""
    html = markdown.markdown(article.content or '', extensions=['fenced_code', 'tables'])
    html = _RE_CODIGO.sub(' ', html)
    if not titulos:
        html = _RE_TITULOS.sub(' ', html)
    return ' '.join(strip_tags(html).split())

def _version(article):
    return '%s:%s' % (article.pk, article.updated_at.timestamp() if article.updated_at else 0)


def articulo_html(article):
    """(html, índice) del contenido completo del artículo."""
    def _render():
        md = markdown.Markdown(extensions=[
            'fenced_code',
            'tables',
            'toc',
            CodeHiliteExtension(linenums=False, guess_lang=False, css_class='highlight',
                                pygments_formatter=LangHtmlFormatter),
        ])
        return md.convert(article.content), md.toc
    return cacheado('md:articulo:' + _version(article), _render, CACHE_RENDER)


def descripcion(article, limite=155):
    """Meta descripción: la escrita a mano o el inicio del artículo cortado en una palabra."""
    if (article.meta_description or '').strip():
        return article.meta_description.strip()

    def _calcular():
        texto = texto_plano(article)
        if len(texto) <= limite:
            return texto
        corte = texto[:limite - 1].rsplit(' ', 1)[0].rstrip(' ,.;:')
        return corte + '…'
    return cacheado('md:desc2:%d:' % limite + _version(article), _calcular, CACHE_RENDER)


def resumen(article, longitud=200):
    """Primeros caracteres del artículo en texto plano, para listados."""
    return cacheado('md:resumen2:' + _version(article),
                    lambda: texto_plano(article, titulos=False)[:longitud],
                    CACHE_RENDER)
