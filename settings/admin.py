from django.contrib import admin
from .models import CancellationReason


@admin.register(CancellationReason)
class CancellationReasonAdmin(admin.ModelAdmin):
    """Admin interface for managing cancellation reasons"""
    list_display = ['code', 'label', 'is_refundable', 'active', 'sort_order', 'created_at']
    list_filter = ['is_refundable', 'active', 'created_at']
    search_fields = ['code', 'label']
    list_editable = ['label', 'is_refundable', 'active', 'sort_order']
    ordering = ['sort_order', 'label']
    
    fieldsets = [
        ('Basic Information', {
            'fields': ('code', 'label', 'sort_order'),
            'description': 'Unique identifier, display label, and sort order for the cancellation reason.'
        }),
        ('Settings', {
            'fields': ('is_refundable', 'active'),
            'description': 'Configure whether this reason allows refunds and if it should be available for selection.'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
            'description': 'System timestamps for tracking when the reason was created and last modified.'
        })
    ]
    
    readonly_fields = ['created_at', 'updated_at']
    
    def get_queryset(self, request):
        """Return all cancellation reasons"""
        return super().get_queryset(request).order_by('sort_order', 'label')