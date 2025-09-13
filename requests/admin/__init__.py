# Admin package initialization
# Import all admin classes to ensure registration

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from requests.models import (
    Request, CancelledRequest, RoomEntry, Transportation, EventAgenda, SeriesGroupEntry, SeriesRoomEntry,
    RoomType, RoomOccupancy, CancellationReason, SystemFieldRequirement, SystemFormLayout,
    RequestFieldRequirement, RequestFormLayout, DynamicModel, DynamicField, DynamicModelMigration, DynamicFieldValue
)
from hotel_sales.admin.mixins import ConfigEnforcedAdminMixin

class RoomEntryInline(admin.TabularInline):
    model = RoomEntry
    extra = 1
    fields = ['room_type', 'occupancy_type', 'category', 'occupancy', 'quantity', 'rate_per_night']
    verbose_name = "Room Entry"
    verbose_name_plural = "Room Configuration"
    can_delete = True
    
    def get_queryset(self, request):
        """Optimize foreign key queries"""
        return super().get_queryset(request).select_related('room_type', 'occupancy_type')

class TransportationInline(admin.TabularInline):
    model = Transportation
    extra = 0
    fields = ['vehicle_type', 'number_of_pax', 'cost', 'notes']

class EventAgendaInline(admin.TabularInline):
    model = EventAgenda
    extra = 0
    fields = ['event_date', 'start_time', 'end_time', 'coffee_break_time', 'lunch_time', 'agenda_details']

class SeriesRoomEntryInline(admin.TabularInline):
    model = SeriesRoomEntry
    extra = 1
    fields = ['room_type', 'occupancy_type', 'category', 'occupancy', 'quantity', 'rate_per_night']
    verbose_name = "Room Configuration"
    verbose_name_plural = "Room Configuration for this Date"
    can_delete = True
    
    def get_queryset(self, request):
        """Optimize foreign key queries"""
        return super().get_queryset(request).select_related('room_type', 'occupancy_type')

class SeriesGroupEntryInline(admin.TabularInline):
    model = SeriesGroupEntry
    extra = 0
    fields = ['arrival_date', 'departure_date', 'arrival_time', 'departure_time', 'group_size', 'special_notes']
    readonly_fields = ['nights']

@admin.register(Request)
class RequestAdmin(ConfigEnforcedAdminMixin, admin.ModelAdmin):
    list_display = ['confirmation_number', 'account', 'request_type', 'meal_plan', 'status', 'check_in_date', 'check_out_date', 'nights', 'total_rooms', 'total_room_nights', 'total_cost', 'created_at']
    list_filter = ['request_type', 'meal_plan', 'status', 'created_at', 'check_in_date']
    search_fields = ['confirmation_number', 'account__name', 'account__contact_person']
    readonly_fields = ['nights', 'total_cost', 'total_rooms', 'total_room_nights', 'created_at', 'updated_at']
    inlines = [RoomEntryInline, TransportationInline, EventAgendaInline, SeriesGroupEntryInline]
    ordering = ['-created_at']
    
    def get_config_form_type(self, obj=None):
        """Get the form type for configuration lookup based on request type"""
        if obj and hasattr(obj, 'request_type'):
            return f"requests.{obj.request_type}"
        # Default for new objects
        return "requests.Group Accommodation"
    
    def get_original_fieldsets(self, request, obj=None):
        """
        Fallback fieldsets when no configuration is available.
        These are the original hardcoded fieldsets.
        """
        # Base fieldsets
        fieldsets = [
            ('Basic Information', {
                'fields': ('request_type', 'account', 'confirmation_number', 'request_received_date')
            }),
            ('Accommodation Details & Room Configuration', {
                'fields': ('check_in_date', 'check_out_date', 'nights', 'meal_plan'),
                'description': 'Add room entries below in the "Room entries" section - room costs will be automatically included in total cost calculation.'
            }),
            ('Status & Payment', {
                'fields': ('status', 'offer_acceptance_deadline', 'deposit_deadline', 'full_payment_deadline')
            }),
            ('Financial Tracking (Auto-Calculated)', {
                'fields': ('total_cost', 'total_rooms', 'total_room_nights', 'deposit_amount', 'paid_amount'),
                'description': 'Financial totals are automatically calculated from room entries and transportation. If total_cost shows zero, ensure room entries have been added with valid rates.'
            }),
            ('File & Notes', {
                'fields': ('agreement_file', 'notes'),
                'classes': ('collapse',)
            }),
            ('Metadata', {
                'fields': ('created_at', 'updated_at'),
                'classes': ('collapse',)
            })
        ]
        return fieldsets
    
    def get_conditional_fieldsets(self, request, obj=None):
        """
        Get conditional fieldsets based on object state.
        For requests, show cancellation fields when status is 'Cancelled'.
        """
        conditional_fieldsets = []
        
        if obj and obj.status == 'Cancelled':
            conditional_fieldsets.append(('Cancellation Details', {
                'fields': ('cancellation_reason_fixed', 'cancellation_reason'),
                'description': 'Cancellation information for this request'
            }))
        
        return conditional_fieldsets
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Force update financial totals after model save
        obj.update_financial_totals()
    
    def save_formset(self, request, form, formset, change):
        """Save formset and update totals after room/transportation entries are saved"""
        super().save_formset(request, form, formset, change)
        # Update financial totals after any inline forms (room entries, transportation) are saved
        if formset.model in [RoomEntry, Transportation]:
            form.instance.update_financial_totals()

# Import configuration admin classes
from .configuration_admin import DynamicModelAdmin, DynamicFieldAdmin, DynamicModelMigrationAdmin

# @admin.register(DynamicFieldValue)  # Removed from admin panel - use Configuration dashboard instead
class DynamicFieldValueAdmin(admin.ModelAdmin):
    list_display = ['field', 'content_type', 'object_id', 'get_value_display', 'created_at']
    list_filter = ['field__field_type', 'content_type', 'created_at']
    search_fields = ['field__name', 'field__display_name', 'value_text']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['field']
    
    def get_value_display(self, obj):
        """Display the field value in a readable format"""
        value = obj.get_value()
        if value is None:
            return "None"
        elif isinstance(value, str) and len(value) > 50:
            return f"{value[:47]}..."
        else:
            return str(value)
    get_value_display.short_description = "Value"