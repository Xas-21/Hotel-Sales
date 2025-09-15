from django.contrib import admin
from .models import Agreement
from django.utils.html import format_html
from datetime import date, timedelta
from hotel_sales.admin.mixins import ConfigEnforcedAdminMixin

@admin.register(Agreement)
class AgreementAdmin(ConfigEnforcedAdminMixin, admin.ModelAdmin):
    list_display = ['account', 'rate_type', 'start_date', 'end_date', 'return_deadline', 'status', 'deadline_status', 'created_at', 'get_file_status', 'get_notes_summary']
    list_filter = ['rate_type', 'status', 'start_date', 'end_date', 'return_deadline', 'created_at']
    search_fields = ['account__name', 'account__contact_person', 'notes', 'account__address']
    readonly_fields = ['created_at', 'updated_at', 'get_file_status', 'get_notes_summary']
    
    # Enhanced export preparation for Phase 3
    actions = ['export_selected_agreements']
    
    def get_config_form_type(self, obj=None):
        """Get the form type for configuration lookup"""
        return "agreements.Agreement"
    
    def get_original_fieldsets(self, request, obj=None):
        """Enhanced fieldsets for Phase 1F - better organization with proper DateField and file upload support"""
        return [
            ('Agreement Information', {
                'fields': ('account', 'rate_type', 'status'),
                'description': 'Core agreement details and current status'
            }),
            ('Date Management', {
                'fields': ('start_date', 'end_date', 'return_deadline'),
                'description': 'All dates are properly configured as DateField types for accurate date handling. Return deadline includes automated status tracking.',
                'classes': ('wide',)
            }),
            ('File Upload & Documentation', {
                'fields': ('agreement_file', 'notes'),
                'description': 'File upload functionality with proper storage directory structure. Notes field enlarged as TextField for comprehensive documentation.',
                'classes': ('wide',)
            }),
            ('System Tracking', {
                'fields': ('created_at', 'updated_at', 'get_file_status', 'get_notes_summary'),
                'classes': ('collapse',),
                'description': 'System-generated timestamps and enhanced status displays'
            })
        ]
    
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
    
    # Enhanced display methods for Phase 1F
    def get_file_status(self, obj):
        """Display file upload status"""
        if obj and obj.agreement_file:
            return format_html('<span style="color: green;">✓ Uploaded</span>')
        return format_html('<span style="color: orange;">No File</span>')
    get_file_status.short_description = "File Status"
    
    def get_notes_summary(self, obj):
        """Display a summary of notes"""
        if obj and obj.notes:
            summary = obj.notes[:80]  # First 80 characters
            if len(obj.notes) > 80:
                summary += "..."
            return summary
        return "No notes"
    get_notes_summary.short_description = "Notes Summary"
    
    def export_selected_agreements(self, request, queryset):
        """Placeholder action for future CSV export functionality (Phase 3)"""
        self.message_user(request, "Agreements export functionality will be implemented in Phase 3")
    export_selected_agreements.short_description = "Export selected agreements (Coming in Phase 3)"
