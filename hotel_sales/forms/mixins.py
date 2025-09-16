"""
Form Mixins for Configuration Enforcement

Provides mixins that automatically apply centralized field requirements and
form layouts to Django forms across all modules.
"""

from django import forms
from django.core.exceptions import ValidationError
from requests.services.config_enforcement import ConfigEnforcementService
import logging

logger = logging.getLogger(__name__)


class ConfigEnforcedFormMixin:
    """
    Mixin to enforce centralized configuration on Django forms.
    
    Automatically applies:
    - Field enabled/disabled states
    - Required field flags  
    - Form sections and ordering
    - Server-side validation of requirements
    """
    
    def __init__(self, *args, **kwargs):
        """Initialize form with configuration enforcement"""
        # Extract instance for form type detection
        instance = kwargs.get('instance', None)
        
        # Call parent initialization first
        super().__init__(*args, **kwargs)
        
        # Determine form type
        form_type = self.get_form_type(instance)
        
        # Apply configuration enforcement
        try:
            self.form_sections = ConfigEnforcementService.apply_to_form(
                form=self,
                form_type=form_type,
                instance=instance
            )
            self._config_form_type = form_type
            logger.debug(f"Applied configuration enforcement for {form_type}")
        except Exception as e:
            logger.error(f"Failed to apply configuration enforcement: {e}")
            # Fallback to original form without enforcement
            self.form_sections = []
            self._config_form_type = None
    
    def get_form_type(self, instance=None):
        """
        Get the form type for configuration lookup.
        Override this method in subclasses for custom form type logic.
        """
        if instance:
            return ConfigEnforcementService.map_form_type(instance)
        elif hasattr(self, '_meta') and hasattr(self._meta, 'model'):
            return ConfigEnforcementService.map_form_type(self._meta.model)
        return None
    
    def clean(self):
        """Enhanced validation with configuration enforcement"""
        cleaned_data = super().clean()
        
        # Server-side validation of required fields
        if hasattr(self, '_config_form_type') and self._config_form_type:
            errors = ConfigEnforcementService.validate_required(
                instance=getattr(self, 'instance', None),
                form_type=self._config_form_type,
                data=cleaned_data
            )
            
            if errors:
                for error in errors:
                    self.add_error(None, error)
        
        return cleaned_data
    
    def has_sections(self):
        """Check if form has configured sections"""
        return bool(getattr(self, 'form_sections', []))
    
    def get_sections(self):
        """Get form sections for template rendering"""
        return getattr(self, 'form_sections', [])


class SalesCallForm(ConfigEnforcedFormMixin, forms.ModelForm):
    """Form for Sales Calls with configuration enforcement"""
    
    class Meta:
        from sales_calls.models import SalesCall
        model = SalesCall
        fields = '__all__'
        widgets = {
            'detailed_notes': forms.Textarea(attrs={'rows': 2}),
            'next_steps': forms.Textarea(attrs={'rows': 2}),
            'follow_up_required': forms.CheckboxInput(),
            'follow_up_completed': forms.CheckboxInput(),
        }
    
    def get_form_type(self, instance=None):
        """Always return Sales Call form type"""
        return 'sales_calls.SalesCall'


class AgreementForm(ConfigEnforcedFormMixin, forms.ModelForm):
    """Form for Agreements with configuration enforcement"""
    
    class Meta:
        from agreements.models import Agreement
        model = Agreement
        fields = '__all__'
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 4}),
        }
    
    def get_form_type(self, instance=None):
        """Always return Agreement form type"""
        return 'agreements.Agreement'


class RequestForm(ConfigEnforcedFormMixin, forms.ModelForm):
    """Form for Requests with configuration enforcement"""
    
    class Meta:
        from requests.models import Request
        model = Request
        fields = '__all__'
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 4}),
        }
    
    def get_form_type(self, instance=None):
        """Get form type based on request type"""
        if instance and hasattr(instance, 'request_type'):
            return f"requests.{instance.request_type}"
        # Default to Group Accommodation for new requests
        return "requests.Group Accommodation"


class AccountForm(ConfigEnforcedFormMixin, forms.ModelForm):
    """Form for Accounts with configuration enforcement"""
    
    class Meta:
        from accounts.models import Account
        model = Account
        fields = '__all__'
        widgets = {
            'address': forms.Textarea(attrs={'rows': 2}),
        }
    
    def get_form_type(self, instance=None):
        """Always return Account form type"""
        return 'accounts.Account'