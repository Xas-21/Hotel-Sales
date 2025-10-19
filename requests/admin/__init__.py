# Admin package initialization
# Import all admin classes to ensure registration

from django.contrib import admin
from django.contrib.admin import widgets as admin_widgets
from django import forms
from django.utils.html import format_html
from django.urls import reverse, path
from django.db import models
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.contrib import messages
import csv
from hotel_sales.currency_utils import format_currency
from requests.models import (
    Request, CancelledRequest, RoomEntry, Transportation, EventAgenda, SeriesGroupEntry, SeriesRoomEntry,
    RoomType, RoomOccupancy, CancellationReason, SystemFieldRequirement, SystemFormLayout,
    RequestFieldRequirement, RequestFormLayout, DynamicModel, DynamicField, DynamicModelMigration, DynamicFieldValue,
    AccommodationRequest, EventOnlyRequest, EventWithRoomsRequest, SeriesGroupRequest
)
from hotel_sales.admin.mixins import ConfigEnforcedAdminMixin
from django.contrib.admin import SimpleListFilter
from django.utils.translation import gettext_lazy as _


class StatusFilter(SimpleListFilter):
    """Custom status filter to ensure proper filtering"""
    title = _('Status')
    parameter_name = 'status'
    
    def lookups(self, request, model_admin):
        """Return the status choices for the filter"""
        return Request.STATUS_CHOICES
    
    def queryset(self, request, queryset):
        """Filter the queryset based on the selected status"""
        if self.value():
            return queryset.filter(status=self.value())
        return queryset


def sanitize_csv_value(value):
    """Sanitize CSV values to prevent CSV injection attacks"""
    if value is None:
        return ""
    
    str_value = str(value)
    # If value starts with formula characters, prefix with single quote
    if str_value and str_value[0] in ['=', '+', '-', '@', '\t']:
        return "'" + str_value
    return str_value


def write_enhanced_request_export_rows(writer, req, row_type, **kwargs):
    """
    Helper function to write enhanced export rows for different request types.
    
    Args:
        writer: CSV writer object
        req: Request object
        row_type: Type of row ('accommodation', 'event', 'series_entry')
        **kwargs: Additional data for the specific row type
    """
    # Common fields for all rows
    common_fields = [
        sanitize_csv_value(req.confirmation_number),
        sanitize_csv_value(req.account.name if req.account else 'No Account'),
        sanitize_csv_value(req.account.account_type if req.account else ''),
        sanitize_csv_value(req.account.contact_person if req.account else ''),
        sanitize_csv_value(req.get_request_type_display()),
        sanitize_csv_value(req.get_status_display()),
        sanitize_csv_value(req.request_received_date.strftime('%Y-%m-%d') if req.request_received_date else ''),
    ]
    
    if row_type == 'accommodation':
        # Accommodation row: check-in/check-out dates
        accommodation_fields = [
            sanitize_csv_value('Accommodation'),
            sanitize_csv_value(req.check_in_date.strftime('%Y-%m-%d') if req.check_in_date else ''),
            sanitize_csv_value(req.check_out_date.strftime('%Y-%m-%d') if req.check_out_date else ''),
            sanitize_csv_value(req.nights),
            sanitize_csv_value(req.get_meal_plan_display()),
            sanitize_csv_value(req.total_rooms),
            sanitize_csv_value(req.total_room_nights),
            sanitize_csv_value(f"{req.get_room_total():.2f}" if req.get_room_total() else '0.00'),
            sanitize_csv_value(f"{req.get_display_paid_amount():.2f}" if req.get_display_paid_amount() else '0.00'),
            sanitize_csv_value(f"{req.deposit_amount:.2f}" if req.deposit_amount else '0.00'),
            sanitize_csv_value(req.offer_acceptance_deadline.strftime('%Y-%m-%d') if req.offer_acceptance_deadline else ''),
            sanitize_csv_value(req.deposit_deadline.strftime('%Y-%m-%d') if req.deposit_deadline else ''),
            sanitize_csv_value(req.full_payment_deadline.strftime('%Y-%m-%d') if req.full_payment_deadline else ''),
            sanitize_csv_value(f"{req.get_adr():.2f}" if req.get_adr() else '0.00'),
            sanitize_csv_value(req.created_at.strftime('%Y-%m-%d %H:%M') if req.created_at else ''),
            sanitize_csv_value(req.updated_at.strftime('%Y-%m-%d %H:%M') if req.updated_at else ''),
            sanitize_csv_value(req.notes),
            # Event-specific fields (empty for accommodation)
            sanitize_csv_value(''),  # number_of_guests
            sanitize_csv_value(''),  # package_plan
            sanitize_csv_value(''),  # meeting_room_name
            sanitize_csv_value(''),  # event_start_date
            sanitize_csv_value(''),  # event_end_date
        ]
        writer.writerow(common_fields + accommodation_fields)
        
    elif row_type == 'event':
        # Event row: enhanced event details
        event_agenda = kwargs.get('event_agenda')
        
        # Calculate number of days for the event
        event_days = 1  # Default to 1 day if no end date
        if event_agenda and event_agenda.event_date:
            event_days = 1  # Events are typically single day
        
        event_fields = [
            sanitize_csv_value('Event'),
            sanitize_csv_value(event_agenda.event_date.strftime('%Y-%m-%d') if event_agenda and event_agenda.event_date else ''),
            sanitize_csv_value(event_agenda.event_date.strftime('%Y-%m-%d') if event_agenda and event_agenda.event_date else ''),  # Same date for start/end
            sanitize_csv_value(event_days),  # Number of days
            sanitize_csv_value(''),  # meal plan (not applicable for events)
            sanitize_csv_value(''),  # total rooms (not applicable for events)
            sanitize_csv_value(''),  # total room nights (not applicable for events)
            sanitize_csv_value(f"{event_agenda.rental_fees_per_day + (event_agenda.rate_per_person * event_agenda.total_persons):.2f}" if event_agenda else '0.00'),
            sanitize_csv_value(f"{req.get_display_paid_amount():.2f}" if req.get_display_paid_amount() else '0.00'),
            sanitize_csv_value(f"{req.deposit_amount:.2f}" if req.deposit_amount else '0.00'),
            sanitize_csv_value(req.offer_acceptance_deadline.strftime('%Y-%m-%d') if req.offer_acceptance_deadline else ''),
            sanitize_csv_value(req.deposit_deadline.strftime('%Y-%m-%d') if req.deposit_deadline else ''),
            sanitize_csv_value(req.full_payment_deadline.strftime('%Y-%m-%d') if req.full_payment_deadline else ''),
            sanitize_csv_value('0.00'),  # ADR (not applicable for events)
            sanitize_csv_value(req.created_at.strftime('%Y-%m-%d %H:%M') if req.created_at else ''),
            sanitize_csv_value(req.updated_at.strftime('%Y-%m-%d %H:%M') if req.updated_at else ''),
            sanitize_csv_value(req.notes),
            # Enhanced event-specific fields
            sanitize_csv_value(event_agenda.total_persons if event_agenda else ''),
            sanitize_csv_value(event_agenda.get_packages_display() if event_agenda and event_agenda.packages else ''),
            sanitize_csv_value(event_agenda.meeting_room_name if event_agenda else ''),
            sanitize_csv_value(event_agenda.event_date.strftime('%Y-%m-%d') if event_agenda and event_agenda.event_date else ''),
            sanitize_csv_value(event_agenda.event_date.strftime('%Y-%m-%d') if event_agenda and event_agenda.event_date else ''),  # Same date for single-day events
        ]
        writer.writerow(common_fields + event_fields)
        
    elif row_type == 'series_entry':
        # Series Group entry row: arrival/departure dates
        series_entry = kwargs.get('series_entry')
        series_fields = [
            sanitize_csv_value(f'Series Entry {kwargs.get("entry_number", 1)}'),
            sanitize_csv_value(series_entry.arrival_date.strftime('%Y-%m-%d') if series_entry and series_entry.arrival_date else ''),
            sanitize_csv_value(series_entry.departure_date.strftime('%Y-%m-%d') if series_entry and series_entry.departure_date else ''),
            sanitize_csv_value(series_entry.nights if series_entry else ''),
            sanitize_csv_value(''),  # meal plan (not applicable for series entries)
            sanitize_csv_value(series_entry.number_of_rooms if series_entry else ''),
            sanitize_csv_value(series_entry.number_of_rooms * series_entry.nights if series_entry else ''),
            sanitize_csv_value(f"{series_entry.get_total_cost():.2f}" if series_entry else '0.00'),
            sanitize_csv_value(f"{req.get_display_paid_amount():.2f}" if req.get_display_paid_amount() else '0.00'),
            sanitize_csv_value(f"{req.deposit_amount:.2f}" if req.deposit_amount else '0.00'),
            sanitize_csv_value(req.offer_acceptance_deadline.strftime('%Y-%m-%d') if req.offer_acceptance_deadline else ''),
            sanitize_csv_value(req.deposit_deadline.strftime('%Y-%m-%d') if req.deposit_deadline else ''),
            sanitize_csv_value(req.full_payment_deadline.strftime('%Y-%m-%d') if req.full_payment_deadline else ''),
            sanitize_csv_value(f"{req.get_adr():.2f}" if req.get_adr() else '0.00'),
            sanitize_csv_value(req.created_at.strftime('%Y-%m-%d %H:%M') if req.created_at else ''),
            sanitize_csv_value(req.updated_at.strftime('%Y-%m-%d %H:%M') if req.updated_at else ''),
            sanitize_csv_value(req.notes),
            # Event-specific fields (empty for series entries)
            sanitize_csv_value(''),  # number_of_guests
            sanitize_csv_value(''),  # package_plan
            sanitize_csv_value(''),  # meeting_room_name
            sanitize_csv_value(''),  # event_start_date
            sanitize_csv_value(''),  # event_end_date
        ]
        writer.writerow(common_fields + series_fields)


