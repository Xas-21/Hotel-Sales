from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from accounts.models import Account
from typing import TYPE_CHECKING, cast
from datetime import date
from decimal import Decimal
import json

if TYPE_CHECKING:
    from django.db.models.manager import RelatedManager




# Configuration Models for Admin Panel Management
class RoomType(models.Model):
    """Admin-configurable room types"""
    code = models.CharField(max_length=50, unique=True, help_text="Unique identifier (e.g., SUP, DLX)")
    name = models.CharField(max_length=100, help_text="Display name (e.g., Superior, Deluxe)")
    description = models.TextField(blank=True, help_text="Optional description")
    active = models.BooleanField(default=True, help_text="Available for selection")
    sort_order = models.PositiveIntegerField(default=0, help_text="Display order")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = "Room Type"
        verbose_name_plural = "Room Types"

    def __str__(self):
        return self.name


class RoomOccupancy(models.Model):
    """Admin-configurable room occupancy types"""
    code = models.CharField(max_length=50, unique=True, help_text="Unique identifier (e.g., SGL, DBL)")
    label = models.CharField(max_length=100, help_text="Display label (e.g., Single, Double)")
    pax_count = models.PositiveIntegerField(help_text="Number of guests")
    description = models.TextField(blank=True, help_text="Optional description")
    active = models.BooleanField(default=True, help_text="Available for selection")
    sort_order = models.PositiveIntegerField(default=0, help_text="Display order")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'label']
        verbose_name = "Room Occupancy"
        verbose_name_plural = "Room Occupancies"

    def __str__(self):
        return f"{self.label} ({self.pax_count} pax)"


class CancellationReason(models.Model):
    """Admin-configurable cancellation reasons"""
    code = models.CharField(max_length=50, unique=True, help_text="Unique identifier")
    label = models.CharField(max_length=200, help_text="Reason description")
    is_refundable = models.BooleanField(default=False, help_text="Allows refund")
    active = models.BooleanField(default=True, help_text="Available for selection")
    sort_order = models.PositiveIntegerField(default=0, help_text="Display order")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'label']
        verbose_name = "Cancellation Reason"
        verbose_name_plural = "Cancellation Reasons"

    def __str__(self):
        return self.label


class SystemFieldRequirement(models.Model):
    """System-wide configurable field requirements for all modules"""
    MODULE_CHOICES = [
        ('requests', 'Requests'),
        ('sales_calls', 'Sales Calls'),
        ('agreements', 'Agreements'),
        ('accounts', 'Accounts'),
    ]
    
    FORM_TYPE_CHOICES = [
        # Requests module
        ('requests.Group Accommodation', 'Requests - Group Accommodation'),
        ('requests.Individual Accommodation', 'Requests - Individual Accommodation'),
        ('requests.Event with Rooms', 'Requests - Event with Rooms'),
        ('requests.Event without Rooms', 'Requests - Event without Rooms'),
        ('requests.Series Group', 'Requests - Series Group'),
        # Sales Calls module
        ('sales_calls.SalesCall', 'Sales Calls - Visit Form'),
        # Agreements module
        ('agreements.Agreement', 'Agreements - Agreement Form'),
        # Accounts module
        ('accounts.Account', 'Accounts - Account Form'),
    ]
    
    module = models.CharField(max_length=20, choices=MODULE_CHOICES)
    form_type = models.CharField(max_length=50, choices=FORM_TYPE_CHOICES)
    field_name = models.CharField(max_length=100, help_text="Django field name")
    field_label = models.CharField(max_length=200, help_text="Display label")
    required = models.BooleanField(default=False, help_text="Field is required")
    enabled = models.BooleanField(default=True, help_text="Field is visible")
    section_name = models.CharField(max_length=100, default='Basic Information', help_text="Section/fieldset name")
    sort_order = models.PositiveIntegerField(default=0, help_text="Display order within section")
    help_text = models.TextField(blank=True, help_text="Custom help text for this field")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['module', 'form_type', 'section_name', 'sort_order', 'field_name']
        unique_together = ['form_type', 'field_name']
        verbose_name = "System Field Requirement"
        verbose_name_plural = "System Field Requirements"

    def __str__(self):
        return f"{self.get_form_type_display()}: {self.field_label} ({'Required' if self.required else 'Optional'})"


