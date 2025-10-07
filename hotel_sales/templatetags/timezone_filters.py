"""
Template filters for timezone-aware date and time formatting.
"""
from django import template
from django.utils import timezone
from django.utils.safestring import mark_safe
import pytz
from datetime import datetime

register = template.Library()


@register.filter
def user_timezone(dt, user_tz=None):
    """
    Convert datetime to user's timezone.
    """
    if not dt:
        return dt
    
    if user_tz:
        try:
            user_timezone = pytz.timezone(user_tz)
            if dt.tzinfo is None:
                # If datetime is naive, assume it's in UTC
                dt = pytz.UTC.localize(dt)
            return dt.astimezone(user_timezone)
        except Exception:
            pass
    
    # Fallback to default timezone
    return timezone.localtime(dt)


@register.filter
def format_user_datetime(dt, user_tz=None, format_string='%Y-%m-%d %H:%M:%S'):
    """
    Format datetime for user's timezone.
    """
    if not dt:
        return ''
    
    local_dt = user_timezone(dt, user_tz)
    return local_dt.strftime(format_string)


@register.filter
def format_user_date(dt, user_tz=None):
    """
    Format date for user's timezone.
    """
    return format_user_datetime(dt, user_tz, '%Y-%m-%d')


@register.filter
def format_user_time(dt, user_tz=None):
    """
    Format time for user's timezone.
    """
    return format_user_datetime(dt, user_tz, '%H:%M:%S')


@register.filter
def format_user_datetime_short(dt, user_tz=None):
    """
    Format datetime for user's timezone (short format).
    """
    return format_user_datetime(dt, user_tz, '%m/%d/%Y %H:%M')


@register.filter
def timezone_name(user_tz=None):
    """
    Get timezone name for display.
    """
    if user_tz:
        try:
            tz = pytz.timezone(user_tz)
            return tz.zone
        except Exception:
            pass
    
    return 'Asia/Riyadh'  # Default


@register.filter
def timezone_offset(user_tz=None):
    """
    Get timezone offset for display.
    """
    if user_tz:
        try:
            tz = pytz.timezone(user_tz)
            now = datetime.now(tz)
            offset = now.strftime('%z')
            return f"UTC{offset[:3]}:{offset[3:]}"
        except Exception:
            pass
    
    return 'UTC+03:00'  # Default for Riyadh

