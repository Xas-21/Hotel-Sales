"""
Field Synchronization Service

This service ensures that field types and choices are always synchronized
between Django models and the Configuration Dashboard, with immediate reflection
of any changes made.
"""

from django.db import models
from django.apps import apps
from django.contrib import admin
from typing import Dict, Any, Optional
import json
import logging

from requests.models import DynamicSection, DynamicField

logger = logging.getLogger(__name__)


class FieldSyncService:
    """Service to keep model fields synchronized with Configuration Dashboard"""
    
    # Field type mapping from Django to DynamicField types
    FIELD_TYPE_MAP = {
        models.CharField: 'char',
        models.TextField: 'text',
        models.EmailField: 'email', 
        models.URLField: 'url',
        models.SlugField: 'slug',
        models.IntegerField: 'integer',
        models.BigIntegerField: 'integer',
        models.SmallIntegerField: 'integer',
        models.PositiveIntegerField: 'integer',
        models.PositiveSmallIntegerField: 'integer',
        models.DecimalField: 'decimal',
        models.FloatField: 'float',
        models.DateField: 'date',
        models.DateTimeField: 'datetime',
        models.TimeField: 'time',
        models.BooleanField: 'boolean',
        models.NullBooleanField: 'boolean',
        models.FileField: 'file',
        models.ImageField: 'image',
        models.ForeignKey: 'foreign_key',
        models.ManyToManyField: 'many_to_many',
        models.OneToOneField: 'foreign_key',
        models.AutoField: 'integer',
        models.BigAutoField: 'integer'
    }
    
    @classmethod
    def sync_model_to_section(cls, model_class) -> Optional[DynamicSection]:
        """
        Synchronize a Django model's fields to its Configuration Dashboard section.
        This ensures the configuration always reflects the exact model structure.
        
        Args:
            model_class: The Django model class to sync
            
        Returns:
            The DynamicSection if found/created, None otherwise
        """
        app_label = model_class._meta.app_label
        model_name = model_class._meta.object_name
        source_model = f"{app_label}.{model_name}"
        
        # Get or create the section
        section, created = DynamicSection.objects.get_or_create(
            source_model=source_model,
            defaults={
                'name': model_name,
                'display_name': model_class._meta.verbose_name or model_name,
                'description': f'Configuration for {model_name} model',
                'is_core_section': True,
                'is_active': True,
                'order': 0
            }
        )
        
        if created:
            logger.info(f"Created new section for {source_model}")
        
        # Sync all fields
        cls.sync_fields_for_section(section, model_class)
        
        return section
    
    @classmethod
    def sync_fields_for_section(cls, section: DynamicSection, model_class) -> None:
        """
        Synchronize all fields from a model to its section.
        
        Args:
            section: The DynamicSection to update
            model_class: The Django model class
        """
        # Track existing field names for cleanup
        existing_field_names = set()
        
        for field in model_class._meta.get_fields():
            # Skip reverse relations and auto-created fields
            if (hasattr(field, 'auto_created') and field.auto_created) or \
               field.one_to_many or (field.many_to_many and not field.concrete):
                continue
            
            existing_field_names.add(field.name)
            
            # Get field configuration
            field_type = cls.get_field_type(field)
            choices = cls.get_field_choices(field, model_class)
            
            # Update or create the DynamicField
            dynamic_field, created = DynamicField.objects.update_or_create(
                section=section,
                name=field.name,
                defaults={
                    'display_name': getattr(field, 'verbose_name', field.name),
                    'field_type': field_type,
                    'required': not field.null if hasattr(field, 'null') else False,
                    'is_core_field': True,
                    'is_active': True,
                    'order': 0,
                    'choices': choices,
                    'max_length': getattr(field, 'max_length', None),
                    'default_value': cls.get_default_value(field)
                }
            )
            
            if created:
                logger.debug(f"Created field {field.name} ({field_type}) for {section.source_model}")
            else:
                logger.debug(f"Updated field {field.name} ({field_type}) for {section.source_model}")
        
        # Deactivate fields that no longer exist in the model
        removed_fields = DynamicField.objects.filter(
            section=section,
            is_core_field=True,
            is_active=True
        ).exclude(name__in=existing_field_names)
        
        if removed_fields.exists():
            removed_count = removed_fields.update(is_active=False)
            logger.info(f"Deactivated {removed_count} removed fields from {section.source_model}")
    
    @classmethod
    def get_field_type(cls, field) -> str:
        """Get the DynamicField type string for a Django model field"""
        field_class = field.__class__
        
        # Special handling for specific field types
        if isinstance(field, models.ForeignKey):
            return 'foreign_key'
        elif isinstance(field, models.ManyToManyField):
            return 'many_to_many'
        elif isinstance(field, models.OneToOneField):
            return 'foreign_key'
        
        # Check if CharField has choices
        if isinstance(field, models.CharField) and hasattr(field, 'choices') and field.choices:
            return 'choice'
        
        # Look up in mapping
        for django_field_class, type_string in cls.FIELD_TYPE_MAP.items():
            if isinstance(field, django_field_class):
                return type_string
        
        # Default to char for unknown types
        return 'char'
    
    @classmethod
    def get_field_choices(cls, field, model_class) -> Dict[str, str]:
        """Extract choices from a field"""
        choices_dict = {}
        
        # Check if field has choices attribute
        if hasattr(field, 'choices') and field.choices:
            for choice_value, choice_label in field.choices:
                choices_dict[str(choice_value)] = str(choice_label)
        
        # Special handling for known choice fields by name
        elif field.name in ['meeting_subject', 'business_potential', 'request_type', 
                           'status', 'rate_type', 'account_type']:
            # Try to get choices from model constants
            constant_names = {
                'meeting_subject': 'MEETING_SUBJECT',
                'business_potential': 'BUSINESS_POTENTIAL', 
                'request_type': 'REQUEST_TYPES',
                'status': 'STATUS_CHOICES',
                'rate_type': 'RATE_TYPE_CHOICES',
                'account_type': 'ACCOUNT_TYPES'
            }
            
            constant_name = constant_names.get(field.name, field.name.upper() + '_CHOICES')
            
            if hasattr(model_class, constant_name):
                choices = getattr(model_class, constant_name)
                for choice_value, choice_label in choices:
                    choices_dict[str(choice_value)] = str(choice_label)
        
        return choices_dict
    
    @classmethod
    def get_default_value(cls, field) -> str:
        """Get the default value for a field"""
        if hasattr(field, 'default') and field.default != models.NOT_PROVIDED:
            default = field.default
            if callable(default):
                try:
                    default = default()
                except:
                    return ''
            if default is True or default is False:
                return str(default).lower()
            return str(default) if default is not None else ''
        return ''
    
    @classmethod
    def ensure_sync_on_startup(cls) -> None:
        """
        Ensure all registered admin models are synchronized on startup.
        This should be called once during Django initialization.
        """
        # Ensure admin autodiscovery has run
        admin.autodiscover()
        
        # Target apps to sync
        target_apps = ['accounts', 'requests', 'agreements', 'sales_calls']
        
        synced_count = 0
        for model, admin_class in admin.site._registry.items():
            if model._meta.app_label in target_apps:
                section = cls.sync_model_to_section(model)
                if section:
                    synced_count += 1
        
        logger.info(f"Synchronized {synced_count} models to Configuration Dashboard")
    
    @classmethod
    def get_field_value_for_instance(cls, instance, field_name: str) -> Any:
        """
        Get the value of a field from a model instance, handling
        both core model fields and dynamic fields.
        
        Args:
            instance: The model instance
            field_name: The name of the field
            
        Returns:
            The field value or None if not found
        """
        # First check if it's a model field
        if hasattr(instance, field_name):
            return getattr(instance, field_name)
        
        # Then check for dynamic field values
        from requests.models import DynamicFieldValue
        
        section = cls.get_section_for_instance(instance)
        if not section:
            return None
        
        try:
            field = DynamicField.objects.get(
                section=section,
                name=field_name,
                is_active=True
            )
            
            value_obj = DynamicFieldValue.objects.filter(
                field=field,
                instance_id=str(instance.pk)
            ).first()
            
            if value_obj:
                return value_obj.get_typed_value()
        except DynamicField.DoesNotExist:
            pass
        
        return None
    
    @classmethod
    def set_field_value_for_instance(cls, instance, field_name: str, value: Any) -> bool:
        """
        Set the value of a field for a model instance, handling
        both core model fields and dynamic fields.
        
        Args:
            instance: The model instance
            field_name: The name of the field
            value: The value to set
            
        Returns:
            True if successful, False otherwise
        """
        # First check if it's a model field
        if hasattr(instance, field_name):
            setattr(instance, field_name, value)
            instance.save(update_fields=[field_name])
            return True
        
        # Then handle as dynamic field
        from requests.models import DynamicFieldValue
        
        section = cls.get_section_for_instance(instance)
        if not section:
            return False
        
        try:
            field = DynamicField.objects.get(
                section=section,
                name=field_name,
                is_active=True
            )
            
            value_obj, created = DynamicFieldValue.objects.update_or_create(
                field=field,
                instance_id=str(instance.pk),
                defaults={
                    'value_text': str(value) if value is not None else '',
                    'value_json': json.dumps(value) if isinstance(value, (dict, list)) else None
                }
            )
            
            return True
        except DynamicField.DoesNotExist:
            logger.warning(f"Field {field_name} not found for {instance.__class__.__name__}")
            return False
    
    @classmethod
    def get_section_for_instance(cls, instance) -> Optional[DynamicSection]:
        """Get the DynamicSection for a model instance"""
        model_class = instance.__class__
        app_label = model_class._meta.app_label
        model_name = model_class._meta.object_name
        source_model = f"{app_label}.{model_name}"
        
        return DynamicSection.objects.filter(
            source_model=source_model,
            is_core_section=True,
            is_active=True
        ).first()