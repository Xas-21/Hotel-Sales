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


class RequestFieldRequirement(models.Model):
    """Admin-configurable field requirements per request type"""
    REQUEST_TYPE_CHOICES = [
        ('Group Accommodation', 'Group Accommodation (10+ rooms)'),
        ('Individual Accommodation', 'Individual Accommodation (1-9 rooms)'),
        ('Event with Rooms', 'Event with Rooms'),
        ('Event without Rooms', 'Event without Rooms'),
        ('Series Group', 'Series Group (multiple dates)'),
    ]
    
    request_type = models.CharField(max_length=30, choices=REQUEST_TYPE_CHOICES)
    field_name = models.CharField(max_length=100, help_text="Django field name")
    field_label = models.CharField(max_length=200, help_text="Display label")
    required = models.BooleanField(default=False, help_text="Field is required")
    enabled = models.BooleanField(default=True, help_text="Field is visible")
    sort_order = models.PositiveIntegerField(default=0, help_text="Display order within section")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['request_type', 'sort_order', 'field_name']
        unique_together = ['request_type', 'field_name']
        verbose_name = "Field Requirement"
        verbose_name_plural = "Field Requirements"

    def __str__(self):
        return f"{self.request_type}: {self.field_label} ({'Required' if self.required else 'Optional'})"


class RequestFormLayout(models.Model):
    """Admin-configurable form section layouts per request type"""
    REQUEST_TYPE_CHOICES = [
        ('Group Accommodation', 'Group Accommodation (10+ rooms)'),
        ('Individual Accommodation', 'Individual Accommodation (1-9 rooms)'),
        ('Event with Rooms', 'Event with Rooms'),
        ('Event without Rooms', 'Event without Rooms'),
        ('Series Group', 'Series Group (multiple dates)'),
    ]
    
    request_type = models.CharField(max_length=30, choices=REQUEST_TYPE_CHOICES, unique=True)
    sections = models.JSONField(
        default=list,
        help_text="JSON array of sections: [{'name': 'Basic Info', 'fields': ['field1', 'field2'], 'order': 1}]"
    )
    active = models.BooleanField(default=True, help_text="Layout is active")
    updated_by = models.CharField(max_length=100, blank=True, help_text="Last updated by")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['request_type']
        verbose_name = "Form Layout"
        verbose_name_plural = "Form Layouts"

    def __str__(self):
        return f"{self.request_type} Layout"
    
    def get_sections(self):
        """Get sections as parsed JSON"""
        try:
            return json.loads(self.sections) if isinstance(self.sections, str) else self.sections
        except (json.JSONDecodeError, TypeError):
            return []

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
        if self.status == 'Cancelled' and not (self.cancellation_reason and self.cancellation_reason.strip()):
            raise ValidationError({'cancellation_reason': 'Cancellation reason is required when status is Cancelled.'})
        
        # Validate financial values are non-negative (additional layer beyond field validators)
        if self.total_cost < 0:
            raise ValidationError({'total_cost': 'Total cost cannot be negative.'})
        if self.deposit_amount < 0:
            raise ValidationError({'deposit_amount': 'Deposit amount cannot be negative.'})
        if self.paid_amount < 0:
            raise ValidationError({'paid_amount': 'Paid amount cannot be negative.'})
    
    def save(self, *args, **kwargs):
        # Auto-calculate nights if both dates are provided
        if self.check_in_date and self.check_out_date:
            check_in = cast(date, self.check_in_date)
            check_out = cast(date, self.check_out_date)
            self.nights = (check_out - check_in).days
        
        # Call clean method for validation
        self.clean()
        super().save(*args, **kwargs)
    
    def get_room_total(self):
        """Calculate total room cost from all room entries"""
        return sum((room.get_total_cost() for room in self.room_entries.all()), Decimal('0'))
    
    def get_transportation_total(self):
        """Calculate total transportation cost"""
        return sum((transport.cost for transport in self.transportation_entries.all()), Decimal('0'))
    
    def update_financial_totals(self):
        """Update all financial totals: cost, rooms, and room nights"""
        # Refresh from database to ensure we have latest related objects
        self.refresh_from_db()
        
        # Calculate totals from room entries
        room_total = self.get_room_total()
        transport_total = self.get_transportation_total()
        total_rooms = sum(room.quantity for room in self.room_entries.all())
        total_room_nights = sum(room.quantity * (self.nights or 0) for room in self.room_entries.all())
        
        # Calculate totals from series entries if it's a series group request
        if self.request_type == 'Series Group':
            series_room_total = Decimal('0')
            series_total_rooms = 0
            series_total_room_nights = 0
            
            for series_entry in self.series_entries.all():
                for room in series_entry.room_entries.all():
                    series_room_total += room.get_total_cost()
                    series_total_rooms += room.quantity
                    series_total_room_nights += room.quantity * series_entry.nights
            
            room_total = series_room_total
            total_rooms = series_total_rooms
            total_room_nights = series_total_room_nights
        
        # Update fields
        self.total_cost = room_total + transport_total
        self.total_rooms = total_rooms
        self.total_room_nights = total_room_nights
        
        self.save(update_fields=['total_cost', 'total_rooms', 'total_room_nights'])


