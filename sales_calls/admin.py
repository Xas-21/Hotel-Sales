from django.contrib import admin
from .models import SalesCall
from django.utils.html import format_html

@admin.register(SalesCall)
class SalesCallAdmin(admin.ModelAdmin):
    list_display = ['account', 'meeting_subject', 'visit_date', 'city', 'business_potential', 'follow_up_status', 'created_at']
    list_filter = ['meeting_subject', 'business_potential', 'visit_date', 'follow_up_required', 'follow_up_completed']
    search_fields = ['account__name', 'account__contact_person', 'city', 'next_steps']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Visit Information', {
            'fields': ('account', 'visit_date', 'city', 'address')
        }),
        ('Meeting Details', {
            'fields': ('meeting_subject', 'business_potential', 'detailed_notes', 'next_steps')
        }),
        ('Follow-up', {
            'fields': ('follow_up_required', 'follow_up_date', 'follow_up_completed')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    ordering = ['-visit_date']
    
    def follow_up_status(self, obj):
        """Display follow-up status with color coding"""
        if not obj.follow_up_required:
            return format_html('<span style="color: gray;">Not Required</span>')
        elif obj.follow_up_completed:
            return format_html('<span style="color: green;">Completed</span>')
        elif obj.is_follow_up_overdue():
            return format_html('<span style="color: red;">Overdue</span>')
        else:
            return format_html('<span style="color: orange;">Pending</span>')
    follow_up_status.short_description = 'Follow-up Status'
