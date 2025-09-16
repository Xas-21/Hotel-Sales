"""
Context processors for making user preferences available globally across all templates.
"""

from form_composer.preference_service import PreferenceService


def user_preferences(request):
    """
    Inject user preferences into template context for all views.
    Makes navigation placement, UI theme, and other preferences 
    available as 'user_prefs' in all templates.
    """
    if not hasattr(request, 'user'):
        # Handle cases where user might not be available
        return {
            'user_prefs': {
                'navigation': {
                    'navigation_placement': 'left',
                    'sidebar_width': 'medium',
                    'ui_theme': 'light'
                },
                'form_composer': {
                    'layout': 'horizontal',
                    'auto_save_interval': 5,
                    'show_field_keys': False
                }
            }
        }
    
    # Get user preferences from the service
    navigation_prefs = PreferenceService.get_navigation_context(request.user)
    form_composer_prefs = PreferenceService.get_form_composer_context(request.user)
    
    return {
        'user_prefs': {
            'navigation': navigation_prefs,
            'form_composer': form_composer_prefs
        }
    }