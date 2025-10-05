"""
AdminModelDetector - Service to discover existing Django admin models and convert them 
to Configuration Dashboard sections as "Core Sections"
"""

from django.contrib import admin
from django.apps import apps
from django.db import models
from requests.models import DynamicSection, DynamicField
import json
from typing import Dict, List, Any, Optional

class AdminModelDetector:
    """Detects and analyzes existing admin models to create Core Sections"""
    
    def __init__(self):
        # Target apps to include in configuration system
        self.target_apps = ['accounts', 'requests', 'agreements', 'sales_calls', 'auth']
        
        # Exclude internal configuration models to avoid clutter/recursion
        self.excluded_models = [
            'requests.DynamicSection',
            'requests.DynamicModel', 
            'requests.DynamicField',
            'requests.DynamicFieldValue',
            'requests.DynamicModelMigration'
        ]
    
    def get_registered_admin_models(self) -> Dict[str, Any]:
        """Get all registered admin models and their configurations"""
        # Ensure admin autodiscovery has run
        admin.autodiscover()
        
        admin_models = {}
        
        for model, admin_class in admin.site._registry.items():
            app_label = model._meta.app_label
            model_name = model._meta.object_name  # Use object_name for proper capitalization
            full_name = f"{app_label}.{model_name}"
            
            # Only process models from target apps (excluding internal config models)
            if self._should_include_model(full_name):
                admin_models[full_name] = {
                    'model': model,
                    'admin_class': admin_class,
                    'app_label': app_label,
                    'model_name': model_name,
                    'verbose_name': model._meta.verbose_name,
                    'verbose_name_plural': model._meta.verbose_name_plural,
                    'fields': self._extract_model_fields(model),
                    'admin_config': self._extract_admin_config(admin_class)
                }
        
        return admin_models
    
    def _should_include_model(self, full_name: str) -> bool:
        """Check if this model should be included in configuration system"""
        app_label = full_name.split('.')[0]
        
        # Include if from target apps and not in excluded list
        return (app_label in self.target_apps and 
                full_name not in self.excluded_models)
    
    def _extract_model_fields(self, model) -> List[Dict[str, Any]]:
        """Extract field information from Django model, filtering out non-editable fields"""
        fields = []
        
        for field in model._meta.get_fields():
            # Skip non-editable fields and reverse relations
            if (hasattr(field, 'editable') and not field.editable) or \
               (hasattr(field, 'auto_created') and field.auto_created) or \
               (hasattr(field, 'primary_key') and field.primary_key) or \
               (field.is_relation and not field.many_to_one):
                continue
            
            # Skip computed/auto fields by name
            if field.name in ['id', 'created_at', 'updated_at', 'nights', 'total_cost', 
                             'total_rooms', 'total_room_nights']:
                continue
                
            field_info = {
                'name': field.name,
                'verbose_name': getattr(field, 'verbose_name', field.name.replace('_', ' ').title()),
                'field_type': self._map_django_field_to_config_type(field),
                'required': not getattr(field, 'blank', True),
                'max_length': getattr(field, 'max_length', None),
                'help_text': getattr(field, 'help_text', ''),
                'choices': self._extract_choices(field),
                'is_foreign_key': field.many_to_one if hasattr(field, 'many_to_one') else False,
                'related_model': str(field.related_model) if hasattr(field, 'related_model') and field.related_model else None
            }
            fields.append(field_info)
        
        return fields
    
    def _map_django_field_to_config_type(self, field) -> str:
        """Map Django field types to Configuration field types"""
        field_type_map = {
            'CharField': 'CharField',
            'TextField': 'TextField', 
            'IntegerField': 'IntegerField',
            'FloatField': 'FloatField',
            'DecimalField': 'DecimalField',
            'BooleanField': 'BooleanField',
            'DateField': 'DateField',
            'DateTimeField': 'DateTimeField',
            'EmailField': 'EmailField',
            'URLField': 'URLField',
            'FileField': 'FileField',
            'ImageField': 'ImageField',
            'ForeignKey': 'ForeignKey',
            'PositiveIntegerField': 'IntegerField',
        }
        
        field_type = type(field).__name__
        return field_type_map.get(field_type, 'CharField')  # Default to CharField
    
    def _extract_choices(self, field) -> str:
        """Extract choices from field if available"""
        if hasattr(field, 'choices') and field.choices:
            choices_dict = {str(choice[0]): choice[1] for choice in field.choices}
            return json.dumps(choices_dict)
        return '{}'
    
    def _extract_admin_config(self, admin_class) -> Dict[str, Any]:
        """Extract admin configuration details"""
        return {
            'list_display': getattr(admin_class, 'list_display', []),
            'list_filter': getattr(admin_class, 'list_filter', []),
            'search_fields': getattr(admin_class, 'search_fields', []),
            'readonly_fields': getattr(admin_class, 'readonly_fields', []),
            'fieldsets': getattr(admin_class, 'fieldsets', None),
            'has_config_methods': self._check_config_methods(admin_class)
        }
    
    def _check_config_methods(self, admin_class) -> bool:
        """Check if admin class has configuration methods"""
        config_methods = [
            'get_config_form_type',
            'get_original_fieldsets', 
            'get_conditional_fieldsets'
        ]
        return any(hasattr(admin_class, method) for method in config_methods)
    
    def create_core_sections(self) -> List[DynamicSection]:
        """Create DynamicSection objects for each core admin model"""
        admin_models = self.get_registered_admin_models()
        core_sections = []
        
        for full_name, model_info in admin_models.items():
            # Check if core section already exists
            section_name = f"Core: {model_info['verbose_name_plural']}"
            existing_section = DynamicSection.objects.filter(
                name=section_name,
                is_core_section=True
            ).first()
            
            if not existing_section:
                # Create new core section
                section = DynamicSection.objects.create(
                    name=section_name,
                    display_name=model_info['verbose_name_plural'],
                    description=f"Core admin section for {model_info['verbose_name_plural']} management",
                    is_core_section=True,
                    source_model=full_name,
                    order=self._get_section_order(full_name)
                )
                
                # Create fields for this core section
                self._create_core_section_fields(section, model_info['fields'])
                core_sections.append(section)
            else:
                core_sections.append(existing_section)
        
        return core_sections
    
    def _create_core_section_fields(self, section: DynamicSection, fields: List[Dict[str, Any]]):
        """Create DynamicField objects for core section fields"""
        for i, field_info in enumerate(fields):
            # Skip auto fields and some meta fields
            if field_info['name'] in ['id', 'created_at', 'updated_at']:
                continue
                
            DynamicField.objects.get_or_create(
                section=section,
                name=field_info['name'],
                defaults={
                    'display_name': field_info['verbose_name'],
                    'field_type': field_info['field_type'],
                    'required': field_info['required'],
                    'max_length': field_info['max_length'] or 255,
                    'choices': field_info['choices'],
                    'default_value': '',
                    'order': i * 10,  # Leave space for insertions
                    'is_core_field': True,
                    'help_text': field_info['help_text']
                }
            )
    
    def _get_section_order(self, full_name: str) -> int:
        """Get display order for core sections with app-based ordering"""
        app_label = full_name.split('.')[0].lower()
        model_name = full_name.split('.')[1].lower()
        
        # App-based base ordering
        app_order_map = {
            'accounts': 10,
            'requests': 20,
            'agreements': 30,
            'sales_calls': 40,
            'auth': 90
        }
        
        # Specific model adjustments within apps
        model_adjustments = {
            'requests.request': 0,
            'requests.accommodationrequest': 1,
            'requests.eventonlyrequest': 2,
            'requests.eventwithRoomsrequest': 3,
            'requests.seriesgrouprequest': 4,
            'auth.user': 1,
            'auth.group': 2
        }
        
        base_order = app_order_map.get(app_label, 100)
        adjustment = model_adjustments.get(full_name.lower(), 0)
        
        return base_order + adjustment
    
    def sync_core_sections(self) -> Dict[str, Any]:
        """Synchronize core sections with current admin models"""
        try:
            core_sections = self.create_core_sections()
            return {
                'success': True,
                'core_sections_count': len(core_sections),
                'sections': [
                    {
                        'name': section.name,
                        'display_name': section.display_name, 
                        'field_count': section.fields.count(),
                        'source_model': section.source_model
                    }
                    for section in core_sections
                ]
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }