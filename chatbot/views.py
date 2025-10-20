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
from decimal import Decimal

from requests.models import Request, EventAgenda, RoomEntry, SeriesGroupEntry
from accounts.models import Account
from sales_calls.models import SalesCall
from agreements.models import Agreement
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
            event_date=target_date
        ).select_related('request', 'request__account')
        
        print(f"Found {events.count()} events for {target_date}")
        
        result = {
            'date': date_str,
            'events': [],
            'total_count': events.count()
        }
        
        for event in events:
            event_data = {
                'event_name': event.request.account.name if event.request.account else 'N/A',
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
            name=company_name,
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
                'company_name': account.name,
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


def get_accommodations_by_date(date_str):
    """Get all accommodation arrivals for a specific date"""
    try:
        print(f"=== GET ACCOMMODATIONS BY DATE DEBUG ===")
        print(f"Date string: {date_str}")
        
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        print(f"Parsed date: {target_date}")
        
        # Get accommodation requests for the date
        accommodations = Request.objects.filter(
            check_in_date=target_date,
            request_type__in=['Group Accommodation', 'Individual Accommodation', 'Event with Rooms', 'Series Group']
        ).select_related('account')
        
        print(f"Found {accommodations.count()} accommodations for {target_date}")
        
        # Also check SeriesGroupEntry for series group arrivals
        series_entries = SeriesGroupEntry.objects.filter(
            arrival_date=target_date
        ).select_related('request', 'request__account')
        
        print(f"Found {series_entries.count()} series group entries for {target_date}")
        
        result = {
            'date': date_str,
            'accommodations': [],
            'total_count': accommodations.count() + series_entries.count()
        }
        
        # Add regular accommodations
        for acc in accommodations:
            acc_data = {
                'company_name': acc.account.name if acc.account else 'N/A',
                'request_type': acc.get_request_type_display(),
                'check_in_date': acc.check_in_date.strftime('%Y-%m-%d') if acc.check_in_date else 'N/A',
                'check_out_date': acc.check_out_date.strftime('%Y-%m-%d') if acc.check_out_date else 'N/A',
                'nights': acc.nights or 0,
                'total_rooms': acc.total_rooms or 0,
                'total_cost': float(acc.total_cost) if acc.total_cost else 0,
                'status': acc.status,
                'confirmation_number': acc.confirmation_number or 'Draft',
                'request_id': acc.id
            }
            result['accommodations'].append(acc_data)
        
        # Add series group entries
        for series in series_entries:
            acc_data = {
                'company_name': series.request.account.name if series.request.account else 'N/A',
                'request_type': 'Series Group',
                'check_in_date': series.arrival_date.strftime('%Y-%m-%d'),
                'check_out_date': series.departure_date.strftime('%Y-%m-%d'),
                'nights': series.nights or 0,
                'total_rooms': series.number_of_rooms or 0,
                'total_cost': float(series.get_total_cost()) if series.get_total_cost() else 0,
                'status': series.request.status,
                'confirmation_number': series.request.confirmation_number or 'Draft',
                'request_id': series.request.id
            }
            result['accommodations'].append(acc_data)
        
        return result
    except Exception as e:
        print(f"Error in get_accommodations_by_date: {str(e)}")
        return {'error': str(e)}


def get_sales_calls_by_date(date_str):
    """Get all sales calls for a specific date"""
    try:
        print(f"=== GET SALES CALLS BY DATE DEBUG ===")
        print(f"Date string: {date_str}")
        
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        print(f"Parsed date: {target_date}")
        
        # Get sales calls for the date
        sales_calls = SalesCall.objects.filter(
            visit_date=target_date
        ).select_related('account')
        
        print(f"Found {sales_calls.count()} sales calls for {target_date}")
        
        result = {
            'date': date_str,
            'sales_calls': [],
            'total_count': sales_calls.count()
        }
        
        for call in sales_calls:
            call_data = {
                'company_name': call.account.name if call.account else 'N/A',
                'visit_date': call.visit_date.strftime('%Y-%m-%d'),
                'city': call.city,
                'meeting_subject': call.get_meeting_subject_display(),
                'business_potential': call.business_potential,
                'follow_up_required': call.follow_up_required,
                'follow_up_date': call.follow_up_date.strftime('%Y-%m-%d') if call.follow_up_date else 'N/A',
                'follow_up_completed': call.follow_up_completed,
                'call_id': call.id
            }
            result['sales_calls'].append(call_data)
        
        return result
    except Exception as e:
        print(f"Error in get_sales_calls_by_date: {str(e)}")
        return {'error': str(e)}


def get_total_revenue():
    """Get total revenue from all paid and actual requests"""
    try:
        print(f"=== GET TOTAL REVENUE DEBUG ===")
        
        # Get revenue from paid and actual requests
        revenue_data = Request.objects.filter(
            status__in=['Paid', 'Actual', 'Partially Paid']
        ).aggregate(
            total_revenue=Sum('total_cost'),
            total_requests=Count('id'),
            paid_requests=Count('id', filter=Q(status='Paid')),
            actual_requests=Count('id', filter=Q(status='Actual')),
            partially_paid_requests=Count('id', filter=Q(status='Partially Paid'))
        )
        
        print(f"Revenue data: {revenue_data}")
        
        result = {
            'total_revenue': float(revenue_data['total_revenue'] or 0),
            'total_requests': revenue_data['total_requests'] or 0,
            'paid_requests': revenue_data['paid_requests'] or 0,
            'actual_requests': revenue_data['actual_requests'] or 0,
            'partially_paid_requests': revenue_data['partially_paid_requests'] or 0
        }
        
        return result
    except Exception as e:
        print(f"Error in get_total_revenue: {str(e)}")
        return {'error': str(e)}


def get_room_availability_by_date(date_str):
    """Get room availability for a specific date"""
    try:
        print(f"=== GET ROOM AVAILABILITY BY DATE DEBUG ===")
        print(f"Date string: {date_str}")
        
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        print(f"Parsed date: {target_date}")
        
        # Get all meeting rooms
        all_rooms = ['AL JADIDA', 'DADAN', 'HEGRA', 'IKMA', 'All Halls', 'Board Room', 'Al Badiya', 'La Palma']
        
        # Get booked rooms for the date
        booked_rooms = EventAgenda.objects.filter(
            event_date=target_date
        ).values_list('meeting_room_name', flat=True).distinct()
        
        booked_rooms_list = list(booked_rooms)
        print(f"Booked rooms: {booked_rooms_list}")
        
        # Calculate available rooms
        available_rooms = [room for room in all_rooms if room not in booked_rooms_list]
        
        result = {
            'date': date_str,
            'available_rooms': available_rooms,
            'booked_rooms': booked_rooms_list,
            'total_rooms': len(all_rooms),
            'available_count': len(available_rooms),
            'booked_count': len(booked_rooms_list)
        }
        
        return result
    except Exception as e:
        print(f"Error in get_room_availability_by_date: {str(e)}")
        return {'error': str(e)}


def get_all_requests_summary():
    """Get summary of all requests by type and status"""
    try:
        print(f"=== GET ALL REQUESTS SUMMARY DEBUG ===")
        
        # Get requests by type
        by_type = Request.objects.values('request_type').annotate(
            count=Count('id')
        ).order_by('request_type')
        
        # Get requests by status
        by_status = Request.objects.values('status').annotate(
            count=Count('id')
        ).order_by('status')
        
        # Get total counts
        total_requests = Request.objects.count()
        total_revenue = Request.objects.filter(
            status__in=['Paid', 'Actual', 'Partially Paid']
        ).aggregate(total=Sum('total_cost'))['total'] or 0
        
        result = {
            'total_requests': total_requests,
            'total_revenue': float(total_revenue),
            'by_type': list(by_type),
            'by_status': list(by_status)
        }
        
        return result
    except Exception as e:
        print(f"Error in get_all_requests_summary: {str(e)}")
        return {'error': str(e)}


def extract_date_from_message(message):
    """Extract date from user message in various formats"""
    import re
    from datetime import datetime
    
    message_lower = message.lower()
    
    # Common date patterns
    patterns = [
        # November 25, 2025 or 25 November 2025
        r'(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})',
        r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})\s*,?\s*(\d{4})',
        # 25/11/2025 or 11/25/2025
        r'(\d{1,2})/(\d{1,2})/(\d{4})',
        # 2025-11-25
        r'(\d{4})-(\d{1,2})-(\d{1,2})',
        # November 25 or 25 November (current year)
        r'(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)',
        r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})',
    ]
    
    month_names = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4,
        'may': 5, 'june': 6, 'july': 7, 'august': 8,
        'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    
    for pattern in patterns:
        match = re.search(pattern, message_lower)
        if match:
            groups = match.groups()
            try:
                if len(groups) == 3:
                    if groups[0] in month_names:  # Month Day Year
                        month = month_names[groups[0]]
                        day = int(groups[1])
                        year = int(groups[2])
                    elif groups[1] in month_names:  # Day Month Year
                        day = int(groups[0])
                        month = month_names[groups[1]]
                        year = int(groups[2])
                    else:  # Numeric format
                        if '/' in message:
                            # Try both MM/DD/YYYY and DD/MM/YYYY
                            try:
                                month, day, year = int(groups[0]), int(groups[1]), int(groups[2])
                                if month > 12:  # DD/MM/YYYY
                                    day, month = month, day
                            except:
                                month, day, year = int(groups[0]), int(groups[1]), int(groups[2])
                        else:  # YYYY-MM-DD
                            year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                    
                    return f"{year}-{month:02d}-{day:02d}"
                elif len(groups) == 2:
                    if groups[0] in month_names:  # Month Day (current year)
                        month = month_names[groups[0]]
                        day = int(groups[1])
                        year = datetime.now().year
                    else:  # Day Month (current year)
                        day = int(groups[0])
                        month = month_names[groups[1]]
                        year = datetime.now().year
                    
                    return f"{year}-{month:02d}-{day:02d}"
            except (ValueError, KeyError):
                continue
    
    return None


