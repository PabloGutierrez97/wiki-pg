import requests
from django.conf import settings

LINKEDIN_AUTH_URL = 'https://www.linkedin.com/oauth/v2/authorization'
LINKEDIN_TOKEN_URL = 'https://www.linkedin.com/oauth/v2/accessToken'
LINKEDIN_API_URL = 'https://api.linkedin.com/v2'

def get_auth_url():
    params = {
        'response_type': 'code',
        'client_id': settings.LINKEDIN_CLIENT_ID,
        'redirect_uri': settings.LINKEDIN_REDIRECT_URI,
        'scope': 'openid profile w_member_social',
    }
    query = '&'.join([f'{k}={v}' for k, v in params.items()])
    return f'{LINKEDIN_AUTH_URL}?{query}'

def get_access_token(code):
    response = requests.post(LINKEDIN_TOKEN_URL, data={
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': settings.LINKEDIN_REDIRECT_URI,
        'client_id': settings.LINKEDIN_CLIENT_ID,
        'client_secret': settings.LINKEDIN_CLIENT_SECRET,
    })
    return response.json()

def get_profile(access_token):
    headers = {'Authorization': f'Bearer {access_token}'}
    response = requests.get(f'{LINKEDIN_API_URL}/userinfo', headers=headers)
    return response.json()

def post_to_linkedin(access_token, author_id, text):
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'X-Restli-Protocol-Version': '2.0.0'
    }
    payload = {
        'author': f'urn:li:person:{author_id}',
        'lifecycleState': 'PUBLISHED',
        'specificContent': {
            'com.linkedin.ugc.ShareContent': {
                'shareCommentary': {
                    'text': text
                },
                'shareMediaCategory': 'NONE'
            }
        },
        'visibility': {
            'com.linkedin.ugc.MemberNetworkVisibility': 'PUBLIC'
        }
    }
    response = requests.post(
        f'{LINKEDIN_API_URL}/ugcPosts',
        headers=headers,
        json=payload
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
        json=payload
    )
    return response.json()
