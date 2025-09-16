# Admin package initialization
# Import all admin classes to ensure registration

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db import models
from django.http import HttpResponse
import csv
from requests.models import (
    Request, CancelledRequest, RoomEntry, Transportation, EventAgenda, SeriesGroupEntry, SeriesRoomEntry,
    RoomType, RoomOccupancy, CancellationReason, SystemFieldRequirement, SystemFormLayout,
    RequestFieldRequirement, RequestFormLayout, DynamicModel, DynamicField, DynamicModelMigration, DynamicFieldValue
)
from hotel_sales.admin.mixins import ConfigEnforcedAdminMixin

def sanitize_csv_value(value):
    """Sanitize CSV values to prevent CSV injection attacks"""
    if value is None:
        return ""
    
    str_value = str(value)
    # If value starts with formula characters, prefix with single quote
    if str_value and str_value[0] in ['=', '+', '-', '@', '\t']:
        return "'" + str_value
    return str_value

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
    fields = ['vehicle_type', 'number_of_pax', 'cost_per_way', 'timing', 'notes']
    verbose_name = "Transportation Entry"
    verbose_name_plural = "Transportation Arrangements"
    can_delete = True
    
    def get_extra(self, request, obj=None, **kwargs):
        """Show 1 extra form for new requests, 0 for existing ones"""
        if obj and obj.pk:
            return 0
        return 1

class EventAgendaInline(admin.TabularInline):
    model = EventAgenda
    extra = 0
    fields = [
        'event_date', 'start_time', 'end_time', 
        'coffee_break_time', 'lunch_time', 'dinner_time',
        'rate_per_person', 'total_persons', 'rental_fees_per_day',
        'packages', 'agenda_details'
    ]
    verbose_name = "Event Agenda Entry"
    verbose_name_plural = "Event Agenda & Costs"
    can_delete = True
    
    def get_extra(self, request, obj=None, **kwargs):
        """Show 1 extra form for new event requests, 0 for existing ones"""
        if obj and obj.pk:
            return 0
        return 1

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
    fields = ['arrival_date', 'departure_date', 'nights', 'arrival_time', 'departure_time', 'group_size', 'special_notes']
    readonly_fields = ['nights']
    verbose_name = "Series Group Entry"
    verbose_name_plural = "Series Group Schedule & Arrivals"
    can_delete = True
    
    def get_extra(self, request, obj=None, **kwargs):
        """Show 1 extra form for new series group requests, 0 for existing ones"""
        if obj and obj.pk:
            return 0
        return 1

