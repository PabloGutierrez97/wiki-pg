from django.urls import path
from . import views

urlpatterns = [
    path('', views.honeypot_admin),
    path('login/', views.honeypot_admin),
]
