from django.contrib import admin
from .models import SalesCall
from django.utils.html import format_html
from django.http import HttpResponse
from hotel_sales.admin.mixins import ConfigEnforcedAdminMixin
import csv

def sanitize_csv_value(value):
    """Sanitize CSV values to prevent CSV injection attacks"""
    if value is None:
        return ""
    
    str_value = str(value)
    # If value starts with formula characters, prefix with single quote
    if str_value and str_value[0] in ['=', '+', '-', '@', '\t']:
        return "'" + str_value
    return str_value


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
        """Export selected sales calls to CSV file with security safeguards"""
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="sales_calls_export.csv"'
        
        writer = csv.writer(response)
        # Write CSV header
        writer.writerow([
            'Account', 'Meeting Subject', 'Visit Date', 'City', 'Address',
            'Business Potential', 'Next Steps', 'Detailed Notes',
            'Follow-up Required', 'Follow-up Date', 'Follow-up Completed', 'Created Date'
        ])
        
        # Write sales call data with sanitization and proper display values
        for call in queryset.order_by('-visit_date'):
            writer.writerow([
                sanitize_csv_value(call.account.name if call.account else ''),
                sanitize_csv_value(call.get_meeting_subject_display()),
                sanitize_csv_value(call.visit_date.strftime('%Y-%m-%d') if call.visit_date else ''),
                sanitize_csv_value(call.city),
                sanitize_csv_value(call.address),
                sanitize_csv_value(call.get_business_potential_display()),
                sanitize_csv_value(call.next_steps),
                sanitize_csv_value(call.detailed_notes),
                sanitize_csv_value('Yes' if call.follow_up_required else 'No'),
                sanitize_csv_value(call.follow_up_date.strftime('%Y-%m-%d') if call.follow_up_date else ''),
                sanitize_csv_value('Yes' if call.follow_up_completed else 'No'),
                sanitize_csv_value(call.created_at.strftime('%Y-%m-%d %H:%M') if call.created_at else '')
            ])
        
        return response
    export_selected_sales_calls.short_description = "Export selected sales calls to CSV"
