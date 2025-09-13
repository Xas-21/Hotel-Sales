from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.db.models import Count, Sum, Q, Min
from django.contrib.admin.views.decorators import staff_member_required
from django.urls import reverse
from accounts.models import Account
from requests.models import Request, SeriesGroupEntry, EventAgenda
from agreements.models import Agreement
from sales_calls.models import SalesCall
from datetime import date, timedelta, datetime
import json

def dashboard_view(request):
    """
    Main dashboard with key metrics and analytics
    """
    # Key metrics
    total_accounts = Account.objects.count()
    total_requests = Request.objects.count()
    
    # Split agreements into signed vs pending
    signed_agreements = Agreement.objects.filter(status='Signed').count()
    pending_agreements = Agreement.objects.filter(status__in=['Draft', 'Sent']).count()
    total_agreements = Agreement.objects.count()
    
    # Request statistics
    confirmed_requests = Request.objects.filter(status='Confirmed').count()
    cancelled_requests = Request.objects.filter(status='Cancelled').count()
    paid_requests = Request.objects.filter(status='Paid').count()
    
    # Financial metrics - Total revenue includes both paid and unpaid amounts
    total_revenue = Request.objects.exclude(status='Cancelled').aggregate(
        total=Sum('total_cost'))['total'] or 0
    pending_revenue = Request.objects.filter(
        Q(status='Confirmed') | Q(status='Partially Paid')).aggregate(
        total=Sum('total_cost'))['total'] or 0
    
    # New enhanced financial metrics
    cancelled_lost_amount = Request.objects.filter(status='Cancelled').aggregate(
        total=Sum('total_cost'))['total'] or 0
    confirmed_paid_amount = Request.objects.filter(status='Paid').aggregate(
        total=Sum('paid_amount'))['total'] or 0
    
    # Calculate unpaid amounts (total cost minus paid amount for non-cancelled requests)
    unpaid_total = 0
    non_cancelled_requests = Request.objects.exclude(status='Cancelled').exclude(status='Paid')
    for req in non_cancelled_requests:
        unpaid_amount = req.total_cost - req.paid_amount
        if unpaid_amount > 0:
            unpaid_total += unpaid_amount
    
    # Request type breakdown
    request_types = Request.objects.values('request_type').annotate(
        count=Count('id')).order_by('-count')
    
    # Recent activity
    recent_requests = Request.objects.order_by('-created_at')[:5]
    recent_sales_calls = SalesCall.objects.order_by('-visit_date')[:5]
    
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
    
    context = {
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
        'approaching_deadlines': approaching_deadlines,
        'overdue_followups': overdue_followups,
    }
    
    return render(request, 'dashboard/dashboard.html', context)

def api_request_chart_data(request):
    """
    API endpoint for request chart data
    """
    request_data = Request.objects.values('request_type').annotate(
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
    status_data = Request.objects.values('status').annotate(
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

def api_health_check(request):
    """
    API health check endpoint for deployment monitoring
    """
    return JsonResponse({"status": "healthy", "service": "hotel_sales"}, status=200)

@staff_member_required
def calendar_view(request):
    """
    Calendar view displaying groups, events, and sales calls
    """
    return render(request, 'dashboard/calendar.html')

@staff_member_required
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
    group_requests = Request.objects.filter(
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
