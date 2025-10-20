#!/usr/bin/env python
import os
import sys
import django

# Add the project directory to Python path
sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_sales.settings')
django.setup()

from chatbot.views import get_comprehensive_date_data

def test_comprehensive_data():
    """Test comprehensive date data function"""
    print("=== TESTING COMPREHENSIVE DATE DATA ===")
    
    # Test December 1st, 2025
    date_str = '2025-12-01'
    print(f"Testing date: {date_str}")
    
    result = get_comprehensive_date_data(date_str)
    print(f"Result: {result}")

if __name__ == "__main__":
    test_comprehensive_data()
