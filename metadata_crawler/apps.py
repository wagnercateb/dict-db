from django.apps import AppConfig

from django.apps import AppConfig
from django.db.utils import OperationalError, ProgrammingError

"""
When you start a Django project (e.g., with runserver, migrate, or shell), Django will import:
    (first loads settings.py)
    Your app's apps.py config.
    Your app’s models.py, because Django scans models during setup.
    Anything imported at the top level of those modules (including things like forms, utils, signals, etc.)
    Any module you import directly in urls.py, views.py, or elsewhere in your code.
"""

class MetadataCrawlerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'metadata_crawler'


# inicializa username e password após os outros objetos do Django terem sido inicializados
class Metadata_Crawler_Config(AppConfig):
    name = 'myapp'

    def ready(self):
        # Delay import until environment and app are ready
        try:
            from .models import DatabaseConnection
            from .utilitarios import autenticar_usuario  
        except ImportError:
            return  # Silent fail if model or function not ready

        try:
            # Check if default DB connection exists
            if not DatabaseConnection.objects.filter(name='Default Connection').exists():
                # ✅ This runs only if environment is fully ready
                username, password = autenticar_usuario()

                DatabaseConnection.objects.create(
                    username=username,
                    password=password,
                )
        except (OperationalError, ProgrammingError):
            # Happens during migrate or if DB isn't fully ready yet
            pass
