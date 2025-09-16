"""
Deadline-based notification generation service.

Generates notifications for:
- Payment deadlines (deposit, full payment)
- Offer acceptance deadlines
- Group information sheet reminders (based on check-in dates)
- Agreement return deadlines
"""
from datetime import date, timedelta
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.db.models import Q

from dashboard.models import Notification
from requests.models import Request
from agreements.models import Agreement
import logging

logger = logging.getLogger(__name__)


def get_recipients(obj):
    """
    Get notification recipients for an object.
    
    Priority:
    1. request.assigned_to if present
    2. account.owner if present  
    3. All active staff users as fallback
    """
    recipients = []
    
    # Try to get assigned user or account owner
    if hasattr(obj, 'assigned_to') and obj.assigned_to:
        recipients.append(obj.assigned_to)
    elif hasattr(obj, 'account') and hasattr(obj.account, 'owner') and obj.account.owner:
        recipients.append(obj.account.owner)
    
    # Fallback to all active staff if no specific recipient found
    if not recipients:
        recipients = list(User.objects.filter(is_active=True, is_staff=True))
    
    return recipients


def create_notification_if_absent(user, obj, title, message, notification_type, priority, link_url=None, link_text=None):
    """
    Create notification only if it doesn't already exist for today.
    
    This ensures idempotency - running multiple times per day won't create duplicates.
    """
    today = timezone.localdate()
    content_type = ContentType.objects.get_for_model(obj)
    
    # Check if notification already exists for today
    existing = Notification.objects.filter(
        user=user,
        content_type=content_type,
        object_id=obj.id,
        notification_type=notification_type,
        title=title,  # Title includes days_before info, making it unique
        created_at__date=today
    ).exists()
    
    if existing:
        return None  # Already exists, skip
    
    # Create new notification
    notification = Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type=notification_type,
        priority=priority,
        link_url=link_url,
        link_text=link_text,
        content_type=content_type,
        object_id=obj.id,
        is_read=False
    )
    
    return notification


def generate_for_requests_payments():
    """Generate notifications for request payment deadlines."""
    today = timezone.localdate()
    window_end = today + timedelta(days=3)
    created_count = 0
    
    # Get requests with payment deadlines in the next 3 days
    requests_with_deadlines = Request.objects.filter(
        Q(deposit_deadline__range=[today, window_end]) |
        Q(full_payment_deadline__range=[today, window_end]),
        status__in=['Pending', 'Confirmed', 'Partially Paid']  # Only actionable statuses
    ).select_related('account')
    
    for request in requests_with_deadlines:
        recipients = get_recipients(request)
        
        # Check deposit deadline
        if request.deposit_deadline and today <= request.deposit_deadline <= window_end:
            days_before = (request.deposit_deadline - today).days
            priority = 'urgent' if days_before == 0 else ('high' if days_before <= 1 else 'medium')
            
            if days_before == 0:
                title = f"URGENT: Deposit due TODAY - {request.account.name}"
                message = f"Deposit payment is due today for {request.request_type} request."
            else:
                title = f"Deposit due in {days_before} day{'s' if days_before > 1 else ''} - {request.account.name}"
                message = f"Deposit payment is due on {request.deposit_deadline.strftime('%B %d, %Y')} for {request.request_type} request."
            
            link_url = f"/admin/requests/request/{request.id}/change/"
            
            for user in recipients:
                if create_notification_if_absent(user, request, title, message, 'payment', priority, link_url, 'View Request'):
                    created_count += 1
        
        # Check full payment deadline
        if request.full_payment_deadline and today <= request.full_payment_deadline <= window_end:
            days_before = (request.full_payment_deadline - today).days
            priority = 'urgent' if days_before == 0 else ('high' if days_before <= 1 else 'medium')
            
            if days_before == 0:
                title = f"URGENT: Full payment due TODAY - {request.account.name}"
                message = f"Full payment is due today for {request.request_type} request."
            else:
                title = f"Full payment due in {days_before} day{'s' if days_before > 1 else ''} - {request.account.name}"
                message = f"Full payment is due on {request.full_payment_deadline.strftime('%B %d, %Y')} for {request.request_type} request."
            
            link_url = f"/admin/requests/request/{request.id}/change/"
            
            for user in recipients:
                if create_notification_if_absent(user, request, title, message, 'payment', priority, link_url, 'View Request'):
                    created_count += 1
    
    logger.info(f"Created {created_count} payment deadline notifications")
    return created_count


