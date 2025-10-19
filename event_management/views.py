from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum, Count, Avg
from django.db import models
from django.utils import timezone
from datetime import date, timedelta, datetime
from decimal import Decimal
import json

from .models import MeetingRoom, EventBooking, EventMetrics
from accounts.models import Account
from requests.models import Request, EventAgenda
from .signals import map_meeting_room_to_agenda_name
from hotel_sales.currency_utils import get_currency_context, convert_currency
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


@login_required
def event_management_dashboard(request):
    """
    Main Event Management dashboard with calendar, metrics, and event creation.
    """
    # Check if user is staff (required for dashboard access)
    if hasattr(request, 'user') and request.user.is_authenticated and not request.user.is_staff:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("You need staff permissions to access this dashboard.")
    
    # Get date range (default to show ALL events - no date restrictions)
    today = date.today()
    start_date = request.GET.get('start_date', '2020-01-01')  # Show all events from 2020 onwards
    end_date = request.GET.get('end_date', '2030-12-31')     # Show all events until 2030
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        start_date = date(2020, 1, 1)  # Default to 2020
        end_date = date(2030, 12, 31)  # Default to 2030
    
    # Get all accounts for event creation
    accounts = Account.objects.all().order_by('name')
    
    # Get meeting rooms
    combined_rooms = MeetingRoom.get_combined_rooms()
    separate_rooms = MeetingRoom.get_separate_rooms()
    
    # Get events for the date range (both EventBooking and existing Request events)
    event_bookings = EventBooking.objects.filter(
        event_date__gte=start_date,
        event_date__lte=end_date
    ).select_related('account', 'request').prefetch_related('meeting_rooms')
    
    # Get existing events from admin panel (Request with EventAgenda)
    from requests.models import Request, EventAgenda
    existing_events = EventAgenda.objects.filter(
        event_date__gte=start_date,
        event_date__lte=end_date
    ).select_related('request__account')
    
    
    # Combine both types of events for display
    events = list(event_bookings) + list(existing_events)
    
    # Calculate event metrics with MoM calculation
    event_metrics = calculate_event_metrics(start_date, end_date, calculate_mom=True)
    
    # Get room availability for calendar
    room_availability = get_room_availability(start_date, end_date)
    
    
    # Get currency context
    currency_context = get_currency_context(request)
    
    # Convert event metrics to current currency if needed
    current_currency = currency_context['currency_code']
    if current_currency == 'USD':
        event_metrics['total_revenue'] = convert_currency(event_metrics['total_revenue'], 'SAR', 'USD')
        event_metrics['average_revenue_per_event'] = convert_currency(event_metrics['average_revenue_per_event'], 'SAR', 'USD')
        
        # Convert account performance revenue to USD
        for account_name, account_data in event_metrics['account_performance'].items():
            account_data['revenue'] = convert_currency(account_data['revenue'], 'SAR', 'USD')
    
    context = {
        'start_date': start_date,
        'end_date': end_date,
        'accounts': accounts,
        'combined_rooms': combined_rooms,
        'separate_rooms': separate_rooms,
        'events': events,
        'event_metrics': event_metrics,
        'room_availability': room_availability,
        **currency_context,  # Add currency context
    }
    
    return render(request, 'event_management/dashboard.html', context)


