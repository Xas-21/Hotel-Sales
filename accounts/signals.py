from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User, Group
from .models import UserProfile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create a UserProfile when a User is created"""
    if created:
        profile = UserProfile.objects.create(user=instance)
        
        # Auto-assign default role based on user status
        if instance.is_superuser:
            # Superusers get Admin group (if it exists)
            admin_group, _ = Group.objects.get_or_create(name='Admin')
            instance.groups.add(admin_group)
        elif instance.is_staff:
            # Staff users get Sales Executive group by default
            sales_executive_group, _ = Group.objects.get_or_create(name='Sales Executive')
            instance.groups.add(sales_executive_group)
        else:
            # Regular users get Viewer group
            viewer_group, _ = Group.objects.get_or_create(name='Viewer')
            instance.groups.add(viewer_group)
        
        # Update display name from first/last name if available
        if instance.first_name and instance.last_name:
            profile.display_name = f"{instance.first_name} {instance.last_name}"
            profile.save()


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save the UserProfile when the User is saved"""
    if hasattr(instance, 'profile'):
        # Update display name if user's name changed
        if instance.first_name and instance.last_name:
            full_name = f"{instance.first_name} {instance.last_name}"
            if instance.profile.display_name != full_name:
                instance.profile.display_name = full_name
                instance.profile.save()


@receiver(post_save, sender=User)
def update_user_groups_on_save(sender, instance, **kwargs):
    """Update user groups when user permissions change - only for new users or permission changes"""
    # Only run this logic for new users or when permissions actually change
    if kwargs.get('created', False):
        # This is a new user - let the create_user_profile signal handle it
        return
    
    # Check if this is a permission change by looking at the raw data
    if hasattr(instance, '_state') and instance._state.adding:
        return
    
    # Only modify groups if user has no groups at all (newly created staff users)
    if instance.is_staff and not instance.groups.exists():
        # Only add Sales Executive if user has no groups at all
        sales_executive_group, _ = Group.objects.get_or_create(name='Sales Executive')
        instance.groups.add(sales_executive_group)
    elif not instance.is_staff and not instance.is_superuser and not instance.groups.exists():
        # Only add Viewer if user has no groups at all
        viewer_group, _ = Group.objects.get_or_create(name='Viewer')
        instance.groups.add(viewer_group)