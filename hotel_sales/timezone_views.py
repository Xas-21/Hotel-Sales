"""
Timezone detection and management views.
"""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
import json
from .timezone_utils import (
    get_timezone_from_coordinates, 
    get_timezone_from_country_code,
    set_user_timezone,
    get_user_timezone
)


@csrf_exempt
@require_http_methods(["POST"])
def detect_timezone(request):
    """
    API endpoint to detect timezone from coordinates or country code.
    """
    try:
        data = json.loads(request.body)
        timezone_name = None
        
        # Try to get timezone from coordinates first
        if 'latitude' in data and 'longitude' in data:
            lat = float(data['latitude'])
            lon = float(data['longitude'])
            timezone_name = get_timezone_from_coordinates(lat, lon)
        
        # Fallback to country code
        if not timezone_name and 'country_code' in data:
            country_code = data['country_code'].upper()
            timezone_name = get_timezone_from_country_code(country_code)
        
        # Default to Riyadh if no timezone detected
        if not timezone_name:
            timezone_name = 'Asia/Riyadh'
        
        # Set user timezone in session
        if set_user_timezone(request, timezone_name):
            return JsonResponse({
                'success': True,
                'timezone': timezone_name,
                'message': f'Timezone set to {timezone_name}'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Invalid timezone'
            }, status=400)
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def get_current_timezone(request):
    """
    Get current user timezone.
    """
    timezone_name = get_user_timezone(request)
    return JsonResponse({
        'timezone': timezone_name
    })


@csrf_exempt
@require_http_methods(["POST"])
def set_timezone(request):
    """
    Manually set user timezone.
    """
    try:
        data = json.loads(request.body)
        timezone_name = data.get('timezone')
        
        if not timezone_name:
            return JsonResponse({
                'success': False,
                'error': 'Timezone is required'
            }, status=400)
        
        if set_user_timezone(request, timezone_name):
            return JsonResponse({
                'success': True,
                'timezone': timezone_name,
                'message': f'Timezone set to {timezone_name}'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Invalid timezone'
            }, status=400)
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

