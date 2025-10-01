from datetime import date, timedelta
from decimal import Decimal
import random
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Account
from requests.models import Request as BookingRequest, RoomType, RoomOccupancy, RoomEntry, CancellationReason


class Command(BaseCommand):
    help = "Add extra demo requests: N this month and 5 in September."

    def add_arguments(self, parser):
        parser.add_argument('--this_month', type=int, default=5, help='How many requests to add in current month')
        parser.add_argument('--seed', type=int, default=7)

    def handle(self, *args, **opts):
        random.seed(opts['seed'])
        today = timezone.localdate()
        month_start = today.replace(day=1)

        accounts = list(Account.objects.all())
        if not accounts:
            self.stdout.write(self.style.WARNING('No accounts exist; run seed_demo_data first.'))
            return

        room_type = RoomType.objects.first() or RoomType.objects.create(code='SUP', name='Superior')
        occupancy = RoomOccupancy.objects.first() or RoomOccupancy.objects.create(code='DBL', label='Double', pax_count=2)
        cancel_reason = CancellationReason.objects.first()

        def create_req(dt):
            acc = random.choice(accounts)
            r_type = random.choice([t for t, _ in BookingRequest.REQUEST_TYPES])
            nights = random.randint(1, 3)
            req = BookingRequest(
                request_type=r_type,
                account=acc,
                request_received_date=dt - timedelta(days=3),
                check_in_date=dt,
                check_out_date=dt + timedelta(days=nights),
                status=random.choice([s for s, _ in BookingRequest.STATUS_CHOICES]),
                meal_plan='RO'
            )
            if req.status == 'Cancelled' and cancel_reason:
                req.cancellation_reason_fixed = cancel_reason
            req.set_default_deadlines()
            req.save()
            if r_type != 'Event without Rooms':
                RoomEntry.objects.create(
                    request=req,
                    room_type=room_type,
                    occupancy_type=occupancy,
                    quantity=random.randint(1, 4),
                    rate_per_night=random.choice([250, 350, 420])
                )
                req.update_financial_totals()

        # Add in current month
        count_this = opts['this_month']
        for i in range(count_this):
            day = min(26, 1 + i * 2)
            create_req(month_start.replace(day=day))

        # Add exactly 5 in September of current year (or previous if already past)
        target_year = today.year
        september_start = date(target_year, 9, 1)
        for i in range(5):
            create_req(september_start.replace(day=1 + i * 5))

        self.stdout.write(self.style.SUCCESS('Added extra requests for current month and five in September.'))