class RoomEntryInline(admin.TabularInline):
    model = RoomEntry
    extra = 1
    fields = ['room_type', 'occupancy_type', 'quantity', 'rate_per_night']
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
        'event_date', 'event_name', 'meeting_room_name', 'style', 'start_time', 'end_time', 
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
    fields = ['room_type', 'occupancy_type', 'quantity', 'rate_per_night']
    verbose_name = "Room Configuration"
    verbose_name_plural = "Room Configuration for this Date"
    can_delete = True
    
    def get_queryset(self, request):
        """Optimize foreign key queries"""
        return super().get_queryset(request).select_related('room_type', 'occupancy_type')

class SeriesGroupEntryInline(admin.TabularInline):
    model = SeriesGroupEntry
    extra = 0
    fields = ['arrival_date', 'departure_date', 'nights', 'room_type', 'occupancy_type', 'number_of_rooms', 'rate_per_night']
    readonly_fields = ['nights']
    verbose_name = "Series Group Entry"
    verbose_name_plural = "Series Group Details"
    can_delete = True
    
    def get_extra(self, request, obj=None, **kwargs):
        """Show 1 extra form for new series group requests, 0 for existing ones"""
        if obj and obj.pk:
            return 0
        return 1

# Custom form to exclude 'Cancelled' from status choices
class RequestAdminForm(forms.ModelForm):
    class Meta:
        model = Request
        fields = '__all__'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Use DISPLAY_STATUS_CHOICES for status field (excludes 'Cancelled')
        if 'status' in self.fields:
            self.fields['status'].choices = Request.DISPLAY_STATUS_CHOICES