def generate_for_requests_offers():
    """Generate notifications for offer acceptance deadlines."""
    today = timezone.localdate()
    window_end = today + timedelta(days=3)
    created_count = 0
    
    # Get requests with offer acceptance deadlines in the next 3 days
    requests_with_offers = Request.objects.filter(
        offer_acceptance_deadline__range=[today, window_end],
        status__in=['Pending', 'Sent']  # Only actionable statuses
    ).select_related('account')
    
    for request in requests_with_offers:
        recipients = get_recipients(request)
        days_before = (request.offer_acceptance_deadline - today).days
        priority = 'urgent' if days_before == 0 else ('high' if days_before <= 1 else 'medium')
        
        if days_before == 0:
            title = f"URGENT: Offer expires TODAY - {request.account.name}"
            message = f"Offer acceptance deadline is today for {request.request_type} request."
        else:
            title = f"Offer expires in {days_before} day{'s' if days_before > 1 else ''} - {request.account.name}"
            message = f"Offer acceptance deadline is {request.offer_acceptance_deadline.strftime('%B %d, %Y')} for {request.request_type} request."
        
        link_url = f"/admin/requests/request/{request.id}/change/"
        
        for user in recipients:
            if create_notification_if_absent(user, request, title, message, 'deadline', priority, link_url, 'View Request'):
                created_count += 1
    
    logger.info(f"Created {created_count} offer deadline notifications")
    return created_count


def generate_for_group_checkins():
    """Generate notifications for group information sheet reminders."""
    today = timezone.localdate()
    window_end = today + timedelta(days=3)
    created_count = 0
    
    # Get requests with check-in dates in the next 3 days
    # Include any confirmed request that might need info sheets
    group_requests = Request.objects.filter(
        check_in_date__range=[today, window_end],
        status__in=['Confirmed', 'Partially Paid', 'Paid']  # Only confirmed requests
    ).select_related('account')
    
    for request in group_requests:
        recipients = get_recipients(request)
        days_before = (request.check_in_date - today).days
        priority = 'urgent' if days_before == 0 else ('high' if days_before <= 1 else 'medium')
        
        if days_before == 0:
            title = f"URGENT: Group checks in TODAY - {request.account.name}"
            message = f"Group information sheet needed for {request.request_type} checking in today."
        else:
            title = f"Group info sheet reminder - {days_before} day{'s' if days_before > 1 else ''} until check-in - {request.account.name}"
            message = f"Group information sheet reminder: {request.request_type} checks in on {request.check_in_date.strftime('%B %d, %Y')}."
        
        link_url = f"/admin/requests/request/{request.id}/change/"
        
        for user in recipients:
            if create_notification_if_absent(user, request, title, message, 'deadline', priority, link_url, 'View Request'):
                created_count += 1
    
    logger.info(f"Created {created_count} group check-in notifications")
    return created_count


def generate_for_agreements():
    """Generate notifications for agreement return deadlines."""
    today = timezone.localdate()
    window_end = today + timedelta(days=3)
    created_count = 0
    
    # Get agreements with return deadlines in the next 3 days
    agreements_with_deadlines = Agreement.objects.filter(
        return_deadline__range=[today, window_end],
        status__in=['Draft', 'Sent']  # Only actionable statuses
    ).select_related('account')
    
    for agreement in agreements_with_deadlines:
        recipients = get_recipients(agreement)
        days_before = (agreement.return_deadline - today).days
        priority = 'urgent' if days_before == 0 else ('high' if days_before <= 1 else 'medium')
        
        if days_before == 0:
            title = f"URGENT: Agreement due TODAY - {agreement.account.name}"
            message = f"Agreement return deadline is today for {agreement.rate_type} agreement."
        else:
            title = f"Agreement due in {days_before} day{'s' if days_before > 1 else ''} - {agreement.account.name}"
            message = f"Agreement return deadline is {agreement.return_deadline.strftime('%B %d, %Y')} for {agreement.rate_type} agreement."
        
        link_url = f"/admin/agreements/agreement/{agreement.id}/change/"
        
        for user in recipients:
            if create_notification_if_absent(user, agreement, title, message, 'agreement', priority, link_url, 'View Agreement'):
                created_count += 1
    
    logger.info(f"Created {created_count} agreement deadline notifications")
    return created_count


def generate_all_deadline_notifications():
    """Generate all types of deadline notifications."""
    logger.info("Starting deadline notification generation...")
    
    payment_count = generate_for_requests_payments()
    offer_count = generate_for_requests_offers()
    checkin_count = generate_for_group_checkins()
    agreement_count = generate_for_agreements()
    
    total_count = payment_count + offer_count + checkin_count + agreement_count
    
    logger.info(f"Deadline notification generation complete. Created {total_count} notifications:")
    logger.info(f"  - Payment deadlines: {payment_count}")
    logger.info(f"  - Offer deadlines: {offer_count}")  
    logger.info(f"  - Group check-ins: {checkin_count}")
    logger.info(f"  - Agreement deadlines: {agreement_count}")
    
    return {
        'total': total_count,
        'payments': payment_count,
        'offers': offer_count,
        'checkins': checkin_count,
        'agreements': agreement_count
    }