def get_comprehensive_date_data(date_str):
    """Get all data for a specific date - events, accommodations, sales calls, room availability"""
    try:
        print(f"=== COMPREHENSIVE DATE DATA ===")
        print(f"Date: {date_str}")
        
        # Get all data types
        print("Getting events...")
        events_result = get_events_by_date(date_str)
        print(f"Events result: {events_result}")
        
        print("Getting accommodations...")
        accommodations_result = get_accommodations_by_date(date_str)
        print(f"Accommodations result: {accommodations_result}")
        
        print("Getting sales calls...")
        sales_calls_result = get_sales_calls_by_date(date_str)
        print(f"Sales calls result: {sales_calls_result}")
        
        print("Getting room availability...")
        room_availability_result = get_room_availability_by_date(date_str)
        print(f"Room availability result: {room_availability_result}")
        
        # Build comprehensive response
        response_parts = [f"📅 **COMPLETE SCHEDULE FOR {date_str}**\n"]
        
        # Events
        if events_result.get('total_count', 0) > 0:
            events_text = format_events_response(events_result)
            response_parts.append(f"🎯 **EVENTS**\n{events_text}\n")
        else:
            response_parts.append("🎯 **EVENTS**\nNo events scheduled.\n\n")
        
        # Accommodations
        if accommodations_result.get('total_count', 0) > 0:
            accommodations_text = format_accommodations_response(accommodations_result)
            response_parts.append(f"🏨 **ACCOMMODATIONS**\n{accommodations_text}\n")
        else:
            response_parts.append("🏨 **ACCOMMODATIONS**\nNo accommodations scheduled.\n\n")
        
        # Sales Calls
        if sales_calls_result.get('total_count', 0) > 0:
            sales_calls_text = format_sales_calls_response(sales_calls_result)
            response_parts.append(f"📞 **SALES CALLS**\n{sales_calls_text}\n")
        else:
            response_parts.append("📞 **SALES CALLS**\nNo sales calls scheduled.\n\n")
        
        # Room Availability
        if room_availability_result.get('error'):
            response_parts.append(f"🏨 **ROOM AVAILABILITY**\nError fetching room availability: {room_availability_result.get('error')}\n\n")
        else:
            room_availability_text = format_room_availability_response(room_availability_result)
            response_parts.append(f"🏨 **ROOM AVAILABILITY**\n{room_availability_text}\n")
        
        return {"output_text": "".join(response_parts)}
        
    except Exception as e:
        print(f"Error in get_comprehensive_date_data: {str(e)}")
        return {"output_text": f"I found an error while fetching comprehensive data: {str(e)}"}


