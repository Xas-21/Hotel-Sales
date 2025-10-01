import random
from datetime import timedelta, date
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Account
from requests.models import (
    Request,
    RoomType,
    RoomOccupancy,
    RoomEntry,
    CancellationReason,
    SeriesGroupEntry,
)
from agreements.models import Agreement
from sales_calls.models import SalesCall


class Command(BaseCommand):
    help = "Seed demo data: accounts, requests, sales calls, and agreements for dashboard testing."

    def add_arguments(self, parser):
        parser.add_argument("--accounts", type=int, default=6, help="Number of accounts to create")
        parser.add_argument("--requests", type=int, default=20, help="Number of requests to create")
        parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")

    def handle(self, *args, **options):
        random.seed(options["seed"])
        num_accounts = options["accounts"]
        num_requests = options["requests"]

        self.stdout.write(self.style.MIGRATE_HEADING("Seeding demo data..."))

        # Ensure base config exists
        room_type = RoomType.objects.first() or RoomType.objects.create(code="SUP", name="Superior")
        occupancy = RoomOccupancy.objects.first() or RoomOccupancy.objects.create(code="DBL", label="Double", pax_count=2)
        cancel_reason = CancellationReason.objects.first() or CancellationReason.objects.create(code="client_cancel", label="Client Cancelled", is_refundable=False)

        # Create Accounts
        cities = [c for c, _ in Account.CITY_CHOICES]
        account_types = [t for t, _ in Account.ACCOUNT_TYPES]
        accounts = list(Account.objects.all()[:num_accounts])
        for i in range(len(accounts), num_accounts):
            acc = Account.objects.create(
                name=f"Demo Account {i+1}",
                account_type=random.choice(account_types),
                city=random.choice(cities),
                contact_person=f"Contact {i+1}",
                phone=f"+9665{random.randint(10000000, 99999999)}",
                email=f"demo{i+1}@example.com",
                address="Demo Street, Riyadh",
            )
            accounts.append(acc)

        # Helper for random dates spread across the last, current, and next months
        today = timezone.localdate()
        start_month = today.replace(day=1) - timedelta(days=365)

        def random_date_spread():
            months_offset = random.randint(0, 14)  # spread over ~15 months
            base_month = (start_month.replace(day=15) + timedelta(days=30 * months_offset))
            # clamp day range to avoid invalid dates
            day = random.randint(1, 26)
            return base_month.replace(day=day)

        # Create Agreements (one per account)
        agreement_rate_types = [r for r, _ in Agreement.RATE_TYPES]
        agreement_statuses = [s for s, _ in Agreement.STATUS_CHOICES]
        for acc in accounts:
            start = random_date_spread()
            end = start + timedelta(days=300)
            status = random.choice(agreement_statuses)
            return_deadline = start + timedelta(days=45)
            Agreement.objects.get_or_create(
                account=acc,
                rate_type=random.choice(agreement_rate_types),
                start_date=start,
                end_date=end,
                defaults={
                    "status": status,
                    "return_deadline": return_deadline,
                    "notes": "Seeded demo agreement",
                },
            )

        # Create Requests with diversity
        req_types = [t for t, _ in Request.REQUEST_TYPES]
        statuses = [s for s, _ in Request.STATUS_CHOICES]

        created_requests = []
        for i in range(num_requests):
            acc = random.choice(accounts)
            r_type = random.choice(req_types)
            # dates
            check_in = random_date_spread()
            nights = random.randint(1, 4)
            check_out = check_in + timedelta(days=nights)
            status = random.choice(statuses)

            req = Request(
                request_type=r_type,
                account=acc,
                request_received_date=check_in - timedelta(days=random.randint(1, 20)),
                check_in_date=check_in,
                check_out_date=check_out,
                meal_plan="RO",
                status=status,
                deposit_amount=0,
                paid_amount=0,
                notes="Seeded demo request",
            )

            # For Cancelled, satisfy validation by setting a reason
            if status == "Cancelled":
                req.cancellation_reason_fixed = cancel_reason
            req.set_default_deadlines()
            req.save()

            # Add room entries for financials (except pure event without rooms)
            if r_type != "Event without Rooms":
                RoomEntry.objects.create(
                    request=req,
                    room_type=room_type,
                    occupancy_type=occupancy,
                    quantity=random.randint(1, 5),
                    rate_per_night=random.choice([250, 350, 420, 580]),
                )
            # For series group, add a series entry so totals are computed correctly
            if r_type == "Series Group":
                SeriesGroupEntry.objects.create(
                    request=req,
                    arrival_date=check_in,
                    departure_date=check_out,
                    room_type=room_type,
                    occupancy_type=occupancy,
                    number_of_rooms=random.randint(2, 6),
                    rate_per_night=random.choice([300, 450, 600]),
                )

            # Set paid amounts for Paid/Partially Paid
            if status in ["Paid", "Partially Paid", "Confirmed", "Actual"]:
                # compute totals first
                req.update_financial_totals()
                total = req.total_cost
                if status == "Paid" or status == "Actual":
                    req.paid_amount = total
                elif status == "Partially Paid":
                    req.paid_amount = total * Decimal("0.5")
                elif status == "Confirmed":
                    req.paid_amount = total * Decimal("0.2")
                req.save(update_fields=["paid_amount"])

            # Sometimes set deadlines to be near to trigger alerts
            if status in ["Draft", "Pending", "Partially Paid"]:
                req.offer_acceptance_deadline = timezone.localdate() + timedelta(days=random.randint(1, 10))
                req.deposit_deadline = timezone.localdate() + timedelta(days=random.randint(5, 20))
                # Full payment before check-in
                if req.check_in_date:
                    req.full_payment_deadline = req.check_in_date - timedelta(days=random.randint(3, 10))
                req.save(update_fields=["offer_acceptance_deadline", "deposit_deadline", "full_payment_deadline"])

            # If Paid and check-in passed, mark as Actual
            if status in ["Paid", "Confirmed"] and r_type != "Event without Rooms":
                req.check_and_update_to_actual()

            created_requests.append(req)

        # Create Sales Calls for each account
        subjects = [s for s, _ in SalesCall.MEETING_SUBJECT]
        potentials = [p for p, _ in SalesCall.BUSINESS_POTENTIAL]
        for acc in accounts:
            for _ in range(2):
                visit = random_date_spread()
                SalesCall.objects.create(
                    account=acc,
                    visit_date=visit,
                    city=acc.city or "Riyadh",
                    address="Seeded address",
                    meeting_subject=random.choice(subjects),
                    business_potential=random.choice(potentials),
                    next_steps="Follow up with proposal",
                    detailed_notes="Seeded sales call",
                    follow_up_required=random.choice([True, False]),
                    follow_up_date=visit + timedelta(days=random.randint(5, 30)),
                    follow_up_completed=random.choice([True, False]),
                )

        self.stdout.write(self.style.SUCCESS(
            f"Created {len(accounts)} accounts, {len(created_requests)} requests, "
            f"{Agreement.objects.count()} agreements total, and sales calls for each account."
        ))


