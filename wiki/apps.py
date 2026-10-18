from django.apps import AppConfig


class WikiConfig(AppConfig):
    name = 'wiki'

    def ready(self):
        from . import signals  # noqa: F401
