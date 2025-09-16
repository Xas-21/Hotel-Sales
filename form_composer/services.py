"""
Form Composer Services

Core services for the modern form configuration system.
Provides universal model mapping, configuration enforcement, and
clean APIs for Django admin integration.
"""

from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db.models import Model
from django.apps import apps
from django.forms import ModelForm
from django.contrib.admin import ModelAdmin
from .models import FormDefinition, FormSection, FieldConfig, DynamicFieldValue
import logging
from typing import Dict, List, Any, Optional, Type, Union

logger = logging.getLogger(__name__)


class ConfigRegistry:
    """
    Universal registry for mapping Django models to form configurations.
    
    Uses ContentType for robust model identification instead of fragile string-based
    form_type mapping. Provides clean APIs for registering and resolving form
    configurations for any Django model.
    """
    
    _cache_timeout = 3600  # 1 hour
    _cache_prefix = 'form_composer_registry'
    
    @classmethod
    def register_model(
        cls, 
        model_class: Type[Model], 
        form_type: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        auto_create: bool = True
    ) -> FormDefinition:
        """
        Register a Django model with the form configuration system.
        
        Args:
            model_class: The Django model class to register
            form_type: Optional custom form_type slug (auto-generated if not provided)
            name: Human-readable name for the configuration
            description: Optional description
            auto_create: Whether to create the FormDefinition if it doesn't exist
            
        Returns:
            The FormDefinition instance for this model
            
        Raises:
            ValueError: If model_class is not a Django model
        """
        if not issubclass(model_class, Model):
            raise ValueError(f"{model_class} is not a Django model")
        
        # Get ContentType for this model
        content_type = ContentType.objects.get_for_model(model_class)
        
        # Generate form_type if not provided
        if not form_type:
            form_type = f"{content_type.app_label}_{content_type.model}"
        
        # Generate name if not provided  
        if not name:
            name = f"{model_class._meta.verbose_name_plural.title()} Form"
            
        # Try to get existing FormDefinition
        try:
            form_def = FormDefinition.objects.get(target_model=content_type)
            logger.debug(f"Found existing FormDefinition for {model_class}: {form_def}")
            return form_def
        except FormDefinition.DoesNotExist:
            if not auto_create:
                logger.warning(f"No FormDefinition found for {model_class} and auto_create=False")
                return None
        
        # Create new FormDefinition
        form_def = FormDefinition.objects.create(
            name=name,
            form_type=form_type,
            target_model=content_type,
            description=description or f"Configuration for {model_class._meta.verbose_name_plural}",
            is_active=True
        )
        
        logger.info(f"Created new FormDefinition for {model_class}: {form_def}")
        
        # Clear cache for this model
        cls._clear_cache_for_model(model_class)
        
        return form_def
    
    @classmethod
    def get_form_definition(cls, model_or_instance: Union[Type[Model], Model]) -> Optional[FormDefinition]:
        """
        Get the FormDefinition for a Django model or model instance.
        
        Args:
            model_or_instance: Django model class or instance
            
        Returns:
            FormDefinition instance or None if not found
        """
        # Handle both model classes and instances
        if isinstance(model_or_instance, type) and issubclass(model_or_instance, Model):
            model_class = model_or_instance
        elif hasattr(model_or_instance, '_meta'):
            model_class = model_or_instance.__class__
        else:
            logger.error(f"Invalid model_or_instance: {model_or_instance}")
            return None
        
        # Check cache first
        cache_key = f"{cls._cache_prefix}_form_def_{model_class._meta.app_label}_{model_class._meta.model_name}"
        form_def = cache.get(cache_key)
        
        if form_def is not None:
            logger.debug(f"Found cached FormDefinition for {model_class}")
            return form_def
        
        # Get ContentType and lookup FormDefinition
        try:
            content_type = ContentType.objects.get_for_model(model_class)
            form_def = FormDefinition.objects.filter(
                target_model=content_type,
                is_active=True
            ).first()
            
            # Cache the result (including None results to avoid repeated queries)
            cache.set(cache_key, form_def, cls._cache_timeout)
            
            if form_def:
                logger.debug(f"Found FormDefinition for {model_class}: {form_def}")
            else:
                logger.debug(f"No FormDefinition found for {model_class}")
                
            return form_def
            
        except Exception as e:
            logger.error(f"Error getting FormDefinition for {model_class}: {e}")
            return None
    
    @classmethod
    def get_form_type(cls, model_or_instance: Union[Type[Model], Model]) -> Optional[str]:
        """
        Get the form_type string for a Django model or model instance.
        
        Args:
            model_or_instance: Django model class or instance
            
        Returns:
            form_type string or None if not found
        """
        form_def = cls.get_form_definition(model_or_instance)
        return form_def.form_type if form_def else None
    
    @classmethod
    def get_registered_models(cls) -> List[Dict[str, Any]]:
        """
        Get a list of all registered models with their configurations.
        
        Returns:
            List of dictionaries containing model information
        """
        form_definitions = FormDefinition.objects.filter(is_active=True).select_related('target_model')
        
        results = []
        for form_def in form_definitions:
            model_class = form_def.get_model_class()
            if model_class:
                results.append({
                    'model_class': model_class,
                    'app_label': form_def.target_model.app_label,
                    'model_name': form_def.target_model.model,
                    'form_type': form_def.form_type,
                    'name': form_def.name,
                    'description': form_def.description,
                    'sections_count': form_def.sections.filter(is_active=True).count(),
                    'form_definition': form_def,
                })
        
        return results
    
    @classmethod
    def auto_register_all_models(cls, apps_to_include: Optional[List[str]] = None) -> int:
        """
        Automatically register all Django models in the project.
        
        Args:
            apps_to_include: Optional list of app names to include (all apps if None)
            
        Returns:
            Number of models registered
        """
        registered_count = 0
        
        # Get all models from specified apps or all apps
        if apps_to_include:
            all_models = []
            for app_name in apps_to_include:
                try:
                    app_models = apps.get_app_config(app_name).get_models()
                    all_models.extend(app_models)
                except LookupError:
                    logger.warning(f"App '{app_name}' not found")
        else:
            all_models = apps.get_models()
        
        for model in all_models:
            # Skip abstract models and proxy models
            if model._meta.abstract or model._meta.proxy:
                continue
                
            # Skip models that are already registered
            if cls.get_form_definition(model):
                continue
            
            try:
                cls.register_model(model, auto_create=True)
                registered_count += 1
                logger.debug(f"Auto-registered {model}")
            except Exception as e:
                logger.warning(f"Failed to auto-register {model}: {e}")
        
        logger.info(f"Auto-registered {registered_count} models")
        return registered_count
    
    @classmethod
    def unregister_model(cls, model_class: Type[Model]) -> bool:
        """
        Unregister a Django model from the form configuration system.
        
        Args:
            model_class: The Django model class to unregister
            
        Returns:
            True if successfully unregistered, False if not found
        """
        if not issubclass(model_class, Model):
            raise ValueError(f"{model_class} is not a Django model")
        
        try:
            content_type = ContentType.objects.get_for_model(model_class)
            form_def = FormDefinition.objects.get(target_model=content_type)
            
            # Mark as inactive instead of deleting to preserve data
            form_def.is_active = False
            form_def.save()
            
            # Clear cache
            cls._clear_cache_for_model(model_class)
            
            logger.info(f"Unregistered FormDefinition for {model_class}")
            return True
            
        except FormDefinition.DoesNotExist:
            logger.warning(f"No FormDefinition found for {model_class}")
            return False
        except Exception as e:
            logger.error(f"Error unregistering {model_class}: {e}")
            return False
    
    @classmethod
    def clear_cache(cls):
        """Clear all registry-related cache entries."""
        # This is a simple approach - in production you might want to use cache versioning
        cache_pattern = f"{cls._cache_prefix}_*"
        # Django's cache doesn't support pattern deletion, so we'll clear all
        cache.clear()
        logger.info("Cleared ConfigRegistry cache")
    
    @classmethod
    def _clear_cache_for_model(cls, model_class: Type[Model]):
        """Clear cache entries for a specific model."""
        cache_key = f"{cls._cache_prefix}_form_def_{model_class._meta.app_label}_{model_class._meta.model_name}"
        cache.delete(cache_key)
        logger.debug(f"Cleared cache for {model_class}")
    
    @classmethod
    def get_model_fields(cls, model_class: Type[Model]) -> List[Dict[str, Any]]:
        """
        Get all fields from a Django model for use in configuration.
        
        Args:
            model_class: The Django model class
            
        Returns:
            List of field information dictionaries
        """
        if not issubclass(model_class, Model):
            raise ValueError(f"{model_class} is not a Django model")
        
        fields = []
        
        for field in model_class._meta.get_fields():
            # Skip reverse relations and other non-editable fields
            if hasattr(field, 'editable') and not field.editable:
                continue
            if hasattr(field, 'related_model') and field.related_model and not hasattr(field, 'choices'):
                # This is a reverse relation, skip it
                if hasattr(field, 'one_to_many') or hasattr(field, 'many_to_many'):
                    continue
            
            field_info = {
                'name': field.name,
                'verbose_name': getattr(field, 'verbose_name', field.name.replace('_', ' ').title()),
                'help_text': getattr(field, 'help_text', ''),
                'field_type': field.__class__.__name__,
                'required': not getattr(field, 'blank', True),
                'max_length': getattr(field, 'max_length', None),
                'choices': getattr(field, 'choices', None),
            }
            
            # Add relationship information for foreign keys
            if hasattr(field, 'related_model') and field.related_model:
                field_info['is_relation'] = True
                field_info['related_model'] = field.related_model
                field_info['related_model_name'] = f"{field.related_model._meta.app_label}.{field.related_model._meta.model_name}"
            else:
                field_info['is_relation'] = False
            
            fields.append(field_info)
        
        return fields