def try_manual_function_calls(user_message, user_id):
    """Manually detect and call functions based on user message patterns"""
    try:
        print(f"=== MANUAL FUNCTION DETECTION ===")
        print(f"User message: {user_message}")
        
        message_lower = user_message.lower()
        
        # Extract date from message
        date_str = extract_date_from_message(user_message)
        print(f"Extracted date: {date_str}")
        
        # Check for comprehensive date queries (what do I have, what's on, etc.)
        if any(word in message_lower for word in ['what do i have', 'what\'s on', 'what is on', 'what have i', 'what do we have', 'show me', 'tell me about']):
            if date_str:
                print("Detected: Comprehensive date query")
                print(f"Date extracted: {date_str}")
                return get_comprehensive_date_data(date_str)
            else:
                print("No date extracted from message")
                return {"output_text": "I couldn't extract a date from your message. Please try asking with a specific date like 'What do I have on November 25th?'"}
        
        # Check for specific event queries
        if any(word in message_lower for word in ['events', 'meetings', 'conferences']):
            if date_str:
                print("Detected: Events query")
                result = get_events_by_date(date_str)
                if 'error' not in result:
                    formatted_response = format_events_response(result)
                    return {"output_text": f"Here are your events for {date_str}:\n\n{formatted_response}"}
                else:
                    return {"output_text": f"I found an error while fetching events: {result.get('error', 'Unknown error')}"}
        
        # Check for accommodation queries
        if any(word in message_lower for word in ['accommodations', 'group arrivals', 'arrivals', 'check in', 'check-in', 'guests', 'bookings']):
            if date_str:
                print("Detected: Accommodations query")
                result = get_accommodations_by_date(date_str)
                if 'error' not in result:
                    formatted_response = format_accommodations_response(result)
                    return {"output_text": f"Here are your accommodations for {date_str}:\n\n{formatted_response}"}
                else:
                    return {"output_text": f"I found an error while fetching accommodations: {result.get('error', 'Unknown error')}"}
        
        # Check for sales calls
        if any(word in message_lower for word in ['sales calls', 'visits', 'sales meetings', 'business meetings']):
            if date_str:
                print("Detected: Sales calls query")
                result = get_sales_calls_by_date(date_str)
                if 'error' not in result:
                    formatted_response = format_sales_calls_response(result)
                    return {"output_text": f"Here are your sales calls for {date_str}:\n\n{formatted_response}"}
                else:
                    return {"output_text": f"I found an error while fetching sales calls: {result.get('error', 'Unknown error')}"}
        
        # Check for revenue queries
        if any(word in message_lower for word in ['revenue', 'total revenue', 'income', 'money', 'earnings']):
            print("Detected: Revenue query")
            result = get_total_revenue()
            if 'error' not in result:
                formatted_response = format_revenue_response(result)
                return {"output_text": f"Here's your revenue information:\n\n{formatted_response}"}
            else:
                return {"output_text": f"I found an error while fetching revenue: {result.get('error', 'Unknown error')}"}
        
        # Check for room availability
        if any(word in message_lower for word in ['available', 'availability', 'room', 'hall', 'jadida', 'dadan', 'hegra', 'ikma']):
            if date_str:
                print("Detected: Room availability query")
                result = get_room_availability_by_date(date_str)
                if 'error' not in result:
                    formatted_response = format_room_availability_response(result)
                    return {"output_text": f"Here's the room availability for {date_str}:\n\n{formatted_response}"}
                else:
                    return {"output_text": f"I found an error while fetching room availability: {result.get('error', 'Unknown error')}"}
        
        # Check for account creation
        if any(word in message_lower for word in ['create', 'new account', 'account']):
            print("Detected: Account creation query")
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


