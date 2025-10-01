"""
Django signals for automatic notification cleanup.

Automatically removes or updates notifications when:
- Requests or agreements are deleted
- Status changes make notifications irrelevant (Paid, Signed, etc.)
"""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType

from dashboard.models import Notification
from requests.models import Request as BookingRequest
from agreements.models import Agreement
from dashboard.services.deadline_notifications import generate_for_agreements
import logging

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=BookingRequest)
def cleanup_notifications_on_request_delete(sender, instance, **kwargs):
    """Remove all notifications related to a deleted request."""
    content_type = ContentType.objects.get_for_model(BookingRequest)
    
    deleted_count = Notification.objects.filter(
        content_type=content_type,
        object_id=instance.id
    ).delete()[0]
    
    if deleted_count > 0:
        logger.info(f"Cleaned up {deleted_count} notifications for deleted request {instance.id}")


@receiver(post_delete, sender=Agreement)
def cleanup_notifications_on_agreement_delete(sender, instance, **kwargs):
    """Remove all notifications related to a deleted agreement."""
    content_type = ContentType.objects.get_for_model(Agreement)
    
    deleted_count = Notification.objects.filter(
        content_type=content_type,
        object_id=instance.id
    ).delete()[0]
    
    if deleted_count > 0:
        logger.info(f"Cleaned up {deleted_count} notifications for deleted agreement {instance.id}")


@receiver(post_save, sender=Agreement)
def auto_generate_agreement_notifications(sender, instance, created, **kwargs):
    """Automatically generate deadline notifications when agreements are created or updated."""
    print(f"🔔 SIGNAL DEBUG: Agreement {instance.id} saved - Status: {instance.status}")
    logger.info(f"🔔 Agreement signal triggered: {instance.account.name} (ID: {instance.id}) - Status: {instance.status} - {'Created' if created else 'Updated'}")
    try:
        # FIRST: Clean up existing notifications for this agreement if it's being updated
        # This ensures old notifications with outdated dates are removed
        if not created:
            content_type = ContentType.objects.get_for_model(Agreement)
            old_notifications = Notification.objects.filter(
                content_type=content_type,
                object_id=instance.id,
                notification_type__in=['agreement', 'renewal']
            )
            deleted_count = old_notifications.count()
            if deleted_count > 0:
                old_notifications.delete()
                logger.info(f"Cleaned up {deleted_count} old notifications for agreement {instance.id} before regenerating")
        
        # SECOND: Generate fresh notifications for this specific agreement based on its current state
        from datetime import date, timedelta
        from django.utils import timezone
        from dashboard.services.deadline_notifications import get_recipients, create_notification_if_absent
        
        today = timezone.localdate()
        window_end = today + timedelta(days=5)
        
        # Check if agreement has deadlines within notification window
        agreement_needs_notification = False
        
        # Check return deadline (for Draft/Sent status)
        if (instance.status in ['Draft', 'Sent'] and 
            instance.return_deadline and 
            today <= instance.return_deadline <= window_end):
            agreement_needs_notification = True
            
        # Check end date deadline (for Signed status)  
        if (instance.status == 'Signed' and 
            instance.end_date and 
            today <= instance.end_date <= window_end):
            agreement_needs_notification = True
            
        if agreement_needs_notification:
            # Run the full agreement notification generation
            # This is efficient because it only creates notifications that don't already exist
            created_count = generate_for_agreements()
            if created_count > 0:
                logger.info(f"Auto-generated {created_count} notifications after agreement {instance.id} was {'created' if created else 'updated'}")
        else:
            logger.debug(f"Agreement {instance.id} ({instance.account.name}) does not need notifications - status: {instance.status}")
            
    except Exception as e:
        logger.error(f"Failed to auto-generate notifications for agreement {instance.id}: {e}")


@receiver(post_save, sender=BookingRequest)
def cleanup_notifications_on_request_status_change(sender, instance, created, **kwargs):
    """Remove irrelevant notifications when request status changes."""
    if created:
        return  # Skip for new requests
    
    content_type = ContentType.objects.get_for_model(BookingRequest)
    deleted_count = 0
    
    # Remove payment deadline notifications if request is paid
    if instance.status in ['Paid', 'Completed', 'Cancelled']:
        payment_notifications = Notification.objects.filter(
            content_type=content_type,
            object_id=instance.id,
            notification_type='payment'
        )
        deleted_count += payment_notifications.count()
        payment_notifications.delete()
    
    # Remove offer deadline notifications if request is confirmed/paid
    if instance.status in ['Confirmed', 'Partially Paid', 'Paid', 'Completed', 'Cancelled']:
        offer_notifications = Notification.objects.filter(
            content_type=content_type,
            object_id=instance.id,
            notification_type='deadline'
        )
        deleted_count += offer_notifications.count()
        offer_notifications.delete()
    
    # Remove check-in and event notifications if request is cancelled
    if instance.status == 'Cancelled':
        event_notifications = Notification.objects.filter(
            content_type=content_type,
            object_id=instance.id,
            notification_type__in=['beo', 'arrival', 'event_checkin', 'event_start']
        )
        deleted_count += event_notifications.count()
        event_notifications.delete()
    
    if deleted_count > 0:
        logger.info(f"Cleaned up {deleted_count} notifications for request {instance.id} status change to {instance.status}")


