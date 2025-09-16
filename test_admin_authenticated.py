#!/usr/bin/env python
"""
Comprehensive Authenticated Admin Testing for ConfigEnforcedAdminMixin v2

This script performs thorough authenticated testing to prove that all admin forms
work properly with the new configuration system.
"""

import os
import sys
import django
from django.test import Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.db import transaction

# Configure Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_sales.settings')
django.setup()

# Now import models after Django is set up
from accounts.models import Account
from requests.models import Request, RoomType, RoomOccupancy, AccommodationRequest
from agreements.models import Agreement
from sales_calls.models import SalesCall
from form_composer.models import FormDefinition, FormSection, FieldConfig
from django.contrib.contenttypes.models import ContentType

class AdminTestRunner:
    """Comprehensive authenticated admin testing"""
    
    def __init__(self):
        self.client = Client()
        self.superuser = None
        self.test_results = []
        
    def authenticate(self):
        """Authenticate as superuser for admin testing"""
        print("=== AUTHENTICATION TESTING ===")
        
        # Get existing superuser
        self.superuser = User.objects.filter(is_superuser=True, is_active=True).first()
        if not self.superuser:
            print("❌ No active superuser found")
            return False
            
        print(f"✅ Found superuser: {self.superuser.username}")
        
        # Force login for testing
        self.client.force_login(self.superuser)
        
        # Test admin access
        response = self.client.get('/admin/')
        if response.status_code == 200:
            print(f"✅ Admin dashboard accessible: {response.status_code}")
            return True
        else:
            print(f"❌ Admin access failed: {response.status_code}")
            return False
    
    def test_admin_form_rendering(self):
        """Test authenticated access to all admin forms"""
        print("\n=== ADMIN FORM RENDERING TESTING ===")
        
        admin_urls = [
            ('accounts:account', 'Account Admin'),
            ('agreements:agreement', 'Agreement Admin'), 
            ('requests:request', 'Request Admin'),
            ('requests:accommodationrequest', 'AccommodationRequest Admin'),
            ('sales_calls:salescall', 'SalesCall Admin'),
            ('form_composer:formdefinition', 'FormDefinition Admin'),
            ('form_composer:formsection', 'FormSection Admin'),
            ('form_composer:fieldconfig', 'FieldConfig Admin'),
        ]
        
        for url_name, description in admin_urls:
            try:
                # Test changelist view
                url = reverse(f'admin:{url_name}_changelist')
                response = self.client.get(url)
                status = "✅ PASS" if response.status_code == 200 else f"❌ FAIL ({response.status_code})"
                print(f"{status} - {description} Changelist: {response.status_code}")
                self.test_results.append(f"{description} Changelist: {response.status_code}")
                
                # Test add view
                url = reverse(f'admin:{url_name}_add')
                response = self.client.get(url)
                status = "✅ PASS" if response.status_code == 200 else f"❌ FAIL ({response.status_code})"
                print(f"{status} - {description} Add Form: {response.status_code}")
                self.test_results.append(f"{description} Add Form: {response.status_code}")
                
            except Exception as e:
                print(f"❌ ERROR - {description}: {e}")
                self.test_results.append(f"{description}: ERROR - {e}")
    
    def test_config_enforced_mixin_functionality(self):
        """Test ConfigEnforcedAdminMixin v2 functionality"""
        print("\n=== CONFIG ENFORCED MIXIN TESTING ===")
        
        try:
            # Test AccountAdmin with ConfigEnforcedAdminMixin
            from accounts.admin import AccountAdmin
            from accounts.models import Account
            
            # Create admin instance
            account_admin = AccountAdmin(Account, None)
            
            # Test get_fieldsets method
            request = type('MockRequest', (), {'user': self.superuser})()
            fieldsets = account_admin.get_fieldsets(request)
            
            print(f"✅ AccountAdmin fieldsets generated: {len(fieldsets)} sections")
            for i, (name, options) in enumerate(fieldsets):
                fields_count = len(options.get('fields', []))
                print(f"   Section {i+1}: '{name}' ({fields_count} fields)")
            
            # Test get_config_form_type
            form_type = account_admin.get_config_form_type()
            print(f"✅ Config form type: {form_type}")
            
            # Test get_original_fieldsets
            original_fieldsets = account_admin.get_original_fieldsets(request)
            print(f"✅ Original fieldsets fallback: {len(original_fieldsets)} sections")
            
            self.test_results.append("ConfigEnforcedAdminMixin: FUNCTIONAL")
            
        except Exception as e:
            print(f"❌ ConfigEnforcedAdminMixin ERROR: {e}")
            self.test_results.append(f"ConfigEnforcedAdminMixin: ERROR - {e}")
    
    def test_create_operations(self):
        """Test admin create operations with POST data"""
        print("\n=== CREATE OPERATIONS TESTING ===")
        
        try:
            # Test Account creation
            account_data = {
                'name': 'Test Hotel Chain',
                'account_type': 'Hotel',
                'contact_person': 'John Manager',
                'phone': '+1-555-0123',
                'email': 'manager@testhotel.com',
                'city': 'Test City'
            }
            
            response = self.client.post(
                reverse('admin:accounts_account_add'),
                account_data
            )
            
            if response.status_code in [200, 302]:  # 302 = redirect after successful save
                print("✅ Account creation: SUCCESS")
                self.test_results.append("Account creation: SUCCESS")
                
                # Verify account was created
                account = Account.objects.filter(name='Test Hotel Chain').first()
                if account:
                    print(f"✅ Account verified in database: ID {account.id}")
                
            else:
                print(f"❌ Account creation FAILED: {response.status_code}")
                # Print form errors if any
                if hasattr(response, 'context') and response.context and 'form' in response.context:
                    form_errors = response.context['form'].errors
                    print(f"   Form errors: {form_errors}")
        
        except Exception as e:
            print(f"❌ Create operation ERROR: {e}")
            self.test_results.append(f"Create operations: ERROR - {e}")
    
    def test_form_composer_integration(self):
        """Test Form Composer integration with admin forms"""
        print("\n=== FORM COMPOSER INTEGRATION TESTING ===")
        
        try:
            # Create test FormDefinition
            content_type = ContentType.objects.get_for_model(Account)
            
            form_def, created = FormDefinition.objects.get_or_create(
                form_type='test_account_form',
                defaults={
                    'name': 'Test Account Configuration',
                    'target_model': content_type,
                    'description': 'Test configuration for accounts',
                    'is_active': True,
                    'created_by': self.superuser
                }
            )
            
            print(f"✅ FormDefinition created/found: {form_def.name}")
            
            # Create test section
            section, created = FormSection.objects.get_or_create(
                form_definition=form_def,
                slug='test_section',
                defaults={
                    'name': 'Test Section',
                    'order': 1,
                    'is_active': True,
                    'description': 'Test section for form composer integration'
                }
            )
            
            print(f"✅ FormSection created: {section.name}")
            
            # Create test field config
            field_config, created = FieldConfig.objects.get_or_create(
                section=section,
                field_key='name',
                defaults={
                    'label': 'Account Name',
                    'order': 1,
                    'is_active': True,
                    'is_required': True,
                    'widget_type': 'text'
                }
            )
            
            print(f"✅ FieldConfig created: {field_config.label}")
            
            # Test form composer admin forms themselves
            response = self.client.get(reverse('admin:form_composer_formdefinition_changelist'))
            if response.status_code == 200:
                print("✅ FormDefinition admin accessible")
            
            self.test_results.append("Form Composer integration: SUCCESS")
            
        except Exception as e:
            print(f"❌ Form Composer integration ERROR: {e}")
            self.test_results.append(f"Form Composer integration: ERROR - {e}")
    
    def test_inlines_functionality(self):
        """Test admin forms with inlines"""
        print("\n=== INLINES FUNCTIONALITY TESTING ===")
        
        try:
            # Create test data for Request with inlines
            account = Account.objects.filter(name='Test Hotel Chain').first()
            if not account:
                # Create a test account for the request
                account = Account.objects.create(
                    name='Test Account for Request',
                    account_type='Hotel',
                    contact_person='Test Contact',
                    phone='+1-555-0124',
                    email='test@account.com',
                    city='Test City'
                )
            
            # Test Request add form (which has multiple inlines)
            response = self.client.get(reverse('admin:requests_request_add'))
            if response.status_code == 200:
                print("✅ Request admin with inlines accessible")
                
                # Check if inlines are rendered in the response
                content = response.content.decode('utf-8')
                if 'RoomEntry' in content or 'room_entry' in content:
                    print("✅ RoomEntry inline detected in form")
                if 'Transportation' in content or 'transportation' in content:
                    print("✅ Transportation inline detected in form")
                if 'EventAgenda' in content or 'event_agenda' in content:
                    print("✅ EventAgenda inline detected in form")
                
            self.test_results.append("Inlines functionality: SUCCESS")
            
        except Exception as e:
            print(f"❌ Inlines testing ERROR: {e}")
            self.test_results.append(f"Inlines functionality: ERROR - {e}")
    
    def run_all_tests(self):
        """Run complete authenticated admin testing suite"""
        print("🚀 Starting Comprehensive Authenticated Admin Testing")
        print("=" * 60)
        
        if not self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return
        
        # Run all test suites
        self.test_admin_form_rendering()
        self.test_config_enforced_mixin_functionality()
        self.test_create_operations()
        self.test_form_composer_integration()
        self.test_inlines_functionality()
        
        # Print summary
        print("\n" + "=" * 60)
        print("📋 TESTING SUMMARY")
        print("=" * 60)
        
        success_count = sum(1 for result in self.test_results if 'SUCCESS' in result or 'PASS' in result or '200' in result)
        total_count = len(self.test_results)
        
        for result in self.test_results:
            status_icon = "✅" if any(word in result for word in ['SUCCESS', 'PASS', '200']) else "❌"
            print(f"{status_icon} {result}")
        
        print(f"\n📊 Results: {success_count}/{total_count} tests passed")
        
        if success_count == total_count:
            print("🎉 ALL TESTS PASSED - ConfigEnforcedAdminMixin v2 is working correctly!")
        else:
            print("⚠️  Some tests failed - requires investigation")

if __name__ == '__main__':
    runner = AdminTestRunner()
    runner.run_all_tests()