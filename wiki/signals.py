"""Señales de la app. Se conectan en WikiConfig.ready()."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Article


@receiver(post_save, sender=Article)
def reindexar_al_guardar(sender, instance, update_fields=None, **kwargs):
    """Al guardar un artículo publicado se recalculan sus embeddings en Celery."""
    if update_fields and set(update_fields) <= {'embedding_hash'}:
        return
    if not instance.is_published:
        return
    try:
        from .tasks import reindex_article_task
        reindex_article_task.delay(instance.pk)
    except Exception:
        pass   # sin Redis/Celery el artículo se guarda igual; se reindexa con reindex_articles
