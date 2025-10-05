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
        
        # Register admin form injection for custom fields
        try:
            from requests.services.admin_form_injector import auto_register_admin_injection
            auto_register_admin_injection()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to register admin injection: {e}")
        
        # Disable field sync during startup to avoid database access issues
        # This can be re-enabled later if needed
        pass