@login_required
def create_event(request):
    """
    Create a new event booking.
    """
    if request.method == 'POST':
        try:
            # Get form data
            event_name = request.POST.get('event_name')
            account_id = request.POST.get('account')
            room_ids = request.POST.getlist('meeting_rooms')
            notes = request.POST.get('notes', '')
            
            # Get multi-day event data
            event_dates = request.POST.getlist('event_dates[]')
            start_times = request.POST.getlist('start_times[]')
            end_times = request.POST.getlist('end_times[]')
            
            # New fields
            coffee_break_time = request.POST.get('coffee_break_time')
            lunch_time = request.POST.get('lunch_time')
            dinner_time = request.POST.get('dinner_time')
            style = request.POST.get('style')
            rental_fees_per_day = request.POST.get('rental_fees_per_day', '0.00')
            rate_per_person = request.POST.get('rate_per_person', '0.00')
            total_persons = request.POST.get('total_persons', '0')
            packages = request.POST.get('packages', '')
            
            # Deadline fields
            request_received_date = request.POST.get('request_received_date')
            offer_acceptance_deadline = request.POST.get('offer_acceptance_deadline')
            deposit_deadline = request.POST.get('deposit_deadline')
            full_payment_deadline = request.POST.get('full_payment_deadline')
            
            # Validate required fields
            if not all([event_name, account_id, event_dates, start_times, end_times, room_ids]):
                return JsonResponse({'error': 'Please fill in all required fields.'}, status=400)
            
            # Validate that we have the same number of dates, start times, and end times
            if not (len(event_dates) == len(start_times) == len(end_times)):
                return JsonResponse({'error': 'Please provide matching dates, start times, and end times.'}, status=400)
            
            # Get account
            account = get_object_or_404(Account, id=account_id)
            
            # Check for conflicts for all days
            for i, (event_date, start_time, end_time) in enumerate(zip(event_dates, start_times, end_times)):
                # Check EventBooking conflicts
                booking_conflicts = EventBooking.get_conflicts(
                    event_date, start_time, end_time, room_ids
                )
                
                # Check EventAgenda conflicts (source of truth)
                # Map MeetingRoom names to EventAgenda room names
                room_name_mapping = {
                    'All Halls': 'All Halls',
                    'IKMA': 'IKMA',
                    'HEGRA': 'HEGRA',
                    'DADAN': 'DADAN',
                    'ALJADIDA': 'AL JADIDA',  # Map no space to space
                    'Board Room': 'Board Room',
                    'Al Badia': 'Al Badiya',  # Map different spelling
                    'La Palma': 'La Palma'
                }
                
                agenda_room_names = []
                for room_id in room_ids:
                    room = MeetingRoom.objects.get(id=room_id)
                    agenda_room_name = room_name_mapping.get(room.name, room.name)
                    agenda_room_names.append(agenda_room_name)
                
                agenda_conflicts = EventAgenda.objects.filter(
                    event_date=event_date,
                    meeting_room_name__in=agenda_room_names
                ).exclude(
                    # Exclude events that don't overlap in time
                    models.Q(start_time__gte=end_time) | models.Q(end_time__lte=start_time)
                )
                
                if booking_conflicts.exists() or agenda_conflicts.exists():
                    conflict_rooms = []
                    if booking_conflicts.exists():
                        conflict_rooms.extend([booking.get_room_names() for booking in booking_conflicts])
                    if agenda_conflicts.exists():
                        conflict_rooms.extend([agenda.meeting_room_name for agenda in agenda_conflicts])
                    
                    return JsonResponse({
                        'error': f'Room conflict detected for {event_date} at {start_time}-{end_time}. Conflicting rooms: {", ".join(set(conflict_rooms))}'
                    }, status=400)
            
            # Create Request first
            request_obj = Request.objects.create(
                request_type='Event without Rooms',
                account=account,
                request_received_date=request_received_date or timezone.now().date(),
                offer_acceptance_deadline=offer_acceptance_deadline,
                deposit_deadline=deposit_deadline,
                full_payment_deadline=full_payment_deadline,
                status='Draft',
                notes=f"Multi-day Event: {event_name}\n{notes}"
            )
            
            # Create single EventBooking (first day)
            first_date = event_dates[0]
            first_start_time = start_times[0]
            first_end_time = end_times[0]
            
            # Create EventBooking without triggering signals
            booking = EventBooking(
                event_name=event_name,
                account=account,
                event_date=first_date,
                start_time=first_start_time,
                end_time=first_end_time,
                notes=notes,
                created_by=request.user,
                request=request_obj,
                # New fields
                coffee_break_time=coffee_break_time if coffee_break_time else None,
                lunch_time=lunch_time if lunch_time else None,
                dinner_time=dinner_time if dinner_time else None,
                style=style,
                rental_fees_per_day=Decimal(rental_fees_per_day),
                rate_per_person=Decimal(rate_per_person),
                total_persons=int(total_persons),
                packages=packages,
                # Deadline fields
                request_received_date=request_received_date,
                offer_acceptance_deadline=offer_acceptance_deadline,
                deposit_deadline=deposit_deadline,
                full_payment_deadline=full_payment_deadline,
            )
            booking._skip_signal = True  # Prevent signal from creating duplicate EventAgenda
            booking.save()
            
            # Add selected rooms
            booking.meeting_rooms.set(room_ids)
            
            # Room name mapping for EventAgenda
            room_name_mapping = {
                'All Halls': 'All Halls',
                'IKMA': 'IKMA',
                'HEGRA': 'HEGRA',
                'DADAN': 'DADAN',
                'ALJADIDA': 'AL JADIDA',  # Map no space to space
                'Board Room': 'Board Room',
                'Al Badia': 'Al Badiya',  # Map different spelling
                'La Palma': 'La Palma'
            }
            
            # Get all selected rooms
            selected_rooms = list(booking.meeting_rooms.all())
            
            # Create EventAgenda entries for all days and all rooms
            # For each day: first room gets full details, other rooms get zero details
            total_entries_created = 0
            for i, (event_date, start_time, end_time) in enumerate(zip(event_dates, start_times, end_times)):
                # Create one EventAgenda per room for this day
                for room_index, room in enumerate(selected_rooms):
                    # Map the room name correctly
                    agenda_room_name = room_name_mapping.get(room.name, room.name)
                    
                    # Only first room on each day gets full details
                    if room_index == 0:
                        # Primary room gets full details
                        persons = int(total_persons)
                        rate = Decimal(rate_per_person)
                        fees = Decimal(rental_fees_per_day)
                    else:
                        # Other rooms get zero details (just to block availability)
                        persons = 0
                        rate = Decimal('0.00')
                        fees = Decimal('0.00')
                    
                    # Create EventAgenda without triggering signals
                    agenda = EventAgenda(
                        request=request_obj,
                        event_date=event_date,
                        event_name=event_name,
                        start_time=start_time,
                        end_time=end_time,
                        meeting_room_name=agenda_room_name,
                        agenda_details=event_name,
                        coffee_break_time=coffee_break_time if coffee_break_time else None,
                        lunch_time=lunch_time if lunch_time else None,
                        dinner_time=dinner_time if dinner_time else None,
                        style=style,
                        rental_fees_per_day=fees,
                        rate_per_person=rate,
                        total_persons=persons,
                        packages=packages if room_index == 0 else '',  # Only first room gets packages
                    )
                    agenda._skip_signal = True  # Prevent signal from creating duplicate EventBooking
                    agenda.save()
                    total_entries_created += 1
            
            return JsonResponse({
                'success': True,
                'message': f'Multi-day Event "{event_name}" created successfully with {len(event_dates)} days × {len(selected_rooms)} rooms = {total_entries_created} EventAgenda entries!',
                'request_id': request_obj.id,
                'event_agenda_count': total_entries_created,
                'admin_url': f'/admin/requests/request/{request_obj.id}/change/'
            })
            
        except Exception as e:
            return JsonResponse({'error': f'Error creating event: {str(e)}'}, status=500)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@login_required
