"""
Configuration Admin Interface

This module provides the form builder admin interface for managing
dynamic models, fields, and the complete configuration system.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import path, reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.forms import modelform_factory
from requests.models import DynamicModel, DynamicField, DynamicModelMigration
from requests.services.dynamic_model_factory import DynamicModelFactory
from requests.services.schema_manager import SchemaManager
import json


class DynamicFieldInline(admin.TabularInline):
    """Inline admin for managing dynamic fields within a model"""
    model = DynamicField
    extra = 1
    fields = [
        'name', 'display_name', 'field_type', 'required', 
        'section', 'order', 'max_length', 'choices', 'is_active'
    ]
    ordering = ['section', 'order']
    
    class Media:
        js = ('admin/js/dynamic_field_admin.js',)
        css = {
            'all': ('admin/css/dynamic_field_admin.css',)
        }


# @admin.register(DynamicModel)  # Removed from admin panel - use Configuration dashboard instead
class DynamicModelAdmin(admin.ModelAdmin):
    """Admin interface for dynamic model management"""
    list_display = [
        'display_name', 'name', 'app_label', 'is_active', 
        'field_count', 'created_at', 'model_actions'
    ]
    list_filter = ['app_label', 'is_active', 'created_at']
    search_fields = ['name', 'display_name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    exclude = ['created_at', 'updated_at']  # Exclude non-editable fields from form
    inlines = [DynamicFieldInline]
    
    fieldsets = [
        ('Model Configuration', {
            'fields': ['name', 'display_name', 'app_label', 'table_name', 'description']
        }),
        ('Settings', {
            'fields': ['is_active', 'ordering_fields']
        }),
        ('Metadata', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse']
        })
    ]
    
    def get_urls(self):
        """Add custom URLs for model operations"""
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:model_id>/deploy/',
                self.admin_site.admin_view(self.deploy_model),
                name='requests_dynamicmodel_deploy'
            ),
            path(
                '<int:model_id>/preview/',
                self.admin_site.admin_view(self.preview_model),
                name='requests_dynamicmodel_preview'
            ),
            path(
                'form-builder/',
                self.admin_site.admin_view(self.form_builder),
                name='requests_dynamicmodel_form_builder'
            ),
        ]
        return custom_urls + urls
    
    def field_count(self, obj):
        """Display count of fields in this model"""
        count = obj.fields.filter(is_active=True).count()
        return format_html(
            '<span class="field-count">{} fields</span>',
            count
        )
    field_count.short_description = 'Fields'
    
    def model_actions(self, obj):
        """Display action buttons for the model"""
        if obj.is_active:
            deploy_url = reverse('admin:requests_dynamicmodel_deploy', args=[obj.pk])
            preview_url = reverse('admin:requests_dynamicmodel_preview', args=[obj.pk])
            
            return format_html(
                '<a href="{}" class="button">Deploy</a> '
                '<a href="{}" class="button">Preview</a>',
                deploy_url, preview_url
            )
        else:
            return format_html('<span class="inactive">Inactive</span>')
    model_actions.short_description = 'Actions'
    model_actions.allow_tags = True
    
    def deploy_model(self, request, model_id):
        """Deploy a dynamic model - create tables and register with admin"""
        dynamic_model = get_object_or_404(DynamicModel, pk=model_id)
        
        if request.method == 'POST':
            try:
                success = DynamicModelFactory.create_and_register_model(dynamic_model)
                
                if success:
                    messages.success(
                        request, 
                        f'Model "{dynamic_model.display_name}" deployed successfully! '
                        f'Database table created and admin interface registered.'
                    )
                    
                    # Record migration
                    DynamicModelMigration.objects.create(
                        model_name=dynamic_model.name,
                        operation_type='create_model',
                        operation_data={
                            'model_config': {
                                'name': dynamic_model.name,
                                'table_name': dynamic_model.table_name,
                                'display_name': dynamic_model.display_name,
                            }
                        },
                        success=True
                    )
                else:
                    messages.error(request, f'Failed to deploy model "{dynamic_model.display_name}"')
                    
            except Exception as e:
                messages.error(request, f'Deployment error: {str(e)}')
                
                # Record failed migration
                DynamicModelMigration.objects.create(
                    model_name=dynamic_model.name,
                    operation_type='create_model',
                    operation_data={'error': str(e)},
                    success=False,
                    error_message=str(e)
                )
            
            return redirect('admin:requests_dynamicmodel_changelist')
        
        # GET request - show confirmation page
        context = {
            'dynamic_model': dynamic_model,
            'fields': dynamic_model.fields.filter(is_active=True).order_by('section', 'order'),
            'title': f'Deploy Model: {dynamic_model.display_name}',
        }
        return render(request, 'admin/requests/dynamicmodel/deploy.html', context)
    
    def preview_model(self, request, model_id):
        """Preview how the model will look in forms and admin"""
        dynamic_model = get_object_or_404(DynamicModel, pk=model_id)
        
        # Group fields by section
        sections = {}
        for field in dynamic_model.fields.filter(is_active=True).order_by('section', 'order'):
            section_name = field.section or 'General'
            if section_name not in sections:
                sections[section_name] = []
            sections[section_name].append(field)
        
        context = {
            'dynamic_model': dynamic_model,
            'sections': sections,
            'title': f'Preview Model: {dynamic_model.display_name}',
        }
        return render(request, 'admin/requests/dynamicmodel/preview.html', context)
    
    def form_builder(self, request):
        """Visual form builder interface"""
        context = {
            'title': 'Form Builder',
            'field_types': DynamicField.FIELD_TYPES,
            'available_models': DynamicModel.objects.filter(is_active=True),
        }
        return render(request, 'admin/requests/dynamicmodel/form_builder.html', context)


# @admin.register(DynamicField)  # Removed from admin panel - use Configuration dashboard instead
class DynamicFieldAdmin(admin.ModelAdmin):
    """Admin interface for individual field management"""
    list_display = [
        'display_name', 'name', 'field_type', 'model', 'section', 
        'required', 'is_active', 'order'
    ]
    list_filter = ['field_type', 'required', 'is_active', 'model__name']
    search_fields = ['name', 'display_name', 'model__name']
    list_editable = ['required', 'is_active', 'order']
    exclude = ['created_at', 'updated_at']  # Exclude non-editable fields from form
    
    fieldsets = [
        ('Field Configuration', {
            'fields': ['model', 'name', 'display_name', 'field_type', 'help_text']
        }),
        ('Field Options', {
            'fields': ['required', 'default_value', 'is_active']
        }),
        ('Field Constraints', {
            'fields': ['max_length', 'max_digits', 'decimal_places'],
            'classes': ['collapse']
        }),
        ('Choice Options', {
            'fields': ['choices'],
            'classes': ['collapse'],
            'description': 'For choice fields, enter JSON: {"value1": "Display 1", "value2": "Display 2"}'
        }),
        ('Relationship Options', {
            'fields': ['related_model'],
            'classes': ['collapse'],
            'description': 'For foreign key fields, enter: app_label.ModelName (e.g., accounts.Account)'
        }),
        ('Display Options', {
            'fields': ['section', 'order']
        })
    ]
    
    def get_form(self, request, obj=None, **kwargs):
        """Customize the form based on field type"""
        form = super().get_form(request, obj, **kwargs)
        
        # Add JavaScript to hide/show relevant fields based on field_type
        form.Media.js = form.Media.js + ('admin/js/dynamic_field_form.js',)
        
        return form


# @admin.register(DynamicModelMigration)  # Removed from admin panel - use Configuration dashboard instead
class DynamicModelMigrationAdmin(admin.ModelAdmin):
    """Admin interface for viewing migration history"""
    list_display = [
        'operation_type', 'model_name', 'status_display', 'applied_at'
    ]
    list_filter = ['operation_type', 'success', 'applied_at']
    search_fields = ['model_name', 'error_message']
    readonly_fields = [
        'model_name', 'operation_type', 'operation_data', 
        'applied_at', 'success', 'error_message'
    ]
    ordering = ['-applied_at']
    
    def has_add_permission(self, request):
        """Prevent manual creation of migrations"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Prevent editing of migrations"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Allow deletion for cleanup"""
        return True
    
    def status_display(self, obj):
        """Show status with color coding"""
        if obj.success:
            return format_html(
                '<span style="color: green;">✓ Success</span>'
            )
        else:
            return format_html(
                '<span style="color: red;">✗ Failed</span>'
            )
    status_display.short_description = 'Status'


# Configuration Section Admin
class ConfigurationAdmin:
    """Container for all configuration-related admin interfaces"""
    
    def __init__(self, admin_site):
        self.admin_site = admin_site
    
    def get_urls(self):
        """Get URLs for the configuration section"""
        return [
            path(
                'configuration/',
                self.admin_site.admin_view(self.configuration_index),
                name='configuration_index'
            ),
            path(
                'configuration/models/',
                self.admin_site.admin_view(self.models_overview),
                name='configuration_models'
            ),
            path(
                'configuration/sections/',
                self.admin_site.admin_view(self.sections_overview), 
                name='configuration_sections'
            ),
        ]
    
    def configuration_index(self, request):
        """Main configuration dashboard"""
        context = {
            'title': 'System Configuration',
            'total_models': DynamicModel.objects.count(),
            'active_models': DynamicModel.objects.filter(is_active=True).count(),
            'total_fields': DynamicField.objects.count(),
            'recent_migrations': DynamicModelMigration.objects.order_by('-applied_at')[:5],
        }
        return render(request, 'admin/configuration/index.html', context)
    
    def models_overview(self, request):
        """Overview of all models (existing + dynamic)"""
        from django.apps import apps
        
        # Get existing models
        existing_models = []
        for model in apps.get_models():
            if model._meta.app_label in ['accounts', 'requests', 'agreements', 'sales_calls']:
                existing_models.append({
                    'name': model.__name__,
                    'app_label': model._meta.app_label,
                    'verbose_name': model._meta.verbose_name,
                    'field_count': len(model._meta.get_fields()),
                    'is_dynamic': False,
                })
        
        # Get dynamic models
        dynamic_models = []
        for model in DynamicModel.objects.filter(is_active=True):
            dynamic_models.append({
                'name': model.name,
                'app_label': model.app_label,
                'verbose_name': model.display_name,
                'field_count': model.fields.filter(is_active=True).count(),
                'is_dynamic': True,
                'model_id': model.id,
            })
        
        context = {
            'title': 'Models Overview',
            'existing_models': existing_models,
            'dynamic_models': dynamic_models,
        }
        return render(request, 'admin/configuration/models.html', context)
    
    def sections_overview(self, request):
        """Overview of form sections across all models"""
        sections = {}
        
        # Get sections from dynamic fields
        for field in DynamicField.objects.filter(is_active=True):
            section_name = field.section or 'General'
            model_name = f"{field.model.app_label}.{field.model.name}"
            
            if section_name not in sections:
                sections[section_name] = {}
            if model_name not in sections[section_name]:
                sections[section_name][model_name] = []
            
            sections[section_name][model_name].append({
                'name': field.name,
                'display_name': field.display_name,
                'field_type': field.field_type,
                'required': field.required,
            })
        
        context = {
            'title': 'Form Sections Overview',
            'sections': sections,
        }
        return render(request, 'admin/configuration/sections.html', context)