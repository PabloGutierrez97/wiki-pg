from django.contrib import admin
from .models import Category, Article, SiteConfig, Profile, LinkedInToken

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display        = ['name', 'parent', 'slug', 'created_at']
    search_fields       = ['name']
    list_filter         = ['parent']
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display        = ['title', 'category', 'author', 'is_published', 'linkedin_published', 'linkedin_scheduled', 'created_at']
    list_filter         = ['is_published', 'linkedin_published', 'category']
    search_fields       = ['title', 'content', 'tags']
    prepopulated_fields = {'slug': ('title',)}
    fieldsets = (
    ('Contenido', {
        'fields': ('title', 'slug', 'content', 'category', 'author', 'tags', 'is_published', 'publish_scheduled', 'featured_image')
    }),
    ('LinkedIn', {
        'fields': ('linkedin_text', 'linkedin_scheduled', 'linkedin_published'),
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
        from wiki_pg.celery import app as celery_app

        # Programar publicación del artículo en la wiki
        if obj.publish_scheduled and not obj.is_published:
            from .tasks import publish_article_task

            if obj.publish_task_id:
                celery_app.control.revoke(obj.publish_task_id)

            result = publish_article_task.apply_async(
                args=[obj.id],
                eta=obj.publish_scheduled
            )
            obj.publish_task_id = result.id
            obj.save(update_fields=['publish_task_id'])

        # Programar publicación en LinkedIn
        if obj.linkedin_scheduled and not obj.linkedin_published:
            from .tasks import publish_to_linkedin_task

            if obj.linkedin_task_id:
                celery_app.control.revoke(obj.linkedin_task_id)

            result = publish_to_linkedin_task.apply_async(
                args=[obj.id],
                eta=obj.linkedin_scheduled
            )
            obj.linkedin_task_id = result.id
            obj.save(update_fields=['linkedin_task_id'])

@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not SiteConfig.objects.exists()

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not Profile.objects.exists()

@admin.register(LinkedInToken)
class LinkedInTokenAdmin(admin.ModelAdmin):
    list_display = ['author_id', 'created_at']

    def has_add_permission(self, request):
        return False

from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_email.models import EmailDevice

admin.site.unregister(TOTPDevice)
admin.site.unregister(StaticDevice)
admin.site.unregister(EmailDevice)

from .models import HoneypotAttempt

@admin.register(HoneypotAttempt)
class HoneypotAttemptAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'ip', 'username', 'path']
    list_filter = ['created_at', 'path']
    search_fields = ['ip', 'username', 'user_agent']
    readonly_fields = ['ip', 'username', 'user_agent', 'path', 'created_at']

    def has_add_permission(self, request):
        return False
