from django.core.cache import cache


def maintenance_flag(request):
    """Injects global maintenance banner flag into templates."""
    enabled = cache.get('maintenance_banner_enabled', False)
    return {
        'maintenance_banner_enabled': enabled
    }