def check_availability(request):
    """
    API endpoint to check room availability for given date/time/rooms.
    """
    event_date = request.GET.get('date')
    start_time = request.GET.get('start_time')
    end_time = request.GET.get('end_time')
    room_ids = request.GET.getlist('rooms')
    
    if not all([event_date, start_time, end_time, room_ids]):
        return JsonResponse({'error': 'Missing required parameters'}, status=400)
    
    try:
        conflicts = EventBooking.get_conflicts(event_date, start_time, end_time, room_ids)
        
        if conflicts.exists():
            conflict_details = []
            for conflict in conflicts:
                conflict_details.append({
                    'id': conflict.id,
                    'event_name': conflict.event_name,
                    'start_time': conflict.start_time.strftime('%H:%M'),
                    'end_time': conflict.end_time.strftime('%H:%M'),
                    'rooms': conflict.get_room_names(),
                    'status': conflict.status
                })
            
            return JsonResponse({
                'available': False,
                'conflicts': conflict_details
            })
        else:
            return JsonResponse({'available': True})
            
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def event_metrics_api(request):
    """
    API endpoint for event metrics data.
    """
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    if not start_date or not end_date:
        return JsonResponse({'error': 'Start and end dates required'}, status=400)
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'}, status=400)
    
    metrics = calculate_event_metrics(start_date, end_date)
    return JsonResponse(metrics)


# Global cache for calendar events to prevent duplicate API calls
_calendar_events_cache = {}

