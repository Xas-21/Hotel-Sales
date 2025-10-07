from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from decimal import Decimal
from accounts.models import Account
from requests.models import Request


class MeetingRoom(models.Model):
    """
    Meeting rooms configuration for event management.
    Handles both combined rooms (IKMA, HEGRA, DADAN, ALJADIDA) and separate rooms.
    """
    ROOM_TYPES = [
        ('combined', 'Combined Room (Main Halls)'),
        ('separate', 'Separate Room'),
    ]
    
    name = models.CharField(max_length=50, unique=True, help_text="Room name (e.g., IKMA, Board Room)")
    display_name = models.CharField(max_length=100, help_text="Display name for the room")
    room_type = models.CharField(max_length=20, choices=ROOM_TYPES, default='separate')
    capacity = models.PositiveIntegerField(default=50, help_text="Maximum capacity")
    is_combined = models.BooleanField(default=False, help_text="Can be combined with other rooms")
    combined_group = models.CharField(max_length=20, blank=True, help_text="Group for combined rooms (main_halls)")
    is_active = models.BooleanField(default=True, help_text="Available for booking")
    description = models.TextField(blank=True, help_text="Room description")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['room_type', 'name']
        verbose_name = "Meeting Room"
        verbose_name_plural = "Meeting Rooms"
    
    def __str__(self):
        return self.display_name
    
    @classmethod
    def get_combined_rooms(cls):
        """Get all rooms that can be combined (IKMA, HEGRA, DADAN, ALJADIDA)"""
        return cls.objects.filter(combined_group='main_halls', is_active=True)
    
    @classmethod
    def get_separate_rooms(cls):
        """Get all separate rooms (Board Room, Al Badia, La Palma)"""
        return cls.objects.filter(room_type='separate', is_active=True)


