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
        
        # Avoid database access during app initialization in production.
        # Gate the optional field sync behind DEBUG or explicit opt-in env var.
        try:
            from django.conf import settings
            import os, sys
            run_sync = (
                (bool(getattr(settings, 'DEBUG', False)) and ('runserver' in sys.argv)) or
                (os.getenv('ENABLE_FIELD_SYNC_ON_STARTUP', 'False').lower() == 'true')
            )

            if run_sync:
                from requests.services.field_sync_service import FieldSyncService
                FieldSyncService.ensure_sync_on_startup()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Skipped field sync on startup: {e}")
