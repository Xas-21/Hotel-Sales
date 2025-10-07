from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from decimal import Decimal
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