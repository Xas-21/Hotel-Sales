from django.shortcuts import render
from django.http import JsonResponse
from django.db.models import Count, Sum, Q
from accounts.models import Account
from requests.models import Request
from agreements.models import Agreement
from sales_calls.models import SalesCall
from datetime import date, timedelta

def dashboard_view(request):
    """
    Main dashboard with key metrics and analytics
    """
    # Key metrics
    total_accounts = Account.objects.count()
    total_requests = Request.objects.count()
    
    # Request statistics
    confirmed_requests = Request.objects.filter(status='Confirmed').count()
    cancelled_requests = Request.objects.filter(status='Cancelled').count()
    paid_requests = Request.objects.filter(status='Paid').count()
    
    # Financial metrics
    total_revenue = Request.objects.filter(status='Paid').aggregate(
        total=Sum('paid_amount'))['total'] or 0
    pending_revenue = Request.objects.filter(
        Q(status='Confirmed') | Q(status='Partially Paid')).aggregate(
        total=Sum('total_cost'))['total'] or 0
    
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
        'confirmed_requests': confirmed_requests,
        'cancelled_requests': cancelled_requests,
        'paid_requests': paid_requests,
        'total_revenue': total_revenue,
        'pending_revenue': pending_revenue,
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
