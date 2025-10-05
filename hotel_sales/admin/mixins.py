"""
Admin Mixins for Configuration Enforcement

Provides mixins that integrate the centralized configuration system
with Django admin interfaces.
"""

from django.contrib import admin
from django import forms
from django.forms import widgets
from requests.services.config_enforcement import ConfigEnforcementService
import logging

logger = logging.getLogger(__name__)


class ConfigEnforcedAdminMixin:
    """
    Mixin to apply centralized configuration to Django admin interfaces.
    
    Dynamically generates fieldsets based on SystemFormLayout configurations
    and applies field requirements from SystemFieldRequirement.
    """
    
    @property
    def media(self):
        """
        Ensure date/time widgets JavaScript is always included with proper dependencies
        """
        from django.forms import Media
        # Include core.js first (defines quickElement), then DateTimeShortcuts.js
        extra = Media(js=['admin/js/core.js', 'admin/js/admin/DateTimeShortcuts.js'])
        base_media = super().media if hasattr(super(), 'media') else Media()
        return base_media + extra
    
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """Override to apply correct widget based on DynamicField configuration"""
        # First get the default form field from parent
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        
        # Then check if we have a configuration for this field that should override
        try:
            from requests.models import DynamicSection, DynamicField
            from django.forms import DateField, TimeField, DateTimeField, IntegerField, DecimalField, EmailField, URLField
            
            # Try to get the field configuration
            model_name = self.model.__name__
            app_label = self.model._meta.app_label
            source_model = f"{app_label}.{model_name}"
            
            # Try to find the section for this model
            section = DynamicSection.objects.filter(
                source_model=source_model, 
                is_core_section=True
            ).first()
            
            if section:
                # Check if we have a field configuration
                field_config = DynamicField.objects.filter(
                    section=section,
                    name=db_field.name
                ).first()
                
                if field_config:
                    # Log for debugging
                    logger.info(f"Applying widget for {db_field.name}: {field_config.field_type}")
                    
                    # Apply widget based on field_type configuration
                    # Only override if configuration specifies a different type
                    if field_config.field_type in ['date', 'DateField']:
                        # Return a DateField with the admin widget
                        return DateField(
                            widget=admin.widgets.AdminDateWidget,
                            required=field_config.required if hasattr(field_config, 'required') else True,
                            label=formfield.label if formfield else db_field.verbose_name,
                            help_text=formfield.help_text if formfield else db_field.help_text
                        )
                    elif field_config.field_type == 'TimeField':
                        return TimeField(
                            widget=admin.widgets.AdminTimeWidget,
                            required=field_config.required if hasattr(field_config, 'required') else True,
                            label=formfield.label if formfield else db_field.verbose_name,
                            help_text=formfield.help_text if formfield else db_field.help_text
                        )
                    elif field_config.field_type == 'DateTimeField':
                        return DateTimeField(
                            widget=admin.widgets.AdminSplitDateTime,
                            required=field_config.required if hasattr(field_config, 'required') else True,
                            label=formfield.label if formfield else db_field.verbose_name,
                            help_text=formfield.help_text if formfield else db_field.help_text
                        )
                    elif field_config.field_type == 'TextField' and formfield:
                        # For TextField, just update the widget
                        formfield.widget = forms.Textarea(attrs={'rows': 3, 'cols': 60})
                        if hasattr(field_config, 'required'):
                            formfield.required = field_config.required
                        return formfield
                    elif field_config.field_type == 'IntegerField':
                        return IntegerField(
                            required=field_config.required if hasattr(field_config, 'required') else True,
                            label=formfield.label if formfield else db_field.verbose_name,
                            help_text=formfield.help_text if formfield else db_field.help_text
                        )
                    elif field_config.field_type == 'DecimalField':
                        return DecimalField(
                            required=field_config.required if hasattr(field_config, 'required') else True,
                            label=formfield.label if formfield else db_field.verbose_name,
                            help_text=formfield.help_text if formfield else db_field.help_text
                        )
                    elif field_config.field_type == 'EmailField':
                        return EmailField(
                            required=field_config.required if hasattr(field_config, 'required') else True,
                            label=formfield.label if formfield else db_field.verbose_name,
                            help_text=formfield.help_text if formfield else db_field.help_text
                        )
                    elif field_config.field_type == 'URLField':
                        return URLField(
                            required=field_config.required if hasattr(field_config, 'required') else True,
                            label=formfield.label if formfield else db_field.verbose_name,
                            help_text=formfield.help_text if formfield else db_field.help_text
                        )
                    
                    # For other fields, update the required setting if needed
                    if formfield and hasattr(field_config, 'required'):
                        formfield.required = field_config.required
        except Exception as e:
            logger.error(f"Error applying field configuration for {db_field.name}: {e}")
        
        # Return the formfield (either modified or original)
        return formfield
    
    def get_fieldsets(self, request, obj=None):
        """Generate dynamic fieldsets from configuration - with fallback to original fieldsets"""
        try:
            # Determine form type for this admin
            form_type = self.get_config_form_type(obj)
            
            # Get layout configuration
            layout = ConfigEnforcementService.get_layout(form_type)
            field_configs = ConfigEnforcementService.get_field_configs(form_type)
            
            # PRIORITIZE original fieldsets over dynamic configuration
            # Only use dynamic config if layout exists AND is explicitly enabled
            if layout and layout.get('sections') and layout.get('active', True):
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
            
            # Fallback to original fieldsets if no active configuration
            logger.debug(f"No active dynamic layout found for {form_type}, using original fieldsets")
            return self.get_original_fieldsets(request, obj)
            
        except Exception as e:
            logger.error(f"Error generating dynamic fieldsets: {e}")
            # Always fallback to original implementation for reliability
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
                            # This is a ForeignKey/ManyToMany/OneToOne field - skip it to preserve dropdown functionality
                            logger.debug(f"Skipping ForeignKey field {field_name} to preserve dropdown functionality")
                            continue
                        
                        # Override existing model field choices (for non-relation fields only)
                        if field_name in form_self.fields:
                            existing_field = form_self.fields[field_name]
                            
                            # Get dynamic choices from configuration
                            if field_config.get('choices'):
                                # Parse choices (handle both dict and JSON string formats)
                                if isinstance(field_config['choices'], dict):
                                    dynamic_choices = list(field_config['choices'].items())
                                else:
                                    try:
                                        import json
                                        choices_data = json.loads(field_config['choices'])
                                        dynamic_choices = list(choices_data.items()) if isinstance(choices_data, dict) else []
                                    except (json.JSONDecodeError, ValueError):
                                        dynamic_choices = []
                                
                                if dynamic_choices:
                                    # If current value exists, preserve it in choices
                                    if form_self.instance and hasattr(form_self.instance, field_name):
                                        current_value = getattr(form_self.instance, field_name)
                                        if current_value:
                                            valid_choices = [str(choice[0]) for choice in dynamic_choices]
                                            # If current value not in new choices, add it to preserve data integrity
                                            if str(current_value) not in valid_choices:
                                                dynamic_choices = list(dynamic_choices) + [(current_value, current_value)]
                                    
                                    # Replace field with ChoiceField to ensure proper dropdown rendering
                                    from django.forms import TypedChoiceField
                                    form_self.fields[field_name] = TypedChoiceField(
                                        choices=dynamic_choices,
                                        required=existing_field.required,
                                        label=existing_field.label,
                                        initial=existing_field.initial,
                                        help_text=existing_field.help_text,
                                        coerce=str,
                                        empty_value='',
                                    )
                                    
                                    logger.debug(f"Replaced {field_name} with ChoiceField containing {len(dynamic_choices)} choices")
                            
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
        
        # SKIP dynamic field processing for excluded models (but allow SalesCall for configuration)
        excluded_models = ['Account', 'Agreement', 'Request', 'AccommodationRequest', 'EventOnlyRequest', 'EventWithRoomsRequest', 'SeriesGroupRequest']
        if self.model.__name__ in excluded_models:
            logger.debug(f"Skipping dynamic field processing for excluded model: {self.model.__name__}")
            return
        
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