@admin.register(Request)
class RequestAdmin(ConfigEnforcedAdminMixin, admin.ModelAdmin):
    list_display = ['confirmation_number', 'account', 'request_type', 'meal_plan', 'status', 'check_in_date', 'check_out_date', 'nights', 'total_rooms', 'total_room_nights', 'total_cost', 'created_at']
    list_filter = ['request_type', 'meal_plan', 'status', 'created_at', 'check_in_date']
    search_fields = ['confirmation_number', 'account__name', 'account__contact_person']
    readonly_fields = ['nights', 'total_cost', 'total_rooms', 'total_room_nights', 'created_at', 'updated_at', 
                      'get_adr_display', 'get_room_total_display', 'get_transportation_total_display', 
                      'get_event_total_display', 'get_statistics_summary']
    inlines = [RoomEntryInline, TransportationInline, EventAgendaInline, SeriesGroupEntryInline]
    ordering = ['-created_at']
    actions = ['export_selected_requests']
    
    # Force admin widgets for date/time fields to ensure calendar pickers display
    formfield_overrides = {
        models.DateField: {'widget': admin.widgets.AdminDateWidget},
        models.DateTimeField: {'widget': admin.widgets.AdminSplitDateTime},
        models.TimeField: {'widget': admin.widgets.AdminTimeWidget},
    }
    
    def get_config_form_type(self, obj=None):
        """Get the form type for configuration lookup based on request type"""
        if obj and hasattr(obj, 'request_type'):
            return f"requests.{obj.request_type}"
        # Default for new objects
        return "requests.Group Accommodation"
    
    def get_original_fieldsets(self, request, obj=None):
        """
        Enhanced fieldsets with improved organization for Phase 1B.
        Room configuration is placed prominently above status fields.
        """
        # Enhanced fieldsets with better organization
        fieldsets = [
            ('Basic Information', {
                'fields': ('request_type', 'account', 'confirmation_number', 'request_received_date'),
                'description': 'Core request information and identification'
            }),
            ('Accommodation Details & Room Configuration', {
                'fields': ('check_in_date', 'check_out_date', 'nights', 'meal_plan'),
                'description': 'Configure accommodation dates and meal plan. Add specific room types and occupancy in the "Room Configuration" section below. Room costs will be automatically calculated and included in totals.'
            }),
            ('Transportation & Event Details', {
                'fields': (),  # Transportation handled via inline forms
                'description': 'Transportation arrangements are managed in the "Transportation entries" section below. Event details can be configured in the "Event agenda entries" section for event-type requests.',
                'classes': ('collapse',)
            }),
            ('Status & Payment Tracking', {
                'fields': ('status', 'offer_acceptance_deadline', 'deposit_deadline', 'full_payment_deadline'),
                'description': 'Request status and payment deadlines. Cancellation fields will appear automatically when status is set to "Cancelled".'
            }),
            ('Financial Summary (Auto-Calculated)', {
                'fields': ('total_cost', 'total_rooms', 'total_room_nights', 'deposit_amount', 'paid_amount'),
                'description': 'Automatically calculated totals from room entries, transportation, and event costs. ADR (Average Daily Rate) is calculated as total_cost ÷ total_room_nights.',
                'classes': ('wide',)
            }),
            ('Advanced Statistics & Analytics', {
                'fields': ('get_adr_display', 'get_room_total_display', 'get_transportation_total_display', 'get_event_total_display', 'get_statistics_summary'),
                'description': 'Detailed cost breakdowns and performance analytics for this request.',
                'classes': ('collapse', 'wide')
            }),
            ('Documents & Notes', {
                'fields': ('agreement_file', 'notes'),
                'description': 'Upload agreements and add detailed notes',
                'classes': ('collapse',)
            }),
            ('System Information', {
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
        """Save formset and update totals after room/transportation/event entries are saved"""
        super().save_formset(request, form, formset, change)
        # Update financial totals after any inline forms (room entries, transportation, events) are saved
        if formset.model in [RoomEntry, Transportation, EventAgenda]:
            form.instance.update_financial_totals()
    
    # Statistics display methods for Phase 1C advanced features
    def get_adr_display(self, obj):
        """Display ADR (Average Daily Rate) calculation"""
        if obj:
            adr = obj.get_adr()
            return f"${adr:.2f} per room night"
        return "No ADR calculated"
    get_adr_display.short_description = "ADR (Average Daily Rate)"
    
    def get_room_total_display(self, obj):
        """Display room cost breakdown"""
        if obj:
            room_total = obj.get_room_total()
            return f"${room_total:.2f} from {obj.total_rooms} rooms"
        return "$0.00"
    get_room_total_display.short_description = "Room Costs"
    
    def get_transportation_total_display(self, obj):
        """Display transportation cost breakdown"""
        if obj:
            transport_total = obj.get_transportation_total()
            transport_count = obj.transportation_entries.count()
            return f"${transport_total:.2f} from {transport_count} arrangements"
        return "$0.00"
    get_transportation_total_display.short_description = "Transportation Costs"
    
    def get_event_total_display(self, obj):
        """Display event cost breakdown"""
        if obj:
            event_entries = obj.event_agenda_entries.all()
            if event_entries:
                total_cost = sum(entry.get_total_event_cost() for entry in event_entries)
                return f"${total_cost:.2f} from {event_entries.count()} events"
        return "No event costs"
    get_event_total_display.short_description = "Event Costs"
    
    def get_statistics_summary(self, obj):
        """Display comprehensive statistics summary"""
        if obj:
            summary = []
            if obj.total_room_nights > 0:
                summary.append(f"Room nights: {obj.total_room_nights}")
            # Remove incorrect occupancy calculation - requires inventory data not available
            if obj.total_cost > 0 and obj.total_room_nights > 0:
                adr = obj.get_adr()
                summary.append(f"ADR: ${adr:.2f}")
            
            payment_status = "Unpaid"
            if obj.paid_amount > 0:
                payment_pct = (obj.paid_amount / obj.total_cost) * 100 if obj.total_cost > 0 else 0
                if payment_pct >= 100:
                    payment_status = "Fully Paid"
                else:
                    payment_status = f"Partially Paid ({payment_pct:.1f}%)"
            summary.append(f"Payment: {payment_status}")
            
            return " | ".join(summary)
        return "No statistics available"
    get_statistics_summary.short_description = "Statistics Summary"
    
    def export_selected_requests(self, request, queryset):
        """Export selected requests to CSV file with security safeguards"""
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="requests_export.csv"'
        
        writer = csv.writer(response)
        # Write CSV header with key request information
        writer.writerow([
            'Confirmation Number', 'Account Name', 'Request Type', 'Status', 'Check-In Date', 
            'Check-Out Date', 'Nights', 'Meal Plan', 'Total Rooms', 'Total Cost', 
            'Paid Amount', 'Deposit Amount', 'Created Date', 'Notes'
        ])
        
        # Write request data with sanitization and proper display values
        for req in queryset.order_by('confirmation_number'):
            writer.writerow([
                sanitize_csv_value(req.confirmation_number),
                sanitize_csv_value(req.account.name if req.account else 'No Account'),
                sanitize_csv_value(req.get_request_type_display()),
                sanitize_csv_value(req.get_status_display()),
                sanitize_csv_value(req.check_in_date.strftime('%Y-%m-%d') if req.check_in_date else ''),
                sanitize_csv_value(req.check_out_date.strftime('%Y-%m-%d') if req.check_out_date else ''),
                sanitize_csv_value(req.nights),
                sanitize_csv_value(req.get_meal_plan_display()),
                sanitize_csv_value(req.total_rooms),
                sanitize_csv_value(f"{req.total_cost:.2f}" if req.total_cost else '0.00'),
                sanitize_csv_value(f"{req.paid_amount:.2f}" if req.paid_amount else '0.00'),
                sanitize_csv_value(f"{req.deposit_amount:.2f}" if req.deposit_amount else '0.00'),
                sanitize_csv_value(req.created_at.strftime('%Y-%m-%d %H:%M') if req.created_at else ''),
                sanitize_csv_value(req.notes)
            ])
        
        return response
    export_selected_requests.short_description = "Export selected requests to CSV"

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