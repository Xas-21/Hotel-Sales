"""
Existing Model Bridge Service

This service provides a bridge between the DynamicField system and existing models
(Request, Agreement, SalesCall, Account) to allow dynamic fields to be added
to these models without creating new tables.
"""

from django.db import models
from django.apps import apps
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class ExistingModelBridge:
    """Service to bridge dynamic fields with existing models"""
    
    # Map form types to their actual Django models
    FORM_TYPE_TO_MODEL_MAP = {
        # Generic model mappings (from ConfigEnforcementService.map_form_type)
        'requests.Request': ('requests', 'Request'),
        'sales_calls.SalesCall': ('sales_calls', 'SalesCall'), 
        'agreements.Agreement': ('agreements', 'Agreement'),
        'accounts.Account': ('accounts', 'Account'),
        
        # Specific form type mappings (legacy support)
        'requests.Group Accommodation': ('requests', 'Request'),
        'requests.Individual Accommodation': ('requests', 'Request'),
        'requests.Event with Rooms': ('requests', 'Request'),
        'requests.Event without Rooms': ('requests', 'Request'),
        'requests.Series Group': ('requests', 'Request'),
    }
    
    @classmethod
    def get_dynamic_fields_for_model(cls, form_type: str) -> List:
        """Get dynamic fields that are configured for a specific form type"""
        from requests.models import DynamicField, DynamicModel
        
        # Get the target model info
        model_info = cls.FORM_TYPE_TO_MODEL_MAP.get(form_type)
        if not model_info:
            logger.debug(f"No model mapping found for form type: {form_type}")
            return []
        
        app_label, model_name = model_info
        
        try:
            # Find dynamic models that are intended to extend the existing model
            # We look for models with naming patterns that suggest extension
            extension_patterns = [
                f"{model_name}Extension",
                f"{model_name}Custom",
                f"{model_name}Fields",
                f"Custom{model_name}",
                f"Extended{model_name}",
            ]
            
            dynamic_models = DynamicModel.objects.filter(
                app_label=app_label,
                is_active=True
            ).filter(
                models.Q(name__in=extension_patterns) |
                models.Q(name__icontains='extension') |
                models.Q(description__icontains=f'extend {model_name.lower()}') |
                models.Q(description__icontains=f'{model_name.lower()} extension')
            )
            
            # Get all dynamic fields from these extension models
            dynamic_fields = []
            for dynamic_model in dynamic_models:
                fields = DynamicField.objects.filter(
                    model=dynamic_model,
                    is_active=True
                ).order_by('section', 'order')
                
                logger.debug(f"Found {fields.count()} dynamic fields in model {dynamic_model.name}")
                dynamic_fields.extend(list(fields))
            
            logger.info(f"Retrieved {len(dynamic_fields)} dynamic fields for {form_type}")
            return dynamic_fields
            
        except Exception as e:
            logger.error(f"Error retrieving dynamic fields for {form_type}: {e}")
            return []
    
    @classmethod
    def create_extension_model_if_needed(cls, form_type: str, model_name: str = None) -> Optional:
        """Create a DynamicModel for extending an existing model if it doesn't exist"""
        from requests.models import DynamicModel
        
        model_info = cls.FORM_TYPE_TO_MODEL_MAP.get(form_type)
        if not model_info:
            return None
        
        app_label, base_model_name = model_info
        extension_name = model_name or f"{base_model_name}Extension"
        
        # Check if extension model already exists
        existing_model = DynamicModel.objects.filter(
            app_label=app_label,
            name=extension_name
        ).first()
        
        if existing_model:
            return existing_model
        
        # Create new extension model
        try:
            extension_model = DynamicModel.objects.create(
                name=extension_name,
                app_label=app_label,
                table_name=f"dynamic_{extension_name.lower()}",
                display_name=f"{base_model_name} Extension Fields",
                description=f"Dynamic fields to extend the {base_model_name} model",
                is_active=True
            )
            
            logger.info(f"Created extension model: {extension_model.name}")
            return extension_model
            
        except Exception as e:
            logger.error(f"Error creating extension model for {form_type}: {e}")
            return None
    
    @classmethod
    def get_or_create_extension_model(cls, form_type: str) -> Optional:
        """Get existing or create new extension model for a form type"""
        model_info = cls.FORM_TYPE_TO_MODEL_MAP.get(form_type)
        if not model_info:
            return None
        
        app_label, base_model_name = model_info
        extension_name = f"{base_model_name}Extension"
        
        # Try to get existing
        from requests.models import DynamicModel
        existing_model = DynamicModel.objects.filter(
            app_label=app_label,
            name=extension_name
        ).first()
        
        if existing_model:
            return existing_model
        
        # Create if doesn't exist
        return cls.create_extension_model_if_needed(form_type, extension_name)
    
    @classmethod
    def validate_field_compatibility(cls, form_type: str, field_config: Dict[str, Any]) -> bool:
        """Validate that a dynamic field is compatible with the target model"""
        model_info = cls.FORM_TYPE_TO_MODEL_MAP.get(form_type)
        if not model_info:
            return False
        
        app_label, model_name = model_info
        
        try:
            # Get the actual Django model
            model_class = apps.get_model(app_label, model_name)
            
            # Check if field name conflicts with existing fields
            existing_field_names = [f.name for f in model_class._meta.get_fields()]
            field_name = field_config.get('name', '')
            
            if field_name in existing_field_names:
                logger.warning(f"Field name '{field_name}' conflicts with existing field in {model_class}")
                return False
            
            # Additional validation can be added here
            return True
            
        except Exception as e:
            logger.error(f"Error validating field compatibility: {e}")
            return False
    
    @classmethod
    def get_model_class_for_form_type(cls, form_type: str):
        """Get the actual Django model class for a form type"""
        model_info = cls.FORM_TYPE_TO_MODEL_MAP.get(form_type)
        if not model_info:
            return None
        
        app_label, model_name = model_info
        try:
            return apps.get_model(app_label, model_name)
        except Exception as e:
            logger.error(f"Error getting model class for {form_type}: {e}")
            return None
    
    @classmethod
    def get_form_types_for_model(cls, app_label: str, model_name: str) -> List[str]:
        """Get all form types that map to a specific model"""
        target_key = (app_label, model_name)
        return [
            form_type for form_type, model_info in cls.FORM_TYPE_TO_MODEL_MAP.items()
            if model_info == target_key
        ]