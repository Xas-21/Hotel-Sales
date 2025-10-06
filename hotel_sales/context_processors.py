"""
Context processors for global template context
"""

from .currency_utils import get_currency_context

def currency_context(request):
    """
    Add currency context to all templates
    """
    return get_currency_context(request)


