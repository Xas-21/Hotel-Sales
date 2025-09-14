#!/usr/bin/env python
"""
Simple test script to verify core field creation functionality
"""
import os
import sys
import django
from django.conf import settings

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_sales.settings')
django.setup()

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from requests.models import DynamicSection, DynamicField
import json

def test_core_field_creation():
    """Test the core field creation functionality"""
    print("Testing Core Field Creation Functionality...")
    
    # Create a test user
    User = get_user_model()
    admin_user = User.objects.create_user(
        username='testadmin',
        email='test@test.com',
        password='testpass123',
        is_staff=True,
        is_superuser=True
    )
    
    # Create test client
    client = Client()
    client.force_login(admin_user)
    
    # Get or create a core section for testing
    section = DynamicSection.objects.filter(is_core_section=True).first()
    if not section:
        # Create a core section for testing
        section = DynamicSection.objects.create(
            name="Test Core Section",
            model_name="AccommodationRequest",
            source_model="requests.AccommodationRequest",
            is_core_section=True,
            order=1
        )
        print(f"Created test core section: {section.name}")
    else:
        print(f"Using existing core section: {section.name}")
    
    # Test 1: Create a new core field (create mode)
    print("\n1. Testing core field creation (create mode)...")
    create_data = {
        'name': 'test_new_field',
        'display_name': 'Test New Field',
        'field_type': 'CharField',
        'required': False,
        'core_mode': 'create',
        'section_name': 'Core Fields',
        'max_length': 255,
        'default_value': '',
        'order': 100
    }
    
    response = client.post(
        f'/configuration/add-field/{section.id}/',
        data=json.dumps(create_data),
        content_type='application/json'
    )
    
    if response.status_code == 200:
        result = response.json()
        if result.get('success'):
            print("✓ Successfully created new core field")
            field_id = result['field']['id']
            field = DynamicField.objects.get(id=field_id)
            print(f"  - Field name: {field.name}")
            print(f"  - Core mode: {field.core_mode}")
            print(f"  - Storage: {field.storage}")
            print(f"  - Is core field: {field.is_core_field}")
        else:
            print(f"✗ Failed to create core field: {result.get('error')}")
    else:
        print(f"✗ HTTP error: {response.status_code}")
        print(f"Response: {response.content}")
    
    # Test 2: Attempt to create conflicting field name (should fail)
    print("\n2. Testing name collision protection...")
    conflict_data = {
        'name': 'id',  # This should conflict with model field
        'display_name': 'Test Conflict Field',
        'field_type': 'CharField',
        'required': False,
        'core_mode': 'create'
    }
    
    response = client.post(
        f'/configuration/add-field/{section.id}/',
        data=json.dumps(conflict_data),
        content_type='application/json'
    )
    
    if response.status_code == 200:
        result = response.json()
        if not result.get('success') and 'conflicts' in result.get('error', ''):
            print("✓ Name collision protection working correctly")
        else:
            print(f"✗ Expected conflict error, got: {result}")
    else:
        print(f"✗ HTTP error: {response.status_code}")
    
    # Test 3: Create override field (if we can find a model field to override)
    print("\n3. Testing core field override...")
    override_data = {
        'name': 'test_override',
        'display_name': 'Test Override Field',
        'field_type': 'CharField',
        'required': False,
        'core_mode': 'override',
        'model_field_name': 'notes',  # Assuming this field exists
        'section_name': 'Core Fields'
    }
    
    response = client.post(
        f'/configuration/add-field/{section.id}/',
        data=json.dumps(override_data),
        content_type='application/json'
    )
    
    if response.status_code == 200:
        result = response.json()
        if result.get('success'):
            print("✓ Successfully created core override field")
            field_id = result['field']['id']
            field = DynamicField.objects.get(id=field_id)
            print(f"  - Field name: {field.name}")
            print(f"  - Core mode: {field.core_mode}")
            print(f"  - Model field name: {field.model_field_name}")
            print(f"  - Storage: {field.storage}")
        else:
            print(f"✗ Failed to create override field: {result.get('error')}")
    else:
        print(f"✗ HTTP error: {response.status_code}")
    
    print("\n=== Test Summary ===")
    print("Core field creation functionality test completed.")
    
    # Clean up test data
    admin_user.delete()
    if section.name == "Test Core Section":
        section.delete()
    
    return True

if __name__ == '__main__':
    test_core_field_creation()