"""Conexión con LinkedIn y publicación manual desde el admin (solo staff con 2FA)."""
import logging
import secrets

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from .. import linkedin
from ..models import Article, LinkedInToken
from ..security import staff_verificado

log = logging.getLogger(__name__)

SESION_STATE = 'linkedin_oauth_state'


def _al_admin():
    return redirect(reverse('admin:index'))


@staff_verificado
def linkedin_auth(request):
    state = secrets.token_urlsafe(32)
    request.session[SESION_STATE] = state
    return redirect(linkedin.get_auth_url(state))


@staff_verificado
def linkedin_callback(request):
    # El state impide que alguien te "conecte" su propia cuenta con un enlace preparado.
    esperado = request.session.pop(SESION_STATE, None)
    if not esperado or not secrets.compare_digest(esperado, request.GET.get('state', '')):
        return _al_admin()

    code = request.GET.get('code')
    if not code:
        return _al_admin()
    access_token = linkedin.get_access_token(code).get('access_token')
    if not access_token:
        return _al_admin()

    LinkedInToken(access_token=access_token,
                  author_id=linkedin.get_profile(access_token).get('sub')).save()
    return _al_admin()


@staff_verificado
@require_POST
def linkedin_post(request, article_id):
    token = LinkedInToken.get()
    if not token:
        return redirect(reverse('admin:wiki_linkedintoken_changelist'))
    article = get_object_or_404(Article, pk=article_id)
    text = request.POST.get('text', f'Nuevo artículo en mi wiki: {article.title}\n\n{article.url_publica}')
    linkedin.post_to_linkedin(token.access_token, token.author_id, text[:3000])
    return redirect(reverse('admin:wiki_article_change', args=[article_id]))


@staff_verificado
@require_POST
def generate_linkedin_text(request, article_id):
    article = get_object_or_404(Article, pk=article_id)
    try:
        return JsonResponse({'text': linkedin.texto_con_gemini(article)})
    except Exception:
        log.exception('Error generando el texto de LinkedIn con Gemini')
        return JsonResponse({'error': 'Gemini no ha respondido; prueba de nuevo en un momento'}, status=502)
