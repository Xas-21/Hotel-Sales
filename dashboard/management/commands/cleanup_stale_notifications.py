"""
Management command to clean up stale notifications.

This command removes notifications that are no longer relevant:
- Notifications for deleted requests/agreements
- Payment notifications for paid requests
- Return deadline notifications for signed agreements
- Etc.

Usage:
    python manage.py cleanup_stale_notifications
"""
from django.core.management.base import BaseCommand
from dashboard.signals import cleanup_all_stale_notifications


class Command(BaseCommand):
    help = 'Clean up stale notifications that are no longer relevant'

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Starting stale notification cleanup...')
        )
        
        try:
            deleted_count = cleanup_all_stale_notifications()
            
            if deleted_count > 0:
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully removed {deleted_count} stale notifications')
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS('No stale notifications found - system is clean!')
                )
            
        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f'Error cleaning up notifications: {str(e)}')
            )
            raise