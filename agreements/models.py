from django.db import models
from django.utils import timezone
from accounts.models import Account

class Agreement(models.Model):
    """
    Yearly Agreements with rate types, deadlines, and status tracking.
    """
    RATE_TYPES = [
        ('Corporate', 'Corporate'),
        ('Travel Agency', 'Travel Agency'),
        ('Group', 'Group'),
        ('Government', 'Government'),
    ]
    
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Sent', 'Sent'),
        ('Signed', 'Signed'),
        ('Expired', 'Expired'),
    ]
    
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='agreements')
    rate_type = models.CharField(max_length=20, choices=RATE_TYPES)
    
    # Agreement dates
    start_date = models.DateField()
    end_date = models.DateField()
    return_deadline = models.DateField(help_text="Deadline for signed agreement return")
    
    # Status and file
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Draft')
    agreement_file = models.FileField(upload_to='agreements/', blank=True, null=True)
    
    # Metadata
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ['account', 'rate_type', 'start_date']
    
    def __str__(self):
        return f"{self.account.name} - {self.rate_type} ({self.start_date} to {self.end_date})"
    
    def is_approaching_deadline(self, days_ahead=30):
        """Check if return deadline is approaching within specified days"""
        from datetime import date, timedelta
        return date.today() <= self.return_deadline <= date.today() + timedelta(days=days_ahead)
    
    def is_expired(self):
        """Check if agreement has expired"""
        from datetime import date
        return date.today() > self.end_date