class SystemFormLayout(models.Model):
    """System-wide configurable form section layouts"""
    MODULE_CHOICES = [
        ('requests', 'Requests'),
        ('sales_calls', 'Sales Calls'),
        ('agreements', 'Agreements'),
        ('accounts', 'Accounts'),
    ]
    
    FORM_TYPE_CHOICES = [
        # Requests module
        ('requests.Group Accommodation', 'Requests - Group Accommodation'),
        ('requests.Individual Accommodation', 'Requests - Individual Accommodation'),
        ('requests.Event with Rooms', 'Requests - Event with Rooms'),
        ('requests.Event without Rooms', 'Requests - Event without Rooms'),
        ('requests.Series Group', 'Requests - Series Group'),
        # Sales Calls module
        ('sales_calls.SalesCall', 'Sales Calls - Visit Form'),
        # Agreements module
        ('agreements.Agreement', 'Agreements - Agreement Form'),
        # Accounts module
        ('accounts.Account', 'Accounts - Account Form'),
    ]
    
    module = models.CharField(max_length=20, choices=MODULE_CHOICES)
    form_type = models.CharField(max_length=50, choices=FORM_TYPE_CHOICES, unique=True)
    sections = models.JSONField(
        default=list,
        help_text="JSON array of sections: [{'name': 'Basic Info', 'fields': ['field1', 'field2'], 'order': 1, 'collapsed': false}]"
    )
    active = models.BooleanField(default=True, help_text="Layout is active")
    updated_by = models.CharField(max_length=100, blank=True, help_text="Last updated by")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['module', 'form_type']
        verbose_name = "System Form Layout"
        verbose_name_plural = "System Form Layouts"

    def __str__(self):
        return f"{self.get_form_type_display()} Layout"
    
    def get_sections(self):
        """Get sections as parsed JSON"""
        try:
            return json.loads(self.sections) if isinstance(self.sections, str) else self.sections
        except (json.JSONDecodeError, TypeError):
            return []

# Keep the old models for backward compatibility (deprecated)
class RequestFieldRequirement(SystemFieldRequirement):
    """Deprecated: Use SystemFieldRequirement instead"""
    class Meta:
        proxy = True
        verbose_name = "Request Field Requirement (Deprecated)"
        verbose_name_plural = "Request Field Requirements (Deprecated)"

class RequestFormLayout(SystemFormLayout):
    """Deprecated: Use SystemFormLayout instead"""
    class Meta:
        proxy = True
        verbose_name = "Request Form Layout (Deprecated)"
        verbose_name_plural = "Request Form Layouts (Deprecated)"

