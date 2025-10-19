from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.conf import settings

class Account(models.Model):
    """
    Accounts Database for various business segments and organizations.
    Prevents duplicates based on company name and account type.
    """
    ACCOUNT_TYPES = [
        ('Company', 'Company'),
        ('Government', 'Government'),
        ('Travel Agency', 'Travel Agency'),
        ('Medical', 'Medical'),
        ('Pharmaceuticals', 'Pharmaceuticals'),
        ('Education', 'Education'),
        ('Training and Consulting', 'Training and Consulting'),
        ('Hospitality', 'Hospitality'),
        ('Technology', 'Technology'),
        ('Finance', 'Finance'),
        ('Manufacturing', 'Manufacturing'),
        ('Real Estate', 'Real Estate'),
        ('Retail', 'Retail'),
        ('Other', 'Other'),
    ]
    
    # CITY_CHOICES removed - now managed by dynamic configuration system
    
    name = models.CharField(max_length=200, help_text="Company/Organization name")
    # Note: account_type choices are managed through the dynamic configuration system
    # See Configuration > Account section to manage available types
    account_type = models.CharField(max_length=30, choices=ACCOUNT_TYPES)
    city = models.CharField(max_length=200, blank=True, help_text="Primary city location")
    contact_person = models.TextField(blank=True, max_length=100)
    position = models.TextField(blank=True, help_text="Contact person's position/title (can be detailed)")
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    
    # Enhanced fields for Phase 1D - TextField conversions and additional information
    address = models.TextField(blank=True, help_text="Complete address including street, city, state, country")
    notes = models.TextField(blank=True, help_text="Additional notes about this account")
    website = models.URLField(blank=True, help_text="Company website URL")
    
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


class UserProfile(models.Model):
    """Extended user profile with role and display information"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    display_name = models.CharField(max_length=100, blank=True, help_text="Optional display name override")
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile for {self.user.username}"

    @property
    def full_name(self):
        """Return display name if set, otherwise user's full name, fallback to username"""
        if self.display_name:
            return self.display_name
        user_full_name = self.user.get_full_name()
        if user_full_name:
            return user_full_name
        return self.user.username

    @property
    def role_label(self):
        """Return user-friendly role label based on groups and permissions"""
        user = self.user
        if user.is_superuser:
            return "Admin"
        
        user_groups = list(user.groups.values_list('name', flat=True))
        
        if user_groups:
            # Return the first group name (highest priority) as the role label
            # This will show the actual group name like "Director Of Sales & Marketing"
            return user_groups[0]
        
        # Fallback based on Django permissions
        if user.is_staff:
            return "Staff"
        
        return "User"

    @property
    def permissions_summary(self):
        """Return a list of key permissions for display"""
        permissions = []
        user = self.user
        
        if user.is_superuser:
            return ["All Permissions"]
        
        if user.has_perm('dashboard.view_dashboard'):
            permissions.append("Dashboard Access")
        if user.has_perm('dashboard.view_calendar'):
            permissions.append("Calendar Access")
        if user.has_perm('accounts.view_account'):
            permissions.append("Accounts Access")
        if user.has_perm('requests.view_request'):
            permissions.append("Requests Access")
        if user.has_perm('agreements.view_agreement'):
            permissions.append("Agreements Access")
        if user.has_perm('sales_calls.view_salescall'):
            permissions.append("Sales Calls Access")
        
        if user.is_staff:
            permissions.append("Admin Panel Access")
        
        return permissions if permissions else ["Basic Access"]
