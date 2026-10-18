from django.contrib import admin
from django_otp.plugins.otp_email.models import EmailDevice
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

from .models import Article, Category, HoneypotAttempt, LinkedInToken, Profile

# Los dispositivos 2FA se gestionan desde /account/two_factor/, no desde el admin.
for _modelo in (TOTPDevice, StaticDevice, EmailDevice):
    admin.site.unregister(_modelo)


def _programar(tarea, article, fecha, campo_task_id):
    """Programa `tarea` para `fecha`, cancelando la que hubiera antes para el mismo artículo."""
    from wiki_pg.celery import app as celery_app

    anterior = getattr(article, campo_task_id)
    if anterior:
        celery_app.control.revoke(anterior)
    result = tarea.apply_async(args=[article.id], eta=fecha)
    setattr(article, campo_task_id, result.id)
    article.save(update_fields=[campo_task_id])


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'slug', 'created_at']
    search_fields = ['name']
    list_filter = ['parent']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'author', 'is_published', 'linkedin_published',
                    'linkedin_scheduled', 'created_at']
    list_filter = ['is_published', 'linkedin_published', 'category']
    search_fields = ['title', 'content', 'tags']
    prepopulated_fields = {'slug': ('title',)}
    fieldsets = (
        ('Contenido', {
            'fields': ('title', 'slug', 'content', 'category', 'author', 'tags', 'is_published',
                       'publish_scheduled', 'featured_image'),
        }),
        ('LinkedIn', {
            'fields': ('linkedin_text', 'linkedin_image', 'linkedin_scheduled', 'linkedin_published'),
            'classes': ('collapse',),
        }),
    )

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['article_id'] = object_id
        extra_context['linkedin_connected'] = LinkedInToken.get() is not None
        return super().change_view(request, object_id, form_url, extra_context=extra_context)

    def add_view(self, request, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['linkedin_connected'] = False
        extra_context['hide_linkedin_panel'] = True
        return super().add_view(request, form_url, extra_context=extra_context)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from .tasks import publish_article_task, publish_to_linkedin_task

        if obj.publish_scheduled and not obj.is_published:
            _programar(publish_article_task, obj, obj.publish_scheduled, 'publish_task_id')
        if obj.linkedin_scheduled and not obj.linkedin_published:
            _programar(publish_to_linkedin_task, obj, obj.linkedin_scheduled, 'linkedin_task_id')


class _UnicoAdmin(admin.ModelAdmin):
    """Modelos de una sola fila: no se puede añadir otra."""

    def has_add_permission(self, request):
        return not self.model.objects.exists()


@admin.register(Profile)
class ProfileAdmin(_UnicoAdmin):
    pass


@admin.register(LinkedInToken)
class LinkedInTokenAdmin(admin.ModelAdmin):
    list_display = ['author_id', 'created_at']

    def has_add_permission(self, request):
        return False   # se crea al conectar la cuenta desde el botón de LinkedIn


@admin.register(HoneypotAttempt)
class HoneypotAttemptAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'ip', 'username', 'path']
    list_filter = ['created_at', 'path']
    search_fields = ['ip', 'username', 'user_agent']
    readonly_fields = ['ip', 'username', 'user_agent', 'path', 'created_at']

    def has_add_permission(self, request):
        return False
