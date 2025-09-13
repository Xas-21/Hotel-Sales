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
            mapped_type = form_type_map.get(key, f"{app_label}.{model_name.title()}")
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
            from requests.models import SystemFieldRequirement
            
            configs = {}
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
    from requests.models import SystemFieldRequirement, SystemFormLayout
    
    if isinstance(instance, SystemFieldRequirement):
        ConfigEnforcementService.invalidate_cache(instance.form_type)
    elif isinstance(instance, SystemFormLayout):
        ConfigEnforcementService.invalidate_cache(instance.form_type)