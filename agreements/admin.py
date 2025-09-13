from django.contrib import admin
from .models import Agreement
from django.utils.html import format_html
from datetime import date, timedelta
from hotel_sales.admin.mixins import ConfigEnforcedAdminMixin

@admin.register(Agreement)
class AgreementAdmin(ConfigEnforcedAdminMixin, admin.ModelAdmin):
    list_display = ['account', 'rate_type', 'start_date', 'end_date', 'return_deadline', 'status', 'deadline_status', 'created_at']
    list_filter = ['rate_type', 'status', 'start_date', 'end_date', 'return_deadline']
    search_fields = ['account__name', 'account__contact_person']
    readonly_fields = ['created_at', 'updated_at']
    
    def get_config_form_type(self, obj=None):
        """Get the form type for configuration lookup"""
        return "agreements.Agreement"
    
    def get_original_fieldsets(self, request, obj=None):
        """Original fieldsets for fallback"""
        return (
            ('Agreement Details', {
                'fields': ('account', 'rate_type', 'start_date', 'end_date', 'return_deadline')
            }),
            ('Status & File', {
                'fields': ('status', 'agreement_file')
            }),
            ('Notes & Metadata', {
                'fields': ('notes', 'created_at', 'updated_at'),
                'classes': ('collapse',)
            })
        )
    
    def get_conditional_fieldsets(self, request, obj=None):
        """Get conditional fieldsets based on object state"""
        return []
    
    ordering = ['-created_at']
    
    def deadline_status(self, obj):
        """Display deadline status with color coding"""
        if obj.is_approaching_deadline(7):  # Within 7 days
            return format_html('<span style="color: red;">Urgent</span>')
        elif obj.is_approaching_deadline(30):  # Within 30 days
            return format_html('<span style="color: orange;">Approaching</span>')
        elif obj.is_expired():
            return format_html('<span style="color: gray;">Expired</span>')
        else:
            return format_html('<span style="color: green;">Ok</span>')
    deadline_status.short_description = 'Deadline Status'
