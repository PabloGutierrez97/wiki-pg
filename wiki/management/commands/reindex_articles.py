import json, hashlib, time, os, urllib.request
from django.core.management.base import BaseCommand
from wiki.models import Article


def _texto_articulo(a):
    return (a.title or '') + "\n" + (a.tags or '') + "\n" + (a.content or '')


def _embed_try(texto):
    url = os.getenv('OLLAMA_URL', 'http://192.168.0.183:11434').rstrip('/') + '/api/embeddings'
    modelo = os.getenv('OLLAMA_EMBED_MODEL', 'bge-m3')
    payload = json.dumps({"model": modelo, "prompt": (texto or '')[:3000],
                          "keep_alive": "5m"}).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    emb = data.get('embedding')
    if not emb:
        raise ValueError('respuesta sin embedding: ' + str(data)[:200])
    return emb


class Command(BaseCommand):
    help = 'Calcula los embeddings de los articulos publicados (RAG).'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help='Recalcula todos aunque no hayan cambiado.')

    def handle(self, *args, **opts):
        force = opts['force']
        arts = Article.objects.filter(is_published=True)
        total = arts.count()
        hechos = saltados = fallos = 0
        for a in arts:
            texto = _texto_articulo(a)
            h = hashlib.sha256(texto.encode('utf-8')).hexdigest()
            if not force and a.embedding and a.embedding_hash == h:
                saltados += 1
                continue
            emb, err = None, ''
            for intento in range(3):
                try:
                    emb = _embed_try(texto)
                    break
                except Exception as e:
                    err = str(e)
                    time.sleep(1.5)
            if not emb:
                fallos += 1
                self.stderr.write(self.style.ERROR('  fallo: %s -> %s' % (a.slug, err)))
                continue
            a.embedding = json.dumps(emb)
            a.embedding_hash = h
            a.save(update_fields=['embedding', 'embedding_hash'])
            hechos += 1
            self.stdout.write('  ok: %s (dim %d)' % (a.slug, len(emb)))
            time.sleep(0.2)
        self.stdout.write(self.style.SUCCESS(
            'Reindex: %d nuevos, %d sin cambios, %d fallos (de %d)' % (hechos, saltados, fallos, total)))
