"""
Currency toggle views for switching between SAR and USD
"""

from django.shortcuts import redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from .currency_utils import CURRENCY_SYMBOLS

@login_required
@require_POST
def toggle_currency(request):
    """
    Toggle currency between SAR and USD
    """
    current_currency = request.session.get('currency', 'SAR')
    
    # Toggle between SAR and USD
    new_currency = 'USD' if current_currency == 'SAR' else 'SAR'
    
    # Store in session
    request.session['currency'] = new_currency
    
    # Get the referring URL or default to dashboard
    next_url = request.META.get('HTTP_REFERER', reverse('dashboard'))
    
    # Return JSON response for AJAX requests
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'currency': new_currency,
            'symbol': CURRENCY_SYMBOLS.get(new_currency, new_currency),
            'redirect_url': next_url
        })
    
    # Redirect back to the referring page
    return redirect(next_url)

@login_required
def get_currency_status(request):
    """
    Get current currency status
    """
    currency = request.session.get('currency', 'SAR')
    return JsonResponse({
        'currency': currency,
        'symbol': CURRENCY_SYMBOLS.get(currency, currency)
    })