@receiver(post_save, sender=Agreement)
def cleanup_notifications_on_agreement_status_change(sender, instance, created, **kwargs):
    """Remove irrelevant notifications when agreement status changes."""
    if created:
        return  # Skip for new agreements
    
    content_type = ContentType.objects.get_for_model(Agreement)
    deleted_count = 0
    
    # Remove return deadline notifications if agreement is signed
    if instance.status == 'Signed':
        return_notifications = Notification.objects.filter(
            content_type=content_type,
            object_id=instance.id,
            notification_type='agreement'
        )
        deleted_count += return_notifications.count()
        return_notifications.delete()
    
    # Remove renewal notifications if agreement is expired or cancelled
    if instance.status in ['Expired', 'Cancelled']:
        renewal_notifications = Notification.objects.filter(
            content_type=content_type,
            object_id=instance.id,
            notification_type='renewal'
        )
        deleted_count += renewal_notifications.count()
        renewal_notifications.delete()
    
    if deleted_count > 0:
        logger.info(f"Cleaned up {deleted_count} notifications for agreement {instance.id} status change to {instance.status}")


def cleanup_all_stale_notifications():
    """
    Manual cleanup function to remove stale notifications.
    Can be called as needed to clean up inconsistencies.
    """
    total_deleted = 0
    
    # Clean up notifications for deleted requests
    request_ct = ContentType.objects.get_for_model(BookingRequest)
    stale_request_notifications = Notification.objects.filter(content_type=request_ct).exclude(
        object_id__in=BookingRequest.objects.values_list('id', flat=True)
    )
    count = stale_request_notifications.count()
    if count > 0:
        stale_request_notifications.delete()
        total_deleted += count
        logger.info(f"Cleaned up {count} notifications for deleted requests")
    
    # Clean up notifications for deleted agreements
    agreement_ct = ContentType.objects.get_for_model(Agreement)
    stale_agreement_notifications = Notification.objects.filter(content_type=agreement_ct).exclude(
        object_id__in=Agreement.objects.values_list('id', flat=True)
    )
    count = stale_agreement_notifications.count()
    if count > 0:
        stale_agreement_notifications.delete()
        total_deleted += count
        logger.info(f"Cleaned up {count} notifications for deleted agreements")
    
    # Clean up notifications for non-actionable request statuses
    paid_requests = BookingRequest.objects.filter(status__in=['Paid', 'Completed', 'Cancelled'])
    for request in paid_requests:
        payment_notifications = Notification.objects.filter(
            content_type=request_ct,
            object_id=request.id,
            notification_type='payment'
        )
        count = payment_notifications.count()
        if count > 0:
            payment_notifications.delete()
            total_deleted += count
    
    # Clean up notifications for signed agreements
    signed_agreements = Agreement.objects.filter(status='Signed')
    for agreement in signed_agreements:
        return_notifications = Notification.objects.filter(
            content_type=agreement_ct,
            object_id=agreement.id,
            notification_type='agreement'
        )
        count = return_notifications.count()
        if count > 0:
            return_notifications.delete()
            total_deleted += count
    
    logger.info(f"Manual cleanup completed. Removed {total_deleted} stale notifications")
    return total_deleted


