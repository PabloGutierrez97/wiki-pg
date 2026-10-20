"""Tareas de Celery. Los nombres de las funciones no deben cambiar: las tareas
programadas que ya están en Redis se buscan por "wiki.tasks.<nombre>"."""
from celery import shared_task

TEXTO_LINKEDIN_POR_DEFECTO = """Acabo de publicar un nuevo artículo en mi wiki técnica: {titulo}
Lee el artículo completo aquí: {url}
#sysadmin #linux #infraestructura #tecnologia"""


@shared_task
def publish_to_linkedin_task(article_id):
    from .linkedin import comment_on_post, post_to_linkedin
    from .models import Article, LinkedInToken

    try:
        article = Article.objects.get(pk=article_id)
        token = LinkedInToken.get()
        if not token:
            return 'No hay token de LinkedIn configurado'

        text = article.linkedin_text or TEXTO_LINKEDIN_POR_DEFECTO.format(
            titulo=article.title, url=article.url_publica)
        image_path = article.linkedin_image.path if article.linkedin_image else None
        result = post_to_linkedin(token.access_token, token.author_id, text, image_path=image_path)

        article.linkedin_published = True
        article.save(update_fields=['linkedin_published'])   # sin tocar updated_at (sitemap y "Actualizado")

        # Primer comentario con el enlace al artículo
        post_urn = result.get('id')
        comment_result = None
        if post_urn:
            comment_result = comment_on_post(token.access_token, token.author_id, post_urn,
                                             f"Artículo completo aquí: {article.url_publica}")
        return f'Publicado correctamente: {result}. Comentario: {comment_result}'
    except Exception as e:
        return f'Error: {e}'


@shared_task(bind=True)
def publish_article_task(self, article_id):
    from .models import Article

    try:
        article = Article.objects.get(pk=article_id)
        if article.is_published:
            return 'Ya estaba publicado'
        if not article.publish_scheduled:
            return 'Programación cancelada; no se publica'
        if article.publish_task_id and article.publish_task_id != self.request.id:
            return 'Tarea sustituida por otra programación; no se publica'
        article.is_published = True
        article.save()
        return f'Artículo "{article.title}" publicado correctamente'
    except Exception as e:
        return f'Error al publicar artículo: {e}'


@shared_task
def reindex_article_task(article_id):
    from .ai.rag import reindexar_articulo
    from .models import Article

    article = Article.objects.filter(pk=article_id).first()
    if not article:
        return 'articulo no existe'
    if not article.is_published:
        return 'no publicado, se omite'
    estado, n = reindexar_articulo(article)
    return '%s (%d fragmentos)' % (estado, n)
