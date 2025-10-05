"""
API views for notifications and real-time updates
"""
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.utils import timezone
from django.urls import reverse
from django.db.models import Q
import json

from .models import Notification
from agreements.models import Agreement
from requests.models import Request as BookingRequest


@login_required
@require_http_methods(["GET"])
def get_notifications(request):
    """Get user notifications with pagination"""
    try:
        # Get query parameters
        page = int(request.GET.get('page', 1))
        limit = min(int(request.GET.get('limit', 10)), 50)  # Max 50 per request
        unread_only = request.GET.get('unread_only', 'false').lower() == 'true'
        
        # Query notifications
        queryset = Notification.objects.filter(user=request.user)
        if unread_only:
            queryset = queryset.filter(is_read=False)
        
        # Paginate
        paginator = Paginator(queryset, limit)
        notifications_page = paginator.get_page(page)
        
        # Serialize notifications
        notifications_data = []
        for notification in notifications_page:
            notifications_data.append({
                'id': notification.id,
                'title': notification.title,
                'message': notification.message,
                'type': notification.notification_type,
                'priority': notification.priority,
                'icon': notification.get_icon(),
                'priority_class': notification.get_priority_class(),
                'link_url': notification.link_url,
                'link_text': notification.link_text,
                'is_read': notification.is_read,
                'created_at': notification.created_at.isoformat(),
                'time_since': notification.time_since_created(),
            })
        
        return JsonResponse({
            'success': True,
            'notifications': notifications_data,
            'pagination': {
                'current_page': notifications_page.number,
                'total_pages': paginator.num_pages,
                'total_count': paginator.count,
                'has_next': notifications_page.has_next(),
                'has_previous': notifications_page.has_previous(),
            }
        })
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required 
@require_http_methods(["GET"])
def get_unread_count(request):
    """Get count of unread notifications for the current user"""
    try:
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return JsonResponse({
            'success': True,
            'unread_count': count
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def mark_notification_read(request, notification_id):
    """Mark a specific notification as read"""
    try:
        notification = Notification.objects.get(id=notification_id, user=request.user)
        notification.mark_as_read()
        return JsonResponse({
            'success': True,
            'message': 'Notification marked as read'
        })
    except Notification.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Notification not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def mark_all_read(request):
    """Mark all notifications as read for the current user"""
    try:
        updated_count = Notification.objects.filter(
            user=request.user, 
            is_read=False
        ).update(is_read=True, read_at=timezone.now())
        
        return JsonResponse({
            'success': True,
            'message': f'Marked {updated_count} notifications as read'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def generate_deadline_notifications(user):
    """Generate notifications for approaching agreement deadlines and request status deadlines"""
    from datetime import timedelta
    
    notifications_created = 0
    
    # Find agreements with deadlines in the next 5 days
    upcoming_deadline = timezone.now().date() + timedelta(days=5)
    approaching_agreements = Agreement.objects.filter(
        deadline_date__lte=upcoming_deadline,
        deadline_date__gte=timezone.now().date(),
        status__in=['Draft', 'Sent']
    ).exclude(
        # Don't create duplicate notifications
        id__in=Notification.objects.filter(
            user=user,
            notification_type='deadline',
            created_at__date=timezone.now().date()
        ).values_list('object_id', flat=True)
    )
    
    for agreement in approaching_agreements:
        days_until = (agreement.deadline_date - timezone.now().date()).days
        
        if days_until <= 1:
            priority = 'urgent'
            title = f"⚠️ Agreement deadline TODAY: {agreement.account.name}"
        elif days_until <= 3:
            priority = 'high'  
            title = f"⚠️ Agreement deadline in {days_until} days: {agreement.account.name}"
        else:
            priority = 'medium'
            title = f"Agreement deadline approaching: {agreement.account.name}"
        
        # Create notification
        Notification.objects.create(
            user=user,
            title=title,
            message=f"Agreement with {agreement.account.name} is due on {agreement.deadline_date.strftime('%B %d, %Y')}. Please follow up.",
            notification_type='deadline',
            priority=priority,
            link_url=reverse('admin:agreements_agreement_change', args=[agreement.id]),
            link_text='View Agreement',
            content_type_id=agreement._meta.get_field('id').model._meta.get_for_model(Agreement).id,
            object_id=agreement.id
        )
        notifications_created += 1
    
    # Generate request status-based deadline notifications
    notifications_created += generate_request_status_deadline_notifications(user)
    
    return notifications_created


def generate_request_status_deadline_notifications(user):
    """Generate notifications for request status-based deadlines"""
    from datetime import timedelta
    from django.contrib.contenttypes.models import ContentType
    
    notifications_created = 0
    today = timezone.now().date()
    alert_date = today + timedelta(days=5)  # Check next 5 days
    
    # Get existing notifications for today to avoid duplicates
    existing_notifications = Notification.objects.filter(
        user=user,
        notification_type='deadline',
        created_at__date=today
    ).values_list('object_id', flat=True)
    
    # Draft status: Alert on offer acceptance deadline
    draft_requests = BookingRequest.objects.filter(
        status='Draft',
        offer_acceptance_deadline__lte=alert_date,
        offer_acceptance_deadline__gte=today
    ).exclude(id__in=existing_notifications).select_related('account')
    
    for request in draft_requests:
        days_until = (request.offer_acceptance_deadline - today).days
        
        if days_until <= 1:
            priority = 'urgent'
            title = f"⚠️ Offer acceptance deadline TODAY: {request.account.name}"
        elif days_until <= 3:
            priority = 'high'
            title = f"⚠️ Offer acceptance deadline in {days_until} days: {request.account.name}"
        else:
            priority = 'medium'
            title = f"Offer acceptance deadline approaching: {request.account.name}"
        
        # Create notification
        Notification.objects.create(
            user=user,
            title=title,
            message=f"Request {request.confirmation_number} with {request.account.name} has offer acceptance deadline on {request.offer_acceptance_deadline.strftime('%B %d, %Y')}. Please follow up on offer acceptance.",
            notification_type='deadline',
            priority=priority,
            link_url=reverse('admin:requests_request_change', args=[request.id]),
            link_text='View Request',
            content_type=ContentType.objects.get_for_model(BookingRequest),
            object_id=request.id
        )
        notifications_created += 1
    
    # Pending status: Alert on deposit deadline
    pending_requests = BookingRequest.objects.filter(
        status='Pending',
        deposit_deadline__lte=alert_date,
        deposit_deadline__gte=today
    ).exclude(id__in=existing_notifications).select_related('account')
    
    for request in pending_requests:
        days_until = (request.deposit_deadline - today).days
        
        if days_until <= 1:
            priority = 'urgent'
            title = f"⚠️ Deposit deadline TODAY: {request.account.name}"
        elif days_until <= 3:
            priority = 'high'
            title = f"⚠️ Deposit deadline in {days_until} days: {request.account.name}"
        else:
            priority = 'medium'
            title = f"Deposit deadline approaching: {request.account.name}"
        
        # Create notification
        Notification.objects.create(
            user=user,
            title=title,
            message=f"Request {request.confirmation_number} with {request.account.name} has deposit deadline on {request.deposit_deadline.strftime('%B %d, %Y')}. Please follow up on deposit payment.",
            notification_type='deadline',
            priority=priority,
            link_url=reverse('admin:requests_request_change', args=[request.id]),
            link_text='View Request',
            content_type=ContentType.objects.get_for_model(BookingRequest),
            object_id=request.id
        )
        notifications_created += 1
    
    # Partially Paid status: Alert on full payment deadline
    partially_paid_requests = BookingRequest.objects.filter(
        status='Partially Paid',
        full_payment_deadline__lte=alert_date,
        full_payment_deadline__gte=today
    ).exclude(id__in=existing_notifications).select_related('account')
    
    for request in partially_paid_requests:
        days_until = (request.full_payment_deadline - today).days
        
        if days_until <= 1:
            priority = 'urgent'
            title = f"⚠️ Full payment deadline TODAY: {request.account.name}"
        elif days_until <= 3:
            priority = 'high'
            title = f"⚠️ Full payment deadline in {days_until} days: {request.account.name}"
        else:
            priority = 'medium'
            title = f"Full payment deadline approaching: {request.account.name}"
        
        # Create notification
        Notification.objects.create(
            user=user,
            title=title,
            message=f"Request {request.confirmation_number} with {request.account.name} has full payment deadline on {request.full_payment_deadline.strftime('%B %d, %Y')}. Please follow up on full payment.",
            notification_type='deadline',
            priority=priority,
            link_url=reverse('admin:requests_request_change', args=[request.id]),
            link_text='View Request',
            content_type=ContentType.objects.get_for_model(BookingRequest),
            object_id=request.id
        )
        notifications_created += 1
    
    return notifications_created


def generate_payment_notifications(user):
    """Generate notifications for overdue payments"""
    overdue_requests = BookingRequest.objects.filter(
        status__in=['Confirmed', 'Partially Paid'],
        check_out_date__lt=timezone.now().date()
    ).exclude(
        # Don't create duplicate notifications
        id__in=Notification.objects.filter(
            user=user,
            notification_type='payment',
            created_at__date=timezone.now().date()
        ).values_list('object_id', flat=True)
    )
    
    notifications_created = 0
    for request_obj in overdue_requests:
        days_overdue = (timezone.now().date() - request_obj.check_out_date).days
        outstanding_amount = request_obj.total_cost - request_obj.paid_amount
        
        if days_overdue > 30:
            priority = 'urgent'
        elif days_overdue > 14:
            priority = 'high'
        else:
            priority = 'medium'
        
        Notification.objects.create(
            user=user,
            title=f"💰 Payment overdue: {request_obj.account.name}",
            message=f"Payment of ${outstanding_amount:.2f} is {days_overdue} days overdue for {request_obj.confirmation_number}",
            notification_type='payment',
            priority=priority,
            link_url=reverse('admin:requests_request_change', args=[request_obj.id]),
            link_text='View Request',
            content_type_id=request_obj._meta.get_field('id').model._meta.get_for_model(BookingRequest).id,
            object_id=request_obj.id
        )
        notifications_created += 1
    
    return notifications_created


def generate_sales_calls_followup_notifications(user):
    """Generate notifications for sales calls follow-up reminders."""
    from datetime import timedelta
    from django.contrib.contenttypes.models import ContentType
    from sales_calls.models import SalesCall
    
    notifications_created = 0
    today = timezone.now().date()
    alert_date = today + timedelta(days=5)  # Check next 5 days
    
    # Get existing notifications for today to avoid duplicates
    existing_notifications = Notification.objects.filter(
        user=user,
        notification_type='deadline',
        created_at__date=today
    ).values_list('object_id', flat=True)
    
    # OVERDUE FOLLOW-UPS (urgent)
    overdue_calls = SalesCall.objects.filter(
        follow_up_required=True,
        follow_up_completed=False,
        follow_up_date__lt=today
    ).exclude(id__in=existing_notifications).select_related('account')
    
    for call in overdue_calls:
        days_overdue = (today - call.follow_up_date).days
        
        title = f"🚨 OVERDUE: Follow-up {days_overdue} days late - {call.account.name}"
        message = f"Sales call follow-up with {call.account.name} is {days_overdue} days overdue. Please complete follow-up immediately."
        
        link_url = f"/admin/sales_calls/salescall/{call.id}/change/"
        
        # Create notification
        Notification.objects.create(
            user=user,
            title=title,
            message=message,
            notification_type='deadline',
            priority='urgent',
            link_url=link_url,
            link_text='View Sales Call',
            content_type=ContentType.objects.get_for_model(SalesCall),
            object_id=call.id
        )
        notifications_created += 1
    
    # UPCOMING FOLLOW-UPS
    upcoming_calls = SalesCall.objects.filter(
        follow_up_required=True,
        follow_up_completed=False,
        follow_up_date__range=[today, alert_date]
    ).exclude(id__in=existing_notifications).select_related('account')
    
    for call in upcoming_calls:
        days_until = (call.follow_up_date - today).days
        priority = 'urgent' if days_until == 0 else ('high' if days_until <= 3 else 'medium')
        
        if days_until == 0:
            title = f"⚠️ Follow-up due TODAY: {call.account.name}"
            message = f"Sales call follow-up with {call.account.name} is due today. Please complete follow-up."
        elif days_until <= 3:
            title = f"⚠️ Follow-up due in {days_until} days: {call.account.name}"
            message = f"Sales call follow-up with {call.account.name} is due on {call.follow_up_date.strftime('%B %d, %Y')}. Please prepare follow-up."
        else:
            title = f"Follow-up reminder: {call.account.name}"
            message = f"Sales call follow-up with {call.account.name} is due on {call.follow_up_date.strftime('%B %d, %Y')}. Please prepare follow-up."
        
        link_url = f"/admin/sales_calls/salescall/{call.id}/change/"
        
        # Create notification
        Notification.objects.create(
            user=user,
            title=title,
            message=message,
            notification_type='deadline',
            priority=priority,
            link_url=link_url,
            link_text='View Sales Call',
            content_type=ContentType.objects.get_for_model(SalesCall),
            object_id=call.id
        )
        notifications_created += 1
    
    # HIGH BUSINESS POTENTIAL FOLLOW-UPS (priority)
    high_potential_calls = SalesCall.objects.filter(
        follow_up_required=True,
        follow_up_completed=False,
        business_potential='High',
        follow_up_date__range=[today, alert_date]
    ).exclude(id__in=existing_notifications).select_related('account')
    
    for call in high_potential_calls:
        days_until = (call.follow_up_date - today).days
        
        title = f"💎 HIGH POTENTIAL: Follow-up in {days_until} days - {call.account.name}"
        message = f"High business potential client {call.account.name} has follow-up due on {call.follow_up_date.strftime('%B %d, %Y')}. Priority follow-up required."
        
        link_url = f"/admin/sales_calls/salescall/{call.id}/change/"
        
        # Create notification
        Notification.objects.create(
            user=user,
            title=title,
            message=message,
            notification_type='deadline',
            priority='high',
            link_url=link_url,
            link_text='View Sales Call',
            content_type=ContentType.objects.get_for_model(SalesCall),
            object_id=call.id
        )
        notifications_created += 1
    
    return notifications_created


@login_required
@require_http_methods(["POST"])
def generate_notifications(request):
    """Generate system notifications (called periodically or manually)"""
    try:
        deadline_count = generate_deadline_notifications(request.user)
        payment_count = generate_payment_notifications(request.user)
        sales_calls_count = generate_sales_calls_followup_notifications(request.user)
        
        return JsonResponse({
            'success': True,
            'generated': {
                'deadline_notifications': deadline_count,
                'payment_notifications': payment_count,
                'sales_calls_notifications': sales_calls_count,
                'total': deadline_count + payment_count + sales_calls_count
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def clear_all_notifications(request):
    """Clear (delete) all notifications for the current user"""
    try:
        deleted_count = Notification.objects.filter(user=request.user).delete()[0]
        
        return JsonResponse({
            'success': True,
            'message': f'Cleared {deleted_count} notifications'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)