class Request(models.Model):
    """
    Main requests model supporting all request types with comprehensive features.
    """
    REQUEST_TYPES = [
        ('Group Accommodation', 'Group Accommodation (10+ rooms)'),
        ('Individual Accommodation', 'Individual Accommodation (1-9 rooms)'),
        ('Event with Rooms', 'Event with Rooms'),
        ('Event without Rooms', 'Event without Rooms'),
        ('Series Group', 'Series Group (multiple dates)'),
    ]
    
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Confirmed', 'Confirmed'),
        ('Cancelled', 'Cancelled'),
        ('Pending', 'Pending'),
        ('Paid', 'Paid'),
        ('Partially Paid', 'Partially Paid'),
        ('Actual', 'Actual'),  # Status when paid requests reach arrival date
    ]
    
    # Display choices exclude 'Cancelled' for dropdown (handled via button)
    DISPLAY_STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Confirmed', 'Confirmed'),
        ('Pending', 'Pending'),
        ('Paid', 'Paid'),
        ('Partially Paid', 'Partially Paid'),
        ('Actual', 'Actual'),
    ]
    
    MEAL_PLAN_CHOICES = [
        ('RO', 'Room Only'),
        ('BB', 'Bed & Breakfast'),
        ('HB', 'Half Board (Breakfast + Dinner)'),
        ('FB', 'Full Board (All Meals)'),
    ]
    
    # Basic information
    request_type = models.CharField(max_length=30, choices=REQUEST_TYPES)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='requests')
    confirmation_number = models.CharField(max_length=50, unique=True, blank=True, null=True)
    request_received_date = models.DateField(default=timezone.localdate)
    
    # Accommodation details
    check_in_date = models.DateField(null=True, blank=True, db_index=True)
    check_out_date = models.DateField(null=True, blank=True)
    nights = models.PositiveIntegerField(null=True, blank=True, editable=False, help_text="Automatically calculated")
    meal_plan = models.CharField(max_length=2, choices=MEAL_PLAN_CHOICES, default='RO')
    
    # Status and payment
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    cancellation_reason = models.TextField(blank=True, help_text="Custom cancellation reason (when fixed reason not sufficient)")
    cancellation_reason_fixed = models.ForeignKey(
        'CancellationReason', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="Select from predefined cancellation reasons"
    )
    
    # Payment deadlines
    offer_acceptance_deadline = models.DateField(null=True, blank=True)
    deposit_deadline = models.DateField(null=True, blank=True)
    full_payment_deadline = models.DateField(null=True, blank=True)
    
    # Financial tracking (automatically calculated)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))], editable=False, help_text="Automatically calculated from room entries and transportation")
    total_rooms = models.PositiveIntegerField(default=0, editable=False, help_text="Total number of rooms across all entries")
    total_room_nights = models.PositiveIntegerField(default=0, editable=False, help_text="Total room nights (rooms × nights)")
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))])
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))])
    
    # File attachment
    agreement_file = models.FileField(upload_to='agreements/', blank=True, null=True)
    
    # Metadata
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True)
    
    if TYPE_CHECKING:
        room_entries: 'RelatedManager[RoomEntry]'
        transportation_entries: 'RelatedManager[Transportation]'
        event_agendas: 'RelatedManager[EventAgenda]'
        series_entries: 'RelatedManager[SeriesGroupEntry]'
    
    class Meta:
        ordering = ['-created_at']


    
    def clean(self):
        """Model validation"""
        super().clean()
        
        # Validate date ordering
        if self.check_in_date and self.check_out_date:
            if self.check_out_date <= self.check_in_date:
                raise ValidationError({'check_out_date': 'Check-out date must be after check-in date.'})
        
        # Validate cancellation reason is required when status is Cancelled
        if self.status == 'Cancelled':
            has_fixed_reason = self.cancellation_reason_fixed is not None
            has_custom_reason = self.cancellation_reason and self.cancellation_reason.strip()
            if not (has_fixed_reason or has_custom_reason):
                raise ValidationError({
                    'cancellation_reason': 'Either select a fixed cancellation reason or provide a custom reason when status is Cancelled.',
                    'cancellation_reason_fixed': 'Either select a fixed cancellation reason or provide a custom reason when status is Cancelled.'
                })
        
        # Validate financial values are non-negative (additional layer beyond field validators)
        if self.total_cost < 0:
            raise ValidationError({'total_cost': 'Total cost cannot be negative.'})
        if self.deposit_amount < 0:
            raise ValidationError({'deposit_amount': 'Deposit amount cannot be negative.'})
        if self.paid_amount < 0:
            raise ValidationError({'paid_amount': 'Paid amount cannot be negative.'})
    
    
    def get_room_total(self):
        """Calculate total room cost from all room entries"""
        return sum((room.get_total_cost() for room in self.room_entries.all()), Decimal('0'))
    
    def get_transportation_total(self):
        """Calculate total transportation cost"""
        return sum((transport.cost_per_way for transport in self.transportation_entries.all()), Decimal('0'))
    
    def get_event_total(self):
        """Calculate total event cost from all event agenda entries"""
        return sum((event.get_total_event_cost() for event in self.event_agendas.all()), Decimal('0'))
    
    def update_financial_totals(self):
        """Update all financial totals: cost, rooms, and room nights"""
        # Refresh from database to ensure we have latest related objects
        self.refresh_from_db()
        
        # Calculate totals from room entries
        room_total = self.get_room_total()
        transport_total = self.get_transportation_total()
        event_total = self.get_event_total()
        total_rooms = sum(room.quantity for room in self.room_entries.all())
        total_room_nights = sum(room.quantity * (self.nights or 0) for room in self.room_entries.all())
        
        # Calculate totals from series entries if it's a series group request
        if self.request_type == 'Series Group':
            series_room_total = Decimal('0')
            series_total_rooms = 0
            series_total_room_nights = 0
            
            for series_entry in self.series_entries.all():
                # Check if series entry has direct room configuration or uses SeriesRoomEntry objects
                if series_entry.room_type and series_entry.number_of_rooms:
                    # Use direct room fields from SeriesGroupEntry
                    series_room_total += series_entry.get_total_cost()
                    series_total_rooms += series_entry.number_of_rooms
                    series_total_room_nights += series_entry.number_of_rooms * (series_entry.nights or 0)
                else:
                    # Fall back to SeriesRoomEntry objects (backward compatibility)
                    for room in series_entry.room_entries.all():
                        series_room_total += room.get_total_cost()
                        series_total_rooms += room.quantity
                        series_total_room_nights += room.quantity * (series_entry.nights or 0)
            
            room_total = series_room_total
            total_rooms = series_total_rooms
            total_room_nights = series_total_room_nights
        
        # Update fields
        self.total_cost = room_total + transport_total + event_total
        self.total_rooms = total_rooms
        self.total_room_nights = total_room_nights
        
        self.save(update_fields=['total_cost', 'total_rooms', 'total_room_nights'])
    
    def get_adr(self):
        """Calculate ADR (Average Daily Rate): total_cost / total_room_nights"""
        if self.total_room_nights and self.total_room_nights > 0:
            return self.total_cost / Decimal(str(self.total_room_nights))
        return Decimal('0.00')
    
    def check_and_update_to_actual(self):
        """
        Check if a paid or confirmed request should be transitioned to 'Actual' status
        when the arrival date (check-in or event start) has arrived.
        Returns True if status was updated, False otherwise.
        """
        if self.status not in ['Paid', 'Confirmed']:
            return False
        
        # Determine the arrival date based on request type
        arrival_date = None
        if self.request_type in ['Group Accommodation', 'Individual Accommodation', 'Event with Rooms', 'Series Group']:
            arrival_date = self.check_in_date
        elif self.request_type == 'Event without Rooms':
            arrival_date = self.event_start_date
        
        # Check if arrival date has passed
        if arrival_date and arrival_date <= timezone.localdate():
            self.status = 'Actual'
            self.save(update_fields=['status'])
            return True
        
        return False
    
    def get_display_paid_amount(self):
        """
        Get the amount to display as paid based on status.
        For 'Paid' or 'Actual' status, show total_cost instead of paid_amount.
        """
        if self.status in ['Paid', 'Actual']:
            return self.total_cost
        return self.paid_amount
    
    def set_default_deadlines(self):
        """
        Set default payment deadlines for all request types based on business rules.
        This ensures the alert system works for all request types.
        """
        from datetime import timedelta
        
        today = timezone.localdate()
        
        # Set offer acceptance deadline (7 days from today for all request types)
        if not self.offer_acceptance_deadline:
            self.offer_acceptance_deadline = today + timedelta(days=7)
        
        # Set deposit deadline (14 days from today for all request types)
        if not self.deposit_deadline:
            self.deposit_deadline = today + timedelta(days=14)
        
        # Set full payment deadline based on check-in date or 30 days from today
        if not self.full_payment_deadline:
            if self.check_in_date:
                # Full payment due 7 days before check-in
                self.full_payment_deadline = self.check_in_date - timedelta(days=7)
            else:
                # Default to 30 days from today if no check-in date
                self.full_payment_deadline = today + timedelta(days=30)
    
    def save(self, *args, **kwargs):
        # Set unique default confirmation number if empty to avoid constraint violations
        if not self.confirmation_number:
            import time
            # Generate a unique confirmation number using timestamp
            # Format: PENDING-timestamp to ensure uniqueness
            self.confirmation_number = f"PENDING-{int(time.time() * 1000000)}"
        
        # Auto-calculate nights if both dates are provided
        if self.check_in_date and self.check_out_date:
            check_in = cast(date, self.check_in_date)
            check_out = cast(date, self.check_out_date)
            self.nights = (check_out - check_in).days
        
        # Call clean method for validation
        self.clean()
        super().save(*args, **kwargs)


