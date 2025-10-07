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
from requests.models import Request as BookingRequest, EventAgenda, SeriesGroupEntry
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
    For time-sensitive notifications (deadlines, payments, events), we check by notification_type 
    and object_id to prevent duplicates even when the title changes daily (due to days_before count).
    """
    today = timezone.localdate()
    content_type = ContentType.objects.get_for_model(obj)
    
    # Notification types that change titles daily and need special duplicate prevention
    time_sensitive_types = [
        'beo',                    # BEO reminders - "Event in X days"
        'payment',                # Payment deadlines - "due in X days"
        'deadline',               # Offer deadlines - "expires in X days"
        'arrival',                # Series group arrivals - "X days"
        'event_checkin',          # Event with rooms check-ins - "X days"
        'event_start',            # Event with rooms starts - "starts in X days"
        'agreement',              # Agreement deadlines - "due in X days"
        'event_comprehensive'     # Consolidated event with accommodation alerts
    ]
    
    # For time-sensitive notifications, check by notification_type and object_id to prevent duplicates
    # even when title changes daily (e.g., "3 days" vs "2 days")
    if notification_type in time_sensitive_types:
        existing = Notification.objects.filter(
            user=user,
            content_type=content_type,
            object_id=obj.id,
            notification_type=notification_type,
            created_at__date=today
        ).exists()
    else:
        # For other notification types, check by title as before
        existing = Notification.objects.filter(
            user=user,
            content_type=content_type,
            object_id=obj.id,
            notification_type=notification_type,
            title=title,
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
    window_end = today + timedelta(days=5)
    created_count = 0
    
    # Clean up old payment notifications from previous days
    old_payment_notifications = Notification.objects.filter(
        notification_type='payment',
        created_at__date__lt=today
    ).delete()
    if old_payment_notifications[0] > 0:
        logger.info(f"Cleaned up {old_payment_notifications[0]} old payment notifications")
    
    # Get requests with payment deadlines in the next 5 days
    requests_with_deadlines = BookingRequest.objects.filter(
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
    window_end = today + timedelta(days=5)
    created_count = 0
    
    # Clean up old offer deadline notifications from previous days
    old_deadline_notifications = Notification.objects.filter(
        notification_type='deadline',
        created_at__date__lt=today
    ).delete()
    if old_deadline_notifications[0] > 0:
        logger.info(f"Cleaned up {old_deadline_notifications[0]} old deadline notifications")
    
    # Get requests with offer acceptance deadlines in the next 5 days
    requests_with_offers = BookingRequest.objects.filter(
        offer_acceptance_deadline__range=[today, window_end],
        status__in=['Pending', 'Sent']  # Only actionable statuses
    ).select_related('account')
    
    for request in requests_with_offers:
        # Clean up any existing deadline notifications for this specific request first
        from django.contrib.contenttypes.models import ContentType
        content_type = ContentType.objects.get_for_model(request)
        existing_deadline_notifications = Notification.objects.filter(
            content_type=content_type,
            object_id=request.id,
            notification_type='deadline'
        )
        if existing_deadline_notifications.exists():
            deleted_count = existing_deadline_notifications.count()
            existing_deadline_notifications.delete()
            logger.info(f"Cleaned up {deleted_count} existing deadline notifications for request {request.id}")
        
        recipients = get_recipients(request)
        days_before = (request.offer_acceptance_deadline - today).days
        priority = 'urgent' if days_before == 0 else ('high' if days_before <= 1 else 'medium')
        
        if days_before == 0:
            title = f"⚠️ Offer acceptance deadline TODAY - {request.account.name} - {request.request_type} request"
            message = f"Offer acceptance deadline is today for {request.request_type} request."
        else:
            title = f"⚠️ Offer acceptance deadline in {days_before} day{'s' if days_before > 1 else ''} - {request.account.name} - {request.request_type} request"
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
    window_end = today + timedelta(days=5)
    created_count = 0
    
    # Clean up old group check-in notifications from previous days
    old_checkin_notifications = Notification.objects.filter(
        notification_type='deadline',
        title__icontains='Group info sheet reminder',
        created_at__date__lt=today
    ).delete()
    if old_checkin_notifications[0] > 0:
        logger.info(f"Cleaned up {old_checkin_notifications[0]} old group check-in notifications")
    
    # Get requests with check-in dates in the next 5 days
    # EXCLUDE Event with Rooms and Series Group requests as they have their own alert systems
    group_requests = BookingRequest.objects.filter(
        check_in_date__range=[today, window_end],
        status__in=['Confirmed', 'Paid'],  # Only confirmed/paid requests (exclude Partially Paid)
        request_type='Group Accommodation'  # Only Group Accommodation (Series Group uses arrival_date alerts)
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
    """Generate notifications for agreement return deadlines and renewal reminders."""
    today = timezone.localdate()
    window_end = today + timedelta(days=5)
    created_count = 0
    
    # Clean up old agreement notifications from previous days
    old_agreement_notifications = Notification.objects.filter(
        notification_type='agreement',
        created_at__date__lt=today
    ).delete()
    if old_agreement_notifications[0] > 0:
        logger.info(f"Cleaned up {old_agreement_notifications[0]} old agreement notifications")
    
    # Get agreements with return deadlines in the next 5 days
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
    
    # Get agreements expiring/renewal in the next 5 days
    agreements_expiring = Agreement.objects.filter(
        end_date__range=[today, window_end],
        status='Signed'  # Only signed agreements need renewal
    ).select_related('account')
    
    for agreement in agreements_expiring:
        recipients = get_recipients(agreement)
        days_before = (agreement.end_date - today).days
        priority = 'urgent' if days_before == 0 else ('high' if days_before <= 1 else 'medium')
        
        if days_before == 0:
            title = f"URGENT: Agreement expires TODAY - {agreement.account.name}"
            message = f"Agreement expires today! Contact client to renew {agreement.rate_type} contract."
        else:
            title = f"Agreement renewal reminder - {days_before} day{'s' if days_before > 1 else ''} - {agreement.account.name}"
            message = f"Agreement expires on {agreement.end_date.strftime('%B %d, %Y')}. Contact client to renew {agreement.rate_type} contract."
        
        link_url = f"/admin/agreements/agreement/{agreement.id}/change/"
        
        for user in recipients:
            if create_notification_if_absent(user, agreement, title, message, 'renewal', priority, link_url, 'View Agreement'):
                created_count += 1
    
    logger.info(f"Created {created_count} agreement-related notifications")
    return created_count


def generate_for_event_beo_reminders():
    """Generate BEO (Banquet Event Order) reminders for event requests."""
    today = timezone.localdate()
    window_end = today + timedelta(days=5)
    created_count = 0
    
    # Get event agendas with event dates in the next 5 days
    # EXCLUDE Event with Rooms requests as they are handled by the consolidated function
    event_agendas = EventAgenda.objects.filter(
        event_date__range=[today, window_end],
        request__status__in=['Confirmed', 'Paid'],  # Only confirmed/paid events (exclude Partially Paid)
        request__request_type='Event without Rooms'  # Only Event without Rooms (exclude Event with Rooms)
    ).select_related('request', 'request__account')
    
    # Clean up old BEO notifications for events that are no longer in the 5-day window
    old_beo_notifications = Notification.objects.filter(
        notification_type='beo',
        created_at__date__lt=today
    ).delete()
    if old_beo_notifications[0] > 0:
        logger.info(f"Cleaned up {old_beo_notifications[0]} old BEO notifications")
    
    for agenda in event_agendas:
        recipients = get_recipients(agenda.request)
        days_before = (agenda.event_date - today).days
        priority = 'urgent' if days_before == 0 else ('high' if days_before <= 1 else 'medium')
        
        if days_before == 0:
            title = f"URGENT: Event TODAY - BEO needed - {agenda.request.account.name}"
            message = f"Event starts today! Send BEO (Banquet Event Order) details to operations team."
        else:
            title = f"BEO reminder - Event in {days_before} day{'s' if days_before > 1 else ''} - {agenda.request.account.name}"
            message = f"Event on {agenda.event_date.strftime('%B %d, %Y')} - Send BEO details to operations team."
        
        link_url = f"/admin/requests/request/{agenda.request.id}/change/"
        
        for user in recipients:
            if create_notification_if_absent(user, agenda.request, title, message, 'beo', priority, link_url, 'View Event'):
                created_count += 1
    
    logger.info(f"Created {created_count} BEO reminder notifications")
    return created_count


def generate_for_series_group_arrivals():
    """Generate arrival alerts for series group entries."""
    today = timezone.localdate()
    window_end = today + timedelta(days=5)
    created_count = 0
    
    # Clean up old series group arrival notifications from previous days
    old_arrival_notifications = Notification.objects.filter(
        notification_type='arrival',
        created_at__date__lt=today
    ).delete()
    if old_arrival_notifications[0] > 0:
        logger.info(f"Cleaned up {old_arrival_notifications[0]} old series arrival notifications")
    
    # Get series group entries with arrival dates in the next 5 days
    series_entries = SeriesGroupEntry.objects.filter(
        arrival_date__range=[today, window_end],
        request__status__in=['Confirmed', 'Partially Paid', 'Paid']  # Only confirmed series
    ).select_related('request', 'request__account')
    
    for entry in series_entries:
        recipients = get_recipients(entry.request)
        days_before = (entry.arrival_date - today).days
        priority = 'urgent' if days_before == 0 else ('high' if days_before <= 1 else 'medium')
        
        if days_before == 0:
            title = f"URGENT: Series group arrives TODAY - {entry.request.account.name}"
            message = f"Series group checks in today ({entry.arrival_date.strftime('%B %d, %Y')}) - Prepare arrival arrangements."
        else:
            title = f"Series group arrival - {days_before} day{'s' if days_before > 1 else ''} - {entry.request.account.name}"
            message = f"Series group arrives on {entry.arrival_date.strftime('%B %d, %Y')} - Prepare arrival arrangements."
        
        link_url = f"/admin/requests/request/{entry.request.id}/change/"
        
        for user in recipients:
            if create_notification_if_absent(user, entry.request, title, message, 'arrival', priority, link_url, 'View Series'):
                created_count += 1
    
    logger.info(f"Created {created_count} series group arrival notifications")
    return created_count


def generate_for_event_with_rooms():
    """Generate comprehensive alerts for Event with Rooms requests (consolidated alert)."""
    today = timezone.localdate()
    window_end = today + timedelta(days=5)
    created_count = 0
    
    # Clean up old event with rooms notifications from previous days
    old_event_checkin_notifications = Notification.objects.filter(
        notification_type='event_checkin',
        created_at__date__lt=today
    ).delete()
    old_event_start_notifications = Notification.objects.filter(
        notification_type='event_start',
        created_at__date__lt=today
    ).delete()
    old_beo_notifications = Notification.objects.filter(
        notification_type='beo',
        created_at__date__lt=today
    ).delete()
    old_deadline_notifications = Notification.objects.filter(
        notification_type='deadline',
        title__icontains='Group info sheet reminder',
        created_at__date__lt=today
    ).delete()
    total_cleaned = (old_event_checkin_notifications[0] + old_event_start_notifications[0] + 
                    old_beo_notifications[0] + old_deadline_notifications[0])
    if total_cleaned > 0:
        logger.info(f"Cleaned up {total_cleaned} old event with rooms notifications")
    
    # Get Event with Rooms requests with check-in dates in the next 5 days
    event_room_requests = BookingRequest.objects.filter(
        request_type='Event with Rooms',
        check_in_date__range=[today, window_end],
        status__in=['Confirmed', 'Paid']  # Only confirmed/paid events (exclude Partially Paid)
    ).select_related('account').prefetch_related('event_agendas')
    
    for request in event_room_requests:
        recipients = get_recipients(request)
        
        # Get the earliest event date from event agendas
        earliest_event = request.event_agendas.order_by('event_date').first()
        event_date = earliest_event.event_date if earliest_event else request.check_in_date
        
        # Determine which date is closer to today (check-in or event start)
        checkin_days = (request.check_in_date - today).days
        event_days = (event_date - today).days if earliest_event else None
        
        # Use the closer date for the alert timing
        if event_days is not None and abs(event_days) < abs(checkin_days):
            days_before = event_days
            date_type = "event start"
            date_value = event_date
        else:
            days_before = checkin_days
            date_type = "check-in"
            date_value = request.check_in_date
        
        priority = 'urgent' if days_before == 0 else ('high' if days_before <= 1 else 'medium')
        
        # Create comprehensive message
        if days_before == 0:
            title = f"URGENT: Event with Accommodation TODAY - {request.account.name}"
            message = f"Event with Accommodation is TODAY!\n"
            message += f"• Check-in: {request.check_in_date.strftime('%B %d, %Y')}\n"
            if earliest_event:
                message += f"• Event starts: {event_date.strftime('%B %d, %Y')}\n"
            message += f"• Prepare rooms, event coordination, and send BEO details to operations team."
        else:
            title = f"Event with Accommodation - {days_before} day{'s' if days_before > 1 else ''} - {request.account.name}"
            message = f"Event with Accommodation approaching:\n"
            message += f"• Check-in: {request.check_in_date.strftime('%B %d, %Y')}\n"
            if earliest_event:
                message += f"• Event starts: {event_date.strftime('%B %d, %Y')}\n"
            message += f"• Prepare rooms, event coordination, group information sheet, and BEO details."
        
        link_url = f"/admin/requests/request/{request.id}/change/"
        
        # Use a single notification type for consolidated alerts
        for user in recipients:
            if create_notification_if_absent(user, request, title, message, 'event_comprehensive', priority, link_url, 'View Event'):
                created_count += 1
    
    logger.info(f"Created {created_count} consolidated Event with Rooms notifications")
    return created_count


def generate_all_deadline_notifications():
    """Generate all types of deadline notifications."""
    logger.info("Starting deadline notification generation...")
    
    payment_count = generate_for_requests_payments()
    offer_count = generate_for_requests_offers()
    checkin_count = generate_for_group_checkins()
    agreement_count = generate_for_agreements()
    beo_count = generate_for_event_beo_reminders()
    series_count = generate_for_series_group_arrivals()
    event_rooms_count = generate_for_event_with_rooms()
    
    total_count = payment_count + offer_count + checkin_count + agreement_count + beo_count + series_count + event_rooms_count
    
    logger.info(f"Deadline notification generation complete. Created {total_count} notifications:")
    logger.info(f"  - Payment deadlines: {payment_count}")
    logger.info(f"  - Offer deadlines: {offer_count}")  
    logger.info(f"  - Group check-ins: {checkin_count}")
    logger.info(f"  - Agreement deadlines: {agreement_count}")
    logger.info(f"  - BEO reminders: {beo_count}")
    logger.info(f"  - Series group arrivals: {series_count}")
    logger.info(f"  - Event with Rooms: {event_rooms_count}")
    
    return {
        'total': total_count,
        'payments': payment_count,
        'offers': offer_count,
        'checkins': checkin_count,
        'agreements': agreement_count,
        'beo': beo_count,
        'series': series_count,
        'event_rooms': event_rooms_count
    }