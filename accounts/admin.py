from django.contrib import admin
from django.utils.html import format_html
from .models import Account
from hotel_sales.admin.mixins import ConfigEnforcedAdminMixin

@admin.register(Account)
class AccountAdmin(ConfigEnforcedAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'account_type', 'contact_person', 'phone', 'email', 'created_at', 'get_contact_info_display']
    list_filter = ['account_type', 'created_at']
    search_fields = ['name', 'contact_person', 'email', 'phone']
    ordering = ['name']
    readonly_fields = ['created_at', 'get_contact_info_display']

    def get_config_form_type(self, obj=None):
        """Get the form type for configuration lookup"""
        return "accounts.Account"

    def get_original_fieldsets(self, request, obj=None):
        """Enhanced fieldsets for Phase 1D - better organization and preparation for export functionality"""
        return [
            ('Account Information', {
                'fields': ('name', 'account_type'),
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
        """Placeholder action for future CSV export functionality (Phase 3)"""
        self.message_user(request, "Export functionality will be implemented in Phase 3")
    export_selected_accounts.short_description = "Export selected accounts (Coming in Phase 3)"
