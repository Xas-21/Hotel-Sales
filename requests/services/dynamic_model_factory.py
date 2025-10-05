"""
Dynamic Model Factory Service

This service creates actual Django model classes at runtime based on
DynamicModel and DynamicField configurations.
"""

from django.db import models
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from requests.services.schema_manager import SchemaManager
from typing import Dict, Any, Type, Optional
import logging

logger = logging.getLogger(__name__)


class DynamicModelFactory:
    """Factory for creating Django models at runtime"""
    
    _created_models = {}  # Cache of created model classes
    
    @classmethod
    def create_model_class(cls, dynamic_model) -> Optional[Type[models.Model]]:
        """
        Create a Django model class from a DynamicModel configuration.
        
        Args:
            dynamic_model: DynamicModel instance
            
        Returns:
            Django model class or None if creation fails
        """
        model_name = dynamic_model.name
        cache_key = f"{dynamic_model.app_label}.{model_name}"
        
        # Return cached model if already created
        if cache_key in cls._created_models:
            return cls._created_models[cache_key]
        
        try:
            # Build model attributes dictionary
            attrs = {
                '__module__': f"{dynamic_model.app_label}.models",
                '__qualname__': model_name,
                'Meta': type('Meta', (), {
                    'verbose_name': dynamic_model.display_name,
                    'verbose_name_plural': f"{dynamic_model.display_name}s",
                    'db_table': dynamic_model.table_name,
                }),
            }
            
            # Add fields from DynamicField configurations
            for field_config in dynamic_model.fields.filter(is_active=True):
                field_instance = cls._create_django_field(field_config)
                if field_instance:
                    attrs[field_config.name] = field_instance
            
            # Add standard fields
            attrs['created_at'] = models.DateTimeField(auto_now_add=True)
            attrs['updated_at'] = models.DateTimeField(auto_now=True)
            
            # Create the model class
            model_class = type(model_name, (models.Model,), attrs)
            
            # Cache the created model
            cls._created_models[cache_key] = model_class
            
            logger.info(f"Created dynamic model class: {cache_key}")
            return model_class
            
        except Exception as e:
            logger.error(f"Failed to create model class {model_name}: {e}")
            return None
    
    @classmethod
    def _create_django_field(cls, field_config) -> Optional[models.Field]:
        """
        Create a Django field instance from a DynamicField configuration.
        
        Args:
            field_config: DynamicField instance
            
        Returns:
            Django field instance or None if creation fails
        """
        field_type = field_config.field_type
        kwargs = {
            'verbose_name': field_config.display_name,
            'help_text': field_config.help_text,
            'null': not field_config.required,
            'blank': not field_config.required,
        }
        
        # Add default value if specified
        if field_config.default_value:
            try:
                import json
                kwargs['default'] = json.loads(str(field_config.default_value))
            except (json.JSONDecodeError, TypeError):
                kwargs['default'] = str(field_config.default_value)
        
        try:
            # Create field based on type
            if field_type == 'char':
                return models.CharField(
                    max_length=field_config.max_length or 255,
                    **kwargs
                )
            
            elif field_type == 'text':
                return models.TextField(**kwargs)
            
            elif field_type == 'email':
                return models.EmailField(
                    max_length=field_config.max_length or 254,
                    **kwargs
                )
            
            elif field_type == 'url':
                return models.URLField(
                    max_length=field_config.max_length or 200,
                    **kwargs
                )
            
            elif field_type == 'slug':
                return models.SlugField(
                    max_length=field_config.max_length or 50,
                    **kwargs
                )
            
            elif field_type == 'integer':
                return models.IntegerField(**kwargs)
            
            elif field_type == 'decimal':
                return models.DecimalField(
                    max_digits=field_config.max_digits or 10,
                    decimal_places=field_config.decimal_places or 2,
                    **kwargs
                )
            
            elif field_type == 'float':
                return models.FloatField(**kwargs)
            
            elif field_type == 'date':
                return models.DateField(**kwargs)
            
            elif field_type == 'datetime':
                return models.DateTimeField(**kwargs)
            
            elif field_type == 'time':
                return models.TimeField(**kwargs)
            
            elif field_type == 'boolean':
                # For boolean fields, don't require them even if marked required
                # (checkboxes are inherently optional)
                kwargs['null'] = False
                kwargs['blank'] = True
                return models.BooleanField(**kwargs)
            
            elif field_type == 'choice':
                if field_config.choices and isinstance(field_config.choices, dict):
                    choices = [(k, v) for k, v in field_config.choices.items()]
                    kwargs['choices'] = choices
                return models.CharField(
                    max_length=field_config.max_length or 100,
                    **kwargs
                )
            
            elif field_type == 'multiple_choice':
                # Store as JSON for multiple selections
                return models.JSONField(**kwargs)
            
            elif field_type == 'file':
                kwargs.pop('blank', None)  # FileField handles blank differently
                return models.FileField(upload_to='dynamic_files/', **kwargs)
            
            elif field_type == 'image':
                kwargs.pop('blank', None)  # ImageField handles blank differently
                return models.ImageField(upload_to='dynamic_images/', **kwargs)
            
            elif field_type == 'foreign_key':
                if field_config.related_model:
                    try:
                        # Parse related model (e.g., "accounts.Account")
                        app_label, model_name = field_config.related_model.split('.')
                        related_model = apps.get_model(app_label, model_name)
                        
                        return models.ForeignKey(
                            related_model,
                            on_delete=models.SET_NULL,
                            **kwargs
                        )
                    except (ValueError, LookupError) as e:
                        logger.error(f"Invalid related model {field_config.related_model}: {e}")
                        return None
            
            elif field_type == 'many_to_many':
                if field_config.related_model:
                    try:
                        app_label, model_name = field_config.related_model.split('.')
                        related_model = apps.get_model(app_label, model_name)
                        
                        kwargs.pop('null', None)  # M2M doesn't use null
                        return models.ManyToManyField(related_model, **kwargs)
                    except (ValueError, LookupError) as e:
                        logger.error(f"Invalid related model {field_config.related_model}: {e}")
                        return None
            
            elif field_type == 'json':
                return models.JSONField(**kwargs)
            
            else:
                logger.warning(f"Unknown field type: {field_type}")
                return models.TextField(**kwargs)  # Fallback to text field
                
        except Exception as e:
            logger.error(f"Failed to create field {field_config.name}: {e}")
            return None
    
    @classmethod
    def register_model_with_admin(cls, model_class, dynamic_model):
        """
        Register a dynamic model with Django admin.
        
        Args:
            model_class: Django model class
            dynamic_model: DynamicModel instance
        """
        try:
            from django.contrib import admin
            
            # Create admin class for the dynamic model
            admin_class = type(
                f"{model_class.__name__}Admin",
                (admin.ModelAdmin,),
                {
                    'list_display': cls._get_admin_list_display(dynamic_model),
                    'list_filter': cls._get_admin_list_filter(dynamic_model),
                    'search_fields': cls._get_admin_search_fields(dynamic_model),
                    'fieldsets': cls._get_admin_fieldsets(dynamic_model),
                    'ordering': ['-created_at'],
                }
            )
            
            # Register with admin
            admin.site.register(model_class, admin_class)
            logger.info(f"Registered {model_class.__name__} with admin")
            
        except Exception as e:
            logger.error(f"Failed to register {model_class.__name__} with admin: {e}")
    
    @classmethod
    def _get_admin_list_display(cls, dynamic_model) -> list:
        """Get list_display fields for admin"""
        fields = ['id']
        
        # Add first few fields
        for field in dynamic_model.fields.filter(is_active=True).order_by('section', 'order')[:4]:
            if field.field_type not in ['text', 'file', 'image', 'json']:  # Exclude long fields
                fields.append(field.name)
        
        fields.extend(['created_at', 'updated_at'])
        return fields
    
    @classmethod
    def _get_admin_list_filter(cls, dynamic_model) -> list:
        """Get list_filter fields for admin"""
        filters = []
        
        # Add filterable fields
        for field in dynamic_model.fields.filter(is_active=True):
            if field.field_type in ['boolean', 'choice', 'date', 'datetime', 'foreign_key']:
                filters.append(field.name)
        
        filters.extend(['created_at', 'updated_at'])
        return filters[:5]  # Limit to 5 filters
    
    @classmethod
    def _get_admin_search_fields(cls, dynamic_model) -> list:
        """Get search_fields for admin"""
        fields = []
        
        # Add searchable fields
        for field in dynamic_model.fields.filter(is_active=True):
            if field.field_type in ['char', 'text', 'email', 'url']:
                fields.append(field.name)
        
        return fields[:3]  # Limit to 3 search fields
    
    @classmethod
    def _get_admin_fieldsets(cls, dynamic_model) -> tuple:
        """Get fieldsets for admin"""
        fieldsets = []
        
        # Group fields by section
        sections = {}
        for field in dynamic_model.fields.filter(is_active=True).order_by('section', 'order'):
            section_name = field.section or 'General'
            if section_name not in sections:
                sections[section_name] = []
            sections[section_name].append(field.name)
        
        # Build fieldsets
        for section_name, field_names in sections.items():
            fieldsets.append((section_name, {
                'fields': field_names
            }))
        
        # Add metadata section
        fieldsets.append(('Metadata', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse']
        }))
        
        return tuple(fieldsets)
    
    @classmethod
    def create_and_register_model(cls, dynamic_model):
        """
        Complete workflow: create model class, create database table, and register with admin.
        
        Args:
            dynamic_model: DynamicModel instance
        """
        try:
            # Create the Django model class
            model_class = cls.create_model_class(dynamic_model)
            if not model_class:
                return False
            
            # Create database table
            table_created = SchemaManager.create_dynamic_model_table({
                'table_name': dynamic_model.table_name,
                'name': dynamic_model.name,
                'app_label': dynamic_model.app_label,
            })
            
            if table_created:
                # Add fields to database
                for field_config in dynamic_model.fields.filter(is_active=True):
                    field_data = {
                        'name': field_config.name,
                        'field_type': field_config.field_type,
                        'required': field_config.required,
                        'default_value': field_config.default_value,
                        'max_length': field_config.max_length,
                        'max_digits': field_config.max_digits,
                        'decimal_places': field_config.decimal_places,
                    }
                    
                    SchemaManager.add_dynamic_field(dynamic_model.table_name, field_data)
                
                # Register with admin
                cls.register_model_with_admin(model_class, dynamic_model)
                
                # Create ContentType entry
                content_type, created = ContentType.objects.get_or_create(
                    app_label=dynamic_model.app_label,
                    model=dynamic_model.name.lower(),
                    defaults={'model': dynamic_model.name.lower()}
                )
                dynamic_model.content_type = content_type
                dynamic_model.save()
                
                logger.info(f"Successfully created and registered model: {dynamic_model.name}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to create and register model {dynamic_model.name}: {e}")
            return False
    
    @classmethod
    def clear_cache(cls):
        """Clear the model cache"""
        cls._created_models.clear()
        logger.info("Cleared dynamic model cache")