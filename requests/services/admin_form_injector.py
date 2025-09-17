"""
Admin Form Injection Service

This service dynamically injects custom fields from Configuration Dashboard
into Django admin forms for Core Sections (existing admin models).
"""

from django.contrib import admin
from django.forms import (
    CharField, IntegerField, BooleanField, DateField, DateTimeField, 
    ChoiceField, TypedChoiceField, DecimalField, FloatField, FileField, ImageField, TimeField, 
    MultipleChoiceField, EmailField, URLField
)
from django.core.validators import FileExtensionValidator
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
    # Uses lowercase field type names to match DynamicField.FIELD_TYPES
    FIELD_TYPE_MAPPING = {
        # Text fields
        'char': CharField,
        'text': CharField,  # Will use widget=Textarea
        'email': EmailField,
        'url': URLField,
        'slug': CharField,
        
        # Number fields
        'integer': IntegerField,
        'decimal': DecimalField,
        'float': FloatField,
        
        # Date/Time fields
        'date': DateField,
        'DateField': DateField,  # Support both lowercase and capitalized
        'datetime': DateTimeField,
        'time': TimeField,
        
        # Boolean fields
        'boolean': BooleanField,
        
        # Choice fields
        'choice': ChoiceField,
        'ChoiceField': ChoiceField,  # Support both formats
        'CharField': ChoiceField,  # Override for fields with choices
        'multiple_choice': MultipleChoiceField,
        
        # File fields
        'file': FileField,
        'image': ImageField,  # Now uses proper ImageField with Pillow validation
        
        # Advanced fields
        'json': CharField,  # JSON data as text field for now
        'foreign_key': CharField,  # Link to another model (simplified as text)
        'many_to_many': MultipleChoiceField,  # Multiple links (simplified as multiple choice)
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
        
        # For core models, only allow choices overrides (not field type overrides)
        # This preserves configuration dashboard choices while keeping date widgets
        core_models_choices_only = ['Account', 'Agreement', 'SalesCall', 'Request']
        choices_only_mode = model_class.__name__ in core_models_choices_only
        
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
            
            # Get active fields (both custom and core fields with configured choices)
            all_fields = section.fields.filter(
                is_active=True
            ).order_by('order')
            
            # Split into different field types based on new core_mode field
            custom_fields = all_fields.filter(is_core_field=False)
            core_override_fields = all_fields.filter(
                is_core_field=True,
                core_mode='override'
            )
            core_create_fields = all_fields.filter(
                is_core_field=True,
                core_mode='create'
            )
            
            field_configs = []
            
            # Add custom fields (new fields not in Django model)
            for field in custom_fields:
                field_configs.append({
                    'name': field.name,
                    'display_name': field.display_name,
                    'field_type': field.field_type,
                    'required': field.required,
                    'max_length': field.max_length,
                    'choices': field.choices,
                    'default_value': field.default_value,
                    'section_name': field.section_name or 'Custom Fields',
                    'is_core_override': False,
                    'is_core_create': False,
                    'storage': 'value_store'
                })
            
            # Add core fields that override existing model fields
            for field in core_override_fields:
                field_configs.append({
                    'name': field.model_field_name or field.name,  # Use model_field_name for override
                    'display_name': field.display_name,
                    'field_type': field.field_type,
                    'required': field.required,
                    'max_length': field.max_length,
                    'choices': field.choices,
                    'default_value': field.default_value,
                    'section_name': field.section_name or 'Core Fields',
                    'is_core_override': True,
                    'is_core_create': False,
                    'storage': field.storage,
                    'model_field_name': field.model_field_name
                })
            
            # Add new core fields that don't exist in the model
            for field in core_create_fields:
                field_configs.append({
                    'name': field.name,
                    'display_name': field.display_name,
                    'field_type': field.field_type,
                    'required': field.required,
                    'max_length': field.max_length,
                    'choices': field.choices,
                    'default_value': field.default_value,
                    'section_name': field.section_name or 'Core Fields',
                    'is_core_override': False,
                    'is_core_create': True,
                    'storage': 'value_store',  # Always use value_store for new core fields
                    'dynamic_field_id': field.id  # Store the DynamicField ID for loading values
                })
            
            # Filter for choices_only_mode - only return core overrides with choices
            if choices_only_mode:
                original_count = len(field_configs)
                field_configs = [
                    config for config in field_configs 
                    if (config.get('is_core_override', False) and 
                        config.get('choices') and 
                        config['choices'] not in ['{}', '', None])
                ]
                logger.info(f"Choices-only mode for {model_class.__name__}: {original_count} -> {len(field_configs)} fields (choices overrides only)")
            else:
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
            'label': field_config.get('display_name', field_config.get('name', 'Unknown Field')),
            'required': field_config.get('required', False),
            'initial': field_config.get('default_value', '')
        }
        
        # Add field-specific parameters based on field type
        if field_type in ['char', 'text', 'slug']:
            kwargs['max_length'] = field_config.get('max_length', 255)
            
        # Use textarea widget for text fields
        if field_type == 'text':
            from django import forms
            kwargs['widget'] = forms.Textarea(attrs={'rows': 3})
        
        # Use proper admin widgets for date/time fields to ensure calendar pickers
        if field_type in ['date', 'DateField']:
            from django.contrib import admin
            kwargs['widget'] = admin.widgets.AdminDateWidget()
            # Remove max_length for date fields if it exists
            kwargs.pop('max_length', None)
        elif field_type == 'datetime':
            from django.contrib import admin
            kwargs['widget'] = admin.widgets.AdminSplitDateTime()
        elif field_type == 'time':
            from django.contrib import admin
            kwargs['widget'] = admin.widgets.AdminTimeWidget()
        
        # Add decimal-specific parameters
        if field_type == 'decimal':
            kwargs['max_digits'] = field_config.get('max_digits', 10)
            kwargs['decimal_places'] = field_config.get('decimal_places', 2)
        
        # Add file validation for security
        if field_type == 'file':
            kwargs['validators'] = [
                FileExtensionValidator(allowed_extensions=[
                    'pdf', 'doc', 'docx', 'txt', 'csv', 'xls', 'xlsx'
                ])
            ]
        elif field_type == 'image':
            kwargs['validators'] = [
                FileExtensionValidator(allowed_extensions=[
                    'jpg', 'jpeg', 'png', 'gif', 'svg', 'webp'
                ])
            ]
        
        # Add choice field options - check if field has choices regardless of field_type
        # (CharField with choices should become ChoiceField)
        # Exclude boolean fields from choice field conversion to keep them as checkboxes
        if (field_config.get('choices') and field_config['choices'] not in ['{}', '', None]
            and field_type not in ['boolean', 'BooleanField']):
            try:
                # Parse choices - handle both dict and JSON string formats
                if isinstance(field_config['choices'], dict):
                    # Already a dict, use directly
                    choices_data = field_config['choices']
                else:
                    # JSON string, parse it
                    choices_data = json.loads(field_config['choices'])
                formatted_choices = []
                
                if isinstance(choices_data, dict) and choices_data:  # Non-empty dict
                    # Convert dict to tuples: {'key': 'label'} -> [('key', 'label'), ...]
                    formatted_choices = list(choices_data.items())
                elif isinstance(choices_data, list) and choices_data:
                    # Handle list format properly
                    for choice in choices_data:
                        if isinstance(choice, (list, tuple)) and len(choice) >= 2:
                            # Convert ['value', 'label'] to ('value', 'label')
                            formatted_choices.append((choice[0], choice[1]))
                        elif isinstance(choice, str):
                            # Convert 'value' to ('value', 'value')
                            formatted_choices.append((choice, choice))
                        else:
                            # Convert anything else to string tuple
                            formatted_choices.append((str(choice), str(choice)))
                
                # Only set choices if we have valid formatted choices
                if formatted_choices:
                    kwargs['choices'] = formatted_choices
                    
                    # Override field class for choice fields (not multiple_choice)
                    if field_type not in ['multiple_choice']:
                        # Use TypedChoiceField for core field overrides to match Django's behavior
                        if field_config.get('is_core_override', False):
                            field_class = TypedChoiceField
                            # TypedChoiceField needs a coerce function - use str by default
                            kwargs['coerce'] = str
                            kwargs['empty_value'] = ''
                        else:
                            field_class = ChoiceField
                            
            except (json.JSONDecodeError, ValueError):
                # Fallback to CharField if choices parsing fails
                logger.warning(f"Failed to parse choices for {field_config.get('name', 'unknown')}: {field_config.get('choices', '')}")
                if field_type in ['choice', 'multiple_choice', 'ChoiceField']:
                    # If it was supposed to be a choice field, fallback to CharField
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
        
        # SKIP injection for modules where we want standard Django admin behavior
        excluded_models = ['Account', 'Agreement', 'SalesCall', 'Request']
        
        # Check if admin_class has model attribute
        if not hasattr(admin_class, 'model') or not admin_class.model:
            logger.warning(f"Admin class {admin_class.__name__} does not have model attribute - skipping injection")
            return
            
        if admin_class.model.__name__ in excluded_models:
            logger.info(f"Skipping AdminFormInjector for {admin_class.model.__name__} - using standard Django admin")
            return
        original_get_form = admin_class.get_form
        original_get_fieldsets = getattr(admin_class, 'get_fieldsets', None)
        
        def enhanced_get_form(self, request: HttpRequest, obj=None, **kwargs):
            """Enhanced get_form that includes custom fields without triggering model validation"""
            
            # Debug logging
            logger.info(f"Enhanced get_form called for {self.model.__name__}")
            
            # Get custom fields for this model
            custom_field_configs = cls.get_custom_fields_for_model(self.model)
            logger.info(f"Found {len(custom_field_configs)} custom field configs for {self.model.__name__}")
            
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
                
                # Create enhanced form that adds custom fields and overrides core field choices
                class EnhancedForm(form_class):
                    def __init__(self, *args, **kwargs):
                        super().__init__(*args, **kwargs)
                        
                        # Process both custom fields and core field overrides
                        # Do this AFTER parent __init__ to ensure we override any other modifications
                        for field_config in custom_field_configs:
                            field_name = field_config['name']
                            
                            if field_config.get('is_core_override', False):
                                # Override existing model field choices
                                if field_name in self.fields:
                                    # For core fields with custom choices, always replace the field
                                    # to ensure our choices override any model or mixin choices
                                    new_field = cls.create_form_field(field_config)
                                    
                                    # Try to preserve attributes from existing field
                                    existing_field = self.fields.get(field_name)
                                    if existing_field:
                                        # Only preserve these if not explicitly set in config
                                        if not field_config.get('display_name'):
                                            new_field.label = existing_field.label
                                        new_field.help_text = getattr(existing_field, 'help_text', '')
                                        # Use configured required, not model's
                                        new_field.required = field_config.get('required', existing_field.required)
                                    
                                    # Replace the field completely
                                    self.fields[field_name] = new_field
                                    
                                    # Log for debugging
                                    logger.debug(f"Replaced field {field_name} with custom choices")
                            elif field_config.get('is_core_create', False):
                                # Add new core field (stored in DynamicFieldValue)
                                # Check for name collision with existing model fields
                                if field_name in self.fields:
                                    logger.warning(f"Core-create field '{field_name}' conflicts with existing model field. Skipping to prevent override.")
                                    continue
                                    
                                form_field = cls.create_form_field(field_config)
                                self.fields[field_name] = form_field
                                
                                # Load initial value from DynamicFieldValue for edit forms
                                if self.instance and self.instance.pk:
                                    initial_value = cls.get_dynamic_field_value(
                                        self.instance, field_config.get('dynamic_field_id')
                                    )
                                    if initial_value is not None:
                                        # Handle different field types for initial values
                                        if field_config['field_type'] == 'multiple_choice':
                                            if not isinstance(initial_value, list):
                                                initial_value = [initial_value] if initial_value else []
                                        self.initial[field_name] = initial_value
                                
                                logger.debug(f"Added new core field {field_name}")
                            else:
                                # Add new custom field (original logic)
                                form_field = cls.create_form_field(field_config)
                                self.fields[field_name] = form_field
                            
                            # Load existing value for regular custom fields (not core fields)
                            if not field_config.get('is_core_create', False) and self.instance and self.instance.pk:
                                existing_value = cls.get_existing_field_value(
                                    self.instance, field_config['name']
                                )
                                if existing_value is not None:
                                    # Handle different field types for initial values
                                    if field_config['field_type'] == 'multiple_choice':
                                        # Ensure multiple choice initial is a list
                                        if not isinstance(existing_value, list):
                                            existing_value = [existing_value] if existing_value else []
                                    self.initial[field_name] = existing_value
                
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
            """Enhanced save_model that persists custom field values with file/multiple choice support"""
            
            # Call original save_model first
            if original_save_model:
                original_save_model(self, request, obj, form, change)
            else:
                obj.save()
            
            # Save custom field values using existing DynamicFieldValue model
            from requests.models import DynamicFieldValue, DynamicField
            from django.contrib.contenttypes.models import ContentType
            import json
            
            custom_field_configs = cls.get_custom_fields_for_model(self.model)
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
                    try:
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
                        
                        action = "Created" if created else "Updated" 
                        display_value = field_value.get_value()
                        if field_type in ['file', 'image'] and hasattr(display_value, 'name'):
                            display_value = display_value.name  # Show filename for files
                        elif field_type == 'multiple_choice':
                            display_value = f"{len(display_value) if display_value else 0} items"
                        
                        field_category = "core" if field_config.get('is_core_create') else "custom"
                        logger.info(f"{action} {field_category} field value: {field_name} ({field_type}) = {display_value}")
                        
                    except DynamicField.DoesNotExist:
                        logger.warning(f"DynamicField not found for {field_name}")
                    except Exception as e:
                        field_category = "core" if field_config.get('is_core_create') else "custom"
                        logger.error(f"Error saving {field_category} field {field_name}: {e}")
        
        # Replace the methods
        admin_class.get_form = enhanced_get_form
        admin_class.get_fieldsets = enhanced_get_fieldsets  
        admin_class.save_model = enhanced_save_model
        
        logger.info(f"Injected custom field support into {admin_class.__name__}")
    
    @classmethod
    def get_existing_field_value(cls, instance, field_name: str):
        """Get existing value for a custom field from DynamicFieldValue"""
        try:
            from requests.models import DynamicFieldValue, DynamicField
            from django.contrib.contenttypes.models import ContentType
            
            content_type = ContentType.objects.get_for_model(instance.__class__)
            dynamic_field = DynamicField.objects.get(name=field_name, is_active=True)
            
            field_value = DynamicFieldValue.objects.get(
                content_type=content_type,
                object_id=instance.pk,
                field=dynamic_field
            )
            
            return field_value.get_value()
            
        except (DynamicField.DoesNotExist, DynamicFieldValue.DoesNotExist):
            return None
        except Exception as e:
            logger.error(f"Error loading field value for {field_name}: {e}")
            return None
    
    @classmethod
    def get_dynamic_field_value(cls, instance, dynamic_field_id: int):
        """Get existing value for a core field by DynamicField ID from DynamicFieldValue"""
        try:
            from requests.models import DynamicFieldValue, DynamicField
            from django.contrib.contenttypes.models import ContentType
            
            if not dynamic_field_id:
                return None
                
            content_type = ContentType.objects.get_for_model(instance.__class__)
            dynamic_field = DynamicField.objects.get(id=dynamic_field_id, is_active=True)
            
            field_value = DynamicFieldValue.objects.get(
                content_type=content_type,
                object_id=instance.pk,
                field=dynamic_field
            )
            
            return field_value.get_value()
            
        except (DynamicField.DoesNotExist, DynamicFieldValue.DoesNotExist):
            return None
        except Exception as e:
            logger.error(f"Error loading dynamic field value for ID {dynamic_field_id}: {e}")
            return None
    
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