# Base admin class for shared functionality
class BaseRequestAdmin(ConfigEnforcedAdminMixin, admin.ModelAdmin):
    form = RequestAdminForm
    change_form_template = 'admin/requests/change_form.html'
    list_display = ['confirmation_number', 'account', 'request_type', 'meal_plan', 'status', 'check_in_date', 'check_out_date', 'nights', 'total_rooms', 'total_room_nights', 'total_cost', 'created_at']
    list_filter = ['request_type', 'meal_plan', StatusFilter, 'created_at', 'check_in_date']
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
    
    def get_fieldsets(self, request, obj=None):
        """Override to ensure Financial Summary section is always shown"""
        # Always use original fieldsets to ensure Financial Summary section is visible
        return self.get_original_fieldsets(request, obj)
    
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
                'fields': ('agreement_file', 'invoice_1', 'invoice_2', 'invoice_3', 'notes'),
                'description': 'Upload agreements, invoices and add detailed notes',
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
        # Update financial totals after any inline forms (room entries, transportation, events, series groups) are saved
        if formset.model in [RoomEntry, Transportation, EventAgenda, SeriesGroupEntry, SeriesRoomEntry]:
            form.instance.update_financial_totals()
    
    # Statistics display methods for Phase 1C advanced features
    def get_adr_display(self, obj):
        """Display ADR (Average Daily Rate) calculation"""
        if obj:
            adr = obj.get_adr()
            return f"{format_currency(adr)} per room night"
        return "No ADR calculated"
    get_adr_display.short_description = "ADR (Average Daily Rate)"
    
    def get_room_total_display(self, obj):
        """Display room cost breakdown"""
        if obj:
            room_total = obj.get_room_total()
            return f"{format_currency(room_total)} from {obj.total_rooms} rooms"
        return format_currency(0)
    get_room_total_display.short_description = "Room Costs"
    
    def get_transportation_total_display(self, obj):
        """Display transportation cost breakdown"""
        if obj:
            transport_total = obj.get_transportation_total()
            transport_count = obj.transportation_entries.count()
            return f"{format_currency(transport_total)} from {transport_count} arrangements"
        return format_currency(0)
    get_transportation_total_display.short_description = "Transportation Costs"
    
    def get_event_total_display(self, obj):
        """Display event cost breakdown"""
        if obj:
            event_entries = obj.event_agendas.all()
            if event_entries:
                total_cost = sum(entry.get_total_event_cost() for entry in event_entries)
                return f"{format_currency(total_cost)} from {event_entries.count()} events"
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
                summary.append(f"ADR: {format_currency(adr)}")
            
            payment_status = "Unpaid"
            display_paid_amount = obj.get_display_paid_amount()
            if display_paid_amount and display_paid_amount > 0:
                payment_pct = (display_paid_amount / obj.total_cost) * 100 if obj.total_cost > 0 else 0
                if payment_pct >= 100:
                    payment_status = "Fully Paid"
                else:
                    payment_status = f"Partially Paid ({payment_pct:.1f}%)"
            summary.append(f"Payment: {payment_status}")
            
            return " | ".join(summary)
        return "No statistics available"
    get_statistics_summary.short_description = "Statistics Summary"
    
    def export_selected_requests(self, request, queryset):
        """Export selected requests to CSV file with security safeguards and comprehensive details"""
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="requests_export.csv"'
        
        writer = csv.writer(response)
        # Write CSV header with comprehensive request information
        writer.writerow([
            'Confirmation Number', 'Account Name', 'Account Type', 'Contact Person', 'Request Type', 'Status', 
            'Request Received Date', 'Row Type', 'Start Date/Time', 'End Date/Time', 'Nights/Days', 'Meal Plan', 
            'Total Rooms', 'Total Room Nights', 'Total Cost', 'Paid Amount', 'Deposit Amount', 
            'Offer Acceptance Deadline', 'Deposit Deadline', 'Full Payment Deadline',
            'ADR (Average Daily Rate)', 'Created Date', 'Updated Date', 'Notes',
            'Number of Guests', 'Package Plan', 'Meeting Room Name', 'Event Start Date', 'Event End Date'
        ])
        
        total_requests = 0
        total_revenue = 0
        total_rooms = 0
        total_room_nights = 0
        total_paid = 0
        total_deposit = 0
        status_counts = {}
        
        # Write enhanced request data with multiple rows per request type
        for req in queryset.select_related('account').prefetch_related('event_agendas', 'series_entries').order_by('confirmation_number'):
            adr = req.get_adr()
            paid_amount = req.get_display_paid_amount()
            status = req.get_status_display()
            
            # Handle different request types with multiple rows
            if req.request_type == 'Series Group':
                # Series Group: One row per SeriesGroupEntry
                for i, series_entry in enumerate(req.series_entries.all(), 1):
                    write_enhanced_request_export_rows(
                        writer, req, 'series_entry', 
                        series_entry=series_entry, 
                        entry_number=i
                    )
                    
            elif req.request_type == 'Event without Rooms':
                # Event Only: One row per event agenda, or create a default event row if none exist
                event_agendas = req.event_agendas.all()
                if event_agendas.exists():
                    for event_agenda in event_agendas:
                        write_enhanced_request_export_rows(
                            writer, req, 'event', 
                            event_agenda=event_agenda
                        )
                else:
                    # Create a default event agenda object for Event Only requests without agendas
                    # This ensures Event Only requests always show as "Event" row type with proper structure
                    from decimal import Decimal
                    class DefaultEventAgenda:
                        def __init__(self, request):
                            self.event_date = request.request_received_date  # Use request received date as fallback
                            self.start_time = None
                            self.end_time = None
                            self.total_persons = 0
                            self.packages = ''
                            self.meeting_room_name = ''
                            self.rental_fees_per_day = Decimal('0.00')
                            self.rate_per_person = Decimal('0.00')
                        
                        def get_packages_display(self):
                            return ''
                    
                    default_agenda = DefaultEventAgenda(req)
                    write_enhanced_request_export_rows(
                        writer, req, 'event', 
                        event_agenda=default_agenda
                    )
                
            elif req.request_type == 'Event with Rooms':
                # Event with Rooms: First row for accommodation, then one row per event agenda
                # Row 1: Accommodation details
                write_enhanced_request_export_rows(writer, req, 'accommodation')
                
                # Row 2+: Event details (one row per event agenda)
                event_agendas = req.event_agendas.all()
                if event_agendas.exists():
                    for event_agenda in event_agendas:
                        write_enhanced_request_export_rows(
                            writer, req, 'event', 
                            event_agenda=event_agenda
                        )
                else:
                    # Fallback if no event agendas
                    write_enhanced_request_export_rows(
                        writer, req, 'event', 
                        event_agenda=None
                    )
                
            else:
                # Regular accommodation requests: One row
                write_enhanced_request_export_rows(writer, req, 'accommodation')
            
            # Calculate totals (count each request only once)
            total_requests += 1
            total_revenue += float(req.total_cost or 0)
            total_rooms += req.total_rooms or 0
            total_room_nights += req.total_room_nights or 0
            total_paid += float(paid_amount or 0)
            total_deposit += float(req.deposit_amount or 0)
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Calculate ADR (room costs only, excluding event costs)
        total_room_costs = sum(float(req.get_room_total() or 0) for req in queryset)
        average_adr = (total_room_costs / total_room_nights) if total_room_nights > 0 else 0
        
        # Add comprehensive summary section
        writer.writerow([])
        writer.writerow(['=' * 60])
        writer.writerow(['REQUESTS EXPORT SUMMARY'])
        writer.writerow(['=' * 60])
        writer.writerow([])
        writer.writerow(['REQUEST STATISTICS:'])
        writer.writerow(['Total Requests:', total_requests])
        writer.writerow([])
        writer.writerow(['Requests by Status:'])
        for status, count in sorted(status_counts.items()):
            writer.writerow([f'  {status}:', count])
        writer.writerow([])
        writer.writerow(['FINANCIAL SUMMARY:'])
        writer.writerow(['Total Revenue:', format_currency(total_revenue, request=request, convert_from='SAR')])
        writer.writerow(['Total Paid Amount:', format_currency(total_paid, request=request, convert_from='SAR')])
        writer.writerow(['Total Deposit Amount:', format_currency(total_deposit, request=request, convert_from='SAR')])
        writer.writerow(['Outstanding Balance:', format_currency(total_revenue - total_paid, request=request, convert_from='SAR')])
        writer.writerow([])
        writer.writerow(['ROOM STATISTICS:'])
        writer.writerow(['Total Rooms Booked:', f"{total_rooms:,}"])
        writer.writerow(['Total Room Nights:', f"{total_room_nights:,}"])
        writer.writerow(['Average Daily Rate (ADR):', format_currency(average_adr, request=request, convert_from='SAR')])
        writer.writerow([])
        from datetime import datetime
        writer.writerow(['Export Date:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
        
        return response
    export_selected_requests.short_description = "Export selected requests to CSV"
    
    def get_urls(self):
        """Add custom URL for cancellation"""
        urls = super().get_urls()
        custom_urls = [
            path('<path:object_id>/cancel/', 
                 self.admin_site.admin_view(self.cancel_request_view), 
                 name='requests_request_cancel'),
        ]
        return custom_urls + urls
    
    def cancel_request_view(self, request, object_id):
        """Handle request cancellation with popup form"""
        obj = get_object_or_404(self.model, pk=object_id)
        
        if request.method == 'POST':
            # Get cancellation reason from form
            cancellation_reason_fixed_id = request.POST.get('cancellation_reason_fixed')
            cancellation_reason_text = request.POST.get('cancellation_reason', '')
            
            # Update the request status to Cancelled
            obj.status = 'Cancelled'
            
            # Set cancellation reason
            if cancellation_reason_fixed_id:
                from requests.models import CancellationReason
                obj.cancellation_reason_fixed_id = cancellation_reason_fixed_id
            obj.cancellation_reason = cancellation_reason_text
            
            obj.save()
            
            messages.success(request, f'Request {obj.confirmation_number} has been cancelled.')
            
            # Return JSON response for AJAX requests
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True})
            
            # Redirect back to change page
            return redirect('admin:requests_request_change', obj.pk)
        
        # GET request - show cancellation form
        from requests.models import CancellationReason
        cancellation_reasons = CancellationReason.objects.filter(active=True).order_by('sort_order')
        
        context = {
            'title': f'Cancel Request: {obj.confirmation_number}',
            'object': obj,
            'cancellation_reasons': cancellation_reasons,
            'opts': self.model._meta,
            'has_view_permission': self.has_view_permission(request, obj),
            'has_change_permission': self.has_change_permission(request, obj),
        }
        
        return TemplateResponse(request, 'admin/requests/request_cancel.html', context)
    
    def change_view(self, request, object_id, form_url='', extra_context=None):
        """Override to add cancel button to change form"""
        extra_context = extra_context or {}
        obj = self.get_object(request, object_id)
        
        # Add flag to show cancel button if request is not already cancelled
        if obj and obj.status != 'Cancelled':
            extra_context['show_cancel_button'] = True
            extra_context['cancel_url'] = reverse('admin:requests_request_cancel', args=[obj.pk])
        
        return super().change_view(request, object_id, form_url, extra_context)


