from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Request, RoomEntry, Transportation, SeriesRoomEntry, SeriesGroupEntry

@receiver(post_save, sender=RoomEntry)
@receiver(post_delete, sender=RoomEntry)
def update_request_totals_from_room(sender, instance, **kwargs):
    """Update request financial totals when room entries change"""
    if instance.request_id:
        try:
            request = Request.objects.get(id=instance.request_id)
            request.update_financial_totals()
        except Request.DoesNotExist:
            pass

@receiver(post_save, sender=Transportation)
@receiver(post_delete, sender=Transportation)
def update_request_totals_from_transport(sender, instance, **kwargs):
    """Update request financial totals when transportation entries change"""
    if instance.request_id:
        try:
            request = Request.objects.get(id=instance.request_id)
            request.update_financial_totals()
        except Request.DoesNotExist:
            pass

@receiver(post_save, sender=SeriesRoomEntry)
@receiver(post_delete, sender=SeriesRoomEntry)
def update_request_totals_from_series_room(sender, instance, **kwargs):
    """Update request financial totals when series room entries change"""
    if instance.series_entry and instance.series_entry.request_id:
        try:
            request = Request.objects.get(id=instance.series_entry.request_id)
            request.update_financial_totals()
        except Request.DoesNotExist:
            pass

@receiver(post_save, sender=SeriesGroupEntry)
@receiver(post_delete, sender=SeriesGroupEntry)
def update_request_totals_from_series_group(sender, instance, **kwargs):
    """Update request financial totals when series group entries change"""
    if instance.request_id:
        try:
            request = Request.objects.get(id=instance.request_id)
            request.update_financial_totals()
        except Request.DoesNotExist:
            pass

@receiver(post_save, sender=Request)
def update_request_totals_on_save(sender, instance, **kwargs):
    """Update financial totals when request dates change"""
    # Only update if this is not already being saved from update_financial_totals
    if not kwargs.get('update_fields'):
        instance.update_financial_totals()