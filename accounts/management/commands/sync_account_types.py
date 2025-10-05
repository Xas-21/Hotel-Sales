from django.core.management.base import BaseCommand
from requests.models import DynamicField, DynamicSection
from accounts.models import Account
import json


class Command(BaseCommand):
    help = 'Synchronize account types from model to dynamic configuration'

    def handle(self, *args, **options):
        self.stdout.write("Synchronizing account types...")
        
        # Get or create the Account section
        section, created = DynamicSection.objects.get_or_create(
            name='accounts',
            defaults={
                'display_name': 'Account Information',
                'description': 'Core account fields',
                'is_core_section': True,
                'source_model': 'accounts.Account',
                'order': 1
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS(f"✓ Created section: {section.display_name}"))
        
        # Define all account type choices
        account_type_choices = {
            'Company': 'Company',
            'Government': 'Government',
            'Travel Agency': 'Travel Agency',
            'Medical': 'Medical',
            'Pharmaceuticals': 'Pharmaceuticals',
            'Education': 'Education',
            'Training and Consulting': 'Training and Consulting',
            'Hospitality': 'Hospitality',
            'Technology': 'Technology',
            'Finance': 'Finance',
            'Manufacturing': 'Manufacturing',
            'Real Estate': 'Real Estate',
            'Retail': 'Retail',
            'Other': 'Other',
        }
        
        # Get or create the account_type dynamic field
        field, created = DynamicField.objects.get_or_create(
            name='account_type',
            section=section,
            defaults={
                'display_name': 'Account Type',
                'field_type': 'choice',
                'is_core_field': True,
                'required': True,
                'is_active': True,
                'order': 2,
                'choices': account_type_choices,
                'help_text': 'Select the business segment for this account'
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS(f"✓ Created field: account_type"))
        else:
            # Update existing field with new choices
            field.choices = account_type_choices
            field.field_type = 'choice'
            field.is_active = True
            field.required = True
            field.save()
            self.stdout.write(self.style.SUCCESS(f"✓ Updated field: account_type"))
        
        self.stdout.write(self.style.SUCCESS(f"\n✓ Account type choices synchronized"))
        self.stdout.write(f"  Total choices: {len(account_type_choices)}")
        self.stdout.write(f"  Choices: {', '.join(account_type_choices.keys())}")