@login_required
def calendar_events_api(request):
    """
    API endpoint for calendar events data.
    """
    start_date = request.GET.get('start')
    end_date = request.GET.get('end')
    
    if not start_date or not end_date:
        return JsonResponse({'error': 'Start and end dates required'}, status=400)
    
    # Create cache key
    cache_key = f"{start_date}_{end_date}"
    
    # Check cache first (with 5-second expiry for faster color updates)
    import time
    if cache_key in _calendar_events_cache:
        cached_data, timestamp = _calendar_events_cache[cache_key]
        if time.time() - timestamp < 5:  # 5 seconds cache for faster updates
            print(f"RETURNING CACHED EVENTS for {cache_key}")
            return JsonResponse(cached_data, safe=False)
    
    try:
        # Handle both ISO format and simple YYYY-MM-DD format
        if 'T' in start_date:
            start_date = datetime.fromisoformat(start_date.split('T')[0]).date()
        else:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            
        if 'T' in end_date:
            end_date = datetime.fromisoformat(end_date.split('T')[0]).date()
        else:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except (ValueError, AttributeError):
        return JsonResponse({'error': 'Invalid date format'}, status=400)
    
    # Show EventAgenda events within the requested date range
    from requests.models import EventAgenda
    existing_events = EventAgenda.objects.filter(
        event_date__gte=start_date,
        event_date__lte=end_date
    ).select_related('request__account').order_by('event_date', 'start_time')
    
    events_data = []
    seen_event_ids = set()  # Track unique event IDs to prevent duplicates
    seen_event_keys = set()  # Track by event name + date + time to prevent true duplicates
    
    # Add EventAgenda events only (these are the source of truth)
    for event in existing_events:
        # Create a unique key for this event based on content, not just ID
        event_key = f"{event.event_name}_{event.event_date}_{event.start_time}_{event.end_time}"
        
        # Skip if already added (deduplication by both ID and content)
        event_id = f"agenda_{event.id}"
        if event_id in seen_event_ids or event_key in seen_event_keys:
            print(f"DUPLICATE FILTERED: ID={event_id}, Key={event_key}, Event={event.event_name}")
            continue
            
        seen_event_ids.add(event_id)
        seen_event_keys.add(event_key)
        
        # Create datetime objects for proper time display
        start_datetime = f"{event.event_date}T{event.start_time}"
        end_datetime = f"{event.event_date}T{event.end_time}"
        
        # Color coding based on request status
        status_colors = {
            'Cancelled': '#dc3545',      # Red
            'Pending': '#fd7e14',        # Orange
            'Draft': '#6c757d',          # Gray
            'Paid': '#198754',           # Light Green
            'Confirmed': '#198754',      # Light Green
            'Partially Paid': '#198754', # Light Green
            'Actual': '#0d5016',         # Dark Green
        }
        
        # Get the color for this event's status
        event_color = status_colors.get(event.request.status, '#fd7e14')  # Default orange
        
        
        # Create clear title with meeting room and timing
        room_info = f" - {event.meeting_room_name}" if event.meeting_room_name else ""
        timing_info = f" ({event.start_time.strftime('%H:%M')}-{event.end_time.strftime('%H:%M')})"
        event_title = f"{event.event_name or event.agenda_details}{room_info}{timing_info}"
        
        events_data.append({
            'id': event_id,
            'title': event_title,
            'start': start_datetime,
            'end': end_datetime,
            'allDay': False,  # Show specific times, not all-day
            'backgroundColor': event_color,
            'borderColor': event_color,
            'textColor': '#ffffff',
            'url': f"/admin/requests/request/{event.request.id}/change/",
            'extendedProps': {
                'rooms': event.meeting_room_name,
                'account': event.request.account.name,
                'status': event.request.status,
                'type': 'event_agenda',
                'timing': f"{event.start_time.strftime('%H:%M')} - {event.end_time.strftime('%H:%M')}",
                'status_color': event_color
            }
        })
    
    # Cache the result
    _calendar_events_cache[cache_key] = (events_data, time.time())
    print(f"CACHED EVENTS for {cache_key}: {len(events_data)} events")
    
    return JsonResponse(events_data, safe=False)