# Request-based automatic notification refresh signals
@receiver(post_save, sender=BookingRequest)
def auto_generate_request_notifications(sender, instance, created, **kwargs):
    """Auto-generate request notifications when dates change"""
    from django.contrib.contenttypes.models import ContentType
    from dashboard.models import Notification
    from dashboard.services.deadline_notifications import (
        generate_for_event_beo_reminders, 
        generate_for_series_group_arrivals, 
        generate_for_event_with_rooms,
        generate_for_group_checkins
    )
    # ADD: Import status-based notification function
    from dashboard.api_views import generate_request_status_deadline_notifications, generate_sales_calls_followup_notifications
    from django.contrib.auth.models import User
    
    try:
        logger.info(f"🔔 SIGNAL DEBUG: Request {instance.id} saved - Type: {instance.request_type}")
        
        # Clean up existing request notifications if it's being updated
        if not created:
            content_type = ContentType.objects.get_for_model(instance.__class__)
            old_notifications = Notification.objects.filter(
                content_type=content_type,
                object_id=instance.id,
                notification_type__in=['beo', 'arrival', 'event_checkin', 'event_start', 'checkin', 'deadline']
            )
            deleted_count = old_notifications.count()
            if deleted_count > 0:
                old_notifications.delete()
                logger.info(f"Cleaned up {deleted_count} old notifications for request {instance.id} before regenerating")
        
        # Generate all request-related notifications (they filter appropriately internally)
        created_count = 0
        created_count += generate_for_event_beo_reminders()
        created_count += generate_for_series_group_arrivals()  
        created_count += generate_for_event_with_rooms()
        created_count += generate_for_group_checkins()
        
        # ADD: Generate status-based deadline notifications for all staff users
        staff_users = User.objects.filter(is_staff=True, is_active=True)
        for user in staff_users:
            status_notifications = generate_request_status_deadline_notifications(user)
            sales_calls_notifications = generate_sales_calls_followup_notifications(user)
            created_count += status_notifications + sales_calls_notifications
            if status_notifications > 0:
                logger.info(f"Generated {status_notifications} status-based notifications for user {user.username}")
            if sales_calls_notifications > 0:
                logger.info(f"Generated {sales_calls_notifications} sales calls notifications for user {user.username}")
        
        logger.info(f"Generated {created_count} deadline notifications for request {instance.id}")
    except Exception as e:
        logger.error(f"Error generating deadline notifications for request {instance.id}: {str(e)}")


@receiver(post_save)
def auto_generate_event_agenda_notifications(sender, instance, created, **kwargs):
    # Only process EventAgenda saves
    if sender.__name__ != 'EventAgenda':
        return
    """Auto-generate notifications when EventAgenda dates change"""
    from django.contrib.contenttypes.models import ContentType
    from dashboard.models import Notification
    from dashboard.services.deadline_notifications import generate_for_event_beo_reminders, generate_for_event_with_rooms
    
    try:
        logger.info(f"🔔 SIGNAL DEBUG: EventAgenda {instance.id} saved - Event Date: {instance.event_date}")
        
        # Clean up existing event notifications for this request
        if not created:
            request_content_type = ContentType.objects.get_for_model(instance.request.__class__)
            old_notifications = Notification.objects.filter(
                content_type=request_content_type,
                object_id=instance.request.id,
                notification_type__in=['beo', 'event_start']
            )
            deleted_count = old_notifications.count()
            if deleted_count > 0:
                old_notifications.delete()
                logger.info(f"Cleaned up {deleted_count} old event notifications for request {instance.request.id} before regenerating")
        
        # Regenerate event notifications
        created_count = 0
        created_count += generate_for_event_beo_reminders()
        created_count += generate_for_event_with_rooms()
        
        logger.info(f"Generated {created_count} event notifications for agenda {instance.id}")
    except Exception as e:
        logger.error(f"Error generating event notifications for agenda {instance.id}: {str(e)}")


@receiver(post_save)
def auto_generate_series_entry_notifications(sender, instance, created, **kwargs):
    # Only process SeriesGroupEntry saves
    if sender.__name__ != 'SeriesGroupEntry':
        return
    """Auto-generate notifications when SeriesGroupEntry dates change"""
    from django.contrib.contenttypes.models import ContentType
    from dashboard.models import Notification
    from dashboard.services.deadline_notifications import generate_for_series_group_arrivals
    
    try:
        logger.info(f"🔔 SIGNAL DEBUG: SeriesGroupEntry {instance.id} saved - Arrival Date: {instance.arrival_date}")
        
        # Clean up existing series notifications for this request
        if not created:
            request_content_type = ContentType.objects.get_for_model(instance.request.__class__)
            old_notifications = Notification.objects.filter(
                content_type=request_content_type,
                object_id=instance.request.id,
                notification_type='arrival'
            )
            deleted_count = old_notifications.count()
            if deleted_count > 0:
                old_notifications.delete()
                logger.info(f"Cleaned up {deleted_count} old series notifications for request {instance.request.id} before regenerating")
        
        # Regenerate series group notifications
        created_count = generate_for_series_group_arrivals()
        
        logger.info(f"Generated {created_count} series group notifications for entry {instance.id}")
    except Exception as e:
        logger.error(f"Error generating series notifications for entry {instance.id}: {str(e)}")