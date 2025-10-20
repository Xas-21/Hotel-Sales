#!/usr/bin/env python
import os
import sys
import django

# Add the project directory to Python path
sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_sales.settings')
django.setup()

from chatbot.views import check_room_availability_ai, get_room_availability_by_date

def test_room_availability():
    """Test room availability functions"""
    print("=== TESTING ROOM AVAILABILITY ===")
    
    # Test December 1st, 2025
    date_str = '2025-12-01'
    print(f"Testing date: {date_str}")
    
    # Test get_room_availability_by_date
    print("\n--- get_room_availability_by_date ---")
    result1 = get_room_availability_by_date(date_str)
    print(f"Result: {result1}")
    
    # Test check_room_availability_ai
    print("\n--- check_room_availability_ai ---")
    result2 = check_room_availability_ai(date_str)
    print(f"Result: {result2}")
    
    # Test specific room
    print("\n--- check_room_availability_ai for AL JADIDA ---")
    result3 = check_room_availability_ai(date_str, 'AL JADIDA')
    print(f"Result: {result3}")

if __name__ == "__main__":
    test_room_availability()