def format_accommodations_response(result):
    """Format accommodations response for display"""
    if result.get('total_count', 0) == 0:
        return "No accommodations scheduled for this date."
    
    acc_text = f"Total accommodations: {result['total_count']}\n\n"
    for acc in result.get('accommodations', []):
        acc_text += f"• {acc.get('company_name', 'N/A')} - {acc.get('request_type', 'N/A')}\n"
        acc_text += f"  Check-in: {acc.get('check_in_date', 'N/A')}\n"
        acc_text += f"  Check-out: {acc.get('check_out_date', 'N/A')}\n"
        acc_text += f"  Nights: {acc.get('nights', 0)}\n"
        acc_text += f"  Rooms: {acc.get('total_rooms', 0)}\n"
        acc_text += f"  Cost: ${acc.get('total_cost', 0):,.2f}\n"
        acc_text += f"  Status: {acc.get('status', 'Unknown')}\n"
        acc_text += f"  Confirmation: {acc.get('confirmation_number', 'Draft')}\n\n"
    
    return acc_text


def format_sales_calls_response(result):
    """Format sales calls response for display"""
    if result.get('total_count', 0) == 0:
        return "No sales calls scheduled for this date."
    
    calls_text = f"Total sales calls: {result['total_count']}\n\n"
    for call in result.get('sales_calls', []):
        calls_text += f"• {call.get('company_name', 'N/A')}\n"
        calls_text += f"  Date: {call.get('visit_date', 'N/A')}\n"
        calls_text += f"  City: {call.get('city', 'N/A')}\n"
        calls_text += f"  Subject: {call.get('meeting_subject', 'N/A')}\n"
        calls_text += f"  Potential: {call.get('business_potential', 'N/A')}\n"
        if call.get('follow_up_required'):
            calls_text += f"  Follow-up: {call.get('follow_up_date', 'N/A')}\n"
        calls_text += "\n"
    
    return calls_text


