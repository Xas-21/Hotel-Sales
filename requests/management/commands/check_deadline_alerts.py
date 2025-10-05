"""
Management command to check for deadline alerts based on request status.

This command checks for:
- Draft status: Alert on offer acceptance deadline
- Pending status: Alert on deposit deadline  
- Partially Paid status: Alert on full payment deadline
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q
from requests.models import Request as BookingRequest
from datetime import date, timedelta
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Check for deadline alerts based on request status'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days-ahead',
            type=int,
            default=7,
            help='Number of days ahead to check for upcoming deadlines (default: 7)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be alerted without sending actual alerts'
        )

    def handle(self, *args, **options):
        days_ahead = options['days_ahead']
        dry_run = options['dry_run']
        
        today = date.today()
        alert_date = today + timedelta(days=days_ahead)
        
        self.stdout.write(f"Checking for deadline alerts up to {alert_date}...")
        
        alerts_found = 0
        
        # Draft status: Alert on offer acceptance deadline
        draft_alerts = BookingRequest.objects.filter(
            status='Draft',
            offer_acceptance_deadline__lte=alert_date,
            offer_acceptance_deadline__gte=today
        ).select_related('account')
        
        if draft_alerts.exists():
            alerts_found += draft_alerts.count()
            self.stdout.write(
                self.style.WARNING(
                    f"\n=== DRAFT STATUS ALERTS ({draft_alerts.count()}) ==="
                )
            )
            self.stdout.write("Follow up on offer acceptance deadline:")
            
            for request in draft_alerts:
                days_until = (request.offer_acceptance_deadline - today).days
                self.stdout.write(
                    f"  • {request.confirmation_number} - {request.account.name} "
                    f"(Deadline: {request.offer_acceptance_deadline}, {days_until} days)"
                )
        
        # Pending status: Alert on deposit deadline
        pending_alerts = BookingRequest.objects.filter(
            status='Pending',
            deposit_deadline__lte=alert_date,
            deposit_deadline__gte=today
        ).select_related('account')
        
        if pending_alerts.exists():
            alerts_found += pending_alerts.count()
            self.stdout.write(
                self.style.WARNING(
                    f"\n=== PENDING STATUS ALERTS ({pending_alerts.count()}) ==="
                )
            )
            self.stdout.write("Follow up on deposit deadline:")
            
            for request in pending_alerts:
                days_until = (request.deposit_deadline - today).days
                self.stdout.write(
                    f"  • {request.confirmation_number} - {request.account.name} "
                    f"(Deadline: {request.deposit_deadline}, {days_until} days)"
                )
        
        # Partially Paid status: Alert on full payment deadline
        partially_paid_alerts = BookingRequest.objects.filter(
            status='Partially Paid',
            full_payment_deadline__lte=alert_date,
            full_payment_deadline__gte=today
        ).select_related('account')
        
        if partially_paid_alerts.exists():
            alerts_found += partially_paid_alerts.count()
            self.stdout.write(
                self.style.WARNING(
                    f"\n=== PARTIALLY PAID STATUS ALERTS ({partially_paid_alerts.count()}) ==="
                )
            )
            self.stdout.write("Follow up on full payment deadline:")
            
            for request in partially_paid_alerts:
                days_until = (request.full_payment_deadline - today).days
                self.stdout.write(
                    f"  • {request.confirmation_number} - {request.account.name} "
                    f"(Deadline: {request.full_payment_deadline}, {days_until} days)"
                )
        
        if alerts_found == 0:
            self.stdout.write(
                self.style.SUCCESS("No deadline alerts found for the specified period.")
            )
        else:
            self.stdout.write(
                self.style.WARNING(f"\nTotal alerts found: {alerts_found}")
            )
            
            if dry_run:
                self.stdout.write(
                    self.style.WARNING("DRY RUN: No actual alerts were sent.")
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS("Alerts have been processed.")
                )
        
        return alerts_found
