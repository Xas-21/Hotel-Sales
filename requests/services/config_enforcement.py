"""
Configuration Enforcement Service

This service provides centralized enforcement of field requirements and form layouts
across all modules (Sales Calls, Requests, Agreements) based on SystemFieldRequirement
and SystemFormLayout configurations.
"""

from django.core.cache import cache
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class ConfigEnforcementService:
    """Service to enforce centralized configuration on forms"""
    
    CACHE_TIMEOUT = 3600  # 1 hour
    
    @classmethod
    def map_form_type(cls, model_or_instance) -> str:
        """Map a model instance or class to its canonical form_type string"""
        from django.db import models
        import inspect
        
        try:
            # Determine if it's a model class or instance
            if inspect.isclass(model_or_instance) and issubclass(model_or_instance, models.Model):
                # It's a model class
                app_label = model_or_instance._meta.app_label
                model_name = model_or_instance._meta.model_name
            elif hasattr(model_or_instance, '_meta') and hasattr(model_or_instance, '_state'):
                # It's a model instance  
                app_label = model_or_instance._meta.app_label
                model_name = model_or_instance._meta.model_name
                
                # Handle special cases for requests
                if app_label == 'requests' and model_name == 'request':
                    # For requests, we need to determine the specific request type
                    if hasattr(model_or_instance, 'request_type'):
                        request_type = getattr(model_or_instance, 'request_type', 'Group Accommodation')
                        return f"requests.{request_type}"
                    return "requests.Group Accommodation"  # Default
            else:
                # Fallback for non-model objects
                logger.warning(f"Cannot determine form type for {model_or_instance} - not a Django model")
                return str(model_or_instance)
            
            # Standard mapping for other modules
            form_type_map = {
                'sales_calls.salescall': 'sales_calls.SalesCall',
                'agreements.agreement': 'agreements.Agreement',
                'accounts.account': 'accounts.Account',
            }
            
            key = f"{app_label}.{model_name}"
            mapped_type = form_type_map.get(key)
            
            if mapped_type:
                logger.debug(f"Mapped {key} to {mapped_type}")
                return mapped_type
            
            # For unknown mappings, use proper capitalization
            if app_label == 'accounts':
                mapped_type = f"{app_label}.Account"
            elif app_label == 'sales_calls':
                mapped_type = f"{app_label}.SalesCall"
            elif app_label == 'agreements':
                mapped_type = f"{app_label}.Agreement"
            else:
                mapped_type = f"{app_label}.{model_name.title()}"
            
            logger.debug(f"Mapped {key} to {mapped_type}")
            return mapped_type
            
        except (AttributeError, TypeError) as e:
            logger.warning(f"Error mapping form type for {model_or_instance}: {e}")
            return str(model_or_instance)
    
    @classmethod
    def get_field_configs(cls, form_type: str) -> Dict[str, Any]:
        """Get field configurations for a form type (cached)"""
        cache_key = f"field_configs_{form_type.replace(' ', '_').replace('.', '_')}"
        configs = cache.get(cache_key)
        
        if configs is None:
            from requests.models import SystemFieldRequirement, DynamicField
            
            configs = {}
            
            # Get system field requirements (existing field modifications)
            field_requirements = SystemFieldRequirement.objects.filter(
                form_type=form_type,
                enabled=True
            ).order_by('section_name', 'sort_order')
            
            for req in field_requirements:
                configs[req.field_name] = {
                    'required': req.required,
                    'enabled': req.enabled,
                    'field_label': req.field_label,
                    'section_name': req.section_name,
                    'sort_order': req.sort_order,
                    'help_text': req.help_text,
                    'is_dynamic': False,
                }
            
            # Get dynamic fields for existing models
            dynamic_fields = cls._get_dynamic_fields_for_form_type(form_type)
            for field in dynamic_fields:
                configs[field.name] = {
                    'required': field.required,
                    'enabled': field.is_active,
                    'field_label': field.display_name,
                    'section_name': field.section,
                    'sort_order': field.order,
                    'help_text': field.help_text,
                    'is_dynamic': True,
                    'field_type': field.field_type,
                    'dynamic_field': field,  # Store the field object for later use
                }
            
            cache.set(cache_key, configs, cls.CACHE_TIMEOUT)
            logger.debug(f"Cached field configs for {form_type}: {len(configs)} fields")
        
        return configs
    
    @classmethod
    def get_layout(cls, form_type: str) -> Optional[Dict[str, Any]]:
        """Get form layout for a form type (cached)"""
        cache_key = f"form_layout_{form_type.replace(' ', '_').replace('.', '_')}"
        layout = cache.get(cache_key)
        
        if layout is None:
            from requests.models import SystemFormLayout
            
            try:
                form_layout = SystemFormLayout.objects.get(
                    form_type=form_type,
                    active=True
                )
                layout = {
                    'sections': form_layout.get_sections(),
                    'updated_by': form_layout.updated_by,
                }
                cache.set(cache_key, layout, cls.CACHE_TIMEOUT)
                logger.debug(f"Cached layout for {form_type}")
            except SystemFormLayout.DoesNotExist:
                layout = None
                cache.set(cache_key, layout, cls.CACHE_TIMEOUT)
                logger.debug(f"No layout found for {form_type}")
        
        return layout
    
    @classmethod
    def apply_to_form(cls, form, form_type: str = None, instance=None):
        """Apply configuration to a Django form instance"""
        if form_type is None and instance is not None:
            form_type = cls.map_form_type(instance)
        elif form_type is None:
            # Try to infer from form's model
            if hasattr(form, '_meta') and hasattr(form._meta, 'model'):
                form_type = cls.map_form_type(form._meta.model)
            else:
                logger.warning("Cannot determine form_type for configuration enforcement")
                return []
        
        field_configs = cls.get_field_configs(form_type)
        layout = cls.get_layout(form_type)
        
        # Add dynamic fields to the form
        cls._add_dynamic_fields_to_form(form, field_configs)
        
        # Populate form with existing dynamic field values if editing an instance
        if instance and instance.pk:
            cls._populate_dynamic_field_values(form, instance, field_configs)
        
        # Remove disabled fields
        disabled_fields = [name for name, config in field_configs.items() if not config['enabled']]
        for field_name in disabled_fields:
            if field_name in form.fields:
                del form.fields[field_name]
        
        # Apply required flags and help text
        for field_name, config in field_configs.items():
            if field_name in form.fields:
                form.fields[field_name].required = config['required']
                
                # Merge help text
                existing_help = form.fields[field_name].help_text or ""
                config_help = config.get('help_text', "")
                if config_help and config_help not in existing_help:
                    separator = " " if existing_help else ""
                    form.fields[field_name].help_text = f"{existing_help}{separator}{config_help}"
                
                # Add data attributes for section grouping
                widget = form.fields[field_name].widget
                widget.attrs.update({
                    'data-section': config['section_name'],
                    'aria-required': 'true' if config['required'] else 'false',
                })
        
        # Build form sections for template rendering
        form_sections = cls._build_form_sections(form, layout, field_configs)
        
        # Store sections on form for template access
        form.form_sections = form_sections
        
        return form_sections
    
    @classmethod
    def _build_form_sections(cls, form, layout: Optional[Dict], field_configs: Dict) -> List[Dict]:
        """Build structured sections for template rendering"""
        sections = []
        used_fields = set()
        
        if layout and layout.get('sections'):
            # Use configured layout
            for section in sorted(layout['sections'], key=lambda x: x.get('order', 0)):
                section_fields = []
                for field_name in section.get('fields', []):
                    if field_name in form.fields:
                        section_fields.append(form[field_name])
                        used_fields.add(field_name)
                
                if section_fields:  # Only add sections with fields
                    sections.append({
                        'name': section.get('name', 'Section'),
                        'fields': section_fields,
                        'collapsed': section.get('collapsed', False),
                        'order': section.get('order', 0),
                    })
        
        # Add any remaining fields to a "Other" section
        remaining_fields = []
        for field_name, field in form.fields.items():
            if field_name not in used_fields:
                remaining_fields.append(form[field_name])
        
        if remaining_fields:
            sections.append({
                'name': 'Other Fields',
                'fields': remaining_fields,
                'collapsed': False,
                'order': 999,
            })
        
        return sections
    
    @classmethod
    def _get_dynamic_fields_for_form_type(cls, form_type: str):
        """Get dynamic fields that are configured for existing models"""
        from .existing_model_bridge import ExistingModelBridge
        
        try:
            return ExistingModelBridge.get_dynamic_fields_for_model(form_type)
        except Exception as e:
            logger.warning(f"Error getting dynamic fields for {form_type}: {e}")
            return []
    
    @classmethod
    def _add_dynamic_fields_to_form(cls, form, field_configs):
        """Add dynamic fields to the form based on configuration"""
        from django import forms
        
        for field_name, config in field_configs.items():
            if config.get('is_dynamic') and config.get('enabled'):
                dynamic_field = config.get('dynamic_field')
                if dynamic_field:
                    # Create Django form field based on dynamic field type
                    django_field = cls._create_django_form_field(dynamic_field)
                    if django_field:
                        form.fields[field_name] = django_field
                        logger.debug(f"Added dynamic field {field_name} to form")
    
    @classmethod
    def _create_django_form_field(cls, dynamic_field):
        """Create a Django form field from a DynamicField configuration"""
        from django import forms
        
        field_type = dynamic_field.field_type
        kwargs = {
            'label': dynamic_field.display_name,
            'required': dynamic_field.required,
            'help_text': dynamic_field.help_text,
        }
        
        try:
            if field_type == 'char':
                kwargs['max_length'] = dynamic_field.max_length or 255
                return forms.CharField(**kwargs)
            elif field_type == 'text':
                return forms.CharField(widget=forms.Textarea, **kwargs)
            elif field_type == 'email':
                kwargs['max_length'] = dynamic_field.max_length or 255
                return forms.EmailField(**kwargs)
            elif field_type == 'url':
                kwargs['max_length'] = dynamic_field.max_length or 255
                return forms.URLField(**kwargs)
            elif field_type == 'integer':
                return forms.IntegerField(**kwargs)
            elif field_type == 'decimal':
                kwargs['max_digits'] = dynamic_field.max_digits or 10
                kwargs['decimal_places'] = dynamic_field.decimal_places or 2
                return forms.DecimalField(**kwargs)
            elif field_type == 'float':
                return forms.FloatField(**kwargs)
            elif field_type == 'date':
                return forms.DateField(**kwargs)
            elif field_type == 'datetime':
                return forms.DateTimeField(**kwargs)
            elif field_type == 'time':
                return forms.TimeField(**kwargs)
            elif field_type == 'boolean':
                return forms.BooleanField(**kwargs)
            elif field_type == 'choice':
                choices = list(dynamic_field.choices.items()) if dynamic_field.choices else []
                return forms.ChoiceField(choices=choices, **kwargs)
            elif field_type == 'multiple_choice':
                choices = list(dynamic_field.choices.items()) if dynamic_field.choices else []
                return forms.MultipleChoiceField(choices=choices, **kwargs)
            elif field_type == 'file':
                return forms.FileField(**kwargs)
            elif field_type == 'image':
                return forms.ImageField(**kwargs)
            else:
                logger.warning(f"Unsupported dynamic field type: {field_type}")
                return forms.CharField(**kwargs)  # Fallback to text field
        except Exception as e:
            logger.error(f"Error creating form field for {dynamic_field.name}: {e}")
            return None
    
    @classmethod
    def validate_required(cls, instance, form_type: str = None, data: Dict = None) -> List[str]:
        """Server-side validation of required fields"""
        if form_type is None:
            form_type = cls.map_form_type(instance)
        
        field_configs = cls.get_field_configs(form_type)
        errors = []
        
        for field_name, config in field_configs.items():
            if config['required'] and config['enabled']:
                value = data.get(field_name) if data else getattr(instance, field_name, None)
                if not value:  # Empty string, None, empty list, etc.
                    errors.append(f"{config['field_label']} is required")
        
        return errors
    
    @classmethod
    def _populate_dynamic_field_values(cls, form, instance, field_configs):
        """Populate form fields with existing dynamic field values"""
        from requests.models import DynamicFieldValue
        
        try:
            # Get existing dynamic field values for this instance
            existing_values = DynamicFieldValue.get_values_for_instance(instance)
            
            for value_obj in existing_values:
                field_name = value_obj.field.name
                if field_name in form.fields and field_configs.get(field_name, {}).get('is_dynamic', False):
                    # Set the initial value for the form field
                    form.initial[field_name] = value_obj.get_value()
                    logger.debug(f"Populated dynamic field '{field_name}' with value: {value_obj.get_value()}")
                    
        except Exception as e:
            logger.error(f"Error populating dynamic field values: {e}")
    
    @classmethod
    def save_dynamic_field_values(cls, form, instance, form_type: str = None):
        """Save dynamic field values after form submission"""
        from requests.models import DynamicFieldValue
        from django.contrib.contenttypes.models import ContentType
        
        if form_type is None:
            form_type = cls.map_form_type(instance)
        
        field_configs = cls.get_field_configs(form_type)
        content_type = ContentType.objects.get_for_model(instance)
        
        try:
            for field_name, config in field_configs.items():
                if config.get('is_dynamic', False) and field_name in form.cleaned_data:
                    dynamic_field = config.get('dynamic_field')
                    if dynamic_field:
                        value = form.cleaned_data[field_name]
                        
                        # Get or create the value object
                        value_obj, created = DynamicFieldValue.objects.get_or_create(
                            content_type=content_type,
                            object_id=instance.pk,
                            field=dynamic_field,
                            defaults={}
                        )
                        
                        # Set the value using the dynamic field value's set_value method
                        value_obj.set_value(value)
                        value_obj.save()
                        
                        action = "Created" if created else "Updated"
                        logger.debug(f"{action} dynamic field value '{field_name}': {value}")
                        
        except Exception as e:
            logger.error(f"Error saving dynamic field values: {e}")
    
    @classmethod
    def get_dynamic_field_values_dict(cls, instance, form_type: str = None):
        """Get dynamic field values as a dictionary for easy access"""
        from requests.models import DynamicFieldValue
        
        if not instance or not instance.pk:
            return {}
        
        try:
            existing_values = DynamicFieldValue.get_values_for_instance(instance)
            return {
                value_obj.field.name: value_obj.get_value()
                for value_obj in existing_values
            }
        except Exception as e:
            logger.error(f"Error getting dynamic field values: {e}")
            return {}
    
    @classmethod
    def invalidate_cache(cls, form_type: str):
        """Invalidate cache for a specific form type"""
        clean_form_type = form_type.replace(' ', '_').replace('.', '_')
        cache.delete(f"field_configs_{clean_form_type}")
        cache.delete(f"form_layout_{clean_form_type}")
        logger.info(f"Invalidated cache for {form_type}")


# Signal handlers to invalidate cache when configuration changes
@receiver([post_save, post_delete])
def invalidate_config_cache(sender, instance, **kwargs):
    """Invalidate cache when configuration changes"""
    from requests.models import SystemFieldRequirement, SystemFormLayout, DynamicField, DynamicModel
    
    if isinstance(instance, SystemFieldRequirement):
        ConfigEnforcementService.invalidate_cache(instance.form_type)
    elif isinstance(instance, SystemFormLayout):
        ConfigEnforcementService.invalidate_cache(instance.form_type)
    elif isinstance(instance, (DynamicField, DynamicModel)):
        # Invalidate cache for all relevant form types when dynamic fields change
        form_types = [
            'requests.Group Accommodation',
            'requests.Individual Accommodation', 
            'requests.Event with Rooms',
            'requests.Event without Rooms',
            'requests.Series Group',
            'sales_calls.SalesCall',
            'agreements.Agreement',
            'accounts.Account',
        ]
        for form_type in form_types:
            ConfigEnforcementService.invalidate_cache(form_type)