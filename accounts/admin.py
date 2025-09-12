from django.contrib import admin
from .models import Account

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ['name', 'account_type', 'contact_person', 'phone', 'email', 'created_at']
    list_filter = ['account_type', 'created_at']
    search_fields = ['name', 'contact_person', 'email']
    ordering = ['name']
