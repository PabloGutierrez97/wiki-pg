from urllib.parse import urlencode

import requests
from django.conf import settings

# Sin timeout, una API de LinkedIn colgada dejaría colgado al worker de Celery para siempre.
TIMEOUT = 30

LINKEDIN_AUTH_URL = 'https://www.linkedin.com/oauth/v2/authorization'
LINKEDIN_TOKEN_URL = 'https://www.linkedin.com/oauth/v2/accessToken'
LINKEDIN_API_URL = 'https://api.linkedin.com/v2'

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
    headers = {'Authorization': f'Bearer {access_token}'}
    response = requests.get(f'{LINKEDIN_API_URL}/userinfo', headers=headers, timeout=TIMEOUT)
    return response.json()

def _subir_imagen_linkedin(access_token, author_id, image_path):
    """Registra y sube una imagen a LinkedIn; devuelve el asset URN."""
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'X-Restli-Protocol-Version': '2.0.0',
    }
    register = {
        'registerUploadRequest': {
            'recipes': ['urn:li:digitalmediaRecipe:feedshare-image'],
            'owner': f'urn:li:person:{author_id}',
            'serviceRelationships': [
                {'relationshipType': 'OWNER', 'identifier': 'urn:li:userGeneratedContent'}
            ],
        }
    }
    r = requests.post(f'{LINKEDIN_API_URL}/assets?action=registerUpload',
                      headers=headers, json=register, timeout=30)
    r.raise_for_status()
    value = r.json()['value']
    asset = value['asset']
    upload_url = value['uploadMechanism']['com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest']['uploadUrl']
    with open(image_path, 'rb') as f:
        data = f.read()
    up = requests.post(upload_url,
                       headers={'Authorization': f'Bearer {access_token}'},
                       data=data, timeout=60)
    up.raise_for_status()
    return asset


def post_to_linkedin(access_token, author_id, text, image_path=None):
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'X-Restli-Protocol-Version': '2.0.0'
    }
    share_content = {
        'shareCommentary': {'text': text},
        'shareMediaCategory': 'NONE',
    }
    if image_path:
        asset = _subir_imagen_linkedin(access_token, author_id, image_path)
        share_content['shareMediaCategory'] = 'IMAGE'
        share_content['media'] = [{'status': 'READY', 'media': asset}]
    payload = {
        'author': f'urn:li:person:{author_id}',
        'lifecycleState': 'PUBLISHED',
        'specificContent': {
            'com.linkedin.ugc.ShareContent': share_content
        },
        'visibility': {
            'com.linkedin.ugc.MemberNetworkVisibility': 'PUBLIC'
        }
    }
    response = requests.post(
        f'{LINKEDIN_API_URL}/ugcPosts',
        headers=headers,
        json=payload,
        timeout=30
    )
    return response.json()


def comment_on_post(access_token, author_id, post_urn, comment_text):
    from urllib.parse import quote

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'X-Restli-Protocol-Version': '2.0.0'
    }
    payload = {
        'actor': f'urn:li:person:{author_id}',
        'object': post_urn,
        'message': {
            'text': comment_text
        }
    }
    encoded_urn = quote(post_urn, safe='')
    response = requests.post(
        f'{LINKEDIN_API_URL}/socialActions/{encoded_urn}/comments',
        headers=headers,
        json=payload,
        timeout=TIMEOUT
    )
    return response.json()
