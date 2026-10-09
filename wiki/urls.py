from django.urls import path
from . import views
from .terminal import terminal_command, terminal_ask

app_name = 'wiki'

urlpatterns = [
    path('', views.home, name='home'),
    path('search/', views.search, name='search'),
    path('about/', views.about, name='about'),
    path('category/<slug:slug>/', views.category_detail, name='category_detail'),
    path('article/<slug:slug>/', views.article_detail, name='article_detail'),
    path('linkedin/auth/', views.linkedin_auth, name='linkedin_auth'),
    path('linkedin/callback/', views.linkedin_callback, name='linkedin_callback'),
    path('linkedin/post/<int:article_id>/', views.linkedin_post, name='linkedin_post'),
    path('tag/<str:tag>/', views.tag_detail, name='tag_detail'),
    path('linkedin/generate/<int:article_id>/', views.generate_linkedin_text, name='generate_linkedin_text'),
    path('search/api/', views.search_api, name='search_api'),
    path('terminal/', views.terminal_page, name='terminal'),
    path('terminal/cmd/', terminal_command, name='terminal_command'),
    path('terminal/ask/', terminal_ask, name='terminal_ask'),
]
