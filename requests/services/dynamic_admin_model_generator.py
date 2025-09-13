"""
DynamicAdminModelGenerator - Service to create Django admin models when new sections 
are created in Configuration Dashboard
"""

from django.contrib import admin
from django.db import models
from django.apps import apps
from requests.models import DynamicSection, DynamicField
from typing import Dict, Any, Optional, Type
import logging

logger = logging.getLogger(__name__)

class DynamicAdminModelGenerator:
    """Generates Django admin models for custom sections created in Configuration Dashboard"""
    
    def __init__(self):
        self.app_name = 'requests'  # Where to register dynamic models
        self.generated_models = {}  # Cache of generated models
    
    def create_admin_model_for_section(self, section: DynamicSection) -> Optional[Dict[str, Any]]:
        """
        Create a Django admin model for a custom section.
        Returns model info or None if already exists/is core section.
        """
        if section.is_core_section:
            return None  # Core sections already have admin models
        
        try:
            # Generate model class name
            model_name = self._generate_model_name(section.name)
            model_key = f"{self.app_name}.{model_name}"
            
            # Check if already exists
            if self._model_exists(model_key):
                logger.info(f"Admin model {model_key} already exists")
                return self._get_existing_model_info(model_key)
            
            # Create dynamic model class
            model_class = self._create_model_class(section, model_name)
            
            # Create admin class
            admin_class = self._create_admin_class(section, model_class, model_name)
            
            # Register with admin
            admin.site.register(model_class, admin_class)
            
            # Cache the generated model
            self.generated_models[model_key] = {
                'model_class': model_class,
                'admin_class': admin_class,
                'section': section
            }
            
            return {
                'success': True,
                'model_name': model_name,
                'model_key': model_key,
                'field_count': section.fields.count(),
                'admin_registered': True
            }
            
        except Exception as e:
            logger.error(f"Failed to create admin model for section {section.name}: {e}")
            return {
                'success': False,
                'error': str(e),
                'section': section.name
            }
    
    def _generate_model_name(self, section_name: str) -> str:
        """Generate a valid Django model class name from section name"""
        # Remove special characters and convert to PascalCase
        cleaned_name = ''.join(char for char in section_name if char.isalnum() or char.isspace())
        words = cleaned_name.split()
        model_name = ''.join(word.capitalize() for word in words if word)
        
        # Ensure it's a valid class name
        if not model_name or not model_name[0].isalpha():
            model_name = f"Custom{model_name}"
        
        # Add Dynamic prefix to avoid conflicts
        return f"Dynamic{model_name}"
    
    def _model_exists(self, model_key: str) -> bool:
        """Check if model is already registered in admin"""
        try:
            app_label, model_name = model_key.split('.', 1)
            model_class = apps.get_model(app_label, model_name)
            return model_class in admin.site._registry
        except (LookupError, ValueError):
            return False
    
    def _get_existing_model_info(self, model_key: str) -> Dict[str, Any]:
        """Get info for existing model"""
        app_label, model_name = model_key.split('.', 1)
        model_class = apps.get_model(app_label, model_name)
        return {
            'success': True,
            'model_name': model_name,
            'model_key': model_key,
            'field_count': len([f for f in model_class._meta.get_fields() if not f.is_relation]),
            'admin_registered': model_class in admin.site._registry,
            'existing': True
        }
    
    def _create_model_class(self, section: DynamicSection, model_name: str) -> Type[models.Model]:
        """Create a Django model class dynamically based on section fields"""
        # Base attributes for the model
        attrs = {
            '__module__': f'{self.app_name}.models',
            '__qualname__': model_name,
        }
        
        # Add fields from section
        section_fields = section.fields.filter(is_active=True).order_by('order')
        
        for field in section_fields:
            django_field = self._create_django_field(field)
            if django_field:
                attrs[field.name] = django_field
        
        # Add metadata fields
        attrs['created_at'] = models.DateTimeField(auto_now_add=True)
        attrs['updated_at'] = models.DateTimeField(auto_now=True)
        
        # Add Meta class
        meta_attrs = {
            'verbose_name': section.display_name,
            'verbose_name_plural': f"{section.display_name}s",
            'ordering': ['-created_at']
        }
        attrs['Meta'] = type('Meta', (), meta_attrs)
        
        # Add __str__ method
        def __str__(self):
            # Use first text field or pk for string representation
            first_field = section_fields.filter(field_type__in=['CharField', 'TextField']).first()
            if first_field:
                return str(getattr(self, first_field.name, f"{section.display_name} #{self.pk}"))
            return f"{section.display_name} #{self.pk}"
        
        attrs['__str__'] = __str__
        
        # Create the model class
        return type(model_name, (models.Model,), attrs)
    
    def _create_django_field(self, dynamic_field: DynamicField) -> Optional[models.Field]:
        """Convert DynamicField to Django model field"""
        field_type_map = {
            'char': models.CharField,
            'text': models.TextField,
            'email': models.EmailField,
            'url': models.URLField,
            'slug': models.SlugField,
            'integer': models.IntegerField,
            'decimal': models.DecimalField,
            'float': models.FloatField,
            'date': models.DateField,
            'datetime': models.DateTimeField,
            'time': models.TimeField,
            'boolean': models.BooleanField,
            'file': models.FileField,
            'image': models.ImageField,
            'json': models.JSONField,
        }
        
        field_class = field_type_map.get(dynamic_field.field_type)
        if not field_class:
            logger.warning(f"Unsupported field type: {dynamic_field.field_type}")
            return None
        
        # Build field kwargs
        kwargs = {
            'verbose_name': dynamic_field.display_name,
            'help_text': dynamic_field.help_text or '',
            'blank': not dynamic_field.required,
            'null': not dynamic_field.required,
        }
        
        # Add type-specific kwargs
        if dynamic_field.field_type in ['char', 'email', 'url', 'slug']:
            kwargs['max_length'] = dynamic_field.max_length or 255
        
        if dynamic_field.field_type == 'decimal':
            kwargs['max_digits'] = dynamic_field.max_digits or 10
            kwargs['decimal_places'] = dynamic_field.decimal_places or 2
        
        if dynamic_field.field_type in ['choice', 'multiple_choice'] and dynamic_field.choices:
            # Handle choices field - for now, use CharField with choices
            choices = []
            if isinstance(dynamic_field.choices, dict):
                choices = [(k, v) for k, v in dynamic_field.choices.items()]
            elif isinstance(dynamic_field.choices, str):
                try:
                    import json
                    choices_dict = json.loads(dynamic_field.choices)
                    choices = [(k, v) for k, v in choices_dict.items()]
                except json.JSONDecodeError:
                    pass
            
            if choices:
                kwargs['choices'] = choices
                if dynamic_field.field_type == 'choice':
                    kwargs['max_length'] = 100
                    field_class = models.CharField
        
        # Add default value if provided
        if dynamic_field.default_value:
            try:
                if dynamic_field.field_type == 'boolean':
                    kwargs['default'] = dynamic_field.default_value.lower() in ['true', '1', 'yes']
                elif dynamic_field.field_type in ['integer', 'float', 'decimal']:
                    kwargs['default'] = float(dynamic_field.default_value)
                else:
                    kwargs['default'] = dynamic_field.default_value
            except (ValueError, TypeError):
                pass  # Skip invalid default values
        
        return field_class(**kwargs)
    
    def _create_admin_class(self, section: DynamicSection, model_class: Type[models.Model], model_name: str):
        """Create Django admin class for the model"""
        
        # Get field names for admin display
        field_names = []
        section_fields = section.fields.filter(is_active=True).order_by('order')
        
        for field in section_fields[:5]:  # Limit to first 5 fields for list_display
            field_names.append(field.name)
        
        # Add metadata fields
        field_names.extend(['created_at', 'updated_at'])
        
        # Create admin class attributes
        admin_attrs = {
            '__module__': f'{self.app_name}.admin',
            'list_display': field_names,
            'list_filter': ['created_at', 'updated_at'],
            'search_fields': [f.name for f in section_fields.filter(field_type__in=['char', 'text', 'email'])[:3]],
            'readonly_fields': ['created_at', 'updated_at'],
            'ordering': ['-created_at'],
        }
        
        # Create fieldsets based on section organization
        fieldsets = []
        
        # Main fields fieldset
        main_fields = [f.name for f in section_fields]
        if main_fields:
            fieldsets.append((
                section.display_name,
                {'fields': main_fields}
            ))
        
        # Metadata fieldset
        fieldsets.append((
            'Metadata',
            {
                'fields': ('created_at', 'updated_at'),
                'classes': ('collapse',)
            }
        ))
        
        admin_attrs['fieldsets'] = fieldsets
        
        # Create admin class
        admin_class_name = f"{model_name}Admin"
        return type(admin_class_name, (admin.ModelAdmin,), admin_attrs)
    
    def create_admin_models_for_all_custom_sections(self) -> Dict[str, Any]:
        """Create admin models for all custom sections"""
        custom_sections = DynamicSection.objects.filter(is_core_section=False)
        results = []
        
        for section in custom_sections:
            result = self.create_admin_model_for_section(section)
            if result:
                results.append(result)
        
        successful = [r for r in results if r.get('success', False)]
        failed = [r for r in results if not r.get('success', False)]
        
        return {
            'success': len(failed) == 0,
            'total_sections': len(results),
            'successful_count': len(successful),
            'failed_count': len(failed),
            'successful': successful,
            'failed': failed
        }