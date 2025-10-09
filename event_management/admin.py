from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.http import HttpResponse
from decimal import Decimal
import csv
from .models import MeetingRoom, EventBooking, EventMetrics
from requests.models import EventAgenda


class EventAgendaInline(admin.TabularInline):
    """Custom inline for EventAgenda through Request relationship"""
    model = EventAgenda
    extra = 1
    fields = [
        'event_date', 'event_name', 'meeting_room_name', 'style', 'start_time', 'end_time', 
        'coffee_break_time', 'lunch_time', 'dinner_time',
        'rate_per_person', 'total_persons', 'rental_fees_per_day',
        'packages', 'agenda_details'
    ]
    verbose_name = "Event Day"
    verbose_name_plural = "Event Days"
    can_delete = True
    
    def get_queryset(self, request):
        """Filter EventAgenda entries for this EventBooking's Request"""
        qs = super().get_queryset(request)
        if hasattr(self, 'instance') and self.instance and self.instance.request:
            return qs.filter(request=self.instance.request)
        return qs.none()
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Customize the form field"""
        if db_field.name == "request":
            # Set the request to the EventBooking's request
            if hasattr(self, 'instance') and self.instance and self.instance.request:
                kwargs["initial"] = self.instance.request
                kwargs["disabled"] = True
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(MeetingRoom)
class MeetingRoomAdmin(admin.ModelAdmin):
    list_display = ['name', 'display_name', 'room_type', 'capacity', 'is_combined', 'is_active', 'created_at']
    list_filter = ['room_type', 'is_combined', 'is_active', 'created_at']
    search_fields = ['name', 'display_name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['room_type', 'name']
    
    fieldsets = [
        ('Room Information', {
            'fields': ('name', 'display_name', 'room_type', 'capacity', 'description')
        }),
        ('Configuration', {
            'fields': ('is_combined', 'combined_group', 'is_active')
        }),
        ('System Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    ]


@admin.register(EventBooking)
class EventBookingAdmin(admin.ModelAdmin):
    list_display = ['event_name', 'account', 'event_date', 'start_time', 'end_time', 
                   'get_room_names', 'total_persons', 'rental_fees_per_day', 'status', 'created_at']
    list_filter = ['status', 'event_date', 'meeting_rooms', 'account', 'created_at']
    search_fields = ['event_name', 'account__name', 'notes']
    readonly_fields = ['created_at', 'updated_at', 'get_duration_display', 'get_conflicts_display', 'get_related_agenda_display', 'get_total_cost_display', 'get_total_revenue_display']
    filter_horizontal = ['meeting_rooms']
    date_hierarchy = 'event_date'
    ordering = ['-event_date', '-start_time']
    actions = ['export_event_bookings']
    # inlines = [EventAgendaInline]  # Removed due to ForeignKey issue
    
    fieldsets = [
        ('Event Information', {
            'fields': ('event_name', 'account', 'event_date', 'start_time', 'end_time')
        }),
        ('Deadlines & Important Dates', {
            'fields': ('request_received_date', 'offer_acceptance_deadline', 'deposit_deadline', 'full_payment_deadline')
        }),
        ('Room Selection', {
            'fields': ('meeting_rooms',)
        }),
        ('Event Details', {
            'fields': ('style', 'coffee_break_time', 'lunch_time', 'dinner_time')
        }),
        ('Financial Information', {
            'fields': ('rental_fees_per_day', 'rate_per_person', 'total_persons', 'packages')
        }),
        ('Financial Summary (Auto-Calculated)', {
            'fields': ('get_total_cost_display', 'get_total_revenue_display'),
            'classes': ('wide',)
        }),
        ('Status & Integration', {
            'fields': ('status', 'request', 'notes')
        }),
        ('Related Event Days', {
            'fields': ('get_related_agenda_display',),
            'classes': ('wide',)
        }),
        ('System Information', {
            'fields': ('created_by', 'created_at', 'updated_at', 'get_duration_display', 'get_conflicts_display'),
            'classes': ('collapse',)
        })
    ]
    
    def get_room_names(self, obj):
        """Display room names in list view"""
        return obj.get_room_names()
    get_room_names.short_description = "Rooms"
    
    def get_total_persons(self, obj):
        """Display total persons"""
        return obj.total_persons
    get_total_persons.short_description = "Persons"
    
    def get_rental_fees(self, obj):
        """Display rental fees"""
        return f"${obj.rental_fees_per_day}"
    get_rental_fees.short_description = "Rental Fees"
    
    def get_related_agenda_display(self, obj):
        """Display related EventAgenda entries"""
        if not obj.request:
            return "No linked request"
        
        agendas = EventAgenda.objects.filter(request=obj.request).order_by('event_date', 'start_time')
        if not agendas.exists():
            return "No event agenda entries found"
        
        agenda_html = []
        for agenda in agendas:
            agenda_html.append(f"""
                <div class="border p-2 mb-2 rounded">
                    <strong>{agenda.event_date}</strong> - {agenda.start_time} to {agenda.end_time}<br>
                    <small>Room: {agenda.meeting_room_name} | Style: {agenda.style} | Persons: {agenda.total_persons}</small>
                </div>
            """)
        
        return mark_safe("".join(agenda_html))
    get_related_agenda_display.short_description = "Related Event Days"
    
    def get_total_cost_display(self, obj):
        """Display total cost calculation"""
        if not obj.request:
            return "No linked request"
        
        # Get all related EventAgenda entries
        agendas = EventAgenda.objects.filter(request=obj.request)
        total_cost = Decimal('0.00')
        
        for agenda in agendas:
            # Calculate cost per day: (rate_per_person * total_persons) + rental_fees_per_day
            daily_cost = (agenda.rate_per_person * agenda.total_persons) + agenda.rental_fees_per_day
            total_cost += daily_cost
        
        return f"${total_cost:,.2f}"
    get_total_cost_display.short_description = "Total Event Cost"
    
    def get_total_revenue_display(self, obj):
        """Display total revenue calculation"""
        if not obj.request:
            return "No linked request"
        
        # Get all related EventAgenda entries
        agendas = EventAgenda.objects.filter(request=obj.request)
        total_revenue = Decimal('0.00')
        
        for agenda in agendas:
            # Revenue per day: rate_per_person * total_persons + rental_fees_per_day
            daily_revenue = (agenda.rate_per_person * agenda.total_persons) + agenda.rental_fees_per_day
            total_revenue += daily_revenue
        
        return f"${total_revenue:,.2f}"
    get_total_revenue_display.short_description = "Total Event Revenue"
    
    def get_duration_display(self, obj):
        """Display event duration"""
        duration = obj.get_duration()
        return f"{duration:.1f} hours"
    get_duration_display.short_description = "Duration"
    
    def get_conflicts_display(self, obj):
        """Display any conflicts for this booking"""
        if not obj.pk:
            return "Save to check for conflicts"
        
        conflicts = EventBooking.get_conflicts(
            obj.event_date, obj.start_time, obj.end_time,
            obj.meeting_rooms.values_list('id', flat=True),
            exclude_id=obj.pk
        )
        
        if conflicts.exists():
            conflict_list = []
            for conflict in conflicts:
                conflict_list.append(
                    f'<a href="{reverse("admin:event_management_eventbooking_change", args=[conflict.pk])}">'
                    f'{conflict.event_name} ({conflict.start_time}-{conflict.end_time})</a>'
                )
            return mark_safe("⚠️ Conflicts: " + ", ".join(conflict_list))
        else:
            return "✅ No conflicts"
    get_conflicts_display.short_description = "Conflicts"
    
    def save_model(self, request, obj, form, change):
        """Set created_by user when saving"""
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def export_event_bookings(self, request, queryset):
        """Export selected event bookings to CSV"""
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="event_bookings_export.csv"'
        
        writer = csv.writer(response)
        
        # CSV Header
        writer.writerow([
            'Event Name', 'Account Name', 'Account Type', 'Contact Person',
            'Event Date', 'Start Time', 'End Time', 'Duration (hours)',
            'Meeting Rooms', 'Setup Style', 'Status',
            'Number of Guests', 'Package Plan', 
            'Rate Per Person', 'Rental Fees', 'Total Cost',
            'Request Received Date', 'Offer Acceptance Deadline', 
            'Deposit Deadline', 'Full Payment Deadline',
            'Coffee Break Time', 'Lunch Time', 'Dinner Time',
            'Linked Request ID', 'Created By', 'Created Date', 'Notes'
        ])
        
        # Helper function to sanitize CSV values
        def sanitize_csv_value(value):
            """Prevent CSV injection attacks"""
            if value is None:
                return ''
            str_value = str(value)
            if str_value and str_value[0] in ['=', '+', '-', '@', '\t']:
                return "'" + str_value
            return str_value
        
        # Export data
        total_bookings = 0
        total_revenue = 0
        total_attendees = 0
        status_counts = {}
        
        for booking in queryset.select_related('account', 'request', 'created_by').prefetch_related('meeting_rooms').order_by('event_date', 'start_time'):
            # Calculate total cost
            total_cost = (booking.rate_per_person * booking.total_persons) + booking.rental_fees_per_day
            
            # Get meeting room names
            room_names = ', '.join([room.display_name for room in booking.meeting_rooms.all()])
            
            # Get duration
            duration = booking.get_duration()
            
            # Get package display
            package_display = booking.get_packages_display() if booking.packages else ''
            
            writer.writerow([
                sanitize_csv_value(booking.event_name),
                sanitize_csv_value(booking.account.name if booking.account else 'No Account'),
                sanitize_csv_value(booking.account.account_type if booking.account else ''),
                sanitize_csv_value(booking.account.contact_person if booking.account else ''),
                sanitize_csv_value(booking.event_date.strftime('%Y-%m-%d') if booking.event_date else ''),
                sanitize_csv_value(booking.start_time.strftime('%H:%M') if booking.start_time else ''),
                sanitize_csv_value(booking.end_time.strftime('%H:%M') if booking.end_time else ''),
                sanitize_csv_value(f'{duration:.2f}'),
                sanitize_csv_value(room_names),
                sanitize_csv_value(booking.style),
                sanitize_csv_value(booking.status),
                sanitize_csv_value(booking.total_persons),
                sanitize_csv_value(package_display),
                sanitize_csv_value(f'{booking.rate_per_person:.2f}'),
                sanitize_csv_value(f'{booking.rental_fees_per_day:.2f}'),
                sanitize_csv_value(f'{total_cost:.2f}'),
                sanitize_csv_value(booking.request_received_date.strftime('%Y-%m-%d') if booking.request_received_date else ''),
                sanitize_csv_value(booking.offer_acceptance_deadline.strftime('%Y-%m-%d') if booking.offer_acceptance_deadline else ''),
                sanitize_csv_value(booking.deposit_deadline.strftime('%Y-%m-%d') if booking.deposit_deadline else ''),
                sanitize_csv_value(booking.full_payment_deadline.strftime('%Y-%m-%d') if booking.full_payment_deadline else ''),
                sanitize_csv_value(booking.coffee_break_time.strftime('%H:%M') if booking.coffee_break_time else ''),
                sanitize_csv_value(booking.lunch_time.strftime('%H:%M') if booking.lunch_time else ''),
                sanitize_csv_value(booking.dinner_time.strftime('%H:%M') if booking.dinner_time else ''),
                sanitize_csv_value(booking.request.confirmation_number if booking.request else ''),
                sanitize_csv_value(booking.created_by.username if booking.created_by else ''),
                sanitize_csv_value(booking.created_at.strftime('%Y-%m-%d %H:%M') if booking.created_at else ''),
                sanitize_csv_value(booking.notes),
            ])
            
            # Calculate totals
            total_bookings += 1
            total_revenue += float(total_cost)
            total_attendees += booking.total_persons
            status_counts[booking.status] = status_counts.get(booking.status, 0) + 1
        
        # Add summary rows
        writer.writerow([])
        writer.writerow(['SUMMARY'])
        writer.writerow(['Total Event Bookings:', total_bookings])
        writer.writerow(['Total Revenue:', f'SAR {total_revenue:,.2f}'])
        writer.writerow(['Total Attendees:', total_attendees])
        writer.writerow(['Average Attendees per Event:', f'{total_attendees / total_bookings:.1f}' if total_bookings > 0 else '0'])
        writer.writerow(['Average Revenue per Event:', f'SAR {total_revenue / total_bookings:,.2f}' if total_bookings > 0 else 'SAR 0.00'])
        writer.writerow([])
        writer.writerow(['STATUS BREAKDOWN'])
        for status, count in sorted(status_counts.items()):
            writer.writerow([status, count, f'{(count / total_bookings * 100):.1f}%' if total_bookings > 0 else '0%'])
        
        return response
    export_event_bookings.short_description = "Export selected event bookings to CSV"
    
    def get_queryset(self, request):
        """Optimize queryset for list view"""
        return super().get_queryset(request).select_related('account', 'request', 'created_by').prefetch_related('meeting_rooms')


@admin.register(EventMetrics)
class EventMetricsAdmin(admin.ModelAdmin):
    list_display = ['date', 'total_events', 'total_revenue', 'total_attendees', 'room_utilization', 'updated_at']
    list_filter = ['date', 'updated_at']
    search_fields = ['date']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-date']
    
    fieldsets = [
        ('Date & Overview', {
            'fields': ('date', 'total_events', 'total_revenue', 'total_attendees', 'room_utilization')
        }),
        ('Room-Specific Events', {
            'fields': ('ikma_events', 'hegra_events', 'dadan_events', 'aljadida_events', 
                      'board_room_events', 'al_badia_events', 'la_palma_events')
        }),
        ('System Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    ]
    
    def has_add_permission(self, request):
        """Prevent manual addition of metrics"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Prevent manual editing of metrics"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of metrics"""
        return False