@login_required
def room_availability_api(request):
    """
    API endpoint for room availability on a specific date.
    """
    date_str = request.GET.get('date')
    start_time = request.GET.get('start_time')
    end_time = request.GET.get('end_time')
    rooms = request.GET.get('rooms', '')
    
    if not date_str:
        return JsonResponse({'error': 'Date parameter required'}, status=400)
    
    try:
        from datetime import datetime
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'}, status=400)
    
    # If specific time and rooms are provided, check for conflicts
    if start_time and end_time and rooms:
        room_ids = [int(room_id) for room_id in rooms.split(',') if room_id.strip()]
        
        # Check EventAgenda conflicts
        room_name_mapping = {
            'All Halls': 'All Halls',
            'IKMA': 'IKMA',
            'HEGRA': 'HEGRA',
            'DADAN': 'DADAN',
            'ALJADIDA': 'AL JADIDA',
            'Board Room': 'Board Room',
            'Al Badia': 'Al Badiya',
            'La Palma': 'La Palma'
        }
        
        agenda_room_names = []
        has_main_hall = False
        main_halls = ['AL JADIDA', 'DADAN', 'HEGRA', 'IKMA']
        
        for room_id in room_ids:
            room = MeetingRoom.objects.get(id=room_id)
            agenda_room_name = room_name_mapping.get(room.name, room.name)
            agenda_room_names.append(agenda_room_name)
            
            # Check if any of the selected rooms is a main hall
            if agenda_room_name in main_halls or room.name in main_halls:
                has_main_hall = True
        
        # Build query for conflicts
        from django.db.models import Q
        conflict_query = Q(meeting_room_name__in=agenda_room_names)
        
        # If booking any main hall, also check for "All Halls" conflicts
        # If booking "All Halls", also check for individual main hall conflicts
        if has_main_hall:
            conflict_query |= Q(meeting_room_name='All Halls')
        if 'All Halls' in agenda_room_names:
            conflict_query |= Q(meeting_room_name__in=main_halls)
        
        # Include ALL request statuses for conflict checking EXCEPT cancelled
        conflicts = EventAgenda.objects.filter(
            event_date=target_date,
            request__status__in=['Confirmed', 'Paid', 'Actual', 'Draft', 'Tentative', 'Pending', 'Partially Paid']
            # Exclude 'Cancelled' status from affecting room availability
        ).filter(
            conflict_query
        ).exclude(
            # Exclude events that don't overlap in time
            models.Q(start_time__gte=end_time) | models.Q(end_time__lte=start_time)
        )
        
        if conflicts.exists():
            conflict_rooms = list(conflicts.values_list('meeting_room_name', flat=True))
            return JsonResponse({
                'conflicts': conflict_rooms,
                'message': f'Room conflicts detected for {target_date} at {start_time}-{end_time}'
            })
        
        return JsonResponse({
            'conflicts': [],
            'message': 'Rooms are available'
        })
    
    # Get room availability for the specific date
    availability = get_room_availability(target_date, target_date)
    
    # Convert to JSON-serializable format
    json_availability = {}
    for room_name, room_data in availability.items():
        json_availability[room_name] = {
            'room': {
                'name': room_data['room'].name,
                'display_name': room_data['room'].display_name,
                'capacity': room_data['room'].capacity,
                'room_type': room_data['room'].room_type
            },
            'events': room_data['events']
        }
    
    return JsonResponse({
        'success': True,
        'date': target_date.strftime('%Y-%m-%d'),
        'availability': json_availability
    })


