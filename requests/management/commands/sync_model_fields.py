"""
Management command to sync all model fields to the Configuration Dashboard.
Ensures field types and choices are exactly the same as in the admin models.
"""

from django.core.management.base import BaseCommand
from django.db import models
from django.apps import apps
from django.contrib import admin
from requests.models import DynamicSection, DynamicField
import json


class Command(BaseCommand):
    help = 'Sync all model fields to Configuration Dashboard with exact types and choices'

    def __init__(self):
        super().__init__()
        # Mapping Django field classes to our field type strings
        self.field_type_mapping = {
            models.CharField: 'char',
            models.TextField: 'text',
            models.EmailField: 'email',
            models.URLField: 'url',
            models.SlugField: 'slug',
            models.IntegerField: 'integer',
            models.BigIntegerField: 'integer',
            models.SmallIntegerField: 'integer',
            models.PositiveIntegerField: 'integer',
            models.PositiveSmallIntegerField: 'integer',
            models.DecimalField: 'decimal',
            models.FloatField: 'float',
            models.DateField: 'date',
            models.DateTimeField: 'datetime',
            models.TimeField: 'time',
            models.BooleanField: 'boolean',
            models.NullBooleanField: 'boolean',
            models.FileField: 'file',
            models.ImageField: 'image',
            models.ForeignKey: 'foreign_key',
            models.ManyToManyField: 'many_to_many',
            models.OneToOneField: 'foreign_key',
            models.AutoField: 'integer',
            models.BigAutoField: 'integer'
        }
        
        # Target apps to sync
        self.target_apps = ['accounts', 'requests', 'agreements', 'sales_calls']

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Starting Model Field Synchronization...\n'))
        
        # 1. Sync Admin Models to Core Sections
        self.sync_admin_models()
        
        # 2. Sync all fields with exact types and choices
        self.sync_all_fields()
        
        # 3. Fix specific field issues
        self.fix_specific_field_issues()
        
        self.stdout.write(self.style.SUCCESS('\n✅ Synchronization Complete!'))

    def sync_admin_models(self):
        """Ensure all admin models have corresponding DynamicSection entries"""
        self.stdout.write(self.style.WARNING('1. Syncing Admin Models to Core Sections:'))
        
        # Ensure admin autodiscovery has run
        admin.autodiscover()
        
        for model, admin_class in admin.site._registry.items():
            app_label = model._meta.app_label
            model_name = model._meta.object_name
            
            if app_label not in self.target_apps:
                continue
                
            source_model = f"{app_label}.{model_name}"
            
            # Get or create DynamicSection
            section, created = DynamicSection.objects.get_or_create(
                source_model=source_model,
                defaults={
                    'name': model_name,
                    'display_name': model._meta.verbose_name or model_name,
                    'description': f'Configuration for {model_name} model',
                    'is_core_section': True,
                    'is_active': True,
                    'order': 0
                }
            )
            
            if created:
                self.stdout.write(f"  ✓ Created section for {source_model}")
            else:
                self.stdout.write(f"  - Section exists for {source_model}")

    def sync_all_fields(self):
        """Sync all model fields with exact types and choices"""
        self.stdout.write(self.style.WARNING('\n2. Syncing All Model Fields:'))
        
        for section in DynamicSection.objects.filter(is_core_section=True):
            if not section.source_model:
                continue
                
            try:
                # Get the model class
                app_label, model_name = section.source_model.split('.')
                model = apps.get_model(app_label, model_name)
                
                self.stdout.write(f"\n  Processing {section.source_model}:")
                
                # Process each field in the model
                for field in model._meta.get_fields():
                    # Skip reverse relations and auto-created fields
                    if (hasattr(field, 'auto_created') and field.auto_created) or \
                       field.one_to_many or field.many_to_many:
                        continue
                    
                    # Get field type
                    field_type = self.get_field_type(field)
                    
                    # Get choices if available
                    choices = self.get_field_choices(field, model)
                    
                    # Get or create DynamicField
                    dynamic_field, created = DynamicField.objects.get_or_create(
                        section=section,
                        name=field.name,
                        defaults={
                            'display_name': getattr(field, 'verbose_name', field.name),
                            'field_type': field_type,
                            'required': not field.null if hasattr(field, 'null') else False,
                            'is_core_field': True,
                            'is_active': True,
                            'order': 0,
                            'choices': choices,
                            'max_length': getattr(field, 'max_length', None),
                            'default_value': self.get_default_value(field)
                        }
                    )
                    
                    if created:
                        self.stdout.write(f"    ✓ Created field: {field.name} ({field_type})")
                    else:
                        # Update existing field to ensure correct type and choices
                        updated = False
                        
                        # Always update field type to ensure accuracy
                        if dynamic_field.field_type != field_type:
                            dynamic_field.field_type = field_type
                            updated = True
                            
                        # Update choices if they've changed
                        if choices != dynamic_field.choices:
                            dynamic_field.choices = choices
                            updated = True
                            
                        # Update other attributes
                        if hasattr(field, 'max_length') and dynamic_field.max_length != field.max_length:
                            dynamic_field.max_length = field.max_length
                            updated = True
                            
                        if updated:
                            dynamic_field.save()
                            self.stdout.write(f"    ↻ Updated field: {field.name} ({field_type})")
                        else:
                            self.stdout.write(f"    - Field up-to-date: {field.name}")
                            
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ Error processing {section.source_model}: {e}"))

    def get_field_type(self, field):
        """Get the field type string for a Django model field"""
        field_class = field.__class__
        
        # Check for specific field types first
        if isinstance(field, models.ForeignKey):
            return 'foreign_key'
        elif isinstance(field, models.ManyToManyField):
            return 'many_to_many'
        elif isinstance(field, models.OneToOneField):
            return 'foreign_key'
        
        # Look up in mapping
        for django_field_class, type_string in self.field_type_mapping.items():
            if isinstance(field, django_field_class):
                # Special case: CharField with choices should be 'choice'
                if isinstance(field, models.CharField) and hasattr(field, 'choices') and field.choices:
                    return 'choice'
                return type_string
        
        # Default to char for unknown types
        return 'char'

    def get_field_choices(self, field, model):
        """Extract choices from a field, handling both field.choices and model constants"""
        choices_dict = {}
        
        # Check if field has choices attribute
        if hasattr(field, 'choices') and field.choices:
            for choice_value, choice_label in field.choices:
                choices_dict[choice_value] = choice_label
                
        # Special handling for known choice fields by name
        elif field.name in ['meeting_subject', 'business_potential', 'request_type', 'status', 'rate_type', 'account_type']:
            # Try to get choices from model constants
            constant_names = {
                'meeting_subject': 'MEETING_SUBJECT',
                'business_potential': 'BUSINESS_POTENTIAL', 
                'request_type': 'REQUEST_TYPES',
                'status': 'STATUS_CHOICES',
                'rate_type': 'RATE_TYPE_CHOICES',
                'account_type': 'ACCOUNT_TYPES'
            }
            
            constant_name = constant_names.get(field.name, field.name.upper() + '_CHOICES')
            
            if hasattr(model, constant_name):
                choices = getattr(model, constant_name)
                for choice_value, choice_label in choices:
                    choices_dict[choice_value] = choice_label
        
        return choices_dict if choices_dict else {}

    def get_default_value(self, field):
        """Get the default value for a field"""
        if hasattr(field, 'default') and field.default != models.NOT_PROVIDED:
            default = field.default
            if callable(default):
                try:
                    default = default()
                except:
                    return ''
            if default is True or default is False:
                return str(default).lower()
            return str(default) if default is not None else ''
        return ''

    def fix_specific_field_issues(self):
        """Fix specific known field issues"""
        self.stdout.write(self.style.WARNING('\n3. Fixing Specific Field Issues:'))
        
        # Fix boolean fields that might have incorrect types
        boolean_fields = ['follow_up_required', 'follow_up_completed', 'required', 'enabled', 
                         'is_active', 'is_core_field', 'is_refundable']
        
        for field_name in boolean_fields:
            fields = DynamicField.objects.filter(name=field_name)
            for field in fields:
                if field.field_type not in ['boolean', 'BooleanField']:
                    field.field_type = 'boolean'
                    field.choices = {}  # Clear any choices for boolean fields
                    field.save()
                    self.stdout.write(f"  ✓ Fixed boolean field: {field.name}")
        
        # Fix date fields that might have incorrect types
        date_fields = ['check_in_date', 'check_out_date', 'visit_date', 'start_date', 
                      'end_date', 'return_deadline', 'follow_up_date', 'request_received_date',
                      'payment_deadline', 'arrival_date', 'departure_date', 'event_date']
        
        for field_name in date_fields:
            fields = DynamicField.objects.filter(name=field_name)
            for field in fields:
                if field.field_type not in ['date', 'DateField']:
                    field.field_type = 'date'
                    field.save()
                    self.stdout.write(f"  ✓ Fixed date field: {field.name}")
        
        # Ensure choice fields have their choices properly synced
        self.stdout.write("\n  Syncing choice field options:")
        
        # Meeting Subject choices for SalesCall
        try:
            from sales_calls.models import SalesCall
            meeting_subject_fields = DynamicField.objects.filter(name='meeting_subject')
            for field in meeting_subject_fields:
                choices_dict = dict(SalesCall.MEETING_SUBJECT)
                if field.choices != choices_dict:
                    field.choices = choices_dict
                    field.field_type = 'choice'
                    field.save()
                    self.stdout.write(f"  ✓ Updated meeting_subject choices")
        except Exception as e:
            self.stdout.write(f"  ✗ Could not update meeting_subject: {e}")
        
        # Request Type choices
        try:
            from requests.models import Request as BookingRequest
            request_type_fields = DynamicField.objects.filter(name='request_type')
            for field in request_type_fields:
                choices_dict = dict(BookingRequest.REQUEST_TYPES)
                if field.choices != choices_dict:
                    field.choices = choices_dict
                    field.field_type = 'choice'
                    field.save()
                    self.stdout.write(f"  ✓ Updated request_type choices")
        except Exception as e:
            self.stdout.write(f"  ✗ Could not update request_type: {e}")
        
        # Account Type choices
        try:
            from accounts.models import Account
            account_type_fields = DynamicField.objects.filter(name='account_type')
            for field in account_type_fields:
                choices_dict = dict(Account.ACCOUNT_TYPES)
                if field.choices != choices_dict:
                    field.choices = choices_dict
                    field.field_type = 'choice'
                    field.save()
                    self.stdout.write(f"  ✓ Updated account_type choices")
        except Exception as e:
            self.stdout.write(f"  ✗ Could not update account_type: {e}")