class CancelledRequest(Request):
    """Proxy model to show only cancelled requests in admin"""
    class Meta:
        proxy = True
        verbose_name = "Cancelled Request"
        verbose_name_plural = "Cancelled Requests"
    
    def __str__(self):
        return f"CANCELLED - {self.confirmation_number or 'Draft'} - {self.account.name} ({self.request_type})"


# Proxy models for specialized request forms
class AccommodationRequest(Request):
    """Proxy model for accommodation-only requests"""
    class Meta:
        proxy = True
        verbose_name = "Accommodation Request"
        verbose_name_plural = "Accommodation Requests"
    
    def save(self, *args, **kwargs):
        if not self.pk:  # Set default request_type for new records
            self.request_type = 'Group Accommodation'
        super().save(*args, **kwargs)


class EventOnlyRequest(Request):
    """Proxy model for event-only requests (no accommodation)"""
    class Meta:
        proxy = True
        verbose_name = "Event Only Request"
        verbose_name_plural = "Event Only Requests"
    
    def save(self, *args, **kwargs):
        if not self.pk:  # Set default request_type for new records
            self.request_type = 'Event without Rooms'
        super().save(*args, **kwargs)


class EventWithRoomsRequest(Request):
    """Proxy model for events with accommodation"""
    class Meta:
        proxy = True
        verbose_name = "Event with Accommodation"
        verbose_name_plural = "Events with Accommodation"
    
    def save(self, *args, **kwargs):
        if not self.pk:  # Set default request_type for new records
            self.request_type = 'Event with Rooms'
        super().save(*args, **kwargs)


class SeriesGroupRequest(Request):
    """Proxy model for series group requests"""
    class Meta:
        proxy = True
        verbose_name = "Series Group Request"
        verbose_name_plural = "Series Group Requests"
    
    def save(self, *args, **kwargs):
        if not self.pk:  # Set default request_type for new records
            self.request_type = 'Series Group'
        super().save(*args, **kwargs)


class RoomEntry(models.Model):
    """
    Dynamic room entry system for requests with configurable room types and occupancy types.
    """
    request = models.ForeignKey(Request, on_delete=models.CASCADE, related_name='room_entries')
    
    # Configurable fields linked to admin-configured choices
    room_type = models.ForeignKey(
        'RoomType', 
        on_delete=models.PROTECT, 
        null=False, 
        blank=False,
        help_text="Select from admin-configured room types"
    )
    occupancy_type = models.ForeignKey(
        'RoomOccupancy', 
        on_delete=models.PROTECT, 
        null=False, 
        blank=False,
        help_text="Select from admin-configured occupancy types"
    )
    
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    rate_per_night = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    
    def __str__(self):
        return f"{self.quantity}x {self.room_type.name} ({self.occupancy_type.label})"
    
    def get_total_cost(self):
        """Calculate total cost for this room entry"""
        nights = int(self.request.nights or 0)
        return Decimal(str(self.quantity)) * self.rate_per_night * Decimal(nights)

