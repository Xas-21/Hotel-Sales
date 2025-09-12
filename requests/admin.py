from django.contrib import admin
from .models import Request, CancelledRequest, RoomEntry, Transportation, EventAgenda, SeriesGroupEntry, SeriesRoomEntry

class RoomEntryInline(admin.TabularInline):
    model = RoomEntry
    extra = 1
    fields = ['category', 'occupancy', 'quantity', 'rate_per_night']
    verbose_name = "Room Entry (part of Accommodation Details)"
    verbose_name_plural = "Room Entries (part of Accommodation Details)"

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
    fields = ['category', 'occupancy', 'quantity', 'rate_per_night']
    verbose_name = "Room Configuration"
    verbose_name_plural = "Room Configuration for this Date"
    can_delete = True

class SeriesGroupEntryInline(admin.TabularInline):
    model = SeriesGroupEntry
    extra = 0
    fields = ['arrival_date', 'departure_date', 'arrival_time', 'departure_time', 'group_size', 'special_notes']
    readonly_fields = ['nights']

@admin.register(Request)
class RequestAdmin(admin.ModelAdmin):
    list_display = ['confirmation_number', 'account', 'request_type', 'meal_plan', 'status', 'check_in_date', 'check_out_date', 'nights', 'total_rooms', 'total_room_nights', 'total_cost', 'created_at']
    list_filter = ['request_type', 'meal_plan', 'status', 'created_at', 'check_in_date']
    search_fields = ['confirmation_number', 'account__name', 'account__contact_person']
    readonly_fields = ['nights', 'total_cost', 'total_rooms', 'total_room_nights', 'created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('request_type', 'account', 'confirmation_number', 'request_received_date')
        }),
        ('Accommodation Details & Room Configuration', {
            'fields': ('check_in_date', 'check_out_date', 'nights', 'meal_plan'),
            'description': 'Add room entries below in the "Room entries" section - room costs will be automatically included in total cost calculation.'
        }),
        ('Status & Payment', {
            'fields': ('status', 'cancellation_reason', 'offer_acceptance_deadline', 'deposit_deadline', 'full_payment_deadline')
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
    )
    inlines = [RoomEntryInline, TransportationInline, EventAgendaInline, SeriesGroupEntryInline]
    ordering = ['-created_at']
    
    def save_model(self, request_obj, obj, form, change):
        super().save_model(request_obj, obj, form, change)
        # Force update financial totals after model save
        obj.update_financial_totals()
    
    def save_formset(self, request, form, formset, change):
        """Save formset and update totals after room/transportation entries are saved"""
        super().save_formset(request, form, formset, change)
        # Update financial totals after any inline forms (room entries, transportation) are saved
        if formset.model in [RoomEntry, Transportation]:
            form.instance.update_financial_totals()

@admin.register(SeriesGroupEntry)
class SeriesGroupEntryAdmin(admin.ModelAdmin):
    list_display = ['request', 'arrival_date', 'departure_date', 'arrival_time', 'departure_time', 'nights', 'group_size']
    list_filter = ['arrival_date', 'request__request_type']
    search_fields = ['request__confirmation_number', 'request__account__name']
    readonly_fields = ['nights']
    ordering = ['arrival_date']
    inlines = [SeriesRoomEntryInline]
    
    fieldsets = (
        ('Date & Time Details', {
            'fields': ('arrival_date', 'departure_date', 'nights', 'arrival_time', 'departure_time')
        }),
        ('Group Information', {
            'fields': ('group_size', 'special_notes')
        }),
    )
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Update parent request totals when series entry is saved
        if obj.request:
            obj.request.update_financial_totals()
    
    def save_formset(self, request, form, formset, change):
        """Save formset and update totals after room entries are saved"""
        super().save_formset(request, form, formset, change)
        # Update financial totals after series room entries are saved
        if formset.model == SeriesRoomEntry:
            form.instance.request.update_financial_totals()

class CancelledRequestAdmin(admin.ModelAdmin):
    """Admin view for cancelled requests only"""
    list_display = ['confirmation_number', 'account', 'request_type', 'check_in_date', 'check_out_date', 'total_cost', 'cancellation_reason', 'created_at']
    list_filter = ['request_type', 'created_at', 'check_in_date']
    search_fields = ['confirmation_number', 'account__name', 'account__contact_person', 'cancellation_reason']
    readonly_fields = ['nights', 'total_cost', 'total_rooms', 'total_room_nights', 'created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('request_type', 'account', 'confirmation_number', 'request_received_date')
        }),
        ('Accommodation Details', {
            'fields': ('check_in_date', 'check_out_date', 'nights', 'meal_plan'),
            'classes': ('collapse',)
        }),
        ('Cancellation Details', {
            'fields': ('status', 'cancellation_reason'),
            'description': 'Status is locked to Cancelled for this view'
        }),
        ('Financial Impact', {
            'fields': ('total_cost', 'total_rooms', 'total_room_nights', 'deposit_amount', 'paid_amount'),
            'description': 'Shows the financial impact of this cancellation'
        }),
        ('File & Notes', {
            'fields': ('agreement_file', 'notes'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    ordering = ['-created_at']
    
    def get_queryset(self, request):
        """Only show cancelled requests"""
        return super().get_queryset(request).filter(status='Cancelled')
    
    def has_add_permission(self, request):
        """Prevent adding new records through this view"""
        return False

# Register the cancelled requests proxy model
admin.site.register(CancelledRequest, CancelledRequestAdmin)

@admin.register(SeriesRoomEntry)
class SeriesRoomEntryAdmin(admin.ModelAdmin):
    list_display = ['series_entry', 'category', 'occupancy', 'quantity', 'rate_per_night']
    list_filter = ['category', 'occupancy']
    ordering = ['series_entry__arrival_date']
