from django.db import models
from django.utils import timezone

class Account(models.Model):
    """
    Accounts Database for companies, governments, and travel agencies.
    Prevents duplicates based on company name and account type.
    """
    ACCOUNT_TYPES = [
        ('Company', 'Company'),
        ('Government', 'Government'),
        ('Travel Agency', 'Travel Agency'),
    ]
    
    name = models.CharField(max_length=200, help_text="Company/Organization name")
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES)
    contact_person = models.CharField(max_length=100)
    position = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        # Prevent duplicates: same company name + account type combination
        unique_together = ['name', 'account_type']
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.account_type})"
    
    def get_contact_info(self):
        """Return formatted contact information"""
        contact_parts = [str(self.contact_person)]
        if self.position:
            contact_parts.append(f"({str(self.position)})")
        if self.phone:
            contact_parts.append(f"Phone: {str(self.phone)}")
        if self.email:
            contact_parts.append(f"Email: {str(self.email)}")
        return " - ".join(contact_parts)