def calculate_event_metrics(start_date, end_date, calculate_mom=False):
    """
    Calculate comprehensive event metrics for ALL events in the system.
    Prevents duplication by only counting EventAgenda (source of truth).
    """
    # Get ALL EventBooking events (no date restrictions for total counts)
    event_bookings = EventBooking.objects.filter(
        status__in=['Draft', 'Confirmed', 'Pending', 'Paid', 'Partially Paid', 'Actual']
    )
    
    # Basic metrics - calculate from ALL EventAgenda (source of truth)
    from requests.models import EventAgenda
    from datetime import timedelta
    
    event_agendas = EventAgenda.objects.filter(
        request__status__in=['Draft', 'Confirmed', 'Pending', 'Paid', 'Partially Paid', 'Actual']
    )
    
    # Calculate previous period for MoM if requested
    previous_account_performance = {}
    if calculate_mom and start_date and end_date:
        period_days = (end_date - start_date).days
        mom_start_date = start_date - timedelta(days=period_days + 1)
        mom_end_date = start_date - timedelta(days=1)
        
        # Get previous period event agendas - ALL statuses EXCEPT Cancelled for Account Performance
        previous_event_agendas = EventAgenda.objects.filter(
            request__status__in=['Draft', 'Confirmed', 'Pending', 'Paid', 'Partially Paid', 'Actual'],
            event_date__gte=mom_start_date,
            event_date__lte=mom_end_date
        )
        
        # Calculate previous period account performance
        for agenda in previous_event_agendas:
            account_name = agenda.request.account.name
            if account_name not in previous_account_performance:
                previous_account_performance[account_name] = Decimal('0.00')
            daily_revenue = (agenda.rate_per_person * agenda.total_persons) + agenda.rental_fees_per_day
            previous_account_performance[account_name] += daily_revenue
    
    total_events = event_agendas.count()
    
    # Calculate total revenue: (rate_per_person * total_persons) + rental_fees_per_day for each agenda
    total_revenue = Decimal('0.00')
    total_attendees = 0
    
    for agenda in event_agendas:
        # Full event cost per day
        daily_revenue = (agenda.rate_per_person * agenda.total_persons) + agenda.rental_fees_per_day
        total_revenue += daily_revenue
        total_attendees += agenda.total_persons
    
    average_revenue = total_revenue / total_events if total_events > 0 else Decimal('0.00')
    
    # Room metrics
    room_metrics = {}
    for room in MeetingRoom.objects.all():
        room_events = event_bookings.filter(meeting_rooms=room).count()
        room_metrics[room.name.lower().replace(' ', '_')] = room_events
    
    # Account performance - calculate from EventAgenda for accuracy
    # Include ALL statuses EXCEPT Cancelled for Account Performance display
    account_performance_agendas = event_agendas.filter(
        request__status__in=['Draft', 'Confirmed', 'Pending', 'Paid', 'Partially Paid', 'Actual']
    )
    
    account_performance = {}
    for agenda in account_performance_agendas:
        account_name = agenda.request.account.name
        if account_name not in account_performance:
            account_performance[account_name] = {
                'events': 0,
                'revenue': Decimal('0.00'),
                'account_type': agenda.request.account.account_type,
                'mom_percentage': 0.0
            }
        account_performance[account_name]['events'] += 1
        # Full event revenue per day
        daily_revenue = (agenda.rate_per_person * agenda.total_persons) + agenda.rental_fees_per_day
        account_performance[account_name]['revenue'] += daily_revenue
    
    # Calculate MoM percentage for each account if enabled
    if calculate_mom:
        for account_name, account_data in account_performance.items():
            current_revenue = account_data['revenue']
            previous_revenue = previous_account_performance.get(account_name, Decimal('0.00'))
            
            if previous_revenue > 0:
                mom_percentage = float(((current_revenue - previous_revenue) / previous_revenue) * 100)
            else:
                mom_percentage = 100.0 if current_revenue > 0 else 0.0
            
            account_data['mom_percentage'] = mom_percentage
    
    # Sort by revenue
    account_performance = dict(sorted(
        account_performance.items(), 
        key=lambda x: x[1]['revenue'], 
        reverse=True
    ))
    
    return {
        'total_events': total_events,
        'total_revenue': total_revenue,
        'total_attendees': total_attendees,
        'average_revenue_per_event': average_revenue,
        'room_metrics': room_metrics,
        'account_performance': account_performance
    }


def get_room_availability(start_date, end_date):
    """
    Get room availability data for calendar display.
    Only fetch from EventAgenda to prevent duplicates (EventBooking syncs with EventAgenda).
    """
    availability = {}
    
    # Map MeetingRoom names to EventAgenda room names
    room_name_mapping = {
        'All Halls': 'All Halls',
        'IKMA': 'IKMA',
        'HEGRA': 'HEGRA',
        'DADAN': 'DADAN',
        'ALJADIDA': 'AL JADIDA',  # Map no space to space
        'Board Room': 'Board Room',
        'Al Badia': 'Al Badiya',  # Map different spelling
        'La Palma': 'La Palma'
    }
    
    for room in MeetingRoom.objects.filter(is_active=True):
        # Get the correct room name for EventAgenda lookup
        agenda_room_name = room_name_mapping.get(room.name, room.name)
        
        # Get events from EventAgenda only (source of truth, prevents duplicates)
        # Include ALL request statuses for room availability calculations
        from requests.models import EventAgenda
        from django.db.models import Q
        
        # Build query to include direct room bookings
        room_query = Q(meeting_room_name=agenda_room_name)
        
        # If this is one of the main halls, also check for "All Halls" bookings
        main_halls = ['AL JADIDA', 'DADAN', 'HEGRA', 'IKMA']
        if agenda_room_name in main_halls or room.name in main_halls:
            room_query |= Q(meeting_room_name='All Halls')
        
        existing_events = EventAgenda.objects.filter(
            room_query,
            event_date__gte=start_date,
            event_date__lte=end_date,
            request__status__in=['Confirmed', 'Paid', 'Actual', 'Draft', 'Tentative', 'Pending', 'Partially Paid']
            # Exclude 'Cancelled' status from affecting room availability
        ).select_related('request').order_by('event_date', 'start_time')
        
        # Convert to display format
        all_events = []
        for event in existing_events:
            all_events.append({
                'event_date': event.event_date,
                'start_time': event.start_time,
                'end_time': event.end_time,
                'event_name': event.event_name or event.agenda_details or f"Event {event.request.id}",
                'status': event.request.status,
                'type': 'request'
            })
        
        availability[room.name] = {
            'room': room,
            'events': all_events
        }
    
    return availability