class Transportation(models.Model):
    """
    Transportation options with vehicle type and cost tracking.
    """
    VEHICLE_TYPES = [
        ('Sedan', 'Sedan'),
        ('SUV', 'SUV'),
        ('Van', 'Van'),
        ('Bus', 'Bus'),
        ('Limousine', 'Limousine'),
        ('Coach', 'Coach'),
    ]
    
    request = models.ForeignKey(Request, on_delete=models.CASCADE, related_name='transportation_entries')
    vehicle_type = models.CharField(max_length=20, choices=VEHICLE_TYPES)
    number_of_pax = models.PositiveIntegerField(help_text="Number of passengers", validators=[MinValueValidator(1)])
    cost_per_way = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))], help_text="Cost per one-way trip")
    timing = models.TimeField(null=True, blank=True, help_text="Departure/pickup time")
    notes = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.vehicle_type} for {self.number_of_pax} pax - ${self.cost_per_way}"

class EventAgenda(models.Model):
    """
    Event/Meeting agendas with detailed timing for events.
    """
    PACKAGE_CHOICES = [
        ('coffee_only', 'Coffee Break only'),
        ('coffee_lunch', 'Coffee Break and lunch'),
        ('coffee_lunch_dinner', 'Coffee Break and Lunch and Dinner'),
        ('two_coffee', '2 Coffee Break'),
        ('two_coffee_meal', '2 Coffee Break and lunch or dinner'),
    ]
    
    ROOM_CHOICES = [
        ('All Halls', 'All Halls'),
        ('IKMA', 'IKMA'),
        ('HEGRA', 'HEGRA'),
        ('DADAN', 'DADAN'),
        ('AL JADIDA', 'AL JADIDA'),
        ('Board Room', 'Board Room'),
        ('Al Badiya', 'Al Badiya'),
        ('La Palma', 'La Palma'),
    ]
    
    STYLE_CHOICES = [
        ('Classroom', 'Classroom'),
        ('Theatre', 'Theatre'),
        ('U Shape', 'U Shape'),
        ('Board', 'Board'),
        ('Banquet', 'Banquet'),
        ('Reception', 'Reception'),
    ]
    
    request = models.ForeignKey(Request, on_delete=models.CASCADE, related_name='event_agendas')
    event_date = models.DateField(db_index=True)
    meeting_room_name = models.CharField(max_length=20, choices=ROOM_CHOICES, default='All Halls', help_text="Meeting room for the event")
    start_time = models.TimeField()
    end_time = models.TimeField()
    coffee_break_time = models.TimeField(null=True, blank=True)
    lunch_time = models.TimeField(null=True, blank=True)
    dinner_time = models.TimeField(null=True, blank=True)
    agenda_details = models.TextField()
    
    # Enhanced financial fields
    rental_fees_per_day = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))], help_text="Daily rental fees for venue")
    packages = models.CharField(max_length=20, choices=PACKAGE_CHOICES, blank=True, help_text="Package selection for catering")
    style = models.CharField(max_length=15, choices=STYLE_CHOICES, default='Classroom', help_text="Room setup style")
    rate_per_person = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))], help_text="Rate per person for selected package")
    total_persons = models.PositiveIntegerField(default=0, help_text="Total number of attendees")
    
    class Meta:
        ordering = ['event_date', 'start_time']
    
    def get_total_event_cost(self):
        """Calculate total event cost (rental + person costs)"""
        person_costs = self.rate_per_person * Decimal(str(self.total_persons))
        return self.rental_fees_per_day + person_costs
    
    def __str__(self):
        return f"Event on {self.event_date} ({self.start_time} - {self.end_time})"

class SeriesGroupEntry(models.Model):
    """
    Series Group support for multiple arrival/departure dates with room configurations.
    """
    request = models.ForeignKey(Request, on_delete=models.CASCADE, related_name='series_entries')
    arrival_date = models.DateField(db_index=True)
    departure_date = models.DateField()
    nights = models.PositiveIntegerField(editable=False)
    
    # Room configuration fields
    room_type = models.ForeignKey(
        'RoomType', 
        on_delete=models.PROTECT, 
        null=False, 
        blank=False,
        help_text="Select from admin-configured room types"
    )
    occupancy_type = models.ForeignKey(
        'RoomOccupancy', 
        on_delete=models.PROTECT, 
        null=False, 
        blank=False,
        help_text="Select from admin-configured occupancy types"
    )
    number_of_rooms = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    rate_per_night = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    
    if TYPE_CHECKING:
        room_entries: 'RelatedManager[SeriesRoomEntry]'
    
    class Meta:
        ordering = ['arrival_date']
    
    def clean(self):
        """Model validation"""
        super().clean()
        
        # Validate date ordering
        if self.arrival_date and self.departure_date:
            if self.departure_date <= self.arrival_date:
                raise ValidationError({'departure_date': 'Departure date must be after arrival date.'})
    
    def save(self, *args, **kwargs):
        # Auto-calculate nights
        if self.arrival_date and self.departure_date:
            arr = cast(date, self.arrival_date)
            dep = cast(date, self.departure_date)
            self.nights = (dep - arr).days
        
        # Call clean method for validation
        self.clean()
        super().save(*args, **kwargs)
    
    def get_total_cost(self):
        """Calculate total cost for this series entry"""
        return Decimal(str(self.number_of_rooms)) * self.rate_per_night * Decimal(self.nights or 0)
    
    def __str__(self):
        return f"Series: {self.arrival_date} to {self.departure_date} ({self.number_of_rooms}x {self.room_type.name})"

