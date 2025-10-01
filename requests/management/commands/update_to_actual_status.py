"""
Management command to automatically update request status to 'Actual' 
for paid/confirmed requests that have reached their arrival/start date.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from requests.models import Request as BookingRequest, EventAgenda
from datetime import date
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Update request status to Actual for paid/confirmed requests that have reached arrival date'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making actual changes'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        today = date.today()
        
        self.stdout.write(f"Checking for requests to update to 'Actual' status on {today}...")
        
        updated_count = 0
        
        # Check accommodation requests (Group, Individual, Event with Rooms, Series Group)
        accommodation_requests = BookingRequest.objects.filter(
            status__in=['Paid', 'Confirmed'],
            request_type__in=['Group Accommodation', 'Individual Accommodation', 'Event with Rooms', 'Series Group'],
            check_in_date__lte=today
        ).select_related('account')
        
        if accommodation_requests.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"\n=== ACCOMMODATION REQUESTS TO UPDATE ({accommodation_requests.count()}) ==="
                )
            )
            
            for request in accommodation_requests:
                self.stdout.write(
                    f"  • {request.confirmation_number} - {request.account.name} "
                    f"(Check-in: {request.check_in_date}, Status: {request.status})"
                )
                
                if not dry_run:
                    request.status = 'Actual'
                    request.save(update_fields=['status'])
                    updated_count += 1
                    logger.info(f"Updated request {request.confirmation_number} to Actual status")
        
        # Check event-only requests (Event without Rooms)
        event_only_requests = BookingRequest.objects.filter(
            status__in=['Paid', 'Confirmed'],
            request_type='Event without Rooms'
        ).select_related('account')
        
        # For event-only requests, check if any event agenda has reached its date
        event_requests_to_update = []
        for request in event_only_requests:
            # Check if any event agenda has reached its date
            has_started_event = EventAgenda.objects.filter(
                request=request,
                event_date__lte=today
            ).exists()
            
            if has_started_event:
                event_requests_to_update.append(request)
        
        if event_requests_to_update:
            self.stdout.write(
                self.style.WARNING(
                    f"\n=== EVENT-ONLY REQUESTS TO UPDATE ({len(event_requests_to_update)}) ==="
                )
            )
            
            for request in event_requests_to_update:
                # Get the earliest event date for display
                earliest_event = EventAgenda.objects.filter(
                    request=request,
                    event_date__lte=today
                ).order_by('event_date').first()
                
                self.stdout.write(
                    f"  • {request.confirmation_number} - {request.account.name} "
                    f"(Event started: {earliest_event.event_date if earliest_event else 'Unknown'}, Status: {request.status})"
                )
                
                if not dry_run:
                    request.status = 'Actual'
                    request.save(update_fields=['status'])
                    updated_count += 1
                    logger.info(f"Updated event request {request.confirmation_number} to Actual status")
        
        if updated_count == 0 and not dry_run:
            self.stdout.write(
                self.style.SUCCESS("No requests needed to be updated to 'Actual' status.")
            )
        elif dry_run:
            total_potential = accommodation_requests.count() + len(event_requests_to_update)
            self.stdout.write(
                self.style.WARNING(f"\nDRY RUN: {total_potential} requests would be updated to 'Actual' status.")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"\nSuccessfully updated {updated_count} requests to 'Actual' status.")
            )
        
        return updated_count
