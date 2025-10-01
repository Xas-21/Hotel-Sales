"""
Management command to update request statuses from 'Paid' to 'Actual' 
when the arrival dates arrive.

This command should be run daily (e.g., via cron or scheduled task) to automatically 
transition requests to 'Actual' status when appropriate.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from requests.models import Request as BookingRequest
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Updates request statuses from Paid to Actual when arrival dates arrive'

    def handle(self, *args, **options):
        """
        Process all paid requests and update to 'Actual' if arrival date has passed
        """
        today = timezone.localdate()
        updated_count = 0
        
        # Get all requests with 'Paid' status
        paid_requests = BookingRequest.objects.filter(status='Paid')
        
        self.stdout.write(f"Checking {paid_requests.count()} paid requests for status updates...")
        
        for request in paid_requests:
            try:
                if request.check_and_update_to_actual():
                    updated_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Updated request {request.confirmation_number} to 'Actual' status"
                        )
                    )
                    logger.info(f"Request {request.id} status updated from 'Paid' to 'Actual'")
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"Error updating request {request.id}: {str(e)}"
                    )
                )
                logger.error(f"Failed to update request {request.id}: {str(e)}")
        
        # Summary
        if updated_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nSuccessfully updated {updated_count} request(s) to 'Actual' status"
                )
            )
        else:
            self.stdout.write("No requests needed status updates")
        
        return f"Updated {updated_count} requests"