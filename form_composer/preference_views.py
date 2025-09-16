"""
Views for managing user preferences in the form composer.
Provides AJAX endpoints for updating preferences and settings UI.
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.urls import reverse
import json

from form_composer.models import UserPreference
from .preference_service import PreferenceService


@login_required
def preferences_page(request):
    """User preferences management page"""
    # Ensure user has default preferences
    PreferenceService.ensure_user_preferences(request.user)
    
    # Get all current preferences
    preferences = UserPreference.get_all_user_preferences(request.user)
    
    context = {
        'preferences': preferences,
        'preference_choices': UserPreference.PREFERENCE_CHOICES,
        'defaults': UserPreference.PREFERENCE_DEFAULTS,
        'navigation_options': [
            ('left', 'Left Sidebar'),
            ('right', 'Right Sidebar'),
            ('top', 'Top Navigation'),
        ],
        'theme_options': [
            ('light', 'Light Theme'),
            ('dark', 'Dark Theme'),
            ('auto', 'Auto (System)'),
        ],
        'layout_options': [
            ('horizontal', 'Horizontal Layout'),
            ('vertical', 'Vertical Layout'),
        ],
        'sidebar_width_options': [
            ('small', 'Small'),
            ('medium', 'Medium'),
            ('large', 'Large'),
        ]
    }
    
    return render(request, 'form_composer/preferences.html', context)


@login_required
@require_POST
@csrf_protect
def update_preference(request):
    """AJAX endpoint to update a single preference"""
    try:
        data = json.loads(request.body)
        key = data.get('key')
        value = data.get('value')
        
        if not key:
            return JsonResponse({'success': False, 'error': 'Missing preference key'})
        
        # Update preference
        PreferenceService.update_preference(request.user, key, value)
        
        return JsonResponse({
            'success': True,
            'message': 'Preference updated successfully'
        })
        
    except ValueError as e:
        return JsonResponse({
            'success': False, 
            'error': str(e)
        })
    except Exception as e:
        return JsonResponse({
            'success': False, 
            'error': 'An error occurred while updating preference'
        })


@login_required
@require_POST
@csrf_protect
def reset_preferences(request):
    """Reset all user preferences to defaults"""
    try:
        PreferenceService.reset_user_preferences(request.user)
        messages.success(request, 'All preferences have been reset to defaults.')
        
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({
                'success': True,
                'message': 'Preferences reset successfully'
            })
        else:
            return redirect('form_composer:preferences')
            
    except Exception as e:
        error_msg = 'An error occurred while resetting preferences'
        
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({
                'success': False,
                'error': error_msg
            })
        else:
            messages.error(request, error_msg)
            return redirect('form_composer:preferences')


@login_required
def get_user_preferences(request):
    """Get all user preferences as JSON (for AJAX calls)"""
    preferences = UserPreference.get_all_user_preferences(request.user)
    navigation_context = PreferenceService.get_navigation_context(request.user)
    composer_context = PreferenceService.get_form_composer_context(request.user)
    
    return JsonResponse({
        'preferences': preferences,
        'navigation': navigation_context,
        'composer': composer_context
    })