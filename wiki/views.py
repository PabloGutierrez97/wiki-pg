from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.utils.html import strip_tags
from .models import Category, Article
import markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from django.db import models

def home(request):
    from django.utils import timezone
    categories = Category.objects.filter(parent=None)
    recent_articles = Article.objects.filter(is_published=True)[:5]
    
    # Stats
    total_articles = Article.objects.filter(is_published=True).count()
    total_categories = Category.objects.count()
    last_updated = Article.objects.filter(is_published=True).order_by('-updated_at').first()
    
    return render(request, 'wiki/home.html', {
        'categories': categories,
        'recent_articles': recent_articles,
        'total_articles': total_articles,
        'total_categories': total_categories,
        'last_updated': last_updated,
    })

def category_detail(request, slug):
    category = get_object_or_404(Category, slug=slug)
    articles = Article.objects.filter(category=category, is_published=True)
    md = markdown.Markdown()
    for article in articles:
        article.summary = strip_tags(md.convert(article.content))[:200]
        md.reset()
    return render(request, 'wiki/category_detail.html', {
        'category': category,
        'articles': articles
    })

def article_detail(request, slug):
    article = get_object_or_404(Article, slug=slug, is_published=True)
    md = markdown.Markdown(extensions=[
        'fenced_code',
        'tables',
        'toc',
        CodeHiliteExtension(linenums=False, css_class='highlight')
    ])
    content_html = md.convert(article.content)
    toc = md.toc

    # Tiempo de lectura (200 palabras por minuto)
    word_count = len(article.content.split())
    reading_time = max(1, round(word_count / 200))

    # Justo antes del return render en article_detail
    tags = [t.strip() for t in article.tags.split(',') if t.strip()] if article.tags else []

    featured_image_url = None
    if article.featured_image and article.featured_image.name:
        try:
            featured_image_url = article.featured_image.url
        except ValueError:
            pass

    return render(request, 'wiki/article_detail.html', {
        'article': article,
        'content_html': content_html,
        'toc': toc,
        'reading_time': reading_time,
        'tags': tags,
        'featured_image_url': featured_image_url,
    })

def search(request):
    query = request.GET.get('q', '')
    results = []
    if query:
        articles = Article.objects.filter(
            is_published=True
        ).filter(
            models.Q(title__icontains=query) |
            models.Q(content__icontains=query) |
            models.Q(tags__icontains=query) |
            models.Q(category__name__icontains=query)
        ).distinct()
        md = markdown.Markdown()
        for article in articles:
            article.summary = strip_tags(md.convert(article.content))[:200]
            md.reset()
        results = articles
    return render(request, 'wiki/search.html', {
        'query': query,
        'results': results
    })

def about(request):
    from .models import Profile
    import json
    profile = Profile.get()
    stack = {}
    if profile.stack:
        try:
            stack = json.loads(profile.stack)
        except:
            stack = {}
    return render(request, 'wiki/about.html', {
        'profile': profile,
        'stack': stack,
    })

def linkedin_auth(request):
    from .linkedin import get_auth_url
    return redirect(get_auth_url())

def linkedin_callback(request):
    from .linkedin import get_access_token, get_profile
    from .models import LinkedInToken
    
    code = request.GET.get('code')
    if not code:
        return redirect('/admin/')
    
    token_data = get_access_token(code)
    access_token = token_data.get('access_token')
    
    if not access_token:
        return redirect('/admin/')
    
    profile = get_profile(access_token)
    author_id = profile.get('sub')
    
    token = LinkedInToken()
    token.access_token = access_token
    token.author_id = author_id
    token.save()
    
    return redirect('/admin/')

def linkedin_post(request, article_id):
    from .linkedin import post_to_linkedin
    from .models import LinkedInToken
    
    if request.method != 'POST':
        return redirect('/admin/')
    
    token = LinkedInToken.get()
    if not token:
        return redirect('/admin/wiki/linkedintoken/')
    
    article = get_object_or_404(Article, pk=article_id)
    text = request.POST.get('text', f'Nuevo artículo en mi wiki: {article.title}\n\nhttps://wiki.pablogg.dev/article/{article.slug}/')
    
    result = post_to_linkedin(token.access_token, token.author_id, text)
    
    return redirect(f'/admin/wiki/article/{article_id}/change/')

def tag_detail(request, tag):
    articles = Article.objects.filter(
        is_published=True,
        tags__icontains=tag
    )
    return render(request, 'wiki/tag_detail.html', {
        'tag': tag,
        'articles': articles
    })

def generate_linkedin_text(request, article_id):
    from google import genai
    from django.conf import settings
    from django.http import JsonResponse

    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    article = get_object_or_404(Article, pk=article_id)

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    prompt = f"""Eres un asistente que escribe publicaciones de LinkedIn para un administrador de sistemas que comparte artículos técnicos en su wiki personal.

Genera un texto de LinkedIn en español, profesional pero cercano, basado en este artículo:

Título: {article.title}
Contenido: {article.content[:2000]}

El texto debe:
- Tener entre 3 y 5 frases
- Sonar natural, no como un anuncio genérico
- Terminar con 3-4 hashtags relevantes en español
- NO incluir la URL del artículo (se añadirá después)

Devuelve solo el texto del post, sin comillas ni explicaciones adicionales."""

    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt
        )
        text = response.text.strip()
        text += f"\n\nLee el artículo completo aquí: https://wiki.pablogg.dev/article/{article.slug}/"
        return JsonResponse({'text': text})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def honeypot_admin(request):
    from .models import HoneypotAttempt
    from django.http import HttpResponse

    if request.method == 'POST':
        ip = request.META.get('HTTP_CF_CONNECTING_IP') or request.META.get('REMOTE_ADDR', '0.0.0.0')
        HoneypotAttempt.objects.create(
            ip=ip,
            username=request.POST.get('username', '')[:200],
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:1000],
            path=request.path,
        )

    return render(request, 'wiki/honeypot_login.html', {
        'error': request.method == 'POST',
    })


def search_api(request):
    from django.http import JsonResponse
    query = request.GET.get('q', '').strip()
    resultados = []
    if len(query) >= 2:
        articles = Article.objects.filter(
            is_published=True
        ).filter(
            models.Q(title__icontains=query) |
            models.Q(content__icontains=query) |
            models.Q(tags__icontains=query) |
            models.Q(category__name__icontains=query)
        ).distinct()[:6]
        for article in articles:
            resultados.append({
                'title': article.title,
                'url': f'/article/{article.slug}/',
                'category': article.category.name if article.category else '',
            })
    return JsonResponse({'results': resultados})


def terminal_page(request):
    return render(request, 'wiki/terminal.html')
