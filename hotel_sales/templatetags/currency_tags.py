"""
Custom template tags for currency formatting and conversion
"""

from django import template
from django.template import Context
from hotel_sales.currency_utils import format_currency, convert_currency

register = template.Library()

@register.filter
def currency_format(amount, request=None):
    """
    Format amount with current currency, converting from SAR if needed
    """
    if amount is None:
        amount = 0
    return format_currency(amount, request=request, convert_from='SAR')

@register.filter
def currency_convert(amount, from_currency='SAR'):
    """
    Convert amount from one currency to another
    """
    if amount is None:
        amount = 0
    return convert_currency(amount, from_currency, 'USD')
