import json

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from mdeditor.fields import MDTextField

PALABRAS_POR_MINUTO = 200


class Category(models.Model):
    name        = models.CharField(max_length=100)
    slug        = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    icon        = models.CharField(max_length=100, blank=True, default='fa-solid fa-folder', help_text='Clase de Font Awesome o Simple Icons. Ej: fa-brands fa-linux')
    parent      = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='subcategories')
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        if self.parent:
            return f'{self.parent.name} - {self.name}'
        return self.name

class ArticleQuerySet(models.QuerySet):
    def publicados(self):
        return self.filter(is_published=True)


class Article(models.Model):
    title        = models.CharField(max_length=200)
    slug         = models.SlugField(unique=True)
    content      = MDTextField()
    category     = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='articles')
    author       = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)
    is_published = models.BooleanField(default=False)
    publish_scheduled = models.DateTimeField(null=True, blank=True, help_text='Fecha y hora a la que se publicará automáticamente el artículo en la wiki')
    publish_task_id = models.CharField(max_length=100, blank=True, null=True)
    meta_description = models.CharField(
        max_length=160, blank=True,
        help_text='Resumen para Google y LinkedIn (unos 155 caracteres). Si se deja vacío, se genera '
                  'automáticamente con el inicio del artículo.')
    tags = models.CharField(max_length=300, blank=True, help_text='Etiquetas separadas por comas. Ej: linux, docker, ansible')
    featured_image = models.ImageField(upload_to='articles/', blank=True, null=True, help_text='Imagen destacada del articulo')
    linkedin_text = models.TextField(blank=True, help_text='Texto personalizado para LinkedIn. Si se deja vacío se usará el título.')
    linkedin_image = models.ImageField(upload_to='linkedin/', blank=True, null=True, help_text='Imagen para la publicacion de LinkedIn. Si se deja vacia, se publica solo texto.')
    linkedin_scheduled = models.DateTimeField(null=True, blank=True, help_text='Fecha y hora de publicación en LinkedIn')
    linkedin_published = models.BooleanField(default=False)
    linkedin_task_id = models.CharField(max_length=100, blank=True, null=True)

    # Huella del texto indexado para la IA: si no cambia, no se recalculan los embeddings.
    embedding_hash = models.CharField(max_length=64, blank=True, default='')

    objects = ArticleQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('wiki:article_detail', args=[self.slug])

    @property
    def url_publica(self):
        return settings.SITE_URL + self.get_absolute_url()

    @property
    def tag_list(self):
        return [t.strip() for t in (self.tags or '').split(',') if t.strip()]

    @property
    def minutos_lectura(self):
        return max(1, round(len(self.content.split()) / PALABRAS_POR_MINUTO))


class Profile(models.Model):
    nombre = models.CharField(max_length=100, default='Pablo Gutiérrez Gracia')
    cargo = models.CharField(max_length=200, default='Responsable de Sistemas')
    empresa = models.CharField(max_length=200, default='Texco Solutions SL')
    ubicacion = models.CharField(max_length=200, default='Almodóvar del Río, Córdoba, España')
    email = models.EmailField(default='pgutigracia@gmail.com')
    linkedin = models.URLField(blank=True)
    descripcion = models.TextField(blank=True)
    stack = models.TextField(blank=True, help_text='Formato JSON: {"sistemas": "Windows, Linux", "cloud": "M365"}')
    experiencia = models.TextField(blank=True, help_text='Describe tu experiencia profesional en texto libre')
    formacion = models.TextField(blank=True, help_text='Describe tu formación académica en texto libre')
    certificaciones = models.TextField(blank=True, help_text='Lista de certificaciones separadas por comas')

    class Meta:
        verbose_name = 'Perfil'
        verbose_name_plural = 'Perfil'

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def stack_dict(self):
        """El stack como diccionario {area: tecnologias}; vacío si el JSON no es válido."""
        try:
            data = json.loads(self.stack or '{}')
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def stack_texto(self):
        """El stack en una línea ("area: tecnologias; ..."), o el texto tal cual si no es JSON."""
        data = self.stack_dict()
        if data:
            return '; '.join('%s: %s' % (k, v) for k, v in data.items())
        return (self.stack or '').strip()


class LinkedInToken(models.Model):
    access_token = models.TextField()
    author_id = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Token LinkedIn'
        verbose_name_plural = 'Token LinkedIn'

    def __str__(self):
        return f'Token LinkedIn ({self.created_at})'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        return cls.objects.filter(pk=1).first()


class HoneypotAttempt(models.Model):
    ip = models.GenericIPAddressField()
    username = models.CharField(max_length=200, blank=True)
    user_agent = models.TextField(blank=True)
    path = models.CharField(max_length=200, default='/admin/')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Intento honeypot'
        verbose_name_plural = 'Intentos honeypot'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.ip} - {self.username} ({self.created_at:%d/%m/%Y %H:%M})'


class ArticleChunk(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='chunks')
    idx = models.IntegerField(default=0)
    text = models.TextField()
    embedding = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['article_id', 'idx']

    def __str__(self):
        return 'chunk %s#%d' % (self.article_id, self.idx)

