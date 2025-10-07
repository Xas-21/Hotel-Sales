"""
Custom middleware for timezone detection and management.
"""
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin
from .timezone_utils import get_user_timezone, set_user_timezone


class TimezoneMiddleware(MiddlewareMixin):
    """
    Middleware to activate user's timezone.
    """
    
    def process_request(self, request):
        """
        Activate user's timezone for the request.
        """
        user_timezone = get_user_timezone(request)
        if user_timezone:
            timezone.activate(user_timezone)
        else:
            # Default to Riyadh timezone
            timezone.activate('Asia/Riyadh')
    
    def process_response(self, request, response):
        """
        Clean up timezone after request.
        """
        timezone.deactivate()
        return response

