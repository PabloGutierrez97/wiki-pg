from django import template
from wiki.models import Category

register = template.Library()

@register.simple_tag
def get_categories():
    return Category.objects.filter(parent=None)

@register.filter
def split(value, delimiter=','):
    return value.split(delimiter)

@register.filter
def trim(value):
    return value.strip()
