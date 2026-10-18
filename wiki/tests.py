import json
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from .ai import filtros, prompts, rag, servicio
from .terminal import comandos
from .models import Article, Category, HoneypotAttempt, Profile
from .security import client_ip, reservar_plaza_ia, reservar_turno_ip
from .templatetags.wiki_tags import get_categories

# Los tests no tocan el Redis de producción.
CACHE_TESTS = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                           'LOCATION': 'wiki-tests'}}


@override_settings(CACHES=CACHE_TESTS)
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


@override_settings(CACHES=CACHE_TESTS, AI_MAX_CONCURRENT=2)
class SeguridadTests(TestCase):
    """Cada test reproduce un abuso real y comprueba que ya no funciona."""

    IP = '203.0.113.7'

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username='pablo')
        cat = Category.objects.create(name='Redes', slug='redes')
        cls.article = Article.objects.create(
            title='VPN WireGuard', slug='vpn-wireguard', category=cat, author=cls.user,
            is_published=True, content='Intro wireguard')
        cls.staff = User.objects.create_user('admin', password='x', is_staff=True)

    def setUp(self):
        cache.clear()

    # ------------------------------------------------------------ ayudas --

    def _ask(self, pregunta, ip=IP):
        resp = self.client.post('/terminal/ask/', data=json.dumps({'command': 'ask ' + pregunta}),
                                content_type='application/json', HTTP_X_REAL_IP=ip)
        texto = b''.join(resp.streaming_content).decode()
        resp.close()
        return texto

    def _ollama_falso(self, texto='rclone sincroniza'):
        lineas = [json.dumps({'response': texto, 'done': False}).encode() + b'\n',
                  json.dumps({'response': '', 'done': True}).encode() + b'\n']

        class Respuesta:
            def __enter__(self):
                return iter(lineas)

            def __exit__(self, *a):
                return False
        return mock.patch('urllib.request.urlopen', return_value=Respuesta())

    def _sin_rag(self):
        return mock.patch.object(prompts, 'contexto_general', return_value=('sys', None))

    def _verificar_2fa(self):
        from django_otp import DEVICE_ID_SESSION_KEY
        from django_otp.plugins.otp_static.models import StaticDevice
        device = StaticDevice.objects.create(user=self.staff, name='test')
        session = self.client.session
        session[DEVICE_ID_SESSION_KEY] = device.persistent_id
        session.save()

    def _plazas_libres(self):
        plazas = [reservar_plaza_ia(), reservar_plaza_ia()]
        libres = all(plazas)
        for p in plazas:
            if p:
                p.liberar()
        return libres

    # ----------------------------------------------------------- LinkedIn --

    def test_linkedin_y_subidas_ocultas_para_anonimos(self):
        casos = [('get', '/linkedin/auth/'),
                 ('get', '/linkedin/callback/?code=x&state=y'),
                 ('post', '/linkedin/post/%d/' % self.article.pk),
                 ('post', '/linkedin/generate/%d/' % self.article.pk),
                 ('post', '/mdeditor/uploads/')]
        for metodo, url in casos:
            with self.subTest(url=url):
                self.assertEqual(getattr(self.client, metodo)(url).status_code, 404)

    def test_linkedin_exige_staff_con_2fa(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get('/linkedin/auth/').status_code, 404)
        self._verificar_2fa()
        r = self.client.get('/linkedin/auth/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('state=', r['Location'])
        self.assertTrue(self.client.session['linkedin_oauth_state'])

    def test_callback_rechaza_un_state_ajeno(self):
        self.client.force_login(self.staff)
        self._verificar_2fa()
        with mock.patch('wiki.linkedin.get_access_token') as token:
            r = self.client.get('/linkedin/callback/?code=abc&state=falso')
        self.assertEqual(r.status_code, 302)
        token.assert_not_called()

    def test_admin_real_sale_de_settings(self):
        self.assertEqual(reverse('admin:index'), '/' + settings.ADMIN_URL)

    # ------------------------------------------------------------ IP real --

    def test_ip_real_ignora_cabeceras_falsificables(self):
        from axes.helpers import get_client_ip_address
        rf = RequestFactory()
        req = rf.get('/', HTTP_X_REAL_IP='203.0.113.5',
                     HTTP_X_FORWARDED_FOR='1.2.3.4', HTTP_CF_CONNECTING_IP='5.6.7.8')
        self.assertEqual(client_ip(req), '203.0.113.5')
        self.assertEqual(get_client_ip_address(req), '203.0.113.5')   # axes usa la misma
        self.assertEqual(client_ip(rf.get('/', HTTP_X_REAL_IP='no-es-una-ip')), '127.0.0.1')

    def test_honeypot_limita_los_registros_por_ip(self):
        for _ in range(25):
            self.client.post('/admin/', {'username': 'root', 'password': 'x'},
                             HTTP_X_REAL_IP='198.51.100.9')
        self.assertEqual(HoneypotAttempt.objects.count(), 20)

    # ---------------------------------------------------------- busqueda --

    def test_busqueda_acotada_y_con_limite_por_visitante(self):
        r = self.client.get('/search/', {'q': 'w' * 500}, HTTP_X_REAL_IP='192.0.2.1')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context['query']), 100)
        for _ in range(29):
            self.client.get('/search/', {'q': 'wireguard'}, HTTP_X_REAL_IP='192.0.2.1')
        r = self.client.get('/search/', {'q': 'wireguard'}, HTTP_X_REAL_IP='192.0.2.1')
        self.assertEqual(r.status_code, 429)
        r = self.client.get('/search/', {'q': 'wireguard'}, HTTP_X_REAL_IP='192.0.2.2')
        self.assertContains(r, 'VPN WireGuard')

    def test_articulo_cacheado_se_actualiza_al_editar(self):
        url = reverse('wiki:article_detail', args=['vpn-wireguard'])
        self.assertContains(self.client.get(url), 'Intro wireguard')
        self.article.content = 'Texto nuevo'
        self.article.save()
        self.assertContains(self.client.get(url), 'Texto nuevo')

    # ------------------------------------------------------------ terminal --

    def test_terminal_rechaza_cuerpos_grandes(self):
        r = self.client.post('/terminal/cmd/', data=json.dumps({'command': 'help', 'x': 'a' * 10000}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_terminal_limita_los_comandos(self):
        for _ in range(60):
            self.client.post('/terminal/cmd/', data=json.dumps({'command': 'date'}),
                             content_type='application/json', HTTP_X_REAL_IP='192.0.2.50')
        r = self.client.post('/terminal/cmd/', data=json.dumps({'command': 'date'}),
                             content_type='application/json', HTTP_X_REAL_IP='192.0.2.50')
        self.assertEqual(r.status_code, 429)

    # ------------------------------------------------------------------ IA --

    def test_ask_limita_el_ritmo_tambien_en_respuestas_fijas(self):
        for _ in range(5):
            self.assertIn('Ollama', self._ask('como funcionas'))
        self.assertIn('Vas muy rapido', self._ask('como funcionas'))

    def test_ask_con_plazas_llenas_avisa_sin_llamar_a_ollama(self):
        ocupadas = [reservar_plaza_ia(), reservar_plaza_ia()]
        self.assertTrue(all(ocupadas))
        with mock.patch.object(prompts, 'contexto_general') as ctx, \
                mock.patch('urllib.request.urlopen') as ollama:
            texto = self._ask('que es rclone')
        self.assertIn('atendiendo a otras personas', texto)
        ctx.assert_not_called()
        ollama.assert_not_called()
        for p in ocupadas:
            p.liberar()
        self.assertIsNotNone(reservar_turno_ip(self.IP))   # su turno no quedó bloqueado

    def test_ask_una_pregunta_a_la_vez_por_visitante(self):
        reservar_turno_ip(self.IP)                       # otra pestaña ya está preguntando
        self.assertIn('pregunta en curso', self._ask('que es rclone'))
        with self._sin_rag(), self._ollama_falso():
            self.assertIn('rclone sincroniza', self._ask('que es rclone', ip='203.0.113.8'))

    def test_ask_libera_plazas_y_cachea_la_respuesta(self):
        with self._sin_rag(), self._ollama_falso() as ollama:
            primera = self._ask('que es rclone')
            segunda = self._ask('Que es RCLONE')         # misma pregunta normalizada
        self.assertIn('rclone sincroniza', primera)
        self.assertEqual(primera, segunda)
        self.assertEqual(ollama.call_count, 1)           # la segunda salió de la caché
        self.assertTrue(self._plazas_libres())
        self.assertIsNotNone(reservar_turno_ip(self.IP))

    def test_ask_libera_si_el_visitante_cierra_antes_de_leer(self):
        with self._sin_rag(), self._ollama_falso():
            resp = self.client.post('/terminal/ask/', data=json.dumps({'command': 'ask que es rclone'}),
                                    content_type='application/json', HTTP_X_REAL_IP=self.IP)
            resp.close()                                 # sin leer ni un byte
        self.assertTrue(self._plazas_libres())
        self.assertIsNotNone(reservar_turno_ip(self.IP))

    def test_ask_libera_y_no_cachea_si_ollama_falla(self):
        with self._sin_rag(), mock.patch('urllib.request.urlopen', side_effect=OSError('caido')):
            self.assertIn('no esta disponible', self._ask('que es rclone'))
        self.assertTrue(self._plazas_libres())
        self.assertIsNone(cache.get(servicio.clave_respuesta('que es rclone')))

    def test_ask_por_cmd_tiene_las_mismas_puertas(self):
        ocupadas = [reservar_plaza_ia(), reservar_plaza_ia()]
        with mock.patch('urllib.request.urlopen') as ollama:
            r = self.client.post('/terminal/cmd/', data=json.dumps({'command': 'ask que es rclone'}),
                                 content_type='application/json', HTTP_X_REAL_IP=self.IP)
        self.assertIn('atendiendo a otras personas', r.json()['output'])
        ollama.assert_not_called()
        for p in ocupadas:
            p.liberar()


class IAFueraDeTemaTests(TestCase):
    """La IA no escribe contenido ni se inventa cosas de Pablo (caso real: 'gachas manchegas')."""

    IP = '203.0.113.9'

    def setUp(self):
        cache.clear()

    def _ask(self, pregunta):
        resp = self.client.post('/terminal/ask/', data=json.dumps({'command': 'ask ' + pregunta}),
                                content_type='application/json', HTTP_X_REAL_IP=self.IP)
        texto = b''.join(resp.streaming_content).decode()
        resp.close()
        return texto

    def test_encargos_y_temas_ajenos_no_llegan_al_modelo(self):
        preguntas = [
            'Escribe un artículo sobre las gachas manchegas',
            'que receta de gachas tiene pablo',
            'inventate que opina pablo de proxmox',
            'cuentame una historia',
        ]
        for pregunta in preguntas:
            cache.clear()
            with mock.patch.object(prompts, 'contexto_general') as ctx, \
                    mock.patch('urllib.request.urlopen') as ollama:
                texto = self._ask(pregunta)
            self.assertIn('Solo puedo ayudarte', texto, pregunta)
            ctx.assert_not_called()
            ollama.assert_not_called()

    def test_preguntas_validas_siguen_pasando(self):
        for pregunta in ['que es rclone', 'dame un articulo de rclone', 'quien es pablo',
                         'cuentame una historia del sr termista', 'receta para desplegar con docker',
                         'imagina que se cae el servidor, que hago', 'tienes algo de transformacion digital']:
            self.assertFalse(filtros.esta_fuera_de_tema(pregunta), pregunta)

    def test_por_cmd_tambien_se_filtra(self):
        with mock.patch('urllib.request.urlopen') as ollama:
            r = self.client.post('/terminal/cmd/', data=json.dumps({'command': 'ask receta de paella'}),
                                 content_type='application/json', HTTP_X_REAL_IP=self.IP)
        self.assertIn('Solo puedo ayudarte', r.json()['output'])
        ollama.assert_not_called()

    def test_el_prompt_prohibe_inventar_y_citar_a_pablo(self):
        with mock.patch.object(rag, 'buscar', return_value=[]):
            system, _ = prompts.contexto_general('que es rclone')
        self.assertIn('PROHIBIDO INVENTAR', system)
        self.assertIn('NUNCA pongas palabras en boca de Pablo', system)


class IAIdentidadTests(TestCase):
    """'quien es pablo' siempre presenta a Pablo, aunque el modelo se niegue."""

    IP = '203.0.113.10'

    def setUp(self):
        cache.clear()
        Profile.objects.create(nombre='Pablo Gutierrez Gracia', cargo='Responsable de Sistemas',
                               empresa='Texco Solutions SL', descripcion='Administra la infraestructura.')

    def _ask(self, pregunta, modelo):
        cuerpo = json.dumps({'response': modelo, 'done': True}).encode()

        class Respuesta:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return cuerpo
        with mock.patch('urllib.request.urlopen', return_value=Respuesta()) as ollama, \
                mock.patch.object(prompts, 'contexto_general') as ctx:
            resp = self.client.post('/terminal/ask/', data=json.dumps({'command': 'ask ' + pregunta}),
                                    content_type='application/json', HTTP_X_REAL_IP=self.IP)
            texto = b''.join(resp.streaming_content).decode()
            resp.close()
        ctx.assert_not_called()                          # no usa el prompt general
        return texto, ollama

    def test_si_el_modelo_se_niega_sale_la_presentacion_fija(self):
        texto, _ = self._ask('quien es pablo?', 'Lo siento, pero no puedo proporcionar informacion '
                                                'personal sobre una persona sin conocerla.')
        self.assertNotIn('Lo siento', texto)
        self.assertIn('Pablo Gutierrez Gracia', texto)
        self.assertIn('Responsable de Sistemas', texto)

    def test_si_copia_las_etiquetas_tambien_se_descarta(self):
        texto, _ = self._ask('que sabes sobre pablo?', 'La informacion proporcionada en PERFIL: es la '
                                                       'unica fuente disponible sobre el.')
        self.assertNotIn('PERFIL', texto)
        self.assertIn('Texco Solutions SL', texto)

    def test_respuesta_buena_del_modelo_se_usa(self):
        buena = ('Pablo Gutierrez Gracia es Responsable de Sistemas en Texco Solutions SL, '
                 'donde administra toda la infraestructura.')
        texto, ollama = self._ask('quien es pablo', buena)
        self.assertIn(buena, texto)
        self.assertIn('whoami', texto)
        self.assertEqual(ollama.call_count, 1)

    def test_si_ollama_falla_tambien_responde(self):
        with mock.patch('urllib.request.urlopen', side_effect=OSError('caido')):
            r = self.client.post('/terminal/cmd/', data=json.dumps({'command': 'ask quien es pablo'}),
                                 content_type='application/json', HTTP_X_REAL_IP=self.IP)
        self.assertIn('Pablo Gutierrez Gracia', r.json()['output'])


@override_settings(CACHES=CACHE_TESTS)
class TerminalComandosTests(TestCase):
    """El registro de comandos: la ayuda se genera sola y los alias funcionan."""

    def _cmd(self, texto):
        return self.client.post('/terminal/cmd/', data=json.dumps({'command': texto}),
                                content_type='application/json').json()

    def test_la_ayuda_lista_todos_los_comandos_visibles(self):
        ayuda = self._cmd('help')['output']
        for cmd in set(comandos.REGISTRO.values()):
            if cmd.ayuda:
                self.assertIn('[[amarillo]]%s[[/]]' % cmd.nombre, ayuda)
        self.assertNotIn('sudo', ayuda)                 # los ocultos no salen

    def test_alias_y_comando_desconocido(self):
        self.assertEqual(self._cmd('about'), self._cmd('whoami'))
        self.assertEqual(self._cmd('quit'), self._cmd('exit'))
        self.assertIn('comando no encontrado', self._cmd('rm -rf /')['output'])
        self.assertEqual(self._cmd('clear'), {'output': '', 'clear': True})

    def test_trocear_respeta_el_tamano(self):
        texto = 'parrafo corto\n\n' + 'x' * 2000 + '\n\notro parrafo'
        trozos = rag.trocear(texto, maximo=900)
        self.assertTrue(all(len(t) <= 900 for t in trozos))
        self.assertEqual(''.join(trozos).replace('\n', ''), texto.replace('\n', ''))
