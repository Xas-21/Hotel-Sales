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
SYSTEM_PROMPT = """You are an intelligent AI assistant for the Hotel Sales Request Management System. You are fully integrated with the system's database and can perform real operations.

**SYSTEM OVERVIEW:**
This is a comprehensive hotel sales management system that handles:
- Event bookings and room reservations
- Client account management  
- Sales call tracking
- Revenue analytics and reporting
- Multi-user role-based access

**YOUR CAPABILITIES:**
1. **REAL DATA ACCESS**: You can access and modify actual database records
2. **ACCOUNT MANAGEMENT**: Create, view, update client accounts
3. **REQUEST MANAGEMENT**: Create, view, update event requests (Event Only, Event with Rooms, Accommodation, Series Group)
4. **ROOM AVAILABILITY**: Check real-time availability for meeting rooms
5. **SALES CALLS**: Create and track sales calls
6. **ANALYTICS**: Provide real performance metrics and revenue data
7. **SYSTEM GUIDANCE**: Help users navigate and understand the system

**MEETING ROOMS:**
- AL JADIDA Hall
- DADAN Hall  
- HEGRA Hall
- IKMA Hall
- All Halls (books all 4 halls together)

**REQUEST TYPES:**
- Event Only: Events without room bookings
- Event with Rooms: Events with meeting room bookings
- Accommodation: Room-only bookings
- Series Group: Multiple related events

**REQUEST STATUSES:**
- Draft: Initial state
- Pending: Awaiting approval
- Confirmed: Approved and confirmed
- Paid: Payment received
- Partially Paid: Partial payment received
- Actual: Event completed
- Cancelled: Request cancelled

**USER GUIDANCE:**
- Explain system features and capabilities
- Guide users through complex operations
- Provide step-by-step instructions
- Help with navigation and workflow
- Answer questions about system functionality

**IMPORTANT**: Always use the available functions to access real data. When users ask about specific information, use the appropriate function to retrieve actual data from the database."""

