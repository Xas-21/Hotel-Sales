import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum, Count

from requests.models import Request, EventAgenda
from accounts.models import Account
from event_management.views import get_room_availability

# OpenAI API Configuration
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')

# System knowledge base
SYSTEM_PROMPT = """You are an intelligent assistant for the Hotel Sales Request Management System. You help users manage their hotel sales requests, events, accounts, and analyze their business data.

**System Capabilities:**
1. **Request Management**: Create, view, update event requests (Event Only, Event with Rooms, Accommodation, Series Group)
2. **Calendar & Availability**: Check meeting room availability, view scheduled events
3. **Account Management**: Create and manage client accounts
4. **Analytics**: View performance metrics, revenue data, conversion rates
5. **System Navigation**: Help users understand and navigate the system

**Meeting Rooms Available:**
- AL JADIDA Hall
- DADAN Hall  
- HEGRA Hall
- IKMA Hall
- All Halls (books all 4 halls together)

**Request Status Types:**
- Draft: Initial state
- Pending: Awaiting approval
- Confirmed: Approved and confirmed
- Paid: Payment received
- Partially Paid: Partial payment received
- Actual: Event completed
- Cancelled: Request cancelled

**Key Features:**
- Real-time room availability checking
- Multi-day, multi-room event booking
- Account performance tracking
- Revenue and financial metrics
- Calendar management

When users ask questions, use the available functions to fetch real-time data from the system. Be conversational, helpful, and proactive in offering assistance."""

# Available functions for the AI to call
def get_events_by_date(date_str):
    """Get all events, arrivals, and activities for a specific date"""
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Get event agendas for the date
        events = EventAgenda.objects.filter(
            date=target_date
        ).select_related('request', 'request__account')
        
        result = {
            'date': date_str,
            'events': [],
            'total_count': events.count()
        }
        
        for event in events:
            event_data = {
                'time': f"{event.start_time.strftime('%I:%M %p')} - {event.end_time.strftime('%I:%M %p')}",
                'title': event.request.account.name if event.request.account else 'N/A',
                'type': event.request.get_request_type_display(),
                'room': event.meeting_room_name or 'N/A',
                'guests': event.total_persons,
                'status': event.request.status,
                'request_id': event.request.id
            }
            result['events'].append(event_data)
        
        return result
    except Exception as e:
        return {'error': str(e)}


def check_room_availability_ai(date_str, room_name=None):
    """Check room availability for a specific date"""
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Get availability for all rooms or specific room
        availability = get_room_availability(target_date.isoformat())
        
        if room_name:
            # Filter for specific room
            room_data = next((r for r in availability if r['name'] == room_name), None)
            return {
                'date': date_str,
                'room': room_name,
                'available': room_data['available'] if room_data else False,
                'status': 'Available' if (room_data and room_data['available']) else 'Booked'
            }
        else:
            # Return all rooms
            return {
                'date': date_str,
                'rooms': [
                    {
                        'name': r['name'],
                        'available': r['available'],
                        'status': 'Available' if r['available'] else 'Booked'
                    }
                    for r in availability
                ]
            }
    except Exception as e:
        return {'error': str(e)}


def get_user_requests(user_id, status=None, limit=10):
    """Get user's requests with optional status filter"""
    try:
        query = Request.objects.filter(created_by_id=user_id)
        
        if status:
            query = query.filter(status=status)
        
        requests = query.order_by('-created_at')[:limit]
        
        result = {
            'total_count': query.count(),
            'requests': []
        }
        
        for req in requests:
            req_data = {
                'id': req.id,
                'account': req.account.name if req.account else 'N/A',
                'type': req.get_request_type_display(),
                'status': req.status,
                'created_date': req.created_at.strftime('%Y-%m-%d'),
                'total_amount': str(req.total_amount) if hasattr(req, 'total_amount') else 'N/A'
            }
            result['requests'].append(req_data)
        
        return result
    except Exception as e:
        return {'error': str(e)}


def get_system_metrics(user_id):
    """Get system performance metrics"""
    try:
        # Get all requests for the user
        all_requests = Request.objects.filter(created_by_id=user_id)
        
        # Calculate metrics
        total_requests = all_requests.count()
        confirmed_requests = all_requests.filter(status='Confirmed').count()
        pending_requests = all_requests.filter(status='Pending').count()
        cancelled_requests = all_requests.filter(status='Cancelled').count()
        
        # Get revenue data from event agendas
        total_revenue = EventAgenda.objects.filter(
            request__created_by_id=user_id,
            request__status__in=['Confirmed', 'Paid', 'Partially Paid', 'Actual']
        ).aggregate(
            total=Sum('rental_fees_per_day')
        )['total'] or 0
        
        return {
            'total_requests': total_requests,
            'confirmed_requests': confirmed_requests,
            'pending_requests': pending_requests,
            'cancelled_requests': cancelled_requests,
            'total_revenue': float(total_revenue),
            'conversion_rate': round((confirmed_requests / total_requests * 100), 2) if total_requests > 0 else 0
        }
    except Exception as e:
        return {'error': str(e)}


def get_accounts_list(limit=10):
    """Get list of accounts"""
    try:
        accounts = Account.objects.all().order_by('-created_at')[:limit]
        
        result = {
            'total_count': Account.objects.count(),
            'accounts': []
        }
        
        for account in accounts:
            acc_data = {
                'id': account.id,
                'name': account.name,
                'type': account.account_type,
                'contact_person': account.contact_person,
                'phone': account.phone,
                'email': account.email
            }
            result['accounts'].append(acc_data)
        
        return result
    except Exception as e:
        return {'error': str(e)}