def create_request_from_booking(booking):
    """
    Create a Request object from an EventBooking.
    This integrates with the existing request system.
    """
    # Determine request type based on room selection
    has_combined_rooms = booking.meeting_rooms.filter(combined_group='main_halls').exists()
    request_type = 'Event with Rooms' if has_combined_rooms else 'Event without Rooms'
    
    # Create the request
    request_obj = Request.objects.create(
        request_type=request_type,
        account=booking.account,
        request_received_date=booking.created_at.date(),
        status='Draft',  # Start as draft, can be changed later
        notes=f"Event: {booking.event_name}\n{booking.notes}"
    )
    
    # Create EventAgenda entry with all fields
    primary_room = booking.meeting_rooms.first()
    if primary_room:
        EventAgenda.objects.create(
            request=request_obj,
            event_date=booking.event_date,
            start_time=booking.start_time,
            end_time=booking.end_time,
            meeting_room_name=primary_room.name,
            agenda_details=booking.event_name,
            coffee_break_time=booking.coffee_break_time,
            lunch_time=booking.lunch_time,
            dinner_time=booking.dinner_time,
            style=booking.style,
            rental_fees_per_day=booking.rental_fees_per_day,
            rate_per_person=booking.rate_per_person,
            total_persons=booking.total_persons,
            packages=booking.packages
        )
    
    return request_obj


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def create_account_api(request):
    """
    API endpoint to create a new account from the Event Management page.
    """
    try:
        # Get form data
        name = request.POST.get('name', '').strip()
        account_type = request.POST.get('account_type', '').strip()
        contact_person = request.POST.get('contact_person', '').strip()
        position = request.POST.get('position', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        city = request.POST.get('city', '').strip()
        website = request.POST.get('website', '').strip()
        address = request.POST.get('address', '').strip()
        notes = request.POST.get('notes', '').strip()
        
        # Validate required fields
        if not name or not account_type:
            return JsonResponse({
                'success': False,
                'error': 'Company name and account type are required.'
            }, status=400)
        
        # Check if account with same name already exists
        if Account.objects.filter(name__iexact=name).exists():
            return JsonResponse({
                'success': False,
                'error': f'An account with the name "{name}" already exists.'
            }, status=400)
        
        # Create new account
        account = Account.objects.create(
            name=name,
            account_type=account_type,
            contact_person=contact_person or None,
            position=position or None,
            phone=phone or None,
            email=email or None,
            city=city or None,
            website=website or None,
            address=address or None,
            notes=notes or None
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Account "{name}" created successfully!',
            'account_id': account.id,
            'account_name': account.name
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error creating account: {str(e)}'
        }, status=500)


