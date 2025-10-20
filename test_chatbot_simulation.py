#!/usr/bin/env python
import os
import sys
import django

# Add the project directory to Python path
sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_sales.settings')
django.setup()

from chatbot.views import try_manual_function_calls, extract_date_from_message

def test_chatbot_simulation():
    """Test chatbot function calling simulation"""
    print("=== TESTING CHATBOT SIMULATION ===")
    
    # Test the user's exact message
    user_message = "please check waht meeting rooms are available on 1st december"
    print(f"User message: {user_message}")
    
    # Test date extraction
    date_str = extract_date_from_message(user_message)
    print(f"Extracted date: {date_str}")
    
    # Test manual function calls
    result = try_manual_function_calls(user_message, 1)  # user_id = 1
    print(f"Manual function result: {result}")

if __name__ == "__main__":
    test_chatbot_simulation()