# Specialized admin classes for proxy models
@admin.register(AccommodationRequest)
class AccommodationRequestAdmin(BaseRequestAdmin):
    """Admin for Accommodation-only requests - Room + Transport + Documents & Notes + Calculations"""
    inlines = [RoomEntryInline, TransportationInline]
    
    # Complete admin configuration matching BaseRequestAdmin
    list_display = ['confirmation_number', 'account', 'meal_plan', 'status', 'check_in_date', 'check_out_date', 'nights', 'total_rooms', 'total_room_nights', 'total_cost', 'created_at']
    list_filter = ['meal_plan', StatusFilter, 'created_at', 'check_in_date']
    search_fields = ['confirmation_number', 'account__name', 'account__contact_person']
    readonly_fields = ['nights', 'total_cost', 'total_rooms', 'total_room_nights', 'created_at', 'updated_at', 
                      'get_adr_display', 'get_room_total_display', 'get_transportation_total_display', 
                      'get_event_total_display', 'get_statistics_summary']
    ordering = ['-created_at']
    actions = ['export_selected_requests']
    
    # Display methods for statistics - copied from BaseRequestAdmin
    def get_adr_display(self, obj):
        """Display ADR (Average Daily Rate) calculation"""
        if obj:
            adr = obj.get_adr()
            return f"{format_currency(adr)} per room night"
        return "No ADR calculated"
    get_adr_display.short_description = "ADR (Average Daily Rate)"
    
    def get_room_total_display(self, obj):
        """Display room cost breakdown"""
        if obj:
            room_total = obj.get_room_total()
            return f"{format_currency(room_total)} from {obj.total_rooms} rooms"
        return format_currency(0)
    get_room_total_display.short_description = "Room Costs"
    
    def get_transportation_total_display(self, obj):
        """Display transportation cost breakdown"""
        if obj:
            transport_total = obj.get_transportation_total()
            transport_count = obj.transportation_entries.count()
            return f"{format_currency(transport_total)} from {transport_count} arrangements"
        return format_currency(0)
    get_transportation_total_display.short_description = "Transportation Costs"
    
    def get_event_total_display(self, obj):
        """Display event cost breakdown"""
        if obj:
            event_entries = obj.event_agendas.all()
            if event_entries:
                total_cost = sum(entry.get_total_event_cost() for entry in event_entries)
                return f"{format_currency(total_cost)} from {event_entries.count()} events"
        return "No event costs"
    get_event_total_display.short_description = "Event Costs"
    
    def get_statistics_summary(self, obj):
        """Display comprehensive statistics summary"""
        if obj:
            summary = []
            if obj.total_room_nights > 0:
                summary.append(f"Room nights: {obj.total_room_nights}")
            if obj.total_cost > 0 and obj.total_room_nights > 0:
                adr = obj.get_adr()
                summary.append(f"ADR: {format_currency(adr)}")
            
            payment_status = "Unpaid"
            display_paid_amount = obj.get_display_paid_amount()
            if display_paid_amount and display_paid_amount > 0:
                payment_pct = (display_paid_amount / obj.total_cost) * 100 if obj.total_cost > 0 else 0
                if payment_pct >= 100:
                    payment_status = "Fully Paid"
                else:
                    payment_status = f"Partially Paid ({payment_pct:.1f}%)"
            summary.append(f"Payment: {payment_status}")
            
            return " | ".join(summary)
        return "No statistics available"
    get_statistics_summary.short_description = "Statistics Summary"
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Force update financial totals after model save
        obj.update_financial_totals()
    
    def save_formset(self, request, form, formset, change):
        """Save formset and update totals after room/transportation entries are saved"""
        from requests.models import RoomEntry, Transportation, EventAgenda, SeriesGroupEntry, SeriesRoomEntry
        super().save_formset(request, form, formset, change)
        # Update financial totals after any inline forms are saved
        if formset.model in [RoomEntry, Transportation, EventAgenda, SeriesGroupEntry, SeriesRoomEntry]:
            form.instance.update_financial_totals()
    
    def export_selected_requests(self, request, queryset):
        """Export selected accommodation requests to CSV file with security safeguards and comprehensive details"""
        import csv
        from django.http import HttpResponse
        # sanitize_csv_value is defined in this same file
        
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="accommodation_requests_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Confirmation Number', 'Account Name', 'Account Type', 'Contact Person', 'Request Type', 'Status', 
            'Request Received Date', 'Row Type', 'Start Date/Time', 'End Date/Time', 'Nights/Days', 'Meal Plan', 
            'Total Rooms', 'Total Room Nights', 'Total Cost', 'Paid Amount', 'Deposit Amount', 
            'Offer Acceptance Deadline', 'Deposit Deadline', 'Full Payment Deadline',
            'ADR (Average Daily Rate)', 'Created Date', 'Updated Date', 'Notes',
            'Number of Guests', 'Package Plan', 'Meeting Room Name', 'Event Start Date', 'Event End Date'
        ])
        
        total_requests = 0
        total_revenue = 0
        total_rooms = 0
        total_room_nights = 0
        total_paid = 0
        total_deposit = 0
        status_counts = {}
        
        # Write enhanced accommodation request data
        for req in queryset.order_by('confirmation_number'):
            adr = req.get_adr()
            paid_amount = req.get_display_paid_amount()
            status = req.get_status_display()
            
            # For accommodation requests, just write one row
            write_enhanced_request_export_rows(writer, req, 'accommodation')
            
            # Calculate totals
            total_requests += 1
            total_revenue += float(req.total_cost or 0)
            total_rooms += req.total_rooms or 0
            total_room_nights += req.total_room_nights or 0
            total_paid += float(paid_amount or 0)
            total_deposit += float(req.deposit_amount or 0)
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Calculate ADR (room costs only, excluding event costs)
        total_room_costs = sum(float(req.get_room_total() or 0) for req in queryset)
        average_adr = (total_room_costs / total_room_nights) if total_room_nights > 0 else 0
        
        # Add comprehensive summary section
        writer.writerow([])
        writer.writerow(['=' * 60])
        writer.writerow(['ACCOMMODATION REQUESTS EXPORT SUMMARY'])
        writer.writerow(['=' * 60])
        writer.writerow([])
        writer.writerow(['REQUEST STATISTICS:'])
        writer.writerow(['Total Requests:', total_requests])
        writer.writerow([])
        writer.writerow(['Requests by Status:'])
        for status, count in sorted(status_counts.items()):
            writer.writerow([f'  {status}:', count])
        writer.writerow([])
        writer.writerow(['FINANCIAL SUMMARY:'])
        writer.writerow(['Total Revenue:', format_currency(total_revenue, request=request, convert_from='SAR')])
        writer.writerow(['Total Paid Amount:', format_currency(total_paid, request=request, convert_from='SAR')])
        writer.writerow(['Total Deposit Amount:', format_currency(total_deposit, request=request, convert_from='SAR')])
        writer.writerow(['Outstanding Balance:', format_currency(total_revenue - total_paid, request=request, convert_from='SAR')])
        writer.writerow([])
        writer.writerow(['ROOM STATISTICS:'])
        writer.writerow(['Total Rooms Booked:', f"{total_rooms:,}"])
        writer.writerow(['Total Room Nights:', f"{total_room_nights:,}"])
        writer.writerow(['Average Daily Rate (ADR):', format_currency(average_adr, request=request, convert_from='SAR')])
        writer.writerow([])
        from datetime import datetime
        writer.writerow(['Export Date:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
        
        return response
    export_selected_requests.short_description = "Export selected accommodation requests to CSV"

    
    def get_fieldsets(self, request, obj=None):
        """Complete fieldsets for accommodation requests - hide request_type"""
        fieldsets = [
            ('Basic Information', {
                'fields': ('account', 'confirmation_number', 'request_received_date'),
                'description': 'Core request information and identification'
            }),
            ('Accommodation Details & Room Configuration', {
                'fields': ('check_in_date', 'check_out_date', 'nights', 'meal_plan'),
                'description': 'Configure accommodation dates and meal plan. Add specific room types and occupancy in the "Room Configuration" section below. Room costs will be automatically calculated and included in totals.'
            }),
            ('Transportation & Event Details', {
                'fields': (),  # Transportation handled via inline forms
                'description': 'Transportation arrangements are managed in the "Transportation entries" section below.',
                'classes': ('collapse',)
            }),
            ('Status & Payment Tracking', {
                'fields': ('status', 'offer_acceptance_deadline', 'deposit_deadline', 'full_payment_deadline'),
                'description': 'Request status and payment deadlines. Cancellation fields will appear automatically when status is set to "Cancelled".'
            }),
            ('Financial Summary (Auto-Calculated)', {
                'fields': ('total_cost', 'total_rooms', 'total_room_nights', 'deposit_amount', 'paid_amount'),
                'description': 'Automatically calculated totals from room entries and transportation costs. ADR (Average Daily Rate) is calculated as total_cost ÷ total_room_nights.',
                'classes': ('wide',)
            }),
            ('Advanced Statistics & Analytics', {
                'fields': ('get_adr_display', 'get_room_total_display', 'get_transportation_total_display', 'get_event_total_display', 'get_statistics_summary'),
                'description': 'Detailed cost breakdowns and performance analytics for this request.',
                'classes': ('collapse', 'wide')
            }),
            ('Documents & Notes', {
                'fields': ('agreement_file', 'invoice_1', 'invoice_2', 'invoice_3', 'notes'),
                'description': 'Upload agreements, invoices and add detailed notes',
                'classes': ('collapse',)
            }),
            ('System Information', {
                'fields': ('created_at', 'updated_at'),
                'classes': ('collapse',)
            })
        ]
        
        # Add cancellation fields if status is 'Cancelled'
        if obj and obj.status == 'Cancelled':
            fieldsets.append(('Cancellation Details', {
                'fields': ('cancellation_reason_fixed', 'cancellation_reason'),
                'description': 'Cancellation information for this request'
            }))
        
        return fieldsets


@admin.register(EventOnlyRequest)  
class EventOnlyRequestAdmin(BaseRequestAdmin):
    """Admin for Event-only requests - Events + Transport + Documents & Notes + Calculations"""
    inlines = [EventAgendaInline, TransportationInline]
    
    # Complete admin configuration matching AccommodationRequestAdmin
    list_display = ['confirmation_number', 'account', 'status', 'request_received_date', 'total_cost', 'created_at']
    list_filter = [StatusFilter, 'request_received_date', 'created_at']
    search_fields = ['confirmation_number', 'account__name', 'account__contact_person']
    readonly_fields = ['total_cost', 'created_at', 'updated_at', 
                      'get_adr_display', 'get_room_total_display', 'get_transportation_total_display', 
                      'get_event_total_display', 'get_statistics_summary']
    ordering = ['-created_at']
    actions = ['export_selected_requests']

    
    # Display methods for statistics - copied from AccommodationRequestAdmin
    def get_adr_display(self, obj):
        """Display ADR (Average Daily Rate) calculation"""
        if obj:
            adr = obj.get_adr()
            return f"{format_currency(adr)} per room night"
        return "No ADR calculated"
    get_adr_display.short_description = "ADR (Average Daily Rate)"
    
    def get_room_total_display(self, obj):
        """Display room cost breakdown"""
        if obj:
            room_total = obj.get_room_total()
            return f"{format_currency(room_total)} from {obj.total_rooms} rooms"
        return format_currency(0)
    get_room_total_display.short_description = "Room Costs"
    
    def get_transportation_total_display(self, obj):
        """Display transportation cost breakdown"""
        if obj:
            transport_total = obj.get_transportation_total()
            transport_count = obj.transportation_entries.count()
            return f"{format_currency(transport_total)} from {transport_count} arrangements"
        return format_currency(0)
    get_transportation_total_display.short_description = "Transportation Costs"
    
    def get_event_total_display(self, obj):
        """Display event cost breakdown"""
        if obj:
            event_entries = obj.event_agendas.all()
            if event_entries:
                total_cost = sum(entry.get_total_event_cost() for entry in event_entries)
                return f"{format_currency(total_cost)} from {event_entries.count()} events"
        return "No event costs"
    get_event_total_display.short_description = "Event Costs"
    
    def get_statistics_summary(self, obj):
        """Display comprehensive statistics summary"""
        if obj:
            summary = []
            if obj.total_room_nights > 0:
                summary.append(f"Room nights: {obj.total_room_nights}")
            if obj.total_cost > 0 and obj.total_room_nights > 0:
                adr = obj.get_adr()
                summary.append(f"ADR: {format_currency(adr)}")
            
            payment_status = "Unpaid"
            display_paid_amount = obj.get_display_paid_amount()
            if display_paid_amount and display_paid_amount > 0:
                payment_pct = (display_paid_amount / obj.total_cost) * 100 if obj.total_cost > 0 else 0
                if payment_pct >= 100:
                    payment_status = "Fully Paid"
                else:
                    payment_status = f"Partially Paid ({payment_pct:.1f}%)"
            summary.append(f"Payment: {payment_status}")
            
            return " | ".join(summary)
        return "No statistics available"
    get_statistics_summary.short_description = "Statistics Summary"
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Force update financial totals after model save
        obj.update_financial_totals()
    
    def save_formset(self, request, form, formset, change):
        """Save formset and update totals after event/transportation entries are saved"""
        super().save_formset(request, form, formset, change)
        # Update financial totals after any inline forms are saved
        if formset.model in [RoomEntry, Transportation, EventAgenda, SeriesGroupEntry, SeriesRoomEntry]:
            form.instance.update_financial_totals()
    
    def export_selected_requests(self, request, queryset):
        """Export selected requests to CSV file with security safeguards"""
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="event_only_requests_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Confirmation Number', 'Account Name', 'Account Type', 'Contact Person', 'Request Type', 'Status', 
            'Request Received Date', 'Row Type', 'Start Date/Time', 'End Date/Time', 'Nights/Days', 'Meal Plan', 
            'Total Rooms', 'Total Room Nights', 'Total Cost', 'Paid Amount', 'Deposit Amount', 
            'Offer Acceptance Deadline', 'Deposit Deadline', 'Full Payment Deadline',
            'ADR (Average Daily Rate)', 'Created Date', 'Updated Date', 'Notes',
            'Number of Guests', 'Package Plan', 'Meeting Room Name', 'Event Start Date', 'Event End Date'
        ])
        
        # Write enhanced event-only request data
        for req in queryset.select_related('account').prefetch_related('event_agendas').order_by('confirmation_number'):
            # Event Only: One row per event agenda (can be multiple event agendas)
            event_agendas = req.event_agendas.all()
            if event_agendas.exists():
                for event_agenda in event_agendas:
                    write_enhanced_request_export_rows(
                        writer, req, 'event', 
                        event_agenda=event_agenda
                    )
            else:
                # Create a default event agenda object for Event Only requests without agendas
                from decimal import Decimal
                class DefaultEventAgenda:
                    def __init__(self, request):
                        self.event_date = request.request_received_date  # Use request received date as fallback
                        self.start_time = None
                        self.end_time = None
                        self.total_persons = 0
                        self.packages = ''
                        self.meeting_room_name = ''
                        self.rental_fees_per_day = Decimal('0.00')
                        self.rate_per_person = Decimal('0.00')
                    
                    def get_packages_display(self):
                        return ''
                
                default_agenda = DefaultEventAgenda(req)
                write_enhanced_request_export_rows(
                    writer, req, 'event', 
                    event_agenda=default_agenda
                )
        
        return response
    export_selected_requests.short_description = "Export selected event-only requests to CSV"

    
    def get_fieldsets(self, request, obj=None):
        """Complete fieldsets for event-only requests - hide request_type"""
        fieldsets = [
            ('Basic Information', {
                'fields': ('account', 'confirmation_number', 'request_received_date'),
                'description': 'Core request information and identification'
            }),
            ('Event & Transportation Details', {
                'fields': (),  # Event and transportation handled via inline forms
                'description': 'Event details are configured in the "Event agenda entries" section below. Transportation arrangements are managed in the "Transportation entries" section.',
                'classes': ('collapse',)
            }),
            ('Status & Payment Tracking', {
                'fields': ('status', 'offer_acceptance_deadline', 'deposit_deadline', 'full_payment_deadline'),
                'description': 'Request status and payment deadlines. Cancellation fields will appear automatically when status is set to "Cancelled".'
            }),
            ('Financial Summary (Auto-Calculated)', {
                'fields': ('total_cost', 'deposit_amount', 'paid_amount'),
                'description': 'Automatically calculated totals from event entries and transportation costs.',
                'classes': ('wide',)
            }),
            ('Advanced Statistics & Analytics', {
                'fields': ('get_adr_display', 'get_room_total_display', 'get_transportation_total_display', 'get_event_total_display', 'get_statistics_summary'),
                'description': 'Detailed cost breakdowns and performance analytics for this request.',
                'classes': ('collapse', 'wide')
            }),
            ('Documents & Notes', {
                'fields': ('agreement_file', 'invoice_1', 'invoice_2', 'invoice_3', 'notes'),
                'description': 'Upload agreements, invoices and add detailed notes',
                'classes': ('collapse',)
            }),
            ('System Information', {
                'fields': ('created_at', 'updated_at'),
                'classes': ('collapse',)
            })
        ]
        
        # Add cancellation fields if status is 'Cancelled'
        if obj and obj.status == 'Cancelled':
            fieldsets.append(('Cancellation Details', {
                'fields': ('cancellation_reason_fixed', 'cancellation_reason'),
                'description': 'Cancellation information for this request'
            }))
        
        return fieldsets


