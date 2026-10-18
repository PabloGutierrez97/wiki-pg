"""Cliente de la API de LinkedIn (OAuth, publicaciones con imagen y comentarios)
y generación del texto del post con Gemini."""
from urllib.parse import quote, urlencode

import requests
from django.conf import settings

# Sin timeout, una API de LinkedIn colgada dejaría colgado al worker de Celery para siempre.
TIMEOUT = 30
TIMEOUT_SUBIDA = 60

LINKEDIN_AUTH_URL = 'https://www.linkedin.com/oauth/v2/authorization'
LINKEDIN_TOKEN_URL = 'https://www.linkedin.com/oauth/v2/accessToken'
LINKEDIN_API_URL = 'https://api.linkedin.com/v2'

GEMINI_MODELO = 'gemini-2.0-flash'


def _cabeceras(access_token):
    return {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'X-Restli-Protocol-Version': '2.0.0',
    }


def _persona(author_id):
    return f'urn:li:person:{author_id}'


# ---------------------------------------------------------------- OAuth --

def get_auth_url(state):
    params = {
        'response_type': 'code',
        'client_id': settings.LINKEDIN_CLIENT_ID,
        'redirect_uri': settings.LINKEDIN_REDIRECT_URI,
        'scope': 'openid profile w_member_social',
        'state': state,
    }
    return f'{LINKEDIN_AUTH_URL}?{urlencode(params)}'


def get_access_token(code):
    response = requests.post(LINKEDIN_TOKEN_URL, data={
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': settings.LINKEDIN_REDIRECT_URI,
        'client_id': settings.LINKEDIN_CLIENT_ID,
        'client_secret': settings.LINKEDIN_CLIENT_SECRET,
    }, timeout=TIMEOUT)
    return response.json()


def get_profile(access_token):
    response = requests.get(f'{LINKEDIN_API_URL}/userinfo',
                            headers={'Authorization': f'Bearer {access_token}'}, timeout=TIMEOUT)
    return response.json()


# --------------------------------------------------------- publicaciones --

def _subir_imagen(access_token, author_id, image_path):
    """Registra y sube una imagen a LinkedIn; devuelve el asset URN."""
    register = {
        'registerUploadRequest': {
            'recipes': ['urn:li:digitalmediaRecipe:feedshare-image'],
            'owner': _persona(author_id),
            'serviceRelationships': [
                {'relationshipType': 'OWNER', 'identifier': 'urn:li:userGeneratedContent'}
            ],
        }
    }
    r = requests.post(f'{LINKEDIN_API_URL}/assets?action=registerUpload',
                      headers=_cabeceras(access_token), json=register, timeout=TIMEOUT)
    r.raise_for_status()
    value = r.json()['value']
    upload_url = value['uploadMechanism']['com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest']['uploadUrl']
    with open(image_path, 'rb') as f:
        up = requests.post(upload_url, headers={'Authorization': f'Bearer {access_token}'},
                           data=f.read(), timeout=TIMEOUT_SUBIDA)
    up.raise_for_status()
    return value['asset']


def post_to_linkedin(access_token, author_id, text, image_path=None):
    share_content = {
        'shareCommentary': {'text': text},
        'shareMediaCategory': 'NONE',
    }
    if image_path:
        asset = _subir_imagen(access_token, author_id, image_path)
        share_content['shareMediaCategory'] = 'IMAGE'
        share_content['media'] = [{'status': 'READY', 'media': asset}]
    payload = {
        'author': _persona(author_id),
        'lifecycleState': 'PUBLISHED',
        'specificContent': {'com.linkedin.ugc.ShareContent': share_content},
        'visibility': {'com.linkedin.ugc.MemberNetworkVisibility': 'PUBLIC'},
    }
    response = requests.post(f'{LINKEDIN_API_URL}/ugcPosts', headers=_cabeceras(access_token),
                             json=payload, timeout=TIMEOUT)
    return response.json()


def comment_on_post(access_token, author_id, post_urn, comment_text):
    payload = {
        'actor': _persona(author_id),
        'object': post_urn,
        'message': {'text': comment_text},
    }
    response = requests.post(f'{LINKEDIN_API_URL}/socialActions/{quote(post_urn, safe="")}/comments',
                             headers=_cabeceras(access_token), json=payload, timeout=TIMEOUT)
    return response.json()


# ---------------------------------------------------------------- Gemini --

PROMPT_GEMINI = """Eres un asistente que escribe publicaciones de LinkedIn para un administrador de sistemas que comparte artículos técnicos en su wiki personal.

Genera un texto de LinkedIn en español, profesional pero cercano, basado en este artículo:

Título: {titulo}
Contenido: {contenido}

El texto debe:
- Tener entre 3 y 5 frases
- Sonar natural, no como un anuncio genérico
- Terminar con 3-4 hashtags relevantes en español
- NO incluir la URL del artículo (se añadirá después)

Devuelve solo el texto del post, sin comillas ni explicaciones adicionales."""


def texto_con_gemini(article):
    """Borrador del post de LinkedIn para un artículo, con el enlace al final."""
    from google import genai   # import pesado: solo cuando se usa

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODELO,
        contents=PROMPT_GEMINI.format(titulo=article.title, contenido=article.content[:2000]),
    )
    return response.text.strip() + f"\n\nLee el artículo completo aquí: {article.url_publica}"
