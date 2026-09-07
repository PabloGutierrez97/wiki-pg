import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wiki_pg.settings')

app = Celery('wiki_pg')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
