"""
Admin Form Injection Service

This service dynamically injects custom fields from Configuration Dashboard
into Django admin forms for Core Sections (existing admin models).
"""

from django.contrib import admin
from django.forms import CharField, IntegerField, BooleanField, DateField, ChoiceField
from django.core.exceptions import ValidationError
from django.http import HttpRequest
from typing import Dict, List, Any, Optional
import logging
import json

logger = logging.getLogger(__name__)


class AdminFormInjector:
    """
    Service that injects custom fields from DynamicSection into Django admin forms.
    
    This allows fields added via Configuration Dashboard to appear in admin forms.
    """
    
    # Field type mapping from DynamicField to Django form fields
    FIELD_TYPE_MAPPING = {
        'CharField': CharField,
        'TextField': CharField,
        'IntegerField': IntegerField,
        'BooleanField': BooleanField,
        'DateField': DateField,
        'ChoiceField': ChoiceField,
    }
    
    @classmethod
    def get_custom_fields_for_model(cls, model_class) -> List[Dict[str, Any]]:
        """
        Get custom fields for a given Django model from Configuration Dashboard.
        
        Args:
            model_class: The Django model class
            
        Returns:
            List of custom field configurations
        """
        from requests.models import DynamicSection, DynamicField
        
        try:
            # Find the DynamicSection for this model - use source_model first
            app_label = model_class._meta.app_label
            model_name = model_class._meta.model_name
            model_key = f"{app_label}.{model_name}"
            
            # Primary lookup: by source_model field
            section = DynamicSection.objects.filter(
                source_model__iexact=model_key,
                is_core_section=True
            ).first()
            
            # Fallback lookup: by various name patterns
            if not section:
                section = DynamicSection.objects.filter(
                    name__in=[
                        f"Core: {app_label}",  # "Core: accounts"
                        f"Core: {model_key}",  # "Core: accounts.account"  
                        model_key,             # "accounts.account"
                        app_label              # "accounts"
                    ],
                    is_core_section=True
                ).first()
            
            logger.debug(f"Section lookup for {model_key}: {'Found' if section else 'Not found'} - {section.name if section else 'N/A'}")
            
            if not section:
                logger.debug(f"No DynamicSection found for model: {model_class.__name__}")
                return []
            
            # Get active custom fields (not core fields)
            custom_fields = section.fields.filter(
                is_active=True,
                is_core_field=False  # Only custom fields, not original model fields
            ).order_by('order')
            
            field_configs = []
            for field in custom_fields:
                field_configs.append({
                    'name': field.name,
                    'display_name': field.display_name,
                    'field_type': field.field_type,
                    'required': field.required,
                    'max_length': field.max_length,
                    'choices': field.choices,
                    'default_value': field.default_value,
                    'section_name': field.section_name or 'Custom Fields'
                })
            
            logger.info(f"Found {len(field_configs)} custom fields for {model_class.__name__}")
            return field_configs
            
        except Exception as e:
            logger.error(f"Error getting custom fields for {model_class.__name__}: {e}")
            return []
    
    @classmethod
    def create_form_field(cls, field_config: Dict[str, Any]):
        """
        Create a Django form field from a field configuration.
        
        Args:
            field_config: Dictionary containing field configuration
            
        Returns:
            Django form field instance
        """
        field_type = field_config['field_type']
        field_class = cls.FIELD_TYPE_MAPPING.get(field_type, CharField)
        
        kwargs = {
            'label': field_config['display_name'],
            'required': field_config['required'],
            'initial': field_config.get('default_value', '')
        }
        
        # Add field-specific parameters
        if field_type in ['CharField', 'TextField']:
            kwargs['max_length'] = field_config.get('max_length', 255)
        
        if field_type == 'ChoiceField' and field_config.get('choices'):
            try:
                # Parse choices (assuming JSON format)
                choices_data = json.loads(field_config['choices'])
                if isinstance(choices_data, dict):
                    kwargs['choices'] = list(choices_data.items())
                elif isinstance(choices_data, list):
                    kwargs['choices'] = [(choice, choice) for choice in choices_data]
            except (json.JSONDecodeError, ValueError):
                # Fallback to CharField if choices parsing fails
                field_class = CharField
                kwargs['max_length'] = field_config.get('max_length', 255)
        
        return field_class(**kwargs)
    
    @classmethod
    def inject_custom_fields_into_admin(cls, admin_class):
        """
        Inject custom fields into a Django admin class.
        
        This method modifies the admin class to include custom fields
        from Configuration Dashboard.
        
        Args:
            admin_class: The Django ModelAdmin class to modify
        """
        original_get_form = admin_class.get_form
        original_get_fieldsets = getattr(admin_class, 'get_fieldsets', None)
        
        def enhanced_get_form(self, request: HttpRequest, obj=None, **kwargs):
            """Enhanced get_form that includes custom fields without triggering model validation"""
            
            # Get custom fields for this model
            custom_field_configs = cls.get_custom_fields_for_model(self.model)
            
            if custom_field_configs:
                # Get model-only field names to avoid validation errors
                model_field_names = [
                    f.name for f in self.model._meta.get_fields() 
                    if f.concrete and not f.auto_created and not f.many_to_many
                ]
                
                # Handle kwargs carefully to avoid duplicate 'fields' parameter
                form_kwargs = kwargs.copy()
                form_kwargs['fields'] = model_field_names
                
                # Call original get_form with model fields only
                form_class = original_get_form(self, request, obj, **form_kwargs)
                
                # Create enhanced form that adds custom fields after construction
                class EnhancedForm(form_class):
                    def __init__(self, *args, **kwargs):
                        super().__init__(*args, **kwargs)
                        
                        # Add custom fields to form (these bypass model validation)
                        for field_config in custom_field_configs:
                            field_name = field_config['name']
                            form_field = cls.create_form_field(field_config)
                            self.fields[field_name] = form_field
                
                return EnhancedForm
            
            # No custom fields - use original form
            return original_get_form(self, request, obj, **kwargs)
        
        def enhanced_get_fieldsets(self, request: HttpRequest, obj=None):
            """Enhanced get_fieldsets that includes custom fields section"""
            # Get original fieldsets or create default
            if original_get_fieldsets:
                fieldsets = list(original_get_fieldsets(self, request, obj))
            else:
                # Create default fieldsets from model fields
                fieldsets = [
                    (None, {
                        'fields': [field.name for field in self.model._meta.fields 
                                 if field.name != 'id' and not field.name.endswith('_at')]
                    })
                ]
            
            # Get custom fields for this model
            custom_field_configs = cls.get_custom_fields_for_model(self.model)
            
            if custom_field_configs:
                # Group custom fields by section
                sections = {}
                for field_config in custom_field_configs:
                    section_name = field_config.get('section_name', 'Custom Fields')
                    if section_name not in sections:
                        sections[section_name] = []
                    sections[section_name].append(field_config['name'])
                
                # Add custom field sections to fieldsets
                for section_name, field_names in sections.items():
                    fieldsets.append((
                        section_name,
                        {
                            'fields': field_names,
                            'classes': ['collapse', 'wide'],
                            'description': f'Custom fields managed via Configuration Dashboard'
                        }
                    ))
            
            return fieldsets
        
        # Enhanced save_model to persist custom field values
        original_save_model = getattr(admin_class, 'save_model', None)
        
        def enhanced_save_model(self, request, obj, form, change):
            """Enhanced save_model that persists custom field values"""
            
            # Call original save_model first
            if original_save_model:
                original_save_model(self, request, obj, form, change)
            else:
                obj.save()
            
            # Save custom field values
            custom_field_configs = cls.get_custom_fields_for_model(self.model)
            for field_config in custom_field_configs:
                field_name = field_config['name']
                if field_name in form.cleaned_data:
                    # TODO: Implement DynamicFieldValue storage
                    logger.debug(f"Would save custom field {field_name}: {form.cleaned_data[field_name]}")
        
        # Replace the methods
        admin_class.get_form = enhanced_get_form
        admin_class.get_fieldsets = enhanced_get_fieldsets  
        admin_class.save_model = enhanced_save_model
        
        logger.info(f"Injected custom field support into {admin_class.__name__}")
    
    @classmethod
    def monkey_patch_admin_register(cls):
        """
        Monkey-patch AdminSite.register to inject custom fields AFTER admin registration.
        
        This ensures the injection happens at the right time, after each admin is registered.
        """
        original_register = admin.AdminSite.register
        
        def enhanced_register(self, model_or_iterable, admin_class=None, **options):
            """Enhanced register that applies field injection after registration"""
            
            # Call the original register method
            result = original_register(self, model_or_iterable, admin_class, **options)
            
            # Apply field injection to newly registered models
            if not hasattr(model_or_iterable, '_meta'):
                # Handle iterable of models
                models = model_or_iterable
            else:
                # Handle single model
                models = [model_or_iterable]
            
            for model in models:
                if model in self._registry:
                    registered_admin = self._registry[model]
                    cls.inject_custom_fields_into_admin(registered_admin.__class__)
                    logger.debug(f"Applied field injection to {model.__name__} admin")
            
            return result
        
        # Replace the register method
        admin.AdminSite.register = enhanced_register
        logger.info("Monkey-patched AdminSite.register for custom field injection")
    
    @classmethod
    def patch_existing_admins(cls):
        """
        Apply field injection to already registered admin classes.
        """
        patched_count = 0
        for model, admin_instance in admin.site._registry.items():
            try:
                cls.inject_custom_fields_into_admin(admin_instance.__class__)
                patched_count += 1
                logger.debug(f"Patched existing admin for {model.__name__}")
            except Exception as e:
                logger.error(f"Failed to patch {model.__name__} admin: {e}")
        
        logger.info(f"Patched {patched_count} existing admin classes")


def auto_register_admin_injection():
    """
    Set up admin form injection without database queries during app initialization.
    
    This applies monkey-patch strategy to inject custom fields at the right time.
    """
    try:
        # Apply monkey-patch to capture future admin registrations
        AdminFormInjector.monkey_patch_admin_register()
        
        # Apply injection to any already registered admins
        AdminFormInjector.patch_existing_admins()
        
        logger.info("Successfully set up admin form injection")
        
    except Exception as e:
        logger.error(f"Failed to set up admin injection: {e}")