from django.contrib import admin
from django.db import models
from .models import Agreement
from django.utils.html import format_html
from django.http import HttpResponse
from datetime import date, timedelta
from hotel_sales.admin.mixins import ConfigEnforcedAdminMixin
from hotel_sales.currency_utils import format_currency
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

@admin.register(Agreement)
class AgreementAdmin(ConfigEnforcedAdminMixin, admin.ModelAdmin):
    list_display = ['account', 'rate_type', 'start_date', 'end_date', 'return_deadline', 'status', 'deadline_status', 'created_at', 'get_file_status', 'get_notes_summary']
    list_filter = ['rate_type', 'status', 'start_date', 'end_date', 'return_deadline', 'created_at']
    search_fields = ['account__name', 'account__contact_person', 'notes', 'account__address']
    readonly_fields = ['created_at', 'updated_at', 'get_file_status', 'get_notes_summary']
    
    # Enhanced export preparation for Phase 3
    actions = ['export_selected_agreements']
    
    # Force admin widgets for date/time fields to ensure calendar pickers display
    formfield_overrides = {
        models.DateField: {'widget': admin.widgets.AdminDateWidget},
        models.DateTimeField: {'widget': admin.widgets.AdminSplitDateTime},
        models.TimeField: {'widget': admin.widgets.AdminTimeWidget},
    }
    
    def get_config_form_type(self, obj=None):
        """Get the form type for configuration lookup"""
        return "agreements.Agreement"
    
    def get_original_fieldsets(self, request, obj=None):
        """Enhanced fieldsets for Phase 1F - better organization with proper DateField and file upload support"""
        return [
            ('Agreement Information', {
                'fields': ('account', 'rate_type', 'status')
            }),
            ('Date Management', {
                'fields': ('start_date', 'end_date', 'return_deadline'),
                'classes': ('wide',)
            }),
            ('File Upload & Documentation', {
                'fields': ('agreement_file', 'notes'),
                'classes': ('wide',)
            }),
            ('System Tracking', {
                'fields': ('created_at', 'updated_at', 'get_file_status', 'get_notes_summary'),
                'classes': ('collapse',)
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
        """Export selected agreements to CSV file with security safeguards and comprehensive summary"""
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="agreements_export.csv"'
        
        writer = csv.writer(response)
        # Write CSV header
        writer.writerow([
            'Account', 'Rate Type', 'Start Date', 'End Date', 'Return Deadline',
            'Status', 'File Uploaded', 'Deadline Status', 'Created Date', 'Notes'
        ])
        
        # Initialize counters
        total_agreements = 0
        rate_type_counts = {}
        status_counts = {}
        deadline_status_counts = {}
        files_uploaded = 0
        
        # Write agreement data with sanitization and corrected deadline status logic
        for agreement in queryset.order_by('-created_at'):
            # Determine deadline status - check expired FIRST to avoid misclassification
            if agreement.is_expired():
                deadline_status = 'Expired'
            elif agreement.is_approaching_deadline(7):
                deadline_status = 'Urgent (within 7 days)'
            elif agreement.is_approaching_deadline(30):
                deadline_status = 'Approaching (within 30 days)'
            else:
                deadline_status = 'OK'
            
            # Collect statistics
            total_agreements += 1
            rate_type = agreement.get_rate_type_display()
            rate_type_counts[rate_type] = rate_type_counts.get(rate_type, 0) + 1
            status = agreement.get_status_display()
            status_counts[status] = status_counts.get(status, 0) + 1
            deadline_status_counts[deadline_status] = deadline_status_counts.get(deadline_status, 0) + 1
            if agreement.agreement_file:
                files_uploaded += 1
            
            writer.writerow([
                sanitize_csv_value(agreement.account.name if agreement.account else ''),
                sanitize_csv_value(rate_type),
                sanitize_csv_value(agreement.start_date.strftime('%Y-%m-%d') if agreement.start_date else ''),
                sanitize_csv_value(agreement.end_date.strftime('%Y-%m-%d') if agreement.end_date else ''),
                sanitize_csv_value(agreement.return_deadline.strftime('%Y-%m-%d') if agreement.return_deadline else ''),
                sanitize_csv_value(status),
                sanitize_csv_value('Yes' if agreement.agreement_file else 'No'),
                sanitize_csv_value(deadline_status),
                sanitize_csv_value(agreement.created_at.strftime('%Y-%m-%d %H:%M') if agreement.created_at else ''),
                sanitize_csv_value(agreement.notes)
            ])
        
        # Add comprehensive summary section
        writer.writerow([])
        writer.writerow(['=' * 60])
        writer.writerow(['AGREEMENTS EXPORT SUMMARY'])
        writer.writerow(['=' * 60])
        writer.writerow([])
        writer.writerow(['AGREEMENT STATISTICS:'])
        writer.writerow(['Total Agreements:', total_agreements])
        writer.writerow(['Files Uploaded:', files_uploaded])
        writer.writerow(['Files Pending:', total_agreements - files_uploaded])
        writer.writerow([])
        writer.writerow(['Agreements by Rate Type:'])
        for rate_type, count in sorted(rate_type_counts.items()):
            writer.writerow([f'  {rate_type}:', count])
        writer.writerow([])
        writer.writerow(['Agreements by Status:'])
        for status, count in sorted(status_counts.items()):
            writer.writerow([f'  {status}:', count])
        writer.writerow([])
        writer.writerow(['Deadline Status Distribution:'])
        for deadline_status, count in sorted(deadline_status_counts.items()):
            writer.writerow([f'  {deadline_status}:', count])
        writer.writerow([])
        from datetime import datetime
        writer.writerow(['Export Date:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
        
        return response
    export_selected_agreements.short_description = "Export selected agreements to CSV"
