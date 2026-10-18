from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.generic import TemplateView
from mdeditor.views import UploadView
from two_factor.urls import urlpatterns as tf_urls

from wiki.security import staff_verificado
from wiki.sitemaps import SITEMAPS

urlpatterns = [
    path('', include(tf_urls)),
    path(settings.ADMIN_URL, admin.site.urls),
    # Honeypot: el /admin/ "de siempre" es falso y registra quién lo intenta.
    path('admin/', include('wiki.urls_honeypot')),
    # La subida de imágenes del editor era anónima y sin CSRF (django-mdeditor):
    # ahora solo para staff con 2FA. Mismo nombre de URL que usa el editor.
    path('mdeditor/uploads/', staff_verificado(UploadView.as_view()), name='uploads'),
    path('sitemap.xml', sitemap, {'sitemaps': SITEMAPS}, name='django.contrib.sitemaps.views.sitemap'),
    path('robots.txt', TemplateView.as_view(template_name='robots.txt', content_type='text/plain')),
    path('', include('wiki.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
