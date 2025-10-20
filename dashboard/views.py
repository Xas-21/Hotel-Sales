from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.db.models import Count, Sum, Q, Min
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.urls import reverse
from accounts.models import Account
from requests.models import Request as BookingRequest, SeriesGroupEntry, EventAgenda
from agreements.models import Agreement
from sales_calls.models import SalesCall
from hotel_sales.currency_utils import get_currency_context, convert_currency
from datetime import date, timedelta, datetime
import json
from decimal import Decimal

@login_required
def dashboard_view(request):
    """
    Main dashboard with key metrics and analytics
    """
    # Check if user is staff (required for dashboard access)
    if not request.user.is_staff:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("You need staff permissions to access this dashboard.")
    
    # Create profile if it doesn't exist
    if not hasattr(request.user, 'profile'):
        from accounts.models import UserProfile
        UserProfile.objects.get_or_create(user=request.user)
    # Key metrics
    total_accounts = Account.objects.count()
    total_requests = BookingRequest.objects.count()
    
    # Split agreements into signed vs pending
    signed_agreements = Agreement.objects.filter(status='Signed').count()
    pending_agreements = Agreement.objects.filter(status__in=['Draft', 'Sent']).count()
    total_agreements = Agreement.objects.count()
    
    # Request statistics - treat confirmed, paid, and actual as the same
    confirmed_requests = BookingRequest.objects.filter(Q(status='Confirmed') | Q(status='Paid') | Q(status='Actual')).count()
    cancelled_requests = BookingRequest.objects.filter(status='Cancelled').count()
    paid_requests = BookingRequest.objects.filter(Q(status='Paid') | Q(status='Actual')).count()
    
    # Financial metrics - Dashboard Metrics cards show ALL revenue (rooms + events)
    total_revenue = BookingRequest.objects.exclude(status='Cancelled').aggregate(
        total=Sum('total_cost'))['total'] or 0
    pending_revenue = BookingRequest.objects.filter(
        Q(status='Confirmed') | Q(status='Partially Paid')).aggregate(
        total=Sum('total_cost'))['total'] or 0
    
    # New enhanced financial metrics - confirmed, paid, and actual are treated the same
    cancelled_lost_amount = BookingRequest.objects.filter(status='Cancelled').aggregate(
        total=Sum('total_cost'))['total'] or 0
    confirmed_paid_amount = BookingRequest.objects.filter(Q(status='Confirmed') | Q(status='Paid') | Q(status='Actual')).aggregate(
        total=Sum('total_cost'))['total'] or 0
    
    # Calculate unpaid amounts (total cost minus paid amount for non-cancelled requests)
    unpaid_total = 0
    non_cancelled_requests = BookingRequest.objects.exclude(status='Cancelled').exclude(status='Paid').exclude(status='Actual')
    for req in non_cancelled_requests:
        unpaid_amount = req.total_cost - req.paid_amount
        if unpaid_amount > 0:
            unpaid_total += unpaid_amount
    
    # Request type breakdown
    request_types = BookingRequest.objects.values('request_type').annotate(
        count=Count('id')).order_by('-count')
    
    # Enhanced Analytics Data for new dashboard sections
    
    # Request Segments Analytics (Travel Agent, Company, Government)
    request_segments = BookingRequest.objects.select_related('account').values('account__account_type').annotate(
        count=Count('id')).order_by('-count')
    
    # Request Status Distribution Analytics
    request_status_distribution = BookingRequest.objects.values('status').annotate(
        count=Count('id')).order_by('-count')
    
    # Request Type with Status breakdown
    request_type_status = BookingRequest.objects.values('request_type', 'status').annotate(
        count=Count('id')).order_by('-count')
    
    # Agreements Analytics by Status and Type
    agreement_status_breakdown = Agreement.objects.values('status').annotate(
        count=Count('id')).order_by('-count')
    
    agreement_rate_type_breakdown = Agreement.objects.values('rate_type').annotate(
        count=Count('id')).order_by('-count')
    
    # Sales Calls Analytics by Business Potential and Subject
    sales_calls_by_potential = SalesCall.objects.values('business_potential').annotate(
        count=Count('id')).order_by('-count')
    
    sales_calls_by_subject = SalesCall.objects.values('meeting_subject').annotate(
        count=Count('id')).order_by('-count')
    
    # Follow-up Status Analytics
    follow_up_stats = {
        'required': SalesCall.objects.filter(follow_up_required=True).count(),
        'completed': SalesCall.objects.filter(follow_up_completed=True).count(),
        'pending': SalesCall.objects.filter(follow_up_required=True, follow_up_completed=False).count()
    }
    
    # Recent activity (show more and use scroll in UI)
    # Include event start date for event-type requests
    recent_requests = BookingRequest.objects.select_related('account').prefetch_related('event_agendas').order_by('-created_at')[:20]
    recent_sales_calls = SalesCall.objects.order_by('-visit_date')[:20]
    recent_agreements = Agreement.objects.order_by('-created_at')[:20]
    recent_accounts = Account.objects.order_by('-created_at')[:20]
    
    # Alerts
    approaching_deadlines = Agreement.objects.filter(
        return_deadline__lte=date.today() + timedelta(days=30),
        return_deadline__gte=date.today(),
        status__in=['Draft', 'Sent']
    )
    
    overdue_followups = SalesCall.objects.filter(
        follow_up_required=True,
        follow_up_completed=False,
        follow_up_date__lt=date.today()
    )
    
    # Request deadline alerts based on status
    today = date.today()
    alert_date = today + timedelta(days=7)  # Check next 7 days
    
    # Draft status: Alert on offer acceptance deadline (ALL REQUEST TYPES)
    draft_deadline_alerts = BookingRequest.objects.filter(
        status='Draft',
        offer_acceptance_deadline__lte=alert_date,
        offer_acceptance_deadline__gte=today,
        offer_acceptance_deadline__isnull=False
    ).select_related('account')
    
    # Pending status: Alert on deposit deadline (ALL REQUEST TYPES)
    pending_deadline_alerts = BookingRequest.objects.filter(
        status='Pending',
        deposit_deadline__lte=alert_date,
        deposit_deadline__gte=today,
        deposit_deadline__isnull=False
    ).select_related('account')
    
    # Partially Paid status: Alert on full payment deadline (ALL REQUEST TYPES)
    partially_paid_deadline_alerts = BookingRequest.objects.filter(
        status='Partially Paid',
        full_payment_deadline__lte=alert_date,
        full_payment_deadline__gte=today,
        full_payment_deadline__isnull=False
    ).select_related('account')
    
    # Imminent arrivals (within 1-2 days and today)
    today = date.today()
    tomorrow = today + timedelta(days=1)
    day_after = today + timedelta(days=2)
    
    # Check for arriving requests (check_in_date) - confirmed, paid, and actual are treated the same
    arriving_requests = BookingRequest.objects.filter(
        check_in_date__in=[today, tomorrow, day_after],
        status__in=['Confirmed', 'Paid', 'Actual']
    ).select_related('account')
    
    # Check for starting events (event_date from EventAgenda) - confirmed, paid, and actual are treated the same
    starting_event_agendas = EventAgenda.objects.filter(
        event_date__in=[today, tomorrow, day_after],
        request__status__in=['Confirmed', 'Paid', 'Actual']
    ).select_related('request__account')
    
    # Create normalized arrival data with consistent date access
    normalized_arrivals = []
    seen_ids = set()
    
    # Add regular request arrivals
    for req in arriving_requests:
        if req.id not in seen_ids:
            normalized_arrivals.append({
                'request': req,
                'date': req.check_in_date,
                'type': 'arrival',
                'account': req.account,
                'request_type': req.request_type,
                'id': req.id
            })
            seen_ids.add(req.id)
    
    # Add event starts
    for agenda in starting_event_agendas:
        if agenda.request.id not in seen_ids:
            normalized_arrivals.append({
                'request': agenda.request,
                'date': agenda.event_date,
                'type': 'event',
                'account': agenda.request.account,
                'request_type': agenda.request.request_type,
                'id': agenda.request.id
            })
            seen_ids.add(agenda.request.id)
    
    # Sort by date
    normalized_arrivals.sort(key=lambda x: x['date'])
    
    # Get current currency and convert amounts if needed
    current_currency = get_currency_context(request)['currency_code']
    
    # Convert amounts from SAR to current currency if needed
    if current_currency == 'USD':
        total_revenue = convert_currency(total_revenue, 'SAR', 'USD')
        pending_revenue = convert_currency(pending_revenue, 'SAR', 'USD')
        cancelled_lost_amount = convert_currency(cancelled_lost_amount, 'SAR', 'USD')
        confirmed_paid_amount = convert_currency(confirmed_paid_amount, 'SAR', 'USD')
        unpaid_total = convert_currency(unpaid_total, 'SAR', 'USD')
    
    context = {
        'user': request.user,  # Explicitly pass user to context
        **get_currency_context(request),  # Add currency context
        'total_accounts': total_accounts,
        'total_requests': total_requests,
        'total_agreements': total_agreements,
        'signed_agreements': signed_agreements,
        'pending_agreements': pending_agreements,
        'confirmed_requests': confirmed_requests,
        'cancelled_requests': cancelled_requests,
        'paid_requests': paid_requests,
        'total_revenue': total_revenue,
        'pending_revenue': pending_revenue,
        'cancelled_lost_amount': cancelled_lost_amount,
        'confirmed_paid_amount': confirmed_paid_amount,
        'unpaid_total': unpaid_total,
        'request_types': request_types,
        'recent_requests': recent_requests,
        'recent_sales_calls': recent_sales_calls,
        'recent_agreements': recent_agreements,
        'recent_accounts': recent_accounts,
        'approaching_deadlines': approaching_deadlines,
        'overdue_followups': overdue_followups,
        'draft_deadline_alerts': draft_deadline_alerts,
        'pending_deadline_alerts': pending_deadline_alerts,
        'partially_paid_deadline_alerts': partially_paid_deadline_alerts,
        'imminent_arrivals': normalized_arrivals,
        'today': today,
        'tomorrow': tomorrow,
        
        # New Analytics Section Data
        'request_segments': request_segments,
        'request_status_distribution': request_status_distribution,
        'request_type_status': request_type_status,
        'agreement_status_breakdown': agreement_status_breakdown,
        'agreement_rate_type_breakdown': agreement_rate_type_breakdown,
        'sales_calls_by_potential': sales_calls_by_potential,
        'sales_calls_by_subject': sales_calls_by_subject,
        'follow_up_stats': follow_up_stats,
    }
    
    # ===== COMPREHENSIVE BOOKING ANALYTICS CALCULATIONS =====
    
    # Get date ranges for analytics - support custom date ranges
    today = date.today()
    
    # Check for custom date range parameters
    start_date_param = request.GET.get('start_date')
    end_date_param = request.GET.get('end_date')
    period_type = request.GET.get('period', 'this_month')
    view_type = request.GET.get('view', 'month')  # Default to month view
    
    # Set default date ranges based on period type
    current_period_start = None
    current_period_end = None
    
    if start_date_param and end_date_param:
        try:
            start_date = datetime.strptime(start_date_param, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_param, '%Y-%m-%d').date()
            current_period_start = start_date
            current_period_end = end_date
        except ValueError:
            # Fallback to default if date parsing fails
            start_date = today.replace(day=1)
            end_date = today
            current_period_start = start_date
            current_period_end = end_date
    else:
        # Predefined periods
        if period_type == 'this_month':
            # For Current Period: Show only current month
            # For Charts: Show 4 months for better visualization
            current_month_start = today.replace(day=1)
            if today.month == 12:
                current_month_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                current_month_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
            
            # Chart range: 4 months for better line visualization
            chart_start = current_month_start - timedelta(days=90)  # Approximately 3 months
            chart_start = chart_start.replace(day=1)  # First day of that month
            
            start_date = chart_start  # For charts
            end_date = current_month_end  # For charts
            
            # Current Period: Only current month
            current_period_start = current_month_start
            current_period_end = current_month_end
            
        elif period_type == 'last_month':
            # For Current Period: Show only last month
            # For Charts: Show 4 months for better visualization
            last_month_start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
            last_month_end = today.replace(day=1) - timedelta(days=1)
            
            # Chart range: 4 months for better line visualization
            chart_start = last_month_start - timedelta(days=90)  # Approximately 3 months
            chart_start = chart_start.replace(day=1)  # First day of that month
            
            start_date = chart_start  # For charts
            end_date = last_month_end  # For charts
            
            # Current Period: Only last month
            current_period_start = last_month_start
            current_period_end = last_month_end
        elif period_type == 'last_year':
            start_date = today.replace(year=today.year - 1, month=1, day=1)
            end_date = today.replace(year=today.year - 1, month=12, day=31)
            current_period_start = start_date
            current_period_end = end_date
        elif period_type == 'last_2_years':
            start_date = today.replace(year=today.year - 2, month=1, day=1)
            end_date = today.replace(year=today.year - 1, month=12, day=31)
            current_period_start = start_date
            current_period_end = end_date
        elif period_type == 'this_year':
            start_date = today.replace(month=1, day=1)
            end_date = today.replace(month=12, day=31)
            current_period_start = start_date
            current_period_end = end_date
        elif period_type == 'ytd':
            start_date = today.replace(month=1, day=1)
            # End at current date (not end of current month)
            end_date = today
            current_period_start = start_date
            current_period_end = end_date
        elif period_type == 'qtd':
            # Current quarter - from start of quarter to current date (quarter-to-date)
            # Q1: Jan-Mar (1-3), Q2: Apr-Jun (4-6), Q3: Jul-Sep (7-9), Q4: Oct-Dec (10-12)
            # But you want Q4 to start in August, so: Q1: Jan-Mar, Q2: Apr-Jun, Q3: Jul-Sep, Q4: Aug-Oct
            if today.month <= 3:
                quarter_start_month = 1  # Q1: January
            elif today.month <= 6:
                quarter_start_month = 4  # Q2: April
            elif today.month <= 9:
                quarter_start_month = 7  # Q3: July
            else:
                quarter_start_month = 8  # Q4: August (as you requested)
            
            start_date = today.replace(month=quarter_start_month, day=1)
            # End at current date (not end of quarter)
            end_date = today
            current_period_start = start_date
            current_period_end = end_date
        elif period_type == 'next_year':
            start_date = today.replace(year=today.year + 1, month=1, day=1)
            end_date = today.replace(year=today.year + 1, month=12, day=31)
            current_period_start = start_date
            current_period_end = end_date
        else:
            # Default to this month
            start_date = today.replace(day=1)
            end_date = today
            current_period_start = start_date
            current_period_end = end_date
    
    # For day/week views on this_month and last_month, use only the actual month
    if view_type in ['day', 'week'] and period_type in ['this_month', 'last_month']:
        start_date = current_period_start
        end_date = current_period_end
    
    # Calculate comparison periods
    period_days = (end_date - start_date).days
    
    # For MoM comparison - get previous period of same length
    if period_days <= 31:  # Monthly or shorter periods
        mom_start = start_date - timedelta(days=period_days + 1)
        mom_end = start_date - timedelta(days=1)
    else:  # Longer periods
        mom_start = start_date - timedelta(days=period_days + 1)
        mom_end = start_date - timedelta(days=1)
    
    # For YoY comparison - get same period last year
    yoy_start = start_date.replace(year=start_date.year - 1)
    yoy_end = end_date.replace(year=end_date.year - 1)
    
    # Get current period data (ACCOMMODATION ONLY - exclude Event Only)
    # Include: Group Accommodation, Individual Accommodation, Event with Rooms, Series Group
    current_accommodation = BookingRequest.objects.filter(
        Q(status='Confirmed') | Q(status='Paid') | Q(status='Actual'),
        request_type__in=['Group Accommodation', 'Individual Accommodation', 'Event with Rooms'],
        check_in_date__lt=end_date,
        check_out_date__gt=start_date
    ).select_related('account')
    
    current_series_ids = SeriesGroupEntry.objects.filter(
        request__status__in=['Confirmed', 'Paid', 'Actual'],
        request__request_type='Series Group',
        arrival_date__lt=end_date,
        departure_date__gt=start_date
    ).values_list('request_id', flat=True).distinct()
    current_series = BookingRequest.objects.filter(id__in=current_series_ids).select_related('account')
    
    current_period_requests = current_accommodation | current_series
    
    # Get previous period data for MoM comparison
    mom_accommodation = BookingRequest.objects.filter(
        Q(status='Confirmed') | Q(status='Paid') | Q(status='Actual'),
        request_type__in=['Group Accommodation', 'Individual Accommodation', 'Event with Rooms'],
        check_in_date__lt=mom_end,
        check_out_date__gt=mom_start
    ).select_related('account')
    
    mom_series_ids = SeriesGroupEntry.objects.filter(
        request__status__in=['Confirmed', 'Paid', 'Actual'],
        request__request_type='Series Group',
        arrival_date__lt=mom_end,
        departure_date__gt=mom_start
    ).values_list('request_id', flat=True).distinct()
    mom_series = BookingRequest.objects.filter(id__in=mom_series_ids).select_related('account')
    
    mom_requests = mom_accommodation | mom_series
    
    # Get same period last year for YoY comparison
    yoy_accommodation = BookingRequest.objects.filter(
        Q(status='Confirmed') | Q(status='Paid') | Q(status='Actual'),
        request_type__in=['Group Accommodation', 'Individual Accommodation', 'Event with Rooms'],
        check_in_date__lt=yoy_end,
        check_out_date__gt=yoy_start
    ).select_related('account')
    
    yoy_series_ids = SeriesGroupEntry.objects.filter(
        request__status__in=['Confirmed', 'Paid', 'Actual'],
        request__request_type='Series Group',
        arrival_date__lt=yoy_end,
        departure_date__gt=yoy_start
    ).values_list('request_id', flat=True).distinct()
    yoy_series = BookingRequest.objects.filter(id__in=yoy_series_ids).select_related('account')
    
    yoy_requests = yoy_accommodation | yoy_series
    
    # Calculate current period metrics - using accommodation revenue only (rooms + transportation, NO events)
    current_period_bookings = current_period_requests.count()
    current_period_revenue = Decimal('0.00')
    for req in current_period_requests:
        if req.request_type == 'Series Group':
            # For Series Group: calculate revenue PER NIGHT that falls within period
            for series_entry in req.series_entries.all():
                total_entry_cost = series_entry.get_total_cost()
                nights = series_entry.nights
                revenue_per_night = total_entry_cost / nights if nights > 0 else Decimal('0.00')
                
                # Count nights within the period
                current_night = series_entry.arrival_date
                while current_night < series_entry.departure_date:
                    if start_date <= current_night <= end_date:
                        current_period_revenue += revenue_per_night
                    current_night += timedelta(days=1)
            
            # Add transportation costs (only once for first entry in period)
            if req.series_entries.exists():
                first_entry = req.series_entries.order_by('arrival_date').first()
                if first_entry and start_date <= first_entry.arrival_date <= end_date:
                    current_period_revenue += req.get_transportation_total()
        else:
            # For other accommodation requests: calculate revenue PER NIGHT that falls within period
            if req.check_in_date and req.check_out_date and req.nights:
                total_room_cost = req.get_room_total()
                nights = req.nights
                revenue_per_night = total_room_cost / nights if nights > 0 else Decimal('0.00')
                
                # Count nights within the period
                current_night = req.check_in_date
                while current_night < req.check_out_date:
                    if start_date <= current_night <= end_date:
                        current_period_revenue += revenue_per_night
                    current_night += timedelta(days=1)
                
                # Add transportation costs (only once for check-in date in period)
                if start_date <= req.check_in_date <= end_date:
                    current_period_revenue += req.get_transportation_total()
    current_period_avg_value = current_period_revenue / current_period_bookings if current_period_bookings > 0 else Decimal('0.00')
    
    # Calculate previous period metrics for MoM comparison - using accommodation revenue only
    mom_bookings = mom_requests.count()
    mom_revenue = Decimal('0.00')
    for req in mom_requests:
        if req.request_type == 'Series Group':
            # For Series Group: calculate revenue PER NIGHT that falls within period
            for series_entry in req.series_entries.all():
                total_entry_cost = series_entry.get_total_cost()
                nights = series_entry.nights
                revenue_per_night = total_entry_cost / nights if nights > 0 else Decimal('0.00')
                
                # Count nights within the MoM period
                current_night = series_entry.arrival_date
                while current_night < series_entry.departure_date:
                    if mom_start <= current_night <= mom_end:
                        mom_revenue += revenue_per_night
                    current_night += timedelta(days=1)
            
            # Add transportation costs (only once for first entry in period)
            if req.series_entries.exists():
                first_entry = req.series_entries.order_by('arrival_date').first()
                if first_entry and mom_start <= first_entry.arrival_date <= mom_end:
                    mom_revenue += req.get_transportation_total()
        else:
            # For other accommodation requests: calculate revenue PER NIGHT that falls within MoM period
            if req.check_in_date and req.check_out_date and req.nights:
                total_room_cost = req.get_room_total()
                nights = req.nights
                revenue_per_night = total_room_cost / nights if nights > 0 else Decimal('0.00')
                
                # Count nights within the MoM period
                current_night = req.check_in_date
                while current_night < req.check_out_date:
                    if mom_start <= current_night <= mom_end:
                        mom_revenue += revenue_per_night
                    current_night += timedelta(days=1)
                
                # Add transportation costs (only once for check-in date in period)
                if mom_start <= req.check_in_date <= mom_end:
                    mom_revenue += req.get_transportation_total()
    mom_avg_value = mom_revenue / mom_bookings if mom_bookings > 0 else Decimal('0.00')
    
    # Calculate same period last year metrics for YoY comparison - using accommodation revenue only
    yoy_bookings = yoy_requests.count()
    yoy_revenue = Decimal('0.00')
    for req in yoy_requests:
        if req.request_type == 'Series Group':
            # For Series Group: calculate revenue PER NIGHT that falls within period
            for series_entry in req.series_entries.all():
                total_entry_cost = series_entry.get_total_cost()
                nights = series_entry.nights
                revenue_per_night = total_entry_cost / nights if nights > 0 else Decimal('0.00')
                
                # Count nights within the YoY period
                current_night = series_entry.arrival_date
                while current_night < series_entry.departure_date:
                    if yoy_start <= current_night <= yoy_end:
                        yoy_revenue += revenue_per_night
                    current_night += timedelta(days=1)
            
            # Add transportation costs (only once for first entry in period)
            if req.series_entries.exists():
                first_entry = req.series_entries.order_by('arrival_date').first()
                if first_entry and yoy_start <= first_entry.arrival_date <= yoy_end:
                    yoy_revenue += req.get_transportation_total()
        else:
            # For other accommodation requests: calculate revenue PER NIGHT that falls within YoY period
            if req.check_in_date and req.check_out_date and req.nights:
                total_room_cost = req.get_room_total()
                nights = req.nights
                revenue_per_night = total_room_cost / nights if nights > 0 else Decimal('0.00')
                
                # Count nights within the YoY period
                current_night = req.check_in_date
                while current_night < req.check_out_date:
                    if yoy_start <= current_night <= yoy_end:
                        yoy_revenue += revenue_per_night
                    current_night += timedelta(days=1)
                
                # Add transportation costs (only once for check-in date in period)
                if yoy_start <= req.check_in_date <= yoy_end:
                    yoy_revenue += req.get_transportation_total()
    yoy_avg_value = yoy_revenue / yoy_bookings if yoy_bookings > 0 else Decimal('0.00')
    
    # Calculate MoM changes
    mom_bookings_change = current_period_bookings - mom_bookings
    mom_bookings_change_pct = (mom_bookings_change / mom_bookings * 100) if mom_bookings > 0 else Decimal('0.00')
    mom_revenue_change = current_period_revenue - mom_revenue
    mom_revenue_change_pct = (mom_revenue_change / mom_revenue * 100) if mom_revenue > 0 else Decimal('0.00')
    
    # Calculate YoY changes
    yoy_bookings_change = current_period_bookings - yoy_bookings
    yoy_bookings_change_pct = (yoy_bookings_change / yoy_bookings * 100) if yoy_bookings > 0 else Decimal('0.00')
    yoy_revenue_change = current_period_revenue - yoy_revenue
    yoy_revenue_change_pct = (yoy_revenue_change / yoy_revenue * 100) if yoy_revenue > 0 else Decimal('0.00')
    
    # Calculate occupancy rate (simplified - using total room nights)
    current_period_room_nights = current_period_requests.aggregate(total=Sum('total_room_nights'))['total'] or 0
    # For demo purposes, assume 1000 available room nights per month
    available_room_nights = 1000
    occupancy_rate = (current_period_room_nights / available_room_nights * 100) if available_room_nights > 0 else Decimal('0.00')
    
    # Account type breakdown for current period - accommodation revenue only
    account_type_breakdown = {}
    for req in current_period_requests:
        account_type = req.account.account_type
        if account_type not in account_type_breakdown:
            account_type_breakdown[account_type] = {
                'bookings': 0,
                'revenue': Decimal('0.00'),
                'avg_value': Decimal('0.00')
            }
        account_type_breakdown[account_type]['bookings'] += 1
        
        # Calculate accommodation revenue based on request type
        if req.request_type == 'Series Group':
            # For Series Group: calculate revenue PER NIGHT that falls within period
            for series_entry in req.series_entries.all():
                total_entry_cost = series_entry.get_total_cost()
                nights = series_entry.nights
                revenue_per_night = total_entry_cost / nights if nights > 0 else Decimal('0.00')
                
                # Count nights within the period
                current_night = series_entry.arrival_date
                while current_night < series_entry.departure_date:
                    if start_date <= current_night <= end_date:
                        account_type_breakdown[account_type]['revenue'] += revenue_per_night
                    current_night += timedelta(days=1)
            
            # Add transportation costs (only once for first entry in period)
            if req.series_entries.exists():
                first_entry = req.series_entries.order_by('arrival_date').first()
                if first_entry and start_date <= first_entry.arrival_date <= end_date:
                    account_type_breakdown[account_type]['revenue'] += req.get_transportation_total()
        else:
            # For other accommodation requests: calculate revenue PER NIGHT that falls within period
            if req.check_in_date and req.check_out_date and req.nights:
                total_room_cost = req.get_room_total()
                nights = req.nights
                revenue_per_night = total_room_cost / nights if nights > 0 else Decimal('0.00')
                
                # Count nights within the period
                current_night = req.check_in_date
                while current_night < req.check_out_date:
                    if start_date <= current_night <= end_date:
                        account_type_breakdown[account_type]['revenue'] += revenue_per_night
                    current_night += timedelta(days=1)
                
                # Add transportation costs (only once for check-in date in period)
                if start_date <= req.check_in_date <= end_date:
                    account_type_breakdown[account_type]['revenue'] += req.get_transportation_total()
    
    # Calculate averages for account types
    for account_type in account_type_breakdown:
        if account_type_breakdown[account_type]['bookings'] > 0:
            account_type_breakdown[account_type]['avg_value'] = (
                account_type_breakdown[account_type]['revenue'] / 
                account_type_breakdown[account_type]['bookings']
            )
    
    # Property breakdown (using account names as properties) - accommodation revenue only
    property_breakdown = {}
    for req in current_period_requests:
        property_name = req.account.name
        if property_name not in property_breakdown:
            property_breakdown[property_name] = {
                'bookings': 0,
                'revenue': Decimal('0.00'),
                'avg_value': Decimal('0.00'),
                'account_type': req.account.account_type
            }
        property_breakdown[property_name]['bookings'] += 1
        
        # Calculate accommodation revenue based on request type
        if req.request_type == 'Series Group':
            # For Series Group: calculate revenue PER NIGHT that falls within period
            for series_entry in req.series_entries.all():
                total_entry_cost = series_entry.get_total_cost()
                nights = series_entry.nights
                revenue_per_night = total_entry_cost / nights if nights > 0 else Decimal('0.00')
                
                # Count nights within the period
                current_night = series_entry.arrival_date
                while current_night < series_entry.departure_date:
                    if start_date <= current_night <= end_date:
                        property_breakdown[property_name]['revenue'] += revenue_per_night
                    current_night += timedelta(days=1)
            
            # Add transportation costs (only once for first entry in period)
            if req.series_entries.exists():
                first_entry = req.series_entries.order_by('arrival_date').first()
                if first_entry and start_date <= first_entry.arrival_date <= end_date:
                    property_breakdown[property_name]['revenue'] += req.get_transportation_total()
        else:
            # For other accommodation requests: calculate revenue PER NIGHT that falls within period
            if req.check_in_date and req.check_out_date and req.nights:
                total_room_cost = req.get_room_total()
                nights = req.nights
                revenue_per_night = total_room_cost / nights if nights > 0 else Decimal('0.00')
                
                # Count nights within the period
                current_night = req.check_in_date
                while current_night < req.check_out_date:
                    if start_date <= current_night <= end_date:
                        property_breakdown[property_name]['revenue'] += revenue_per_night
                    current_night += timedelta(days=1)
                
                # Add transportation costs (only once for check-in date in period)
                if start_date <= req.check_in_date <= end_date:
                    property_breakdown[property_name]['revenue'] += req.get_transportation_total()
    
    # Calculate averages and MoM for properties
    for property_name in property_breakdown:
        if property_breakdown[property_name]['bookings'] > 0:
            property_breakdown[property_name]['avg_value'] = (
                property_breakdown[property_name]['revenue'] / 
                property_breakdown[property_name]['bookings']
            )
        
        # Calculate MoM percentage for this property
        current_revenue = property_breakdown[property_name]['revenue']
        previous_revenue = Decimal('0.00')
        
        # Get previous period revenue for this property - accommodation revenue only
        previous_requests = mom_requests.filter(account__name=property_name)
        for prev_request in previous_requests:
            # Calculate accommodation revenue based on request type
            if prev_request.request_type == 'Series Group':
                # For Series Group: calculate revenue PER NIGHT that falls within MoM period
                for series_entry in prev_request.series_entries.all():
                    total_entry_cost = series_entry.get_total_cost()
                    nights = series_entry.nights
                    revenue_per_night = total_entry_cost / nights if nights > 0 else Decimal('0.00')
                    
                    # Count nights within the MoM period
                    current_night = series_entry.arrival_date
                    while current_night < series_entry.departure_date:
                        if mom_start <= current_night <= mom_end:
                            previous_revenue += revenue_per_night
                        current_night += timedelta(days=1)
                
                # Add transportation costs (only once for first entry in period)
                if prev_request.series_entries.exists():
                    first_entry = prev_request.series_entries.order_by('arrival_date').first()
                    if first_entry and mom_start <= first_entry.arrival_date <= mom_end:
                        previous_revenue += prev_request.get_transportation_total()
            else:
                # For other accommodation requests: calculate revenue PER NIGHT that falls within MoM period
                if prev_request.check_in_date and prev_request.check_out_date and prev_request.nights:
                    total_room_cost = prev_request.get_room_total()
                    nights = prev_request.nights
                    revenue_per_night = total_room_cost / nights if nights > 0 else Decimal('0.00')
                    
                    # Count nights within the MoM period
                    current_night = prev_request.check_in_date
                    while current_night < prev_request.check_out_date:
                        if mom_start <= current_night <= mom_end:
                            previous_revenue += revenue_per_night
                        current_night += timedelta(days=1)
                    
                    # Add transportation costs (only once for check-in date in period)
                    if mom_start <= prev_request.check_in_date <= mom_end:
                        previous_revenue += prev_request.get_transportation_total()
        
        if previous_revenue > 0:
            mom_percentage = float(((current_revenue - previous_revenue) / previous_revenue) * 100)
        else:
            mom_percentage = 100.0 if current_revenue > 0 else 0.0
        
        property_breakdown[property_name]['mom_percentage'] = mom_percentage
        
        # Apply currency conversion if needed
        if current_currency == 'USD':
            property_breakdown[property_name]['revenue'] = convert_currency(
                property_breakdown[property_name]['revenue'], 'SAR', 'USD'
            )
            property_breakdown[property_name]['avg_value'] = convert_currency(
                property_breakdown[property_name]['avg_value'], 'SAR', 'USD'
            )
    
    # Revenue trend data - dynamic based on selected period
    revenue_trend_data = []
    bookings_trend_data = []
    rooms_trend_data = []
    trend_labels = []
    
    # Request status trend data
    draft_trend_data = []
    pending_trend_data = []
    partially_paid_trend_data = []
    paid_trend_data = []
    confirmed_trend_data = []
    actual_trend_data = []
    cancelled_trend_data = []
    
    # Calculate number of periods to show based on period type and view granularity
    if view_type == 'day':
        # For day view, show daily data
            periods_to_show = (end_date - start_date).days + 1
    elif view_type == 'week':
        # For week view, show weekly data
            periods_to_show = ((end_date - start_date).days // 7) + 1
    else:  # month view
        # For month view, show monthly data
            periods_to_show = max(1, (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1)
            # Ensure we don't show too many months (cap at 24 for performance)
            periods_to_show = min(periods_to_show, 24)
    
    for i in range(periods_to_show):
        # Calculate period start and end based on view type
        if view_type == 'day':
            # For day view, each period is a single day
            period_start = start_date + timedelta(days=i)
            # For day view, period_end is the same as period_start (single day)
            # We'll use period_start for both start and end when counting nights
            period_end = period_start
        elif view_type == 'week':
            # For week view, each period is a week (Monday to Sunday)
            period_start = start_date + timedelta(days=i*7)
            # Find the Monday of this week
            period_start = period_start - timedelta(days=period_start.weekday())
            period_end = period_start + timedelta(days=6)
        else:  # month view
            # For month view, each period is a month
            # Calculate target month and year starting from start_date
            target_month = start_date.month + i
            target_year = start_date.year
            # Handle year rollover
            while target_month > 12:
                target_month -= 12
                target_year += 1
            period_start = start_date.replace(year=target_year, month=target_month, day=1)
            
            # Calculate month end
            if period_start.month == 12:
                period_end = period_start.replace(year=period_start.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                period_end = period_start.replace(month=period_start.month + 1, day=1) - timedelta(days=1)
        
        # Filter ACCOMMODATION requests only (exclude Event Only/Event without Rooms)
        # Comprehensive Booking Analytics Dashboard shows room accommodations only
        # Events are tracked separately in Event Management page
        
        # For day view: use <= to include same-day check-ins/arrivals
        # For other views: use < to match the broader period
        # Determine the filtering end date based on view type
        filter_end_date = period_end if view_type != 'day' else period_end + timedelta(days=1)
        
        # Group Accommodation, Individual Accommodation, Event with Rooms
        # Check if ANY night of the stay falls within the period (not just check-in date)
        accommodation_requests = BookingRequest.objects.filter(
            Q(status='Confirmed') | Q(status='Paid') | Q(status='Actual'),
            request_type__in=['Group Accommodation', 'Individual Accommodation', 'Event with Rooms'],
            check_in_date__lt=filter_end_date,  # Check-in before filter end
            check_out_date__gt=period_start  # Check-out after period starts
        )
        
        # Series Group (check if ANY night of the stay falls within the period)
        series_group_request_ids = SeriesGroupEntry.objects.filter(
            request__status__in=['Confirmed', 'Paid', 'Actual'],
            request__request_type='Series Group',
            arrival_date__lt=filter_end_date,  # Arrival before filter end
            departure_date__gt=period_start  # Departure after period starts
        ).values_list('request_id', flat=True).distinct()
        series_group_requests = BookingRequest.objects.filter(id__in=series_group_request_ids)
        
        # Combine accommodation requests only (NO Event Only requests)
        period_requests = accommodation_requests | series_group_requests
        
        # Get all request statuses for the same period (ACCOMMODATION only - no Event Only)
        # Use filter_end_date for all queries to ensure consistent filtering
        
        # Draft requests
        draft_accommodation = BookingRequest.objects.filter(
            status='Draft',
            request_type__in=['Group Accommodation', 'Individual Accommodation', 'Event with Rooms'],
            check_in_date__lt=filter_end_date,
            check_out_date__gt=period_start
        )
        draft_series_ids = SeriesGroupEntry.objects.filter(
            request__status='Draft',
            request__request_type='Series Group',
            arrival_date__lt=filter_end_date,
            departure_date__gt=period_start
        ).values_list('request_id', flat=True).distinct()
        draft_series = BookingRequest.objects.filter(id__in=draft_series_ids)
        period_draft_requests = draft_accommodation | draft_series
        
        # Pending requests
        pending_accommodation = BookingRequest.objects.filter(
            status='Pending',
            request_type__in=['Group Accommodation', 'Individual Accommodation', 'Event with Rooms'],
            check_in_date__lt=filter_end_date,
            check_out_date__gt=period_start
        )
        pending_series_ids = SeriesGroupEntry.objects.filter(
            request__status='Pending',
            request__request_type='Series Group',
            arrival_date__lt=filter_end_date,
            departure_date__gt=period_start
        ).values_list('request_id', flat=True).distinct()
        pending_series = BookingRequest.objects.filter(id__in=pending_series_ids)
        period_pending_requests = pending_accommodation | pending_series
        
        # Partially Paid requests
        partially_paid_accommodation = BookingRequest.objects.filter(
            status='Partially Paid',
            request_type__in=['Group Accommodation', 'Individual Accommodation', 'Event with Rooms'],
            check_in_date__lt=filter_end_date,
            check_out_date__gt=period_start
        )
        partially_paid_series_ids = SeriesGroupEntry.objects.filter(
            request__status='Partially Paid',
            request__request_type='Series Group',
            arrival_date__lt=filter_end_date,
            departure_date__gt=period_start
        ).values_list('request_id', flat=True).distinct()
        partially_paid_series = BookingRequest.objects.filter(id__in=partially_paid_series_ids)
        period_partially_paid_requests = partially_paid_accommodation | partially_paid_series
        
        # Paid requests
        paid_accommodation = BookingRequest.objects.filter(
            status='Paid',
            request_type__in=['Group Accommodation', 'Individual Accommodation', 'Event with Rooms'],
            check_in_date__lt=filter_end_date,
            check_out_date__gt=period_start
        )
        paid_series_ids = SeriesGroupEntry.objects.filter(
            request__status='Paid',
            request__request_type='Series Group',
            arrival_date__lt=filter_end_date,
            departure_date__gt=period_start
        ).values_list('request_id', flat=True).distinct()
        paid_series = BookingRequest.objects.filter(id__in=paid_series_ids)
        period_paid_requests = paid_accommodation | paid_series
        
        # Confirmed requests
        confirmed_accommodation = BookingRequest.objects.filter(
            status='Confirmed',
            request_type__in=['Group Accommodation', 'Individual Accommodation', 'Event with Rooms'],
            check_in_date__lt=filter_end_date,
            check_out_date__gt=period_start
        )
        confirmed_series_ids = SeriesGroupEntry.objects.filter(
            request__status='Confirmed',
            request__request_type='Series Group',
            arrival_date__lt=filter_end_date,
            departure_date__gt=period_start
        ).values_list('request_id', flat=True).distinct()
        confirmed_series = BookingRequest.objects.filter(id__in=confirmed_series_ids)
        period_confirmed_requests = confirmed_accommodation | confirmed_series
        
        # Actual requests
        actual_accommodation = BookingRequest.objects.filter(
            status='Actual',
            request_type__in=['Group Accommodation', 'Individual Accommodation', 'Event with Rooms'],
            check_in_date__lt=filter_end_date,
            check_out_date__gt=period_start
        )
        actual_series_ids = SeriesGroupEntry.objects.filter(
            request__status='Actual',
            request__request_type='Series Group',
            arrival_date__lt=filter_end_date,
            departure_date__gt=period_start
        ).values_list('request_id', flat=True).distinct()
        actual_series = BookingRequest.objects.filter(id__in=actual_series_ids)
        period_actual_requests = actual_accommodation | actual_series
        
        # Cancelled requests
        cancelled_accommodation = BookingRequest.objects.filter(
            status='Cancelled',
            request_type__in=['Group Accommodation', 'Individual Accommodation', 'Event with Rooms'],
            check_in_date__lt=filter_end_date,
            check_out_date__gt=period_start
        )
        cancelled_series_ids = SeriesGroupEntry.objects.filter(
            request__status='Cancelled',
            request__request_type='Series Group',
            arrival_date__lt=filter_end_date,
            departure_date__gt=period_start
        ).values_list('request_id', flat=True).distinct()
        cancelled_series = BookingRequest.objects.filter(id__in=cancelled_series_ids)
        period_cancelled_requests = cancelled_accommodation | cancelled_series
        
        # Calculate accommodation-only revenue (rooms + transportation, exclude events)
        period_revenue = Decimal('0.00')
        for req in period_requests:
            if req.request_type == 'Series Group':
                # For Series Group: calculate revenue PER NIGHT, not just on arrival date
                for series_entry in req.series_entries.all():
                    # Calculate revenue per night for this entry
                    total_entry_cost = series_entry.get_total_cost()
                    nights = series_entry.nights
                    revenue_per_night = total_entry_cost / nights if nights > 0 else Decimal('0.00')
                    
                    # Loop through each night of the stay
                    current_night = series_entry.arrival_date
                    while current_night < series_entry.departure_date:
                        # If this night falls within the current period, add revenue for this night
                        if period_start <= current_night <= period_end:
                            period_revenue += revenue_per_night
                        current_night += timedelta(days=1)
                
                # Add transportation costs proportionally if any (only once, distributed across all nights)
                # For simplicity, we'll add transportation to the first period that contains any entry
                # This ensures it's counted once and not duplicated
                if req.series_entries.exists():
                    first_entry = req.series_entries.order_by('arrival_date').first()
                    if first_entry and period_start <= first_entry.arrival_date <= period_end:
                        period_revenue += req.get_transportation_total()
            else:
                # For other accommodation requests: calculate revenue PER NIGHT that falls within this period
                if req.check_in_date and req.check_out_date and req.nights:
                    total_room_cost = req.get_room_total()
                    nights = req.nights
                    revenue_per_night = total_room_cost / nights if nights > 0 else Decimal('0.00')
                    
                    # Loop through each night of the stay
                    current_night = req.check_in_date
                    while current_night < req.check_out_date:
                        # If this night falls within the current period, add revenue for this night
                        if period_start <= current_night <= period_end:
                            period_revenue += revenue_per_night
                        current_night += timedelta(days=1)
                    
                    # Add transportation costs (only once for check-in date in period)
                    if period_start <= req.check_in_date <= period_end:
                        period_revenue += req.get_transportation_total()
        
        period_bookings = period_requests.count()
        
        # Calculate rooms correctly - ALL requests count PER NIGHT, not just check-in/arrival date
        period_rooms = 0
        for req in period_requests:
            if req.request_type == 'Series Group':
                # For Series Group: count rooms for EACH NIGHT of the stay that falls within this period
                for series_entry in req.series_entries.all():
                    # Get all nights of this entry's stay
                    current_night = series_entry.arrival_date
                    # Loop through each night of the stay
                    while current_night < series_entry.departure_date:
                        # If this night falls within the current period, count the rooms
                        if period_start <= current_night <= period_end:
                            period_rooms += series_entry.number_of_rooms
                        current_night += timedelta(days=1)
            else:
                # For other accommodation requests: count rooms for EACH NIGHT that falls within this period
                if req.check_in_date and req.check_out_date:
                    current_night = req.check_in_date
                    while current_night < req.check_out_date:
                        # If this night falls within the current period, count the rooms
                        if period_start <= current_night <= period_end:
                            period_rooms += req.total_rooms or 0
                        current_night += timedelta(days=1)
        
        # Count each status
        period_draft = period_draft_requests.count()
        period_pending = period_pending_requests.count()
        period_partially_paid = period_partially_paid_requests.count()
        period_paid = period_paid_requests.count()
        period_confirmed = period_confirmed_requests.count()
        period_actual = period_actual_requests.count()
        period_cancelled = period_cancelled_requests.count()
        
        # Generate appropriate label based on view type
        if view_type == 'day':
            label = period_start.strftime('%b %d')
        elif view_type == 'week':
            label = period_start.strftime('%b %d')
        else:  # month view
            label = period_start.strftime('%b %Y')
        
        # Always append in chronological order (left-to-right oldest to newest)
        revenue_trend_data.append(float(period_revenue))
        bookings_trend_data.append(period_bookings)
        rooms_trend_data.append(period_rooms)
        draft_trend_data.append(period_draft)
        pending_trend_data.append(period_pending)
        partially_paid_trend_data.append(period_partially_paid)
        paid_trend_data.append(period_paid)
        confirmed_trend_data.append(period_confirmed)
        actual_trend_data.append(period_actual)
        cancelled_trend_data.append(period_cancelled)
        trend_labels.append(label)
    
    # Simple forecast calculation (next month prediction)
    if len(revenue_trend_data) >= 3:
        # Simple linear trend
        recent_revenue = revenue_trend_data[-3:]
        recent_bookings = bookings_trend_data[-3:]
        
        revenue_trend = (recent_revenue[-1] - recent_revenue[0]) / 2 if len(recent_revenue) > 1 else 0
        bookings_trend = (recent_bookings[-1] - recent_bookings[0]) / 2 if len(recent_bookings) > 1 else 0
        
        forecast_revenue = max(0, recent_revenue[-1] + revenue_trend)
        forecast_bookings = max(0, recent_bookings[-1] + bookings_trend)
    else:
        forecast_revenue = float(current_period_revenue)
        forecast_bookings = current_period_bookings
    
    # Convert analytics KPIs amounts if needed
    if current_currency == 'USD':
        current_period_revenue = convert_currency(current_period_revenue, 'SAR', 'USD')
        current_period_avg_value = convert_currency(current_period_avg_value, 'SAR', 'USD')
        mom_revenue_change = convert_currency(mom_revenue_change, 'SAR', 'USD')
        yoy_revenue_change = convert_currency(yoy_revenue_change, 'SAR', 'USD')
    
    # Add analytics data to context
    context.update({
        # KPI Summary Cards Data
        'analytics_kpis': {
            'total_bookings': current_period_bookings,
            'total_revenue': current_period_revenue,
            'avg_booking_value': current_period_avg_value,
            'occupancy_rate': occupancy_rate,
            'mom_bookings_change': mom_bookings_change,
            'mom_bookings_change_pct': mom_bookings_change_pct,
            'mom_revenue_change': mom_revenue_change,
            'mom_revenue_change_pct': mom_revenue_change_pct,
            'yoy_bookings_change': yoy_bookings_change,
            'yoy_bookings_change_pct': yoy_bookings_change_pct,
            'yoy_revenue_change': yoy_revenue_change,
            'yoy_revenue_change_pct': yoy_revenue_change_pct,
        },
        
        # Date range information
        'date_range': {
            'start_date': start_date,
            'end_date': end_date,
            'period_type': period_type,
            'is_custom_range': bool(start_date_param and end_date_param),
            'mom_start': mom_start,
            'mom_end': mom_end,
            'yoy_start': yoy_start,
            'yoy_end': yoy_end,
        },
        
        # View type information
        'view_type': view_type,
        
        # Chart Data
        'revenue_trend_data': revenue_trend_data,
        'bookings_trend_data': bookings_trend_data,
        'rooms_trend_data': rooms_trend_data,
        'trend_labels': trend_labels,
        
        # Request Status Trend Data
        'draft_trend_data': draft_trend_data,
        'pending_trend_data': pending_trend_data,
        'partially_paid_trend_data': partially_paid_trend_data,
        'paid_trend_data': paid_trend_data,
        'confirmed_trend_data': confirmed_trend_data,
        'actual_trend_data': actual_trend_data,
        'cancelled_trend_data': cancelled_trend_data,
        
        # Breakdown Data
        'account_type_breakdown': account_type_breakdown,
        'property_breakdown': property_breakdown,
        
        # Forecast Data
        'forecast_data': {
            'predicted_revenue': convert_currency(forecast_revenue, 'SAR', current_currency) if current_currency == 'USD' else forecast_revenue,
            'predicted_bookings': forecast_bookings,
            'confidence_level': 75,  # Simplified confidence level
        },
        
        # Date ranges for display
        'current_period_name': f"{current_period_start.strftime('%B %d, %Y')} - {current_period_end.strftime('%B %d, %Y')}",
        'mom_period_name': f"{mom_start.strftime('%B %d, %Y')} - {mom_end.strftime('%B %d, %Y')}",
        'yoy_period_name': f"{yoy_start.strftime('%B %d, %Y')} - {yoy_end.strftime('%B %d, %Y')}",
    })
    
    return render(request, 'dashboard/dashboard.html', context)

def api_request_chart_data(request):
    """
    API endpoint for request chart data
    """
    request_data = BookingRequest.objects.values('request_type').annotate(
        count=Count('id')).order_by('request_type')
    
    labels = [item['request_type'] for item in request_data]
    data = [item['count'] for item in request_data]
    
    return JsonResponse({
        'labels': labels,
        'data': data
    })

def api_status_chart_data(request):
    """
    API endpoint for status chart data
    """
    status_data = BookingRequest.objects.values('status').annotate(
        count=Count('id')).order_by('status')
    
    labels = [item['status'] for item in status_data]
    data = [item['count'] for item in status_data]
    
    return JsonResponse({
        'labels': labels,
        'data': data
    })

def health_check(request):
    """
    Simple health check endpoint for deployment monitoring
    """
    return HttpResponse("OK", status=200)

@login_required
def api_property_performance(request):
    """
    Independent endpoint to compute performance by account profile with its own
    date range and optional account search. Not tied to the main date selector.
    Uses per-night distribution for all accommodation types including Series Group.
    Query params:
      - start_date (YYYY-MM-DD)
      - end_date (YYYY-MM-DD)
      - account (substring to filter account name, case-insensitive)
    """
    # Parse dates with defaults
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        if start_date_str and end_date_str:
            start_date_val = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date_val = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        else:
            today_val = date.today()
            start_date_val = today_val.replace(month=1, day=1)
            end_date_val = today_val
    except ValueError:
        return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)

    account_query = request.GET.get('account', '').strip()

    # Get current currency setting
    current_currency = request.session.get('currency', 'SAR')

    # Calculate previous period for MoM comparison
    period_days = (end_date_val - start_date_val).days
    mom_start_date = start_date_val - timedelta(days=period_days + 1)
    mom_end_date = start_date_val - timedelta(days=1)

    # Current period requests - accommodation types (using per-night filtering)
    current_accommodation = BookingRequest.objects.filter(
        Q(status='Confirmed') | Q(status='Paid') | Q(status='Actual'),
        request_type__in=['Group Accommodation', 'Individual Accommodation', 'Event with Rooms'],
        check_in_date__lt=end_date_val + timedelta(days=1),
        check_out_date__gt=start_date_val
    ).select_related('account')

    # Current period Series Group requests
    current_series_ids = SeriesGroupEntry.objects.filter(
        request__status__in=['Confirmed', 'Paid', 'Actual'],
        request__request_type='Series Group',
        arrival_date__lt=end_date_val + timedelta(days=1),
        departure_date__gt=start_date_val
    ).values_list('request_id', flat=True).distinct()
    current_series = BookingRequest.objects.filter(id__in=current_series_ids).select_related('account')
    
    # Apply account filter if provided
    if account_query:
        current_accommodation = current_accommodation.filter(account__name__icontains=account_query)
        current_series = current_series.filter(account__name__icontains=account_query)
    
    # Previous period requests - accommodation types
    previous_accommodation = BookingRequest.objects.filter(
        Q(status='Confirmed') | Q(status='Paid') | Q(status='Actual'),
        request_type__in=['Group Accommodation', 'Individual Accommodation', 'Event with Rooms'],
        check_in_date__lt=mom_end_date + timedelta(days=1),
        check_out_date__gt=mom_start_date
    ).select_related('account')
    
    # Previous period Series Group requests
    previous_series_ids = SeriesGroupEntry.objects.filter(
        request__status__in=['Confirmed', 'Paid', 'Actual'],
        request__request_type='Series Group',
        arrival_date__lt=mom_end_date + timedelta(days=1),
        departure_date__gt=mom_start_date
    ).values_list('request_id', flat=True).distinct()
    previous_series = BookingRequest.objects.filter(id__in=previous_series_ids).select_related('account')
    
    # Apply account filter if provided
    if account_query:
        previous_accommodation = previous_accommodation.filter(account__name__icontains=account_query)
        previous_series = previous_series.filter(account__name__icontains=account_query)

    # Build current period breakdown using per-night distribution
    current_breakdown = {}
    
    # Process accommodation requests
    for req in current_accommodation:
        property_name = req.account.name
        if property_name not in current_breakdown:
            current_breakdown[property_name] = {
                'bookings': 0,
                'revenue': Decimal('0.00'),
                'account_type': req.account.account_type,
            }
        current_breakdown[property_name]['bookings'] += 1
        
        # Calculate revenue PER NIGHT that falls within period
        if req.check_in_date and req.check_out_date and req.nights:
            total_room_cost = req.get_room_total()
            nights = req.nights
            revenue_per_night = total_room_cost / nights if nights > 0 else Decimal('0.00')
            
            # Count nights within the period
            current_night = req.check_in_date
            while current_night < req.check_out_date:
                if start_date_val <= current_night <= end_date_val:
                    current_breakdown[property_name]['revenue'] += revenue_per_night
                current_night += timedelta(days=1)
            
            # Add transportation costs (only once for check-in date in period)
            if start_date_val <= req.check_in_date <= end_date_val:
                current_breakdown[property_name]['revenue'] += req.get_transportation_total()
    
    # Process Series Group requests
    for req in current_series:
        property_name = req.account.name
        if property_name not in current_breakdown:
            current_breakdown[property_name] = {
                'bookings': 0,
                'revenue': Decimal('0.00'),
                'account_type': req.account.account_type,
            }
        current_breakdown[property_name]['bookings'] += 1
        
        # Calculate revenue PER NIGHT for each series entry
        for series_entry in req.series_entries.all():
            total_entry_cost = series_entry.get_total_cost()
            nights = series_entry.nights
            revenue_per_night = total_entry_cost / nights if nights > 0 else Decimal('0.00')
            
            # Count nights within the period
            current_night = series_entry.arrival_date
            while current_night < series_entry.departure_date:
                if start_date_val <= current_night <= end_date_val:
                    current_breakdown[property_name]['revenue'] += revenue_per_night
                current_night += timedelta(days=1)
        
        # Add transportation costs (only once for first entry in period)
        if req.series_entries.exists():
            first_entry = req.series_entries.order_by('arrival_date').first()
            if first_entry and start_date_val <= first_entry.arrival_date <= end_date_val:
                current_breakdown[property_name]['revenue'] += req.get_transportation_total()

    # Build previous period breakdown using per-night distribution
    previous_breakdown = {}
    
    # Process accommodation requests
    for req in previous_accommodation:
        property_name = req.account.name
        if property_name not in previous_breakdown:
            previous_breakdown[property_name] = {
                'bookings': 0,
                'revenue': Decimal('0.00'),
            }
        previous_breakdown[property_name]['bookings'] += 1
        
        # Calculate revenue PER NIGHT that falls within MoM period
        if req.check_in_date and req.check_out_date and req.nights:
            total_room_cost = req.get_room_total()
            nights = req.nights
            revenue_per_night = total_room_cost / nights if nights > 0 else Decimal('0.00')
            
            # Count nights within the MoM period
            current_night = req.check_in_date
            while current_night < req.check_out_date:
                if mom_start_date <= current_night <= mom_end_date:
                    previous_breakdown[property_name]['revenue'] += revenue_per_night
                current_night += timedelta(days=1)
            
            # Add transportation costs (only once for check-in date in period)
            if mom_start_date <= req.check_in_date <= mom_end_date:
                previous_breakdown[property_name]['revenue'] += req.get_transportation_total()
    
    # Process Series Group requests
    for req in previous_series:
        property_name = req.account.name
        if property_name not in previous_breakdown:
            previous_breakdown[property_name] = {
                'bookings': 0,
                'revenue': Decimal('0.00'),
            }
        previous_breakdown[property_name]['bookings'] += 1
        
        # Calculate revenue PER NIGHT for each series entry
        for series_entry in req.series_entries.all():
            total_entry_cost = series_entry.get_total_cost()
            nights = series_entry.nights
            revenue_per_night = total_entry_cost / nights if nights > 0 else Decimal('0.00')
            
            # Count nights within the MoM period
            current_night = series_entry.arrival_date
            while current_night < series_entry.departure_date:
                if mom_start_date <= current_night <= mom_end_date:
                    previous_breakdown[property_name]['revenue'] += revenue_per_night
                current_night += timedelta(days=1)
        
        # Add transportation costs (only once for first entry in period)
        if req.series_entries.exists():
            first_entry = req.series_entries.order_by('arrival_date').first()
            if first_entry and mom_start_date <= first_entry.arrival_date <= mom_end_date:
                previous_breakdown[property_name]['revenue'] += req.get_transportation_total()

    # Finalize results with MoM calculations
    results = []
    for name, data in current_breakdown.items():
        bookings = data['bookings']
        revenue = data['revenue']
        avg_value = (revenue / bookings) if bookings else Decimal('0.00')
        
        # Calculate MoM percentage
        previous_revenue = previous_breakdown.get(name, {}).get('revenue', Decimal('0.00'))
        if previous_revenue > 0:
            mom_percentage = float(((revenue - previous_revenue) / previous_revenue) * 100)
        else:
            mom_percentage = 100.0 if revenue > 0 else 0.0
        
        # Convert currency if needed
        if current_currency == 'USD':
            revenue = convert_currency(revenue, 'SAR', 'USD')
            avg_value = convert_currency(avg_value, 'SAR', 'USD')
        
        results.append({
            'account_name': name,
            'account_type': data['account_type'],
            'bookings': bookings,
            'revenue': float(revenue),
            'avg_value': float(avg_value),
            'mom_percentage': mom_percentage,
        })

    # Sort by revenue desc
    results.sort(key=lambda x: x['revenue'], reverse=True)

    return JsonResponse({'results': results})

def api_health_check(request):
    """
    API health check endpoint for deployment monitoring
    """
    return JsonResponse({"status": "healthy", "service": "hotel_sales"}, status=200)

@login_required
def calendar_view(request):
    """
    Calendar view displaying groups, events, and sales calls
    """
    return render(request, 'dashboard/calendar.html')

@login_required
def api_calendar_events(request):
    """
    API endpoint for calendar events data with date range filtering
    """
    # Get date range from query parameters (expected from FullCalendar)
    start_str = request.GET.get('start')
    end_str = request.GET.get('end')
    
    if not start_str or not end_str:
        return JsonResponse({'error': 'Missing start or end date parameters'}, status=400)
    
    try:
        # Parse date strings in YYYY-MM-DD format from FullCalendar
        # Handle both with and without time components
        start_date = datetime.fromisoformat(start_str.split('T')[0]).date()
        end_date = datetime.fromisoformat(end_str.split('T')[0]).date()
    except (ValueError, AttributeError):
        try:
            # Fallback for simple YYYY-MM-DD format
            from datetime import datetime as dt
            start_date = dt.strptime(start_str, '%Y-%m-%d').date()
            end_date = dt.strptime(end_str, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({'error': 'Invalid date format'}, status=400)
    
    events = []
    
    # 1. Group Accommodation requests (based on arrival/check-in dates)
    # Use gte/lt for proper exclusive end range semantics
    group_requests = BookingRequest.objects.filter(
        request_type='Group Accommodation',
        check_in_date__gte=start_date,
        check_in_date__lt=end_date
    ).exclude(status='Cancelled').select_related('account')
    
    for req in group_requests:
        events.append({
            'id': f'group_{req.id}',
            'type': 'group',
            'title': f'Group: {req.account.name}',
            'start': req.check_in_date.isoformat(),
            'allDay': True,
            'color': '#0d6efd',
            'url': f'/admin/requests/request/{req.id}/change/'
        })
    
    # 2. Series Group entries (based on arrival dates) - exclude cancelled requests
    series_entries = SeriesGroupEntry.objects.filter(
        arrival_date__gte=start_date,
        arrival_date__lt=end_date
    ).exclude(request__status='Cancelled').select_related('request__account')
    
    for entry in series_entries:
        events.append({
            'id': f'series_{entry.id}',
            'type': 'series',
            'title': f'Series: {entry.request.account.name}',
            'start': entry.arrival_date.isoformat(),
            'allDay': True,
            'color': '#6f42c1',
            'url': f'/admin/requests/seriesgrouprequest/{entry.request.id}/change/'
        })
    
    # 3. Event agendas (query directly for efficiency) - one calendar item per agenda date
    event_agendas = EventAgenda.objects.filter(
        event_date__gte=start_date,
        event_date__lt=end_date
    ).exclude(request__status='Cancelled').select_related('request__account')
    
    for agenda in event_agendas:
        events.append({
            'id': f'agenda_{agenda.id}',
            'type': 'event',
            'title': f'Event: {agenda.request.account.name}',
            'start': agenda.event_date.isoformat(),
            'allDay': True,
            'color': '#fd7e14',
            'url': f'/admin/requests/request/{agenda.request.id}/change/'
        })
    
    # 4. Sales Calls (based on visit dates)
    sales_calls = SalesCall.objects.filter(
        visit_date__gte=start_date,
        visit_date__lt=end_date
    ).select_related('account')
    
    for call in sales_calls:
        events.append({
            'id': f'salescall_{call.id}',
            'type': 'salescall',
            'title': f'Sales Call: {call.account.name}',
            'start': call.visit_date.isoformat(),
            'allDay': True,
            'color': '#198754',
            'url': f'/admin/sales_calls/salescall/{call.id}/change/'
        })
    
    response = JsonResponse(events, safe=False)
    # Prevent caching to ensure fresh data
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

@login_required
def api_update_request_status(request):
    """
    API endpoint to update request status from dashboard
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    try:
        import json
        data = json.loads(request.body)
        request_id = data.get('request_id')
        new_status = data.get('status')
        
        if not request_id or not new_status:
            return JsonResponse({'error': 'Missing request_id or status'}, status=400)
        
        # Get the request object
        req = BookingRequest.objects.get(id=request_id)
        
        # Validate status
        valid_statuses = dict(BookingRequest.STATUS_CHOICES).keys()
        if new_status not in valid_statuses:
            return JsonResponse({'error': 'Invalid status'}, status=400)
        
        # Update status
        req.status = new_status
        req.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Request status updated to {new_status}',
            'new_status': new_status
        })
        
    except BookingRequest.DoesNotExist:
        return JsonResponse({'error': 'Request not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def api_update_agreement_status(request):
    """
    API endpoint to update agreement status from dashboard
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    try:
        import json
        data = json.loads(request.body)
        agreement_id = data.get('agreement_id')
        new_status = data.get('status')
        
        if not agreement_id or not new_status:
            return JsonResponse({'error': 'Missing agreement_id or status'}, status=400)
        
        # Get the agreement object
        agreement = Agreement.objects.get(id=agreement_id)
        
        # Validate status
        valid_statuses = dict(Agreement.STATUS_CHOICES).keys()
        if new_status not in valid_statuses:
            return JsonResponse({'error': 'Invalid status'}, status=400)
        
        # Update status
        agreement.status = new_status
        agreement.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Agreement status updated to {new_status}',
            'new_status': new_status
        })
        
    except Agreement.DoesNotExist:
        return JsonResponse({'error': 'Agreement not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def logout_view(request):
    """
    Custom logout view that logs out user and redirects to dashboard
    """
    from django.contrib.auth import logout
    
    # Handle both GET and POST requests
    if request.method in ['GET', 'POST']:
        logout(request)
        return redirect('dashboard')
    
    # If somehow another method is used, still logout
    logout(request)
    return redirect('dashboard')

@login_required
def api_deadline_alerts(request):
    """
    API endpoint for deadline alerts based on request status
    """
    if not request.user.is_staff:
        return JsonResponse({'error': 'Staff permissions required'}, status=403)
    
    today = date.today()
    days_ahead = int(request.GET.get('days_ahead', 7))
    alert_date = today + timedelta(days=days_ahead)
    
    alerts = {
        'draft_alerts': [],
        'pending_alerts': [],
        'partially_paid_alerts': []
    }
    
    # Draft status: Alert on offer acceptance deadline (ALL REQUEST TYPES)
    draft_requests = BookingRequest.objects.filter(
        status='Draft',
        offer_acceptance_deadline__lte=alert_date,
        offer_acceptance_deadline__gte=today,
        offer_acceptance_deadline__isnull=False
    ).select_related('account')
    
    for req in draft_requests:
        days_until = (req.offer_acceptance_deadline - today).days
        alerts['draft_alerts'].append({
            'id': req.id,
            'confirmation_number': req.confirmation_number,
            'account_name': req.account.name if req.account else 'No Account',
            'request_type': req.request_type,
            'deadline': req.offer_acceptance_deadline.isoformat(),
            'days_until': days_until,
            'message': f'Follow up on offer acceptance deadline for {req.request_type}'
        })
    
    # Pending status: Alert on deposit deadline (ALL REQUEST TYPES)
    pending_requests = BookingRequest.objects.filter(
        status='Pending',
        deposit_deadline__lte=alert_date,
        deposit_deadline__gte=today,
        deposit_deadline__isnull=False
    ).select_related('account')
    
    for req in pending_requests:
        days_until = (req.deposit_deadline - today).days
        alerts['pending_alerts'].append({
            'id': req.id,
            'confirmation_number': req.confirmation_number,
            'account_name': req.account.name if req.account else 'No Account',
            'request_type': req.request_type,
            'deadline': req.deposit_deadline.isoformat(),
            'days_until': days_until,
            'message': f'Follow up on deposit deadline for {req.request_type}'
        })
    
    # Partially Paid status: Alert on full payment deadline (ALL REQUEST TYPES)
    partially_paid_requests = BookingRequest.objects.filter(
        status='Partially Paid',
        full_payment_deadline__lte=alert_date,
        full_payment_deadline__gte=today,
        full_payment_deadline__isnull=False
    ).select_related('account')
    
    for req in partially_paid_requests:
        days_until = (req.full_payment_deadline - today).days
        alerts['partially_paid_alerts'].append({
            'id': req.id,
            'confirmation_number': req.confirmation_number,
            'account_name': req.account.name if req.account else 'No Account',
            'request_type': req.request_type,
            'deadline': req.full_payment_deadline.isoformat(),
            'days_until': days_until,
            'message': f'Follow up on full payment deadline for {req.request_type}'
        })
    
    total_alerts = len(alerts['draft_alerts']) + len(alerts['pending_alerts']) + len(alerts['partially_paid_alerts'])
    
    return JsonResponse({
        'alerts': alerts,
        'total_alerts': total_alerts,
        'days_checked': days_ahead
    })

@login_required
def api_generate_notifications(request):
    """
    API endpoint to manually generate notifications for the current user
    """
    if not request.user.is_staff:
        return JsonResponse({'error': 'Staff permissions required'}, status=403)
    
    try:
        from dashboard.api_views import generate_deadline_notifications, generate_payment_notifications
        
        # Generate notifications
        deadline_count = generate_deadline_notifications(request.user)
        payment_count = generate_payment_notifications(request.user)
        
        total_generated = deadline_count + payment_count
        
        return JsonResponse({
            'success': True,
            'generated': {
                'deadline_notifications': deadline_count,
                'payment_notifications': payment_count,
                'total': total_generated
            },
            'message': f'Generated {total_generated} notifications'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def calendar_view(request):
    """
    Calendar view for displaying all events and requests.
    """
    return render(request, 'dashboard/calendar.html')


@login_required
def api_calendar_events(request):
    """
    API endpoint for calendar events data with date range filtering
    """
    # Get date range from query parameters (expected from FullCalendar)
    start_str = request.GET.get('start')
    end_str = request.GET.get('end')
    
    if not start_str or not end_str:
        return JsonResponse({'error': 'Missing start or end date parameters'}, status=400)
    
    try:
        # Parse date strings in YYYY-MM-DD format from FullCalendar
        # Handle both with and without time components
        start_date = datetime.fromisoformat(start_str.split('T')[0]).date()
        end_date = datetime.fromisoformat(end_str.split('T')[0]).date()
    except (ValueError, AttributeError):
        try:
            # Fallback for simple YYYY-MM-DD format
            start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_str, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({'error': 'Invalid date format'}, status=400)
    
    events = []
    
    # 1. Group Accommodation requests (based on arrival/check-in dates)
    # Use gte/lt for proper exclusive end range semantics
    group_requests = BookingRequest.objects.filter(
        request_type='Group Accommodation',
        check_in_date__gte=start_date,
        check_in_date__lt=end_date
    ).exclude(status='Cancelled').select_related('account')
    
    for req in group_requests:
        events.append({
            'id': f'group_{req.id}',
            'type': 'group',
            'title': f'Group: {req.account.name}',
            'start': req.check_in_date.isoformat(),
            'allDay': True,
            'color': '#0d6efd',
            'url': f'/admin/requests/request/{req.id}/change/'
        })
    
    # 2. Series Group entries (based on arrival dates) - exclude cancelled requests
    series_entries = SeriesGroupEntry.objects.filter(
        arrival_date__gte=start_date,
        arrival_date__lt=end_date
    ).exclude(request__status='Cancelled').select_related('request__account')
    
    for entry in series_entries:
        events.append({
            'id': f'series_{entry.id}',
            'type': 'series',
            'title': f'Series: {entry.request.account.name}',
            'start': entry.arrival_date.isoformat(),
            'allDay': True,
            'color': '#6f42c1',
            'url': f'/admin/requests/seriesgrouprequest/{entry.request.id}/change/'
        })
    
    # 3. Event agendas (query directly for efficiency) - one calendar item per agenda date
    event_agendas = EventAgenda.objects.filter(
        event_date__gte=start_date,
        event_date__lt=end_date
    ).exclude(request__status='Cancelled').select_related('request__account')
    
    for agenda in event_agendas:
        events.append({
            'id': f'agenda_{agenda.id}',
            'type': 'event',
            'title': f'Event: {agenda.request.account.name}',
            'start': agenda.event_date.isoformat(),
            'allDay': True,
            'color': '#fd7e14',
            'url': f'/admin/requests/request/{agenda.request.id}/change/'
        })
    
    # 4. Sales Calls (based on visit dates)
    sales_calls = SalesCall.objects.filter(
        visit_date__gte=start_date,
        visit_date__lt=end_date
    ).select_related('account')
    
    for call in sales_calls:
        events.append({
            'id': f'salescall_{call.id}',
            'type': 'salescall',
            'title': f'Sales Call: {call.account.name}',
            'start': call.visit_date.isoformat(),
            'allDay': True,
            'color': '#198754',
            'url': f'/admin/sales_calls/salescall/{call.id}/change/'
        })
    
    return JsonResponse(events, safe=False)
