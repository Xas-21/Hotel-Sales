from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from hotel_sales.admin.mixins import ConfigEnforcedAdminMixin
from .models import (
    Request, CancelledRequest, RoomEntry, Transportation, EventAgenda, SeriesGroupEntry, SeriesRoomEntry,
    RoomType, RoomOccupancy, CancellationReason, SystemFieldRequirement, SystemFormLayout,
    RequestFieldRequirement, RequestFormLayout, DynamicModel, DynamicField, DynamicModelMigration,
    DynamicFieldValue
)

class RoomEntryInline(admin.TabularInline):
    model = RoomEntry
    extra = 1
    fields = ['room_type', 'occupancy_type', 'category', 'occupancy', 'quantity', 'rate_per_night']
    verbose_name = "Room Entry (part of Accommodation Details)"
    verbose_name_plural = "Room Entries (part of Accommodation Details)"
    
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
            'fields': ('status', 'cancellation_reason_fixed', 'cancellation_reason'),
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
    list_display = ['series_entry', 'effective_room_type', 'effective_occupancy', 'quantity', 'rate_per_night']
    list_filter = ['room_type', 'occupancy_type', 'category', 'occupancy']
    ordering = ['series_entry__arrival_date']
    
    def effective_room_type(self, obj):
        return obj.effective_room_type
    effective_room_type.short_description = 'Room Type'
    
    def effective_occupancy(self, obj):
        return obj.effective_occupancy  
    effective_occupancy.short_description = 'Occupancy'


# ============================================================
# CONFIGURATION MODELS ADMIN
# ============================================================

