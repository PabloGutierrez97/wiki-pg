"""Conversión de Markdown a HTML, cacheada por versión del artículo.

Convertir Markdown es lo que más CPU cuesta de servir una página. La clave de
caché incluye updated_at, así que editar un artículo genera otra clave y la
versión vieja caduca sola.
"""
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


def resumen(article, longitud=200):
    """Primeros caracteres del artículo en texto plano, para listados."""
    return cacheado('md:resumen:' + _version(article),
                    lambda: strip_tags(markdown.markdown(article.content))[:longitud],
                    CACHE_RENDER)