class EventBooking(models.Model):
    """
    Event bookings for space management and calendar display.
    Integrates with existing Request system.
    """
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Confirmed', 'Confirmed'),
        ('Cancelled', 'Cancelled'),
        ('Pending', 'Pending'),
        ('Paid', 'Paid'),
        ('Partially Paid', 'Partially Paid'),
        ('Actual', 'Actual'),
    ]
    
    # Event details
    event_name = models.CharField(max_length=200, help_text="Event name")
    event_date = models.DateField(help_text="Event date")
    start_time = models.TimeField(help_text="Start time")
    end_time = models.TimeField(help_text="End time")
    
    # Room selection (many-to-many for multiple rooms)
    meeting_rooms = models.ManyToManyField(MeetingRoom, help_text="Selected meeting rooms")
    
    # Integration with existing system
    request = models.ForeignKey(Request, on_delete=models.CASCADE, null=True, blank=True, 
                               help_text="Linked request from admin panel")
    account = models.ForeignKey(Account, on_delete=models.CASCADE, 
                               help_text="Account organizing the event")
    
    # Status and tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    notes = models.TextField(blank=True, help_text="Additional notes")
    
    # Event timing details
    coffee_break_time = models.TimeField(null=True, blank=True, help_text="Coffee break time")
    lunch_time = models.TimeField(null=True, blank=True, help_text="Lunch time")
    dinner_time = models.TimeField(null=True, blank=True, help_text="Dinner time")
    
    # Event setup and style
    STYLE_CHOICES = [
        ('Classroom', 'Classroom'),
        ('Theatre', 'Theatre'),
        ('U Shape', 'U Shape'),
        ('Board', 'Board'),
        ('Banquet', 'Banquet'),
        ('Reception', 'Reception'),
    ]
    style = models.CharField(max_length=15, choices=STYLE_CHOICES, default='Classroom', help_text="Room setup style")
    
    # Financial details
    rental_fees_per_day = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'), 
                                             validators=[MinValueValidator(Decimal('0.00'))], 
                                             help_text="Daily rental fees for venue")
    rate_per_person = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'), 
                                         validators=[MinValueValidator(Decimal('0.00'))], 
                                         help_text="Rate per person for selected package")
    total_persons = models.PositiveIntegerField(default=0, help_text="Total number of attendees")
    
    # Package selection
    PACKAGE_CHOICES = [
        ('coffee_only', 'Coffee Break only'),
        ('coffee_lunch', 'Coffee Break and lunch'),
        ('coffee_lunch_dinner', 'Coffee Break and Lunch and Dinner'),
        ('two_coffee', '2 Coffee Break'),
        ('two_coffee_meal', '2 Coffee Break and lunch or dinner'),
        ('lunch', 'Lunch'),
        ('dinner', 'Dinner'),
        ('lunch_dinner', 'Lunch and Dinner'),
    ]
    packages = models.CharField(max_length=20, choices=PACKAGE_CHOICES, blank=True, help_text="Package selection for catering")
    
    # Deadline fields
    request_received_date = models.DateField(null=True, blank=True, help_text="Date when request was received")
    offer_acceptance_deadline = models.DateField(null=True, blank=True, help_text="Deadline for offer acceptance")
    deposit_deadline = models.DateField(null=True, blank=True, help_text="Deadline for deposit payment")
    full_payment_deadline = models.DateField(null=True, blank=True, help_text="Deadline for full payment")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, 
                                  help_text="User who created the booking")
    
    class Meta:
        ordering = ['event_date', 'start_time']
        verbose_name = "Event Booking"
        verbose_name_plural = "Event Bookings"
        # Ensure no double booking of same rooms at same time
        unique_together = [['event_date', 'start_time', 'end_time']]
    
    def __str__(self):
        return f"{self.event_name} - {self.event_date} ({self.start_time}-{self.end_time})"
    
    def get_room_names(self):
        """Get comma-separated list of room names"""
        return ", ".join([room.display_name for room in self.meeting_rooms.all()])
    
    def get_duration(self):
        """Calculate event duration in hours"""
        from datetime import datetime, timedelta
        if not self.event_date or not self.start_time or not self.end_time:
            return 0
        start_dt = datetime.combine(self.event_date, self.start_time)
        end_dt = datetime.combine(self.event_date, self.end_time)
        if end_dt < start_dt:  # Handle overnight events
            end_dt += timedelta(days=1)
        duration = end_dt - start_dt
        return duration.total_seconds() / 3600  # Convert to hours
    
    def is_conflict(self, other_booking):
        """Check if this booking conflicts with another"""
        if self.event_date != other_booking.event_date:
            return False
        
        # Check if rooms overlap
        self_rooms = set(self.meeting_rooms.values_list('id', flat=True))
        other_rooms = set(other_booking.meeting_rooms.values_list('id', flat=True))
        if not self_rooms.intersection(other_rooms):
            return False
        
        # Check if times overlap
        return not (self.end_time <= other_booking.start_time or 
                   other_booking.end_time <= self.start_time)
    
    @classmethod
    def get_conflicts(cls, event_date, start_time, end_time, room_ids, exclude_id=None):
        """Get all conflicting bookings for given parameters"""
        conflicts = cls.objects.filter(
            event_date=event_date,
            meeting_rooms__id__in=room_ids,
            status__in=['tentative', 'confirmed']
        ).exclude(
            models.Q(end_time__lte=start_time) | models.Q(start_time__gte=end_time)
        )
        
        if exclude_id:
            conflicts = conflicts.exclude(id=exclude_id)
        
        return conflicts.distinct()


class EventMetrics(models.Model):
    """
    Cached metrics for event performance analytics.
    Updated via signals when events are created/modified.
    """
    date = models.DateField(help_text="Metrics date")
    total_events = models.PositiveIntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_attendees = models.PositiveIntegerField(default=0)
    room_utilization = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    
    # Room-specific metrics
    ikma_events = models.PositiveIntegerField(default=0)
    hegra_events = models.PositiveIntegerField(default=0)
    dadan_events = models.PositiveIntegerField(default=0)
    aljadida_events = models.PositiveIntegerField(default=0)
    board_room_events = models.PositiveIntegerField(default=0)
    al_badia_events = models.PositiveIntegerField(default=0)
    la_palma_events = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date']
        unique_together = ['date']
        verbose_name = "Event Metrics"
        verbose_name_plural = "Event Metrics"
    
    def __str__(self):
        return f"Event Metrics - {self.date}"