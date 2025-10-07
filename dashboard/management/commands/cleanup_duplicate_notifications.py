from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from dashboard.models import Notification
from collections import defaultdict


class Command(BaseCommand):
    help = 'Clean up duplicate notifications for the same object and notification type'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No notifications will be deleted'))
        
        # Get all notifications grouped by user, notification_type, object_id
        notifications = Notification.objects.all().order_by('user', 'notification_type', 'object_id', '-created_at')
        
        # Group by user, notification_type, and object_id
        grouped_notifications = defaultdict(list)
        for notif in notifications:
            key = (notif.user, notif.notification_type, notif.object_id)
            grouped_notifications[key].append(notif)
        
        total_deleted = 0
        
        for (user, notification_type, object_id), notifs in grouped_notifications.items():
            if len(notifs) > 1:
                # Keep the most recent notification, delete the rest
                to_delete = notifs[1:]  # All except the first (most recent)
                deleted_count = len(to_delete)
                
                self.stdout.write(
                    f"User: {user.username}, Type: {notification_type}, Object: {object_id} - "
                    f"Keeping 1, deleting {deleted_count} duplicates"
                )
                
                if not dry_run:
                    for notif in to_delete:
                        notif.delete()
                
                total_deleted += deleted_count
        
        if total_deleted == 0:
            self.stdout.write(self.style.SUCCESS('No duplicate notifications found'))
        else:
            if dry_run:
                self.stdout.write(
                    self.style.WARNING(f'DRY RUN: Would delete {total_deleted} duplicate notifications')
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully deleted {total_deleted} duplicate notifications')
                )