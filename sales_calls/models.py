from django.db import models
from django.utils import timezone
from accounts.models import Account

class SalesCall(models.Model):
    """
    Sales Calls / Visits tracking with detailed business potential and follow-up requirements.
    """
    MEETING_SUBJECT = [
        ('initial_contact', 'Initial Contact Meeting'),
        ('follow_up', 'Follow-up Meeting'),
        ('follow_up_meeting', 'Follow-up Meeting'),  # Keep for backward compatibility
        ('BRM', 'Business Review Management'),
        ('relationship_mgmt', 'Relationship Management'),
        ('sales_presentation', 'Sales Presentation'),
        ('contract_negotiation', 'Contract Negotiation'),
        ('site_inspection', 'Site Inspection'),
        ('client_visit', 'Client Site Visit'),
        ('proposal_presentation', 'Proposal Presentation'),
        ('Unknown', 'Unknown'),
    ]
    BUSINESS_POTENTIAL = [
        ('High', 'High'),
        ('Medium', 'Medium'),
        ('Low', 'Low'),
        ('Unknown', 'Unknown'),
    ]
    
    # Basic information
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='sales_calls')
    visit_date = models.DateField(db_index=True)
    city = models.CharField(max_length=100)
    address = models.TextField(blank=True)
    
    # Meeting details
    meeting_subject = models.CharField(max_length=50, choices=MEETING_SUBJECT)  # Increased length for longer choice labels
    business_potential = models.CharField(max_length=10, choices=BUSINESS_POTENTIAL, default='Unknown')
    
    # Detailed tracking
    next_steps = models.TextField(help_text="Planned next steps from this meeting")
    detailed_notes = models.TextField(help_text="Detailed notes from the meeting")
    follow_up_required = models.BooleanField(default=False)
    follow_up_date = models.DateField(null=True, blank=True, help_text="When to follow up")
    follow_up_completed = models.BooleanField(default=False)
    
    # Metadata
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-visit_date']
    
    def __str__(self):
        return f"{self.account.name} - {self.meeting_subject} ({self.visit_date})"
    
    def is_follow_up_overdue(self):
        """Check if follow-up is required but overdue"""
        if not self.follow_up_required or self.follow_up_completed:
            return False
        if not self.follow_up_date:
            return False
        from datetime import date
        return date.today() > self.follow_up_date
