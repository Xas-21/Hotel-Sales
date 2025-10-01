"""
Management command to backfill payment deadlines for existing requests.

This command sets default deadlines for all existing requests that don't have
deadlines set, ensuring the alert system works for all request types.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q
from requests.models import Request as BookingRequest
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Backfill payment deadlines for existing requests without deadlines'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes'
        )
        parser.add_argument(
            '--request-type',
            type=str,
            help='Only update specific request type (e.g., "Group Accommodation")'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force update even if deadlines already exist'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        request_type = options.get('request_type')
        force = options['force']
        
        today = timezone.localdate()
        
        # Build query for requests without deadlines
        query = Q()
        
        if not force:
            # Only update requests missing deadlines
            query = Q(
                Q(offer_acceptance_deadline__isnull=True) |
                Q(deposit_deadline__isnull=True) |
                Q(full_payment_deadline__isnull=True)
            )
        
        if request_type:
            query &= Q(request_type=request_type)
        
        # Get requests to update
        requests_to_update = BookingRequest.objects.filter(query).exclude(status='Cancelled')
        
        if not requests_to_update.exists():
            self.stdout.write(
                self.style.SUCCESS("No requests found that need deadline updates.")
            )
            return
        
        self.stdout.write(f"Found {requests_to_update.count()} requests to update...")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))
        
        updated_count = 0
        
        for request in requests_to_update:
            changes_made = []
            
            # Set offer acceptance deadline (7 days from today)
            if not request.offer_acceptance_deadline or force:
                new_deadline = today + timedelta(days=7)
                if request.offer_acceptance_deadline != new_deadline:
                    if not dry_run:
                        request.offer_acceptance_deadline = new_deadline
                    changes_made.append(f"Offer acceptance: {new_deadline}")
            
            # Set deposit deadline (14 days from today)
            if not request.deposit_deadline or force:
                new_deadline = today + timedelta(days=14)
                if request.deposit_deadline != new_deadline:
                    if not dry_run:
                        request.deposit_deadline = new_deadline
                    changes_made.append(f"Deposit: {new_deadline}")
            
            # Set full payment deadline
            if not request.full_payment_deadline or force:
                if request.check_in_date:
                    # Full payment due 7 days before check-in
                    new_deadline = request.check_in_date - timedelta(days=7)
                else:
                    # Default to 30 days from today if no check-in date
                    new_deadline = today + timedelta(days=30)
                
                if request.full_payment_deadline != new_deadline:
                    if not dry_run:
                        request.full_payment_deadline = new_deadline
                    changes_made.append(f"Full payment: {new_deadline}")
            
            if changes_made:
                updated_count += 1
                self.stdout.write(
                    f"  • {request.confirmation_number or f'ID:{request.id}'} "
                    f"({request.request_type}) - {request.account.name}: "
                    f"{', '.join(changes_made)}"
                )
                
                if not dry_run:
                    request.save(update_fields=[
                        'offer_acceptance_deadline', 
                        'deposit_deadline', 
                        'full_payment_deadline'
                    ])
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"DRY RUN: Would update {updated_count} requests")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Successfully updated {updated_count} requests")
            )
            
            # Show summary by request type
            self.stdout.write("\nSummary by request type:")
            for req_type in BookingRequest.REQUEST_TYPES:
                type_name = req_type[0]
                count = requests_to_update.filter(request_type=type_name).count()
                if count > 0:
                    self.stdout.write(f"  • {type_name}: {count} requests")
