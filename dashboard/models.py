from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone


class Notification(models.Model):
    """Model for user notifications and alerts"""
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'), 
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    TYPE_CHOICES = [
        ('deadline', 'Deadline Alert'),
        ('payment', 'Payment Due'),
        ('agreement', 'Agreement Status'),
        ('request', 'Request Update'),
        ('system', 'System Alert'),
        ('info', 'Information'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='info')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    link_url = models.URLField(blank=True, null=True, help_text="Optional link for the notification action")
    link_text = models.CharField(max_length=50, blank=True, null=True, help_text="Text for the action link")
    
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(blank=True, null=True)
    
    # Optional: link to specific objects
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, blank=True, null=True)
    object_id = models.PositiveIntegerField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', 'created_at']),
            models.Index(fields=['user', 'notification_type']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.user.username} ({'Read' if self.is_read else 'Unread'})"
    
    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])
    
    def get_icon(self):
        """Get FontAwesome icon based on notification type"""
        icons = {
            'deadline': 'fas fa-clock text-warning',
            'payment': 'fas fa-money-bill-wave text-success',
            'agreement': 'fas fa-file-contract text-info',
            'request': 'fas fa-clipboard-list text-primary',
            'system': 'fas fa-cog text-secondary',
            'info': 'fas fa-info-circle text-info',
        }
        return icons.get(self.notification_type, 'fas fa-bell text-secondary')
    
    def get_priority_class(self):
        """Get Bootstrap class based on priority"""
        classes = {
            'low': 'border-start border-secondary',
            'medium': 'border-start border-primary',
            'high': 'border-start border-warning',
            'urgent': 'border-start border-danger',
        }
        return classes.get(self.priority, 'border-start border-secondary')
    
    def time_since_created(self):
        """Get human-readable time since creation"""
        now = timezone.now()
        diff = now - self.created_at
        
        if diff.days > 0:
            return f"{diff.days}d ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours}h ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes}m ago"
        else:
            return "Just now"
