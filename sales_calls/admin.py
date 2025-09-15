from django.contrib import admin
from .models import SalesCall
from django.utils.html import format_html
from hotel_sales.admin.mixins import ConfigEnforcedAdminMixin


@admin.register(SalesCall)
class SalesCallAdmin(ConfigEnforcedAdminMixin, admin.ModelAdmin):
    list_display = [
        'account', 'meeting_subject', 'visit_date', 'city',
        'business_potential', 'follow_up_status', 'created_at', 'get_next_steps_summary'
    ]
    list_filter = [
        'meeting_subject', 'business_potential', 'visit_date',
        'follow_up_required', 'follow_up_completed', 'created_at'
    ]
    search_fields = [
        'account__name', 'account__contact_person', 'city', 'next_steps', 'detailed_notes', 'address'
    ]
    readonly_fields = ['created_at', 'updated_at', 'get_next_steps_summary']
    
    # Enhanced export preparation for Phase 3 
    actions = ['export_selected_sales_calls']

    def get_config_form_type(self, obj=None):
        """Get the form type for configuration lookup"""
        return "sales_calls.SalesCall"

    def get_original_fieldsets(self, request, obj=None):
        """Enhanced fieldsets for Phase 1E - better organization and descriptions"""
        return [
            ('Visit Information', {
                'fields': ('account', 'visit_date', 'city', 'address'),
                'description': 'Core visit details and location information'
            }),
            ('Meeting Details & Business Assessment', {
                'fields': ('meeting_subject', 'business_potential', 'detailed_notes', 'next_steps'),
                'description': 'Meeting discussion details and business potential evaluation. Text areas are enlarged for comprehensive note-taking.',
                'classes': ('wide',)
            }),
            ('Follow-up Management', {
                'fields': ('follow_up_required', 'follow_up_date', 'follow_up_completed'),
                'description': 'Follow-up requirements and completion tracking. Status will appear in list view with color coding.'
            }),
            ('System Information', {
                'fields': ('created_at', 'updated_at', 'get_next_steps_summary'),
                'classes': ('collapse',),
                'description': 'System-generated timestamps and next steps summary'
            })
        ]

    def get_conditional_fieldsets(self, request, obj=None):
        """Get conditional fieldsets based on object state"""
        return []

    ordering = ['-visit_date']

    def follow_up_status(self, obj):
        """Display follow-up status with color coding"""
        if not obj.follow_up_required:
            return format_html(
                '<span style="color: gray;">Not Required</span>')
        elif obj.follow_up_completed:
            return format_html('<span style="color: green;">Completed</span>')
        elif obj.is_follow_up_overdue():
            return format_html('<span style="color: red;">Overdue</span>')
        else:
            return format_html('<span style="color: orange;">Pending</span>')

    follow_up_status.short_description = 'Follow-up Status'
    
    # Enhanced display methods for Phase 1E
    def get_next_steps_summary(self, obj):
        """Display a summary of next steps"""
        if obj and obj.next_steps:
            summary = obj.next_steps[:100]  # First 100 characters
            if len(obj.next_steps) > 100:
                summary += "..."
            return summary
        return "No next steps defined"
    get_next_steps_summary.short_description = "Next Steps Summary"
    
    def export_selected_sales_calls(self, request, queryset):
        """Placeholder action for future CSV export functionality (Phase 3)"""
        self.message_user(request, "Sales calls export functionality will be implemented in Phase 3")
    export_selected_sales_calls.short_description = "Export selected sales calls (Coming in Phase 3)"