def format_revenue_response(result):
    """Format revenue response for display"""
    revenue_text = f"💰 REVENUE SUMMARY\n\n"
    revenue_text += f"Total Revenue: ${result.get('total_revenue', 0):,.2f}\n"
    revenue_text += f"Total Requests: {result.get('total_requests', 0)}\n"
    revenue_text += f"Paid Requests: {result.get('paid_requests', 0)}\n"
    revenue_text += f"Actual Requests: {result.get('actual_requests', 0)}\n"
    revenue_text += f"Partially Paid: {result.get('partially_paid_requests', 0)}\n"
    
    return revenue_text


def format_room_availability_response(result):
    """Format room availability response for display"""
    avail_text = f"🏨 ROOM AVAILABILITY\n\n"
    avail_text += f"Date: {result.get('date', 'N/A')}\n"
    avail_text += f"Available Rooms: {result.get('available_count', 0)}/{result.get('total_rooms', 0)}\n\n"
    
    if result.get('available_rooms'):
        avail_text += "✅ Available:\n"
        for room in result.get('available_rooms', []):
            avail_text += f"• {room}\n"
        avail_text += "\n"
    
    if result.get('booked_rooms'):
        avail_text += "❌ Booked:\n"
        for room in result.get('booked_rooms', []):
            avail_text += f"• {room}\n"
    
    return avail_text


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
    },
    {
        "name": "get_accommodations_by_date",
        "description": "Get all accommodation arrivals for a specific date. Use this when user asks about group arrivals or accommodations.",
        "parameters": {
            "type": "object",
            "properties": {
                "date_str": {
                    "type": "string",
                    "description": "The date in YYYY-MM-DD format (e.g., '2025-12-16')"
                }
            },
            "required": ["date_str"]
        }
    },
    {
        "name": "get_sales_calls_by_date",
        "description": "Get all sales calls for a specific date. Use this when user asks about sales calls or visits.",
        "parameters": {
            "type": "object",
            "properties": {
                "date_str": {
                    "type": "string",
                    "description": "The date in YYYY-MM-DD format (e.g., '2025-12-16')"
                }
            },
            "required": ["date_str"]
        }
    },
    {
        "name": "get_total_revenue",
        "description": "Get total revenue from all paid and actual requests. Use this when user asks about revenue or income.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_room_availability_by_date",
        "description": "Get room availability for a specific date. Use this when user asks about room availability.",
        "parameters": {
            "type": "object",
            "properties": {
                "date_str": {
                    "type": "string",
                    "description": "The date in YYYY-MM-DD format (e.g., '2025-12-16')"
                }
            },
            "required": ["date_str"]
        }
    },
    {
        "name": "get_all_requests_summary",
        "description": "Get summary of all requests by type and status. Use this when user asks about overall system statistics.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_comprehensive_date_data",
        "description": "Get all data for a specific date including events, accommodations, sales calls, and room availability. Use this when user asks 'what do I have on [date]' or 'show me [date]'.",
        "parameters": {
            "type": "object",
            "properties": {
                "date_str": {
                    "type": "string",
                    "description": "The date in YYYY-MM-DD format (e.g., '2025-11-25')"
                }
            },
            "required": ["date_str"]
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
    "get_system_help": get_system_help,
    "get_accommodations_by_date": get_accommodations_by_date,
    "get_sales_calls_by_date": get_sales_calls_by_date,
    "get_total_revenue": get_total_revenue,
    "get_room_availability_by_date": get_room_availability_by_date,
    "get_all_requests_summary": get_all_requests_summary,
    "get_comprehensive_date_data": get_comprehensive_date_data
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
                
                print(f"Function name: {function_name}")
                print(f"Function args: {function_args}")
                
                # Add user_id if function needs it
                if function_name in ['get_user_requests', 'get_system_metrics']:
                    function_args['user_id'] = user_id
                
                # Call the function
                if function_name in FUNCTION_MAP:
                    print(f"Calling function: {function_name}")
                    function_response = FUNCTION_MAP[function_name](**function_args)
                    print(f"Function response: {function_response}")
                else:
                    print(f"Function {function_name} not found in FUNCTION_MAP")
                    function_response = {"error": f"Function {function_name} not found"}
                
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
        if 'error' in response or 'I apologize' in response.get('output_text', '') or 'No response' in response.get('output_text', ''):
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

