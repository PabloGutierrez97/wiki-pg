from celery import shared_task
from django.utils import timezone

@shared_task
def publish_to_linkedin_task(article_id):
    from .models import Article, LinkedInToken
    from .linkedin import post_to_linkedin, comment_on_post

    try:
        article = Article.objects.get(pk=article_id)
        token = LinkedInToken.get()

        if not token:
            return 'No hay token de LinkedIn configurado'

        if article.linkedin_text:
            text = article.linkedin_text
        else:
            text = f"""Acabo de publicar un nuevo artículo en mi wiki técnica: {article.title}
Lee el artículo completo aquí: https://wiki.pablogg.dev/article/{article.slug}/
#sysadmin #linux #infraestructura #tecnologia"""

        result = post_to_linkedin(token.access_token, token.author_id, text)

        # Marcar como publicado
        article.linkedin_published = True
        article.save()

        # Comentar con el enlace al artículo
        post_urn = result.get('id')
        comment_result = None
        if post_urn:
            comment_text = f"Artículo completo aquí: https://wiki.pablogg.dev/article/{article.slug}/"
            comment_result = comment_on_post(token.access_token, token.author_id, post_urn, comment_text)

        return f'Publicado correctamente: {result}. Comentario: {comment_result}'
    except Exception as e:
        return f'Error: {str(e)}'

@shared_task
def publish_article_task(article_id):
    from .models import Article

    try:
        article = Article.objects.get(pk=article_id)
        article.is_published = True
        article.save()
        return f'Artículo "{article.title}" publicado correctamente'
    except Exception as e:
        return f'Error al publicar artículo: {str(e)}'


@shared_task
def reindex_article_task(article_id):
    from .models import Article
    from .terminal import reindexar_articulo
    try:
        a = Article.objects.get(pk=article_id)
    except Article.DoesNotExist:
        return 'articulo no existe'
    if not a.is_published:
        return 'no publicado, se omite'
    estado, n = reindexar_articulo(a)
    return '%s (%d fragmentos)' % (estado, n)
