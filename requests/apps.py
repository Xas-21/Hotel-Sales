from django.apps import AppConfig


class RequestsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'requests'
    
    def ready(self):
        # Import signals to register them
        try:
            import requests.signals
        except ImportError:
            pass
        
        # Import configuration enforcement to register signal handlers
        import requests.services.config_enforcement
