"""
Admin interface for Form Composer

Provides powerful admin interfaces for managing form configurations,
sections, and fields with intuitive drag-and-drop capabilities.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from hotel_sales.admin.mixins import ConfigEnforcedAdminMixin
from .models import FormDefinition, FormSection, FieldConfig, DynamicFieldValue, UserPreference


class FormSectionInline(admin.TabularInline):
    """Inline editor for form sections"""
    model = FormSection
    extra = 0
    fields = ['name', 'slug', 'order', 'is_active', 'is_collapsed']
    ordering = ['order']
    
    # Media files will be added in Task 4 when building drag-and-drop UI
    # class Media:
    #     css = {
    #         'all': ('admin/css/form_composer.css',)
    #     }
    #     js = ('admin/js/form_composer.js',)


class FieldConfigInline(admin.TabularInline):
    """Inline editor for field configurations"""
    model = FieldConfig
    extra = 0
    fields = ['field_key', 'label', 'order', 'is_active', 'is_required', 'widget_type']
    ordering = ['order']


@admin.register(FormDefinition)
class FormDefinitionAdmin(ConfigEnforcedAdminMixin, admin.ModelAdmin):
    """Admin for form definitions with advanced management capabilities"""
    
    list_display = [
        'name', 'form_type', 'target_model_display', 'is_active', 
        'sections_count', 'fields_count', 'updated_at'
    ]
    
    list_filter = ['is_active', 'target_model', 'created_at']
    search_fields = ['name', 'form_type', 'description']
    
    fieldsets = [
        ('Basic Information', {
            'fields': ['name', 'form_type', 'target_model', 'description']
        }),
        ('Status & Versioning', {
            'fields': ['is_active', 'version'],
            'classes': ['collapse']
        }),
        ('Advanced Settings', {
            'fields': ['layout_settings'],
            'classes': ['collapse']
        }),
    ]
    
    inlines = [FormSectionInline]
    
    readonly_fields = ['created_at', 'updated_at']
    
    def target_model_display(self, obj):
        """Display the target model in a user-friendly format"""
        return f"{obj.target_model.app_label}.{obj.target_model.model}"
    target_model_display.short_description = "Target Model"
    
    def sections_count(self, obj):
        """Display count of active sections"""
        count = obj.sections.filter(is_active=True).count()
        return format_html('<span class="badge">{}</span>', count)
    sections_count.short_description = "Sections"
    
    def fields_count(self, obj):
        """Display count of active fields across all sections"""
        count = FieldConfig.objects.filter(
            section__form_definition=obj,
            section__is_active=True,
            is_active=True
        ).count()
        return format_html('<span class="badge">{}</span>', count)
    fields_count.short_description = "Fields"
    
    def save_model(self, request, obj, form, change):
        """Set the created_by field for new objects"""
        if not change and hasattr(obj, 'created_by'):
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(FormSection)
class FormSectionAdmin(ConfigEnforcedAdminMixin, admin.ModelAdmin):
    """Admin for form sections with field management"""
    
    list_display = [
        'name', 'form_definition', 'order', 'is_active', 
        'is_collapsed', 'fields_count'
    ]
    
    list_filter = ['is_active', 'is_collapsed', 'form_definition']
    search_fields = ['name', 'slug', 'description']
    
    fieldsets = [
        ('Basic Information', {
            'fields': ['form_definition', 'name', 'slug', 'description']
        }),
        ('Display Settings', {
            'fields': ['order', 'is_active', 'is_collapsed']
        }),
        ('Advanced Features', {
            'fields': ['conditional_logic', 'permissions', 'css_classes'],
            'classes': ['collapse']
        }),
    ]
    
    inlines = [FieldConfigInline]
    
    def fields_count(self, obj):
        """Display count of active fields in this section"""
        count = obj.field_configs.filter(is_active=True).count()
        return format_html('<span class="badge">{}</span>', count)
    fields_count.short_description = "Fields"


@admin.register(FieldConfig)
class FieldConfigAdmin(ConfigEnforcedAdminMixin, admin.ModelAdmin):
    """Admin for individual field configurations"""
    
    list_display = [
        'field_key', 'section', 'get_effective_label', 'order', 
        'is_active', 'is_required', 'widget_type'
    ]
    
    list_filter = [
        'is_active', 'is_required', 'is_readonly', 'is_dynamic', 
        'field_type', 'widget_type', 'storage_type'
    ]
    
    search_fields = ['field_key', 'label', 'help_text']
    
    fieldsets = [
        ('Field Identification', {
            'fields': ['section', 'field_key', 'order']
        }),
        ('Display Configuration', {
            'fields': ['label', 'help_text', 'placeholder']
        }),
        ('Behavior', {
            'fields': ['is_active', 'is_required', 'is_readonly']
        }),
        ('Widget & Type', {
            'fields': ['field_type', 'widget_type', 'widget_attrs'],
            'classes': ['collapse']
        }),
        ('Choice Configuration', {
            'fields': ['choices_source', 'choices_data'],
            'classes': ['collapse']
        }),
        ('Validation & Defaults', {
            'fields': ['validation_rules', 'default_value'],
            'classes': ['collapse']
        }),
        ('Dynamic Field Settings', {
            'fields': ['is_dynamic', 'storage_type'],
            'classes': ['collapse']
        }),
        ('Advanced', {
            'fields': ['css_classes', 'conditional_logic'],
            'classes': ['collapse']
        }),
    ]
    
    def get_queryset(self, request):
        """Optimize queries with select_related"""
        return super().get_queryset(request).select_related('section__form_definition')


@admin.register(DynamicFieldValue)
class DynamicFieldValueAdmin(ConfigEnforcedAdminMixin, admin.ModelAdmin):
    """Admin for dynamic field values"""
    
    list_display = [
        'field_config', 'content_type', 'object_id', 'get_value_preview', 'updated_at'
    ]
    
    list_filter = ['field_config__field_type', 'content_type']
    search_fields = ['field_config__field_key', 'value_text']
    
    readonly_fields = ['created_at', 'updated_at']
    
    def get_value_preview(self, obj):
        """Show a preview of the stored value"""
        value = obj.get_value()
        if value is None:
            return format_html('<em>None</em>')
        
        # Truncate long values
        str_value = str(value)
        if len(str_value) > 50:
            str_value = str_value[:47] + "..."
        
        return format_html('<code>{}</code>', str_value)
    get_value_preview.short_description = "Value"


@admin.register(UserPreference)
class UserPreferenceAdmin(ConfigEnforcedAdminMixin, admin.ModelAdmin):
    """Admin for user preferences"""
    
    list_display = ['user', 'preference_key', 'get_value_preview', 'updated_at']
    list_filter = ['preference_key']
    search_fields = ['user__username', 'preference_key']
    
    readonly_fields = ['created_at', 'updated_at']
    
    def get_value_preview(self, obj):
        """Show a preview of the preference value"""
        value = str(obj.preference_value)
        if len(value) > 100:
            value = value[:97] + "..."
        return format_html('<code>{}</code>', value)
    get_value_preview.short_description = "Value"