class CancelledRequest(Request):
    """Proxy model to show only cancelled requests in admin"""
    class Meta:
        proxy = True
        verbose_name = "Cancelled Request"
        verbose_name_plural = "Cancelled Requests"
    
    def __str__(self):
        return f"CANCELLED - {self.confirmation_number or 'Draft'} - {self.account.name} ({self.request_type})"


class RoomEntry(models.Model):
    """
    Dynamic room entry system for requests with different room types and categories.
    """
    ROOM_CATEGORIES = [
        ('Superior', 'Superior'),
        ('Deluxe', 'Deluxe'),
        ('Executive', 'Executive'),
        ('Villa with Garden', 'Villa with Garden'),
        ('Villa with Pool', 'Villa with Pool'),
    ]
    
    OCCUPANCY_TYPES = [
        ('Single', 'Single'),
        ('Double', 'Double'),
        ('Twin', 'Twin'),
    ]
    
    request = models.ForeignKey(Request, on_delete=models.CASCADE, related_name='room_entries')
    category = models.CharField(max_length=20, choices=ROOM_CATEGORIES)
    occupancy = models.CharField(max_length=10, choices=OCCUPANCY_TYPES)
    
    # New configurable fields (nullable for backward compatibility)
    room_type = models.ForeignKey(
        'RoomType', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="Select from admin-configured room types"
    )
    occupancy_type = models.ForeignKey(
        'RoomOccupancy', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="Select from admin-configured occupancy types"
    )
    
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    rate_per_night = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    
    @property
    def effective_room_type(self):
        """Return room type from new config or fallback to legacy category"""
        return self.room_type.name if self.room_type else self.category
    
    @property
    def effective_occupancy(self):
        """Return occupancy from new config or fallback to legacy occupancy"""
        return self.occupancy_type.label if self.occupancy_type else self.occupancy
    
    def __str__(self):
        return f"{self.quantity}x {self.effective_room_type} ({self.effective_occupancy})"
    
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
    cost = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    notes = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.vehicle_type} for {self.number_of_pax} pax - ${self.cost}"

class EventAgenda(models.Model):
    """
    Event/Meeting agendas with detailed timing for events.
    """
    request = models.ForeignKey(Request, on_delete=models.CASCADE, related_name='event_agendas')
    event_date = models.DateField(db_index=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    coffee_break_time = models.TimeField(null=True, blank=True)
    lunch_time = models.TimeField(null=True, blank=True)
    agenda_details = models.TextField()
    
    class Meta:
        ordering = ['event_date', 'start_time']
    
    def __str__(self):
        return f"Event on {self.event_date} ({self.start_time} - {self.end_time})"

class SeriesGroupEntry(models.Model):
    """
    Series Group support for multiple arrival/departure dates with different room configurations.
    """
    request = models.ForeignKey(Request, on_delete=models.CASCADE, related_name='series_entries')
    arrival_date = models.DateField(db_index=True)
    departure_date = models.DateField()
    arrival_time = models.TimeField(null=True, blank=True, help_text="Expected arrival time")
    departure_time = models.TimeField(null=True, blank=True, help_text="Expected departure time") 
    nights = models.PositiveIntegerField(editable=False)
    group_size = models.PositiveIntegerField()
    special_notes = models.TextField(blank=True)
    
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
    
    def __str__(self):
        return f"Series: {self.arrival_date} to {self.departure_date} ({self.group_size} pax)"

class SeriesRoomEntry(models.Model):
    """
    Room configuration for each series group entry.
    """
    ROOM_CATEGORIES = [
        ('Superior', 'Superior'),
        ('Deluxe', 'Deluxe'),
        ('Executive', 'Executive'),
        ('Villa with Garden', 'Villa with Garden'),
        ('Villa with Pool', 'Villa with Pool'),
    ]
    
    OCCUPANCY_TYPES = [
        ('Single', 'Single'),
        ('Double', 'Double'),
        ('Twin', 'Twin'),
    ]
    
    series_entry = models.ForeignKey(SeriesGroupEntry, on_delete=models.CASCADE, related_name='room_entries')
    category = models.CharField(max_length=20, choices=ROOM_CATEGORIES)
    occupancy = models.CharField(max_length=10, choices=OCCUPANCY_TYPES)
    
    # New configurable fields (nullable for backward compatibility)
    room_type = models.ForeignKey(
        'RoomType', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="Select from admin-configured room types"
    )
    occupancy_type = models.ForeignKey(
        'RoomOccupancy', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="Select from admin-configured occupancy types"
    )
    
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    rate_per_night = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    
    @property
    def effective_room_type(self):
        """Return room type from new config or fallback to legacy category"""
        return self.room_type.name if self.room_type else self.category
    
    @property
    def effective_occupancy(self):
        """Return occupancy from new config or fallback to legacy occupancy"""
        return self.occupancy_type.label if self.occupancy_type else self.occupancy
    
    def __str__(self):
        return f"{self.quantity}x {self.effective_room_type} ({self.effective_occupancy})"
    
    def get_total_cost(self):
        """Calculate total cost for this series room entry"""
        return Decimal(str(self.quantity)) * self.rate_per_night * Decimal(self.series_entry.nights or 0)
