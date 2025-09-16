"""
Preference service for managing user preferences in the form composer.
Provides high-level APIs for preference management and UI customization.
"""

from django.contrib.auth.models import User
from django.conf import settings
from form_composer.models import UserPreference


class PreferenceService:
    """Service class for managing user preferences"""
    
    @staticmethod
    def get_navigation_context(user):
        """Get navigation-related preferences for template context"""
        if not user.is_authenticated:
            return {
                'navigation_placement': 'left',
                'sidebar_width': 'medium',
                'ui_theme': 'light'
            }
        
        return {
            'navigation_placement': UserPreference.get_user_preference_with_default(
                user, UserPreference.NAVIGATION_PLACEMENT
            ),
            'sidebar_width': UserPreference.get_user_preference_with_default(
                user, UserPreference.SIDEBAR_WIDTH
            ),
            'ui_theme': UserPreference.get_user_preference_with_default(
                user, UserPreference.UI_THEME
            )
        }
    
    @staticmethod
    def get_form_composer_context(user):
        """Get form composer-related preferences for template context"""
        if not user.is_authenticated:
            return {
                'layout': 'horizontal',
                'auto_save_interval': 5,
                'show_field_keys': False
            }
        
        return {
            'layout': UserPreference.get_user_preference_with_default(
                user, UserPreference.FORM_COMPOSER_LAYOUT
            ),
            'auto_save_interval': UserPreference.get_user_preference_with_default(
                user, UserPreference.AUTO_SAVE_INTERVAL
            ),
            'show_field_keys': UserPreference.get_user_preference_with_default(
                user, UserPreference.SHOW_FIELD_KEYS
            )
        }
    
    @staticmethod
    def update_preference(user, key, value):
        """Update a single preference with validation"""
        if key not in UserPreference.PREFERENCE_DEFAULTS:
            raise ValueError(f"Invalid preference key: {key}")
        
        # Validate preference values
        if key == UserPreference.NAVIGATION_PLACEMENT:
            if value not in ['left', 'right', 'top']:
                raise ValueError("Navigation placement must be 'left', 'right', or 'top'")
        elif key == UserPreference.UI_THEME:
            if value not in ['light', 'dark', 'auto']:
                raise ValueError("UI theme must be 'light', 'dark', or 'auto'")
        elif key == UserPreference.FORM_COMPOSER_LAYOUT:
            if value not in ['horizontal', 'vertical']:
                raise ValueError("Form composer layout must be 'horizontal' or 'vertical'")
        elif key == UserPreference.SIDEBAR_WIDTH:
            if value not in ['small', 'medium', 'large']:
                raise ValueError("Sidebar width must be 'small', 'medium', or 'large'")
        elif key == UserPreference.AUTO_SAVE_INTERVAL:
            if not isinstance(value, int) or value < 1 or value > 60:
                raise ValueError("Auto save interval must be an integer between 1 and 60")
        elif key == UserPreference.SHOW_FIELD_KEYS:
            if not isinstance(value, bool):
                raise ValueError("Show field keys must be a boolean")
        
        return UserPreference.set_user_preference(user, key, value)
    
    @staticmethod
    def ensure_user_preferences(user):
        """Ensure user has all default preferences initialized"""
        UserPreference.initialize_user_defaults(user)
    
    @staticmethod
    def reset_user_preferences(user):
        """Reset all user preferences to defaults"""
        for key, default_value in UserPreference.PREFERENCE_DEFAULTS.items():
            UserPreference.set_user_preference(user, key, default_value)