class SeriesRoomEntry(models.Model):
    """
    Room configuration for each series group entry.
    """
    series_entry = models.ForeignKey(SeriesGroupEntry, on_delete=models.CASCADE, related_name='room_entries')
    
    # Configurable fields linked to admin-configured choices
    room_type = models.ForeignKey(
        'RoomType', 
        on_delete=models.PROTECT, 
        null=False, 
        blank=False,
        help_text="Select from admin-configured room types"
    )
    occupancy_type = models.ForeignKey(
        'RoomOccupancy', 
        on_delete=models.PROTECT, 
        null=False, 
        blank=False,
        help_text="Select from admin-configured occupancy types"
    )
    
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    rate_per_night = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    
    def __str__(self):
        return f"{self.quantity}x {self.room_type.name} ({self.occupancy_type.label})"
    
    def get_total_cost(self):
        """Calculate total cost for this series room entry"""
        return Decimal(str(self.quantity)) * self.rate_per_night * Decimal(self.series_entry.nights or 0)


# Dynamic Model Management System for Form Builder

class DynamicSection(models.Model):
    """
    Represents a configuration section containing fields.
    Used by Configuration Dashboard for both Core Sections (existing admin models) 
    and Custom Sections (user-created forms).
    """
    name = models.CharField(max_length=255, unique=True, help_text="Internal section name")
    display_name = models.CharField(max_length=255, help_text="Display name shown to users")
    description = models.TextField(blank=True, help_text="Description of this section's purpose")
    order = models.IntegerField(default=100, help_text="Display order")
    
    # Core section integration
    is_core_section = models.BooleanField(default=False, help_text="True if this represents an existing admin model")
    source_model = models.CharField(max_length=255, blank=True, help_text="Full model name (e.g. 'accounts.Account') for core sections")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Dynamic Section"
        verbose_name_plural = "Dynamic Sections"
        ordering = ['is_core_section', 'order', 'name']
    
    def __str__(self):
        prefix = "Core: " if self.is_core_section else "Custom: "
        return f"{prefix}{self.display_name}"


class DynamicModel(models.Model):
    """
    Represents a dynamically created model (table) in the system.
    """
    name = models.CharField(max_length=100, unique=True, help_text="Model name (e.g., 'Invoice')")
    app_label = models.CharField(max_length=100, default='requests', help_text="Django app where model belongs")
    table_name = models.CharField(max_length=100, unique=True, help_text="Database table name")
    display_name = models.CharField(max_length=100, help_text="Human-readable name for admin")
    description = models.TextField(blank=True, help_text="Description of this model's purpose")
    
    # Model configuration
    ordering_fields = models.JSONField(default=list, help_text="Fields to use for default ordering")
    is_active = models.BooleanField(default=True, help_text="Whether this model is active in the system")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Dynamic Model"
        verbose_name_plural = "Dynamic Models"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.display_name} ({self.name})"
    
    def get_full_model_name(self):
        """Get the full model name for Django references"""
        return f"{self.app_label}.{self.name}"
    
    def clean(self):
        """Validate model data"""
        if self.table_name and not str(self.table_name).isidentifier():
            raise ValidationError("Table name must be a valid Python identifier")
        
        if self.name and not str(self.name)[0].isupper():
            raise ValidationError("Model name must start with a capital letter")


