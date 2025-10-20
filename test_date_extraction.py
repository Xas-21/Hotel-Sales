#!/usr/bin/env python
import os
import sys
import django

# Add the project directory to Python path
sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_sales.settings')
django.setup()

from chatbot.views import extract_date_from_message

def test_date_extraction():
    """Test date extraction from various user messages"""
    test_messages = [
        "please check waht meeting rooms are available on 1st december",
        "what do I have on December 1st",
        "what events on 1st december 2025",
        "check availability for december 1st",
        "what do I have on November 25th",
        "what's on December 16th"
    ]
    
    for message in test_messages:
        date_str = extract_date_from_message(message)
        print(f"Message: '{message}'")
        print(f"Extracted date: {date_str}")
        print("---")

if __name__ == "__main__":
    test_date_extraction()