class ConfigEnforcementV2:
    """
    Modern configuration enforcement service for Django forms and admin.
    
    Provides clean APIs for applying form configurations from FormDefinition
    models to Django forms and admin interfaces. Replaces the old fragmented
    configuration system with a unified, maintainable approach.
    """
    
    _cache_timeout = 3600  # 1 hour
    _cache_prefix = 'form_composer_enforcement'
    
    @classmethod
    def get_form_config(cls, model_or_instance: Union[Type[Model], Model]) -> Optional[Dict[str, Any]]:
        """
        Get the complete form configuration for a Django model.
        
        Args:
            model_or_instance: Django model class or instance
            
        Returns:
            Dictionary containing complete form configuration or None
        """
        form_def = ConfigRegistry.get_form_definition(model_or_instance)
        if not form_def:
            return None
        
        # Check cache first
        cache_key = f"{cls._cache_prefix}_config_{form_def.id}"
        config = cache.get(cache_key)
        
        if config is not None:
            logger.debug(f"Found cached form config for {form_def}")
            return config
        
        # Build configuration from database
        config = {
            'form_definition': form_def,
            'form_type': form_def.form_type,
            'name': form_def.name,
            'layout_settings': form_def.layout_settings,
            'sections': [],
            'fields': {},
            'field_order': [],
        }
        
        # Get sections and fields
        sections = form_def.get_sections_ordered()
        for section in sections:
            section_config = {
                'id': section.id,
                'name': section.name,
                'slug': section.slug,
                'description': section.description,
                'order': section.order,
                'is_collapsed': section.is_collapsed,
                'css_classes': section.css_classes,
                'conditional_logic': section.conditional_logic,
                'permissions': section.permissions,
                'fields': [],
            }
            
            # Get fields in this section
            fields = section.get_fields_ordered()
            for field_config in fields:
                field_data = {
                    'id': field_config.id,
                    'field_key': field_config.field_key,
                    'label': field_config.label,
                    'help_text': field_config.help_text,
                    'placeholder': field_config.placeholder,
                    'is_active': field_config.is_active,
                    'is_required': field_config.is_required,
                    'is_readonly': field_config.is_readonly,
                    'order': field_config.order,
                    'field_type': field_config.field_type,
                    'widget_type': field_config.widget_type,
                    'widget_attrs': field_config.widget_attrs,
                    'choices_source': field_config.choices_source,
                    'choices_data': field_config.choices_data,
                    'validation_rules': field_config.validation_rules,
                    'default_value': field_config.default_value,
                    'is_dynamic': field_config.is_dynamic,
                    'storage_type': field_config.storage_type,
                    'css_classes': field_config.css_classes,
                    'conditional_logic': field_config.conditional_logic,
                    'section_id': section.id,
                    'section_name': section.name,
                }
                
                section_config['fields'].append(field_data)
                config['fields'][field_config.field_key] = field_data
                config['field_order'].append(field_config.field_key)
            
            config['sections'].append(section_config)
        
        # Cache the configuration
        cache.set(cache_key, config, cls._cache_timeout)
        logger.debug(f"Cached form config for {form_def}")
        
        return config
    
    @classmethod
    def apply_to_form(cls, form: ModelForm, model_or_instance: Union[Type[Model], Model] = None) -> Dict[str, Any]:
        """
        Apply configuration to a Django ModelForm.
        
        Args:
            form: Django ModelForm instance
            model_or_instance: Optional model override (uses form._meta.model if not provided)
            
        Returns:
            Dictionary containing applied configuration details
        """
        # Determine target model
        target = model_or_instance
        if not target and hasattr(form, '_meta') and hasattr(form._meta, 'model'):
            target = form._meta.model
        if not target:
            logger.warning("Cannot determine target model for form configuration")
            return {}
        
        # Get form configuration
        config = cls.get_form_config(target)
        if not config:
            logger.debug(f"No configuration found for {target}")
            return {}
        
        logger.debug(f"Applying configuration to form for {target}")
        
        applied_config = {
            'form_type': config['form_type'],
            'sections': config['sections'],
            'fields_modified': [],
            'fields_added': [],
            'fields_removed': [],
        }
        
        # Apply field configurations
        for field_key, field_config in config['fields'].items():
            if not field_config['is_active']:
                # Remove inactive fields
                if field_key in form.fields:
                    del form.fields[field_key]
                    applied_config['fields_removed'].append(field_key)
                continue
            
            # Handle dynamic fields (not in original model)
            if field_config['is_dynamic']:
                django_field = cls._create_dynamic_field(field_config)
                if django_field:
                    form.fields[field_key] = django_field
                    applied_config['fields_added'].append(field_key)
                continue
            
            # Modify existing model fields
            if field_key in form.fields:
                original_field = form.fields[field_key]
                
                # Apply label override
                if field_config['label']:
                    original_field.label = field_config['label']
                
                # Apply help text
                if field_config['help_text']:
                    original_field.help_text = field_config['help_text']
                
                # Apply required flag
                original_field.required = field_config['is_required']
                
                # Apply readonly flag
                if field_config['is_readonly']:
                    original_field.disabled = True
                
                # Apply widget customizations
                if field_config['widget_type'] != 'default':
                    widget = cls._get_widget(field_config['widget_type'], field_config['widget_attrs'])
                    if widget:
                        original_field.widget = widget
                
                # Apply choices override
                if field_config['choices_data'] and hasattr(original_field, 'choices'):
                    original_field.choices = field_config['choices_data']
                
                # Apply default value
                if field_config['default_value'] and not form.initial.get(field_key):
                    form.initial[field_key] = field_config['default_value']
                
                applied_config['fields_modified'].append(field_key)
        
        # Reorder fields according to configuration
        if config['field_order']:
            new_fields = {}
            # Add fields in configuration order
            for field_key in config['field_order']:
                if field_key in form.fields:
                    new_fields[field_key] = form.fields[field_key]
            
            # Add any remaining fields not in configuration
            for field_key, field in form.fields.items():
                if field_key not in new_fields:
                    new_fields[field_key] = field
            
            form.fields = new_fields
        
        logger.debug(f"Applied configuration: modified={len(applied_config['fields_modified'])}, added={len(applied_config['fields_added'])}, removed={len(applied_config['fields_removed'])}")
        
        return applied_config
    
    @classmethod
    def build_fieldsets(cls, model_admin: ModelAdmin, model_or_instance: Union[Type[Model], Model] = None) -> List[tuple]:
        """
        Build Django admin fieldsets from configuration.
        
        Args:
            model_admin: Django ModelAdmin instance
            model_or_instance: Optional model override (uses model_admin.model if not provided)
            
        Returns:
            List of fieldset tuples for Django admin
        """
        # Determine target model
        target = model_or_instance
        if not target and hasattr(model_admin, 'model'):
            target = model_admin.model
        if not target:
            logger.warning("Cannot determine target model for fieldset generation")
            return []
        
        # Get form configuration
        config = cls.get_form_config(target)
        if not config:
            logger.debug(f"No configuration found for {target}, using default fieldsets")
            return []
        
        logger.debug(f"Building fieldsets for {target}")
        
        fieldsets = []
        
        for section_config in config['sections']:
            section_name = section_config['name']
            section_fields = []
            
            # Add active fields in this section
            for field_data in section_config['fields']:
                if field_data['is_active']:
                    section_fields.append(field_data['field_key'])
            
            if section_fields:
                fieldset_options = {}
                
                # Add collapse option
                if section_config['is_collapsed']:
                    fieldset_options['classes'] = ('collapse',)
                
                # Add description
                if section_config['description']:
                    fieldset_options['description'] = section_config['description']
                
                # Add custom CSS classes
                if section_config['css_classes']:
                    existing_classes = fieldset_options.get('classes', ())
                    fieldset_options['classes'] = existing_classes + (section_config['css_classes'],)
                
                fieldsets.append((section_name, {
                    'fields': section_fields,
                    **fieldset_options
                }))
        
        logger.debug(f"Built {len(fieldsets)} fieldsets for {target}")
        return fieldsets
    
    @classmethod
    def _create_dynamic_field(cls, field_config: Dict[str, Any]):
        """Create a Django form field from dynamic field configuration."""
        from django import forms
        
        field_type = field_config['field_type']
        widget_type = field_config['widget_type']
        widget_attrs = field_config.get('widget_attrs', {})
        
        # Field type mapping
        field_classes = {
            'char': forms.CharField,
            'text': forms.CharField,
            'email': forms.EmailField,
            'url': forms.URLField,
            'integer': forms.IntegerField,
            'decimal': forms.DecimalField,
            'boolean': forms.BooleanField,
            'date': forms.DateField,
            'datetime': forms.DateTimeField,
            'time': forms.TimeField,
            'choice': forms.ChoiceField,
            'multiple_choice': forms.MultipleChoiceField,
            'file': forms.FileField,
            'image': forms.ImageField,
            'json': forms.CharField,
        }
        
        field_class = field_classes.get(field_type, forms.CharField)
        
        # Field kwargs
        field_kwargs = {
            'label': field_config.get('label') or field_config['field_key'].replace('_', ' ').title(),
            'help_text': field_config.get('help_text', ''),
            'required': field_config.get('is_required', False),
        }
        
        # Add widget
        widget = cls._get_widget(widget_type, widget_attrs)
        if widget:
            field_kwargs['widget'] = widget
        
        # Add choices for choice fields
        if field_type in ['choice', 'multiple_choice'] and field_config.get('choices_data'):
            field_kwargs['choices'] = field_config['choices_data']
        
        # Add default value
        if field_config.get('default_value'):
            field_kwargs['initial'] = field_config['default_value']
        
        try:
            return field_class(**field_kwargs)
        except Exception as e:
            logger.error(f"Failed to create dynamic field {field_config['field_key']}: {e}")
            return None
    
    @classmethod
    def _get_widget(cls, widget_type: str, widget_attrs: Dict[str, Any]):
        """Get Django widget instance from widget type and attributes."""
        from django import forms
        
        # Widget mapping
        widget_classes = {
            'text': forms.TextInput,
            'textarea': forms.Textarea,
            'number': forms.NumberInput,
            'email': forms.EmailInput,
            'url': forms.URLInput,
            'password': forms.PasswordInput,
            'checkbox': forms.CheckboxInput,
            'radio': forms.RadioSelect,
            'select': forms.Select,
            'multiselect': forms.SelectMultiple,
            'date': forms.DateInput,
            'datetime': forms.DateTimeInput,
            'time': forms.TimeInput,
            'file': forms.FileInput,
            'image': forms.FileInput,
            'hidden': forms.HiddenInput,
        }
        
        if widget_type == 'default' or widget_type not in widget_classes:
            return None
        
        widget_class = widget_classes[widget_type]
        
        try:
            return widget_class(attrs=widget_attrs)
        except Exception as e:
            logger.error(f"Failed to create widget {widget_type}: {e}")
            return None
    
    @classmethod
    def clear_cache(cls, form_definition_id: Optional[int] = None):
        """Clear enforcement cache entries."""
        if form_definition_id:
            cache_key = f"{cls._cache_prefix}_config_{form_definition_id}"
            cache.delete(cache_key)
            logger.debug(f"Cleared cache for FormDefinition {form_definition_id}")
        else:
            # Clear all cache entries (in production, use cache versioning)
            cache.clear()
            logger.info("Cleared all ConfigEnforcement cache")