@admin.register(RoomType)
class RoomTypeAdmin(admin.ModelAdmin):
    """Admin interface for configurable room types"""
    list_display = ['code', 'name', 'description', 'active', 'sort_order', 'created_at']
    list_filter = ['active', 'created_at']
    search_fields = ['code', 'name', 'description']
    list_editable = ['active', 'sort_order']
    ordering = ['sort_order', 'name']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = [
        ('Basic Information', {
            'fields': ('code', 'name', 'description')
        }),
        ('Display Settings', {
            'fields': ('active', 'sort_order')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    ]
    
    actions = ['activate_selected', 'deactivate_selected']
    
    def activate_selected(self, request, queryset):
        queryset.update(active=True)
        self.message_user(request, f"Activated {queryset.count()} room types.")
    activate_selected.short_description = "Activate selected room types"
    
    def deactivate_selected(self, request, queryset):
        queryset.update(active=False)
        self.message_user(request, f"Deactivated {queryset.count()} room types.")
    deactivate_selected.short_description = "Deactivate selected room types"


@admin.register(RoomOccupancy)
class RoomOccupancyAdmin(admin.ModelAdmin):
    """Admin interface for configurable room occupancy types"""
    list_display = ['code', 'label', 'pax_count', 'description', 'active', 'sort_order', 'created_at']
    list_filter = ['active', 'pax_count', 'created_at']
    search_fields = ['code', 'label', 'description']
    list_editable = ['active', 'sort_order']
    ordering = ['sort_order', 'label']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = [
        ('Basic Information', {
            'fields': ('code', 'label', 'pax_count', 'description')
        }),
        ('Display Settings', {
            'fields': ('active', 'sort_order')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    ]
    
    actions = ['activate_selected', 'deactivate_selected']
    
    def activate_selected(self, request, queryset):
        queryset.update(active=True)
        self.message_user(request, f"Activated {queryset.count()} occupancy types.")
    activate_selected.short_description = "Activate selected occupancy types"
    
    def deactivate_selected(self, request, queryset):
        queryset.update(active=False)
        self.message_user(request, f"Deactivated {queryset.count()} occupancy types.")
    deactivate_selected.short_description = "Deactivate selected occupancy types"


@admin.register(CancellationReason)
class CancellationReasonAdmin(admin.ModelAdmin):
    """Admin interface for configurable cancellation reasons"""
    list_display = ['code', 'label', 'is_refundable', 'active', 'sort_order', 'created_at']
    list_filter = ['active', 'is_refundable', 'created_at']
    search_fields = ['code', 'label']
    list_editable = ['active', 'sort_order', 'is_refundable']
    ordering = ['sort_order', 'label']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = [
        ('Basic Information', {
            'fields': ('code', 'label')
        }),
        ('Policy Settings', {
            'fields': ('is_refundable',),
            'description': 'Configure refund policy for this cancellation reason'
        }),
        ('Display Settings', {
            'fields': ('active', 'sort_order')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    ]
    
    actions = ['activate_selected', 'deactivate_selected', 'make_refundable', 'make_non_refundable']
    
    def activate_selected(self, request, queryset):
        queryset.update(active=True)
        self.message_user(request, f"Activated {queryset.count()} cancellation reasons.")
    activate_selected.short_description = "Activate selected cancellation reasons"
    
    def deactivate_selected(self, request, queryset):
        queryset.update(active=False)
        self.message_user(request, f"Deactivated {queryset.count()} cancellation reasons.")
    deactivate_selected.short_description = "Deactivate selected cancellation reasons"
    
    def make_refundable(self, request, queryset):
        queryset.update(is_refundable=True)
        self.message_user(request, f"Made {queryset.count()} cancellation reasons refundable.")
    make_refundable.short_description = "Mark as refundable"
    
    def make_non_refundable(self, request, queryset):
        queryset.update(is_refundable=False)
        self.message_user(request, f"Made {queryset.count()} cancellation reasons non-refundable.")
    make_non_refundable.short_description = "Mark as non-refundable"


# ============================================================
# CENTRALIZED SYSTEM CONFIGURATION ADMIN
# ============================================================

@admin.register(SystemFieldRequirement)
class SystemFieldRequirementAdmin(admin.ModelAdmin):
    """Centralized admin interface for configurable field requirements across all modules"""
    list_display = ['module', 'form_type_short', 'field_label', 'section_name', 'required', 'enabled', 'sort_order']
    list_filter = ['module', 'form_type', 'section_name', 'required', 'enabled']
    search_fields = ['field_name', 'field_label', 'help_text']
    list_editable = ['required', 'enabled', 'sort_order']
    ordering = ['module', 'form_type', 'section_name', 'sort_order', 'field_name']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = [
        ('Module & Form Configuration', {
            'fields': ('module', 'form_type'),
            'description': 'Select the module and form type to configure'
        }),
        ('Field Information', {
            'fields': ('field_name', 'field_label', 'help_text')
        }),
        ('Layout & Behavior', {
            'fields': ('section_name', 'required', 'enabled', 'sort_order'),
            'description': 'Configure field behavior, visibility, and section placement'
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    ]
    
    actions = ['make_required', 'make_optional', 'enable_selected', 'disable_selected', 'move_to_section']
    
    def form_type_short(self, obj):
        """Display shortened form type for better readability"""
        return obj.form_type.split('.')[-1] if '.' in obj.form_type else obj.form_type
    form_type_short.short_description = 'Form Type'
    
    def make_required(self, request, queryset):
        queryset.update(required=True)
        self.message_user(request, f"Made {queryset.count()} fields required.")
    make_required.short_description = "Make selected fields required"
    
    def make_optional(self, request, queryset):
        queryset.update(required=False)
        self.message_user(request, f"Made {queryset.count()} fields optional.")
    make_optional.short_description = "Make selected fields optional"
    
    def enable_selected(self, request, queryset):
        queryset.update(enabled=True)
        self.message_user(request, f"Enabled {queryset.count()} fields.")
    enable_selected.short_description = "Enable selected fields"
    
    def disable_selected(self, request, queryset):
        queryset.update(enabled=False)
        self.message_user(request, f"Disabled {queryset.count()} fields.")
    disable_selected.short_description = "Disable selected fields"


@admin.register(SystemFormLayout)
class SystemFormLayoutAdmin(admin.ModelAdmin):
    """Centralized admin interface for configurable form layouts across all modules"""
    list_display = ['module', 'form_type_short', 'sections_count', 'active', 'updated_by', 'updated_at']
    list_filter = ['module', 'form_type', 'active', 'updated_at']
    search_fields = ['form_type', 'updated_by']
    list_editable = ['active']
    ordering = ['module', 'form_type']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = [
        ('Module & Form Configuration', {
            'fields': ('module', 'form_type'),
            'description': 'Select the module and form type to configure'
        }),
        ('Layout Configuration', {
            'fields': ('sections', 'active'),
            'description': 'Configure form sections and field arrangement using JSON format'
        }),
        ('Management', {
            'fields': ('updated_by',),
            'description': 'Track who last updated this layout'
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    ]
    
    actions = ['activate_selected', 'deactivate_selected']
    
    def form_type_short(self, obj):
        """Display shortened form type for better readability"""
        return obj.form_type.split('.')[-1] if '.' in obj.form_type else obj.form_type
    form_type_short.short_description = 'Form Type'
    
    def sections_count(self, obj):
        """Display number of sections in layout"""
        sections = obj.get_sections()
        return len(sections) if sections else 0
    sections_count.short_description = 'Sections'
    
    def activate_selected(self, request, queryset):
        queryset.update(active=True)
        self.message_user(request, f"Activated {queryset.count()} form layouts.")
    activate_selected.short_description = "Activate selected form layouts"
    
    def deactivate_selected(self, request, queryset):
        queryset.update(active=False)
        self.message_user(request, f"Deactivated {queryset.count()} form layouts.")
    deactivate_selected.short_description = "Deactivate selected form layouts"
    
    def save_model(self, request, obj, form, change):
        """Auto-populate updated_by field"""
        if hasattr(request, 'user') and request.user.is_authenticated:
            obj.updated_by = request.user.username
        super().save_model(request, obj, form, change)


# Keep the old admin classes for backward compatibility (deprecated)
class RequestFieldRequirementAdmin(admin.ModelAdmin):
    """Deprecated admin - redirects to SystemFieldRequirement"""
    def changelist_view(self, request, extra_context=None):
        from django.shortcuts import redirect
        return redirect('/admin/requests/systemfieldrequirement/')

class RequestFormLayoutAdmin(admin.ModelAdmin):
    """Deprecated admin - redirects to SystemFormLayout"""
    def changelist_view(self, request, extra_context=None):
        from django.shortcuts import redirect
        return redirect('/admin/requests/systemformlayout/')


# Register dynamic model admin interfaces  
from .admin.configuration_admin import DynamicModelAdmin, DynamicFieldAdmin, DynamicModelMigrationAdmin

# Note: These are registered with @admin.register decorators in configuration_admin.py
# but we ensure the admin classes are imported here for proper registration

@admin.register(DynamicFieldValue)
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
