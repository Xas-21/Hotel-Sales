"""
Admin Mixins for Configuration Enforcement

Provides mixins that integrate the centralized configuration system
with Django admin interfaces.
"""

from django.contrib import admin
from requests.services.config_enforcement import ConfigEnforcementService
import logging

logger = logging.getLogger(__name__)


class ConfigEnforcedAdminMixin:
    """
    Mixin to apply centralized configuration to Django admin interfaces.
    
    Dynamically generates fieldsets based on SystemFormLayout configurations
    and applies field requirements from SystemFieldRequirement.
    """
    
    def get_fieldsets(self, request, obj=None):
        """Generate dynamic fieldsets from configuration"""
        try:
            # Determine form type for this admin
            form_type = self.get_config_form_type(obj)
            
            # Get layout configuration
            layout = ConfigEnforcementService.get_layout(form_type)
            field_configs = ConfigEnforcementService.get_field_configs(form_type)
            
            if layout and layout.get('sections'):
                # Build fieldsets from configuration
                fieldsets = []
                
                for section in sorted(layout['sections'], key=lambda x: x.get('order', 0)):
                    section_name = section.get('name', 'Section')
                    section_fields = []
                    
                    # Add enabled fields to section
                    for field_name in section.get('fields', []):
                        if field_name in field_configs and field_configs[field_name]['enabled']:
                            section_fields.append(field_name)
                    
                    # Only add section if it has fields
                    if section_fields:
                        options = {}
                        if section.get('collapsed', False):
                            options['classes'] = ('collapse',)
                        
                        fieldsets.append((section_name, {
                            'fields': section_fields,
                            **options
                        }))
                
                # Add any remaining fields that aren't in sections
                model_fields = [f.name for f in self.model._meta.get_fields() 
                              if not f.is_relation or f.one_to_one or (f.many_to_one and f.related_model)]
                configured_fields = set()
                for section in layout['sections']:
                    configured_fields.update(section.get('fields', []))
                
                remaining_fields = [f for f in model_fields 
                                  if f not in configured_fields and f in field_configs 
                                  and field_configs[f]['enabled']]
                
                if remaining_fields:
                    fieldsets.append(('Other Fields', {
                        'fields': remaining_fields,
                        'classes': ('collapse',)
                    }))
                
                # Merge with conditional fieldsets if they exist
                conditional_fieldsets = self.get_conditional_fieldsets(request, obj)
                if conditional_fieldsets:
                    fieldsets.extend(conditional_fieldsets)
                
                return fieldsets
            
            # Fallback to original fieldsets if no configuration
            return self.get_original_fieldsets(request, obj)
            
        except Exception as e:
            logger.error(f"Error generating dynamic fieldsets: {e}")
            # Fallback to original implementation
            return self.get_original_fieldsets(request, obj)
    
    def get_config_form_type(self, obj=None):
        """
        Get the form type for configuration lookup.
        Override in subclasses for custom form type logic.
        """
        return ConfigEnforcementService.map_form_type(self.model)
    
    def get_original_fieldsets(self, request, obj=None):
        """
        Fallback to original fieldsets implementation.
        Override in subclasses to provide original behavior.
        """
        # Default Django admin behavior
        if hasattr(super(), 'get_fieldsets'):
            return super().get_fieldsets(request, obj)
        
        # Simple fallback
        fields = [f.name for f in self.model._meta.get_fields() 
                 if not f.is_relation or f.one_to_one or (f.many_to_one and f.related_model)]
        return [('Fields', {'fields': fields})]
    
    def get_conditional_fieldsets(self, request, obj=None):
        """
        Get additional conditional fieldsets (e.g., for specific statuses).
        Override in subclasses to add conditional logic.
        """
        return []
    
    def get_form(self, request, obj=None, **kwargs):
        """Apply configuration enforcement to forms"""
        form_class = super().get_form(request, obj, **kwargs)
        
        # Create a new form class that includes configuration enforcement
        class ConfigEnforcedForm(form_class):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                
                # Apply configuration enforcement
                form_type = ConfigEnforcementService.map_form_type(self._meta.model)
                ConfigEnforcementService.apply_to_form(self, form_type, kwargs.get('instance'))
        
        return ConfigEnforcedForm