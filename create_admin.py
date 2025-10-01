#!/usr/bin/env python
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_sales.settings')
django.setup()

from django.contrib.auth.models import User

# Create the admin user
try:
    user, created = User.objects.get_or_create(
        username='Abdullah',
        defaults={
            'email': 'abdullah@example.com',
            'is_staff': True,
            'is_superuser': True,
            'is_active': True
        }
    )
    
    # Set password
    user.set_password('Welcome@2025')
    user.is_staff = True
    user.is_superuser = True
    user.is_active = True
    user.save()
    
    print(f"✅ User {'created' if created else 'updated'} successfully!")
    print(f"Username: {user.username}")
    print(f"Email: {user.email}")
    print(f"Password: Welcome@2025")
    
except Exception as e:
    print(f"❌ Error: {e}")