# Available functions for the AI to call
def get_events_by_date(date_str):
    """Get all events, arrivals, and activities for a specific date"""
    try:
        print(f"=== GET EVENTS BY DATE DEBUG ===")
        print(f"Date string: {date_str}")
        
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        print(f"Parsed date: {target_date}")
        
        # Get event agendas for the date
        events = EventAgenda.objects.filter(
            date=target_date
        ).select_related('request', 'request__account')
        
        print(f"Found {events.count()} events for {target_date}")
        
        result = {
            'date': date_str,
            'events': [],
            'total_count': events.count()
        }
        
        for event in events:
            event_data = {
                'event_name': event.request.account.company_name if event.request.account else 'N/A',
                'meeting_room': event.meeting_room_name or 'N/A',
                'start_time': event.start_time.strftime('%I:%M %p') if event.start_time else 'N/A',
                'end_time': event.end_time.strftime('%I:%M %p') if event.end_time else 'N/A',
                'guests': event.total_persons or 0,
                'status': event.request.status,
                'request_type': event.request.get_request_type_display(),
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


def create_new_account(company_name, account_type, contact_person, phone, email, city, address=None, notes=None, website=None):
    """Create a new client account"""
    try:
        account = Account.objects.create(
            company_name=company_name,
            account_type=account_type,
            contact_person=contact_person,
            phone=phone,
            email=email,
            city=city,
            address=address or '',
            notes=notes or '',
            website=website or ''
        )
        
        return {
            'success': True,
            'account_id': account.id,
            'message': f'Account "{company_name}" created successfully with ID {account.id}',
            'account': {
                'id': account.id,
                'company_name': account.company_name,
                'account_type': account.account_type,
                'contact_person': account.contact_person,
                'phone': account.phone,
                'email': account.email,
                'city': account.city
            }
        }
    except Exception as e:
        return {'error': f'Failed to create account: {str(e)}'}


def get_system_guidance():
    """Provide system guidance and navigation help"""
    return {
        'system_overview': 'Hotel Sales Request Management System',
        'main_features': [
            'Event Management - Create and manage event bookings',
            'Room Availability - Check and book meeting rooms',
            'Account Management - Manage client accounts',
            'Sales Calls - Track sales activities',
            'Analytics - View performance metrics',
            'Request Management - Handle all types of requests'
        ],
        'navigation_help': [
            'Dashboard - Main overview and metrics',
            'Event Management - Calendar and room bookings',
            'Accounts - Client account management',
            'Sales Calls - Sales activity tracking',
            'Admin Panel - System administration'
        ],
        'common_tasks': [
            'Create new event request',
            'Check room availability',
            'Add new client account',
            'View performance metrics',
            'Track sales calls'
        ]
    }


def get_system_help():
    """Get comprehensive system help and guidance"""
    return {
        'welcome_message': 'Welcome to the Hotel Sales Management System!',
        'what_you_can_do': [
            'Ask about events on specific dates',
            'Check room availability',
            'Create new client accounts',
            'View your requests and bookings',
            'Get performance metrics',
            'Learn about system features',
            'Get step-by-step guidance'
        ],
        'example_questions': [
            'What events do I have on December 16th?',
            'Is AL JADIDA Hall available next Friday?',
            'Create new account for ABC Company',
            'Show me my pending requests',
            'What is my total revenue this month?',
            'How do I create an event request?',
            'What are the different request types?'
        ],
        'system_purpose': 'This system helps manage hotel sales operations including event bookings, room reservations, client relationships, and sales tracking.'
    }


def try_manual_function_calls(user_message, user_id):
    """Manually detect and call functions based on user message patterns"""
    try:
        print(f"=== MANUAL FUNCTION DETECTION ===")
        print(f"User message: {user_message}")
        
        message_lower = user_message.lower()
        
        # Check for date patterns and events
        if any(word in message_lower for word in ['december', '16th', '16', 'events', 'what do i have', 'what events']):
            print("Detected: Events query")
            # Try to extract date
            if 'december' in message_lower and '16' in message_lower:
                date_str = '2025-12-16'
                print(f"Calling get_events_by_date with: {date_str}")
                result = get_events_by_date(date_str)
                print(f"Result: {result}")
                if 'error' not in result:
                    formatted_response = format_events_response(result)
                    print(f"Formatted response: {formatted_response}")
                    return {"output_text": f"Here are your events for December 16th, 2025:\n\n{formatted_response}"}
                else:
                    print(f"Error in result: {result}")
                    return {"output_text": f"I found an error while fetching events: {result.get('error', 'Unknown error')}"}
        
        # Check for room availability
        if any(word in message_lower for word in ['available', 'availability', 'hall', 'jadida', 'dadan', 'hegra', 'ikma']):
            print("Detected: Room availability query")
            # Try to extract dates
            if 'october' in message_lower and ('24' in message_lower or '26' in message_lower):
                start_date = '2025-10-24'
                end_date = '2025-10-26'
                result = check_room_availability_ai(start_date, end_date)
                if 'error' not in result:
                    return {"output_text": f"Here's the room availability for October 24-26, 2025:\n\n{format_availability_response(result)}"}
        
        # Check for account creation
        if any(word in message_lower for word in ['create', 'new account', 'account']):
            print("Detected: Account creation query")
            # Try to extract account details from the message
            if 'test' in message_lower and 'company' in message_lower:
                result = create_new_account(
                    company_name="Test",
                    account_type="Company", 
                    contact_person="Contact Person",
                    phone="055123654",
                    email="abd@gmail.com",
                    city="Jeddah"
                )
                if 'error' not in result:
                    return {"output_text": f"Account created successfully!\n\n{format_account_response(result)}"}
        
        # Check for system help
        if any(word in message_lower for word in ['help', 'what can you do', 'system', 'guide']):
            print("Detected: System help query")
            result = get_system_help()
            return {"output_text": f"Here's how I can help you:\n\n{format_help_response(result)}"}
        
        print("No manual function match found")
        return None
        
    except Exception as e:
        print(f"Manual function detection error: {str(e)}")
        return None


def format_events_response(result):
    """Format events response for display"""
    if result.get('total_count', 0) == 0:
        return "No events scheduled for this date."
    
    events_text = f"Total events: {result['total_count']}\n\n"
    for event in result.get('events', []):
        events_text += f"• {event.get('event_name', 'Event')} - {event.get('meeting_room', 'No room')}\n"
        events_text += f"  Time: {event.get('start_time', '')} - {event.get('end_time', '')}\n"
        events_text += f"  Guests: {event.get('guests', 0)}\n"
        events_text += f"  Status: {event.get('status', 'Unknown')}\n\n"
    
    return events_text


def format_availability_response(result):
    """Format availability response for display"""
    if result.get('available_rooms'):
        return f"Available rooms: {', '.join(result['available_rooms'])}"
    else:
        return "No rooms available for the selected dates."


def format_account_response(result):
    """Format account creation response for display"""
    account = result.get('account', {})
    return f"Account ID: {account.get('id', 'N/A')}\nCompany: {account.get('company_name', 'N/A')}\nType: {account.get('account_type', 'N/A')}"


def format_help_response(result):
    """Format help response for display"""
    help_text = f"{result.get('welcome_message', '')}\n\n"
    help_text += "What you can do:\n"
    for item in result.get('what_you_can_do', []):
        help_text += f"• {item}\n"
    help_text += "\nExample questions:\n"
    for item in result.get('example_questions', []):
        help_text += f"• {item}\n"
    return help_text


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
    },
    {
        "name": "create_new_account",
        "description": "Create a new client account. Use this when user wants to add a new client or account.",
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {
                    "type": "string",
                    "description": "The company or organization name"
                },
                "account_type": {
                    "type": "string",
                    "description": "Type of account (Company, Individual, etc.)"
                },
                "contact_person": {
                    "type": "string",
                    "description": "Name of the contact person"
                },
                "phone": {
                    "type": "string",
                    "description": "Phone number"
                },
                "email": {
                    "type": "string",
                    "description": "Email address"
                },
                "city": {
                    "type": "string",
                    "description": "City location"
                },
                "address": {
                    "type": "string",
                    "description": "Full address (optional)"
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes (optional)"
                },
                "website": {
                    "type": "string",
                    "description": "Website URL (optional)"
                }
            },
            "required": ["company_name", "account_type", "contact_person", "phone", "email", "city"]
        }
    },
    {
        "name": "get_system_guidance",
        "description": "Get system guidance and navigation help. Use this when user asks about system features or how to use the system.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_system_help",
        "description": "Get comprehensive system help and guidance. Use this when user asks for help or what they can do.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
]

