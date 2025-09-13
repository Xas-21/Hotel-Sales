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
            # Staff users get Staff group
            staff_group, _ = Group.objects.get_or_create(name='Staff')
            instance.groups.add(staff_group)
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