@admin.register(EventWithRoomsRequest)
class EventWithRoomsRequestAdmin(BaseRequestAdmin):
    """Admin for Events with accommodation - Events + Room + Transport + Documents & Notes + Calculations"""
    inlines = [EventAgendaInline, RoomEntryInline, TransportationInline]
    
    # Complete admin configuration matching AccommodationRequestAdmin
    list_display = ['confirmation_number', 'account', 'meal_plan', 'status', 'check_in_date', 'check_out_date', 'nights', 'total_rooms', 'total_room_nights', 'total_cost', 'created_at']
    list_filter = ['meal_plan', StatusFilter, 'created_at', 'check_in_date']
    search_fields = ['confirmation_number', 'account__name', 'account__contact_person']
    readonly_fields = ['nights', 'total_cost', 'total_rooms', 'total_room_nights', 'created_at', 'updated_at', 
                      'get_adr_display', 'get_room_total_display', 'get_transportation_total_display', 
                      'get_event_total_display', 'get_statistics_summary']
    ordering = ['-created_at']
    actions = ['export_selected_requests']
    
    # Display methods for statistics - copied from AccommodationRequestAdmin
    def get_adr_display(self, obj):
        """Display ADR (Average Daily Rate) calculation"""
        if obj:
            adr = obj.get_adr()
            return f"{format_currency(adr)} per room night"
        return "No ADR calculated"
    get_adr_display.short_description = "ADR (Average Daily Rate)"
    
    def get_room_total_display(self, obj):
        """Display room cost breakdown"""
        if obj:
            room_total = obj.get_room_total()
            return f"{format_currency(room_total)} from {obj.total_rooms} rooms"
        return format_currency(0)
    get_room_total_display.short_description = "Room Costs"
    
    def get_transportation_total_display(self, obj):
        """Display transportation cost breakdown"""
        if obj:
            transport_total = obj.get_transportation_total()
            transport_count = obj.transportation_entries.count()
            return f"{format_currency(transport_total)} from {transport_count} arrangements"
        return format_currency(0)
    get_transportation_total_display.short_description = "Transportation Costs"
    
    def get_event_total_display(self, obj):
        """Display event cost breakdown"""
        if obj:
            event_entries = obj.event_agendas.all()
            if event_entries:
                total_cost = sum(entry.get_total_event_cost() for entry in event_entries)
                return f"{format_currency(total_cost)} from {event_entries.count()} events"
        return "No event costs"
    get_event_total_display.short_description = "Event Costs"
    
    def get_statistics_summary(self, obj):
        """Display comprehensive statistics summary"""
        if obj:
            summary = []
            if obj.total_room_nights > 0:
                summary.append(f"Room nights: {obj.total_room_nights}")
            if obj.total_cost > 0 and obj.total_room_nights > 0:
                adr = obj.get_adr()
                summary.append(f"ADR: {format_currency(adr)}")
            
            payment_status = "Unpaid"
            display_paid_amount = obj.get_display_paid_amount()
            if display_paid_amount and display_paid_amount > 0:
                payment_pct = (display_paid_amount / obj.total_cost) * 100 if obj.total_cost > 0 else 0
                if payment_pct >= 100:
                    payment_status = "Fully Paid"
                else:
                    payment_status = f"Partially Paid ({payment_pct:.1f}%)"
            summary.append(f"Payment: {payment_status}")
            
            return " | ".join(summary)
        return "No statistics available"
    get_statistics_summary.short_description = "Statistics Summary"
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Force update financial totals after model save
        obj.update_financial_totals()
    
    def save_formset(self, request, form, formset, change):
        """Save formset and update totals after room/event/transportation entries are saved"""
        super().save_formset(request, form, formset, change)
        # Update financial totals after any inline forms are saved
        if formset.model in [RoomEntry, Transportation, EventAgenda, SeriesGroupEntry, SeriesRoomEntry]:
            form.instance.update_financial_totals()
    
    def export_selected_requests(self, request, queryset):
        """Export selected requests to CSV file with security safeguards"""
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="event_with_rooms_requests_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Confirmation Number', 'Account Name', 'Account Type', 'Contact Person', 'Request Type', 'Status', 
            'Request Received Date', 'Row Type', 'Start Date/Time', 'End Date/Time', 'Nights/Days', 'Meal Plan', 
            'Total Rooms', 'Total Room Nights', 'Total Cost', 'Paid Amount', 'Deposit Amount', 
            'Offer Acceptance Deadline', 'Deposit Deadline', 'Full Payment Deadline',
            'ADR (Average Daily Rate)', 'Created Date', 'Updated Date', 'Notes',
            'Number of Guests', 'Package Plan', 'Meeting Room Name', 'Event Start Date', 'Event End Date'
        ])
        
        # Write enhanced event-with-rooms request data
        for req in queryset.select_related('account').prefetch_related('event_agendas').order_by('confirmation_number'):
            # Event with Rooms: First row for accommodation, then one row per event agenda
            # Row 1: Accommodation details
            write_enhanced_request_export_rows(writer, req, 'accommodation')
            
            # Row 2+: Event details (one row per event agenda)
            event_agendas = req.event_agendas.all()
            if event_agendas.exists():
                for event_agenda in event_agendas:
                    write_enhanced_request_export_rows(
                        writer, req, 'event', 
                        event_agenda=event_agenda
                    )
            else:
                # If no event agendas exist, still write a row with empty event details
                write_enhanced_request_export_rows(
                    writer, req, 'event', 
                    event_agenda=None
                )
        
        return response
    export_selected_requests.short_description = "Export selected event-with-rooms requests to CSV"

    
    def get_fieldsets(self, request, obj=None):
        """Complete fieldsets for events with accommodation - hide request_type"""
        fieldsets = [
            ('Basic Information', {
                'fields': ('account', 'confirmation_number', 'request_received_date'),
                'description': 'Core request information and identification'
            }),
            ('Accommodation Details & Room Configuration', {
                'fields': ('check_in_date', 'check_out_date', 'nights', 'meal_plan'),
                'description': 'Configure accommodation dates and meal plan. Add specific room types and occupancy in the "Room Configuration" section below. Room costs will be automatically calculated and included in totals.'
            }),
            ('Event & Transportation Details', {
                'fields': (),  # Event and transportation handled via inline forms
                'description': 'Event details are configured in the "Event agenda entries" section below. Transportation arrangements are managed in the "Transportation entries" section.',
                'classes': ('collapse',)
            }),
            ('Status & Payment Tracking', {
                'fields': ('status', 'offer_acceptance_deadline', 'deposit_deadline', 'full_payment_deadline'),
                'description': 'Request status and payment deadlines. Cancellation fields will appear automatically when status is set to "Cancelled".'
            }),
            ('Financial Summary (Auto-Calculated)', {
                'fields': ('total_cost', 'total_rooms', 'total_room_nights', 'deposit_amount', 'paid_amount'),
                'description': 'Automatically calculated totals from room entries, event costs, and transportation costs. ADR (Average Daily Rate) is calculated as total_cost ÷ total_room_nights.',
                'classes': ('wide',)
            }),
            ('Advanced Statistics & Analytics', {
                'fields': ('get_adr_display', 'get_room_total_display', 'get_transportation_total_display', 'get_event_total_display', 'get_statistics_summary'),
                'description': 'Detailed cost breakdowns and performance analytics for this request.',
                'classes': ('collapse', 'wide')
            }),
            ('Documents & Notes', {
                'fields': ('agreement_file', 'invoice_1', 'invoice_2', 'invoice_3', 'notes'),
                'description': 'Upload agreements, invoices and add detailed notes',
                'classes': ('collapse',)
            }),
            ('System Information', {
                'fields': ('created_at', 'updated_at'),
                'classes': ('collapse',)
            })
        ]
        
        # Add cancellation fields if status is 'Cancelled'
        if obj and obj.status == 'Cancelled':
            fieldsets.append(('Cancellation Details', {
                'fields': ('cancellation_reason_fixed', 'cancellation_reason'),
                'description': 'Cancellation information for this request'
            }))
        
        return fieldsets