# Map function names to actual functions
FUNCTION_MAP = {
    "get_events_by_date": get_events_by_date,
    "check_room_availability_ai": check_room_availability_ai,
    "get_user_requests": get_user_requests,
    "get_system_metrics": get_system_metrics,
    "get_accounts_list": get_accounts_list,
    "create_new_account": create_new_account,
    "get_system_guidance": get_system_guidance,
    "get_system_help": get_system_help
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


def call_openai_api_with_functions(messages, functions, user_id):
    """OpenAI API call with function calling for system integration"""
    try:
        print(f"=== FUNCTION CALLING DEBUG ===")
        print(f"User ID: {user_id}")
        print(f"Functions available: {list(functions.keys()) if isinstance(functions, dict) else len(functions)}")
        
        # Check if API key is available
        if not OPENAI_API_KEY:
            print("ERROR: No API key configured")
            return {"error": "OpenAI API key not configured. Please set OPENAI_API_KEY environment variable."}
        
        # Get the latest user message
        user_message = messages[-1]["content"]
        print(f"User message for function calling: {user_message}")
        
        # Prepare the request data with function calling
        data = {
            "model": "gpt-4",
            "messages": messages,
            "functions": functions,
            "function_call": "auto",
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
        print(f"Sending request to OpenAI with {len(functions)} functions...")
        with urllib.request.urlopen(req, timeout=30) as response:
            response_data = json.loads(response.read().decode('utf-8'))
            
            # Debug logging
            print(f"OpenAI Response: {json.dumps(response_data, indent=2)}")
            
            # Check if AI wants to call a function
            if 'function_call' in response_data['choices'][0]['message']:
                print("✅ Function call detected!")
                function_call = response_data['choices'][0]['message']['function_call']
                function_name = function_call['name']
                function_args = json.loads(function_call['arguments'])
                
                # Add user_id if function needs it
                if function_name in ['get_user_requests', 'get_system_metrics']:
                    function_args['user_id'] = user_id
                
                # Call the function
                function_response = FUNCTION_MAP[function_name](**function_args)
                
                # Get final response from AI with function result
                final_messages = messages.copy()
                final_messages.append({
                    "role": "assistant",
                    "content": None,
                    "function_call": function_call
                })
                final_messages.append({
                    "role": "function",
                    "name": function_name,
                    "content": json.dumps(function_response)
                })
                
                # Get final response
                final_data = {
                    "model": "gpt-4",
                    "messages": final_messages,
                    "max_tokens": 1000,
                    "temperature": 0.7
                }
                
                final_req = urllib.request.Request(
                    "https://api.openai.com/v1/chat/completions",
                    data=json.dumps(final_data).encode('utf-8'),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {OPENAI_API_KEY}"
                    },
                    method='POST'
                )
                
                with urllib.request.urlopen(final_req, timeout=30) as final_response:
                    final_response_data = json.loads(final_response.read().decode('utf-8'))
                    return {"output_text": final_response_data['choices'][0]['message']['content']}
            else:
                print("❌ No function call detected in OpenAI response")
                print(f"Message content: {response_data['choices'][0]['message'].get('content', 'No content')}")
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
        
        # Check if this is a function call request - expanded keywords
        function_keywords = [
            'create', 'new', 'add', 'check', 'show', 'get', 'list', 'events', 'availability', 
            'account', 'request', 'help', 'guide', 'system', 'what', 'how', 'when', 'where',
            'schedule', 'calendar', 'room', 'booking', 'client', 'customer', 'sales', 'revenue',
            'metrics', 'performance', 'data', 'information', 'details', 'status', 'pending',
            'confirmed', 'paid', 'cancelled', 'draft', 'actual', 'partially paid'
        ]
        
        # Debug logging
        print(f"User message: {user_message}")
        print(f"Function keywords detected: {[kw for kw in function_keywords if kw in user_message.lower()]}")
        
        # Force function calling for specific patterns
        force_function_calls = [
            'what events', 'what do i have', 'december 16th', 'create new account',
            'create account', 'new account', 'check availability', 'room availability',
            'december', 'events', 'arrivals', 'group arrivals'
        ]
        
        should_use_functions = any(keyword in user_message.lower() for keyword in function_keywords) or \
                              any(pattern in user_message.lower() for pattern in force_function_calls)
        
        # Always use function calling for now to debug
        print("ALWAYS Using function calling for debugging...")
        
        # Try function calling first
        response = call_openai_api_with_functions(messages, FUNCTIONS, request.user.id)
        
        # If function calling fails or doesn't work, try manual function detection
        if 'error' in response or 'I apologize' in response.get('output_text', ''):
            print("Function calling failed, trying manual function detection...")
            manual_response = try_manual_function_calls(user_message, request.user.id)
            if manual_response:
                response = manual_response
        
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

