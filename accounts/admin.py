from django.contrib import admin
from django.utils.html import format_html
from django.http import HttpResponse
from django.db import models
from .models import Account
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

@admin.register(Account)
class AccountAdmin(ConfigEnforcedAdminMixin,admin.ModelAdmin):
    list_display = ['name', 'account_type', 'contact_person', 'phone', 'email', 'created_at', 'get_contact_info_display']
    list_filter = ['account_type', 'created_at']
    search_fields = ['name', 'contact_person', 'email', 'phone']
    ordering = ['name']
    readonly_fields = ['created_at', 'get_contact_info_display']
    
    # Force admin widgets for date/time fields to ensure calendar pickers display
    formfield_overrides = {
        models.DateField: {'widget': admin.widgets.AdminDateWidget},
        models.DateTimeField: {'widget': admin.widgets.AdminSplitDateTime},
        models.TimeField: {'widget': admin.widgets.AdminTimeWidget},
    }

    def get_config_form_type(self, obj=None):
        """Get the form type for configuration lookup"""
        return "accounts.Account"

    def get_original_fieldsets(self, request, obj=None):
        """Enhanced fieldsets for Phase 1D - better organization and preparation for export functionality"""
        return [
            ('Account Information', {
                'fields': ('name', 'account_type', 'city'),
                'description': 'Core account identification and classification'
            }),
            ('Contact Details', {
                'fields': ('contact_person', 'position', 'phone', 'email'),
                'description': 'Primary contact information and role details. Position field enhanced as TextField for detailed role descriptions.'
            }),
            ('Additional Information', {
                'fields': ('address', 'website', 'notes'),
                'description': 'Extended account information with Phase 1D enhancements: address and notes as TextField, website as URLField',
                'classes': ('wide',)
            }),
            ('System Information', {
                'fields': ('created_at', 'get_contact_info_display'),
                'classes': ('collapse',),
                'description': 'System-generated information and formatted contact summary'
            })
        ]

    def get_conditional_fieldsets(self, request, obj=None):
        """Get conditional fieldsets based on object state"""
        return []
    
    # Add export preparation - enhanced for future CSV export functionality
    actions = ['export_selected_accounts']
    
    def get_contact_info_display(self, obj):
        """Display formatted contact information for admin interface"""
        if obj:
            return obj.get_contact_info()
        return "No contact information"
    get_contact_info_display.short_description = "Contact Information Summary"
    
    def export_selected_accounts(self, request, queryset):
        """Export selected accounts to CSV file with security safeguards"""
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="accounts_export.csv"'
        
        writer = csv.writer(response)
        # Write CSV header
        writer.writerow([
            'Name', 'Account Type', 'Contact Person', 'Position', 'Phone', 'Email', 
            'Address', 'Website', 'Created Date', 'Notes'
        ])
        
        # Write account data with sanitization and proper display values
        for account in queryset.order_by('name'):
            writer.writerow([
                sanitize_csv_value(account.name),
                sanitize_csv_value(account.get_account_type_display()),  # Use display value for choice field
                sanitize_csv_value(account.contact_person),
                sanitize_csv_value(account.position),
                sanitize_csv_value(account.phone),
                sanitize_csv_value(account.email),
                sanitize_csv_value(account.address),
                sanitize_csv_value(account.website),
                sanitize_csv_value(account.created_at.strftime('%Y-%m-%d %H:%M') if account.created_at else ''),
                sanitize_csv_value(account.notes)
            ])
        
        return response
    export_selected_accounts.short_description = "Export selected accounts to CSV"
