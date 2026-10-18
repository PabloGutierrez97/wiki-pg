"""Vistas de la wiki, separadas por área.

- paginas:   páginas públicas (portada, artículos, categorías, etiquetas, sobre mí).
- busqueda:  buscador y sugerencias instantáneas.
- linkedin:  conexión OAuth y publicación (solo staff con 2FA).
- honeypot:  falso /admin/ que registra intentos de acceso.
"""
from .busqueda import search, search_api
from .honeypot import honeypot_admin
from .linkedin import generate_linkedin_text, linkedin_auth, linkedin_callback, linkedin_post
from .paginas import about, article_detail, category_detail, home, tag_detail

__all__ = [
    'about', 'article_detail', 'category_detail', 'home', 'tag_detail',
    'search', 'search_api', 'honeypot_admin',
    'linkedin_auth', 'linkedin_callback', 'linkedin_post', 'generate_linkedin_text',
]
