from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Article, Category
from .templatetags.wiki_tags import get_categories


class FrontendTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username='pablo')
        cls.redes = Category.objects.create(name='Redes', slug='redes')
        cls.mikrotik = Category.objects.create(name='Mikrotik', slug='mikrotik', parent=cls.redes)
        cls.article = Article.objects.create(
            title='VPN WireGuard', slug='vpn-wireguard', category=cls.mikrotik, author=cls.user,
            is_published=True, tags='mikrotik, vpn',
            content='Intro\n\n## Configurar\n\n```bash\nip a\n```\n',
        )
        Article.objects.create(title='Borrador', slug='borrador', category=cls.redes, author=cls.user,
                               is_published=False, content='x')

    def test_paginas_principales_responden(self):
        urls = [
            reverse('wiki:home'),
            reverse('wiki:article_detail', args=['vpn-wireguard']),
            reverse('wiki:category_detail', args=['redes']),
            reverse('wiki:search') + '?q=wireguard',
            reverse('wiki:search') + '?q=nada-de-nada',
            reverse('wiki:tag_detail', args=['vpn']),
            reverse('wiki:about'),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_titulo_de_sobre_mi_es_texto_plano(self):
        html = self.client.get(reverse('wiki:about')).content.decode()
        title = html.split('<title>', 1)[1].split('</title>', 1)[0]
        self.assertEqual(title, 'Sobre mí - Wiki PG')

    def test_sin_imagen_destacada_no_hay_og_image(self):
        html = self.client.get(reverse('wiki:article_detail', args=['vpn-wireguard'])).content.decode()
        self.assertNotIn('og:image', html)

    def test_bloques_de_codigo_indican_el_lenguaje(self):
        html = self.client.get(reverse('wiki:article_detail', args=['vpn-wireguard'])).content.decode()
        self.assertIn('<code class="language-bash">', html)

    def test_ruta_de_la_barra_superior(self):
        html = self.client.get(reverse('wiki:article_detail', args=['vpn-wireguard'])).content.decode()
        self.assertIn('>redes</a>', html)
        self.assertIn('>mikrotik</a>', html)
        self.assertIn('<span aria-current="page">vpn-wireguard</span>', html)

    def test_recuento_de_articulos_por_categoria(self):
        cats = {c.slug: c for c in get_categories()}
        self.assertEqual(cats['redes'].n_articles, 0)       # el borrador no cuenta
        self.assertEqual(cats['redes'].total_articles, 1)   # incluye Mikrotik
        self.assertEqual(cats['redes'].subs[0].n_articles, 1)