class DynamicField(models.Model):
    """
    Represents a dynamically created field within a model.
    """
    FIELD_TYPES = [
        # Text fields
        ('char', 'Text (Short)'),
        ('text', 'Text (Long)'),
        ('email', 'Email'),
        ('url', 'URL'),
        ('slug', 'Slug'),
        
        # Number fields
        ('integer', 'Integer'),
        ('decimal', 'Decimal'),
        ('float', 'Float'),
        
        # Date/Time fields
        ('date', 'Date'),
        ('datetime', 'Date & Time'),
        ('time', 'Time'),
        
        # Boolean fields
        ('boolean', 'Checkbox (Yes/No)'),
        
        # Choice fields
        ('choice', 'Dropdown (Single Choice)'),
        ('multiple_choice', 'Multiple Choice'),
        
        # File fields
        ('file', 'File Upload'),
        ('image', 'Image Upload'),
        
        # Relationship fields
        ('foreign_key', 'Link to Another Model'),
        ('many_to_many', 'Multiple Links'),
        
        # Special fields
        ('json', 'JSON Data'),
    ]
    
    # Relationships - a field can belong to either a DynamicModel (full DB table) OR DynamicSection (form section)
    model = models.ForeignKey(DynamicModel, on_delete=models.CASCADE, related_name='fields', null=True, blank=True)
    section = models.ForeignKey(DynamicSection, on_delete=models.CASCADE, related_name='fields', null=True, blank=True)
    
    name = models.CharField(max_length=100, help_text="Field name in database (lowercase, underscores)")
    display_name = models.CharField(max_length=100, help_text="Label shown in forms")
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES)
    
    # Core field integration
    is_core_field = models.BooleanField(default=False, help_text="True if this represents an existing model field")
    
    # New core field creation features
    CORE_MODE_CHOICES = [
        ('override', 'Override Existing Field'),
        ('create', 'Create New Core Field'),
    ]
    
    STORAGE_CHOICES = [
        ('model_field', 'Store in Model Field'),
        ('value_store', 'Store in DynamicFieldValue'),
    ]
    
    core_mode = models.CharField(
        max_length=20, 
        choices=CORE_MODE_CHOICES, 
        default='override',
        help_text="Whether to override existing field or create new one"
    )
    model_field_name = models.CharField(
        max_length=100, 
        blank=True,
        help_text="Name of existing model field to override (required for override mode)"
    )
    storage = models.CharField(
        max_length=20,
        choices=STORAGE_CHOICES,
        default='value_store',
        help_text="Where to store field values"
    )
    
    # Field options
    required = models.BooleanField(default=False)
    default_value = models.TextField(blank=True, help_text="Default value (JSON format for complex types)")
    help_text = models.CharField(max_length=200, blank=True)
    
    # Field constraints
    max_length = models.PositiveIntegerField(null=True, blank=True, help_text="For text fields")
    max_digits = models.PositiveIntegerField(null=True, blank=True, help_text="For decimal fields")
    decimal_places = models.PositiveIntegerField(null=True, blank=True, help_text="For decimal fields")
    
    # Choice field options
    choices = models.JSONField(default=dict, help_text="For choice fields: {'value': 'display_name'}")
    
    # Foreign key options
    related_model = models.CharField(max_length=100, blank=True, help_text="Model to link to (app.Model)")
    
    # Display options
    section_name = models.CharField(max_length=100, default='General', help_text="Form section name for grouping (legacy field)")
    order = models.PositiveIntegerField(default=0, help_text="Order within section")
    is_active = models.BooleanField(default=True, help_text="Whether field is shown in forms")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Dynamic Field"
        verbose_name_plural = "Dynamic Fields"
        ordering = ['model', 'section', 'section_name', 'order']
    
    def __str__(self):
        parent = self.model.name if self.model else self.section.name if self.section else "Unknown"
        return f"{parent}.{self.display_name} ({self.field_type})"
    
    def clean(self):
        """Validate field data and relationships"""
        # Validate that field belongs to either model or section, not both
        if not self.model and not self.section:
            raise ValidationError("Field must belong to either a DynamicModel or DynamicSection")
        if self.model and self.section:
            raise ValidationError("Field cannot belong to both a DynamicModel and DynamicSection")
        
        # Validate core field configuration
        if self.is_core_field:
            if self.core_mode == 'override' and not self.model_field_name:
                raise ValidationError("Override mode requires model_field_name to be specified")
            if self.core_mode == 'create' and self.model_field_name:
                raise ValidationError("Create mode should not have model_field_name specified")
            if self.core_mode == 'create' and self.storage == 'model_field':
                raise ValidationError("New core fields must use value_store storage")
        
        # Validate field data
        if self.name and (not str(self.name).isidentifier() or not str(self.name).islower()):
            raise ValidationError("Field name must be lowercase and a valid Python identifier")
        
        if self.field_type in ['char', 'email', 'url', 'slug'] and not self.max_length:
            raise ValidationError(f"{self.field_type} fields require max_length")
        
        if self.field_type == 'decimal' and (not self.max_digits or self.decimal_places is None):
            raise ValidationError("Decimal fields require max_digits and decimal_places")
        
        if self.field_type in ['choice', 'multiple_choice'] and not self.choices:
            raise ValidationError("Choice fields require choices to be defined")
        
        if self.field_type == 'foreign_key' and not self.related_model:
            raise ValidationError("Foreign key fields require related_model")


