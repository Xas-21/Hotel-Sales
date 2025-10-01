from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Request as BookingRequest, RoomEntry, Transportation, SeriesRoomEntry, SeriesGroupEntry, EventAgenda

@receiver(post_save, sender=RoomEntry)
@receiver(post_delete, sender=RoomEntry)
def update_request_totals_from_room(sender, instance, **kwargs):
    """Update request financial totals when room entries change"""
    if instance.request_id:
        try:
            request = BookingRequest.objects.get(id=instance.request_id)
            request.update_financial_totals()
        except BookingRequest.DoesNotExist:
            pass

@receiver(post_save, sender=Transportation)
@receiver(post_delete, sender=Transportation)
def update_request_totals_from_transport(sender, instance, **kwargs):
    """Update request financial totals when transportation entries change"""
    if instance.request_id:
        try:
            request = BookingRequest.objects.get(id=instance.request_id)
            request.update_financial_totals()
        except BookingRequest.DoesNotExist:
            pass

@receiver(post_save, sender=SeriesRoomEntry)
@receiver(post_delete, sender=SeriesRoomEntry)
def update_request_totals_from_series_room(sender, instance, **kwargs):
    """Update request financial totals when series room entries change"""
    if instance.series_entry and instance.series_entry.request_id:
        try:
            request = BookingRequest.objects.get(id=instance.series_entry.request_id)
            request.update_financial_totals()
        except BookingRequest.DoesNotExist:
            pass

@receiver(post_save, sender=SeriesGroupEntry)
@receiver(post_delete, sender=SeriesGroupEntry)
def update_request_totals_from_series_group(sender, instance, **kwargs):
    """Update request financial totals when series group entries change"""
    if instance.request_id:
        try:
            request = BookingRequest.objects.get(id=instance.request_id)
            request.update_financial_totals()
        except BookingRequest.DoesNotExist:
            pass

@receiver(post_save, sender=EventAgenda)
@receiver(post_delete, sender=EventAgenda)
def update_request_totals_from_event(sender, instance, **kwargs):
    """Update request financial totals when event agenda entries change"""
    if instance.request_id:
        try:
            request = BookingRequest.objects.get(id=instance.request_id)
            request.update_financial_totals()
        except BookingRequest.DoesNotExist:
            pass

@receiver(post_save, sender=BookingRequest)
def update_request_totals_on_save(sender, instance, **kwargs):
    """Update financial totals when request dates change"""
    # Only update if this is not already being saved from update_financial_totals
    update_fields = kwargs.get('update_fields')
    if not update_fields:
        instance.update_financial_totals()

@receiver(post_save, sender=BookingRequest)
def set_default_deadlines_for_new_requests(sender, instance, created, **kwargs):
    """Set default deadlines for new requests"""
    if created:
        # Set default deadlines for new requests
        instance.set_default_deadlines()
        # Save again with deadlines set
        instance.save(update_fields=['offer_acceptance_deadline', 'deposit_deadline', 'full_payment_deadline'])