# Function definitions for OpenAI
FUNCTIONS = [
    {
        "name": "get_events_by_date",
        "description": "Get all events, meetings, arrivals, and activities scheduled for a specific date. Use this when user asks 'what do I have on [date]' or 'show me my schedule for [date]'",
        "parameters": {
            "type": "object",
            "properties": {
                "date_str": {
                    "type": "string",
                    "description": "The date in YYYY-MM-DD format (e.g., '2025-10-25')"
                }
            },
            "required": ["date_str"]
        }
    },
    {
        "name": "check_room_availability_ai",
        "description": "Check if meeting rooms are available on a specific date. Use this when user asks about room availability.",
        "parameters": {
            "type": "object",
            "properties": {
                "date_str": {
                    "type": "string",
                    "description": "The date in YYYY-MM-DD format"
                },
                "room_name": {
                    "type": "string",
                    "description": "Optional specific room name (AL JADIDA, DADAN, HEGRA, IKMA, All Halls)",
                    "enum": ["AL JADIDA", "DADAN", "HEGRA", "IKMA", "All Halls"]
                }
            },
            "required": ["date_str"]
        }
    },
    {
        "name": "get_user_requests",
        "description": "Get user's requests with optional status filter. Use this when user asks about their requests, bookings, or specific status requests.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "integer",
                    "description": "The user's ID"
                },
                "status": {
                    "type": "string",
                    "description": "Optional status filter (Pending, Confirmed, Paid, Cancelled, etc.)",
                    "enum": ["Draft", "Pending", "Confirmed", "Paid", "Partially Paid", "Actual", "Cancelled"]
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of requests to return (default 10)",
                    "default": 10
                }
            },
            "required": ["user_id"]
        }
    },
    {
        "name": "get_system_metrics",
        "description": "Get performance metrics including total requests, revenue, conversion rates. Use this when user asks about performance, statistics, or metrics.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "integer",
                    "description": "The user's ID"
                }
            },
            "required": ["user_id"]
        }
    },
    {
        "name": "get_accounts_list",
        "description": "Get list of client accounts. Use this when user asks about accounts or clients.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of accounts to return (default 10)",
                    "default": 10
                }
            }
        }
    }
]

# Map function names to actual functions
FUNCTION_MAP = {
    "get_events_by_date": get_events_by_date,
    "check_room_availability_ai": check_room_availability_ai,
    "get_user_requests": get_user_requests,
    "get_system_metrics": get_system_metrics,
    "get_accounts_list": get_accounts_list
}


def call_openai_api(messages, functions=None):
    """OpenAI API call using direct HTTP - bypasses library issues"""
    try:
        # Check if API key is available
        if not OPENAI_API_KEY:
            return {"error": "OpenAI API key not configured. Please set OPENAI_API_KEY environment variable."}
        
        # Get the latest user message
        user_message = messages[-1]["content"]
        
        # Prepare the request data for chat completions API
        data = {
            "model": "gpt-4",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            "max_tokens": 1000,
            "temperature": 0.7
        }
        
        # Create the request
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(data).encode('utf-8'),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENAI_API_KEY}"
            },
            method='POST'
        )
        
        # Make the request
        with urllib.request.urlopen(req, timeout=30) as response:
            response_data = json.loads(response.read().decode('utf-8'))
            return {"output_text": response_data['choices'][0]['message']['content']}
            
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"OpenAI API HTTP Error: {e.code} - {error_body}")
        return {"error": f"HTTP {e.code}: {error_body}"}
    except Exception as e:
        print(f"OpenAI API error: {str(e)}")
        return {"error": str(e)}


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def chat_api(request):
    """Main chat API endpoint - using direct HTTP calls"""
    try:
        data = json.loads(request.body)
        user_message = data.get('message', '')
        chat_history = data.get('history', [])
        
        if not user_message:
            return JsonResponse({'error': 'Message is required'}, status=400)
        
        # Build messages for OpenAI
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(chat_history)
        messages.append({"role": "user", "content": user_message})
        
        # Simple API call
        response = call_openai_api(messages, FUNCTIONS)
        
        if 'error' in response:
            final_message = f"Sorry, I encountered an error: {response['error']}"
        else:
            final_message = response.get('output_text', 'I apologize, but I couldn\'t process your request.')
        
        # Debug logging
        print(f"Chatbot response: {final_message}")
        print(f"Full response: {response}")
        
        return JsonResponse({
            'success': True,
            'message': final_message,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"Chatbot error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Error processing your request: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
@login_required
def chat_help(request):
    """Get help information about chatbot capabilities"""
    help_text = {
        'capabilities': [
            'Check room availability for specific dates',
            'View your schedule and events',
            'Get system performance metrics',
            'List your requests and bookings',
            'View client accounts',
            'Navigate the system',
            'Answer questions about system features'
        ],
        'example_questions': [
            'What do I have on October 25th?',
            'Is AL JADIDA Hall available next Friday?',
            'Show me my pending requests',
            'What\'s my total revenue this month?',
            'How many confirmed requests do I have?',
            'List all my accounts',
            'How do I create an event request?'
        ]
    }
    return JsonResponse(help_text)