@login_required
def api_event_account_performance(request):
    """
    API endpoint to compute event account performance with custom date range and account search.
    Query params:
      - start_date (YYYY-MM-DD)
      - end_date (YYYY-MM-DD)
      - account (substring to filter account name, case-insensitive)
    """
    from requests.models import EventAgenda
    
    # Parse dates with defaults
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        if start_date_str and end_date_str:
            start_date_val = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date_val = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        else:
            # Default to all time
            start_date_val = date(2020, 1, 1)
            end_date_val = date(2030, 12, 31)
    except ValueError:
        return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)

    account_query = request.GET.get('account', '').strip()

    # Get current currency setting
    currency_context = get_currency_context(request)
    current_currency = currency_context['currency_code']

    # Calculate previous period for MoM comparison
    period_days = (end_date_val - start_date_val).days
    mom_start_date = start_date_val - timedelta(days=period_days + 1)
    mom_end_date = start_date_val - timedelta(days=1)

    # Current period event agendas - ALL statuses EXCEPT Cancelled for Account Performance
    current_event_agendas = EventAgenda.objects.filter(
        request__status__in=['Draft', 'Confirmed', 'Pending', 'Paid', 'Partially Paid', 'Actual'],
        event_date__gte=start_date_val,
        event_date__lte=end_date_val
    ).select_related('request__account')
    
    # Previous period event agendas for MoM - ALL statuses EXCEPT Cancelled
    previous_event_agendas = EventAgenda.objects.filter(
        request__status__in=['Draft', 'Confirmed', 'Pending', 'Paid', 'Partially Paid', 'Actual'],
        event_date__gte=mom_start_date,
        event_date__lte=mom_end_date
    ).select_related('request__account')

    # Apply account filter if provided
    if account_query:
        current_event_agendas = current_event_agendas.filter(request__account__name__icontains=account_query)
        previous_event_agendas = previous_event_agendas.filter(request__account__name__icontains=account_query)

    # Build current period account performance
    current_account_performance = {}
    for agenda in current_event_agendas:
        account_name = agenda.request.account.name
        if account_name not in current_account_performance:
            current_account_performance[account_name] = {
                'events': 0,
                'revenue': Decimal('0.00'),
                'account_type': agenda.request.account.account_type,
            }
        current_account_performance[account_name]['events'] += 1
        # Full event revenue per day
        daily_revenue = (agenda.rate_per_person * agenda.total_persons) + agenda.rental_fees_per_day
        current_account_performance[account_name]['revenue'] += daily_revenue

    # Build previous period account performance
    previous_account_performance = {}
    for agenda in previous_event_agendas:
        account_name = agenda.request.account.name
        if account_name not in previous_account_performance:
            previous_account_performance[account_name] = Decimal('0.00')
        daily_revenue = (agenda.rate_per_person * agenda.total_persons) + agenda.rental_fees_per_day
        previous_account_performance[account_name] += daily_revenue

    # Finalize results with MoM calculations
    results = []
    for account_name, data in current_account_performance.items():
        events = data['events']
        revenue = data['revenue']
        
        # Calculate MoM percentage
        previous_revenue = previous_account_performance.get(account_name, Decimal('0.00'))
        if previous_revenue > 0:
            mom_percentage = float(((revenue - previous_revenue) / previous_revenue) * 100)
        else:
            mom_percentage = 100.0 if revenue > 0 else 0.0
        
        # Convert currency if needed
        if current_currency == 'USD':
            revenue = convert_currency(revenue, 'SAR', 'USD')
        
        results.append({
            'account_name': account_name,
            'account_type': data['account_type'],
            'events': events,
            'revenue': float(revenue),
            'mom_percentage': mom_percentage,
        })

    # Sort by revenue desc
    results.sort(key=lambda x: x['revenue'], reverse=True)

    return JsonResponse({'results': results})


@login_required
def api_recent_event_requests(request):
    """
    API endpoint to get recent event requests (Event Only and Event with Rooms).
    Excludes cancelled requests.
    """
    from requests.models import Request
    
    # Get recent event requests (Event Only and Event with Rooms)
    recent_requests = Request.objects.filter(
        request_type__in=['Event without Rooms', 'Event with Rooms'],
        status__in=['Draft', 'Confirmed', 'Pending', 'Paid', 'Partially Paid', 'Actual']
        # Exclude cancelled requests
    ).select_related('account').order_by('-request_received_date')[:10]
    
    results = []
    for req in recent_requests:
        # Get the first EventAgenda for basic info
        first_agenda = req.event_agendas.first()
        
        results.append({
            'id': req.id,
            'request_type': req.request_type,
            'account_name': req.account.name,
            'account_type': req.account.account_type,
            'status': req.status,
            'request_received_date': req.request_received_date.strftime('%Y-%m-%d'),
            'event_date': first_agenda.event_date.strftime('%Y-%m-%d') if first_agenda else None,
            'event_name': first_agenda.event_name if first_agenda else 'No Event Details',
            'meeting_room': first_agenda.meeting_room_name if first_agenda else None,
            'url': f"/admin/requests/request/{req.id}/change/"
        })
    
    return JsonResponse({
        'success': True,
        'requests': results
    })


@login_required
def update_request_status(request):
    """
    API endpoint to update request status (Cancel or other status changes).
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    try:
        data = json.loads(request.body)
        request_id = data.get('request_id')
        new_status = data.get('status')
        
        if not request_id or not new_status:
            return JsonResponse({'error': 'request_id and status are required'}, status=400)
        
        # Get the request
        from requests.models import Request
        req = Request.objects.get(id=request_id)
        
        # Update status
        req.status = new_status
        req.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Request status updated to {new_status}'
        })
        
    except Request.DoesNotExist:
        return JsonResponse({'error': 'Request not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)