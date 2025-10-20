#!/usr/bin/env python
import os
import sys
import django

# Add the project directory to Python path
sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_sales.settings')
django.setup()

from datetime import datetime
from requests.models import Request, EventAgenda, SeriesGroupEntry
from accounts.models import Account
from sales_calls.models import SalesCall

def test_events_by_date():
    """Test the get_events_by_date function"""
    print("=== TESTING EVENTS BY DATE ===")
    
    # Test December 1st, 2025
    date_str = '2025-12-01'
    target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    print(f"Testing date: {target_date}")
    
    # Get event agendas for the date
    events = EventAgenda.objects.filter(
        event_date=target_date
    ).select_related('request', 'request__account')
    
    print(f"Found {events.count()} events for {target_date}")
    
    for event in events:
        print(f"Event: {event.event_name}")
        print(f"Meeting Room: {event.meeting_room_name}")
        print(f"Start Time: {event.start_time}")
        print(f"End Time: {event.end_time}")
        print(f"Account: {event.request.account.name if event.request.account else 'N/A'}")
        print(f"Request Type: {event.request.get_request_type_display()}")
        print(f"Status: {event.request.status}")
        print("---")

def test_all_events():
    """Test all events in the system"""
    print("=== TESTING ALL EVENTS ===")
    
    all_events = EventAgenda.objects.all().order_by('event_date')
    print(f"Total events in system: {all_events.count()}")
    
    for event in all_events:
        print(f"Date: {event.event_date}, Event: {event.event_name}, Room: {event.meeting_room_name}, Account: {event.request.account.name if event.request.account else 'N/A'}")

def test_requests():
    """Test all requests in the system"""
    print("=== TESTING ALL REQUESTS ===")
    
    all_requests = Request.objects.all().order_by('-created_at')
    print(f"Total requests in system: {all_requests.count()}")
    
    for req in all_requests[:10]:  # Show first 10
        print(f"ID: {req.id}, Type: {req.get_request_type_display()}, Account: {req.account.name if req.account else 'N/A'}, Status: {req.status}")

if __name__ == "__main__":
    test_events_by_date()
    test_all_events()
    test_requests()
