"""
Management command to recalculate financial totals for all requests.

This command fixes any issues with auto-calculation by manually triggering
the update_financial_totals() method for all requests.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from requests.models import Request as BookingRequest
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Recalculate financial totals for all requests'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes'
        )
        parser.add_argument(
            '--request-id',
            type=int,
            help='Only recalculate specific request ID'
        )
        parser.add_argument(
            '--request-type',
            type=str,
            help='Only recalculate specific request type'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        request_id = options.get('request_id')
        request_type = options.get('request_type')
        
        # Build query
        query = BookingRequest.objects.all()
        
        if request_id:
            query = query.filter(id=request_id)
        if request_type:
            query = query.filter(request_type=request_type)
        
        requests_to_update = query.exclude(status='Cancelled')
        
        if not requests_to_update.exists():
            self.stdout.write(
                self.style.SUCCESS("No requests found to recalculate.")
            )
            return
        
        self.stdout.write(f"Found {requests_to_update.count()} requests to recalculate...")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))
        
        updated_count = 0
        
        with transaction.atomic():
            for request in requests_to_update:
                # Store original values for comparison
                original_total_cost = request.total_cost
                original_total_rooms = request.total_rooms
                original_total_room_nights = request.total_room_nights
                
                if not dry_run:
                    # Recalculate totals
                    request.update_financial_totals()
                    
                    # Check if values changed
                    if (request.total_cost != original_total_cost or 
                        request.total_rooms != original_total_rooms or 
                        request.total_room_nights != original_total_room_nights):
                        updated_count += 1
                        
                        self.stdout.write(
                            f"✅ {request.confirmation_number or f'ID:{request.id}'} "
                            f"({request.request_type}) - {request.account.name}"
                        )
                        self.stdout.write(f"   Cost: ${original_total_cost} → ${request.total_cost}")
                        self.stdout.write(f"   Rooms: {original_total_rooms} → {request.total_rooms}")
                        self.stdout.write(f"   Room Nights: {original_total_room_nights} → {request.total_room_nights}")
                        self.stdout.write("")
                    else:
                        self.stdout.write(
                            f"⚪ {request.confirmation_number or f'ID:{request.id}'} "
                            f"({request.request_type}) - {request.account.name} (no changes needed)"
                        )
                else:
                    # Dry run - just show what would be recalculated
                    self.stdout.write(
                        f"🔄 {request.confirmation_number or f'ID:{request.id}'} "
                        f"({request.request_type}) - {request.account.name}"
                    )
                    self.stdout.write(f"   Current: Cost=${request.total_cost}, Rooms={request.total_rooms}, Nights={request.total_room_nights}")
                    updated_count += 1
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"DRY RUN: Would recalculate {updated_count} requests")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Successfully recalculated {updated_count} requests")
            )
            
            # Show summary by request type
            self.stdout.write("\n📊 Summary by request type:")
            for req_type in BookingRequest.REQUEST_TYPES:
                type_name = req_type[0]
                count = requests_to_update.filter(request_type=type_name).count()
                if count > 0:
                    self.stdout.write(f"   • {type_name}: {count} requests")
        
        self.stdout.write("\n🎯 Auto-calculation should now work properly for:")
        self.stdout.write("   • New requests (automatic deadline setting)")
        self.stdout.write("   • Room entry changes (signals)")
        self.stdout.write("   • Transportation changes (signals)")
        self.stdout.write("   • Event agenda changes (signals)")
        self.stdout.write("   • Series group changes (signals)")
