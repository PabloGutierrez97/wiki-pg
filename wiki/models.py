from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
from mdeditor.fields import MDTextField

class Category(models.Model):
    name        = models.CharField(max_length=100)
    slug        = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    icon	= models.CharField(max_length=100, blank=True, default='fa-solid fa-folder', help_text='Clase de Font Awesome o Simple Icons. Ej: fa-brands fa-linux')
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
    tags = models.CharField(max_length=300, blank=True, help_text='Etiquetas separadas por comas. Ej: linux, docker, ansible')
    featured_image = models.ImageField(upload_to='articles/', blank=True, null=True, help_text='Imagen destacada del articulo')
    linkedin_text = models.TextField(blank=True, help_text='Texto personalizado para LinkedIn. Si se deja vacío se usará el título.')
    linkedin_scheduled = models.DateTimeField(null=True, blank=True, help_text='Fecha y hora de publicación en LinkedIn')
    linkedin_published = models.BooleanField(default=False)
    linkedin_task_id = models.CharField(max_length=100, blank=True, null=True)

    # --- RAG: busqueda semantica ---
    embedding = models.TextField(blank=True, default='')
    embedding_hash = models.CharField(max_length=64, blank=True, default='')

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

class SiteConfig(models.Model):
    favicon = models.ImageField(upload_to='favicon/', blank=True, null=True)

    class Meta:
        verbose_name = 'Configuracion del sitio'
        verbose_name_plural = 'Configuracion del sitio'

    def __str__(self):
        return 'Configuracion del sitio'

    def save(self, *args, **kwargs):
        # Solo permitir una instancia
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

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
        obj = cls.objects.filter(pk=1).first()
        return obj


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


# --- RAG: reindexar automaticamente al guardar un articulo publicado ---
from django.db.models.signals import post_save as _post_save
from django.dispatch import receiver as _receiver


@_receiver(_post_save, sender=Article)
def _reindex_articulo(sender, instance, created=False, update_fields=None, **kwargs):
    if update_fields and set(update_fields) <= {'embedding', 'embedding_hash'}:
        return
    if not instance.is_published:
        return
    try:
        from .tasks import reindex_article_task
        reindex_article_task.delay(instance.pk)
    except Exception:
        pass
