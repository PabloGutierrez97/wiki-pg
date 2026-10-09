from django.core.management.base import BaseCommand
from wiki.models import Article
from wiki.terminal import reindexar_articulo


class Command(BaseCommand):
    help = 'Trocea e indexa (embeddings por fragmento) los articulos publicados.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help='Recalcula todos aunque no hayan cambiado.')

    def handle(self, *args, **opts):
        arts = Article.objects.filter(is_published=True)
        total = arts.count()
        indexados = saltados = fallos = 0
        total_frag = 0
        for a in arts:
            try:
                estado, n = reindexar_articulo(a, force=opts['force'])
            except Exception as e:
                fallos += 1
                self.stderr.write(self.style.ERROR('  fallo: %s -> %s' % (a.slug, e)))
                continue
            total_frag += n
            if estado == 'indexado':
                indexados += 1
                self.stdout.write('  ok: %s (%d fragmentos)' % (a.slug, n))
            else:
                saltados += 1
                self.stdout.write('  sin cambios: %s (%d fragmentos)' % (a.slug, n))
        self.stdout.write(self.style.SUCCESS(
            'Hecho: %d indexados, %d sin cambios, %d fallos | %d fragmentos totales (de %d articulos)'
            % (indexados, saltados, fallos, total_frag, total)))