@admin.register(SeriesGroupRequest)
class SeriesGroupRequestAdmin(BaseRequestAdmin):
    """Admin for Series Group requests - Series Details + Transport + Documents & Notes + Calculations"""
    inlines = [SeriesGroupEntryInline, TransportationInline]
    
    # Complete admin configuration matching AccommodationRequestAdmin
    list_display = ['confirmation_number', 'account', 'status', 'request_received_date', 'total_rooms', 'total_room_nights', 'total_cost', 'created_at']
    list_filter = [StatusFilter, 'request_received_date', 'created_at']
    search_fields = ['confirmation_number', 'account__name', 'account__contact_person']
    readonly_fields = ['total_cost', 'total_rooms', 'total_room_nights', 'created_at', 'updated_at', 
                      'get_adr_display', 'get_room_total_display', 'get_transportation_total_display', 
                      'get_event_total_display', 'get_statistics_summary']
    ordering = ['-created_at']
    actions = ['export_selected_requests']

    
    # Display methods for statistics - copied from AccommodationRequestAdmin
    def get_adr_display(self, obj):
        """Display ADR (Average Daily Rate) calculation"""
        if obj:
            adr = obj.get_adr()
            return f"{format_currency(adr)} per room night"
        return "No ADR calculated"
    get_adr_display.short_description = "ADR (Average Daily Rate)"
    
    def get_room_total_display(self, obj):
        """Display room cost breakdown"""
        if obj:
            room_total = obj.get_room_total()
            return f"{format_currency(room_total)} from {obj.total_rooms} rooms"
        return format_currency(0)
    get_room_total_display.short_description = "Room Costs"
    
    def get_transportation_total_display(self, obj):
        """Display transportation cost breakdown"""
        if obj:
            transport_total = obj.get_transportation_total()
            transport_count = obj.transportation_entries.count()
            return f"{format_currency(transport_total)} from {transport_count} arrangements"
        return format_currency(0)
    get_transportation_total_display.short_description = "Transportation Costs"
    
    def get_event_total_display(self, obj):
        """Display event cost breakdown"""
        if obj:
            event_entries = obj.event_agendas.all()
            if event_entries:
                total_cost = sum(entry.get_total_event_cost() for entry in event_entries)
                return f"{format_currency(total_cost)} from {event_entries.count()} events"
        return "No event costs"
    get_event_total_display.short_description = "Event Costs"
    
    def get_statistics_summary(self, obj):
        """Display comprehensive statistics summary"""
        if obj:
            summary = []
            if obj.total_room_nights > 0:
                summary.append(f"Room nights: {obj.total_room_nights}")
            if obj.total_cost > 0 and obj.total_room_nights > 0:
                adr = obj.get_adr()
                summary.append(f"ADR: {format_currency(adr)}")
            
            payment_status = "Unpaid"
            display_paid_amount = obj.get_display_paid_amount()
            if display_paid_amount and display_paid_amount > 0:
                payment_pct = (display_paid_amount / obj.total_cost) * 100 if obj.total_cost > 0 else 0
                if payment_pct >= 100:
                    payment_status = "Fully Paid"
                else:
                    payment_status = f"Partially Paid ({payment_pct:.1f}%)"
            summary.append(f"Payment: {payment_status}")
            
            return " | ".join(summary)
        return "No statistics available"
    get_statistics_summary.short_description = "Statistics Summary"
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Force update financial totals after model save
        obj.update_financial_totals()
    
    def save_formset(self, request, form, formset, change):
        """Save formset and update totals after series group/transportation entries are saved"""
        super().save_formset(request, form, formset, change)
        # Update financial totals after any inline forms are saved
        if formset.model in [RoomEntry, Transportation, EventAgenda, SeriesGroupEntry, SeriesRoomEntry]:
            form.instance.update_financial_totals()
    
    def export_selected_requests(self, request, queryset):
        """Export selected requests to CSV file with security safeguards"""
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="series_group_requests_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Confirmation Number', 'Account Name', 'Account Type', 'Contact Person', 'Request Type', 'Status', 
            'Request Received Date', 'Row Type', 'Start Date/Time', 'End Date/Time', 'Nights/Days', 'Meal Plan', 
            'Total Rooms', 'Total Room Nights', 'Total Cost', 'Paid Amount', 'Deposit Amount', 
            'Offer Acceptance Deadline', 'Deposit Deadline', 'Full Payment Deadline',
            'ADR (Average Daily Rate)', 'Created Date', 'Updated Date', 'Notes',
            'Number of Guests', 'Package Plan', 'Meeting Room Name', 'Event Start Date', 'Event End Date'
        ])
        
        # Write enhanced series group request data
        for req in queryset.order_by('confirmation_number'):
            # Series Group: One row per SeriesGroupEntry
            for i, series_entry in enumerate(req.series_entries.all(), 1):
                write_enhanced_request_export_rows(
                    writer, req, 'series_entry', 
                    series_entry=series_entry, 
                    entry_number=i
                )
        
        return response
    export_selected_requests.short_description = "Export selected series group requests to CSV"

    
    def get_fieldsets(self, request, obj=None):
        """Complete fieldsets for series group requests - hide request_type"""
        fieldsets = [
            ('Basic Information', {
                'fields': ('account', 'confirmation_number', 'request_received_date'),
                'description': 'Core request information and identification'
            }),
            ('Series Group & Transportation Details', {
                'fields': (),  # Series group and transportation handled via inline forms
                'description': 'Series group details are configured in the "Series Group Details" section below. Transportation arrangements are managed in the "Transportation entries" section.',
                'classes': ('collapse',)
            }),
            ('Status & Payment Tracking', {
                'fields': ('status', 'offer_acceptance_deadline', 'deposit_deadline', 'full_payment_deadline'),
                'description': 'Request status and payment deadlines. Cancellation fields will appear automatically when status is set to "Cancelled".'
            }),
            ('Financial Summary (Auto-Calculated)', {
                'fields': ('total_cost', 'total_rooms', 'total_room_nights', 'deposit_amount', 'paid_amount'),
                'description': 'Automatically calculated totals from series group entries and transportation costs. ADR (Average Daily Rate) is calculated as total_cost ÷ total_room_nights.',
                'classes': ('wide',)
            }),
            ('Advanced Statistics & Analytics', {
                'fields': ('get_adr_display', 'get_room_total_display', 'get_transportation_total_display', 'get_event_total_display', 'get_statistics_summary'),
                'description': 'Detailed cost breakdowns and performance analytics for this request.',
                'classes': ('collapse', 'wide')
            }),
            ('Documents & Notes', {
                'fields': ('agreement_file', 'invoice_1', 'invoice_2', 'invoice_3', 'notes'),
                'description': 'Upload agreements, invoices and add detailed notes',
                'classes': ('collapse',)
            }),
            ('System Information', {
                'fields': ('created_at', 'updated_at'),
                'classes': ('collapse',)
            })
        ]
        
        # Add cancellation fields if status is 'Cancelled'
        if obj and obj.status == 'Cancelled':
            fieldsets.append(('Cancellation Details', {
                'fields': ('cancellation_reason_fixed', 'cancellation_reason'),
                'description': 'Cancellation information for this request'
            }))
        
        return fieldsets


# Keep original RequestAdmin for backward compatibility and unified view
@admin.register(Request)
class RequestAdmin(BaseRequestAdmin):
    """Original unified request admin (for backward compatibility)"""
    inlines = [RoomEntryInline, TransportationInline, EventAgendaInline, SeriesGroupEntryInline]


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