class DynamicModelMigration(models.Model):
    """
    Track migrations applied to dynamic models for rollback capability.
    """
    OPERATION_TYPES = [
        ('create_model', 'Create Model'),
        ('add_field', 'Add Field'),
        ('remove_field', 'Remove Field'),
        ('alter_field', 'Alter Field'),
        ('delete_model', 'Delete Model'),
    ]
    
    model_name = models.CharField(max_length=100)
    operation_type = models.CharField(max_length=20, choices=OPERATION_TYPES)
    operation_data = models.JSONField(help_text="Serialized operation data for rollback")
    applied_at = models.DateTimeField(auto_now_add=True)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Dynamic Migration"
        verbose_name_plural = "Dynamic Migrations"
        ordering = ['-applied_at']
    
    def __str__(self):
        status = "✓" if self.success else "✗"
        return f"{status} {self.operation_type} on {self.model_name} ({self.applied_at})"


class DynamicFieldValue(models.Model):
    """
    Stores dynamic field values for existing model instances.
    This provides persistence for dynamic fields without modifying existing tables.
    """
    # Reference to the existing model instance
    content_type = models.ForeignKey(
        'contenttypes.ContentType',
        on_delete=models.CASCADE,
        help_text="The model this value belongs to"
    )
    object_id = models.PositiveIntegerField(help_text="The ID of the model instance")
    
    # Reference to the dynamic field definition
    field = models.ForeignKey(
        DynamicField,
        on_delete=models.CASCADE,
        help_text="The dynamic field definition"
    )
    
    # Flexible value storage for different field types
    value_text = models.TextField(blank=True, null=True, help_text="For text, email, url, choice fields")
    value_integer = models.IntegerField(blank=True, null=True, help_text="For integer fields")
    value_decimal = models.DecimalField(max_digits=20, decimal_places=10, blank=True, null=True, help_text="For decimal fields")
    value_float = models.FloatField(blank=True, null=True, help_text="For float fields")
    value_boolean = models.BooleanField(blank=True, null=True, help_text="For boolean fields")
    value_date = models.DateField(blank=True, null=True, help_text="For date fields")
    value_datetime = models.DateTimeField(blank=True, null=True, help_text="For datetime fields")
    value_time = models.TimeField(blank=True, null=True, help_text="For time fields")
    value_file = models.FileField(upload_to='dynamic_fields/', blank=True, null=True, help_text="For file fields")
    value_json = models.JSONField(blank=True, null=True, help_text="For JSON and multiple choice fields")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Dynamic Field Value"
        verbose_name_plural = "Dynamic Field Values"
        unique_together = [['content_type', 'object_id', 'field']]
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['field']),
        ]
    
    def __str__(self):
        return f"{self.field.display_name}: {self.get_value()}"
    
    def get_value(self):
        """Get the actual value based on field type"""
        field_type = self.field.field_type
        
        if field_type in ['char', 'text', 'email', 'url', 'slug', 'choice']:
            return self.value_text
        elif field_type == 'integer':
            return self.value_integer
        elif field_type == 'decimal':
            return self.value_decimal
        elif field_type == 'float':
            return self.value_float
        elif field_type == 'boolean':
            return self.value_boolean
        elif field_type == 'date':
            return self.value_date
        elif field_type == 'datetime':
            return self.value_datetime
        elif field_type == 'time':
            return self.value_time
        elif field_type in ['file', 'image']:
            return self.value_file
        elif field_type in ['multiple_choice', 'json']:
            return self.value_json
        
        return None
    
    def set_value(self, value):
        """Set the value based on field type"""
        field_type = self.field.field_type
        
        # Clear all value fields first
        self.value_text = None
        self.value_integer = None
        self.value_decimal = None
        self.value_float = None
        self.value_boolean = None
        self.value_date = None
        self.value_datetime = None
        self.value_time = None
        self.value_file = None
        self.value_json = None
        
        # Set the appropriate field based on type
        if field_type in ['char', 'text', 'email', 'url', 'slug', 'choice']:
            self.value_text = str(value) if value is not None else None
        elif field_type == 'integer':
            self.value_integer = int(value) if value is not None else None
        elif field_type == 'decimal':
            self.value_decimal = Decimal(str(value)) if value is not None else None
        elif field_type == 'float':
            self.value_float = float(value) if value is not None else None
        elif field_type == 'boolean':
            self.value_boolean = bool(value) if value is not None else None
        elif field_type == 'date':
            self.value_date = value
        elif field_type == 'datetime':
            self.value_datetime = value
        elif field_type == 'time':
            self.value_time = value
        elif field_type in ['file', 'image']:
            self.value_file = value
        elif field_type in ['multiple_choice', 'json']:
            self.value_json = value
    
    @classmethod
    def get_values_for_instance(cls, instance):
        """Get all dynamic field values for a model instance"""
        from django.contrib.contenttypes.models import ContentType
        
        content_type = ContentType.objects.get_for_model(instance)
        return cls.objects.filter(
            content_type=content_type,
            object_id=instance.pk
        ).select_related('field')
