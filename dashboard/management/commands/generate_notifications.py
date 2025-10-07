"""
Management command to generate deadline notifications for all users.

This command should be run periodically (e.g., daily) to generate
notifications for approaching deadlines based on request status.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from dashboard.api_views import generate_deadline_notifications, generate_payment_notifications
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Generate deadline and payment notifications for all users'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='Generate notifications for specific user ID only'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what notifications would be generated without creating them'
        )

    def handle(self, *args, **options):
        user_id = options.get('user_id')
        dry_run = options.get('dry_run')
        
        if dry_run:
            self.stdout.write("DRY RUN: No notifications will be created")
        
        # Get users to process
        if user_id:
            try:
                users = [User.objects.get(id=user_id)]
                self.stdout.write(f"Processing notifications for user ID: {user_id}")
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"User with ID {user_id} not found")
                )
                return
        else:
            # Get all staff users (assuming only staff should get notifications)
            users = User.objects.filter(is_staff=True, is_active=True)
            self.stdout.write(f"Processing notifications for {users.count()} staff users")
        
        total_notifications = 0
        
        for user in users:
            self.stdout.write(f"\nProcessing user: {user.username}")
            
            if not dry_run:
                try:
                    # Generate deadline notifications (includes request status-based alerts)
                    deadline_count = generate_deadline_notifications(user)
                    
                    # Generate payment notifications
                    payment_count = generate_payment_notifications(user)
                    
                    user_total = deadline_count + payment_count
                    total_notifications += user_total
                    
                    if user_total > 0:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  ✓ Generated {deadline_count} deadline notifications, "
                                f"{payment_count} payment notifications"
                            )
                        )
                    else:
                        self.stdout.write("  - No new notifications needed")
                        
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"  ERROR: Error generating notifications: {e}")
                    )
                    logger.error(f"Error generating notifications for user {user.id}: {e}")
            else:
                # Dry run - just show what would be generated
                self.stdout.write("  - Would generate deadline and payment notifications")
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"\nDRY RUN COMPLETE: Would generate notifications for {users.count()} users")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"\nCOMPLETE: Generated {total_notifications} total notifications")
            )
        
        return total_notifications
