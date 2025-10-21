from django.db import models


class CancellationReason(models.Model):
    """Admin-configurable cancellation reasons"""
    code = models.CharField(max_length=50, unique=True, help_text="Unique identifier")
    label = models.CharField(max_length=200, help_text="Reason description")
    is_refundable = models.BooleanField(default=False, help_text="Allows refund")
    active = models.BooleanField(default=True, help_text="Available for selection")
    sort_order = models.PositiveIntegerField(default=0, help_text="Display order")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'label']
        verbose_name = "Cancellation Reason"
        verbose_name_plural = "Cancellation Reasons"

    def __str__(self):
        return self.label