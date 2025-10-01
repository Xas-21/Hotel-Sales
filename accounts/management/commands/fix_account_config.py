from django.core.management.base import BaseCommand
from requests.models import DynamicField


class Command(BaseCommand):
    help = 'Fix account configuration - add new choices and fix field types'

    def handle(self, *args, **options):
        self.stdout.write("Fixing account configuration...")
        
        # Fix account_type field - add all new choices
        try:
            account_type_field = DynamicField.objects.filter(name='account_type').first()
            if account_type_field:
                # Set all the choices including the new ones
                new_choices = {
                    'Company': 'Company',
                    'Government': 'Government', 
                    'Travel Agency': 'Travel Agency',
                    'Medical': 'Medical',
                    'Training and Consulting': 'Training and Consulting',
                    'Pharmaceuticals': 'Pharmaceuticals',
                    'Education': 'Education'
                }
                
                account_type_field.choices = new_choices
                account_type_field.save()
                self.stdout.write(
                    self.style.SUCCESS(f"✓ Updated account_type with {len(new_choices)} choices")
                )
                self.stdout.write(f"  Choices: {', '.join(new_choices.keys())}")
            else:
                self.stdout.write(
                    self.style.ERROR("✗ account_type field not found")
                )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"✗ Error updating account_type: {e}")
            )
        
        # Fix city field - change to text field
        try:
            # Deactivate the choice field
            city_choice_field = DynamicField.objects.filter(name='city', field_type='choice').first()
            if city_choice_field:
                city_choice_field.is_active = False
                city_choice_field.save()
                self.stdout.write("✓ Deactivated city choice field")
            
            # Activate and configure the text field
            city_text_field = DynamicField.objects.filter(name='city', field_type='char').first()
            if city_text_field:
                city_text_field.is_active = True
                city_text_field.field_type = 'text'  # Make it a textarea
                city_text_field.choices = {}  # Clear any choices
                city_text_field.save()
                self.stdout.write(
                    self.style.SUCCESS("✓ Activated city text field (textarea)")
                )
            else:
                self.stdout.write(
                    self.style.ERROR("✗ city char/text field not found")
                )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"✗ Error updating city field: {e}")
            )
        
        # Verify the changes
        self.stdout.write("\nVerification:")
        try:
            account_field = DynamicField.objects.filter(name='account_type', is_active=True).first()
            if account_field:
                self.stdout.write(f"Account type choices: {account_field.choices}")
            
            city_field = DynamicField.objects.filter(name='city', is_active=True).first()
            if city_field:
                self.stdout.write(f"City field type: {city_field.field_type}")
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"✗ Error verifying changes: {e}")
            )
        
        self.stdout.write(
            self.style.SUCCESS("\nAccount configuration fix completed!")
        )
