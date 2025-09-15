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
                    
                    # Add enabled fields to section (including dynamic fields)
                    for field_name in section.get('fields', []):
                        if field_name in field_configs and field_configs[field_name]['enabled']:
                            section_fields.append(field_name)
                    
                    # Add dynamic fields that belong to this section but aren't explicitly listed
                    for field_name, config in field_configs.items():
                        if (config.get('is_dynamic', False) and 
                            config.get('enabled', True) and 
                            config.get('section_name', 'General') == section_name and 
                            field_name not in section_fields):
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
                
                # Add any remaining fields that aren't in sections (including dynamic fields)
                model_fields = [f.name for f in self.model._meta.get_fields() 
                              if not f.is_relation or f.one_to_one or (f.many_to_one and f.related_model)]
                
                # Get all configured field names including dynamic ones
                all_configured_fields = [f for f in field_configs.keys() if field_configs[f]['enabled']]
                
                configured_fields = set()
                for section in layout['sections']:
                    configured_fields.update(section.get('fields', []))
                    # Also add dynamic fields that were added to sections
                    for field_name, config in field_configs.items():
                        if (config.get('is_dynamic', False) and 
                            config.get('enabled', True) and 
                            config.get('section_name', 'General') == section.get('name', 'Section')):
                            configured_fields.add(field_name)
                
                # Find remaining fields (both model fields and dynamic fields)
                remaining_fields = []
                for field_name in all_configured_fields:
                    if field_name not in configured_fields:
                        remaining_fields.append(field_name)
                
                if remaining_fields:
                    fieldsets.append(('Dynamic Fields', {
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
        """Apply configuration enforcement to forms using AdminFormInjector"""
        from requests.services.admin_form_injector import AdminFormInjector
        
        # Get the base form class first
        form_class = super().get_form(request, obj, **kwargs)
        
        # Get custom field configurations
        custom_field_configs = AdminFormInjector.get_custom_fields_for_model(self.model)
        
        if not custom_field_configs:
            # No custom fields, return original form
            return form_class
        
        # Create a new form class that includes dynamic field injection
        class ConfigEnforcedForm(form_class):
            def __init__(form_self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                
                # Process each custom field configuration
                for field_config in custom_field_configs:
                    field_name = field_config['name']
                    
                    if field_config.get('is_core_override', False):
                        # Skip ForeignKey and other relation fields - let Django handle them normally
                        model_field = None
                        for field in self.model._meta.get_fields():
                            if field.name == field_name:
                                model_field = field
                                break
                        
                        if model_field and (hasattr(model_field, 'remote_field') and model_field.remote_field):
                            # This is a ForeignKey/ManyToMany/OneToOne field - skip it
                            logger.debug(f"Skipping ForeignKey field {field_name} to preserve dropdown functionality")
                            continue
                        
                        # Override existing model field choices (for non-relation fields only)
                        if field_name in form_self.fields:
                            # Replace the field completely with custom choices
                            new_field = AdminFormInjector.create_form_field(field_config)
                            
                            # Preserve existing field attributes if not overridden
                            existing_field = form_self.fields.get(field_name)
                            if existing_field:
                                if not field_config.get('display_name'):
                                    new_field.label = existing_field.label
                                new_field.help_text = getattr(existing_field, 'help_text', '')
                                new_field.required = field_config.get('required', existing_field.required)
                            
                            # Replace the field
                            form_self.fields[field_name] = new_field
                            
                    elif field_config.get('is_core_create', False):
                        # Add new core field (doesn't exist in model)
                        if field_name not in form_self.fields:  # Avoid conflicts
                            form_field = AdminFormInjector.create_form_field(field_config)
                            form_self.fields[field_name] = form_field
                            
                            # Load initial value for edit forms
                            instance = kwargs.get('instance')
                            if instance and instance.pk:
                                initial_value = AdminFormInjector.get_dynamic_field_value(
                                    instance, field_config.get('dynamic_field_id')
                                )
                                if initial_value is not None:
                                    form_self.initial[field_name] = initial_value
                    
                    else:
                        # Add regular custom field
                        form_field = AdminFormInjector.create_form_field(field_config)
                        form_self.fields[field_name] = form_field
                        
                        # Load existing value for custom fields
                        instance = kwargs.get('instance')
                        if instance and instance.pk:
                            existing_value = AdminFormInjector.get_existing_field_value(
                                instance, field_config['name']
                            )
                            if existing_value is not None:
                                form_self.initial[field_name] = existing_value
        
        return ConfigEnforcedForm
    
    def save_model(self, request, obj, form, change):
        """Save the model and handle dynamic field values"""
        # First save the main model
        super().save_model(request, obj, form, change)
        
        # Then save dynamic field values
        try:
            from requests.services.admin_form_injector import AdminFormInjector
            from requests.models import DynamicFieldValue, DynamicField
            from django.contrib.contenttypes.models import ContentType
            
            custom_field_configs = AdminFormInjector.get_custom_fields_for_model(self.model)
            content_type = ContentType.objects.get_for_model(self.model)
            
            for field_config in custom_field_configs:
                field_name = field_config['name']
                field_type = field_config['field_type']
                storage = field_config.get('storage', 'value_store')
                
                # Skip fields that are stored in model fields (core overrides)
                if storage == 'model_field':
                    continue
                
                # Check both cleaned_data and FILES for file fields
                field_value_data = None
                if field_name in form.cleaned_data:
                    field_value_data = form.cleaned_data[field_name]
                elif field_type in ['file', 'image'] and field_name in request.FILES:
                    field_value_data = request.FILES[field_name]
                
                if field_value_data is not None:
                    # For new core fields, use the dynamic_field_id if available
                    if field_config.get('dynamic_field_id'):
                        dynamic_field = DynamicField.objects.get(
                            id=field_config['dynamic_field_id'], 
                            is_active=True
                        )
                    else:
                        # For regular custom fields, find by name
                        dynamic_field = DynamicField.objects.get(name=field_name, is_active=True)
                    
                    # Update or create the field value
                    field_value, created = DynamicFieldValue.objects.update_or_create(
                        content_type=content_type,
                        object_id=obj.pk,
                        field=dynamic_field,
                        defaults={}
                    )
                    
                    # Handle different field types properly
                    if field_type == 'multiple_choice':
                        # Serialize list data as JSON
                        if isinstance(field_value_data, list):
                            field_value.set_value(field_value_data)
                        else:
                            field_value.set_value([field_value_data] if field_value_data else [])
                    elif field_type in ['file', 'image']:
                        # Handle file uploads
                        field_value.set_value(field_value_data)
                    else:
                        # Standard field types
                        field_value.set_value(field_value_data)
                    
                    field_value.save()
                    logger.debug(f"Saved dynamic field value for {field_name}")
                    
        except Exception as e:
            logger.error(f"Error saving dynamic field values for {obj}: {e}")