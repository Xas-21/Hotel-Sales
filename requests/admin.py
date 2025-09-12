from django.contrib import admin
from .models import Request, RoomEntry, Transportation, EventAgenda, SeriesGroupEntry, SeriesRoomEntry

class RoomEntryInline(admin.TabularInline):
    model = RoomEntry
    extra = 1
    fields = ['category', 'occupancy', 'quantity', 'rate_per_night']

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
        ('Accommodation Details', {
            'fields': ('check_in_date', 'check_out_date', 'nights', 'meal_plan'),
            'classes': ('collapse',)
        }),
        ('Status & Payment', {
            'fields': ('status', 'cancellation_reason', 'offer_acceptance_deadline', 'deposit_deadline', 'full_payment_deadline')
        }),
        ('Financial Tracking (Auto-Calculated)', {
            'fields': ('total_cost', 'total_rooms', 'total_room_nights', 'deposit_amount', 'paid_amount'),
            'description': 'Financial totals are automatically calculated from room entries and transportation.'
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
        obj.update_financial_totals()

@admin.register(SeriesGroupEntry)
class SeriesGroupEntryAdmin(admin.ModelAdmin):
    list_display = ['request', 'arrival_date', 'departure_date', 'arrival_time', 'departure_time', 'nights', 'group_size']
    list_filter = ['arrival_date', 'request__request_type']
    ordering = ['arrival_date']
    inlines = [SeriesRoomEntryInline]

@admin.register(SeriesRoomEntry)
class SeriesRoomEntryAdmin(admin.ModelAdmin):
    list_display = ['series_entry', 'category', 'occupancy', 'quantity', 'rate_per_night']
    list_filter = ['category', 'occupancy']
    ordering = ['series_entry__arrival_date']
