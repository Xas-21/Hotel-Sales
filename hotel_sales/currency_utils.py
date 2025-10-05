"""
Currency utility functions for consistent currency formatting throughout the system.
Supports both USD ($) and SAR (Saudi Riyal) currencies.
"""

from django.conf import settings
from decimal import Decimal

# Default currency settings
DEFAULT_CURRENCY = 'SAR'
CURRENCY_SYMBOLS = {
    'USD': '$',
    'SAR': 'SAR'
}

# Currency conversion rates (SAR to USD)
# Note: In a real application, these should be fetched from an API
CURRENCY_RATES = {
    'SAR_TO_USD': 0.2667,  # 1 SAR = 0.2667 USD (approximate)
    'USD_TO_SAR': 3.75,    # 1 USD = 3.75 SAR (approximate)
}

def get_currency_symbol(request=None):
    """Get the current currency symbol based on session or settings."""
    if request and hasattr(request, 'session'):
        return request.session.get('currency', DEFAULT_CURRENCY)
    return getattr(settings, 'CURRENCY_SYMBOL', DEFAULT_CURRENCY)

def convert_currency(amount, from_currency, to_currency):
    """
    Convert amount from one currency to another.
    
    Args:
        amount: Decimal or float amount to convert
        from_currency: Source currency (USD, SAR)
        to_currency: Target currency (USD, SAR)
    
    Returns:
        Converted amount as Decimal
    """
    if amount is None or amount == 0:
        return Decimal('0')
    
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    
    # No conversion needed if same currency
    if from_currency == to_currency:
        return amount
    
    # Convert based on rates
    if from_currency == 'SAR' and to_currency == 'USD':
        return amount * Decimal(str(CURRENCY_RATES['SAR_TO_USD']))
    elif from_currency == 'USD' and to_currency == 'SAR':
        return amount * Decimal(str(CURRENCY_RATES['USD_TO_SAR']))
    else:
        return amount

def format_currency(amount, currency=None, request=None, convert_from=None):
    """
    Format a decimal amount with the appropriate currency symbol.
    
    Args:
        amount: Decimal or float amount to format
        currency: Optional currency override (USD, SAR)
        request: Optional request object for session-based currency
        convert_from: Optional source currency for conversion
    
    Returns:
        Formatted currency string (e.g., "SAR 1,234.56" or "$1,234.56")
    """
    if amount is None:
        amount = 0
    
    # Convert to Decimal for precise formatting
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    
    # Determine target currency
    if currency is None:
        currency = get_currency_symbol(request)
    
    # Convert currency if needed
    if convert_from and convert_from != currency:
        amount = convert_currency(amount, convert_from, currency)
    
    # Get currency symbol
    symbol = CURRENCY_SYMBOLS.get(currency, currency)
    
    # Format the amount with commas for thousands
    formatted_amount = f"{amount:,.2f}"
    
    # Return formatted currency string
    if currency == 'SAR':
        return f"{symbol} {formatted_amount}"
    else:
        return f"{symbol}{formatted_amount}"

def format_currency_compact(amount, currency=None):
    """
    Format currency in compact form (e.g., "SAR 1.2K" instead of "SAR 1,200.00").
    
    Args:
        amount: Decimal or float amount to format
        currency: Optional currency override (USD, SAR)
    
    Returns:
        Compact formatted currency string
    """
    if amount is None:
        amount = 0
    
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    
    if currency is None:
        currency = get_currency_symbol()
    
    symbol = CURRENCY_SYMBOLS.get(currency, currency)
    
    # Format compact amounts
    if amount >= 1000000:
        return f"{symbol} {amount/1000000:.1f}M"
    elif amount >= 1000:
        return f"{symbol} {amount/1000:.1f}K"
    else:
        return f"{symbol} {amount:.0f}"

def get_currency_context(request=None):
    """
    Get currency context for templates.
    
    Args:
        request: Optional request object for session-based currency
    
    Returns:
        Dictionary with currency information for template context
    """
    currency = get_currency_symbol(request)
    return {
        'currency_symbol': CURRENCY_SYMBOLS.get(currency, currency),
        'currency_code': currency,
        'currency_name': 'Saudi Riyal' if currency == 'SAR' else 'US Dollar',
        'other_currency': 'USD' if currency == 'SAR' else 'SAR',
        'other_currency_symbol': CURRENCY_SYMBOLS.get('USD' if currency == 'SAR' else 'SAR', 'USD' if currency == 'SAR' else 'SAR')
    }
