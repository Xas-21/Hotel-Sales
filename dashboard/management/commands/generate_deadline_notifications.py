"""
Management command to generate deadline-based notifications.

This command should be run daily to generate notifications for upcoming deadlines.
It's idempotent - can be run multiple times per day without creating duplicates.

Usage:
    python manage.py generate_deadline_notifications
"""
from django.core.management.base import BaseCommand
from dashboard.services.deadline_notifications import generate_all_deadline_notifications


class Command(BaseCommand):
    help = 'Generate deadline-based notifications for payments, offers, check-ins, and agreements'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what notifications would be created without actually creating them',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Starting deadline notification generation...')
        )
        
        if options['dry_run']:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No notifications will be created')
            )
        
        try:
            if options['dry_run']:
                # For dry run, we'd need to modify the service to not create notifications
                # For now, just show the message
                self.stdout.write(
                    self.style.WARNING('Dry run mode not implemented yet - would scan for deadlines')
                )
                return
            
            results = generate_all_deadline_notifications()
            
            self.stdout.write(
                self.style.SUCCESS(f'Successfully created {results["total"]} notifications:')
            )
            self.stdout.write(f'  - Payment deadlines: {results["payments"]}')
            self.stdout.write(f'  - Offer deadlines: {results["offers"]}')
            self.stdout.write(f'  - Group check-ins: {results["checkins"]}')
            self.stdout.write(f'  - Agreement deadlines: {results["agreements"]}')
            
        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f'Error generating notifications: {str(e)}')
            )
            raise