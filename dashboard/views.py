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
    
    # Financial metrics - Total revenue includes both paid and unpaid amounts
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
    recent_requests = BookingRequest.objects.order_by('-created_at')[:20]
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
    if start_date_param and end_date_param:
        try:
            start_date = datetime.strptime(start_date_param, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_param, '%Y-%m-%d').date()
        except ValueError:
            # Fallback to default if date parsing fails
            start_date = today.replace(day=1)
            end_date = today
    else:
        # Predefined periods
        if period_type == 'this_month':
            start_date = today.replace(day=1)
            # Get last day of current month
            if today.month == 12:
                end_date = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end_date = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        elif period_type == 'last_month':
            start_date = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
            end_date = today.replace(day=1) - timedelta(days=1)
        elif period_type == 'last_3_months':
            # Get 3 complete months back from current month (including current month)
            if today.month >= 3:
                start_date = today.replace(month=today.month - 2, day=1)
            else:
                start_date = today.replace(year=today.year - 1, month=12 - (2 - today.month), day=1)
            # End of current month (include current month)
            if today.month == 12:
                end_date = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end_date = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        elif period_type == 'last_6_months':
            # Get 6 complete months back from current month (including current month)
            if today.month >= 6:
                start_date = today.replace(month=today.month - 5, day=1)
            else:
                start_date = today.replace(year=today.year - 1, month=12 - (5 - today.month), day=1)
            # End of current month (include current month)
            if today.month == 12:
                end_date = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end_date = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        elif period_type == 'last_year':
            start_date = today.replace(year=today.year - 1, month=1, day=1)
            end_date = today.replace(year=today.year - 1, month=12, day=31)
        elif period_type == 'last_2_years':
            start_date = today.replace(year=today.year - 2, month=1, day=1)
            end_date = today.replace(year=today.year - 1, month=12, day=31)
        elif period_type == 'this_year':
            start_date = today.replace(month=1, day=1)
            end_date = today.replace(month=12, day=31)
        elif period_type == 'ytd':
            start_date = today.replace(month=1, day=1)
            # Include current month in YTD
            if today.month == 12:
                end_date = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end_date = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        elif period_type == 'qtd':
            # Current quarter - include current month
            current_quarter = (today.month - 1) // 3 + 1
            quarter_start_month = (current_quarter - 1) * 3 + 1
            quarter_end_month = quarter_start_month + 2
            start_date = today.replace(month=quarter_start_month, day=1)
            # Include current month in QTD
            if today.month == 12:
                end_date = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end_date = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        elif period_type == 'next_year':
            start_date = today.replace(year=today.year + 1, month=1, day=1)
            end_date = today.replace(year=today.year + 1, month=12, day=31)
        else:
            # Default to this month
            start_date = today.replace(day=1)
            end_date = today
    
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
    
    # Get current period data
    current_period_requests = BookingRequest.objects.filter(
        Q(status='Confirmed') | Q(status='Paid') | Q(status='Actual'),
        check_in_date__gte=start_date,
        check_in_date__lte=end_date
    ).select_related('account')
    
    # Get previous period data for MoM comparison
    mom_requests = BookingRequest.objects.filter(
        Q(status='Confirmed') | Q(status='Paid') | Q(status='Actual'),
        check_in_date__gte=mom_start,
        check_in_date__lte=mom_end
    ).select_related('account')
    
    # Get same period last year for YoY comparison
    yoy_requests = BookingRequest.objects.filter(
        Q(status='Confirmed') | Q(status='Paid') | Q(status='Actual'),
        check_in_date__gte=yoy_start,
        check_in_date__lte=yoy_end
    ).select_related('account')
    
    # Calculate current period metrics
    current_period_bookings = current_period_requests.count()
    current_period_revenue = current_period_requests.aggregate(total=Sum('total_cost'))['total'] or Decimal('0.00')
    current_period_avg_value = current_period_revenue / current_period_bookings if current_period_bookings > 0 else Decimal('0.00')
    
    # Calculate previous period metrics for MoM comparison
    mom_bookings = mom_requests.count()
    mom_revenue = mom_requests.aggregate(total=Sum('total_cost'))['total'] or Decimal('0.00')
    mom_avg_value = mom_revenue / mom_bookings if mom_bookings > 0 else Decimal('0.00')
    
    # Calculate same period last year metrics for YoY comparison
    yoy_bookings = yoy_requests.count()
    yoy_revenue = yoy_requests.aggregate(total=Sum('total_cost'))['total'] or Decimal('0.00')
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
    
    # Account type breakdown for current period
    account_type_breakdown = {}
    for request in current_period_requests:
        account_type = request.account.account_type
        if account_type not in account_type_breakdown:
            account_type_breakdown[account_type] = {
                'bookings': 0,
                'revenue': Decimal('0.00'),
                'avg_value': Decimal('0.00')
            }
        account_type_breakdown[account_type]['bookings'] += 1
        account_type_breakdown[account_type]['revenue'] += request.total_cost
    
    # Calculate averages for account types
    for account_type in account_type_breakdown:
        if account_type_breakdown[account_type]['bookings'] > 0:
            account_type_breakdown[account_type]['avg_value'] = (
                account_type_breakdown[account_type]['revenue'] / 
                account_type_breakdown[account_type]['bookings']
            )
    
    # Property breakdown (using account names as properties) with MOM calculation
    # Show all accounts by default
    all_accounts = Account.objects.all()
    property_breakdown = {}
    
    # Calculate previous period for MOM comparison
    period_days = (end_date - start_date).days
    prev_end_date = start_date - timedelta(days=1)
    prev_start_date = prev_end_date - timedelta(days=period_days)
    
    # Get previous period requests for MOM calculation
    previous_period_requests = BookingRequest.objects.filter(
        (Q(status='Confirmed') | Q(status='Paid') | Q(status='Actual')) &
        Q(check_in_date__gte=prev_start_date) & Q(check_in_date__lte=prev_end_date)
    ).select_related('account')
    
    # Build previous period breakdown
    previous_breakdown = {}
    for request in previous_period_requests:
        property_name = request.account.name
        if property_name not in previous_breakdown:
            previous_breakdown[property_name] = {
                'revenue': Decimal('0.00'),
            }
        previous_breakdown[property_name]['revenue'] += request.total_cost
    
    # Build current period breakdown
    current_breakdown = {}
    for request in current_period_requests:
        property_name = request.account.name
        if property_name not in current_breakdown:
            current_breakdown[property_name] = {
                'bookings': 0,
                'revenue': Decimal('0.00'),
                'account_type': request.account.account_type
            }
        current_breakdown[property_name]['bookings'] += 1
        current_breakdown[property_name]['revenue'] += request.total_cost
    
    # Build results for all accounts
    for account in all_accounts:
        account_name = account.name
        account_type = account.account_type
        
        # Current period data
        current_data = current_breakdown.get(account_name, {'bookings': 0, 'revenue': Decimal('0.00')})
        current_bookings = current_data['bookings']
        current_revenue = current_data['revenue']
        current_avg_value = (current_revenue / current_bookings) if current_bookings else Decimal('0.00')
        
        # Previous period data
        previous_data = previous_breakdown.get(account_name, {'revenue': Decimal('0.00')})
        previous_revenue = previous_data['revenue']
        
        # Calculate MOM percentage
        if previous_revenue > 0:
            mom_percentage = ((current_revenue - previous_revenue) / previous_revenue) * 100
        elif current_revenue > 0:
            mom_percentage = 100.0  # 100% growth from 0
        else:
            mom_percentage = 0.0
            
        property_breakdown[account_name] = {
            'bookings': current_bookings,
            'revenue': current_revenue,
            'avg_value': current_avg_value,
            'account_type': account_type,
            'mom_percentage': round(mom_percentage, 1)
        }
    
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
        if start_date_param and end_date_param:
            periods_to_show = (end_date - start_date).days + 1
        else:
            periods_to_show = 30  # Default to 30 days
    elif view_type == 'week':
        # For week view, show weekly data
        if start_date_param and end_date_param:
            periods_to_show = ((end_date - start_date).days // 7) + 1
        else:
            periods_to_show = 12  # Default to 12 weeks
    else:  # month view
        # For month view, show monthly data
        if start_date_param and end_date_param:
            periods_to_show = max(1, (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1)
            # Ensure we don't show too many months (cap at 24 for performance)
            periods_to_show = min(periods_to_show, 24)
        elif period_type in ['this_month', 'last_month']:
            periods_to_show = 12
        elif period_type in ['last_3_months']:
            periods_to_show = 3  # Show exactly 3 months
        elif period_type in ['last_6_months']:
            periods_to_show = 6  # Show exactly 6 months
        elif period_type in ['qtd']:
            periods_to_show = 3  # Show exactly 3 months for quarter
        elif period_type in ['this_year', 'ytd', 'last_year', 'next_year']:
            periods_to_show = 12  # Show 12 months for year periods
        elif period_type in ['last_2_years']:
            periods_to_show = 24  # Show 24 months for 2 years
        else:
            periods_to_show = 12
    
    for i in range(periods_to_show):
        # Calculate period start and end based on view type
        if view_type == 'day':
            # For day view, each period is a single day
            if start_date_param and end_date_param:
                period_start = start_date + timedelta(days=i)
                period_end = period_start
            else:
                # Default: last 30 days
                period_start = today - timedelta(days=periods_to_show-i-1)
                period_end = period_start
        elif view_type == 'week':
            # For week view, each period is a week (Monday to Sunday)
            if start_date_param and end_date_param:
                period_start = start_date + timedelta(days=i*7)
                # Find the Monday of this week
                period_start = period_start - timedelta(days=period_start.weekday())
                period_end = period_start + timedelta(days=6)
            else:
                # Default: last 12 weeks
                period_start = today - timedelta(days=(periods_to_show-i)*7)
                period_start = period_start - timedelta(days=period_start.weekday())
                period_end = period_start + timedelta(days=6)
        else:  # month view
            # For month view, each period is a month
            if start_date_param and end_date_param:
                # Calculate target month and year starting from start_date
                target_month = start_date.month + i
                target_year = start_date.year
                # Handle year rollover
                while target_month > 12:
                    target_month -= 12
                    target_year += 1
                period_start = start_date.replace(year=target_year, month=target_month, day=1)
            elif period_type == 'next_year':
                # Calculate target month and year
                target_month = start_date.month + i
                target_year = start_date.year
                # Handle year rollover
                while target_month > 12:
                    target_month -= 12
                    target_year += 1
                period_start = start_date.replace(year=target_year, month=target_month, day=1)
            elif period_type in ['this_year', 'ytd']:
                # For current year periods, go forward from January
                target_month = 1 + i
                target_year = start_date.year
                # Handle year rollover
                while target_month > 12:
                    target_month -= 12
                    target_year += 1
                period_start = start_date.replace(year=target_year, month=target_month, day=1)
            elif period_type in ['last_3_months', 'last_6_months', 'qtd']:
                # For these periods, go forward from start_date to show actual months in the period
                target_month = start_date.month + i
                target_year = start_date.year
                # Handle year rollover
                while target_month > 12:
                    target_month -= 12
                    target_year += 1
                period_start = start_date.replace(year=target_year, month=target_month, day=1)
            elif period_type in ['last_year', 'last_2_years']:
                # For year periods, go forward from start_date
                target_month = start_date.month + i
                target_year = start_date.year
                # Handle year rollover
                while target_month > 12:
                    target_month -= 12
                    target_year += 1
                period_start = start_date.replace(year=target_year, month=target_month, day=1)
            else:
                # For other past periods, go backward from start_date
                period_start = (start_date - timedelta(days=30*i)).replace(day=1)
            
            # Calculate month end
            if period_start.month == 12:
                period_end = period_start.replace(year=period_start.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                period_end = period_start.replace(month=period_start.month + 1, day=1) - timedelta(days=1)
        
        period_requests = BookingRequest.objects.filter(
            Q(status='Confirmed') | Q(status='Paid') | Q(status='Actual'),
            check_in_date__gte=period_start,
            check_in_date__lte=period_end
        )
        
        # Get all request statuses for the same period
        period_draft_requests = BookingRequest.objects.filter(
            status='Draft',
            check_in_date__gte=period_start,
            check_in_date__lte=period_end
        )
        period_pending_requests = BookingRequest.objects.filter(
            status='Pending',
            check_in_date__gte=period_start,
            check_in_date__lte=period_end
        )
        period_partially_paid_requests = BookingRequest.objects.filter(
            status='Partially Paid',
            check_in_date__gte=period_start,
            check_in_date__lte=period_end
        )
        period_paid_requests = BookingRequest.objects.filter(
            status='Paid',
            check_in_date__gte=period_start,
            check_in_date__lte=period_end
        )
        period_confirmed_requests = BookingRequest.objects.filter(
            status='Confirmed',
            check_in_date__gte=period_start,
            check_in_date__lte=period_end
        )
        period_actual_requests = BookingRequest.objects.filter(
            status='Actual',
            check_in_date__gte=period_start,
            check_in_date__lte=period_end
        )
        period_cancelled_requests = BookingRequest.objects.filter(
            status='Cancelled',
            check_in_date__gte=period_start,
            check_in_date__lte=period_end
        )
        
        period_revenue = period_requests.aggregate(total=Sum('total_cost'))['total'] or Decimal('0.00')
        period_bookings = period_requests.count()
        period_rooms = period_requests.aggregate(total=Sum('total_rooms'))['total'] or 0
        
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
        'current_period_name': f"{start_date.strftime('%B %d, %Y')} - {end_date.strftime('%B %d, %Y')}",
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
    date range and optional account search. Shows all accounts by default with real MOM calculations.
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

    # Calculate previous period for MOM comparison
    period_days = (end_date_val - start_date_val).days
    prev_end_date = start_date_val - timedelta(days=1)
    prev_start_date = prev_end_date - timedelta(days=period_days)

    # Get all accounts (for showing all accounts by default)
    all_accounts = Account.objects.all()
    if account_query:
        all_accounts = all_accounts.filter(name__icontains=account_query)

    # Current period requests
    current_requests_qs = BookingRequest.objects.filter(
        (Q(status='Confirmed') | Q(status='Paid') | Q(status='Actual')) &
        Q(check_in_date__gte=start_date_val) & Q(check_in_date__lte=end_date_val)
    ).select_related('account')

    # Previous period requests for MOM calculation
    previous_requests_qs = BookingRequest.objects.filter(
        (Q(status='Confirmed') | Q(status='Paid') | Q(status='Actual')) &
        Q(check_in_date__gte=prev_start_date) & Q(check_in_date__lte=prev_end_date)
    ).select_related('account')

    # Build current period breakdown
    current_breakdown = {}
    for req in current_requests_qs:
        property_name = req.account.name
        if property_name not in current_breakdown:
            current_breakdown[property_name] = {
                'bookings': 0,
                'revenue': Decimal('0.00'),
                'account_type': req.account.account_type,
            }
        current_breakdown[property_name]['bookings'] += 1
        current_breakdown[property_name]['revenue'] += req.total_cost

    # Build previous period breakdown
    previous_breakdown = {}
    for req in previous_requests_qs:
        property_name = req.account.name
        if property_name not in previous_breakdown:
            previous_breakdown[property_name] = {
                'bookings': 0,
                'revenue': Decimal('0.00'),
            }
        previous_breakdown[property_name]['bookings'] += 1
        previous_breakdown[property_name]['revenue'] += req.total_cost

    # Build results for all accounts
    results = []
    for account in all_accounts:
        account_name = account.name
        account_type = account.account_type
        
        # Current period data
        current_data = current_breakdown.get(account_name, {'bookings': 0, 'revenue': Decimal('0.00')})
        current_bookings = current_data['bookings']
        current_revenue = current_data['revenue']
        current_avg_value = (current_revenue / current_bookings) if current_bookings else Decimal('0.00')
        
        # Previous period data
        previous_data = previous_breakdown.get(account_name, {'bookings': 0, 'revenue': Decimal('0.00')})
        previous_revenue = previous_data['revenue']
        
        # Calculate MOM percentage
        if previous_revenue > 0:
            mom_percentage = ((current_revenue - previous_revenue) / previous_revenue) * 100
        elif current_revenue > 0:
            mom_percentage = 100.0  # 100% growth from 0
        else:
            mom_percentage = 0.0
        
        results.append({
            'account_name': account_name,
            'account_type': account_type,
            'bookings': current_bookings,
            'revenue': float(current_revenue),
            'avg_value': float(current_avg_value),
            'mom_percentage': round(mom_percentage, 1),
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
            'url': f'/admin/requests/seriesgroupentry/{entry.id}/change/'
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
            'url': f'/admin/requests/eventagenda/{agenda.id}/change/'
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
